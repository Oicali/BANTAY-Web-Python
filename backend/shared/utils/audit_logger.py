# ================================================================================
# FILE: backend/shared/utils/audit_logger.py
# ================================================================================

from __future__ import annotations

from typing import Optional

from fastapi import Request

import config.database as db


async def log_audit(
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
    """
    Insert one audit log row.  Fire-and-forget — never raises.

    Args:
        user_id:     UUID of the acting user (None if unknown).
        username:    Username string (None if unknown).
        event_name:  Short label, e.g. "User Login", "OTP Requested".
        description: Human-readable sentence describing the event.
        action:      One of LOGIN | LOGOUT | UPDATE | OTP.
        status:      "success" or "failed".
        source:      "Web Portal" | "Mobile App" | None.
        ip_address:  Client IP string.
    """
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO audit_logs
                     (user_id, username, event_name, description,
                      action, status, source, ip_address)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                user_id, username, event_name, description,
                action, status, source, ip_address,
            )
    except Exception as err:
        # Never crash the main request because of a logging failure
        print(f"⚠️  Audit log failed: {err}")


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract the real client IP from a FastAPI Request.
    Respects the X-Forwarded-For header set by Railway / reverse proxies.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # FastAPI exposes the raw client address via request.client
    if request.client:
        return request.client.host
    return None