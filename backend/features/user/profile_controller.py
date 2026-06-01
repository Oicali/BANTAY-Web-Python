# ================================================================================
# FILE: backend/features/user/profile_controller.py
# ================================================================================

import math
import secrets
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request, UploadFile

import asyncio
import config.cloudinary  # noqa: F401 — registers cloudinary config on import
import cloudinary.uploader
import config.database as db
from features.user.user import User as UserModel
from features.user.profile_validator import ProfileValidator
from shared.utils.token_manager import revoke_all_user_tokens
from features.user.email_verification_controller import (
    get_verified_email,
    set_old_email_for_notification,
    consume_session,
)
from features.user.email_service import (
    send_password_otp_email,
    send_password_changed_notification,
)
from shared.utils.audit_logger import log_audit


# ── Password-change OTP constants ─────────────────────────────────────────────
PW_OTP_EXPIRY           = 2  * 60 * 1000
PW_MAX_OTP_ATTEMPTS     = 3
PW_MAX_RESENDS          = 3
PW_OTP_LOCKOUT_MS       = 15 * 60 * 1000
PW_MAX_CHANGES          = 2
PW_WINDOW_MS            = 24 * 60 * 60 * 1000
PW_RESEND_WINDOW_MS     = 15 * 60 * 1000
PW_MAX_CURRENT_ATTEMPTS = 5
PW_CURRENT_LOCKOUT_MS   = 15 * 60 * 1000


# ── In-memory stores ──────────────────────────────────────────────────────────
pw_otp_store:             dict[str, dict] = {}
pw_current_attempt_store: dict[str, dict] = {}
pw_persistent_locks:      dict[str, dict] = {}


def get_pool():
    """
    Always read the live pool from config.database at request time.

    Do NOT use:
        from config.database import pool

    because that can keep the old None value from module import time.
    """
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


def now_ms() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# ── Lock helpers ──────────────────────────────────────────────────────────────

def get_pw_persistent_locks(user_id: str) -> dict:
    if user_id not in pw_persistent_locks:
        pw_persistent_locks[user_id] = {"locked_until": None}
    return pw_persistent_locks[user_id]


def set_pw_lock(user_id: str, value: Optional[int]) -> None:
    get_pw_persistent_locks(user_id)["locked_until"] = value
    if user_id in pw_otp_store:
        pw_otp_store[user_id]["locked_until"] = value


def reset_expired_pw_lock(user_id: str, session: dict) -> None:
    if session.get("locked_until") and now_ms() >= session["locked_until"]:
        session["locked_until"]        = None
        session["resend_count"]        = 0
        session["resend_window_count"] = 0
        session["resend_window_start"] = None
        session["attempts"]            = 0
        set_pw_lock(user_id, None)


def get_pw_current_attempt_session(user_id: str) -> dict:
    if user_id not in pw_current_attempt_store:
        pw_current_attempt_store[user_id] = {
            "attempts": 0,
            "locked_until": None,
        }
    return pw_current_attempt_store[user_id]


def get_pw_session(user_id: str) -> dict:
    if user_id not in pw_otp_store:
        persisted_lock = get_pw_persistent_locks(user_id)["locked_until"]
        pw_otp_store[user_id] = {
            "otp":                 None,
            "hashed_password":     None,
            "expires_at":          None,
            "sent_at":             None,
            "attempts":            0,
            "resend_count":        0,
            "locked_until":        persisted_lock,
            "resend_window_start": None,
            "resend_window_count": 0,
            "change_count":        0,
            "window_start":        None,
        }
    return pw_otp_store[user_id]


def reset_pw_otp(session: dict) -> None:
    session["otp"]             = None
    session["hashed_password"] = None
    session["expires_at"]      = None
    session["sent_at"]         = None
    session["attempts"]        = 0

# ── Cloudinary upload helper ─────────────────────────────────────────────────
async def _cloudinary_upload(buffer: bytes, user_id: str) -> str:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: cloudinary.uploader.upload(
            buffer,
            public_id=str(user_id),
            overwrite=True,
            folder="profiles",
            resource_type="image",
        )
    )
    return result["secure_url"]

# ── DB-backed change count ────────────────────────────────────────────────────

async def get_db_change_count(user_id) -> dict:
    try:
        row = await get_pool().fetchrow(
            "SELECT pw_change_count, pw_window_start FROM users WHERE user_id = $1",
            user_id,
        )
        if not row:
            return {"change_count": 0, "window_start": None}

        return {
            "change_count": row["pw_change_count"] or 0,
            "window_start": int(row["pw_window_start"]) if row["pw_window_start"] else None,
        }
    except Exception as e:
        print(f"get_db_change_count error: {e}")
        return {"change_count": 0, "window_start": None}


