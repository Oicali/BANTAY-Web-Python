# ================================================================================
# FILE: backend/features/user/profile_routes.py
# ================================================================================

from flask import Blueprint
from shared.middleware.token_middleware import authenticate
from features.user.profile_controller import (
    get_profile,
    check_phone_availability,
    update_profile,
    upload_profile_picture_for_user,
    upload_profile_picture,
    get_password_status,
    verify_current_password,
    request_password_otp,
    change_password_with_otp,
    force_password_lock,
)

from features.user.email_verification_controller import (
    bp as email_bp,  # noqa: F401  — register in main.py under /users
    get_email_status,
    force_lock,
    verify_password,
    request_old_otp,
    verify_old_otp,
    request_new_otp,
    verify_new_otp,
)

profile_bp = Blueprint("profile", __name__)

# ── Profile ───────────────────────────────────────────────────────────────────
profile_bp.add_url_rule("/profile",                   view_func=authenticate(get_profile),                     methods=["GET"])
profile_bp.add_url_rule("/check-phone",               view_func=authenticate(check_phone_availability),        methods=["POST"])
# ⚠️  Static paths BEFORE parameterised — /profile/picture must come before /profile/<id>
profile_bp.add_url_rule("/profile/picture",           view_func=authenticate(upload_profile_picture),          methods=["POST"])
profile_bp.add_url_rule("/profile/picture/<user_id>", view_func=authenticate(upload_profile_picture_for_user), methods=["POST"])
profile_bp.add_url_rule("/profile/<id>",              view_func=authenticate(update_profile),                  methods=["PUT"])

# ── Secure Password Change ────────────────────────────────────────────────────
profile_bp.add_url_rule("/password/status",         view_func=authenticate(get_password_status),      methods=["GET"])
profile_bp.add_url_rule("/password/verify-current", view_func=authenticate(verify_current_password),  methods=["POST"])
profile_bp.add_url_rule("/password/request-otp",    view_func=authenticate(request_password_otp),     methods=["POST"])
profile_bp.add_url_rule("/password/verify-otp",     view_func=authenticate(change_password_with_otp), methods=["POST"])
profile_bp.add_url_rule("/password/force-lock",     view_func=authenticate(force_password_lock),      methods=["POST"])

# ── Secure Email Change (4-step flow) ─────────────────────────────────────────
profile_bp.add_url_rule("/email/status",           view_func=authenticate(get_email_status), methods=["GET"])
profile_bp.add_url_rule("/email/force-lock",       view_func=authenticate(force_lock),       methods=["POST"])
profile_bp.add_url_rule("/email/verify-password",  view_func=authenticate(verify_password),  methods=["POST"])
profile_bp.add_url_rule("/email/request-old-otp",  view_func=authenticate(request_old_otp),  methods=["POST"])
profile_bp.add_url_rule("/email/verify-old-otp",   view_func=authenticate(verify_old_otp),   methods=["POST"])
profile_bp.add_url_rule("/email/request-new-otp",  view_func=authenticate(request_new_otp),  methods=["POST"])
profile_bp.add_url_rule("/email/verify-new-otp",   view_func=authenticate(verify_new_otp),   methods=["POST"])