# ================================================================================
# FILE: backend/features/auth/auth_controller.py
# ================================================================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Request
from fastapi.responses import JSONResponse

import config.database as db
from features.auth.auth_service import resend_otp, send_otp, verify_otp
from features.auth.auth_validator import (
    validate_email,
    validate_login_input,
    validate_otp_code,
    validate_password_change,
    validate_reset_password,
)
from shared.utils.audit_logger import get_client_ip, log_audit
from shared.utils.token_manager import create_token, revoke_all_user_tokens, revoke_token


# ── Login ─────────────────────────────────────────────────────────────────────
async def login(req: Request):
    try:
        body     = await req.json()
        username = body.get("username", "")
        password = body.get("password", "")
        ip       = get_client_ip(req)

        errors = validate_login_input(username, password)
        if errors:
            return JSONResponse(status_code=400, content={"success": False, "errors": errors})

        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                """SELECT
                     u.user_id, u.username, u.password, u.email,
                     u.first_name, u.last_name, u.user_type,
                     u.profile_picture, u.status, u.lockout_until,
                     u.failed_login_attempts, u.last_login,
                     r.role_name,
                     bd.barangay_code AS assigned_barangay_code
                   FROM users u
                   JOIN roles r ON u.role_id = r.role_id
                   LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                   WHERE u.username = $1""",
                username.strip(),
            )

            if not user:
                await log_audit(
                    username=username.strip(),
                    event_name="Login Failed",
                    description="Account does not exist",
                    action="LOGIN",
                    status="failed",
                    source="Web Portal",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "message": "Account does not exist"},
                )

            now = datetime.now(timezone.utc)

            # ── STATUS CHECKS ─────────────────────────────────────────────────

            if user["status"] == "deactivated":
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is deactivated",
                    action="LOGIN",
                    status="failed",
                    source="Web Portal",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "message": "Account has been deactivated"},
                )

            if user["status"] == "unverified":
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is not yet verified",
                    action="LOGIN",
                    status="failed",
                    source="Web Portal",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "message": "Account is not yet verified"},
                )

            if user["status"] == "locked" and user["lockout_until"]:
                lockout_until = user["lockout_until"]
                if lockout_until.tzinfo is None:
                    lockout_until = lockout_until.replace(tzinfo=timezone.utc)

                if now < lockout_until:
                    diff    = lockout_until - now
                    minutes = int(diff.total_seconds() // 60)
                    seconds = int(diff.total_seconds() % 60)
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Blocked",
                        description=f"Account is temporarily locked ({minutes}m {seconds}s remaining)",
                        action="LOGIN",
                        status="failed",
                        source="Web Portal",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success":           False,
                            "message":           f"Account locked. Try again in {minutes}m {seconds}s",
                            "lockout_until":     str(user["lockout_until"]),
                            "remaining_minutes": minutes,
                            "remaining_seconds": seconds,
                        },
                    )

                # Lock expired — reset
                await conn.execute(
                    "UPDATE users SET status=$1, lockout_until=NULL, failed_login_attempts=0 WHERE user_id=$2",
                    "verified", user["user_id"],
                )

            if user["status"] == "locked" and not user["lockout_until"]:
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is permanently locked",
                    action="LOGIN",
                    status="failed",
                    source="Web Portal",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "message": "Account is permanently locked. Please contact an administrator.",
                    },
                )

            # ── PASSWORD VERIFICATION ─────────────────────────────────────────

            valid = bcrypt.checkpw(
                password.encode("utf-8"),
                user["password"].encode("utf-8"),
            )

            if not valid:
                attempts    = user["failed_login_attempts"] + 1
                lock_minutes: int | None = None

                if attempts >= 8:
                    lock_minutes = None  # permanent
                elif attempts == 5:
                    lock_minutes = 15
                elif attempts == 3:
                    lock_minutes = 5

                if attempts >= 8:
                    await conn.execute(
                        "UPDATE users SET failed_login_attempts=$1, status=$2, lockout_until=NULL WHERE user_id=$3",
                        attempts, "locked", user["user_id"],
                    )
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Failed",
                        description=f"Account permanently locked after {attempts} failed attempts",
                        action="LOGIN",
                        status="failed",
                        source="Web Portal",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "message": "Account permanently locked due to too many failed attempts. Contact an administrator.",
                            "attempts": attempts,
                        },
                    )

                if lock_minutes:
                    lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
                    await conn.execute(
                        "UPDATE users SET failed_login_attempts=$1, status=$2, lockout_until=$3 WHERE user_id=$4",
                        attempts, "locked", lock_until, user["user_id"],
                    )
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Failed",
                        description=f"Account locked for {lock_minutes} minutes after {attempts} failed attempts",
                        action="LOGIN",
                        status="failed",
                        source="Web Portal",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success":       False,
                            "message":       f"Account locked for {lock_minutes} minutes",
                            "lockout_until": str(lock_until),
                            "attempts":      attempts,
                        },
                    )

                await conn.execute(
                    "UPDATE users SET failed_login_attempts=$1 WHERE user_id=$2",
                    attempts, user["user_id"],
                )
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Failed",
                    description=f"Incorrect password (attempt {attempts})",
                    action="LOGIN",
                    status="failed",
                    source="Web Portal",
                    ip_address=ip,
                )
                attempts_left = (5 - attempts) if attempts < 5 else None
                content: dict = {"success": False, "message": "Invalid credentials"}
                if attempts_left is not None:
                    content["attempts_left"] = attempts_left
                return JSONResponse(status_code=401, content=content)

            # ── SUCCESS ───────────────────────────────────────────────────────

            await conn.execute(
                """UPDATE users
                   SET failed_login_attempts=0, status='verified',
                       lockout_until=NULL, last_login=NOW()
                   WHERE user_id=$1""",
                user["user_id"],
            )

        token = await create_token({
            "user_id":   str(user["user_id"]),
            "username":  user["username"],
            "email":     user["email"],
            "role":      user["role_name"],
            "user_type": user["user_type"],
        })

        await log_audit(
            user_id=str(user["user_id"]),
            username=user["username"],
            event_name="User Login",
            description="Account successfully logged in via web portal",
            action="LOGIN",
            status="success",
            source="Web Portal",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "token":   token,
                "user": {
                    "user_id":                str(user["user_id"]),
                    "username":               user["username"],
                    "role":                   user["role_name"],
                    "user_type":              user["user_type"],
                    "first_name":             user["first_name"],
                    "last_name":              user["last_name"],
                    "profile_picture":        user["profile_picture"] or None,
                    "assigned_barangay_code": user["assigned_barangay_code"] or None,
                },
            },
        )

    except Exception as e:
        print(f"Login error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Login failed"},
        )