async def reset_db_change_count_if_expired(user_id) -> None:
    try:
        row = await get_pool().fetchrow(
            "SELECT pw_window_start FROM users WHERE user_id = $1",
            user_id,
        )
        if not row:
            return

        ws = int(row["pw_window_start"]) if row["pw_window_start"] else None

        if ws and now_ms() - ws >= PW_WINDOW_MS:
            await get_pool().execute(
                "UPDATE users SET pw_change_count = 0, pw_window_start = NULL WHERE user_id = $1",
                user_id,
            )
    except Exception as e:
        print(f"reset_db_change_count_if_expired error: {e}")


async def increment_db_change_count(user_id) -> None:
    try:
        await get_pool().execute(
            """UPDATE users
               SET pw_change_count = pw_change_count + 1,
                   pw_window_start = COALESCE(pw_window_start, $2::BIGINT)
               WHERE user_id = $1""",
            user_id,
            now_ms(),
        )
    except Exception as e:
        print(f"increment_db_change_count error: {e}")


# ── Shared helpers ────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_repo() -> UserModel:
    return UserModel(get_pool())


# =============================================================================
# HANDLERS — all take only (request: Request), body read via request.json()
# =============================================================================

async def get_profile(request: Request):
    user_id = request.state.user["user_id"]

    try:
        profile = await _user_repo().get_profile(user_id)

        if not profile:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "Profile not found",
                },
            )

        return {
            "success": True,
            "user": profile,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_profile error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to fetch profile",
            },
        )


async def check_phone_availability(request: Request):
    current_user = request.state.user

    try:
        body = await request.json()
        phone = body.get("phone")
        exclude_current = body.get("exclude_current", False)

        if not phone:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Phone number is required",
                },
            )

        exclude_id = current_user["user_id"] if exclude_current else None
        available = await _user_repo().check_phone_availability(phone, exclude_id)

        return {"available": available}

    except HTTPException:
        raise
    except Exception as e:
        print(f"check_phone_availability error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Error checking phone availability",
            },
        )


async def upload_profile_picture(request: Request):
    current_user = request.state.user

    try:
        form = await request.form()
        file = form.get("profilePicture")

        if not file:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "No image file provided",
                },
            )

        buffer = await file.read()
        profile_picture = await _cloudinary_upload(buffer, current_user["user_id"])

        await _user_repo().update_profile_picture(
            current_user["user_id"],
            profile_picture,
        )

        return {
            "success": True,
            "message": "Profile picture updated successfully",
            "profile_picture": profile_picture,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"upload_profile_picture error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to upload profile picture",
            },
        )


async def update_profile(request: Request):
    current_user = request.state.user
    user_id = current_user["user_id"]
    id_ = request.path_params["id"]

    if str(user_id) != str(id_):
        raise HTTPException(
            status_code=403,
            detail={"success": False, "message": "You can only update your own profile"},
        )

    try:
        # ✅ Read as form data, not JSON
        form = await request.form()

        def clean(v):
            return v.strip() if isinstance(v, str) else (v or None)

        fields = {
            k: clean(form.get(k))
            for k in (
                "first_name", "last_name", "middle_name", "suffix",
                "gender", "phone", "alternate_phone",
                "region_code", "province_code", "municipality_code",
                "barangay_code", "address_line",
            )
        }

        # Also grab email from form if your flow ever sends it directly,
        # but keep the verified-session email as the source of truth
        session_verified_email = get_verified_email(user_id)
        email = session_verified_email or None

        if email:
            current_user_data = await _user_repo().get_user_by_id(user_id)
            if current_user_data and current_user_data.get("email"):
                set_old_email_for_notification(
                    user_id,
                    current_user_data["email"],
                )

        validation = ProfileValidator.validate_profile_update(fields)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Validation failed",
                    "errors": validation["errors"],
                },
            )

        repo = _user_repo()

        if fields["phone"] and not await repo.check_phone_availability(fields["phone"], user_id):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Phone number is already registered to another user",
                },
            )

        if fields["alternate_phone"] and not await repo.check_phone_availability(fields["alternate_phone"], user_id):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Alternate phone number is already registered to another user",
                },
            )

        updated_user = await repo.update_profile(
            user_id,
            {
                **fields,
                "email": email,
            },
        )

        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if email:
            await consume_session(user_id)

        fresh_profile = await repo.get_profile(user_id)

        await log_audit(
            user_id=user_id,
            username=current_user.get("username"),
            event_name="Profile & Email Updated" if email else "Profile Updated",
            description=f"Updated profile and changed email to {email}" if email else "Updated profile",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "Profile updated successfully",
            "user": fresh_profile,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"update_profile error: {e}")

        if hasattr(e, "pgcode") and e.pgcode == "23505":
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Phone number is already registered to another user",
                },
            )

        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to update profile",
            },
        )


