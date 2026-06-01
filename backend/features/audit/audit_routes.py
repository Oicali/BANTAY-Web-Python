# audit_routes.py
from fastapi import APIRouter
from shared.middleware.token_middleware import authenticate
from features.audit.audit_controller import get_audit_logs

router = APIRouter()

router.add_api_route("/", authenticate(get_audit_logs), methods=["GET"])