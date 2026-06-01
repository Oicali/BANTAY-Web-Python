# backend/features/user/profile_routes.py

from fastapi import APIRouter
from shared.middleware.token_middleware import authenticate
from features.user.profile_controller import (
    get_profile,
    check_phone_availability,
    update_profile,
    change_password,
    upload_profile_picture_for_user,
    upload_profile_picture,
    get_password_status,
    verify_current_password,
    request_password_otp,
    change_password_with_otp,
    force_password_lock,
)
from features.user.email_verification_controller import (
    get_email_status,
    force_lock,
    verify_password,
    request_old_otp,
    verify_old_otp,
    request_new_otp,
    verify_new_otp,
)

router = APIRouter()

# ── Profile ───────────────────────────────────────────────────────────────────
router.add_api_route("/profile",                   authenticate(get_profile),                     methods=["GET"])
router.add_api_route("/check-phone",               authenticate(check_phone_availability),        methods=["POST"])
# ⚠️  Static paths BEFORE parameterized — /profile/picture must come before /profile/{id}
router.add_api_route("/profile/picture",           authenticate(upload_profile_picture),          methods=["POST"])
router.add_api_route("/profile/picture/{user_id}", authenticate(upload_profile_picture_for_user), methods=["POST"])
router.add_api_route("/profile/{id}",              authenticate(update_profile),                  methods=["PUT"])
router.add_api_route("/change-password",           authenticate(change_password),                 methods=["POST"])

# ── Secure Email Change ───────────────────────────────────────────────────────
router.add_api_route("/email/status",              authenticate(get_email_status),   methods=["GET"])
router.add_api_route("/email/force-lock",          authenticate(force_lock),         methods=["POST"])
router.add_api_route("/email/verify-password",     authenticate(verify_password),    methods=["POST"])
router.add_api_route("/email/request-old-otp",     authenticate(request_old_otp),    methods=["POST"])
router.add_api_route("/email/verify-old-otp",      authenticate(verify_old_otp),     methods=["POST"])
router.add_api_route("/email/request-new-otp",     authenticate(request_new_otp),    methods=["POST"])
router.add_api_route("/email/verify-new-otp",      authenticate(verify_new_otp),     methods=["POST"])

# ── Secure Password Change ────────────────────────────────────────────────────
router.add_api_route("/password/status",           authenticate(get_password_status),        methods=["GET"])
router.add_api_route("/password/verify-current",   authenticate(verify_current_password),    methods=["POST"])
router.add_api_route("/password/request-otp",      authenticate(request_password_otp),       methods=["POST"])
router.add_api_route("/password/verify-otp",       authenticate(change_password_with_otp),   methods=["POST"])
router.add_api_route("/password/force-lock",       authenticate(force_password_lock),        methods=["POST"])