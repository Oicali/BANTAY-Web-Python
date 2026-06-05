# backend/features/auth/auth_service.py

import os, random
from config.database import get_db
import httpx

def generate_otp() -> str:
    return str(random.randint(100000, 999999))

def send_email(to: str, subject: str, html: str):
    import requests
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "Content-Type": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
        },
        json={
            "sender": {"name": "BANTAY System", "email": os.getenv("BREVO_SENDER_EMAIL")},
            "to":      [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        },
    )
    if response.status_code == 429:
        raise Exception("BREVO_RATE_LIMITED")
    if not response.ok:
        raise Exception(f"Brevo API error: {response.text}")

def send_otp(email: str) -> dict:
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT email, first_name FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        user = cursor.fetchone()

        if not user:
            cursor.close()
            return {"success": False, "message": "No account found with this email address"}

        cursor.execute(
            """SELECT request_count,
                      (DATE(last_request_at) = CURDATE()) AS is_same_day
               FROM otp_requests WHERE email = %s""",
            (email,),
        )
        otp_row = cursor.fetchone()

        request_count = 1
        if otp_row:
            request_count = otp_row["request_count"] + 1 if otp_row["is_same_day"] else 1
            if request_count > 10:
                cursor.close()
                return {"success": False, "message": "Maximum OTP requests reached. Try again tomorrow."}

        cursor.execute("DELETE FROM otp_requests WHERE expires_at < NOW()")
        conn.commit()

        otp = generate_otp()

        cursor.execute(
            """INSERT INTO otp_requests (email, otp_hash, expires_at, request_count, last_request_at)
               VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL 2 MINUTE), %s, NOW())
               ON DUPLICATE KEY UPDATE
                 otp_hash        = VALUES(otp_hash),
                 expires_at      = VALUES(expires_at),
                 request_count   = VALUES(request_count),
                 last_request_at = VALUES(last_request_at)""",
            (email, otp, request_count),
        )
        conn.commit()
        cursor.close()

        first_name = user["first_name"] or "Officer"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
          <div style="background:#1e3a8a;color:white;padding:30px;text-align:center;border-radius:10px 10px 0 0">
            <h1>BANTAY SYSTEM</h1>
          </div>
          <div style="background:#f9fafb;padding:30px;border-radius:0 0 10px 10px">
            <h2>Verification Code</h2>
            <p>Hello {first_name},</p>
            <div style="border:3px solid #1e3a8a;padding:20px;text-align:center;margin:20px 0;border-radius:8px">
              <div style="font-size:36px;font-weight:bold;color:#1e3a8a;letter-spacing:8px">{otp}</div>
            </div>
            <p>This code expires in <strong>2 minutes</strong>.</p>
          </div>
        </div>
        """
        send_email(email, "BANTAY System - Verification Code", html)
        return {"success": True, "message": "Verification code sent to your email"}

    except Exception as e:
        print(f"Send OTP error: {e}")
        return {"success": False, "message": "Failed to send verification code"}

def verify_otp(email: str, code: str) -> dict:
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT otp_hash, (expires_at < NOW()) AS is_expired FROM otp_requests WHERE email = %s",
            (email,),
        )
        row = cursor.fetchone()

        if not row:
            cursor.close()
            return {"success": False, "message": "No OTP found. Please request a new one."}
        if row["is_expired"]:
            cursor.execute("DELETE FROM otp_requests WHERE email = %s", (email,))
            conn.commit()
            cursor.close()
            return {"success": False, "message": "OTP expired. Please request a new one."}

        if code != row["otp_hash"]:
            cursor.close()
            return {"success": False, "message": "Invalid OTP."}

        cursor.execute("DELETE FROM otp_requests WHERE email = %s", (email,))
        conn.commit()
        cursor.close()
        return {"success": True, "message": "OTP verified."}

    except Exception as e:
        print(f"Verify OTP error: {e}")
        return {"success": False, "message": "Verification failed."}

def resend_otp(email: str) -> dict:
    return send_otp(email)