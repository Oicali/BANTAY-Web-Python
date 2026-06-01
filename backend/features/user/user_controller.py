# ================================================================================
# FILE: backend/features/user/user_controller.py
# ================================================================================

import hashlib
import json
import math
import os
import secrets
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Assumed local imports — adjust paths to match your project structure
# ---------------------------------------------------------------------------
# from config.database import pool
# from features.user.services.email_service import (
#     email_service, generate_username, generate_password,
#     send_verification_email, send_welcome_email
# )
# from features.user.validators.user_validator import UserValidator
# from shared.utils.audit_logger import log_audit, get_client_ip
# from features.notifications.notification_service import notify_all_by_role




# ── Placeholder DB / service helpers — replace with real implementations ───────
import config.database as db


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


async def db_fetch(sql: str, *args):
    return await get_pool().fetch(sql, *args)


async def db_fetchrow(sql: str, *args):
    return await get_pool().fetchrow(sql, *args)


async def db_execute(sql: str, *args):
    return await get_pool().execute(sql, *args)


async def db_fetchval(sql: str, *args):
    return await get_pool().fetchval(sql, *args)


def db_acquire():
    return get_pool().acquire()  # context manager — use with `async with`, not await

# ----------------------------------------

from shared.utils.audit_logger import log_audit, get_client_ip
from features.user.user_validator import UserValidator


def generate_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%?"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def slug_part(value: str) -> str:
    import re
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value or "user"


async def generate_username(first: str, middle: str, last: str, prefix: str, conn) -> str:
    base = f"{prefix}{slug_part(first)}{slug_part(last)}"
    username = base
    counter = 1

    while True:
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE username = $1",
            username,
        )
        if not existing:
            return username

        counter += 1
        username = f"{base}{counter}"


async def send_verification_email(to_email: str, first: str, last: str, verification_url: str) -> dict:
    print(f"Verification URL for {to_email}: {verification_url}")
    return {"success": True}


async def send_welcome_email(
    to_email: str,
    first: str,
    last: str,
    username: str,
    password: str,
    user_type: str,
    role: str,
) -> dict:
    print(f"Welcome email for {to_email}: username={username}, password={password}")
    return {"success": True}


async def notify_all_by_role(roles: list, payload: dict, exclude_id=None) -> None:
    # Temporary no-op until notification service is connected
    return None


# =============================================================================
# ENDPOINTS
# =============================================================================