async def change_password(request: Request):
    current_user = request.state.user
    user_id = current_user["user_id"]

    try:
        body = await request.json()
        current_password = (body.get("currentPassword") or body.get("current_password") or "").strip()
        new_password     = (body.get("newPassword")      or body.get("new_password")      or "").strip()
        confirm_password = (body.get("confirmPassword")  or body.get("confirm_password")  or "").strip()

        validation = ProfileValidator.validate_password_change({
            "currentPassword": current_password,
            "newPassword": new_password,
            "confirmPassword": confirm_password,
        })

        if not validation["is_valid"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Validation failed",
                    "errors": validation["errors"],
                },
            )

        repo = _user_repo()
        user = await repo.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if user.get("status") == "deactivated":
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "message": "Account is deactivated",
                },
            )

        if not bcrypt.checkpw(current_password.encode(), user["password"].encode()):
            raise HTTPException(
                status_code=401,
                detail={
                    "success": False,
                    "message": "Current password is incorrect",
                },
            )

        if bcrypt.checkpw(new_password.encode(), user["password"].encode()):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "New password cannot be the same as the current password",
                },
            )

        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(12)).decode()

        await repo.update_password(user_id, hashed)
        await revoke_all_user_tokens(user_id)

        return {
            "success": True,
            "message": "Password changed successfully. Please login again with your new password.",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"change_password error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to change password",
            },
        )


async def upload_profile_picture_for_user(request: Request):
    current_user = request.state.user
    user_id = request.path_params["user_id"]

    try:
        form = await request.form()
        file = form.get("profilePicture")

        if not file:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "No image file provided",
                },
            )

        buffer = await file.read()
        profile_picture = await _cloudinary_upload(buffer, user_id)

        await _user_repo().update_profile_picture(user_id, profile_picture)

        await log_audit(
            user_id=current_user["user_id"],
            username=current_user.get("username"),
            event_name="Profile Image Changed",
            description=f"Updated profile picture for user ID {user_id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "Profile picture updated successfully",
            "profile_picture": profile_picture,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"upload_profile_picture_for_user error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to upload profile picture",
            },
        )


# =============================================================================
# PASSWORD CHANGE WITH OTP
# =============================================================================

async def get_password_status(request: Request):
    user_id = str(request.state.user["user_id"])

    try:
        await reset_db_change_count_if_expired(user_id)

        data = await get_db_change_count(user_id)
        change_count = data["change_count"]
        window_start = data["window_start"]

        if window_start and now_ms() - window_start < PW_WINDOW_MS:
            if change_count >= PW_MAX_CHANGES:
                ms_left = PW_WINDOW_MS - (now_ms() - window_start)
                hours_left = math.ceil(ms_left / 3_600_000)

                return {
                    "blocked": True,
                    "hoursLeft": hours_left,
                    "msLeft": ms_left,
                }

        session = get_pw_session(user_id)
        reset_expired_pw_lock(user_id, session)

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)

            return {
                "blocked": False,
                "sessionLocked": True,
                "minsLeft": mins_left,
            }

        attempt_session = get_pw_current_attempt_session(user_id)

        if attempt_session.get("locked_until") and now_ms() < attempt_session["locked_until"]:
            mins_left = math.ceil((attempt_session["locked_until"] - now_ms()) / 60_000)

            return {
                "blocked": False,
                "pwLocked": True,
                "minsLeft": mins_left,
            }

        return {"blocked": False}

    except Exception as e:
        print(f"get_password_status error: {e}")
        return {"blocked": False}


async def force_password_lock(request: Request):
    user_id = str(request.state.user["user_id"])

    try:
        session = get_pw_session(user_id)

        if session.get("resend_count", 0) >= PW_MAX_RESENDS:
            lu = session.get("locked_until")
            if not lu or now_ms() >= lu:
                set_pw_lock(user_id, now_ms() + PW_OTP_LOCKOUT_MS)

        return {"success": True}

    except Exception as e:
        print(f"force_password_lock error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False},
        )


