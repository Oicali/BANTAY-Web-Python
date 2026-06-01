"""
email_verification_controller.py
Converted from: backend/features/user/controllers/emailVerificationController.js

In-memory session store + persistent lock store that survive logout/re-login.
All rate-limiting, OTP generation, and lock logic ported 1-to-1 from the JS version.
"""

import secrets
import time
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
import bcrypt

from email_service import send_otp_email, send_email_changed_notification

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/users/email", tags=["email-verification"])

# ---------------------------------------------------------------------------
# Constants  (mirror JS values exactly)
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
    """Current time in milliseconds (mirrors JS Date.now())."""
    return int(time.time() * 1_000)


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_sessions: dict[str, dict] = {}

# Persistent locks — never deleted; survive clearSession()/logout/re-login.
# Cleared only on successful email change or when resetExpiredLock fires.
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
    """Write a lock to both the active session AND the persistent store atomically."""
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
    """Reset resend counters when a lock has expired so the user gets a clean window."""
    if session.get(lock_key) and _now() >= session[lock_key]:
        session[lock_key]        = None
        session[resends_key]     = 0
        session[window_start_key] = None
        if window_count_key:
            session[window_count_key] = 0
        if attempts_key:
            session[attempts_key]     = 0
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
# Dependency stubs — replace with your actual auth + DB dependencies
# ---------------------------------------------------------------------------
# from your_app.deps import get_current_user, get_db
# async def get_current_user(request: Request): ...
# async def get_db(): ...
#
# For clarity, the endpoints below show the dependency parameters with type hints
# matching what you'd inject.  Swap the stubs for real ones.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class VerifyPasswordBody(BaseModel):
    password: str

class OldOtpBody(BaseModel):
    otp: str

class NewEmailBody(BaseModel):
    newEmail: str

class NewOtpBody(BaseModel):
    otp: str

class ForceLockBody(BaseModel):
    which: str  # "old" | "new"


# ---------------------------------------------------------------------------
# Helper: get user record from DB
# (Replace the body with your actual DB query)
# ---------------------------------------------------------------------------
async def _get_user_by_id(user_id: str, db) -> Optional[dict]:
    """Return a dict with at least: user_id, email, password, email_changed_at."""
    result = await db.execute(
        "SELECT user_id, email, password, email_changed_at FROM users WHERE user_id = $1",
        (user_id,),
    )
    row = result.fetchone()
    return dict(row) if row else None


async def _update_email_changed_at(user_id: str, db) -> None:
    await db.execute(
        "UPDATE users SET email_changed_at = NOW() WHERE user_id = $1",
        (user_id,),
    )
    await db.commit()