# ── GET /user-management/users ────────────────────────────────────────────────
async def get_all_users(request: Request):
    try:
        query = request.query_params

        user_type = query.get("userType") or query.get("user_type") or "police"
        status = query.get("status")
        search = query.get("search")
        role = query.get("role")
        barangay_code = query.get("barangayCode") or query.get("barangay_code")

        page = int(query.get("page", 1))
        limit = int(query.get("limit", 20))

        if page < 1:
            page = 1
        if limit < 1:
            limit = 20

        offset = (page - 1) * limit

        conditions = ["u.user_type = $1"]
        params = [user_type]
        idx = 2

        if status and status != "all":
            if status == "active":
                status = "verified"
            conditions.append(f"u.status = ${idx}")
            params.append(status)
            idx += 1
        elif not status:
            conditions.append("u.status != 'deactivated'")

        if search:
            conditions.append(
                f"(u.username ILIKE ${idx} OR u.email ILIKE ${idx} OR "
                f"u.first_name ILIKE ${idx} OR u.last_name ILIKE ${idx})"
            )
            params.append(f"%{search}%")
            idx += 1

        if role and role != "all":
            conditions.append(f"r.role_name = ${idx}")
            params.append(role)
            idx += 1

        if barangay_code and barangay_code != "all":
            conditions.append(f"bd.barangay_code = ${idx}")
            params.append(barangay_code)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}"

        count_row = await db_fetchrow(
            f"""SELECT COUNT(*) AS total
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                {where}""",
            *params,
        )

        total = int(count_row["total"]) if count_row else 0

        rows = await db_fetch(
            f"""SELECT
                  u.user_id, u.username, u.email,
                  u.first_name, u.last_name, u.middle_name, u.suffix,
                  u.phone, u.alternate_phone, u.gender,
                  TO_CHAR(u.date_of_birth, 'YYYY-MM-DD') AS date_of_birth,
                  u.profile_picture,
                  u.status, u.last_login, u.created_at,
                  u.user_type, u.rank_id,
                  pr.rank_name AS rank,
                  pr.abbreviation AS rank_abbreviation,
                  r.role_id,
                  r.role_name AS role,
                  ua.region_code,
                  ua.province_code,
                  ua.municipality_code,
                  ua.barangay_code AS address_barangay_code,
                  ua.address_line,
                  bd.barangay_code AS assigned_barangay_code
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
                LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                {where}
                ORDER BY u.created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params,
            limit,
            offset,
        )

        return {
            "success": True,
            "users": [dict(r) for r in rows],
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": math.ceil(total / limit) if limit else 0,
            },
        }

    except Exception as e:
        print(f"get_all_users error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch users"},
        )

# ── GET /user-management/filter-options ───────────────────────────────────────
async def get_filter_options(request: Request):
    """GET FILTER OPTIONS."""
    current_user = request.state.user
    try:
        police_roles   = await db_fetch(
            "SELECT DISTINCT r.role_name FROM roles r WHERE r.user_type = 'police' ORDER BY r.role_name"
        )
        barangay_roles = await db_fetch(
            "SELECT DISTINCT r.role_name FROM roles r WHERE r.user_type = 'barangay' ORDER BY r.role_name"
        )
        return {
            "success":       True,
            "roles":         [r["role_name"] for r in police_roles],
            "barangayRoles": [r["role_name"] for r in barangay_roles],
        }
    except Exception as e:
        print(f"get_filter_options error: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail={"success": False, "message": "Failed to fetch filter options"})


# ── GET /user-management/users/{id} ───────────────────────────────────────────
async def get_user_by_id(request: Request):
    user_id = request.path_params["id"]

    try:
        row = await db_fetchrow(
            """SELECT
                 u.user_id, u.username, u.email,
                 u.first_name, u.last_name, u.middle_name, u.suffix,
                 u.phone, u.alternate_phone, u.gender,
                 TO_CHAR(u.date_of_birth, 'YYYY-MM-DD') AS date_of_birth,
                 u.profile_picture,
                 u.status, u.last_login, u.created_at,
                 u.user_type, u.rank_id,
                 pr.rank_name AS rank, pr.abbreviation AS rank_abbreviation,
                 r.role_id, r.role_name AS role,
                 ua.region_code, ua.province_code, ua.municipality_code,
                 ua.barangay_code AS address_barangay_code, ua.address_line,
                 bd.barangay_code AS assigned_barangay_code
               FROM users u
               LEFT JOIN roles r ON u.role_id = r.role_id
               LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
               LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
               LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
               WHERE u.user_id = $1""",
            user_id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "User not found"},
            )

        return {"success": True, "user": dict(row)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_user_by_id error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch user"},
        )

# ── POST /user-management/users ───────────────────────────────────────────────
async def register_user(request: Request):
    current_user = request.state.user

    form = await request.form()

    def f(key):
        return (form.get(key) or "").strip()

    def cap(s: str) -> str:
        return s[0].upper() + s[1:].lower() if s else ""

    # Read raw form values (camelCase — matches what frontend sends)
    user_type            = f("userType")
    email                = f("email").lower()
    first_name           = f("firstName")
    last_name            = f("lastName")
    middle_name          = f("middleName")
    suffix               = f("suffix")
    phone                = f("phone")
    alternate_phone      = f("alternatePhone")
    gender               = f("gender")
    date_of_birth        = f("dateOfBirth")
    region_code          = f("regionCode") or None
    province_code        = f("provinceCode") or None
    municipality_code    = f("municipalityCode") or None
    barangay_code        = f("barangay") or f("barangayCode") or None
    address_line         = f("addressLine") or None
    role                 = f("role")
    rank_id              = f("rankId") or None

    # Capitalized versions
    trimmed_email        = email
    trimmed_first        = cap(first_name)
    trimmed_last         = cap(last_name)
    trimmed_middle       = cap(middle_name)
    trimmed_suffix       = suffix
    trimmed_phone        = phone
    trimmed_alt_phone    = alternate_phone or None
    trimmed_region       = region_code
    trimmed_province     = province_code
    trimmed_municipality = municipality_code
    trimmed_barangay     = barangay_code
    trimmed_address_line = address_line

    # Pass camelCase body to validator — same shape as JS req.body
    body = {
        "userType":         user_type,
        "email":            trimmed_email,
        "firstName":        trimmed_first,
        "lastName":         trimmed_last,
        "middleName":       trimmed_middle or None,
        "suffix":           trimmed_suffix or None,
        "phone":            trimmed_phone,
        "alternatePhone":   trimmed_alt_phone,
        "gender":           gender,
        "dateOfBirth":      date_of_birth,
        "regionCode":       trimmed_region,
        "provinceCode":     trimmed_province,
        "municipalityCode": trimmed_municipality,
        "barangay":         trimmed_barangay,
        "barangayCode":     trimmed_barangay,
        "addressLine":      trimmed_address_line,
        "role":             role,
        "rankId":           rank_id,
        # also snake_case aliases in case validator checks either
        "user_type":        user_type,
        "first_name":       trimmed_first,
        "last_name":        trimmed_last,
        "middle_name":      trimmed_middle or None,
        "phone":            trimmed_phone,
        "alternate_phone":  trimmed_alt_phone,
        "region_code":      trimmed_region,
        "province_code":    trimmed_province,
        "municipality_code":trimmed_municipality,
        "barangay_code":    trimmed_barangay,
        "address_line":     trimmed_address_line,
        "date_of_birth":    date_of_birth,
        "rank_id":          rank_id,
    }

    async with db_acquire() as conn:
        try:
            validation = await UserValidator.validate_registration(body, conn)
            print(f"DEBUG validation body: {body}")        # <-- add here
            print(f"DEBUG validation result: {validation}") # <-- add here
            if not validation.get("is_valid", validation.get("isValid", False)):
                raise HTTPException(status_code=400, detail={
                    "success": False,
                    "message": "Validation failed",
                    "errors": validation.get("errors", {}),
                })

            role_row = await conn.fetchrow(
                "SELECT role_id FROM roles WHERE role_name = $1 AND user_type = $2",
                role, user_type,
            )
            if not role_row:
                raise HTTPException(status_code=400, detail={
                    "success": False,
                    "message": f"Invalid role '{role}' for {user_type} user",
                    "errors": {"role": f"Invalid role for {user_type} user"},
                })
            role_id = role_row["role_id"]

            await conn.execute("BEGIN")

            username       = await generate_username(
                trimmed_first, trimmed_middle or "", trimmed_last,
                "pnp" if user_type == "police" else "brgy",
                conn,
            )
            plain_password = generate_password()
            hashed         = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt(10)).decode()

            user_row = await conn.fetchrow(
                """INSERT INTO users (
                     username, email, password,
                     first_name, last_name, middle_name, suffix,
                     phone, alternate_phone,
                     gender, date_of_birth,
                     user_type, role_id, rank_id,
                     status, created_at
                   ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'unverified',CURRENT_TIMESTAMP)
                   RETURNING user_id""",
                username, trimmed_email, hashed,
                trimmed_first, trimmed_last, trimmed_middle or None, trimmed_suffix or None,
                trimmed_phone, trimmed_alt_phone or None,
                gender, date_of_birth,
                user_type, role_id,
                int(rank_id) if rank_id else None,
            )
            user_id = user_row["user_id"]

            await conn.execute(
                """INSERT INTO user_addresses
                     (user_id, region_code, province_code, municipality_code, barangay_code, address_line)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                user_id, trimmed_region, trimmed_province,
                trimmed_municipality, trimmed_barangay, trimmed_address_line,
            )

            if user_type == "barangay":
                await conn.execute(
                    "INSERT INTO barangay_details (user_id, barangay_code) VALUES ($1,$2)",
                    user_id, trimmed_barangay,
                )

            raw_token  = secrets.token_hex(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            from datetime import datetime, timezone, timedelta
            token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

            await conn.execute(
                "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES ($1,$2,$3)",
                user_id, token_hash, token_expiry,
            )

            credentials_json = json.dumps({
                "username": username,
                "password": plain_password,
                "userType": user_type,
                "role":     role,
            })
            await conn.execute(
                """INSERT INTO pending_credentials (user_id, credentials, expires_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id) DO UPDATE
                     SET credentials = EXCLUDED.credentials,
                         expires_at  = EXCLUDED.expires_at""",
                user_id, credentials_json, token_expiry,
            )

            await conn.execute("COMMIT")

            backend_url      = os.getenv("BACKEND_URL", f"http://localhost:{os.getenv('PORT', 5000)}")
            verification_url = f"{backend_url}/user-management/verify-account?token={raw_token}"

            email_result = await send_verification_email(
                trimmed_email, trimmed_first, trimmed_last, verification_url
            )

            await log_audit(
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                event_name="User Registered",
                description=f"Registered new {user_type} user \"{username}\" with role {role}",
                action="CREATE",
                status="success",
                source="Web Portal",
                ip_address=get_client_ip(request),
            )

            await notify_all_by_role(
                ["Administrator", "Technical Administrator"],
                {
                    "sender_id":   current_user["user_id"],
                    "sender_name": current_user["username"],
                    "type":        "USER_REGISTERED",
                    "title":       "New Account Created",
                    "message":     f"New {user_type} account created: {username} ({role})",
                    "link_to":     "/user-management",
                },
                current_user["user_id"],
            )

            return {
                "success": True,
                "message": f"Account created. A verification email has been sent to {trimmed_email}.",
                "user": {
                    "userId":                user_id,
                    "username":              username,
                    "email":                 trimmed_email,
                    "firstName":             trimmed_first,
                    "lastName":              trimmed_last,
                    "userType":              user_type,
                    "role":                  role,
                    "status":                "unverified",
                    "verificationEmailSent": email_result.get("success", False),
                },
            }

        except HTTPException:
            await conn.execute("ROLLBACK")
            raise
        except Exception as e:
            await conn.execute("ROLLBACK")
            print(f"register_user error: {e}")
            raise HTTPException(status_code=500, detail={
                "success": False,
                "message": "Registration failed",
            })

# ── GET /user-management/verify-account ──────────────────────────────────────
async def verify_account(request: Request):
    from datetime import datetime, timezone

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    token = request.query_params.get("token")

    if not token:
        return RedirectResponse(f"{frontend_url}/verification-success?status=invalid")

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    async with db_acquire() as conn:
        try:
            token_row = await conn.fetchrow(
                """SELECT
                     t.token_id, t.user_id, t.expires_at, t.is_revoked,
                     u.status, u.email, u.first_name, u.last_name,
                     u.username, u.user_type,
                     r.role_name AS role
                   FROM tokens t
                   JOIN users u ON t.user_id = u.user_id
                   LEFT JOIN roles r ON u.role_id = r.role_id
                   WHERE t.token_hash = $1""",
                token_hash,
            )

            if not token_row:
                return RedirectResponse(f"{frontend_url}/verification-success?status=invalid")
            if token_row["is_revoked"]:
                return RedirectResponse(f"{frontend_url}/verification-success?status=used")
            if token_row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                return RedirectResponse(f"{frontend_url}/verification-success?status=expired")
            if token_row["status"] == "verified":
                return RedirectResponse(f"{frontend_url}/verification-success?status=already_verified")

            user_id = token_row["user_id"]

            await conn.execute("BEGIN")

            await conn.execute(
                "UPDATE users SET status = 'verified', updated_at = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id,
            )
            await conn.execute(
                "UPDATE tokens SET is_revoked = TRUE, revoked_at = CURRENT_TIMESTAMP WHERE token_hash = $1",
                token_hash,
            )

            cred_row       = await conn.fetchrow(
                "SELECT credentials FROM pending_credentials WHERE user_id = $1", user_id
            )
            username       = token_row["username"]
            plain_password = None
            user_type      = token_row["user_type"]
            role           = token_row["role"]

            if cred_row:
                try:
                    creds          = json.loads(cred_row["credentials"])
                    username       = creds.get("username", username)
                    plain_password = creds.get("password")
                    user_type      = creds.get("userType", user_type)
                    role           = creds.get("role", role)
                except Exception as parse_err:
                    print(f"Failed to parse pending credentials: {parse_err}")
                await conn.execute(
                    "DELETE FROM pending_credentials WHERE user_id = $1", user_id
                )

            await conn.execute("COMMIT")

            if plain_password:
                email_result = await send_welcome_email(
                    token_row["email"], token_row["first_name"], token_row["last_name"],
                    username, plain_password, user_type, role,
                )
                if not email_result.get("success"):
                    print(f"Failed to send welcome email: {email_result.get('message')}")

            print(f"Account verified and activated: {username}")
            return RedirectResponse(f"{frontend_url}/verification-success?status=success")

        except Exception as e:
            await conn.execute("ROLLBACK")
            print(f"verify_account error: {e}")
            return RedirectResponse(f"{frontend_url}/verification-success?status=error")

# ── POST /user-management/users/{id}/resend-verification ──────────────────────
async def resend_verification_email(request: Request):
    current_user = request.state.user
    id = request.path_params["id"]
    from datetime import datetime, timezone, timedelta

    async with db_acquire() as conn:
        try:
            user_row = await conn.fetchrow(
                """SELECT u.user_id, u.email, u.first_name, u.last_name, u.username,
                          u.status, u.user_type, r.role_name AS role
                   FROM users u
                   LEFT JOIN roles r ON u.role_id = r.role_id
                   WHERE u.user_id = $1""",
                id,
            )
            if not user_row:
                raise HTTPException(status_code=404, detail={"success": False, "message": "User not found"})
            if user_row["status"] != "unverified":
                raise HTTPException(status_code=400, detail={
                    "success": False,
                    "message": f"Account is already {user_row['status']}. Verification email is only for unverified accounts.",
                })

            await conn.execute("BEGIN")

            await conn.execute(
                "UPDATE tokens SET is_revoked = TRUE, revoked_at = CURRENT_TIMESTAMP WHERE user_id = $1 AND is_revoked = FALSE",
                user_row["user_id"],
            )

            cred_row       = await conn.fetchrow(
                "SELECT credentials FROM pending_credentials WHERE user_id = $1", user_row["user_id"]
            )
            username       = user_row["username"]
            plain_password = None
            user_type      = user_row["user_type"]
            role           = user_row["role"]

            if cred_row:
                try:
                    creds          = json.loads(cred_row["credentials"])
                    username       = creds.get("username", username)
                    plain_password = creds.get("password")
                    user_type      = creds.get("userType", user_type)
                    role           = creds.get("role", role)
                except Exception as parse_err:
                    print(f"Failed to parse pending credentials: {parse_err}")

            if not plain_password:
                plain_password = generate_password()
                hashed         = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt(10)).decode()
                await conn.execute(
                    "UPDATE users SET password = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                    hashed, user_row["user_id"],
                )

            raw_token    = secrets.token_hex(32)
            token_hash   = hashlib.sha256(raw_token.encode()).hexdigest()
            token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

            await conn.execute(
                "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES ($1,$2,$3)",
                user_row["user_id"], token_hash, token_expiry,
            )

            credentials_json = json.dumps({
                "username": username,
                "password": plain_password,
                "userType": user_type,
                "role":     role,
            })
            await conn.execute(
                """INSERT INTO pending_credentials (user_id, credentials, expires_at)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id) DO UPDATE
                     SET credentials = EXCLUDED.credentials,
                         expires_at  = EXCLUDED.expires_at""",
                user_row["user_id"], credentials_json, token_expiry,
            )

            await conn.execute("COMMIT")

            backend_url      = os.getenv("BACKEND_URL", f"http://localhost:{os.getenv('PORT', 5000)}")
            verification_url = f"{backend_url}/user-management/verify-account?token={raw_token}"

            email_result = await send_verification_email(
                user_row["email"], user_row["first_name"], user_row["last_name"], verification_url
            )

            await log_audit(
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                event_name="Verification Email Resent",
                description=f"Resent verification email to user \"{username}\" ({user_row['email']})",
                action="CREATE",
                status="success",
                source="Web Portal",
                ip_address=get_client_ip(request),
            )

            return {
                "success":   True,
                "message":   f"Verification email resent to {user_row['email']}",
                "emailSent": email_result.get("success", False),
            }

        except HTTPException:
            await conn.execute("ROLLBACK")
            raise
        except Exception as e:
            await conn.execute("ROLLBACK")
            print(f"resend_verification_email error: {e}")
            raise HTTPException(status_code=500, detail={"success": False, "message": "Failed to resend verification email"})

