# backend/features/auth/auth_controller.py

from datetime import datetime, timedelta, timezone
from flask import request, g, jsonify

from config.database import get_db
from features.auth.auth_service import resend_otp, send_otp, verify_otp
from features.auth.auth_validator import (
    validate_email, validate_login_input,
    validate_otp_code, validate_password_change, validate_reset_password,
)
from shared.utils.audit_logger import get_client_ip, log_audit
from shared.utils.token_manager import create_token, revoke_all_user_tokens, revoke_token


def get_ip():
    return request.remote_addr


# ── Login ─────────────────────────────────────────────────────────────────────
def login():
    try:
        body     = request.get_json()
        username = body.get("username", "")
        password = body.get("password", "")
        ip       = get_ip()

        errors = validate_login_input(username, password)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.user_id, u.username, u.password, u.email,
                      u.first_name, u.last_name, u.user_type,
                      u.profile_picture, u.status, u.lockout_until,
                      u.failed_login_attempts, u.last_login,
                      r.role_name,
                      bd.barangay_code AS assigned_barangay_code
               FROM users u
               JOIN roles r ON u.role_id = r.role_id
               LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
               WHERE u.username = %s""",
            (username.strip(),),
        )
        user = cursor.fetchone()

        if not user:
            cursor.close()
            log_audit(username=username.strip(), event_name="Login Failed",
                      description="Account does not exist", action="LOGIN",
                      status="failed", source="Web Portal", ip_address=ip)
            return jsonify({"success": False, "message": "Account does not exist"}), 401

        now = datetime.now(timezone.utc)

        if user["status"] == "deactivated":
            cursor.close()
            return jsonify({"success": False, "message": "Account has been deactivated"}), 403

        if user["status"] == "unverified":
            cursor.close()
            return jsonify({"success": False, "message": "Account is not yet verified"}), 403

        if user["status"] == "locked" and user["lockout_until"]:
            lockout_until = user["lockout_until"]
            if lockout_until.tzinfo is None:
                lockout_until = lockout_until.replace(tzinfo=timezone.utc)
            if now < lockout_until:
                diff    = lockout_until - now
                minutes = int(diff.total_seconds() // 60)
                seconds = int(diff.total_seconds() % 60)
                cursor.close()
                return jsonify({
                    "success": False,
                    "message": f"Account locked. Try again in {minutes}m {seconds}s",
                    "lockout_until": str(user["lockout_until"]),
                }), 403
            # Lock expired — reset
            cursor.execute(
                "UPDATE users SET status=%s, lockout_until=NULL, failed_login_attempts=0 WHERE user_id=%s",
                ("verified", user["user_id"]),
            )
            conn.commit()

        if user["status"] == "locked" and not user["lockout_until"]:
            cursor.close()
            return jsonify({"success": False, "message": "Account is permanently locked. Please contact an administrator."}), 403

        # ── PASSWORD CHECK (plain text) ────────────────────────────────────────
        if password != user["password"]:
            attempts     = user["failed_login_attempts"] + 1
            lock_minutes = None

            if attempts >= 8:
                cursor.execute(
                    "UPDATE users SET failed_login_attempts=%s, status=%s, lockout_until=NULL WHERE user_id=%s",
                    (attempts, "locked", user["user_id"]),
                )
                conn.commit()
                cursor.close()
                return jsonify({"success": False, "message": "Account permanently locked. Contact an administrator."}), 403

            if attempts == 5:
                lock_minutes = 15
            elif attempts == 3:
                lock_minutes = 5

            if lock_minutes:
                lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
                cursor.execute(
                    "UPDATE users SET failed_login_attempts=%s, status=%s, lockout_until=%s WHERE user_id=%s",
                    (attempts, "locked", lock_until, user["user_id"]),
                )
                conn.commit()
                cursor.close()
                return jsonify({
                    "success": False,
                    "message": f"Account locked for {lock_minutes} minutes",
                    "lockout_until": str(lock_until),
                }), 403

            cursor.execute(
                "UPDATE users SET failed_login_attempts=%s WHERE user_id=%s",
                (attempts, user["user_id"]),
            )
            conn.commit()
            cursor.close()
            attempts_left = (5 - attempts) if attempts < 5 else None
            resp = {"success": False, "message": "Invalid credentials"}
            if attempts_left:
                resp["attempts_left"] = attempts_left
            return jsonify(resp), 401

        # ── SUCCESS ───────────────────────────────────────────────────────────
        cursor.execute(
            "UPDATE users SET failed_login_attempts=0, status='verified', lockout_until=NULL, last_login=NOW() WHERE user_id=%s",
            (user["user_id"],),
        )
        conn.commit()
        cursor.close()

        token = create_token({
            "user_id":   str(user["user_id"]),
            "username":  user["username"],
            "email":     user["email"],
            "role":      user["role_name"],
            "user_type": user["user_type"],
        })

        log_audit(user_id=str(user["user_id"]), username=user["username"],
                  event_name="User Login", description="Logged in via web portal",
                  action="LOGIN", status="success", source="Web Portal", ip_address=ip)

        return jsonify({
            "success": True,
            "token":   token,
            "user": {
                "user_id":                str(user["user_id"]),
                "username":               user["username"],
                "role":                   user["role_name"],
                "user_type":              user["user_type"],
                "first_name":             user["first_name"],
                "last_name":              user["last_name"],
                "profile_picture":        user["profile_picture"] or None,
                "assigned_barangay_code": user["assigned_barangay_code"] or None,
            },
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"success": False, "message": "Login failed"}), 500


# ── Logout ────────────────────────────────────────────────────────────────────
def logout():
    try:
        auth  = request.headers.get("Authorization", "")
        token = auth.split(" ")[-1]
        ip    = get_ip()

        if not token:
            return jsonify({"success": False, "message": "No token provided"}), 400

        revoke_token(token)
        log_audit(user_id=str(g.user["user_id"]), username=g.user["username"],
                  event_name="User Logout", description="User logged out",
                  action="LOGOUT", status="success", source="Web Portal", ip_address=ip)

        return jsonify({"success": True, "message": "Logged out successfully"}), 200
    except Exception as e:
        print(f"Logout error: {e}")
        return jsonify({"success": False, "message": "Logout failed"}), 500


# ── Logout All ────────────────────────────────────────────────────────────────
def logout_all():
    try:
        ip = get_ip()
        revoke_all_user_tokens(g.user["user_id"])
        log_audit(user_id=str(g.user["user_id"]), username=g.user["username"],
                  event_name="Logout All Devices", description="All sessions revoked",
                  action="LOGOUT", status="success", source="Web Portal", ip_address=ip)
        return jsonify({"success": True, "message": "Logged out from all devices"}), 200
    except Exception as e:
        print(f"Logout all error: {e}")
        return jsonify({"success": False, "message": "Logout all failed"}), 500


# ── Send OTP ──────────────────────────────────────────────────────────────────
def send_otp_handler():
    try:
        body  = request.get_json()
        email = body.get("email", "")

        errors = validate_email(email)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, email, status FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        user = cursor.fetchone()
        cursor.close()

        if not user:
            return jsonify({"success": False, "message": "Email not found"}), 200
        if user["status"] == "deactivated":
            return jsonify({"success": False, "message": "Account is deactivated"}), 403
        if user["status"] == "unverified":
            return jsonify({"success": False, "message": "Account is not yet verified"}), 403

        result = send_otp(email)
        return jsonify(result), 200 if result["success"] else 429

    except Exception as e:
        print(f"Send OTP error: {e}")
        return jsonify({"success": False, "message": "Failed to send OTP"}), 500


# ── Verify OTP ────────────────────────────────────────────────────────────────
def verify_otp_handler():
    try:
        body  = request.get_json()
        email = body.get("email", "")
        code  = body.get("code", "")

        errors = validate_email(email) + validate_otp_code(code)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        result = verify_otp(email, code)
        return jsonify(result), 200 if result["success"] else 400

    except Exception as e:
        print(f"Verify OTP error: {e}")
        return jsonify({"success": False, "message": "OTP verification failed"}), 500


# ── Resend OTP ────────────────────────────────────────────────────────────────
def resend_otp_handler():
    try:
        body  = request.get_json()
        email = body.get("email", "")

        errors = validate_email(email)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        result = resend_otp(email)
        return jsonify(result), 200 if result["success"] else 429

    except Exception as e:
        print(f"Resend OTP error: {e}")
        return jsonify({"success": False, "message": "Failed to resend OTP"}), 500


# ── Reset Password ────────────────────────────────────────────────────────────
def reset_password():
    try:
        body         = request.get_json()
        email        = body.get("email", "")
        new_password = (body.get("newPassword") or "").strip()
        ip           = get_ip()

        errors = validate_reset_password(email, new_password)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, username, password, status FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        user = cursor.fetchone()

        if not user:
            cursor.close()
            return jsonify({"success": False, "message": "User not found"}), 404
        if user["status"] == "deactivated":
            cursor.close()
            return jsonify({"success": False, "message": "Account is deactivated"}), 403
        if new_password == user["password"]:
            cursor.close()
            return jsonify({"success": False, "message": "New password cannot be the same as the old password"}), 400

        cursor.execute(
            """UPDATE users SET password=%s, failed_login_attempts=0,
               status=CASE WHEN status='locked' THEN 'verified' ELSE status END,
               lockout_until=NULL, updated_at=NOW() WHERE user_id=%s""",
            (new_password, user["user_id"]),
        )
        cursor.execute("DELETE FROM otp_requests WHERE LOWER(email) = LOWER(%s)", (email,))
        conn.commit()
        cursor.close()

        log_audit(user_id=str(user["user_id"]), username=user["username"],
                  event_name="Password Reset", description=f"Password reset via OTP for {email}",
                  action="UPDATE", status="success", source="Web Portal", ip_address=ip)

        return jsonify({"success": True, "message": "Password reset successfully"}), 200

    except Exception as e:
        print(f"Reset password error: {e}")
        return jsonify({"success": False, "message": "Password reset failed"}), 500


# ── Change Password ───────────────────────────────────────────────────────────
def change_password():
    try:
        body             = request.get_json()
        current_password = (body.get("currentPassword") or "").strip()
        new_password     = (body.get("newPassword") or "").strip()
        ip               = get_ip()

        errors = validate_password_change(current_password, new_password)
        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT password FROM users WHERE user_id=%s",
            (g.user["user_id"],),
        )
        row = cursor.fetchone()

        if not row:
            cursor.close()
            return jsonify({"success": False, "message": "User not found"}), 404
        if current_password != row["password"]:
            cursor.close()
            log_audit(user_id=str(g.user["user_id"]), username=g.user["username"],
                      event_name="Password Change Failed", description="Incorrect current password",
                      action="UPDATE", status="failed", source="Web Portal", ip_address=ip)
            return jsonify({"success": False, "message": "Current password is incorrect"}), 401
        if new_password == row["password"]:
            cursor.close()
            return jsonify({"success": False, "message": "New password cannot be the same as the current password"}), 400

        cursor.execute(
            "UPDATE users SET password=%s, updated_at=NOW() WHERE user_id=%s",
            (new_password, g.user["user_id"]),
        )
        conn.commit()
        cursor.close()

        revoke_all_user_tokens(g.user["user_id"])

        log_audit(user_id=str(g.user["user_id"]), username=g.user["username"],
                  event_name="Password Changed", description="All sessions revoked after password change",
                  action="UPDATE", status="success", source="Web Portal", ip_address=ip)

        return jsonify({"success": True, "message": "Password changed successfully. Please log in again."}), 200

    except Exception as e:
        print(f"Change password error: {e}")
        return jsonify({"success": False, "message": "Password change failed"}), 500