# backend\features\auth\auth_validator.py

import re

# ── Login ─────────────────────────────────────────────────────────────────────
def validate_login_input(username: str, password: str) -> list:
    errors = []
    if not username or not username.strip():
        errors.append("Username is required")
    if not password or not password.strip():
        errors.append("Password is required")
    return errors

# ── Email ─────────────────────────────────────────────────────────────────────
def validate_email(email: str) -> list:
    errors = []
    if not email:
        errors.append("Email is required")
        return errors
    pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(pattern, email):
        errors.append("Invalid email format")
    return errors

# ── Password change ───────────────────────────────────────────────────────────
def validate_password_change(current_password: str, new_password: str) -> list:
    errors = []
    if not current_password:
        errors.append("Current password is required")
    if not new_password:
        errors.append("New password is required")
    if new_password and len(new_password) < 8:
        errors.append("New password must be at least 8 characters")
    return errors

# ── Reset password ────────────────────────────────────────────────────────────
def validate_reset_password(email: str, new_password: str) -> list:
    errors = []
    if not email:
        errors.append("Email is required")
    if not new_password:
        errors.append("New password is required")
    if new_password and len(new_password) < 8:
        errors.append("Password must be at least 8 characters")
    return errors

# ── OTP code ──────────────────────────────────────────────────────────────────
def validate_otp_code(code: str) -> list:
    errors = []
    if not code:
        errors.append("Verification code is required")
        return errors
    if len(code) != 6:
        errors.append("Verification code must be 6 digits")
    if not re.fullmatch(r"\d{6}", code):
        errors.append("Verification code must contain only numbers")
    return errors