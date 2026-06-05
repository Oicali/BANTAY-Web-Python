"""
email_verification_controller.py  (Flask / sync rewrite)
Converted from the FastAPI async version.

Assumptions about your Flask app:
  - request.user  has a  .user_id  attribute  (set by your auth middleware)
  - request.db    is a live MySQL connection   (set by your DB middleware)
  - Plain-text password comparison (no hashing)
"""

import secrets
import time
import threading
from typing import Optional

from flask import Blueprint, request, jsonify, abort, g

from config.database import get_db
from features.user.email_service import send_otp_email, send_email_changed_notification

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
bp = Blueprint("email_verification", __name__, url_prefix="/users/email")

# ---------------------------------------------------------------------------
# Constants  (mirror original values exactly)
# ---------------------------------------------------------------------------
OTP_EXPIRY_MS     = 2  * 60 * 1_000
EMAIL_COOLDOWN_MS = 24 * 60 * 60 * 1_000
RESEND_WAIT_MS    = 60 * 1_000
PW_MAX_ATTEMPTS   = 5
OTP_MAX_ATTEMPTS  = 3
MAX_RESENDS       = 3
PW_LOCKOUT_MS     = 15 * 60 * 1_000
RESEND_WINDOW_MS  = 15 * 60 * 1_000
SESSION_LOCK_MS   = 15 * 60 * 1_000


def _now() -> int:
    """Current time in milliseconds."""
    return int(time.time() * 1_000)


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_sessions: dict[str, dict] = {}
_persistent_locks: dict[str, dict] = {}


def _get_persistent_locks(user_id: str) -> dict:
    key = str(user_id)
    if key not in _persistent_locks:
        _persistent_locks[key] = {
            "oldOtpLockedUntil": None,
            "newOtpLockedUntil": None,
            "pwLockedUntil":     None,
        }
    return _persistent_locks[key]


def _set_lock(user_id: str, lock_key: str, value: Optional[int]) -> None:
    key = str(user_id)
    _get_persistent_locks(key)[lock_key] = value
    if key in _sessions:
        _sessions[key][lock_key] = value


def _reset_expired_lock(
    user_id: str,
    session: dict,
    lock_key: str,
    resends_key: str,
    window_start_key: str,
    window_count_key: Optional[str],
    attempts_key: Optional[str],
) -> None:
    if session.get(lock_key) and _now() >= session[lock_key]:
        session[lock_key]         = None
        session[resends_key]      = 0
        session[window_start_key] = None
        if window_count_key:
            session[window_count_key] = 0
        if attempts_key:
            session[attempts_key] = 0
        _set_lock(user_id, lock_key, None)


def _get_session(user_id: str) -> dict:
    key = str(user_id)
    if key not in _sessions:
        locks = _get_persistent_locks(key)
        _sessions[key] = {
            "pwAttempts": 0, "pwLockedUntil": locks["pwLockedUntil"],
            "passwordVerified": False,
            "oldOtp": None, "oldOtpExpires": None, "oldOtpAttempts": 0,
            "oldOtpSentAt": None, "oldOtpResends": 0, "oldResendWindowStart": None,
            "oldOtpLockedUntil": locks["oldOtpLockedUntil"],
            "oldEmailVerified": False,
            "newEmail": None,
            "newOtp": None, "newOtpExpires": None, "newOtpAttempts": 0,
            "newOtpSentAt": None, "newOtpResends": 0, "newResendWindowStart": None,
            "newOtpLockedUntil": locks["newOtpLockedUntil"],
            "verifiedEmail": None,
            "changedAt": None,
            "_oldEmailForNotification": None,
        }
    return _sessions[key]


