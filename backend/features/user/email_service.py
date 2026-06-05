"""
email_service.py  (Flask / sync rewrite)
Converted from the FastAPI async version.

Uses `requests` instead of `httpx.AsyncClient`.
asyncpg → mysql-connector-python cursor style.
"""

import html as html_lib
import os
import random
import re
import string
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests as http_requests
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# ENV HELPERS
# ============================================================

def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _esc(value) -> str:
    return html_lib.escape(str(value or ""))


# ============================================================
# BREVO HTTP EMAIL HELPER
# ============================================================

def send_brevo_email(*, to: str, subject: str, html: str) -> bool:
    """
    Send an email via Brevo Transactional Email API.

    Required .env:
        BREVO_API_KEY=your_brevo_api_key
        BREVO_SENDER_EMAIL=your_verified_sender@email.com

    Optional .env:
        BREVO_SENDER_NAME=BANTAY System
    """
    api_key      = _get_env("BREVO_API_KEY")
    sender_email = _get_env("BREVO_SENDER_EMAIL")
    sender_name  = os.getenv("BREVO_SENDER_NAME", "BANTAY System")

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to":     [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    response = http_requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers=headers,
        timeout=15,
    )

    if response.status_code == 429:
        raise RuntimeError("BREVO_RATE_LIMITED")

    if not response.ok:
        raise RuntimeError(
            f"Brevo API error: {response.status_code} {response.text}"
        )

    return True


# ============================================================
# GENERATE USERNAME
# ============================================================

def _initial(value: str) -> str:
    value = (value or "").strip()
    return value[0].upper() if value else "X"


def generate_username(
    first_name: str,
    middle_name: Optional[str],
    last_name: str,
    user_type: str,
    db,          # mysql-connector-python connection
) -> str:
    """
    Generate username like:
        DJS26001_police
        DJS26001_barangay
    """
    yy = str(datetime.now(timezone.utc).year)[-2:]

    li = _initial(last_name)
    fi = _initial(first_name)
    mi = _initial(middle_name) if middle_name else ""

    initials        = f"{li}{fi}{mi}"
    safe_user_type  = re.sub(r"[^a-zA-Z0-9_]", "", user_type or "user")
    pattern         = rf"^[A-Z]{{2,3}}{yy}[0-9]+_{re.escape(safe_user_type)}$"

    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM users WHERE username REGEXP %s",
        (pattern,),
    )
    row         = cursor.fetchone()
    cursor.close()

    next_number = int(row["cnt"]) + 1 if row else 1
    seq         = str(next_number).zfill(3) if next_number < 1000 else str(next_number)

    return f"{initials}{yy}{seq}_{safe_user_type}"


# ============================================================
# GENERATE PASSWORD
# ============================================================

def generate_password() -> str:
    upper   = string.ascii_uppercase
    lower   = string.ascii_lowercase
    digits  = string.digits
    special = "!@#$%^&*"
    all_chars = upper + lower + digits + special

    chars = [
        random.choice(upper),
        random.choice(lower),
        random.choice(digits),
        random.choice(special),
    ]
    chars += [random.choice(all_chars) for _ in range(8)]
    random.shuffle(chars)
    return "".join(chars)


# ============================================================
# SHARED EMAIL STYLES
# ============================================================

_BASE_STYLES = """
  body{
    font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;
    line-height:1.6;
    color:#333;
    max-width:600px;
    margin:0 auto;
    padding:20px;
  }
  .header{
    background:linear-gradient(135deg,#1e3a5f 0%,#0a1628 100%);
    color:white;
    padding:30px;
    text-align:center;
    border-radius:10px 10px 0 0;
  }
  .header h1{
    margin:0;
    font-size:28px;
  }
  .content{
    background:#f8f9fa;
    padding:30px;
    border-radius:0 0 10px 10px;
  }
  .footer{
    text-align:center;
    color:#6c757d;
    font-size:12px;
    margin-top:30px;
    padding-top:20px;
    border-top:1px solid #dee2e6;
  }
  .warning-box{
    background:#fff3cd;
    border-left:4px solid #ffc107;
    padding:15px;
    margin:20px 0;
    border-radius:4px;
  }
  .info-box{
    background:#d1ecf1;
    border-left:4px solid #17a2b8;
    padding:15px;
    margin:20px 0;
    border-radius:4px;
  }
  .success-box{
    background:#d4edda;
    border-left:4px solid #28a745;
    padding:15px;
    margin:20px 0;
    border-radius:4px;
  }
  .danger-box{
    background:#f8d7da;
    border-left:4px solid #dc3545;
    padding:15px;
    margin:20px 0;
    border-radius:4px;
  }
  .alert-box{
    background:#fef2f2;
    border-left:4px solid #dc3545;
    padding:15px;
    margin:20px 0;
    border-radius:4px;
  }
  .otp-box{
    background:#fff;
    border:2px dashed #1e3a5f;
    border-radius:10px;
    padding:24px;
    text-align:center;
    margin:24px 0;
  }
  .otp-code{
    font-size:44px;
    font-weight:700;
    letter-spacing:14px;
    color:#0a285c;
    font-family:'Courier New',monospace;
  }
"""