async def _update_user_email(user_id: str, new_email: str, db) -> None:
    await db.execute(
        "UPDATE users SET email = $1 WHERE user_id = $2",
        (new_email, user_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# STATUS CHECK
# GET /users/email/status
# ---------------------------------------------------------------------------
@router.get("/status")
async def get_email_status(
    request: Request,
    # current_user = Depends(get_current_user),
    # db = Depends(get_db),
):
    """Called when the email-change modal opens."""
    # Replace with: user_id = str(current_user.user_id)
    user_id = str(request.state.user.user_id)
    db = request.state.db

    user = await _get_user_by_id(user_id, db)
    if user and user.get("email_changed_at"):
        since   = _now() - int(user["email_changed_at"].timestamp() * 1_000)
        if since < EMAIL_COOLDOWN_MS:
            ms_left    = EMAIL_COOLDOWN_MS - since
            hours_left = -(-ms_left // 3_600_000)       # ceiling division
            return {"blocked": True, "hoursLeft": hours_left, "msLeft": ms_left}

    session = _get_session(user_id)

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")
    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("pwLockedUntil") and _now() < session["pwLockedUntil"]:
        mins_left = -((session["pwLockedUntil"] - _now()) // -60_000)
        return {"pwLocked": True, "minsLeft": mins_left}

    old_lock = session.get("oldOtpLockedUntil")
    new_lock = session.get("newOtpLockedUntil")
    active_lock = (
        old_lock if (old_lock and _now() < old_lock) else
        new_lock if (new_lock and _now() < new_lock) else None
    )
    if active_lock:
        mins_left = -((active_lock - _now()) // -60_000)
        return {"sessionLocked": True, "minsLeft": mins_left}

    return {"blocked": False}


# ---------------------------------------------------------------------------
# FORCE LOCK
# POST /users/email/force-lock
# ---------------------------------------------------------------------------
@router.post("/force-lock")
async def force_lock(
    body: ForceLockBody,
    request: Request,
):
    user_id = str(request.state.user.user_id)
    session = _get_session(user_id)

    if body.which == "old":
        if session.get("oldOtpResends", 0) >= MAX_RESENDS:
            locked = session.get("oldOtpLockedUntil")
            if not locked or _now() >= locked:
                _set_lock(user_id, "oldOtpLockedUntil", _now() + SESSION_LOCK_MS)
    elif body.which == "new":
        if session.get("newOtpResends", 0) >= MAX_RESENDS:
            locked = session.get("newOtpLockedUntil")
            if not locked or _now() >= locked:
                _set_lock(user_id, "newOtpLockedUntil", _now() + SESSION_LOCK_MS)

    return {"success": True}


# ---------------------------------------------------------------------------
# STEP 1 — Verify current password
# POST /users/email/verify-password
# ---------------------------------------------------------------------------
@router.post("/verify-password")
async def verify_password(
    body: VerifyPasswordBody,
    request: Request,
):
    user_id  = str(request.state.user.user_id)
    password = (body.password or "").strip()
    if not password:
        raise HTTPException(400, detail={"success": False, "message": "Password is required"})

    session = _get_session(user_id)
    db = request.state.db

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")
    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("pwLockedUntil") and _now() < session["pwLockedUntil"]:
        mins_left = -((session["pwLockedUntil"] - _now()) // -60_000)
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "locked": True,
                "message": f"Too many incorrect attempts. Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                "minutesLeft": mins_left,
            },
        )

    user = await _get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(404, detail={"success": False, "message": "User not found"})

    if user.get("email_changed_at"):
        since = _now() - int(user["email_changed_at"].timestamp() * 1_000)
        if since < EMAIL_COOLDOWN_MS:
            hours_left = -((EMAIL_COOLDOWN_MS - since) // -3_600_000)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False, "cooldown": True,
                    "message": f"You can only change your email once every 24 hours. "
                               f"Try again in {hours_left} hour{'s' if hours_left != 1 else ''}.",
                    "hoursLeft": hours_left,
                },
            )

    match = bcrypt.checkpw(password.encode(), user["password"].encode()
                           if isinstance(user["password"], str) else user["password"])
    if not match:
        session["pwAttempts"] = session.get("pwAttempts", 0) + 1
        attempts_left = PW_MAX_ATTEMPTS - session["pwAttempts"]
        if attempts_left <= 0:
            lock_until = _now() + PW_LOCKOUT_MS
            session["pwLockedUntil"] = lock_until
            session["pwAttempts"]    = 0
            _set_lock(user_id, "pwLockedUntil", lock_until)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False, "locked": True,
                    "message": "Too many incorrect attempts. Try again in 15 minutes.",
                    "minutesLeft": 15,
                },
            )
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": f"Incorrect password — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
                "attemptsLeft": attempts_left,
            },
        )

    session["pwAttempts"]    = 0
    session["pwLockedUntil"] = None
    _set_lock(user_id, "pwLockedUntil", None)
    _clear_session(user_id)
    _get_session(user_id)["passwordVerified"] = True
    return {"success": True}


