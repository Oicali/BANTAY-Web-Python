# backend/features/auth/auth_routes.py

from flask import Blueprint
from shared.middleware.token_middleware import authenticate
from features.auth.auth_controller import (
    login, logout, logout_all,
    send_otp_handler, verify_otp_handler, resend_otp_handler,
    reset_password, change_password,
)

auth_bp = Blueprint("auth", __name__)

auth_bp.post("/login")(login)
auth_bp.post("/otp/send")(send_otp_handler)
auth_bp.post("/otp/verify")(verify_otp_handler)
auth_bp.post("/otp/resend")(resend_otp_handler)
auth_bp.post("/password/reset")(reset_password)

auth_bp.post("/logout")(authenticate(logout))
auth_bp.post("/logout-all")(authenticate(logout_all))
auth_bp.post("/password/change")(authenticate(change_password))