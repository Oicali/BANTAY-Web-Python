# backend/features/audit/audit_routes.py

from flask import Blueprint
from shared.middleware.token_middleware import authenticate
from features.audit.audit_controller import get_audit_logs

audit_bp = Blueprint("audit", __name__)

audit_bp.add_url_rule("", view_func=authenticate(get_audit_logs), methods=["GET"])