# ---------------------------------------------------------------------------
# STEP 2 — Send OTP to current email
# POST /users/email/request-old-otp
# ---------------------------------------------------------------------------
@router.post("/request-old-otp")
async def request_old_otp(request: Request):
    user_id = str(request.state.user.user_id)
    session = _get_session(user_id)
    db = request.state.db

    if not session.get("passwordVerified"):
        raise HTTPException(403, detail={"success": False, "message": "Please verify your password first"})

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")

    if session.get("oldOtpLockedUntil") and _now() < session["oldOtpLockedUntil"]:
        mins_left = -((session["oldOtpLockedUntil"] - _now()) // -60_000)
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "sessionLocked": True,
                "message": f"For security reasons, this process has been temporarily locked. "
                           f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                "minutesLeft": mins_left,
            },
        )

    # Resend window
    window_start = session.get("oldResendWindowStart")
    if window_start and _now() - window_start < RESEND_WINDOW_MS:
        if session.get("oldOtpResends", 0) >= MAX_RESENDS:
            lock_until = _now() + SESSION_LOCK_MS
            _set_lock(user_id, "oldOtpLockedUntil", lock_until)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False, "sessionLocked": True,
                    "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                    "minutesLeft": 15,
                },
            )
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
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "resendLocked": True,
                "message": f"Please wait {wait}s before resending",
                "waitSeconds": wait,
            },
        )

    result = await db.execute(
        "SELECT email FROM users WHERE user_id = $1", (request.state.user.user_id,)
    )
    row = result.fetchone()
    current_email = row["email"] if row else None
    if not current_email:
        raise HTTPException(400, detail={"success": False, "message": "No email address on file"})

    otp = str(secrets.randbelow(900_000) + 100_000)
    session["oldOtp"]           = otp
    session["oldOtpExpires"]    = _now() + OTP_EXPIRY_MS
    session["oldOtpSentAt"]     = _now()
    session["oldOtpAttempts"]   = 0
    session["oldOtpResends"]    = session.get("oldOtpResends", 0) + 1
    session["oldEmailVerified"] = False

    send_result = await send_otp_email(current_email, otp, "current")
    if not send_result.get("success"):
        session["oldOtpResends"] -= 1
        return JSONResponse(status_code=500, content={"success": False, "message": "Failed to send code. Please try again."})

    return {
        "success": True,
        "maskedEmail": _mask_email(current_email),
        "resendsLeft": MAX_RESENDS - session["oldOtpResends"],
        "otpExpiresAt": session["oldOtpExpires"],
    }


# ---------------------------------------------------------------------------
# STEP 3 — Verify OTP from current email
# POST /users/email/verify-old-otp
# ---------------------------------------------------------------------------
@router.post("/verify-old-otp")
async def verify_old_otp(body: OldOtpBody, request: Request):
    user_id   = str(request.state.user.user_id)
    session   = _get_session(user_id)
    submitted = (body.otp or "").strip()

    if not session.get("passwordVerified"):
        raise HTTPException(403, detail={"success": False, "message": "Please verify your password first"})

    _reset_expired_lock(user_id, session, "oldOtpLockedUntil", "oldOtpResends", "oldResendWindowStart", None, "oldOtpAttempts")

    if session.get("oldOtpLockedUntil") and _now() < session["oldOtpLockedUntil"]:
        mins_left = -((session["oldOtpLockedUntil"] - _now()) // -60_000)
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "sessionLocked": True,
                "message": f"For security reasons, this process has been temporarily locked. "
                           f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                "minutesLeft": mins_left,
            },
        )

    if not session.get("oldOtp"):
        raise HTTPException(400, detail={"success": False, "expired": True, "message": "No code pending — request a new one"})

    if _now() > session["oldOtpExpires"]:
        session["oldOtp"] = None
        raise HTTPException(400, detail={"success": False, "expired": True, "message": "Code expired — request a new one"})

    session["oldOtpAttempts"] = session.get("oldOtpAttempts", 0) + 1

    if submitted != session["oldOtp"]:
        attempts_left = OTP_MAX_ATTEMPTS - session["oldOtpAttempts"]
        if attempts_left <= 0:
            if session.get("oldOtpResends", 0) >= MAX_RESENDS:
                lock_until = _now() + SESSION_LOCK_MS
                _set_lock(user_id, "oldOtpLockedUntil", lock_until)
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False, "sessionLocked": True,
                        "message": "For security reasons, this process has been temporarily locked. Please try again after 15 minutes.",
                        "minutesLeft": 15,
                    },
                )
            return JSONResponse(
                status_code=429,
                content={"success": False, "attemptLocked": True, "message": "Too many incorrect attempts. Please request a new code.", "attemptsLeft": 0},
            )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Incorrect code — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
                "attemptsLeft": attempts_left,
            },
        )

    session["oldOtp"]           = None
    session["oldEmailVerified"] = True
    return {"success": True}