def _clear_session(user_id: str) -> None:
    key  = str(user_id)
    prev = _sessions.get(key)
    now  = _now()

    locks = _get_persistent_locks(key)
    if prev:
        if prev.get("oldOtpLockedUntil") and prev["oldOtpLockedUntil"] > now:
            locks["oldOtpLockedUntil"] = prev["oldOtpLockedUntil"]
        if prev.get("newOtpLockedUntil") and prev["newOtpLockedUntil"] > now:
            locks["newOtpLockedUntil"] = prev["newOtpLockedUntil"]
        if prev.get("pwLockedUntil") and prev["pwLockedUntil"] > now:
            locks["pwLockedUntil"] = prev["pwLockedUntil"]

    _sessions.pop(key, None)


def _mask_email(email: str) -> str:
    if not email:
        return ""
    at = email.find("@")
    if at < 0:
        return email
    local  = email[:at]
    domain = email[at:]
    if len(local) <= 2:
        return local[0] + "*" + domain
    if len(local) <= 4:
        return local[0] + "*" * (len(local) - 1) + domain
    return local[0] + "*" * (len(local) - 3) + local[-2:] + domain


# ---------------------------------------------------------------------------
# DB helpers  (mysql-connector-python)
# ---------------------------------------------------------------------------
def _get_user_by_id(user_id: str, db) -> Optional[dict]:
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, email, password, email_changed_at FROM users WHERE user_id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    return row or None


def _update_email_changed_at(user_id: str, db) -> None:
    cursor = db.cursor()
    cursor.execute(
        "UPDATE users SET email_changed_at = NOW() WHERE user_id = %s",
        (user_id,),
    )
    db.commit()
    cursor.close()


def _update_user_email(user_id: str, new_email: str, db) -> None:
    cursor = db.cursor()
    cursor.execute(
        "UPDATE users SET email = %s WHERE user_id = %s",
        (new_email, user_id),
    )
    db.commit()
    cursor.close()


def _get_email_by_user_id(user_id: str, db) -> Optional[str]:
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT email FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    return row["email"] if row else None


