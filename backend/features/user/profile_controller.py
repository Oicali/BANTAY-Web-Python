# ================================================================================
# FILE: backend/features/user/profile_controller.py
# ================================================================================

import math
import os
import secrets
import uuid
from typing import Optional

from flask import request, jsonify, g

from config.database import get_db, get_pool
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


PW_OTP_EXPIRY           = 2  * 60 * 1000
PW_MAX_OTP_ATTEMPTS     = 3
PW_MAX_RESENDS          = 3
PW_OTP_LOCKOUT_MS       = 15 * 60 * 1000
PW_MAX_CHANGES          = 2
PW_WINDOW_MS            = 24 * 60 * 60 * 1000
PW_RESEND_WINDOW_MS     = 15 * 60 * 1000
PW_MAX_CURRENT_ATTEMPTS = 5
PW_CURRENT_LOCKOUT_MS   = 15 * 60 * 1000


pw_otp_store:             dict[str, dict] = {}
pw_current_attempt_store: dict[str, dict] = {}
pw_persistent_locks:      dict[str, dict] = {}


def now_ms() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp() * 1000)


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
            "attempts":     0,
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


_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "profiles",
)

_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def _save_profile_picture(file, user_id: str) -> str:
    os.makedirs(_UPLOAD_DIR, exist_ok=True)

    original_filename = file.filename or ""
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "jpg"

    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: .{ext}")

    for existing in os.listdir(_UPLOAD_DIR):
        if existing.startswith(f"{user_id}_"):
            try:
                os.remove(os.path.join(_UPLOAD_DIR, existing))
            except OSError:
                pass

    filename    = f"{user_id}_{uuid.uuid4().hex}.{ext}"
    destination = os.path.join(_UPLOAD_DIR, filename)
    file.save(destination)
    return f"/uploads/profiles/{filename}"


def get_db_change_count(user_id) -> dict:
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT pw_change_count, pw_window_start FROM users WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return {"change_count": 0, "window_start": None}
        return {
            "change_count": row["pw_change_count"] or 0,
            "window_start": int(row["pw_window_start"]) if row["pw_window_start"] else None,
        }
    except Exception as e:
        print(f"get_db_change_count error: {e}")
        return {"change_count": 0, "window_start": None}


def reset_db_change_count_if_expired(user_id) -> None:
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT pw_window_start FROM users WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return
        ws = int(row["pw_window_start"]) if row["pw_window_start"] else None
        if ws and now_ms() - ws >= PW_WINDOW_MS:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET pw_change_count = 0, pw_window_start = NULL WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
            cursor.close()
    except Exception as e:
        print(f"reset_db_change_count_if_expired error: {e}")