# ---------------------------------------------------------------------------
# STEP 4 — Send OTP to new email
# POST /users/email/request-new-otp
# ---------------------------------------------------------------------------
@router.post("/request-new-otp")
async def request_new_otp(body: NewEmailBody, request: Request):
    user_id   = str(request.state.user.user_id)
    session   = _get_session(user_id)
    new_email = (body.newEmail or "").strip().lower()
    db = request.state.db

    if not session.get("passwordVerified") or not session.get("oldEmailVerified"):
        raise HTTPException(403, detail={"success": False, "message": "Please complete the previous steps first"})

    if not new_email:
        raise HTTPException(400, detail={"success": False, "message": "New email is required"})

    import re
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", new_email):
        raise HTTPException(400, detail={"success": False, "message": "Invalid email format"})

    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("newOtpLockedUntil") and _now() < session["newOtpLockedUntil"]:
        mins_left = -((session["newOtpLockedUntil"] - _now()) // -60_000)
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "sessionLocked": True,
                "message": f"For security reasons, this process has been temporarily locked. "
                           f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                "minutesLeft": mins_left,
            },
        )

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
            return JSONResponse(
                status_code=429,
                content={
                    "success": False, "sessionLocked": True,
                    "message": "Maximum codes sent. For security, this process is locked for 15 minutes.",
                    "minutesLeft": 15,
                },
            )
    else:
        session["newResendWindowStart"] = _now()
        session["newOtpResends"]        = 0

    # Must differ from current
    row = await db.execute("SELECT email FROM users WHERE user_id = $1", (request.state.user.user_id,))
    row = row.fetchone()
    if row and row["email"] and row["email"].lower() == new_email:
        raise HTTPException(400, detail={"success": False, "message": "New email must be different from your current email"})

    # Must not be taken
    taken = await db.execute(
        "SELECT user_id FROM users WHERE LOWER(email) = $1 AND user_id != $2",
        (new_email, request.state.user.user_id),
    )
    if taken.fetchone():
        return JSONResponse(status_code=409, content={"success": False, "message": "This email is already registered to another account"})

    # 60s cooldown (bypassed when attempts exhausted)
    attempts_exhausted = session.get("newOtpAttempts", 0) >= OTP_MAX_ATTEMPTS
    if (
        not attempts_exhausted
        and session.get("newOtpSentAt")
        and new_email == session.get("newEmail")
        and _now() - session["newOtpSentAt"] < RESEND_WAIT_MS
    ):
        wait = -(-(RESEND_WAIT_MS - (_now() - session["newOtpSentAt"])) // 1_000)
        return JSONResponse(
            status_code=429,
            content={"success": False, "resendLocked": True, "message": f"Please wait {wait}s before resending", "waitSeconds": wait},
        )

    otp = str(secrets.randbelow(900_000) + 100_000)
    session["newEmail"]       = new_email
    session["newOtp"]         = otp
    session["newOtpExpires"]  = _now() + OTP_EXPIRY_MS
    session["newOtpSentAt"]   = _now()
    session["newOtpAttempts"] = 0
    session["newOtpResends"]  = session.get("newOtpResends", 0) + 1
    session["verifiedEmail"]  = None

    send_result = await send_otp_email(new_email, otp, "new")
    if not send_result.get("success"):
        session["newOtpResends"] -= 1
        return JSONResponse(status_code=500, content={"success": False, "message": "Failed to send code. Please try again."})

    return {
        "success": True,
        "maskedEmail": _mask_email(new_email),
        "resendsLeft": MAX_RESENDS - session["newOtpResends"],
        "otpExpiresAt": session["newOtpExpires"],
    }


# ---------------------------------------------------------------------------
# STEP 5 — Verify OTP from new email
# POST /users/email/verify-new-otp
# ---------------------------------------------------------------------------
@router.post("/verify-new-otp")
async def verify_new_otp(body: NewOtpBody, request: Request):
    user_id   = str(request.state.user.user_id)
    session   = _get_session(user_id)
    submitted = (body.otp or "").strip()

    if not session.get("passwordVerified") or not session.get("oldEmailVerified"):
        raise HTTPException(403, detail={"success": False, "message": "Please complete the previous steps first"})

    _reset_expired_lock(user_id, session, "newOtpLockedUntil", "newOtpResends", "newResendWindowStart", None, "newOtpAttempts")

    if session.get("newOtpLockedUntil") and _now() < session["newOtpLockedUntil"]:
        mins_left = -((session["newOtpLockedUntil"] - _now()) // -60_000)
        return JSONResponse(
            status_code=429,
            content={
                "success": False, "sessionLocked": True,
                "message": f"For security reasons, this process has been temporarily locked. "
                           f"Try again in {mins_left} minute{'s' if mins_left != 1 else ''}.",
                "minutesLeft": mins_left,
            },
        )

    if not session.get("newOtp"):
        raise HTTPException(400, detail={"success": False, "expired": True, "message": "No code pending — request a new one"})

    if _now() > session["newOtpExpires"]:
        session["newOtp"] = None
        raise HTTPException(400, detail={"success": False, "expired": True, "message": "Code expired — request a new one"})

    session["newOtpAttempts"] = session.get("newOtpAttempts", 0) + 1

    if submitted != session["newOtp"]:
        attempts_left = OTP_MAX_ATTEMPTS - session["newOtpAttempts"]
        if attempts_left <= 0:
            if session.get("newOtpResends", 0) >= MAX_RESENDS:
                lock_until = _now() + SESSION_LOCK_MS
                _set_lock(user_id, "newOtpLockedUntil", lock_until)
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False, "sessionLocked": True,
                        "message": "For security reasons, this process has been temporarily locked. Please try again after 15 minutes.",
                        "minutesLeft": 15,
                    },
                )
            return JSONResponse(
                status_code=429,
                content={"success": False, "attemptLocked": True, "message": "Too many incorrect attempts. Please request a new code.", "attemptsLeft": 0},
            )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Incorrect code — {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining",
                "attemptsLeft": attempts_left,
            },
        )

    verified_email     = session["newEmail"]
    session["newOtp"]        = None
    session["verifiedEmail"] = verified_email
    return {"success": True, "verifiedEmail": verified_email}


# ---------------------------------------------------------------------------
# Utility functions called externally (e.g. from a profile controller)
# ---------------------------------------------------------------------------
async def consume_session(user_id: str, db) -> None:
    """Call after a successful email save in your profile controller."""
    session   = _sessions.get(str(user_id))
    old_email = session.get("_oldEmailForNotification") if session else None
    new_email = session.get("verifiedEmail")             if session else None

    locks = _get_persistent_locks(str(user_id))
    locks["oldOtpLockedUntil"] = None
    locks["newOtpLockedUntil"] = None
    locks["pwLockedUntil"]     = None

    _clear_session(str(user_id))
    await _update_email_changed_at(user_id, db)

    if old_email and new_email:
        asyncio.create_task(send_email_changed_notification(old_email, new_email))


def get_verified_email(user_id: str) -> Optional[str]:
    return _sessions.get(str(user_id), {}).get("verifiedEmail")


def set_old_email_for_notification(user_id: str, email: str) -> None:
    session = _get_session(str(user_id))
    session["_oldEmailForNotification"] = email