# ── PUT /user-management/users/{id} ───────────────────────────────────────────
async def update_user(request: Request):
    current_user = request.state.user
    id = request.path_params["id"]
    try:
        body = await request.json()
    except Exception:
        body = {}

    print(f"DEBUG update_user body: {body}")  # remove after confirming

    if current_user.get("role") != "Technical Administrator":
        raise HTTPException(status_code=403, detail={
            "success": False, "message": "Only technical administrators can update user information"
        })

    async with db_acquire() as conn:
        try:
            existing = await conn.fetchrow(
                "SELECT user_id, user_type, email, phone, alternate_phone FROM users WHERE user_id = $1", id
            )
            if not existing:
                raise HTTPException(status_code=404, detail={"success": False, "message": "User not found"})

            validation = await UserValidator.validate_update(body, dict(existing), conn)
            print(f"DEBUG validation body: {body}")        # <-- add here
            print(f"DEBUG validation result: {validation}") # <-- add here
            if not validation.get("is_valid", validation.get("isValid", False)):
                raise HTTPException(status_code=400, detail={
                    "success": False, "message": "Validation failed", "errors": validation.get("errors", {})
                })

            role_id = None
            if body.get("role"):
                role_row = await conn.fetchrow(
                    "SELECT role_id FROM roles WHERE role_name = $1 AND user_type = $2",
                    body.get("role"), existing["user_type"],
                )
                if not role_row:
                    raise HTTPException(status_code=400, detail={
                        "success": False,
                        "message": f"Invalid role '{body.get('role')}' for {existing['user_type']} user",
                    })
                role_id = role_row["role_id"]

            def cap(s):
                return s[0].upper() + s[1:].lower() if s else None

            # Handle both camelCase and snake_case
            trimmed_email     = (body.get("email") or "").lower().strip() or None
            trimmed_first     = cap((body.get("firstName") or body.get("first_name") or "").strip()) or None
            trimmed_last      = cap((body.get("lastName") or body.get("last_name") or "").strip()) or None
            trimmed_middle    = cap((body.get("middleName") or body.get("middle_name") or "").strip())
            trimmed_suffix    = (body.get("suffix") or "").strip()
            trimmed_phone     = (body.get("phone") or "").strip()
            trimmed_alt_phone = (body.get("alternatePhone") or body.get("alternate_phone") or "").strip()

            date_of_birth = body.get("dateOfBirth")     or body.get("date_of_birth")
            gender        = body.get("gender")
            rank_id       = body.get("rankId")          or body.get("rank_id")
            new_password  = body.get("newPassword")     or body.get("new_password")

            region        = body.get("regionCode")       or body.get("region_code")
            province      = body.get("provinceCode")     or body.get("province_code")
            municipality  = body.get("municipalityCode") or body.get("municipality_code")
            barangay      = body.get("barangayCode")     or body.get("barangay_code")
            addr_line     = body.get("addressLine")      or body.get("address_line")
            assigned_brgy = body.get("assignedBarangayCode") or body.get("assigned_barangay_code")

            fields  = []
            values  = []
            p       = 1

            if trimmed_email:
                fields.append(f"email = ${p}");           values.append(trimmed_email);      p += 1
            if trimmed_first:
                fields.append(f"first_name = ${p}");      values.append(trimmed_first);      p += 1
            if trimmed_last:
                fields.append(f"last_name = ${p}");       values.append(trimmed_last);       p += 1

            fields.append(f"middle_name = ${p}");         values.append(trimmed_middle);     p += 1
            fields.append(f"suffix = ${p}");              values.append(trimmed_suffix or None); p += 1

            if date_of_birth:
                fields.append(f"date_of_birth = ${p}");   values.append(date_of_birth);      p += 1
            if gender:
                fields.append(f"gender = ${p}");          values.append(gender);             p += 1
            if trimmed_phone:
                fields.append(f"phone = ${p}");           values.append(trimmed_phone);      p += 1

            fields.append(f"alternate_phone = ${p}");     values.append(trimmed_alt_phone or None); p += 1

            if role_id:
                fields.append(f"role_id = ${p}");         values.append(role_id);            p += 1
            if rank_id is not None:
                fields.append(f"rank_id = ${p}");         values.append(int(rank_id) if rank_id else None); p += 1
            if new_password:
                hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(10)).decode()
                fields.append(f"password = ${p}");        values.append(hashed);             p += 1

            fields.append("updated_at = CURRENT_TIMESTAMP")

            if len(fields) == 1:
                raise HTTPException(status_code=400, detail={
                    "success": False, "message": "No fields provided to update"
                })

            values.append(id)

            print(f"DEBUG SQL fields: {fields}")
            print(f"DEBUG values count: {len(values)}, p={p}")

            # ── Use asyncpg transaction API instead of raw BEGIN/COMMIT ──
            async with conn.transaction():
                await conn.execute(
                    f"UPDATE users SET {', '.join(fields)} WHERE user_id = ${p}",
                    *values,
                )

                # ── Address update ─────────────────────────────────────────
                addr_fields = []
                addr_values = []
                ap          = 1

                if region:
                    addr_fields.append(f"region_code = ${ap}");        addr_values.append(region);        ap += 1
                if province:
                    addr_fields.append(f"province_code = ${ap}");      addr_values.append(province);      ap += 1
                if municipality:
                    addr_fields.append(f"municipality_code = ${ap}");  addr_values.append(municipality);  ap += 1

                effective_brgy = (
                    assigned_brgy or barangay or None
                    if existing["user_type"] == "barangay"
                    else barangay or None
                )
                if effective_brgy:
                    addr_fields.append(f"barangay_code = ${ap}");      addr_values.append(effective_brgy); ap += 1
                if addr_line is not None:
                    addr_fields.append(f"address_line = ${ap}");       addr_values.append(addr_line.strip() if addr_line else None); ap += 1

                if addr_fields:
                    addr_values.append(id)
                    await conn.execute(
                        f"UPDATE user_addresses SET {', '.join(addr_fields)} WHERE user_id = ${ap}",
                        *addr_values,
                    )

                # ── Barangay details ───────────────────────────────────────
                if existing["user_type"] == "barangay":
                    brgy = assigned_brgy or barangay
                    if brgy:
                        await conn.execute(
                            "UPDATE barangay_details SET barangay_code = $1 WHERE user_id = $2",
                            brgy, id,
                        )

            await log_audit(
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                event_name="User Updated",
                description=f"Updated user ID {id}",
                action="UPDATE",
                status="success",
                source="Web Portal",
                ip_address=get_client_ip(request),
            )
            return {"success": True, "message": "User updated successfully"}

        except HTTPException:
            raise
        except Exception as e:
            print(f"update_user error: {e}")
            raise HTTPException(status_code=500, detail={"success": False, "message": "Failed to update user"})

