# backend/main.py
import os
import time
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from config.database import init_db, close_db, get_db

load_dotenv()

# ── 1. App instance ───────────────────────────────────────────────────────────
app = Flask(__name__)

# ── 2. CORS ───────────────────────────────────────────────────────────────────
allowed_origins = list(filter(None, [
    os.getenv("FRONTEND_URL"),
    "http://localhost:5173",
    "http://localhost:8081",
]))

CORS(app,
    origins=allowed_origins,
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── 3. DB init ────────────────────────────────────────────────────────────────
init_db()
app.teardown_appcontext(close_db) 

# ── 4. Routes ─────────────────────────────────────────────────────────────────
from features.auth.auth_routes import auth_bp
from features.user.profile_routes import profile_bp
from features.user.user_routes import user_bp
from features.modus.modus_routes import modus_bp
# from features.crime_map.crime_map_routes import crime_map_bp
# from features.dashboard.crime_dashboard_router import dashboard_bp
# from features.residents.resident_routes import resident_bp
from features.audit.audit_routes import audit_bp
from features.patrols.patrol_routes import patrol_bp
# from features.notifications.notification_routes import notification_bp

app.register_blueprint(auth_bp,         url_prefix="/auth")
app.register_blueprint(profile_bp,      url_prefix="/users")
app.register_blueprint(user_bp,         url_prefix="/user-management")
app.register_blueprint(modus_bp,        url_prefix="/modus-management")
app.register_blueprint(patrol_bp,        url_prefix="/patrol")
# app.register_blueprint(crime_map_bp,    url_prefix="/crime-map")
# app.register_blueprint(dashboard_bp,    url_prefix="/crime-dashboard")
# app.register_blueprint(resident_bp,     url_prefix="/residents")
app.register_blueprint(audit_bp,        url_prefix="/audit-log")
# app.register_blueprint(notification_bp, url_prefix="/notifications")

# ── 5. Static uploads ─────────────────────────────────────────────────────────
from flask import send_from_directory

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ── 6. Health check ───────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "🗄️ BANTAY Backend is running!"}

@app.get("/health")
def health():
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DATABASE() AS db, NOW() AS time")
        result = cursor.fetchone()
        cursor.close()
        return {
            "status":   "✅ ok",
            "database": result["db"],
            "time":     str(result["time"]),
        }
    except Exception as e:
        return {"status": "❌ error", "message": str(e)}, 500

# ── 7. Run ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=8000, use_reloader=False)