async def verify_current_password(request: Request):
    user_id = str(request.state.user["user_id"])

    try:
        body = await request.json()
        current_password = (body.get("currentPassword") or body.get("current_password") or "").strip()

        if not current_password:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Current password is required",
                },
            )

        session = get_pw_session(user_id)
        reset_expired_pw_lock(user_id, session)

        await reset_db_change_count_if_expired(user_id)

        data = await get_db_change_count(user_id)

        if data["window_start"] and now_ms() - data["window_start"] < PW_WINDOW_MS:
            if data["change_count"] >= PW_MAX_CHANGES:
                ms_left = PW_WINDOW_MS - (now_ms() - data["window_start"])
                hours_left = math.ceil(ms_left / 3_600_000)

                raise HTTPException(
                    status_code=429,
                    detail={
                        "success": False,
                        "blocked": True,
                        "rateLimited": True,
                        "message": "You've already changed your password twice today. You can update it again after 24 hours.",
                        "hoursLeft": hours_left,
                        "msLeft": ms_left,
                    },
                )

        attempt_session = get_pw_current_attempt_session(user_id)

        user = await _user_repo().get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if user.get("status") == "deactivated":
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "message": "Account is deactivated",
                },
            )

        if not bcrypt.checkpw(current_password.encode(), user["password"].encode()):
            attempt_session["attempts"] = attempt_session.get("attempts", 0) + 1
            attempts_left = PW_MAX_CURRENT_ATTEMPTS - attempt_session["attempts"]

            if attempts_left <= 0:
                attempt_session["locked_until"] = now_ms() + PW_CURRENT_LOCKOUT_MS
                attempt_session["attempts"] = 0

                raise HTTPException(
                    status_code=401,
                    detail={
                        "success": False,
                        "locked": True,
                        "message": "Too many incorrect attempts. Your account is locked for 15 minutes.",
                        "attemptsLeft": 0,
                        "minutesLeft": 15,
                    },
                )

            raise HTTPException(
                status_code=401,
                detail={
                    "success": False,
                    "message": f"Incorrect password — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
                    "attemptsLeft": attempts_left,
                },
            )

        attempt_session["attempts"] = 0
        attempt_session["locked_until"] = None

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        print(f"verify_current_password error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Server error. Please try again.",
            },
        )


async def request_password_otp(request: Request):
    current_user = request.state.user
    user_id = current_user["user_id"]

    try:
        body = await request.json()
        current_password = (body.get("currentPassword") or body.get("current_password") or "").strip()
        new_password     = (body.get("newPassword")      or body.get("new_password")      or "").strip()
        confirm_password = (body.get("confirmPassword")  or body.get("confirm_password")  or "").strip()

        session = get_pw_session(str(user_id))
        reset_expired_pw_lock(str(user_id), session)

        await reset_db_change_count_if_expired(user_id)

        data = await get_db_change_count(user_id)

        if data["window_start"] and now_ms() - data["window_start"] < PW_WINDOW_MS:
            if data["change_count"] >= PW_MAX_CHANGES:
                ms_left = PW_WINDOW_MS - (now_ms() - data["window_start"])
                hours_left = math.ceil(ms_left / 3_600_000)

                raise HTTPException(
                    status_code=429,
                    detail={
                        "success": False,
                        "blocked": True,
                        "rateLimited": True,
                        "message": "You've already changed your password twice today. You can update it again after 24 hours.",
                        "hoursLeft": hours_left,
                        "msLeft": ms_left,
                    },
                )

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)

            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "sessionLocked": True,
                    "message": f"Too many failed attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                    "minutesLeft": mins_left,
                },
            )

        if session.get("resend_count", 0) >= PW_MAX_RESENDS:
            set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)

            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "sessionLocked": True,
                    "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                    "minutesLeft": 15,
                },
            )

        if (
            session.get("resend_window_start")
            and now_ms() - session["resend_window_start"] < PW_RESEND_WINDOW_MS
        ):
            if session.get("resend_window_count", 0) >= PW_MAX_RESENDS:
                set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)

                raise HTTPException(
                    status_code=429,
                    detail={
                        "success": False,
                        "sessionLocked": True,
                        "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                        "minutesLeft": 15,
                    },
                )
        else:
            session["resend_window_start"] = now_ms()
            session["resend_window_count"] = 0

        repo = _user_repo()
        user = await repo.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "message": "User not found",
                },
            )

        if user.get("status") == "deactivated":
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "message": "Account is deactivated",
                },
            )

        if not bcrypt.checkpw(current_password.encode(), user["password"].encode()):
            raise HTTPException(
                status_code=401,
                detail={
                    "success": False,
                    "message": "Current password is incorrect. Please go back and re-enter it.",
                },
            )

        validation = ProfileValidator.validate_password_change({
            "currentPassword": current_password,
            "newPassword": new_password,
            "confirmPassword": confirm_password,
        })

        if not validation["is_valid"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Validation failed",
                    "errors": validation["errors"],
                },
            )

        if bcrypt.checkpw(new_password.encode(), user["password"].encode()):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "New password cannot be the same as current password",
                },
            )

        row = await get_pool().fetchrow(
            "SELECT email, first_name FROM users WHERE user_id = $1",
            user_id,
        )

        email = row["email"] if row else None
        first_name = row["first_name"] if row else None

        if not email:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "No email address on file",
                },
            )

        otp = str(secrets.randbelow(900000) + 100000)
        hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(12)).decode()

        session["otp"]                 = otp
        session["hashed_password"]     = hashed_password
        session["expires_at"]          = now_ms() + PW_OTP_EXPIRY
        session["sent_at"]             = now_ms()
        session["attempts"]            = 0
        session["resend_count"]        = session.get("resend_count", 0) + 1
        session["resend_window_count"] = session.get("resend_window_count", 0) + 1

        result = await send_password_otp_email(
            email,
            first_name or "User",
            otp,
        )

        if not result.get("success"):
            session["resend_count"] -= 1
            session["resend_window_count"] -= 1

            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "message": "Failed to send verification code. Please try again.",
                },
            )

        at = email.index("@")
        local = email[:at]
        domain = email[at:]

        masked = (
            local[0] + "*" + domain
            if len(local) <= 2
            else local[0] + "*" * (len(local) - 3) + local[-2:] + domain
        )

        return {
            "success": True,
            "maskedEmail": masked,
            "resendsLeft": PW_MAX_RESENDS - session["resend_count"],
            "otpExpiresAt": session["expires_at"],
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"request_password_otp error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Server error. Please try again.",
            },
        )