def increment_db_change_count(user_id) -> None:
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE users
               SET pw_change_count = pw_change_count + 1,
                   pw_window_start = COALESCE(pw_window_start, %s)
               WHERE user_id = %s""",
            (now_ms(), user_id),
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"increment_db_change_count error: {e}")


def get_client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


def _user_repo() -> UserModel:
    return UserModel(get_pool())


def _err(status: int, **kwargs):
    return jsonify({"success": False, **kwargs}), status


def _ok(**kwargs):
    return jsonify({"success": True, **kwargs})


def _fetchrow(sql: str, params: tuple) -> Optional[dict]:
    """Run a SELECT and return the first row as a dict, or None."""
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    return dict(row) if row else None


def get_profile():
    user_id = g.user["user_id"]

    try:
        profile = _user_repo().get_profile(user_id)

        if not profile:
            return _err(404, message="Profile not found")

        return _ok(user=profile)

    except Exception as e:
        print(f"get_profile error: {e}")
        return _err(500, message="Failed to fetch profile")


def check_phone_availability():
    current_user = g.user

    try:
        body            = request.get_json(force=True) or {}
        phone           = body.get("phone")
        exclude_current = body.get("exclude_current", False)

        if not phone:
            return _err(400, message="Phone number is required")

        exclude_id = current_user["user_id"] if exclude_current else None
        available  = _user_repo().check_phone_availability(phone, exclude_id)

        return jsonify({"available": available})

    except Exception as e:
        print(f"check_phone_availability error: {e}")
        return _err(500, message="Error checking phone availability")


def upload_profile_picture():
    current_user = g.user

    try:
        file = request.files.get("profilePicture")

        if not file:
            return _err(400, message="No image file provided")

        profile_picture = _save_profile_picture(file, str(current_user["user_id"]))
        _user_repo().update_profile_picture(current_user["user_id"], profile_picture)

        return _ok(
            message="Profile picture updated successfully",
            profile_picture=profile_picture,
        )

    except Exception as e:
        print(f"upload_profile_picture error: {e}")
        return _err(500, message="Failed to upload profile picture")


def update_profile(id):
    current_user = g.user
    user_id      = current_user["user_id"]

    if str(user_id) != str(id):
        return _err(403, message="You can only update your own profile")

    try:
        form = request.form

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

        session_verified_email = get_verified_email(user_id)
        email = session_verified_email or None

        if email:
            current_user_data = _user_repo().get_user_by_id(user_id)
            if current_user_data and current_user_data.get("email"):
                set_old_email_for_notification(user_id, current_user_data["email"])

        validation = ProfileValidator.validate_profile_update(fields)
        if not validation["is_valid"]:
            return _err(400, message="Validation failed", errors=validation["errors"])

        repo = _user_repo()

        if fields["phone"] and not repo.check_phone_availability(fields["phone"], user_id):
            return _err(400, message="Phone number is already registered to another user")

        if fields["alternate_phone"] and not repo.check_phone_availability(fields["alternate_phone"], user_id):
            return _err(400, message="Alternate phone number is already registered to another user")

        updated_user = repo.update_profile(user_id, {**fields, "email": email})

        if not updated_user:
            return _err(404, message="User not found")

        if email:
            consume_session(user_id)

        fresh_profile = repo.get_profile(user_id)

        log_audit(
            user_id=user_id,
            username=current_user.get("username"),
            event_name="Profile & Email Updated" if email else "Profile Updated",
            description=f"Updated profile and changed email to {email}" if email else "Updated profile",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(),
        )

        return _ok(message="Profile updated successfully", user=fresh_profile)

    except Exception as e:
        print(f"update_profile error: {e}")

        if hasattr(e, "errno") and e.errno == 1062:  # MySQL duplicate entry
            return _err(400, message="Phone number is already registered to another user")

        return _err(500, message="Failed to update profile")


def upload_profile_picture_for_user(user_id):
    current_user = g.user

    try:
        file = request.files.get("profilePicture")

        if not file:
            return _err(400, message="No image file provided")

        profile_picture = _save_profile_picture(file, str(user_id))
        _user_repo().update_profile_picture(user_id, profile_picture)

        log_audit(
            user_id=current_user["user_id"],
            username=current_user.get("username"),
            event_name="Profile Image Changed",
            description=f"Updated profile picture for user ID {user_id}",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(),
        )

        return _ok(
            message="Profile picture updated successfully",
            profile_picture=profile_picture,
        )

    except Exception as e:
        print(f"upload_profile_picture_for_user error: {e}")
        return _err(500, message="Failed to upload profile picture")


def get_password_status():
    user_id = str(g.user["user_id"])

    try:
        reset_db_change_count_if_expired(user_id)

        data         = get_db_change_count(user_id)
        change_count = data["change_count"]
        window_start = data["window_start"]

        if window_start and now_ms() - window_start < PW_WINDOW_MS:
            if change_count >= PW_MAX_CHANGES:
                ms_left    = PW_WINDOW_MS - (now_ms() - window_start)
                hours_left = math.ceil(ms_left / 3_600_000)
                return jsonify({"blocked": True, "hoursLeft": hours_left, "msLeft": ms_left})

        session = get_pw_session(user_id)
        reset_expired_pw_lock(user_id, session)

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)
            return jsonify({"blocked": False, "sessionLocked": True, "minsLeft": mins_left})

        attempt_session = get_pw_current_attempt_session(user_id)

        if attempt_session.get("locked_until") and now_ms() < attempt_session["locked_until"]:
            mins_left = math.ceil((attempt_session["locked_until"] - now_ms()) / 60_000)
            return jsonify({"blocked": False, "pwLocked": True, "minsLeft": mins_left})

        return jsonify({"blocked": False})

    except Exception as e:
        print(f"get_password_status error: {e}")
        return jsonify({"blocked": False})


def force_password_lock():
    user_id = str(g.user["user_id"])

    try:
        session = get_pw_session(user_id)

        if session.get("resend_count", 0) >= PW_MAX_RESENDS:
            lu = session.get("locked_until")
            if not lu or now_ms() >= lu:
                set_pw_lock(user_id, now_ms() + PW_OTP_LOCKOUT_MS)

        return _ok()

    except Exception as e:
        print(f"force_password_lock error: {e}")
        return _err(500)


def verify_current_password():
    user_id = str(g.user["user_id"])

    try:
        body             = request.get_json(force=True) or {}
        current_password = (body.get("currentPassword") or body.get("current_password") or "").strip()

        if not current_password:
            return _err(400, message="Current password is required")

        session = get_pw_session(user_id)
        reset_expired_pw_lock(user_id, session)

        reset_db_change_count_if_expired(user_id)
        data = get_db_change_count(user_id)

        if data["window_start"] and now_ms() - data["window_start"] < PW_WINDOW_MS:
            if data["change_count"] >= PW_MAX_CHANGES:
                ms_left    = PW_WINDOW_MS - (now_ms() - data["window_start"])
                hours_left = math.ceil(ms_left / 3_600_000)
                return _err(
                    429,
                    blocked=True, rateLimited=True,
                    message="You've already changed your password twice today. You can update it again after 24 hours.",
                    hoursLeft=hours_left, msLeft=ms_left,
                )

        attempt_session = get_pw_current_attempt_session(user_id)

        if attempt_session.get("locked_until") and now_ms() < attempt_session["locked_until"]:
            mins_left = math.ceil((attempt_session["locked_until"] - now_ms()) / 60_000)
            return _err(
                429,
                locked=True,
                message=f"Too many incorrect attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                minutesLeft=mins_left,
            )

        user = _user_repo().get_user_by_id(user_id)

        if not user:
            return _err(404, message="User not found")

        if user.get("status") == "deactivated":
            return _err(403, message="Account is deactivated")

        if current_password != user["password"]:
            attempt_session["attempts"] = attempt_session.get("attempts", 0) + 1
            attempts_left = PW_MAX_CURRENT_ATTEMPTS - attempt_session["attempts"]

            if attempts_left <= 0:
                attempt_session["locked_until"] = now_ms() + PW_CURRENT_LOCKOUT_MS
                attempt_session["attempts"]     = 0
                return _err(
                    401,
                    locked=True,
                    message="Too many incorrect attempts. Your account is locked for 15 minutes.",
                    attemptsLeft=0, minutesLeft=15,
                )

            return _err(
                401,
                message=f"Incorrect password — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
                attemptsLeft=attempts_left,
            )

        attempt_session["attempts"]     = 0
        attempt_session["locked_until"] = None

        return _ok()

    except Exception as e:
        print(f"verify_current_password error: {e}")
        return _err(500, message="Server error. Please try again.")


def request_password_otp():
    current_user = g.user
    user_id      = current_user["user_id"]

    try:
        body             = request.get_json(force=True) or {}
        current_password = (body.get("currentPassword") or body.get("current_password") or "").strip()
        new_password     = (body.get("newPassword")      or body.get("new_password")      or "").strip()
        confirm_password = (body.get("confirmPassword")  or body.get("confirm_password")  or "").strip()

        session = get_pw_session(str(user_id))
        reset_expired_pw_lock(str(user_id), session)

        reset_db_change_count_if_expired(user_id)
        data = get_db_change_count(user_id)

        if data["window_start"] and now_ms() - data["window_start"] < PW_WINDOW_MS:
            if data["change_count"] >= PW_MAX_CHANGES:
                ms_left    = PW_WINDOW_MS - (now_ms() - data["window_start"])
                hours_left = math.ceil(ms_left / 3_600_000)
                return _err(
                    429,
                    blocked=True, rateLimited=True,
                    message="You've already changed your password twice today. You can update it again after 24 hours.",
                    hoursLeft=hours_left, msLeft=ms_left,
                )

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)
            return _err(
                429,
                sessionLocked=True,
                message=f"Too many failed attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                minutesLeft=mins_left,
            )

        if session.get("resend_count", 0) >= PW_MAX_RESENDS:
            set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)
            return _err(
                429,
                sessionLocked=True,
                message="Maximum codes sent. For security, this process is locked for 15 minutes.",
                minutesLeft=15,
            )

        if (
            session.get("resend_window_start")
            and now_ms() - session["resend_window_start"] < PW_RESEND_WINDOW_MS
        ):
            if session.get("resend_window_count", 0) >= PW_MAX_RESENDS:
                set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)
                return _err(
                    429,
                    sessionLocked=True,
                    message="Maximum codes sent. For security, this process is locked for 15 minutes.",
                    minutesLeft=15,
                )
        else:
            session["resend_window_start"] = now_ms()
            session["resend_window_count"] = 0

        user = _user_repo().get_user_by_id(user_id)

        if not user:
            return _err(404, message="User not found")

        if user.get("status") == "deactivated":
            return _err(403, message="Account is deactivated")

        if current_password != user["password"]:
            return _err(401, message="Current password is incorrect. Please go back and re-enter it.")

        validation = ProfileValidator.validate_password_change({
            "currentPassword": current_password,
            "newPassword":     new_password,
            "confirmPassword": confirm_password,
        })

        if not validation["is_valid"]:
            return _err(400, message="Validation failed", errors=validation["errors"])

        if new_password == user["password"]:
            return _err(400, message="New password cannot be the same as current password")

        row = _fetchrow(
            "SELECT email, first_name FROM users WHERE user_id = %s",
            (user_id,),
        )

        email      = row["email"]      if row else None
        first_name = row["first_name"] if row else None

        if not email:
            return _err(400, message="No email address on file")

        otp = str(secrets.randbelow(900000) + 100000)

        session["otp"]                 = otp
        session["hashed_password"]     = new_password  # plaintext, no hashing needed
        session["expires_at"]          = now_ms() + PW_OTP_EXPIRY
        session["sent_at"]             = now_ms()
        session["attempts"]            = 0
        session["resend_count"]        = session.get("resend_count", 0) + 1
        session["resend_window_count"] = session.get("resend_window_count", 0) + 1

        result = send_password_otp_email(email, first_name or "User", otp)

        if not result.get("success"):
            session["resend_count"]        -= 1
            session["resend_window_count"] -= 1
            return _err(500, message="Failed to send verification code. Please try again.")

        at     = email.index("@")
        local  = email[:at]
        domain = email[at:]
        masked = (
            local[0] + "*" + domain
            if len(local) <= 2
            else local[0] + "*" * (len(local) - 3) + local[-2:] + domain
        )

        return _ok(
            maskedEmail=masked,
            resendsLeft=PW_MAX_RESENDS - session["resend_count"],
            otpExpiresAt=session["expires_at"],
        )

    except Exception as e:
        print(f"request_password_otp error: {e}")
        return _err(500, message="Server error. Please try again.")



def change_password_with_otp():
    current_user = g.user
    user_id      = current_user["user_id"]

    try:
        body      = request.get_json(force=True) or {}
        submitted = (body.get("otp") or "").strip()
        session   = get_pw_session(str(user_id))

        reset_expired_pw_lock(str(user_id), session)

        if session.get("locked_until") and now_ms() < session["locked_until"]:
            mins_left = math.ceil((session["locked_until"] - now_ms()) / 60_000)
            return _err(
                429,
                locked=True,
                message=f"Too many failed attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
            )

        if not session.get("otp"):
            return _err(400, message="No pending verification. Please start over.")

        if now_ms() > session["expires_at"]:
            reset_pw_otp(session)
            return _err(400, message="Code expired. Please request a new one.")

        session["attempts"] = session.get("attempts", 0) + 1

        if submitted != session["otp"]:
            left = PW_MAX_OTP_ATTEMPTS - session["attempts"]

            if left <= 0:
                resends_exhausted = session.get("resend_count", 0) >= PW_MAX_RESENDS
                reset_pw_otp(session)

                if resends_exhausted:
                    set_pw_lock(str(user_id), now_ms() + PW_OTP_LOCKOUT_MS)
                    return _err(
                        429,
                        sessionLocked=True, autoClose=True,
                        message="Too many incorrect attempts and no resends remaining. Please try again in 15 minutes.",
                        minutesLeft=15,
                    )

                return _err(
                    400,
                    forceResend=True,
                    message="Too many incorrect attempts. Please request a new code.",
                    resendsLeft=PW_MAX_RESENDS - session.get("resend_count", 0),
                )

            return _err(
                400,
                message=f"Incorrect code — {left} attempt{'s' if left != 1 else ''} remaining",
                attemptsLeft=left,
            )

        new_password = session["hashed_password"]  # plaintext password stored in session
        reset_pw_otp(session)

        increment_db_change_count(user_id)

        session["resend_count"]        = 0
        session["resend_window_count"] = 0
        session["resend_window_start"] = None

        set_pw_lock(str(user_id), None)

        attempt_session                 = get_pw_current_attempt_session(str(user_id))
        attempt_session["attempts"]     = 0
        attempt_session["locked_until"] = None

        repo = _user_repo()
        repo.update_password(user_id, new_password)
        repo.update_password_changed_at(user_id)
        revoke_all_user_tokens(user_id)

        row = _fetchrow(
            "SELECT email, first_name FROM users WHERE user_id = %s",
            (user_id,),
        )

        email      = row["email"]      if row else None
        first_name = row["first_name"] if row else None

        if email:
            try:
                send_password_changed_notification(email, first_name or "User")
            except Exception as e:
                print(f"send_password_changed_notification error: {e}")

        data = get_db_change_count(user_id)

        log_audit(
            user_id=current_user["user_id"],
            username=current_user.get("username"),
            event_name="Password Changed",
            description="Password changed via OTP verification",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(),
        )

        return _ok(
            message="Password changed successfully! Please login with your new password.",
            changesLeft=max(0, PW_MAX_CHANGES - data["change_count"]),
        )

    except Exception as e:
        print(f"change_password_with_otp error: {e}")
        return _err(500, message="Server error. Please try again.")