# ── Mobile Login ──────────────────────────────────────────────────────────────
_MOBILE_ALLOWED_ROLES  = {"Administrator", "Patrol"}
_MOBILE_TOKEN_EXPIRY   = "30d"


async def mobile_login(req: Request):
    try:
        body     = await req.json()
        username = body.get("username", "")
        password = body.get("password", "")
        ip       = get_client_ip(req)

        errors = validate_login_input(username, password)
        if errors:
            return JSONResponse(status_code=400, content={"success": False, "errors": errors})

        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                """SELECT
                     u.user_id, u.username, u.password, u.email,
                     u.first_name, u.last_name, u.user_type,
                     u.profile_picture, u.status, u.lockout_until,
                     u.failed_login_attempts, u.last_login,
                     r.role_name,
                     bd.barangay_code AS assigned_barangay_code
                   FROM users u
                   JOIN roles r ON u.role_id = r.role_id
                   LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                   WHERE u.username = $1""",
                username.strip(),
            )

            if not user:
                await log_audit(
                    username=username.strip(),
                    event_name="Login Failed",
                    description="Account does not exist",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "message": "Account does not exist"},
                )

            now = datetime.now(timezone.utc)

            # ── MOBILE ROLE GUARD ─────────────────────────────────────────────
            if user["role_name"] not in _MOBILE_ALLOWED_ROLES:
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description=f"Role '{user['role_name']}' is not permitted on the mobile app",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "message": "Access denied. This app is restricted to Admin and Patrol officers only.",
                    },
                )

            # ── STATUS CHECKS ─────────────────────────────────────────────────

            if user["status"] == "deactivated":
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is deactivated",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "message": "Account has been deactivated"},
                )

            if user["status"] == "unverified":
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is not yet verified",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "message": "Account is not yet verified"},
                )

            if user["status"] == "locked" and user["lockout_until"]:
                lockout_until = user["lockout_until"]
                if lockout_until.tzinfo is None:
                    lockout_until = lockout_until.replace(tzinfo=timezone.utc)

                if now < lockout_until:
                    diff    = lockout_until - now
                    minutes = int(diff.total_seconds() // 60)
                    seconds = int(diff.total_seconds() % 60)
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Blocked",
                        description=f"Account is temporarily locked ({minutes}m {seconds}s remaining)",
                        action="LOGIN",
                        status="failed",
                        source="Mobile App",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success":       False,
                            "message":       f"Account locked. Try again in {minutes}m {seconds}s",
                            "lockout_until": str(user["lockout_until"]),
                        },
                    )

                await conn.execute(
                    "UPDATE users SET status=$1, lockout_until=NULL, failed_login_attempts=0 WHERE user_id=$2",
                    "verified", user["user_id"],
                )

            if user["status"] == "locked" and not user["lockout_until"]:
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Blocked",
                    description="Account is permanently locked",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "message": "Account is permanently locked. Please contact an administrator.",
                    },
                )

            # ── PASSWORD VERIFICATION ─────────────────────────────────────────

            valid = bcrypt.checkpw(
                password.encode("utf-8"),
                user["password"].encode("utf-8"),
            )

            if not valid:
                attempts    = user["failed_login_attempts"] + 1
                lock_minutes: int | None = None

                if attempts >= 8:
                    lock_minutes = None
                elif attempts == 5:
                    lock_minutes = 15
                elif attempts == 3:
                    lock_minutes = 5

                if attempts >= 8:
                    await conn.execute(
                        "UPDATE users SET failed_login_attempts=$1, status=$2, lockout_until=NULL WHERE user_id=$3",
                        attempts, "locked", user["user_id"],
                    )
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Failed",
                        description=f"Account permanently locked after {attempts} failed attempts",
                        action="LOGIN",
                        status="failed",
                        source="Mobile App",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "message": "Account permanently locked due to too many failed attempts. Contact an administrator.",
                        },
                    )

                if lock_minutes:
                    lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
                    await conn.execute(
                        "UPDATE users SET failed_login_attempts=$1, status=$2, lockout_until=$3 WHERE user_id=$4",
                        attempts, "locked", lock_until, user["user_id"],
                    )
                    await log_audit(
                        user_id=str(user["user_id"]),
                        username=user["username"],
                        event_name="Login Failed",
                        description=f"Account locked for {lock_minutes} minutes after {attempts} failed attempts",
                        action="LOGIN",
                        status="failed",
                        source="Mobile App",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success":       False,
                            "message":       f"Account locked for {lock_minutes} minutes",
                            "lockout_until": str(lock_until),
                        },
                    )

                await conn.execute(
                    "UPDATE users SET failed_login_attempts=$1 WHERE user_id=$2",
                    attempts, user["user_id"],
                )
                await log_audit(
                    user_id=str(user["user_id"]),
                    username=user["username"],
                    event_name="Login Failed",
                    description=f"Incorrect password (attempt {attempts})",
                    action="LOGIN",
                    status="failed",
                    source="Mobile App",
                    ip_address=ip,
                )
                attempts_left = (5 - attempts) if attempts < 5 else None
                content: dict = {"success": False, "message": "Invalid credentials"}
                if attempts_left is not None:
                    content["attempts_left"] = attempts_left
                return JSONResponse(status_code=401, content=content)

            # ── SUCCESS ───────────────────────────────────────────────────────

            await conn.execute(
                """UPDATE users
                   SET failed_login_attempts=0, status='verified',
                       lockout_until=NULL, last_login=NOW()
                   WHERE user_id=$1""",
                user["user_id"],
            )

        token = await create_token(
            {
                "user_id":   str(user["user_id"]),
                "username":  user["username"],
                "email":     user["email"],
                "role":      user["role_name"],
                "user_type": user["user_type"],
            },
            expires_in=_MOBILE_TOKEN_EXPIRY,
        )

        await log_audit(
            user_id=str(user["user_id"]),
            username=user["username"],
            event_name="User Login",
            description="Account successfully logged in via Mobile App",
            action="LOGIN",
            status="success",
            source="Mobile App",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "token":   token,
                "user": {
                    "user_id":                str(user["user_id"]),
                    "username":               user["username"],
                    "role":                   user["role_name"],
                    "user_type":              user["user_type"],
                    "first_name":             user["first_name"],
                    "last_name":              user["last_name"],
                    "profile_picture":        user["profile_picture"] or None,
                    "assigned_barangay_code": user["assigned_barangay_code"] or None,
                },
            },
        )

    except Exception as e:
        print(f"Mobile login error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Login failed"},
        )


