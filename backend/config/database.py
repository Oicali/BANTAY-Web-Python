# config/database.py
import os
import mysql.connector
from mysql.connector import pooling
from flask import g
from dotenv import load_dotenv

load_dotenv()

# ── 1. Validate required env vars ─────────────────────────────────────────────
REQUIRED_ENV = ["DB_USER", "DB_PASS"]
missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)}")
    exit(1)

# ── 2. Pool instance ──────────────────────────────────────────────────────────
_pool = None

# ── 3. Init pool (called once at startup in main.py) ─────────────────────────
def init_db():
    global _pool
    _pool = pooling.MySQLConnectionPool(
        pool_name="bantay_pool",
        pool_size=10,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME", "bantay"),
        time_zone="+08:00",
    )
    print("🗄️ MySQL pool created")

# ── 4. Get connection per request (stored in Flask's g) ───────────────────────
def get_db():
    if "db" not in g:
        g.db = _pool.get_connection()
    return g.db

# ── 5. Close connection after each request ────────────────────────────────────
def close_db(error=None):
    db = g.pop("db", None)
    if db and db.is_connected():
        db.close()

def get_pool():
    return _pool