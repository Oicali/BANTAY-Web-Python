# backend\main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio, os, time

from config.database import init_db, close_db
from shared.utils.token_manager import cleanup_expired_tokens
from features.auth.auth_routes import router as auth_router
from features.user.profile_routes import router as profile_router
# from features.user.user_routes import router as user_router
from features.dashboard.crime_dashboard_router import router as dashboard_router
from features.audit.audit_routes import router as audit_router
from features.modus.modus_routes import router as modus_router
from features.residents.resident_routes import router as resident_router

load_dotenv()

# ── 1. Lifespan (replaces app.listen + setInterval) ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(token_cleanup_task())
    print("🧹 Token cleanup scheduled (runs every hour)")
    yield
    await close_db()

async def token_cleanup_task():
    while True:
        await asyncio.sleep(60 * 60)  # 1 hour
        try:
            await cleanup_expired_tokens()
        except Exception as e:
            print(f"🧹 Token cleanup error: {e}")

# ── 2. App instance ───────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ── 3. CORS (replaces app.use(cors(...))) ─────────────────────────────────────
allowed_origins = list(filter(None, [
    os.getenv("FRONTEND_URL"),
    "http://localhost:5173",
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── 4. Routes (replaces app.use("/auth", require(...))) ───────────────────────
app.include_router(auth_router, prefix="/auth")
app.include_router(audit_router, prefix="/audit-log")
app.include_router(dashboard_router, prefix="/crime-dashboard")
app.include_router(profile_router, prefix="/users")
# app.include_router(user_router, prefix="/user-management")
app.include_router(modus_router, prefix="/modus-management") 
app.include_router(resident_router, prefix="/residents")

# ── 5. Static uploads (replaces express.static) ──────────────────────────────
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── 6. Health check ───────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "🗄️ BANTAY Backend is running!"}

@app.get("/health")
def health():
    return {
        "status": "✅ ok",
        "uptime": f"⏱️ {int(time.process_time())}s",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }