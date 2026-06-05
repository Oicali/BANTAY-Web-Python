# ================================================================================
# FILE: backend/features/modus/modus_routes.py
# ================================================================================

from flask import Blueprint
from shared.middleware.token_middleware import authenticate
from features.modus.modus_controller import (
    get_all_modus,
    get_modus_by_id,
    create_modus,
    update_modus,
)

modus_bp = Blueprint("modus", __name__)

modus_bp.add_url_rule("",      view_func=authenticate(get_all_modus), methods=["GET"])
modus_bp.add_url_rule("/<id>", view_func=authenticate(get_modus_by_id), methods=["GET"])
modus_bp.add_url_rule("",      view_func=authenticate(create_modus),  methods=["POST"])
modus_bp.add_url_rule("/<id>", view_func=authenticate(update_modus),  methods=["PATCH"])