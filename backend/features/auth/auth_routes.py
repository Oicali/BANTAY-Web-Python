from fastapi import APIRouter, Request, Depends
from shared.middleware.token_middleware import authenticate
from features.auth.auth_controller import (
    login, logout, logout_all,
    send_otp_handler, verify_otp_handler, resend_otp_handler,
    reset_password, change_password,
)

router = APIRouter()

# ── Public routes ─────────────────────────────────────────────────────────────
router.post("/login")(login)
router.post("/otp/send")(send_otp_handler)
router.post("/otp/verify")(verify_otp_handler)
router.post("/otp/resend")(resend_otp_handler)
router.post("/password/reset")(reset_password)

# ── Protected routes ──────────────────────────────────────────────────────────
router.post("/logout")(authenticate(logout))
router.post("/logout-all")(authenticate(logout_all))
router.post("/password/change")(authenticate(change_password))