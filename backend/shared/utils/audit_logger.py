# backend/shared/utils/audit_logger.py

from __future__ import annotations
from typing import Optional
from flask import request as flask_request
from config.database import get_db


def log_audit(
    *,
    user_id:     Optional[str] = None,
    username:    Optional[str] = None,
    event_name:  str,
    description: str,
    action:      str,
    status:      str = "success",
    source:      Optional[str] = None,
    ip_address:  Optional[str] = None,
) -> None:
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO audit_logs
                 (user_id, username, event_name, description,
                  action, status, source, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, username, event_name, description,
             action, status, source, ip_address),
        )
        conn.commit()
        cursor.close()
    except Exception as err:
        print(f"⚠️  Audit log failed: {err}")


def get_client_ip(req=None) -> Optional[str]:
    forwarded = flask_request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return flask_request.remote_addr