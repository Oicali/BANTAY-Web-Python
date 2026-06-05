# ================================================================================
# FILE: backend/features/user/user_controller.py
# ================================================================================

import hashlib
import json
import math
import os
import secrets
import uuid
from typing import Optional
from datetime import date

from flask import g, jsonify, redirect, request

import config.database as db
from config.database import get_db
from shared.utils.audit_logger import log_audit, get_client_ip
from features.user.user_validator import UserValidator
from features.user.email_service import (
    send_verification_email,
    send_welcome_email,
)


# ---------------------------------------------------------------------------
# DB helpers (synchronous, mysql-connector-python style)
# ---------------------------------------------------------------------------

def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


def db_fetch(sql: str, params: tuple = ()):
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return [dict(r) for r in rows]


def db_fetchrow(sql: str, params: tuple = ()):
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    return dict(row) if row else None


def db_execute(sql: str, params: tuple = ()):
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    return affected


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------

def generate_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%?"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def slug_part(value: str) -> str:
    import re
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value or "user"


def generate_username(first: str, middle: str, last: str, prefix: str) -> str:
    base     = f"{prefix}{slug_part(first)}{slug_part(last)}"
    username = base
    counter  = 1
    while True:
        existing = db_fetchrow(
            "SELECT user_id FROM users WHERE username = %s", (username,)
        )
        if not existing:
            return username
        counter  += 1
        username  = f"{base}{counter}"


def notify_all_by_role(roles: list, payload: dict, exclude_id=None) -> None:
    return None


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def error_response(status: int, message: str, **extra):
    body = {"success": False, "message": message, **extra}
    return jsonify(body), status


def ok(body: dict):
    return jsonify(body), 200


def _get_client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


# =============================================================================
# ENDPOINTS
# =============================================================================

