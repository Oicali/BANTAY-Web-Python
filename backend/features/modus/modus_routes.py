# ================================================================================
# FILE: backend/features/modus/modus_routes.py
# ================================================================================

from fastapi import APIRouter
from shared.middleware.token_middleware import authenticate
from features.modus.modus_controller import (
    get_all_modus,
    get_modus_by_id,
    create_modus,
    update_modus,
)

router = APIRouter()

router.add_api_route("/",    authenticate(get_all_modus),  methods=["GET"])
router.add_api_route("/{id}", authenticate(get_modus_by_id), methods=["GET"])
router.add_api_route("/",    authenticate(create_modus),   methods=["POST"])
router.add_api_route("/{id}", authenticate(update_modus),  methods=["PATCH"])