# ── POST /user-management/users/{id}/deactivate ───────────────────────────────
async def deactivate_user(request: Request):
    current_user = request.state.user
    id = request.path_params["id"]
    body = await request.json()
    admin_password = body.get("admin_password") or body.get("adminPassword")
    """DEACTIVATE USER."""
    from fastapi import HTTPException

    if not admin_password:
        raise HTTPException(status_code=400, detail={"success": False, "message": "Administrator password is required"})

    try:
        admin_row = await db_fetchrow(
            "SELECT password FROM users WHERE user_id = $1", current_user["user_id"]
        )
        if not admin_row:
            raise HTTPException(status_code=401, detail={"success": False, "message": "Admin user not found"})
        if not bcrypt.checkpw(admin_password.encode(), admin_row["password"].encode()):
            raise HTTPException(status_code=401, detail={"success": False, "message": "Incorrect password"})

        result = await db_execute(
            "UPDATE users SET status = 'deactivated', updated_at = NOW() WHERE user_id = $1", id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail={"success": False, "message": "User not found"})

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Deactivated",
            description=f"Deactivated user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )
        return {"success": True, "message": "User deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"deactivate_user error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": "Failed to deactivate user"})


# ── POST /user-management/users/{id}/lock ─────────────────────────────────────
async def lock_user(request: Request):
    """LOCK USER ACCOUNT."""
    current_user = request.state.user
    id = request.path_params["id"]

    if current_user.get("role") != "Technical Administrator":
        raise HTTPException(
            status_code=403,
            detail={
                "success": False,
                "message": "Only technical administrators can lock user accounts",
            },
        )

    if str(current_user["user_id"]) == str(id):
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "message": "You cannot lock your own account",
            },
        )

    try:
        row = await db_fetchrow(
            "SELECT user_id, status FROM users WHERE user_id = $1",
            id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if row["status"] == "locked":
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Account is already locked",
                },
            )

        await db_execute(
            "UPDATE users SET status = 'locked', updated_at = CURRENT_TIMESTAMP WHERE user_id = $1",
            id,
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Locked",
            description=f"Locked account for user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        await notify_all_by_role(
            ["Administrator", "Technical Administrator"],
            {
                "sender_id": current_user["user_id"],
                "sender_name": current_user["username"],
                "type": "ACCOUNT_LOCKED",
                "title": "Account Locked",
                "message": f"{current_user['username']} locked account ID {id}",
                "link_to": "/user-management",
            },
            current_user["user_id"],
        )

        return {
            "success": True,
            "message": "Account locked successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"lock_user error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to lock account",
            },
        )

