# backend/shared/middleware/token_middleware.py

from flask import request, g
from shared.utils.token_manager import verify_token
from functools import wraps

def authenticate(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return {"success": False, "message": "No authentication token provided"}, 401

        token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return {"success": False, "message": "No authentication token provided"}, 401

        try:
            decoded = verify_token(token)
            g.user = decoded
        except Exception as e:
            return {"success": False, "message": e.args[0] if e.args else "Authentication failed"}, 401

        return handler(*args, **kwargs)
    return wrapper