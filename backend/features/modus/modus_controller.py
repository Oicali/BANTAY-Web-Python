# ================================================================================
# FILE: backend/features/modus_controller.py
# ================================================================================

from fastapi import HTTPException, Request
from shared.utils.audit_logger import log_audit

import config.database as db


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


INDEX_CRIMES = {
    "MURDER",
    "HOMICIDE",
    "PHYSICAL INJURIES",
    "RAPE",
    "ROBBERY",
    "THEFT",
    "CARNAPPING - MC",
    "CARNAPPING - MV",
    "SPECIAL COMPLEX CRIME",
}


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ── GET all modus ─────────────────────────────────────────────────────────────

async def get_all_modus(request: Request):
    try:
        sort_by = request.query_params.get("sort_by", "")

        if sort_by == "created_at":
            order_by = "created_at DESC"
        elif sort_by == "created_at_asc":
            order_by = "created_at ASC"
        else:
            order_by = "crime_type, modus_name"

        rows = await get_pool().fetch(
            f"SELECT * FROM crime_modus_reference ORDER BY {order_by}"
        )

        return {"success": True, "data": [dict(r) for r in rows]}

    except Exception as e:
        print(f"get_all_modus error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch modus list"},
        )


# ── GET one modus ─────────────────────────────────────────────────────────────

async def get_modus_by_id(request: Request):
    try:
        modus_id = request.path_params["id"]

        row = await get_pool().fetchrow(
            "SELECT * FROM crime_modus_reference WHERE id = $1",
            int(modus_id),
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "Not found"},
            )

        return {"success": True, "data": dict(row)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_modus_by_id error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch modus"},
        )


# ── POST create ───────────────────────────────────────────────────────────────

async def create_modus(request: Request):
    current_user = request.state.user

    try:
        body = await request.json()
        crime_type  = (body.get("crime_type")  or "").strip()
        modus_name  = (body.get("modus_name")  or "").strip()
        description = (body.get("description") or "").strip() or None

        if not crime_type or not modus_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "crime_type and modus_name are required",
                },
            )

        if crime_type.upper() not in INDEX_CRIMES:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "Invalid crime type"},
            )

        dup = await get_pool().fetchrow(
            """SELECT id FROM crime_modus_reference
               WHERE UPPER(crime_type) = $1 AND LOWER(modus_name) = LOWER($2)""",
            crime_type.upper(),
            modus_name,
        )

        if dup:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Modus already exists for this crime type",
                },
            )

        row = await get_pool().fetchrow(
            """INSERT INTO crime_modus_reference (crime_type, modus_name, description, is_active)
               VALUES ($1, $2, $3, true)
               RETURNING *""",
            crime_type.upper(),
            modus_name,
            description,
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Modus Created",
            description=f'Created modus "{modus_name}" for {crime_type.upper()}',
            action="CREATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "data": dict(row)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"create_modus error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to create modus"},
        )


# ── PATCH update ──────────────────────────────────────────────────────────────

async def update_modus(request: Request):
    current_user = request.state.user

    try:
        modus_id = request.path_params["id"]
        body     = await request.json()

        crime_type  = body.get("crime_type")
        modus_name  = body.get("modus_name")
        description = body.get("description")   # may be intentionally None/null
        is_active   = body.get("is_active")      # may be intentionally False

        row = await get_pool().fetchrow(
            """UPDATE crime_modus_reference
               SET
                 crime_type  = COALESCE($1, crime_type),
                 modus_name  = COALESCE($2, modus_name),
                 description = COALESCE($3, description),
                 is_active   = COALESCE($4, is_active),
                 updated_at  = NOW()
               WHERE id = $5
               RETURNING *""",
            crime_type.upper() if crime_type else None,
            modus_name or None,
            description if description is not None else None,
            is_active   if is_active   is not None else None,
            int(modus_id),
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "Not found"},
            )

        updated = dict(row)

        if is_active is False:
            event_name = "Modus Deactivated"
        elif is_active is True:
            event_name = "Modus Restored"
        else:
            event_name = "Modus Updated"

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name=event_name,
            description=f"Changes made with Modus ID {updated['id']}: {updated['modus_name']} ({updated['crime_type']})",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {"success": True, "data": updated}

    except HTTPException:
        raise
    except Exception as e:
        print(f"update_modus error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to update modus"},
        )