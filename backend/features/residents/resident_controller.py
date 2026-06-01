# ================================================================================
# FILE: backend/features/residents/resident_controller.py
# ================================================================================

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import cloudinary.uploader
from fastapi import HTTPException, Request

import config.cloudinary  # noqa: F401
import config.database as db
from shared.utils.audit_logger import log_audit


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── Helper: get barangay_code of logged-in user ───────────────────────────────

async def _get_user_barangay_code(user_id) -> Optional[str]:
    row = await get_pool().fetchrow(
        "SELECT barangay_code FROM barangay_details WHERE user_id = $1",
        user_id,
    )
    return row["barangay_code"] if row else None


# ── Cloudinary upload helper ──────────────────────────────────────────────────

async def _cloudinary_upload(buffer: bytes, public_id: str) -> str:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: cloudinary.uploader.upload(
            buffer,
            public_id=public_id,
            overwrite=True,
            folder="residents",
            resource_type="image",
        ),
    )
    return result["secure_url"]


# ── GET /residents ─────────────────────────────────────────────────────────────

async def get_residents(request: Request):
    try:
        user_id       = request.state.user["user_id"]
        barangay_code = await _get_user_barangay_code(user_id)

        if not barangay_code:
            raise HTTPException(
                status_code=403,
                detail={"success": False, "message": "No barangay assigned"},
            )

        params = request.query_params
        q             = (params.get("q") or "").strip()
        gender        = params.get("gender")
        civil_status  = params.get("civil_status")
        voter_status  = params.get("voter_status")

        conditions = ["barangay_code = $1", "is_active = true"]
        values: list = [barangay_code]

        def p() -> str:
            return f"${len(values)}"

        if q:
            values.append(f"%{q}%")
            n = p()
            conditions.append(
                f"(first_name ILIKE {n} OR last_name ILIKE {n} OR middle_name ILIKE {n})"
            )

        if gender:
            values.append(gender)
            conditions.append(f"LOWER(gender) = LOWER({p()})")

        if civil_status:
            values.append(civil_status)
            conditions.append(f"LOWER(civil_status) = LOWER({p()})")

        if voter_status:
            values.append(voter_status)
            conditions.append(f"LOWER(voter_status) = LOWER({p()})")

        where = " AND ".join(conditions)
        rows  = await get_pool().fetch(
            f"SELECT * FROM barangay_residents WHERE {where} ORDER BY last_name ASC, first_name ASC",
            *values,
        )

        return {"success": True, "data": [dict(r) for r in rows]}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_residents error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── POST /residents/import ────────────────────────────────────────────────────