# ── Validate Token ────────────────────────────────────────────────────────────
async def validate_token(req: Request):
    """Used by mobile splash screen — middleware already verified the token."""
    return JSONResponse(
        status_code=200,
        content={"success": True, "user": req.state.user},
    )


# ── Logout ────────────────────────────────────────────────────────────────────
async def logout(req: Request):
    try:
        token = req.headers.get("authorization", "").split(" ")[-1]
        ip    = get_client_ip(req)

        if not token:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "No token provided"},
            )

        await revoke_token(token)

        await log_audit(
            user_id=str(req.state.user["user_id"]),
            username=req.state.user["username"],
            event_name="User Logout",
            description="User logged out",
            action="LOGOUT",
            status="success",
            source="Web Portal",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Logged out successfully"},
        )
    except Exception as e:
        print(f"Logout error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Logout failed"},
        )


# ── Logout All Devices ────────────────────────────────────────────────────────
async def logout_all(req: Request):
    try:
        ip = get_client_ip(req)
        await revoke_all_user_tokens(req.state.user["user_id"])

        await log_audit(
            user_id=str(req.state.user["user_id"]),
            username=req.state.user["username"],
            event_name="Logout All Devices",
            description="User revoked all active sessions",
            action="LOGOUT",
            status="success",
            source="Web Portal",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Logged out from all devices"},
        )
    except Exception as e:
        print(f"Logout all error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Logout all failed"},
        )