# ── POST /user-management/users/{id}/unlock ───────────────────────────────────
async def unlock_user(request: Request):
    """UNLOCK USER ACCOUNT."""
    current_user = request.state.user
    id = request.path_params["id"]

    if current_user.get("role") != "Technical Administrator":
        raise HTTPException(
            status_code=403,
            detail={
                "success": False,
                "message": "Only technical administrators can unlock user accounts",
            },
        )

    try:
        row = await db_fetchrow(
            "SELECT user_id, status FROM users WHERE user_id = $1",
            id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if row["status"] != "locked":
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Account is not locked",
                },
            )

        await db_execute(
            """UPDATE users
               SET status = 'verified',
                   failed_login_attempts = 0,
                   lockout_until = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = $1""",
            id,
        )

        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Unlocked",
            description=f"Unlocked account for user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        await notify_all_by_role(
            ["Administrator", "Technical Administrator"],
            {
                "sender_id": current_user["user_id"],
                "sender_name": current_user["username"],
                "type": "ACCOUNT_UNLOCKED",
                "title": "Account Unlocked",
                "message": f"{current_user['username']} unlocked account ID {id}",
                "link_to": "/user-management",
            },
            current_user["user_id"],
        )

        return {
            "success": True,
            "message": "Account unlocked successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"unlock_user error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to unlock account",
            },
        )