async def import_residents(request: Request):
    current_user = request.state.user

    try:
        barangay_code = await _get_user_barangay_code(current_user["user_id"])

        if not barangay_code:
            raise HTTPException(
                status_code=403,
                detail={"success": False, "message": "No barangay assigned"},
            )

        form = await request.form()
        file = form.get("file")

        if not file:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "No file uploaded"},
            )

        buffer = await file.read()

        # openpyxl — parse workbook from bytes
        import io
        import openpyxl

        wb   = openpyxl.load_workbook(io.BytesIO(buffer), data_only=True)
        ws   = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 2:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "File is empty"},
            )

        # Header row → normalise to uppercase stripped strings
        headers = [str(h).strip().upper() if h is not None else "" for h in rows[0]]

        if "FIRST_NAME" not in headers or "LAST_NAME" not in headers:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Invalid template. Use the official Bantay Resident import template.",
                },
            )

        def col(row_dict: dict, key: str) -> Optional[str]:
            v = row_dict.get(key)
            if v is None or v == "":
                return None
            return str(v).strip() or None

        def parse_date(v) -> Optional[datetime]:
            if v is None or v == "":
                return None
            if isinstance(v, (int, float)):
                # Excel serial date → Python datetime
                from datetime import timedelta
                return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=v)
            if isinstance(v, datetime):
                return v
            try:
                d = datetime.fromisoformat(str(v))
                return d
            except Exception:
                return None

        inserted = 0
        skipped  = 0
        errors   = []

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for i, raw_row in enumerate(rows[1:], start=2):
                    row_dict = dict(zip(headers, raw_row))

                    first_name = col(row_dict, "FIRST_NAME")
                    last_name  = col(row_dict, "LAST_NAME")

                    if not first_name or not last_name:
                        errors.append({"row": i, "message": "Missing first or last name"})
                        skipped += 1
                        continue

                    await conn.execute(
                        """INSERT INTO barangay_residents
                               (barangay_code, first_name, middle_name, last_name, qualifier,
                                gender, date_of_birth, contact_number, house_street,
                                civil_status, voter_status, imported_by)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                        barangay_code,
                        first_name,
                        col(row_dict, "MIDDLE_NAME"),
                        last_name,
                        col(row_dict, "QUALIFIER"),
                        col(row_dict, "GENDER"),
                        parse_date(row_dict.get("DATE_OF_BIRTH")),
                        col(row_dict, "CONTACT_NUMBER"),
                        col(row_dict, "HOUSE_STREET"),
                        col(row_dict, "CIVIL_STATUS"),
                        col(row_dict, "VOTER_STATUS"),
                        current_user["user_id"],
                    )
                    inserted += 1

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Residents Imported",
            description=f"Imported {inserted} resident(s) to barangay {barangay_code} — {skipped} skipped",
            action="CREATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "summary": {"inserted": inserted, "skipped": skipped, "errors": errors}}

    except HTTPException:
        raise
    except Exception as e:
        print(f"import_residents error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── GET /residents/removed ────────────────────────────────────────────────────

async def get_removed_residents(request: Request):
    try:
        user_id       = request.state.user["user_id"]
        barangay_code = await _get_user_barangay_code(user_id)

        if not barangay_code:
            raise HTTPException(
                status_code=403,
                detail={"success": False, "message": "No barangay assigned"},
            )

        rows = await get_pool().fetch(
            """SELECT * FROM barangay_residents
               WHERE barangay_code = $1 AND is_active = false
               ORDER BY last_name ASC, first_name ASC""",
            barangay_code,
        )

        return {"success": True, "data": [dict(r) for r in rows]}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_removed_residents error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── GET /residents/:id ────────────────────────────────────────────────────────

async def get_resident_by_id(request: Request):
    try:
        user_id       = request.state.user["user_id"]
        resident_id   = request.path_params["id"]
        barangay_code = await _get_user_barangay_code(user_id)

        row = await get_pool().fetchrow(
            """SELECT * FROM barangay_residents
               WHERE resident_id = $1 AND barangay_code = $2 AND is_active = true""",
            int(resident_id),
            barangay_code,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "Resident not found"},
            )

        return {"success": True, "data": dict(row)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_resident_by_id error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── PUT /residents/:id ────────────────────────────────────────────────────────

async def update_resident(request: Request):
    current_user = request.state.user

    try:
        resident_id   = request.path_params["id"]
        barangay_code = await _get_user_barangay_code(current_user["user_id"])

        form = await request.form()

        def f(key: str) -> Optional[str]:
            v = form.get(key)
            return v.strip() if isinstance(v, str) and v.strip() else None

        first_name     = f("first_name")
        last_name      = f("last_name")
        middle_name    = f("middle_name")
        qualifier      = f("qualifier")
        gender         = f("gender")
        date_of_birth  = f("date_of_birth")
        contact_number = f("contact_number")
        house_street   = f("house_street")
        civil_status   = f("civil_status")
        voter_status   = f("voter_status")

        if not first_name or not last_name:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "First name and last name are required"},
            )

        if contact_number and not re.match(r"^09\d{9}$", contact_number):
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "Contact number must be 09XXXXXXXXX format"},
            )

        # Optional profile picture upload
        profile_picture: Optional[str] = None
        file = form.get("profile_picture")

        if file and hasattr(file, "read"):
            buffer          = await file.read()
            profile_picture = await _cloudinary_upload(buffer, f"resident_{resident_id}")

        # Build SET clause conditionally for profile_picture
        pic_sql = ", profile_picture = $13" if profile_picture else ""

        await get_pool().execute(
            f"""UPDATE barangay_residents SET
                    first_name     = $1,
                    middle_name    = $2,
                    last_name      = $3,
                    qualifier      = $4,
                    gender         = $5,
                    date_of_birth  = $6,
                    contact_number = $7,
                    house_street   = $8,
                    civil_status   = $9,
                    voter_status   = $10
                    {pic_sql}
                WHERE resident_id = $11 AND barangay_code = $12""",
            *([
                first_name, middle_name, last_name, qualifier,
                gender, date_of_birth, contact_number,
                house_street, civil_status, voter_status,
                int(resident_id), barangay_code,
            ] + ([profile_picture] if profile_picture else [])),
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Resident Updated",
            description=f"Updated resident ID {resident_id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "Resident updated", "profile_picture": profile_picture}

    except HTTPException:
        raise
    except Exception as e:
        print(f"update_resident error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── DELETE /residents/:id (soft delete) ───────────────────────────────────────

async def delete_resident(request: Request):
    current_user = request.state.user

    try:
        resident_id   = request.path_params["id"]
        barangay_code = await _get_user_barangay_code(current_user["user_id"])

        await get_pool().execute(
            "UPDATE barangay_residents SET is_active = false WHERE resident_id = $1 AND barangay_code = $2",
            int(resident_id),
            barangay_code,
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Resident Removed",
            description=f"Soft-deleted resident ID {resident_id} from barangay {barangay_code}",
            action="DELETE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "Resident removed"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"delete_resident error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )


# ── PUT /residents/:id/restore ────────────────────────────────────────────────

async def restore_resident(request: Request):
    current_user = request.state.user

    try:
        resident_id   = request.path_params["id"]
        barangay_code = await _get_user_barangay_code(current_user["user_id"])

        await get_pool().execute(
            "UPDATE barangay_residents SET is_active = true WHERE resident_id = $1 AND barangay_code = $2",
            int(resident_id),
            barangay_code,
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Resident Restored",
            description=f"Restored resident ID {resident_id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "Resident restored"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"restore_resident error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": str(e)},
        )