# ── Send OTP ──────────────────────────────────────────────────────────────────
async def send_otp_handler(req: Request):
    try:
        body  = await req.json()
        email = body.get("email", "")

        errors = validate_email(email)
        if errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": errors},
            )

        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT user_id, email, status FROM users WHERE LOWER(email) = LOWER($1)",
                email,
            )

        if not user:
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Email not found"},
            )

        if user["status"] == "deactivated":
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Account is deactivated"},
            )

        if user["status"] == "unverified":
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Account is not yet verified"},
            )

        result = await send_otp(email)

        return JSONResponse(
            status_code=200 if result["success"] else 429,
            content=result,
        )

    except Exception as e:
        print(f"Send OTP error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to send OTP"},
        )


# ── Verify OTP ────────────────────────────────────────────────────────────────
async def verify_otp_handler(req: Request):
    try:
        body  = await req.json()
        email = body.get("email", "")
        code  = body.get("code", "")

        errors = validate_email(email) + validate_otp_code(code)
        if errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": errors},
            )

        result = await verify_otp(email, code)

        return JSONResponse(
            status_code=200 if result["success"] else 400,
            content=result,
        )

    except Exception as e:
        print(f"Verify OTP error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "OTP verification failed"},
        )


# ── Resend OTP ────────────────────────────────────────────────────────────────
async def resend_otp_handler(req: Request):
    try:
        body  = await req.json()
        email = body.get("email", "")

        errors = validate_email(email)
        if errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": errors},
            )

        result = await resend_otp(email)

        return JSONResponse(
            status_code=200 if result["success"] else 429,
            content=result,
        )

    except Exception as e:
        print(f"Resend OTP error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to resend OTP"},
        )