# ── GET /user-management/users ───────────────────────────────────────────────
def get_all_users():
    try:
        user_type     = request.args.get("userType") or request.args.get("user_type") or "police"
        status        = request.args.get("status")
        search        = request.args.get("search")
        role          = request.args.get("role")
        barangay_code = request.args.get("barangayCode") or request.args.get("barangay_code")

        page   = max(1, int(request.args.get("page", 1)))
        limit  = max(1, int(request.args.get("limit", 20)))
        offset = (page - 1) * limit

        conditions = ["u.user_type = %s"]
        params     = [user_type]

        if status and status != "all":
            if status == "active":
                status = "verified"
            conditions.append("u.status = %s")
            params.append(status)
        elif not status:
            conditions.append("u.status != 'deactivated'")

        if search:
            conditions.append(
                "(u.username LIKE %s OR u.email LIKE %s OR "
                "u.first_name LIKE %s OR u.last_name LIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])

        if role and role != "all":
            conditions.append("r.role_name = %s")
            params.append(role)

        if barangay_code and barangay_code != "all":
            conditions.append("bd.barangay_code = %s")
            params.append(barangay_code)

        where = f"WHERE {' AND '.join(conditions)}"

        count_row = db_fetchrow(
            f"""SELECT COUNT(*) AS total
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                {where}""",
            tuple(params),
        )
        total = int(count_row["total"]) if count_row else 0

        rows = db_fetch(
            f"""SELECT
                  u.user_id, u.username, u.email,
                  u.first_name, u.last_name, u.middle_name, u.suffix,
                  u.phone, u.alternate_phone, u.gender,
                  DATE_FORMAT(u.date_of_birth, '%%Y-%%m-%%d') AS date_of_birth,
                  u.profile_picture,
                  u.status, u.last_login, u.created_at,
                  u.user_type, u.rank_id,
                  pr.rank_name AS `rank`,
                  pr.abbreviation AS rank_abbreviation,
                  r.role_id,
                  r.role_name AS `role`,
                  ua.region_code, ua.province_code, ua.municipality_code,
                  ua.barangay_code AS address_barangay_code, ua.address_line,
                  bd.barangay_code AS assigned_barangay_code
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.role_id
                LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
                LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                {where}
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s""",
            tuple(params) + (limit, offset),
        )

        return ok({
            "success": True,
            "users":   rows,
            "pagination": {
                "total":      total,
                "page":       page,
                "limit":      limit,
                "totalPages": math.ceil(total / limit) if limit else 0,
            },
        })

    except Exception as e:
        print(f"get_all_users error: {e}")
        return error_response(500, "Failed to fetch users")


# ── GET /user-management/filter-options ──────────────────────────────────────
def get_filter_options():
    try:
        police_roles   = db_fetch(
            "SELECT DISTINCT r.role_name FROM roles r WHERE r.user_type = 'police' ORDER BY r.role_name",
        )
        barangay_roles = db_fetch(
            "SELECT DISTINCT r.role_name FROM roles r WHERE r.user_type = 'barangay' ORDER BY r.role_name",
        )
        return ok({
            "success":       True,
            "roles":         [r["role_name"] for r in police_roles],
            "barangayRoles": [r["role_name"] for r in barangay_roles],
        })
    except Exception as e:
        print(f"get_filter_options error: {e}")
        return error_response(500, "Failed to fetch filter options")


# ── GET /user-management/users/<id> ──────────────────────────────────────────
def get_user_by_id(id):
    try:
        row = db_fetchrow(
            """SELECT
                 u.user_id, u.username, u.email,
                 u.first_name, u.last_name, u.middle_name, u.suffix,
                 u.phone, u.alternate_phone, u.gender,
                 DATE_FORMAT(u.date_of_birth, '%%Y-%%m-%%d') AS date_of_birth,
                 u.profile_picture,
                 u.status, u.last_login, u.created_at,
                 u.user_type, u.rank_id,
                 pr.rank_name AS `rank`, pr.abbreviation AS rank_abbreviation,
                 r.role_id, r.role_name AS `role`,
                 ua.region_code, ua.province_code, ua.municipality_code,
                 ua.barangay_code AS address_barangay_code, ua.address_line,
                 bd.barangay_code AS assigned_barangay_code
               FROM users u
               LEFT JOIN roles r ON u.role_id = r.role_id
               LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
               LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
               LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
               WHERE u.user_id = %s""",
            (id,),
        )
        if not row:
            return error_response(404, "User not found")
        return ok({"success": True, "user": row})
    except Exception as e:
        print(f"get_user_by_id error: {e}")
        return error_response(500, "Failed to fetch user")


# ── POST /user-management/register ───────────────────────────────────────────
def register_user():
    current_user = g.user

    def f(key):
        return (request.form.get(key) or "").strip()

    def cap(s: str) -> str:
        return s[0].upper() + s[1:].lower() if s else ""

    user_type         = f("userType")
    email             = f("email").lower()
    first_name        = f("firstName")
    last_name         = f("lastName")
    middle_name       = f("middleName")
    suffix            = f("suffix")
    phone             = f("phone")
    alternate_phone   = f("alternatePhone")
    gender            = f("gender")
    _dob_str          = f("dateOfBirth")
    date_of_birth     = date.fromisoformat(_dob_str) if _dob_str else None
    region_code       = f("regionCode") or None
    province_code     = f("provinceCode") or None
    municipality_code = f("municipalityCode") or None
    barangay_code     = f("barangay") or f("barangayCode") or None
    address_line      = f("addressLine") or None
    role              = f("role")
    rank_id           = f("rankId") or None

    trimmed_first        = cap(first_name)
    trimmed_last         = cap(last_name)
    trimmed_middle       = cap(middle_name)
    trimmed_email        = email
    trimmed_phone        = phone
    trimmed_alt_phone    = alternate_phone or None
    trimmed_suffix       = suffix
    trimmed_region       = region_code
    trimmed_province     = province_code
    trimmed_municipality = municipality_code
    trimmed_barangay     = barangay_code
    trimmed_address_line = address_line

    body = {
        "userType":          user_type,
        "email":             trimmed_email,
        "firstName":         trimmed_first,
        "lastName":          trimmed_last,
        "middleName":        trimmed_middle or None,
        "suffix":            trimmed_suffix or None,
        "phone":             trimmed_phone,
        "alternatePhone":    trimmed_alt_phone,
        "gender":            gender,
        "dateOfBirth":       date_of_birth,
        "regionCode":        trimmed_region,
        "provinceCode":      trimmed_province,
        "municipalityCode":  trimmed_municipality,
        "barangay":          trimmed_barangay,
        "barangayCode":      trimmed_barangay,
        "addressLine":       trimmed_address_line,
        "role":              role,
        "rankId":            rank_id,
        "user_type":         user_type,
        "first_name":        trimmed_first,
        "last_name":         trimmed_last,
        "middle_name":       trimmed_middle or None,
        "alternate_phone":   trimmed_alt_phone,
        "region_code":       trimmed_region,
        "province_code":     trimmed_province,
        "municipality_code": trimmed_municipality,
        "barangay_code":     trimmed_barangay,
        "address_line":      trimmed_address_line,
        "date_of_birth":     date_of_birth,
        "rank_id":           rank_id,
    }

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        validation = UserValidator.validate_registration(body, cursor)
        print(f"DEBUG validation body: {body}")
        print(f"DEBUG validation result: {validation}")
        if not validation.get("is_valid", validation.get("isValid", False)):
            return error_response(400, "Validation failed", errors=validation.get("errors", {}))

        cursor.execute(
            "SELECT role_id FROM roles WHERE role_name = %s AND user_type = %s",
            (role, user_type),
        )
        role_row = cursor.fetchone()
        if not role_row:
            return error_response(
                400,
                f"Invalid role '{role}' for {user_type} user",
                errors={"role": f"Invalid role for {user_type} user"},
            )
        role_id = role_row["role_id"]

        username       = generate_username(
            trimmed_first, trimmed_middle or "", trimmed_last,
            "pnp" if user_type == "police" else "brgy",
        )
        plain_password = generate_password()

        # ── Generate UUID in Python so all subsequent inserts use the same value ──
        user_id = str(uuid.uuid4())

        cursor.execute(
            """INSERT INTO users (
                 user_id,
                 username, email, password,
                 first_name, last_name, middle_name, suffix,
                 phone, alternate_phone,
                 gender, date_of_birth,
                 user_type, role_id, rank_id,
                 status, created_at
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'unverified',NOW())""",
            (
                user_id,
                username, trimmed_email, plain_password,
                trimmed_first, trimmed_last, trimmed_middle or None, trimmed_suffix or None,
                trimmed_phone, trimmed_alt_phone or None,
                gender, date_of_birth,
                user_type, role_id,
                int(rank_id) if rank_id else None,
            ),
        )

        cursor.execute(
            """INSERT INTO user_addresses
                 (user_id, region_code, province_code, municipality_code, barangay_code, address_line)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (user_id, trimmed_region, trimmed_province,
             trimmed_municipality, trimmed_barangay, trimmed_address_line),
        )

        if user_type == "barangay":
            cursor.execute(
                "INSERT INTO barangay_details (user_id, barangay_code) VALUES (%s,%s)",
                (user_id, trimmed_barangay),
            )

        raw_token  = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        from datetime import datetime, timezone, timedelta
        token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

        cursor.execute(
            "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
            (user_id, token_hash, token_expiry),
        )

        credentials_json = json.dumps({
            "username": username,
            "password": plain_password,
            "userType": user_type,
            "role":     role,
        })
        cursor.execute(
            """INSERT INTO pending_credentials (user_id, credentials, expires_at)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 credentials = VALUES(credentials),
                 expires_at  = VALUES(expires_at)""",
            (user_id, credentials_json, token_expiry),
        )

        conn.commit()

        backend_url      = os.getenv("BACKEND_URL", f"http://localhost:{os.getenv('PORT', 5000)}")
        verification_url = f"{backend_url}/user-management/verify-account?token={raw_token}"
        email_result     = send_verification_email(trimmed_email, trimmed_first, trimmed_last, verification_url)

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Registered",
            description=f"Registered new {user_type} user \"{username}\" with role {role}",
            action="CREATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )

        notify_all_by_role(
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

        return ok({
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
        })

    except Exception as e:
        conn.rollback()
        print(f"register_user error: {e}")
        return error_response(500, "Registration failed")
    finally:
        cursor.close()


# ── GET /user-management/verify-account ──────────────────────────────────────
def verify_account():
    from datetime import datetime, timezone

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    token        = request.args.get("token")

    if not token:
        return redirect(f"{frontend_url}/verification-success?status=invalid")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn       = get_db()
    cursor     = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """SELECT
                 t.token_id, t.user_id, t.expires_at, t.is_revoked,
                 u.status, u.email, u.first_name, u.last_name,
                 u.username, u.user_type,
                 r.role_name AS role
               FROM tokens t
               JOIN users u ON t.user_id = u.user_id
               LEFT JOIN roles r ON u.role_id = r.role_id
               WHERE t.token_hash = %s""",
            (token_hash,),
        )
        token_row = cursor.fetchone()

        if not token_row:
            return redirect(f"{frontend_url}/verification-success?status=invalid")
        if token_row["is_revoked"]:
            return redirect(f"{frontend_url}/verification-success?status=used")
        expires_at = token_row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return redirect(f"{frontend_url}/verification-success?status=expired")
        if token_row["status"] == "verified":
            return redirect(f"{frontend_url}/verification-success?status=already_verified")

        user_id = token_row["user_id"]

        cursor.execute(
            "UPDATE users SET status = 'verified', updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )
        cursor.execute(
            "UPDATE tokens SET is_revoked = TRUE, revoked_at = NOW() WHERE token_hash = %s",
            (token_hash,),
        )

        cursor.execute(
            "SELECT credentials FROM pending_credentials WHERE user_id = %s", (user_id,)
        )
        cred_row       = cursor.fetchone()
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
            cursor.execute(
                "DELETE FROM pending_credentials WHERE user_id = %s", (user_id,)
            )

        conn.commit()

        if plain_password:
            email_result = send_welcome_email(
                token_row["email"], token_row["first_name"], token_row["last_name"],
                username, plain_password, user_type, role,
            )
            if not email_result.get("success"):
                print(f"Failed to send welcome email: {email_result.get('message')}")

        print(f"Account verified and activated: {username}")
        return redirect(f"{frontend_url}/verification-success?status=success")

    except Exception as e:
        conn.rollback()
        print(f"verify_account error: {e}")
        return redirect(f"{frontend_url}/verification-success?status=error")
    finally:
        cursor.close()


# ── POST /user-management/users/<id>/resend-verification ─────────────────────
def resend_verification_email(id):
    current_user = g.user
    from datetime import datetime, timezone, timedelta

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """SELECT u.user_id, u.email, u.first_name, u.last_name, u.username,
                      u.status, u.user_type, r.role_name AS role
               FROM users u
               LEFT JOIN roles r ON u.role_id = r.role_id
               WHERE u.user_id = %s""",
            (id,),
        )
        user_row = cursor.fetchone()

        if not user_row:
            return error_response(404, "User not found")
        if user_row["status"] != "unverified":
            return error_response(
                400,
                f"Account is already {user_row['status']}. Verification email is only for unverified accounts.",
            )

        cursor.execute(
            "UPDATE tokens SET is_revoked = TRUE, revoked_at = NOW() WHERE user_id = %s AND is_revoked = FALSE",
            (user_row["user_id"],),
        )

        cursor.execute(
            "SELECT credentials FROM pending_credentials WHERE user_id = %s", (user_row["user_id"],)
        )
        cred_row       = cursor.fetchone()
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
            cursor.execute(
                "UPDATE users SET password = %s, updated_at = NOW() WHERE user_id = %s",
                (plain_password, user_row["user_id"]),
            )

        raw_token    = secrets.token_hex(32)
        token_hash   = hashlib.sha256(raw_token.encode()).hexdigest()
        token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

        cursor.execute(
            "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
            (user_row["user_id"], token_hash, token_expiry),
        )

        credentials_json = json.dumps({
            "username": username,
            "password": plain_password,
            "userType": user_type,
            "role":     role,
        })
        cursor.execute(
            """INSERT INTO pending_credentials (user_id, credentials, expires_at)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 credentials = VALUES(credentials),
                 expires_at  = VALUES(expires_at)""",
            (user_row["user_id"], credentials_json, token_expiry),
        )

        conn.commit()

        backend_url      = os.getenv("BACKEND_URL", f"http://localhost:{os.getenv('PORT', 5000)}")
        verification_url = f"{backend_url}/user-management/verify-account?token={raw_token}"
        email_result     = send_verification_email(
            user_row["email"], user_row["first_name"], user_row["last_name"], verification_url
        )

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Verification Email Resent",
            description=f"Resent verification email to user \"{username}\" ({user_row['email']})",
            action="CREATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )

        return ok({
            "success":   True,
            "message":   f"Verification email resent to {user_row['email']}",
            "emailSent": email_result.get("success", False),
        })

    except Exception as e:
        conn.rollback()
        print(f"resend_verification_email error: {e}")
        return error_response(500, "Failed to resend verification email")
    finally:
        cursor.close()


# ── PUT /user-management/users/<id> ──────────────────────────────────────────
def update_user(id):
    current_user = g.user

    # ── FIX: Read from form data (multipart) sent by the frontend.
    #         request.get_json() returns {} for multipart requests,
    #         which caused the silent no-op update.
    def _form(key, *aliases):
        """Return the first non-empty value from request.form, or None."""
        for k in (key, *aliases):
            v = request.form.get(k)
            if v is not None:
                return v.strip() or None
        return None

    body = {
        "email":                _form("email"),
        "firstName":            _form("firstName", "first_name"),
        "lastName":             _form("lastName", "last_name"),
        "middleName":           _form("middleName", "middle_name"),
        "suffix":               _form("suffix"),
        "gender":               _form("gender"),
        "phone":                _form("phone"),
        "alternatePhone":       _form("alternatePhone", "alternate_phone"),
        "dateOfBirth":          _form("dateOfBirth", "date_of_birth"),
        "role":                 _form("role"),
        "rankId":               _form("rankId", "rank_id"),
        "regionCode":           _form("regionCode", "region_code"),
        "provinceCode":         _form("provinceCode", "province_code"),
        "municipalityCode":     _form("municipalityCode", "municipality_code"),
        "barangayCode":         _form("barangayCode", "barangay_code"),
        "addressLine":          _form("addressLine", "address_line"),
        "assignedBarangayCode": _form("assignedBarangayCode", "assigned_barangay_code"),
        "newPassword":          _form("newPassword", "new_password"),
    }

    print(f"DEBUG update_user body: {body}")

    if current_user.get("role") != "Technical Administrator":
        return error_response(403, "Only technical administrators can update user information")

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT user_id, user_type, email, phone, alternate_phone FROM users WHERE user_id = %s", (id,)
        )
        existing = cursor.fetchone()
        if not existing:
            return error_response(404, "User not found")

        validation = UserValidator.validate_update(body, existing, cursor)
        print(f"DEBUG validation body: {body}")
        print(f"DEBUG validation result: {validation}")
        if not validation.get("is_valid", validation.get("isValid", False)):
            return error_response(400, "Validation failed", errors=validation.get("errors", {}))

        role_id = None
        if body.get("role"):
            cursor.execute(
                "SELECT role_id FROM roles WHERE role_name = %s AND user_type = %s",
                (body.get("role"), existing["user_type"]),
            )
            role_row = cursor.fetchone()
            if not role_row:
                return error_response(
                    400,
                    f"Invalid role '{body.get('role')}' for {existing['user_type']} user",
                )
            role_id = role_row["role_id"]

        def cap(s):
            return s[0].upper() + s[1:].lower() if s else None

        trimmed_email     = (body.get("email") or "").lower().strip() or None
        trimmed_first     = cap((body.get("firstName") or "").strip())
        trimmed_last      = cap((body.get("lastName") or "").strip())
        trimmed_middle    = cap((body.get("middleName") or "").strip())
        trimmed_suffix    = (body.get("suffix") or "").strip() or None
        trimmed_phone     = (body.get("phone") or "").strip() or None
        trimmed_alt_phone = (body.get("alternatePhone") or "").strip() or None

        date_of_birth = body.get("dateOfBirth")
        if date_of_birth:
            try:
                date_of_birth = date.fromisoformat(date_of_birth)
            except (ValueError, TypeError):
                date_of_birth = None

        gender        = body.get("gender")
        rank_id       = body.get("rankId")
        new_password  = body.get("newPassword")
        region        = body.get("regionCode")
        province      = body.get("provinceCode")
        municipality  = body.get("municipalityCode")
        barangay      = body.get("barangayCode")
        addr_line     = body.get("addressLine")
        assigned_brgy = body.get("assignedBarangayCode")

        set_clauses = []
        values      = []

        if trimmed_email:
            set_clauses.append("email = %s");         values.append(trimmed_email)
        if trimmed_first:
            set_clauses.append("first_name = %s");    values.append(trimmed_first)
        if trimmed_last:
            set_clauses.append("last_name = %s");     values.append(trimmed_last)

        set_clauses.append("middle_name = %s");       values.append(trimmed_middle)
        set_clauses.append("suffix = %s");            values.append(trimmed_suffix)

        if date_of_birth:
            set_clauses.append("date_of_birth = %s"); values.append(date_of_birth)
        if gender:
            set_clauses.append("gender = %s");        values.append(gender)
        if trimmed_phone:
            set_clauses.append("phone = %s");         values.append(trimmed_phone)

        set_clauses.append("alternate_phone = %s");   values.append(trimmed_alt_phone)

        if role_id:
            set_clauses.append("role_id = %s");       values.append(role_id)
        if rank_id is not None:
            set_clauses.append("rank_id = %s");       values.append(int(rank_id) if rank_id else None)
        if new_password:
            set_clauses.append("password = %s");      values.append(new_password)

        set_clauses.append("updated_at = NOW()")

        if len(set_clauses) == 1:
            return error_response(400, "No fields provided to update")

        values.append(id)
        cursor.execute(
            f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = %s",
            tuple(values),
        )

        addr_clauses = []
        addr_values  = []

        if region:
            addr_clauses.append("region_code = %s");       addr_values.append(region)
        if province:
            addr_clauses.append("province_code = %s");     addr_values.append(province)
        if municipality:
            addr_clauses.append("municipality_code = %s"); addr_values.append(municipality)

        effective_brgy = (
            assigned_brgy or barangay or None
            if existing["user_type"] == "barangay"
            else barangay or None
        )
        if effective_brgy:
            addr_clauses.append("barangay_code = %s");     addr_values.append(effective_brgy)
        if addr_line is not None:
            addr_clauses.append("address_line = %s");      addr_values.append(addr_line.strip() if addr_line else None)

        if addr_clauses:
            addr_values.append(id)
            cursor.execute(
                f"UPDATE user_addresses SET {', '.join(addr_clauses)} WHERE user_id = %s",
                tuple(addr_values),
            )

        if existing["user_type"] == "barangay":
            brgy = assigned_brgy or barangay
            if brgy:
                cursor.execute(
                    "UPDATE barangay_details SET barangay_code = %s WHERE user_id = %s",
                    (brgy, id),
                )

        conn.commit()

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Updated",
            description=f"Updated user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )
        return ok({"success": True, "message": "User updated successfully"})

    except Exception as e:
        conn.rollback()
        print(f"update_user error: {e}")
        return error_response(500, "Failed to update user")
    finally:
        cursor.close()


# ── DELETE /user-management/users/<id> (deactivate) ──────────────────────────
def deactivate_user(id):
    current_user   = g.user
    body           = request.get_json(silent=True) or {}
    admin_password = body.get("admin_password") or body.get("adminPassword")

    if not admin_password:
        return error_response(400, "Administrator password is required")

    try:
        admin_row = db_fetchrow(
            "SELECT password FROM users WHERE user_id = %s", (current_user["user_id"],)
        )
        if not admin_row:
            return error_response(401, "Admin user not found")
        if admin_password != admin_row["password"]:
            return error_response(401, "Incorrect password")

        affected = db_execute(
            "UPDATE users SET status = 'deactivated', updated_at = NOW() WHERE user_id = %s", (id,)
        )
        if affected == 0:
            return error_response(404, "User not found")

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Deactivated",
            description=f"Deactivated user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )
        return ok({"success": True, "message": "User deactivated successfully"})

    except Exception as e:
        print(f"deactivate_user error: {e}")
        return error_response(500, "Failed to deactivate user")


# ── PUT /user-management/users/<id>/lock ─────────────────────────────────────
def lock_user(id):
    current_user = g.user

    if current_user.get("role") != "Technical Administrator":
        return error_response(403, "Only technical administrators can lock user accounts")

    if str(current_user["user_id"]) == str(id):
        return error_response(400, "You cannot lock your own account")

    try:
        row = db_fetchrow("SELECT user_id, status FROM users WHERE user_id = %s", (id,))

        if not row:
            return error_response(404, "User not found")
        if row["status"] == "locked":
            return error_response(400, "Account is already locked")

        db_execute(
            "UPDATE users SET status = 'locked', updated_at = NOW() WHERE user_id = %s", (id,)
        )

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Locked",
            description=f"Locked account for user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )

        notify_all_by_role(
            ["Administrator", "Technical Administrator"],
            {
                "sender_id":   current_user["user_id"],
                "sender_name": current_user["username"],
                "type":        "ACCOUNT_LOCKED",
                "title":       "Account Locked",
                "message":     f"{current_user['username']} locked account ID {id}",
                "link_to":     "/user-management",
            },
            current_user["user_id"],
        )
        return ok({"success": True, "message": "Account locked successfully"})

    except Exception as e:
        print(f"lock_user error: {e}")
        return error_response(500, "Failed to lock account")


# ── PUT /user-management/users/<id>/unlock ───────────────────────────────────
def unlock_user(id):
    current_user = g.user

    if current_user.get("role") != "Technical Administrator":
        return error_response(403, "Only technical administrators can unlock user accounts")

    try:
        row = db_fetchrow("SELECT user_id, status FROM users WHERE user_id = %s", (id,))

        if not row:
            return error_response(404, "User not found")
        if row["status"] != "locked":
            return error_response(400, "Account is not locked")

        db_execute(
            """UPDATE users
               SET status = 'verified',
                   failed_login_attempts = 0,
                   lockout_until = NULL,
                   updated_at = NOW()
               WHERE user_id = %s""",
            (id,),
        )

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Unlocked",
            description=f"Unlocked account for user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )

        notify_all_by_role(
            ["Administrator", "Technical Administrator"],
            {
                "sender_id":   current_user["user_id"],
                "sender_name": current_user["username"],
                "type":        "ACCOUNT_UNLOCKED",
                "title":       "Account Unlocked",
                "message":     f"{current_user['username']} unlocked account ID {id}",
                "link_to":     "/user-management",
            },
            current_user["user_id"],
        )
        return ok({"success": True, "message": "Account unlocked successfully"})

    except Exception as e:
        print(f"unlock_user error: {e}")
        return error_response(500, "Failed to unlock account")


# ── GET /user-management/roles ────────────────────────────────────────────────
def get_all_roles():
    try:
        rows = db_fetch(
            "SELECT role_id, role_name, user_type FROM roles ORDER BY user_type, role_name",
        )
        return ok({"success": True, "roles": rows})
    except Exception as e:
        print(f"get_all_roles error: {e}")
        return error_response(500, "Failed to fetch roles")


# ── PUT /user-management/users/<id>/restore ──────────────────────────────────
def restore_user(id):
    current_user   = g.user
    body           = request.get_json(silent=True) or {}
    admin_password = body.get("admin_password") or body.get("adminPassword")

    if not admin_password:
        return error_response(400, "Administrator password is required")

    try:
        admin_row = db_fetchrow(
            "SELECT password FROM users WHERE user_id = %s", (current_user["user_id"],)
        )
        if not admin_row:
            return error_response(401, "Admin user not found")
        if admin_password != admin_row["password"]:
            return error_response(401, "Incorrect password")

        target = db_fetchrow("SELECT user_id, status FROM users WHERE user_id = %s", (id,))
        if not target:
            return error_response(404, "User not found")
        if target["status"] != "deactivated":
            return error_response(400, "User account is not deactivated")

        db_execute(
            "UPDATE users SET status = 'verified', updated_at = NOW() WHERE user_id = %s", (id,)
        )
        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="User Restored",
            description=f"Restored user ID {id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=_get_client_ip(),
        )
        return ok({"success": True, "message": "User account restored successfully"})

    except Exception as e:
        print(f"restore_user error: {e}")
        return error_response(500, "Failed to restore user")


# ── GET /user-management/ranks ────────────────────────────────────────────────
def get_ranks():
    try:
        rows = db_fetch(
            "SELECT rank_id, rank_name, abbreviation FROM pnp_ranks ORDER BY rank_order ASC",
        )
        return ok({"success": True, "ranks": rows})
    except Exception as e:
        print(f"get_ranks error: {e}")
        return error_response(500, "Failed to fetch ranks")