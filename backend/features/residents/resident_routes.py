# ================================================================================
# FILE: backend/features/residents/resident_routes.py
# ================================================================================

from fastapi import APIRouter
from shared.middleware.token_middleware import authenticate
from features.residents.resident_controller import (
    get_residents,
    import_residents,
    get_removed_residents,
    get_resident_by_id,
    update_resident,
    delete_resident,
    restore_resident,
)

router = APIRouter()

# ⚠️ Static paths BEFORE parameterised — same rule as profile_routes.py
router.add_api_route("/",              authenticate(get_residents),         methods=["GET"])
router.add_api_route("/import",        authenticate(import_residents),      methods=["POST"])
router.add_api_route("/removed",       authenticate(get_removed_residents), methods=["GET"])
router.add_api_route("/{id}/restore",  authenticate(restore_resident),      methods=["PUT"])
router.add_api_route("/{id}",          authenticate(delete_resident),       methods=["DELETE"])
router.add_api_route("/{id}",          authenticate(get_resident_by_id),    methods=["GET"])
router.add_api_route("/{id}",          authenticate(update_resident),       methods=["PUT"])