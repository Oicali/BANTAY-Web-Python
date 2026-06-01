import asyncpg, ssl, os, signal
from dotenv import load_dotenv

load_dotenv()

# ── 1. Validate required env vars ─────────────────────────────────────────────
REQUIRED_ENV = ["DB_USER", "DB_PASS", "DB_HOST", "DB_PORT", "DB_NAME"]
missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)}")
    exit(1)

# ── 2. SSL configuration ──────────────────────────────────────────────────────
def build_ssl_context():
    ssl_ctx = ssl.create_default_context()

    if os.getenv("DB_SSL_CA_CONTENT"):
        ca = os.getenv("DB_SSL_CA_CONTENT").replace("\\n", "\n")
        ssl_ctx.load_verify_locations(cadata=ca)
        print("🔐 SSL: using cert from DB_SSL_CA_CONTENT")

    elif os.getenv("DB_SSL_CA"):
        ssl_ctx.load_verify_locations(cafile=os.getenv("DB_SSL_CA"))
        print("🔐 SSL: using cert from DB_SSL_CA file")

    else:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        print("🔐 SSL: no cert (Railway mode)")

    return ssl_ctx

# ── 3. Pool instance (set during init_db) ─────────────────────────────────────
pool: asyncpg.Pool = None

# ── 4. Init pool (called in main.py lifespan) ─────────────────────────────────
async def init_db():
    global pool
    ssl_ctx = build_ssl_context()

    pool = await asyncpg.create_pool(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
        ssl=ssl_ctx,
        min_size=0,
        max_size=10,
        command_timeout=30,
        # replaces pool.on("connect") — runs on every new connection
        init=_configure_connection,
    )
    print("🗄️ PostgreSQL pool created")

# ── 5. Per-connection config (replaces pool.on("connect")) ────────────────────
async def _configure_connection(conn):
    await conn.execute("SET TIMEZONE = 'Asia/Manila'")
    await conn.execute("SET statement_timeout = '30s'")

# ── 6. Close pool (called in main.py lifespan on shutdown) ────────────────────
async def close_db():
    global pool
    if pool:
        await pool.close()
        print("🗄️ PostgreSQL pool closed")

# ── 7. Dependency for routes — yields a connection from the pool ───────────────
async def get_db():
    async with pool.acquire() as conn:
        yield conn