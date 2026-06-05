# ================================================================================
# FILE: backend/features/user/user_routes.py
# ================================================================================

from flask import Blueprint
from shared.middleware.token_middleware import authenticate

from features.user.user_controller import (
    get_all_users,
    get_filter_options,
    get_user_by_id,
    register_user,
    verify_account,
    resend_verification_email,
    update_user,
    deactivate_user,
    lock_user,
    unlock_user,
    restore_user,
    get_all_roles,
    get_ranks,
)

user_bp = Blueprint("user_management", __name__)


# GET /verify-account?token=<raw_token>
user_bp.route("/verify-account", methods=["GET"])(verify_account)

# GET  /users?userType=police&status=active&search=...&role=...&page=1&limit=20
user_bp.route("/users", methods=["GET"])(authenticate(get_all_users))

# GET  /filter-options
user_bp.route("/filter-options", methods=["GET"])(authenticate(get_filter_options))

# GET  /roles
user_bp.route("/roles", methods=["GET"])(authenticate(get_all_roles))

# GET  /ranks
user_bp.route("/ranks", methods=["GET"])(authenticate(get_ranks))

# GET  /users/:id
user_bp.route("/users/<id>", methods=["GET"])(authenticate(get_user_by_id))

# POST /register
user_bp.route("/register", methods=["POST"])(authenticate(register_user))

# PUT  /users/:id
user_bp.route("/users/<id>", methods=["PUT"])(authenticate(update_user))

# PUT  /users/:id/lock
user_bp.route("/users/<id>/lock", methods=["PUT"])(authenticate(lock_user))

# PUT  /users/:id/unlock
user_bp.route("/users/<id>/unlock", methods=["PUT"])(authenticate(unlock_user))

# PUT  /users/:id/restore
user_bp.route("/users/<id>/restore", methods=["PUT"])(authenticate(restore_user))

# DELETE /users/:id  (deactivate)
user_bp.route("/users/<id>", methods=["DELETE"])(authenticate(deactivate_user))

# POST /users/:id/resend-verification
user_bp.route("/users/<id>/resend-verification", methods=["POST"])(authenticate(resend_verification_email))