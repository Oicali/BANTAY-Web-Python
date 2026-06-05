# backend/shared/utils/token_manager.py

import os, hashlib
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError, ExpiredSignatureError
from config.database import get_db
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
JWT_EXPIRY = os.getenv("JWT_EXPIRY", "24h")

# ── Convert expiry string to seconds ──────────────────────────────────────────
def get_expiry_seconds(expiry: str) -> int:
    unit  = expiry[-1]
    value = int(expiry[:-1])
    if unit == "h": return value * 3600
    if unit == "d": return value * 86400
    if unit == "m": return value * 60
    return 86400

# ── Hash token for DB storage ─────────────────────────────────────────────────
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

# ── Create JWT + store in DB ──────────────────────────────────────────────────
def create_token(user_data: dict, expires_in: str = None) -> str:
    expiry_seconds = get_expiry_seconds(expires_in or JWT_EXPIRY)
    expires_at     = datetime.utcnow() + timedelta(seconds=expiry_seconds)

    payload    = {**user_data, "exp": expires_at}
    token      = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    token_hash = hash_token(token)

    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_data["user_id"], token_hash, expires_at),
    )
    conn.commit()
    cursor.close()

    return token

# ── Verify token (JWT + DB check) ─────────────────────────────────────────────
def verify_token(token: str) -> dict:
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise Exception("Token has expired. Please login again.")
    except JWTError:
        raise Exception("Invalid token format")

    token_hash = hash_token(token)

    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT t.*, u.status
           FROM tokens t
           JOIN users u ON t.user_id = u.user_id
           WHERE t.token_hash = %s
             AND t.is_revoked = false
             AND t.expires_at > NOW()""",
        (token_hash,),
    )
    row = cursor.fetchone()
    cursor.close()

    if not row:
        raise Exception("Token not found or expired")
    if row["status"] == "deactivated":
        raise Exception("Account is deactivated")
    if row["status"] == "locked":
        raise Exception("Account is locked")
    if row["status"] == "unverified":
        raise Exception("Account is not yet verified")

    return decoded

# ── Revoke single token ───────────────────────────────────────────────────────
def revoke_token(token: str) -> bool:
    token_hash = hash_token(token)
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tokens SET is_revoked = true, revoked_at = NOW() WHERE token_hash = %s",
        (token_hash,),
    )
    conn.commit()
    cursor.close()
    return True

# ── Revoke all user tokens ────────────────────────────────────────────────────
def revoke_all_user_tokens(user_id: str) -> bool:
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tokens SET is_revoked = true, revoked_at = NOW() WHERE user_id = %s AND is_revoked = false",
        (user_id,),
    )
    conn.commit()
    cursor.close()
    return True

# ── Cleanup expired tokens ────────────────────────────────────────────────────
def cleanup_expired_tokens() -> int:
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE expires_at < NOW()")
    count = cursor.rowcount
    conn.commit()
    cursor.close()
    print(f"🧹 Cleaned up {count} expired tokens")
    return count

# ── Get active sessions for a user ────────────────────────────────────────────
def get_user_sessions(user_id: str) -> list:
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT token_id, created_at, expires_at
           FROM tokens
           WHERE user_id = %s
             AND is_revoked = false
             AND expires_at > NOW()
           ORDER BY created_at DESC""",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows