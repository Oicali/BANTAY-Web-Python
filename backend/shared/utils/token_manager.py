# backend\shared\utils\token_manager.py
import os, hashlib
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError, ExpiredSignatureError
import config.database as db
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
JWT_EXPIRY = os.getenv("JWT_EXPIRY", "24h")

# ── Convert expiry string to seconds (replaces getExpiryMs) ──────────────────
def get_expiry_seconds(expiry: str) -> int:
    unit = expiry[-1]
    value = int(expiry[:-1])
    if unit == "h": return value * 60 * 60
    if unit == "d": return value * 24 * 60 * 60
    if unit == "m": return value * 60
    return 24 * 60 * 60

# ── Hash token for DB storage (replaces hashToken) ────────────────────────────
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

# ── Create JWT + store in DB (replaces createToken) ───────────────────────────
async def create_token(user_data: dict) -> str:
    expiry_seconds = get_expiry_seconds(JWT_EXPIRY)
    expires_at = datetime.utcnow() + timedelta(seconds=expiry_seconds)

    payload = {**user_data, "exp": expires_at}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    token_hash = hash_token(token)

    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            user_data["user_id"], token_hash, expires_at,
        )

    return token

# ── Verify token (JWT + DB check) (replaces verifyToken) ─────────────────────
async def verify_token(token: str) -> dict:
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise Exception("Token has expired. Please login again.")
    except JWTError:
        raise Exception("Invalid token format")

    token_hash = hash_token(token)

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT t.*, u.status
               FROM tokens t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.token_hash = $1
                 AND t.is_revoked = false
                 AND t.expires_at > NOW()""",
            token_hash,
        )

    if not row:
        raise Exception("Token not found or expired")

    if row["status"] == "deactivated":
        raise Exception("Account is deactivated")
    if row["status"] == "locked":
        raise Exception("Account is locked")
    if row["status"] == "unverified":
        raise Exception("Account is not yet verified")

    return decoded

# ── Revoke single token / logout (replaces revokeToken) ──────────────────────
async def revoke_token(token: str) -> bool:
    token_hash = hash_token(token)
    async with db.pool.acquire() as conn:
        await conn.execute(
            "UPDATE tokens SET is_revoked=true, revoked_at=NOW() WHERE token_hash=$1",
            token_hash,
        )
    return True

# ── Revoke all user tokens / logout all (replaces revokeAllUserTokens) ────────
async def revoke_all_user_tokens(user_id: str) -> bool:
    async with db.pool.acquire() as conn:
        await conn.execute(
            "UPDATE tokens SET is_revoked=true, revoked_at=NOW() WHERE user_id=$1 AND is_revoked=false",
            user_id,
        )
    return True

# ── Cleanup expired tokens (called hourly from main.py) ──────────────────────
async def cleanup_expired_tokens() -> int:
    async with db.pool.acquire() as conn:
        result = await conn.execute("DELETE FROM tokens WHERE expires_at < NOW()")
        count = int(result.split()[-1])
        print(f"🧹 Cleaned up {count} expired tokens")
        return count

# ── Get active sessions for a user (replaces getUserSessions) ─────────────────
async def get_user_sessions(user_id: str) -> list:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT token_id, created_at, expires_at
               FROM tokens
               WHERE user_id=$1
                 AND is_revoked=false
                 AND expires_at > NOW()
               ORDER BY created_at DESC""",
            user_id,
        )
    return [dict(r) for r in rows]