def _html_doc(head_styles: str, body: str) -> str:
    year = datetime.now(timezone.utc).year

    footer = f"""
      <div class="footer">
        <p>
          <strong>BANTAY Crime Monitoring System</strong><br>
          This is an automated message, please do not reply to this email.
        </p>
        <p style="margin-top:10px">
          © {year} BANTAY System. All rights reserved.
        </p>
      </div>
    """

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    {_BASE_STYLES}
    {head_styles}
  </style>
</head>
<body>
  {body}
  {footer}
</body>
</html>
"""


# ============================================================
# SEND VERIFICATION EMAIL
# ============================================================

def send_verification_email(
    email: str,
    first_name: str,
    last_name: str,
    verification_url: str,
) -> dict:
    first_name       = _esc(first_name)
    last_name        = _esc(last_name)
    verification_url = _esc(verification_url)

    extra = """
      .verify-button{
        display:inline-block;
        background:#1e3a5f;
        color:white!important;
        padding:14px 36px;
        text-decoration:none;
        border-radius:6px;
        font-weight:600;
        font-size:16px;
        margin:24px 0;
      }
      .url-fallback{
        word-break:break-all;
        font-family:'Courier New',monospace;
        font-size:12px;
        color:#555;
        background:#eee;
        padding:8px;
        border-radius:4px;
      }
    """

    body = f"""
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0 0;opacity:.9">
          Crime Monitoring and Management System
        </p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Hello, {first_name} {last_name}!</h2>

        <p>
          Your account has been created on the <strong>BANTAY System</strong>.
          Before you can log in and receive your credentials, you must first
          verify that this email address belongs to you.
        </p>

        <div style="text-align:center">
          <a href="{verification_url}" class="verify-button">✅ Verify My Account</a>
        </div>

        <div class="info-box">
          <strong>ℹ️ What happens after verification?</strong>
          <p style="margin:10px 0 0 0">
            Once you click the button above, your account will be activated and
            you will receive a separate email containing your login credentials.
          </p>
        </div>

        <div class="warning-box">
          <strong>⚠️ Important:</strong>
          <ul style="margin:10px 0 0 0;padding-left:20px">
            <li>This verification link expires in <strong>24 hours</strong>.</li>
            <li>If you did not expect this email, please ignore it or contact your administrator.</li>
            <li>Do not share this link with anyone.</li>
          </ul>
        </div>

        <p style="color:#6c757d;font-size:13px">
          If the button above does not work, copy and paste the link below into your browser:
        </p>

        <div class="url-fallback">{verification_url}</div>
      </div>
    """

    try:
        send_brevo_email(
            to=email,
            subject="BANTAY System – Verify Your Account",
            html=_html_doc(extra, body),
        )
        return {"success": True, "message": "Verification email sent successfully"}
    except Exception as exc:
        print(f"send_verification_email error: {exc}")
        return {"success": False, "message": "Failed to send verification email", "error": str(exc)}


# ============================================================
# SEND WELCOME EMAIL
# ============================================================

def send_welcome_email(
    email: str,
    first_name: str,
    last_name: str,
    username: str,
    password: str,
    user_type: str,
    role: str,
) -> dict:
    first_name      = _esc(first_name)
    last_name       = _esc(last_name)
    username        = _esc(username)
    password        = _esc(password)
    role            = _esc(role)
    user_type_label = _esc("PNP" if user_type == "police" else "Barangay")

    extra = """
      .credentials-box{
        background:white;
        border:2px solid #1e3a5f;
        border-radius:8px;
        padding:20px;
        margin:20px 0;
      }
      .credential-item{
        display:flex;
        justify-content:space-between;
        padding:12px 0;
        border-bottom:1px solid #dee2e6;
      }
      .credential-item:last-child{
        border-bottom:none;
      }
      .credential-label{
        font-weight:600;
        color:#495057;
      }
      .credential-value{
        font-family:'Courier New',monospace;
        background:#f8f9fa;
        padding:4px 12px;
        border-radius:4px;
        color:#c1272d;
        font-weight:600;
      }
    """

    body = f"""
      <div class="header">
        <h1>🛡️ Welcome to BANTAY System</h1>
        <p style="margin:10px 0 0 0;opacity:.9">
          Crime Monitoring and Management System
        </p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Hello, {first_name} {last_name}!</h2>

        <div class="success-box">
          <strong>✅ Your account has been verified and is now active!</strong>
          <p style="margin:8px 0 0 0">
            You can now log in to the BANTAY System using the credentials below.
          </p>
        </div>

        <div class="credentials-box">
          <h3 style="margin-top:0;color:#1e3a5f">Your Login Credentials</h3>

          <div class="credential-item">
            <span class="credential-label">Username:</span>
            <span class="credential-value">{username}</span>
          </div>

          <div class="credential-item">
            <span class="credential-label">Password:</span>
            <span class="credential-value">{password}</span>
          </div>

          <div class="credential-item">
            <span class="credential-label">Role:</span>
            <span class="credential-value">{role}</span>
          </div>

          <div class="credential-item">
            <span class="credential-label">User Type:</span>
            <span class="credential-value">{user_type_label}</span>
          </div>
        </div>

        <div class="warning-box">
          <strong>⚠️ Important Security Notice:</strong>
          <ul style="margin:10px 0 0 0;padding-left:20px">
            <li>Please change your password immediately after your first login.</li>
            <li>Do not share your credentials with anyone.</li>
            <li>Keep this email secure or delete it after changing your password.</li>
          </ul>
        </div>

        <div class="info-box">
          <strong>📋 Password Requirements when changing:</strong>
          <ul style="margin:10px 0 0 0;padding-left:20px">
            <li>At least 8 characters long</li>
            <li>Contains uppercase and lowercase letters</li>
            <li>Contains at least one number</li>
            <li>Contains at least one special character (!@#$%^&amp;*)</li>
          </ul>
        </div>
      </div>
    """

    try:
        send_brevo_email(
            to=email,
            subject="BANTAY System – Your Account is Now Active",
            html=_html_doc(extra, body),
        )
        return {"success": True, "message": "Welcome email sent successfully"}
    except Exception as exc:
        print(f"send_welcome_email error: {exc}")
        return {"success": False, "message": "Failed to send welcome email", "error": str(exc)}


# ============================================================
# SEND OTP EMAIL
# ============================================================

def send_otp_email(email: str, otp: str, type_: str = "new") -> dict:
    is_current = type_ == "current"

    subject = (
        "BANTAY System – Verify Your Current Email"
        if is_current
        else "BANTAY System – Verify Your New Email Address"
    )
    heading = (
        "Confirm Your Current Email"
        if is_current
        else "Verify Your New Email Address"
    )
    body_text = (
        "Someone requested an email address change on your account. "
        "Enter this code to confirm you own your current email:"
        if is_current
        else "You are changing your email address on the <strong>BANTAY System</strong>. "
             "Enter this code to verify your new email:"
    )

    otp = _esc(otp)

    body = f"""
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0;opacity:.9">Email Verification</p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">{heading}</h2>
        <p>{body_text}</p>

        <div class="otp-box">
          <div class="otp-code">{otp}</div>
          <p style="margin:12px 0 0;color:#6c757d;font-size:13px">
            This code expires in <strong>2 minutes</strong>
          </p>
        </div>

        <div class="warning-box">
          <strong>⚠️ Important:</strong>
          <ul style="margin:10px 0 0;padding-left:20px">
            <li>Never share this code with anyone.</li>
            <li>BANTAY System staff will never ask for this code.</li>
            <li>If you did not request this change, please secure your account immediately.</li>
          </ul>
        </div>
      </div>
    """

    try:
        send_brevo_email(to=email, subject=subject, html=_html_doc("", body))
        return {"success": True}
    except Exception as exc:
        print(f"send_otp_email error: {exc}")
        return {"success": False, "message": "Failed to send verification email", "error": str(exc)}


# ============================================================
# SEND PASSWORD OTP EMAIL
# ============================================================

def send_password_otp_email(email: str, first_name: str, otp: str) -> dict:
    first_name = _esc(first_name or "User")
    otp        = _esc(otp)

    body = f"""
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0;opacity:.9">
          Password Change Verification
        </p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Hello, {first_name}!</h2>

        <p>
          You requested to change your password. Enter this code to complete the process:
        </p>

        <div class="otp-box">
          <div class="otp-code">{otp}</div>
          <p style="margin:12px 0 0;color:#6c757d;font-size:13px">
            Expires in <strong>2 minutes</strong>
          </p>
        </div>

        <div class="warning-box">
          <strong>⚠️ Important:</strong>
          <ul style="margin:10px 0 0;padding-left:20px">
            <li>Never share this code with anyone.</li>
            <li>If you did not request a password change, secure your account immediately.</li>
            <li>BANTAY staff will never ask for this code.</li>
          </ul>
        </div>
      </div>
    """

    try:
        send_brevo_email(
            to=email,
            subject="BANTAY System – Password Change Verification Code",
            html=_html_doc("", body),
        )
        return {"success": True}
    except Exception as exc:
        print(f"send_password_otp_email error: {exc}")
        return {"success": False, "message": "Failed to send OTP email", "error": str(exc)}


# ============================================================
# SEND PASSWORD CHANGED NOTIFICATION
# ============================================================

def send_password_changed_notification(email: str, first_name: str) -> dict:
    first_name = _esc(first_name or "User")
    now_ph     = datetime.now(ZoneInfo("Asia/Manila")).strftime("%B %d, %Y, %I:%M %p")

    body = f"""
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0;opacity:.9">Security Notification</p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Hello, {first_name}!</h2>

        <div class="success-box">
          <strong>✅ Your password was successfully changed</strong>
          <p style="margin:8px 0 0">
            Changed on: <strong>{now_ph} (Philippine Time)</strong>
          </p>
        </div>

        <div class="danger-box">
          <strong>🚨 Wasn't you?</strong>
          <p style="margin:8px 0 0">
            If you did not make this change, your account may be compromised.
            Contact your system administrator immediately.
          </p>
        </div>
      </div>
    """

    try:
        send_brevo_email(
            to=email,
            subject="BANTAY System – Your Password Was Changed",
            html=_html_doc("", body),
        )
        return {"success": True}
    except Exception as exc:
        print(f"send_password_changed_notification error: {exc}")
        return {"success": False, "error": str(exc)}


# ============================================================
# SEND EMAIL CHANGED NOTIFICATION
# ============================================================

def send_email_changed_notification(old_email: str, new_email: str) -> dict:
    now_ph = datetime.now(ZoneInfo("Asia/Manila")).strftime("%B %d, %Y, %I:%M %p")

    old_body = f"""
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0;opacity:.9">Security Alert</p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Your Account Email Has Been Changed</h2>

        <p>Your account email address has been successfully changed.</p>

        <div class="alert-box">
          <strong>⚠️ If this was not you, please contact support immediately.</strong><br>
          Your account may have been compromised.
        </div>

        <p>This change was made on <strong>{now_ph} (Philippine Time)</strong>.</p>
      </div>
    """

    new_body = """
      <div class="header">
        <h1>🛡️ BANTAY System</h1>
        <p style="margin:10px 0 0;opacity:.9">Email Updated</p>
      </div>

      <div class="content">
        <h2 style="color:#0a1628">Your Email Has Been Successfully Updated</h2>

        <p>Your BANTAY System account email has been updated to this address.</p>

        <div class="success-box">
          <strong>✓ This is now your login email.</strong><br>
          Please use this email address to log in from now on.
        </div>
      </div>
    """

    try:
        send_brevo_email(
            to=old_email,
            subject="BANTAY System – Your Account Email Has Been Changed",
            html=_html_doc("", old_body),
        )
        send_brevo_email(
            to=new_email,
            subject="BANTAY System – Your Email Has Been Successfully Updated",
            html=_html_doc("", new_body),
        )
        return {"success": True}
    except Exception as exc:
        print(f"send_email_changed_notification error: {exc}")
        return {"success": False, "error": str(exc)}