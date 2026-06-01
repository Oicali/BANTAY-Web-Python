import os, random, string
import bcrypt
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import config.database as db
import httpx



# ── Generate 6-digit OTP ──────────────────────────────────────────────────────
def generate_otp() -> str:
    return str(random.randint(100000, 999999))

# ── Send email via Brevo (replaces nodemailer) ────────────────────────────────
async def send_email(to: str, subject: str, html: str, first_name: str = "Officer"):
    payload = {
        "sender": {
            "name":  "BANTAY System",
            "email": os.getenv("BREVO_SENDER_EMAIL"),
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "Content-Type": "application/json",
                "api-key": os.getenv("BREVO_API_KEY"),
            },
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("BREVO_RATE_LIMITED")

    if not response.is_success:
        raise Exception(f"Brevo API error: {response.text}")

# ── Send OTP ──────────────────────────────────────────────────────────────────
async def send_otp(email: str) -> dict:
    try:
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT email, first_name FROM users WHERE LOWER(email) = LOWER($1)",
                email,
            )
            if not user:
                return {"success": False, "message": "No account found with this email address"}

            otp_row = await conn.fetchrow(
                """SELECT request_count,
                          (last_request_at::date = CURRENT_DATE) AS is_same_day
                   FROM otp_requests WHERE email = $1""",
                email,
            )

            request_count = 1
            if otp_row:
                request_count = otp_row["request_count"] + 1 if otp_row["is_same_day"] else 1
                if request_count > 10:
                    return {
                        "success": False,
                        "message": "Maximum OTP requests reached. Try again tomorrow or contact administrator.",
                    }

            otp = generate_otp()
            otp_hash = bcrypt.hashpw(otp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

            await conn.execute(
                """INSERT INTO otp_requests (email, otp_hash, expires_at, request_count, last_request_at)
                   VALUES ($1, $2, NOW() + INTERVAL '2 minutes', $3, CURRENT_TIMESTAMP)
                   ON CONFLICT (email) DO UPDATE SET
                     otp_hash = EXCLUDED.otp_hash,
                     expires_at = EXCLUDED.expires_at,
                     request_count = EXCLUDED.request_count,
                     last_request_at = EXCLUDED.last_request_at""",
                email, otp_hash, request_count,
            )

        first_name = user["first_name"] or "Officer"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #1e293b 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 10px 10px; }}
            .otp-box {{ background: white; border: 3px solid #1e3a8a; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px; }}
            .otp-code {{ font-size: 36px; font-weight: bold; color: #1e3a8a; letter-spacing: 8px; margin: 10px 0; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header"><h1>BANTAY SYSTEM</h1></div>
            <div class="content">
              <h2>New Verification Code</h2>
              <p>Hello {first_name},</p>
              <p>Here is your new verification code:</p>
              <div class="otp-box">
                <div class="otp-code">{otp}</div>
              </div>
              <p>This code will expire in <strong>2 minutes</strong>.</p>
            </div>
          </div>
        </body>
        </html>
        """
        await send_email(email, "BANTAY System - New Verification Code", html)
        return {"success": True, "message": "Verification code sent to your email"}

    except Exception as e:
        print(f"Error sending OTP: {e}")
        return {"success": False, "message": "Failed to send verification code"}

# ── Verify OTP ────────────────────────────────────────────────────────────────
async def verify_otp(email: str, code: str) -> dict:
    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT otp_hash, (expires_at < NOW()) AS is_expired
                   FROM otp_requests WHERE email = $1""",
                email,
            )
            if not row:
                return {"success": False, "message": "No OTP found. Please request a new one."}

            if row["is_expired"]:
                await conn.execute("DELETE FROM otp_requests WHERE email = $1", email)
                return {"success": False, "message": "OTP expired. Please request a new one."}

            if not bcrypt.checkpw(code.encode("utf-8"), row["otp_hash"].encode("utf-8")):
                return {"success": False, "message": "Invalid OTP."}

            await conn.execute("DELETE FROM otp_requests WHERE email = $1", email)
            return {"success": True, "message": "OTP verified."}

    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return {"success": False, "message": "Verification failed."}

# ── Resend OTP ────────────────────────────────────────────────────────────────
async def resend_otp(email: str) -> dict:
    return await send_otp(email)