async def change_password_with_otp(request: Request):
    current_user = request.state.user
    user_id = current_user["user_id"]

    try:
        body = await request.json()
        submitted = (body.get("otp") or "").strip()
        session = get_pw_session(str(user_id))

        reset_expired_pw_lock(str(user_id), session)

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)

            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "locked": True,
                    "message": f"Too many failed attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                },
            )

        if not session.get("otp"):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "No pending verification. Please start over.",
                },
            )

        if now_ms() > session["expires_at"]:
            reset_pw_otp(session)

            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": "Code expired. Please request a new one.",
                },
            )

        session["attempts"] = session.get("attempts", 0) + 1

        if submitted != session["otp"]:
            left = PW_MAX_OTP_ATTEMPTS - session["attempts"]

            if left <= 0:
                resends_exhausted = session.get("resend_count", 0) >= PW_MAX_RESENDS
                reset_pw_otp(session)

                if resends_exhausted:
                    set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)

                    raise HTTPException(
                        status_code=429,
                        detail={
                            "success": False,
                            "sessionLocked": True,
                            "autoClose": True,
                            "message": "Too many incorrect attempts and no resends remaining. Please try again in 15 minutes.",
                            "minutesLeft": 15,
                        },
                    )

                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "forceResend": True,
                        "message": "Too many incorrect attempts. Please request a new code.",
                        "resendsLeft": PW_MAX_RESENDS - session.get("resend_count", 0),
                    },
                )

            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "message": f"Incorrect code — {left} attempt{'s' if left != 1 else ''} remaining",
                    "attemptsLeft": left,
                },
            )

        hashed_password = session["hashed_password"]
        reset_pw_otp(session)

        await increment_db_change_count(user_id)

        session["resend_count"] = 0
        session["resend_window_count"] = 0
        session["resend_window_start"] = None

        set_pw_lock(str(user_id), None)

        attempt_session = get_pw_current_attempt_session(str(user_id))
        attempt_session["attempts"] = 0
        attempt_session["locked_until"] = None

        repo = _user_repo()

        await repo.update_password(user_id, hashed_password)
        await repo.update_password_changed_at(user_id)
        await revoke_all_user_tokens(user_id)

        row = await get_pool().fetchrow(
            "SELECT email, first_name FROM users WHERE user_id = $1",
            user_id,
        )

        email = row["email"] if row else None
        first_name = row["first_name"] if row else None

        if email:
            try:
                await send_password_changed_notification(
                    email,
                    first_name or "User",
                )
            except Exception as e:
                print(f"send_password_changed_notification error: {e}")

        data = await get_db_change_count(user_id)

        await log_audit(
            user_id=current_user["user_id"],
            username=current_user.get("username"),
            event_name="Password Changed",
            description="Password changed via OTP verification",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "Password changed successfully! Please login with your new password.",
            "changesLeft": max(0, PW_MAX_CHANGES - data["change_count"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"change_password_with_otp error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Server error. Please try again.",
            },
        )