# ---------------------------------------------------------------------------
# STATUS CHECK
# GET /users/email/status
# ---------------------------------------------------------------------------
@bp.get("/status")
def get_email_status():
    user_id = str(g.user["user_id"])
    db = get_db()

    user = _get_user_by_id(user_id, db)
    if user and user.get("email_changed_at"):
        since = _now() - int(user["email_changed_at"].timestamp() * 1_000)
        if since < EMAIL_COOLDOWN_MS:
            ms_left    = EMAIL_COOLDOWN_MS - since
            hours_left = -(-ms_left // 3_600_000)
            return jsonify({"blocked": True, "hoursLeft": hours_left, "msLeft": ms_left})

    session = _get_session(user_id)

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")
    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("pwLockedUntil") and _now() < session["pwLockedUntil"]:
        mins_left = -((session["pwLockedUntil"] - _now()) // -60_000)
        return jsonify({"pwLocked": True, "minsLeft": mins_left})

    old_lock = session.get("oldOtpLockedUntil")
    new_lock = session.get("newOtpLockedUntil")
    active_lock = (
        old_lock if (old_lock and _now() < old_lock) else
        new_lock if (new_lock and _now() < new_lock) else None
    )
    if active_lock:
        mins_left = -((active_lock - _now()) // -60_000)
        return jsonify({"sessionLocked": True, "minsLeft": mins_left})

    return jsonify({"blocked": False})


# ---------------------------------------------------------------------------
# FORCE LOCK
# POST /users/email/force-lock
# ---------------------------------------------------------------------------
@bp.post("/force-lock")
def force_lock():
    user_id = str(g.user["user_id"])
    session = _get_session(user_id)
    body    = request.get_json(silent=True) or {}
    which   = body.get("which", "")

    if which == "old":
        if session.get("oldOtpResends", 0) >= MAX_RESENDS:
            locked = session.get("oldOtpLockedUntil")
            if not locked or _now() >= locked:
                _set_lock(user_id, "oldOtpLockedUntil", _now() + SESSION_LOCK_MS)
    elif which == "new":
        if session.get("newOtpResends", 0) >= MAX_RESENDS:
            locked = session.get("newOtpLockedUntil")
            if not locked or _now() >= locked:
                _set_lock(user_id, "newOtpLockedUntil", _now() + SESSION_LOCK_MS)

    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# STEP 1 — Verify current password
# POST /users/email/verify-password
# ---------------------------------------------------------------------------
@bp.post("/verify-password")
def verify_password():
    user_id  = str(g.user["user_id"])
    body     = request.get_json(silent=True) or {}
    password = (body.get("password") or "").strip()

    if not password:
        return jsonify({"success": False, "message": "Password is required"}), 400

    session = _get_session(user_id)
    db = get_db()

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")
    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("pwLockedUntil") and _now() < session["pwLockedUntil"]:
        mins_left = -((session["pwLockedUntil"] - _now()) // -60_000)
        return jsonify({
            "success": False, "locked": True,
            "message": f"Too many incorrect attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
            "minutesLeft": mins_left,
        }), 429

    user = _get_user_by_id(user_id, db)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if user.get("email_changed_at"):
        since = _now() - int(user["email_changed_at"].timestamp() * 1_000)
        if since < EMAIL_COOLDOWN_MS:
            hours_left = -((EMAIL_COOLDOWN_MS - since) // -3_600_000)
            return jsonify({
                "success": False, "cooldown": True,
                "message": (
                    f"You can only change your email once every 24 hours. "
                    f"Try again in {hours_left} hour{'s' if hours_left != 1 else ''}."
                ),
                "hoursLeft": hours_left,
            }), 429

    # Plain-text comparison (no hashing)
    if password != user["password"]:
        session["pwAttempts"] = session.get("pwAttempts", 0) + 1
        attempts_left = PW_MAX_ATTEMPTS - session["pwAttempts"]
        if attempts_left <= 0:
            lock_until = _now() + PW_LOCKOUT_MS
            session["pwLockedUntil"] = lock_until
            session["pwAttempts"]    = 0
            _set_lock(user_id, "pwLockedUntil", lock_until)
            return jsonify({
                "success": False, "locked": True,
                "message": "Too many incorrect attempts. Try again in 15 minutes.",
                "minutesLeft": 15,
            }), 429
        return jsonify({
            "success": False,
            "message": f"Incorrect password — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
            "attemptsLeft": attempts_left,
        }), 401

    session["pwAttempts"]    = 0
    session["pwLockedUntil"] = None
    _set_lock(user_id, "pwLockedUntil", None)
    _clear_session(user_id)
    _get_session(user_id)["passwordVerified"] = True
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# STEP 2 — Send OTP to current email
# POST /users/email/request-old-otp
# ---------------------------------------------------------------------------
@bp.post("/request-old-otp")
def request_old_otp():
    user_id = str(g.user["user_id"])
    session = _get_session(user_id)
    db = get_db()

    if not session.get("passwordVerified"):
        return jsonify({"success": False, "message": "Please verify your password first"}), 403

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")

    if session.get("oldOtpLockedUntil") and _now() < session["oldOtpLockedUntil"]:
        mins_left = -((session["oldOtpLockedUntil"] - _now()) // -60_000)
        return jsonify({
            "success": False, "sessionLocked": True,
            "message": (
                f"For security reasons, this process has been temporarily locked. "
                f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}."
            ),
            "minutesLeft": mins_left,
        }), 429

    # Resend window
    window_start = session.get("oldResendWindowStart")
    if window_start and _now() - window_start < RESEND_WINDOW_MS:
        if session.get("oldOtpResends", 0) >= MAX_RESENDS:
            lock_until = _now() + SESSION_LOCK_MS
            _set_lock(user_id, "oldOtpLockedUntil", lock_until)
            return jsonify({
                "success": False, "sessionLocked": True,
                "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                "minutesLeft": 15,
            }), 429
    else:
        session["oldResendWindowStart"] = _now()
        session["oldOtpResends"]        = 0

    # 60s cooldown (bypassed when attempts exhausted)
    attempts_exhausted = session.get("oldOtpAttempts", 0) >= OTP_MAX_ATTEMPTS
    if (
        not attempts_exhausted
        and session.get("oldOtpSentAt")
        and _now() - session["oldOtpSentAt"] < RESEND_WAIT_MS
    ):
        wait = -(-(RESEND_WAIT_MS - (_now() - session["oldOtpSentAt"])) // 1_000)
        return jsonify({
            "success": False, "resendLocked": True,
            "message": f"Please wait {wait}s before resending",
            "waitSeconds": wait,
        }), 429

    current_email = _get_email_by_user_id(g.user["user_id"], db)
    if not current_email:
        return jsonify({"success": False, "message": "No email address on file"}), 400

    otp = str(secrets.randbelow(900_000) + 100_000)
    session["oldOtp"]           = otp
    session["oldOtpExpires"]    = _now() + OTP_EXPIRY_MS
    session["oldOtpSentAt"]     = _now()
    session["oldOtpAttempts"]   = 0
    session["oldOtpResends"]    = session.get("oldOtpResends", 0) + 1
    session["oldEmailVerified"] = False

    send_result = send_otp_email(current_email, otp, "current")
    if not send_result.get("success"):
        session["oldOtpResends"] -= 1
        return jsonify({"success": False, "message": "Failed to send code. Please try again."}), 500

    return jsonify({
        "success": True,
        "maskedEmail": _mask_email(current_email),
        "resendsLeft": MAX_RESENDS - session["oldOtpResends"],
        "otpExpiresAt": session["oldOtpExpires"],
    })


# ---------------------------------------------------------------------------
# STEP 3 — Verify OTP from current email
# POST /users/email/verify-old-otp
# ---------------------------------------------------------------------------
@bp.post("/verify-old-otp")
def verify_old_otp():
    user_id   = str(g.user["user_id"])
    session   = _get_session(user_id)
    body      = request.get_json(silent=True) or {}
    submitted = (body.get("otp") or "").strip()

    if not session.get("passwordVerified"):
        return jsonify({"success": False, "message": "Please verify your password first"}), 403

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")

    if session.get("oldOtpLockedUntil") and _now() < session["oldOtpLockedUntil"]:
        mins_left = -((session["oldOtpLockedUntil"] - _now()) // -60_000)
        return jsonify({
            "success": False, "sessionLocked": True,
            "message": (
                f"For security reasons, this process has been temporarily locked. "
                f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}."
            ),
            "minutesLeft": mins_left,
        }), 429

    if not session.get("oldOtp"):
        return jsonify({"success": False, "expired": True, "message": "No code pending — request a new one"}), 400

    if _now() > session["oldOtpExpires"]:
        session["oldOtp"] = None
        return jsonify({"success": False, "expired": True, "message": "Code expired — request a new one"}), 400

    session["oldOtpAttempts"] = session.get("oldOtpAttempts", 0) + 1

    if submitted != session["oldOtp"]:
        attempts_left = OTP_MAX_ATTEMPTS - session["oldOtpAttempts"]
        if attempts_left <= 0:
            if session.get("oldOtpResends", 0) >= MAX_RESENDS:
                lock_until = _now() + SESSION_LOCK_MS
                _set_lock(user_id, "oldOtpLockedUntil", lock_until)
                return jsonify({
                    "success": False, "sessionLocked": True,
                    "message": "For security reasons, this process has been temporarily locked. Please try again after 15 minutes.",
                    "minutesLeft": 15,
                }), 429
            return jsonify({
                "success": False, "attemptLocked": True,
                "message": "Too many incorrect attempts. Please request a new code.",
                "attemptsLeft": 0,
            }), 429
        return jsonify({
            "success": False,
            "message": f"Incorrect code — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
            "attemptsLeft": attempts_left,
        }), 400

    session["oldOtp"]           = None
    session["oldEmailVerified"] = True
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# STEP 4 — Send OTP to new email
# POST /users/email/request-new-otp
# ---------------------------------------------------------------------------
@bp.post("/request-new-otp")
def request_new_otp():
    user_id   = str(g.user["user_id"])
    session   = _get_session(user_id)
    body      = request.get_json(silent=True) or {}
    new_email = (body.get("newEmail") or "").strip().lower()
    db = get_db()

    if not session.get("passwordVerified") or not session.get("oldEmailVerified"):
        return jsonify({"success": False, "message": "Please complete the previous steps first"}), 403

    if not new_email:
        return jsonify({"success": False, "message": "New email is required"}), 400

    import re
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", new_email):
        return jsonify({"success": False, "message": "Invalid email format"}), 400

    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("newOtpLockedUntil") and _now() < session["newOtpLockedUntil"]:
        mins_left = -((session["newOtpLockedUntil"] - _now()) // -60_000)
        return jsonify({
            "success": False, "sessionLocked": True,
            "message": (
                f"For security reasons, this process has been temporarily locked. "
                f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}."
            ),
            "minutesLeft": mins_left,
        }), 429

    # Reset counters when email address changes
    if new_email != session.get("newEmail"):
        session["newOtpResends"]        = 0
        session["newResendWindowStart"] = None
        session["newOtpAttempts"]       = 0
        session["newOtpLockedUntil"]    = None

    # Resend window
    window_start = session.get("newResendWindowStart")
    if window_start and _now() - window_start < RESEND_WINDOW_MS:
        if session.get("newOtpResends", 0) >= MAX_RESENDS:
            lock_until = _now() + SESSION_LOCK_MS
            _set_lock(user_id, "newOtpLockedUntil", lock_until)
            return jsonify({
                "success": False, "sessionLocked": True,
                "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                "minutesLeft": 15,
            }), 429
    else:
        session["newResendWindowStart"] = _now()
        session["newOtpResends"]        = 0

    # Must differ from current
    current_email = _get_email_by_user_id(g.user["user_id"], db)
    if current_email and current_email.lower() == new_email:
        return jsonify({"success": False, "message": "New email must be different from your current email"}), 400

    # Must not be taken
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id FROM users WHERE LOWER(email) = %s AND user_id != %s",
        (new_email, g.user["user_id"]),
    )
    taken = cursor.fetchone()
    cursor.close()
    if taken:
        return jsonify({"success": False, "message": "This email is already registered to another account"}), 409

    # 60s cooldown (bypassed when attempts exhausted)
    attempts_exhausted = session.get("newOtpAttempts", 0) >= OTP_MAX_ATTEMPTS
    if (
        not attempts_exhausted
        and session.get("newOtpSentAt")
        and new_email == session.get("newEmail")
        and _now() - session["newOtpSentAt"] < RESEND_WAIT_MS
    ):
        wait = -(-(RESEND_WAIT_MS - (_now() - session["newOtpSentAt"])) // 1_000)
        return jsonify({
            "success": False, "resendLocked": True,
            "message": f"Please wait {wait}s before resending",
            "waitSeconds": wait,
        }), 429

    otp = str(secrets.randbelow(900_000) + 100_000)
    session["newEmail"]       = new_email
    session["newOtp"]         = otp
    session["newOtpExpires"]  = _now() + OTP_EXPIRY_MS
    session["newOtpSentAt"]   = _now()
    session["newOtpAttempts"] = 0
    session["newOtpResends"]  = session.get("newOtpResends", 0) + 1
    session["verifiedEmail"]  = None

    send_result = send_otp_email(new_email, otp, "new")
    if not send_result.get("success"):
        session["newOtpResends"] -= 1
        return jsonify({"success": False, "message": "Failed to send code. Please try again."}), 500

    return jsonify({
        "success": True,
        "maskedEmail": _mask_email(new_email),
        "resendsLeft": MAX_RESENDS - session["newOtpResends"],
        "otpExpiresAt": session["newOtpExpires"],
    })


# ---------------------------------------------------------------------------
# STEP 5 — Verify OTP from new email
# POST /users/email/verify-new-otp
# ---------------------------------------------------------------------------
@bp.post("/verify-new-otp")
def verify_new_otp():
    user_id   = str(g.user["user_id"])
    session   = _get_session(user_id)
    body      = request.get_json(silent=True) or {}
    submitted = (body.get("otp") or "").strip()

    if not session.get("passwordVerified") or not session.get("oldEmailVerified"):
        return jsonify({"success": False, "message": "Please complete the previous steps first"}), 403

    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("newOtpLockedUntil") and _now() < session["newOtpLockedUntil"]:
        mins_left = -((session["newOtpLockedUntil"] - _now()) // -60_000)
        return jsonify({
            "success": False, "sessionLocked": True,
            "message": (
                f"For security reasons, this process has been temporarily locked. "
                f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}."
            ),
            "minutesLeft": mins_left,
        }), 429

    if not session.get("newOtp"):
        return jsonify({"success": False, "expired": True, "message": "No code pending — request a new one"}), 400

    if _now() > session["newOtpExpires"]:
        session["newOtp"] = None
        return jsonify({"success": False, "expired": True, "message": "Code expired — request a new one"}), 400

    session["newOtpAttempts"] = session.get("newOtpAttempts", 0) + 1

    if submitted != session["newOtp"]:
        attempts_left = OTP_MAX_ATTEMPTS - session["newOtpAttempts"]
        if attempts_left <= 0:
            if session.get("newOtpResends", 0) >= MAX_RESENDS:
                lock_until = _now() + SESSION_LOCK_MS
                _set_lock(user_id, "newOtpLockedUntil", lock_until)
                return jsonify({
                    "success": False, "sessionLocked": True,
                    "message": "For security reasons, this process has been temporarily locked. Please try again after 15 minutes.",
                    "minutesLeft": 15,
                }), 429
            return jsonify({
                "success": False, "attemptLocked": True,
                "message": "Too many incorrect attempts. Please request a new code.",
                "attemptsLeft": 0,
            }), 429
        return jsonify({
            "success": False,
            "message": f"Incorrect code — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
            "attemptsLeft": attempts_left,
        }), 400

    verified_email           = session["newEmail"]
    session["newOtp"]        = None
    session["verifiedEmail"] = verified_email
    return jsonify({"success": True, "verifiedEmail": verified_email})


# ---------------------------------------------------------------------------
# Utility functions called externally (e.g. from a profile controller)
# ---------------------------------------------------------------------------
def consume_session(user_id: str) -> None:
    """
    Call after a successful email save in your profile controller.
    Runs send_email_changed_notification in a background thread so it
    doesn't block the response (replaces asyncio.create_task).
    """
    session   = _sessions.get(str(user_id))
    old_email = session.get("_oldEmailForNotification") if session else None
    new_email = session.get("verifiedEmail")             if session else None

    locks = _get_persistent_locks(str(user_id))
    locks["oldOtpLockedUntil"] = None
    locks["newOtpLockedUntil"] = None
    locks["pwLockedUntil"]     = None

    _clear_session(str(user_id))
    _update_email_changed_at(user_id, get_db())

    if old_email and new_email:
        t = threading.Thread(
            target=send_email_changed_notification,
            args=(old_email, new_email),
            daemon=True,
        )
        t.start()


def get_verified_email(user_id: str) -> Optional[str]:
    return _sessions.get(str(user_id), {}).get("verifiedEmail")


def set_old_email_for_notification(user_id: str, email: str) -> None:
    session = _get_session(str(user_id))
    session["_oldEmailForNotification"] = email