# ── GET /user-management/roles ────────────────────────────────────────────────
async def get_all_roles(request: Request):
    try:
        rows = await db_fetch(
            "SELECT role_id, role_name, user_type FROM roles ORDER BY user_type, role_name"
        )

        return {
            "success": True,
            "roles": [dict(r) for r in rows],
        }

    except Exception as e:
        print(f"get_all_roles error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch roles"},
        )

# ── POST /user-management/users/{id}/restore ──────────────────────────────────
async def restore_user(request: Request):
    current_user = request.state.user
    id = request.path_params["id"]
    body = await request.json()
    admin_password = body.get("admin_password") or body.get("adminPassword")
    """RESTORE USER."""
    from fastapi import HTTPException

    if not admin_password:
        raise HTTPException(status_code=400, detail={"success": False, "message": "Administrator password is required"})

    try:
        admin_row = await db_fetchrow(
            "SELECT password FROM users WHERE user_id = $1", current_user["user_id"]
        )
        if not admin_row:
            raise HTTPException(status_code=401, detail={"success": False, "message": "Admin user not found"})
        if not bcrypt.checkpw(admin_password.encode(), admin_row["password"].encode()):
            raise HTTPException(status_code=401, detail={"success": False, "message": "Incorrect password"})

        target = await db_fetchrow("SELECT user_id, status FROM users WHERE user_id = $1", id)
        if not target:
            raise HTTPException(status_code=404, detail={"success": False, "message": "User not found"})
        if target["status"] != "deactivated":
            raise HTTPException(status_code=400, detail={"success": False, "message": "User account is not deactivated"})

        await db_execute(
            "UPDATE users SET status = 'verified', updated_at = NOW() WHERE user_id = $1", id
        )
        await log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Restored",
            description=f"Restored user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )
        return {"success": True, "message": "User account restored successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"restore_user error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": "Failed to restore user"})


# ── GET /user-management/ranks ────────────────────────────────────────────────
async def get_ranks(request: Request):
    try:
        rows = await db_fetch(
            "SELECT rank_id, rank_name, abbreviation FROM pnp_ranks ORDER BY rank_order ASC"
        )

        return {
            "success": True,
            "ranks": [dict(r) for r in rows],
        }

    except Exception as e:
        print(f"get_ranks error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch ranks"},
        )