# ── Reset Password ────────────────────────────────────────────────────────────
async def reset_password(req: Request):
    try:
        body         = await req.json()
        email        = body.get("email", "")
        new_password = (body.get("newPassword") or "").strip()
        ip           = get_client_ip(req)

        errors = validate_reset_password(email, new_password)
        if errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": errors},
            )

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow(
                    "SELECT user_id, username, password, status FROM users WHERE LOWER(email) = LOWER($1)",
                    email,
                )
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={"success": False, "message": "User not found"},
                    )
                if user["status"] == "deactivated":
                    return JSONResponse(
                        status_code=403,
                        content={"success": False, "message": "Account is deactivated"},
                    )
                if bcrypt.checkpw(
                    new_password.encode("utf-8"),
                    user["password"].encode("utf-8"),
                ):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "message": "New password cannot be the same as the old password",
                        },
                    )

                hashed = bcrypt.hashpw(
                    new_password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")

                await conn.execute(
                    """UPDATE users
                       SET password=$1,
                           failed_login_attempts=0,
                           status=CASE WHEN status='locked' THEN 'verified' ELSE status END,
                           lockout_until=NULL,
                           updated_at=NOW()
                       WHERE user_id=$2""",
                    hashed, user["user_id"],
                )
                await conn.execute(
                    "DELETE FROM otp_requests WHERE LOWER(email) = LOWER($1)", email
                )

        await log_audit(
            user_id=str(user["user_id"]),
            username=user["username"],
            event_name="Password Reset",
            description=f"Password reset via OTP for {email}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Password reset successfully"},
        )
    except Exception as e:
        print(f"Reset password error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Password reset failed"},
        )


# ── Change Password ───────────────────────────────────────────────────────────
async def change_password(req: Request):
    try:
        body             = await req.json()
        current_password = (body.get("currentPassword") or "").strip()
        new_password     = (body.get("newPassword") or "").strip()
        ip               = get_client_ip(req)

        errors = validate_password_change(current_password, new_password)
        if errors:
            return JSONResponse(
                status_code=400,
                content={"success": False, "errors": errors},
            )

        async with db.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT password FROM users WHERE user_id=$1",
                    req.state.user["user_id"],
                )
                if not row:
                    return JSONResponse(
                        status_code=404,
                        content={"success": False, "message": "User not found"},
                    )
                if not bcrypt.checkpw(
                    current_password.encode("utf-8"),
                    row["password"].encode("utf-8"),
                ):
                    await log_audit(
                        user_id=str(req.state.user["user_id"]),
                        username=req.state.user["username"],
                        event_name="Password Change Failed",
                        description="Incorrect current password",
                        action="UPDATE",
                        status="failed",
                        source="Web Portal",
                        ip_address=ip,
                    )
                    return JSONResponse(
                        status_code=401,
                        content={"success": False, "message": "Current password is incorrect"},
                    )
                if bcrypt.checkpw(
                    new_password.encode("utf-8"),
                    row["password"].encode("utf-8"),
                ):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "message": "New password cannot be the same as the current password",
                        },
                    )

                hashed = bcrypt.hashpw(
                    new_password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")
                await conn.execute(
                    "UPDATE users SET password=$1, updated_at=NOW() WHERE user_id=$2",
                    hashed, req.state.user["user_id"],
                )

        await revoke_all_user_tokens(req.state.user["user_id"])

        await log_audit(
            user_id=str(req.state.user["user_id"]),
            username=req.state.user["username"],
            event_name="Password Changed",
            description="All account sessions revoked",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=ip,
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Password changed successfully. Please log in again.",
            },
        )
    except Exception as e:
        print(f"Change password error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Password change failed"},
        )