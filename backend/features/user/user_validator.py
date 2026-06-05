# ================================================================================
# FILE: backend/features/user/user_validator.py
# ================================================================================

from __future__ import annotations

import re
from typing import Optional


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+639\d{9}$")


def _fetchrow(cursor, sql: str, params: tuple):
    """Execute a SELECT and return the first row as a dict, or None."""
    cursor.execute(sql, params)
    return cursor.fetchone()


class UserValidator:


    @staticmethod
    def validate_email(email: Optional[str], required: bool = True) -> Optional[str]:
        if not email or not email.strip():
            return "Email is required" if required else None
        if not _EMAIL_RE.match(email.strip()):
            return "Invalid email format"
        return None

    @staticmethod
    def validate_phone(
        phone: Optional[str],
        field_name: str = "Phone number",
        required: bool = True,
    ) -> Optional[str]:
        if not phone or not phone.strip():
            return f"{field_name} is required" if required else None
        if not _PHONE_RE.match(phone.strip()):
            return (
                f"{field_name} must be in format +639XXXXXXXXX "
                f"(e.g., +639171234567)"
            )
        return None


    @staticmethod
    def validate_user_type(user_type: Optional[str]) -> Optional[str]:
        if not user_type:
            return "User type is required"
        if user_type not in ("police", "barangay"):
            return "Invalid user type. Must be 'police' or 'barangay'"
        return None

  
    @staticmethod
    def validate_required_fields(data: dict) -> Optional[str]:
        base_required = [
            "userType",
            "email",
            "firstName",
            "lastName",
            "phone",
            "role",
            "gender",
            "dateOfBirth",
            "regionCode",
            "provinceCode",
            "municipalityCode",
        ]

        missing = [f for f in base_required if not data.get(f)]

        # Accept either 'barangayCode' or 'barangay'
        if not data.get("barangayCode") and not data.get("barangay"):
            missing.append("barangayCode")

        if missing:
            return f"Missing required fields: {', '.join(missing)}"
        return None

  
    @staticmethod
    def validate_phone_difference(
        phone: Optional[str],
        alternate_phone: Optional[str],
    ) -> Optional[str]:
        if phone and alternate_phone and phone == alternate_phone:
            return "Phone and alternate phone cannot be the same"
        return None


    @staticmethod
    def validate_phone_uniqueness(
        phone: Optional[str],
        cursor,
        exclude_user_id=None,
    ) -> Optional[str]:
        if not phone:
            return None
        if exclude_user_id:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users "
                "WHERE (phone = %s OR alternate_phone = %s) AND user_id != %s",
                (phone, phone, exclude_user_id),
            )
        else:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users WHERE phone = %s OR alternate_phone = %s",
                (phone, phone),
            )
        return "Phone number already registered" if row else None

    @staticmethod
    def validate_alternate_phone_uniqueness(
        alternate_phone: Optional[str],
        cursor,
        exclude_user_id=None,
    ) -> Optional[str]:
        if not alternate_phone:
            return None
        if exclude_user_id:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users "
                "WHERE (phone = %s OR alternate_phone = %s) AND user_id != %s",
                (alternate_phone, alternate_phone, exclude_user_id),
            )
        else:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users WHERE phone = %s OR alternate_phone = %s",
                (alternate_phone, alternate_phone),
            )
        return "Alternate phone number already registered" if row else None

    @staticmethod
    def validate_email_uniqueness(
        email: Optional[str],
        cursor,
        exclude_user_id=None,
    ) -> Optional[str]:
        if not email:
            return None
        if exclude_user_id:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users "
                "WHERE LOWER(email) = LOWER(%s) AND user_id != %s",
                (email, exclude_user_id),
            )
        else:
            row = _fetchrow(
                cursor,
                "SELECT user_id FROM users WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
        return "Email already registered" if row else None

    @staticmethod
    def validate_role(
        role: Optional[str],
        user_type: Optional[str],
        cursor,
    ) -> Optional[str]:
        if not role:
            return "Role is required"
        row = _fetchrow(
            cursor,
            "SELECT role_id FROM roles WHERE role_name = %s AND user_type = %s",
            (role, user_type),
        )
        if not row:
            return f"Invalid role '{role}' for {user_type} user."
        return None


    @classmethod
    def validate_registration(cls, data: dict, cursor) -> dict:
        errors: dict[str, str] = {}

        required_error = cls.validate_required_fields(data)
        if required_error:
            errors["general"] = required_error

        user_type_error = cls.validate_user_type(data.get("userType"))
        if user_type_error:
            errors["userType"] = user_type_error

        email_error = cls.validate_email(data.get("email"))
        if email_error:
            errors["email"] = email_error

        phone_error = cls.validate_phone(data.get("phone"))
        if phone_error:
            errors["phone"] = phone_error

        if data.get("alternatePhone"):
            alt_phone_error = cls.validate_phone(
                data["alternatePhone"], "Alternate phone number", required=False
            )
            if alt_phone_error:
                errors["alternatePhone"] = alt_phone_error

        diff_error = cls.validate_phone_difference(
            data.get("phone"), data.get("alternatePhone")
        )
        if diff_error:
            errors["alternatePhone"] = diff_error

        # DB uniqueness checks
        if "email" not in errors:
            email_uniq = cls.validate_email_uniqueness(data.get("email"), cursor)
            if email_uniq:
                errors["email"] = email_uniq

        if "phone" not in errors:
            phone_uniq = cls.validate_phone_uniqueness(data.get("phone"), cursor)
            if phone_uniq:
                errors["phone"] = phone_uniq

        if data.get("alternatePhone") and "alternatePhone" not in errors:
            alt_uniq = cls.validate_alternate_phone_uniqueness(
                data["alternatePhone"], cursor
            )
            if alt_uniq:
                errors["alternatePhone"] = alt_uniq

        if "role" not in errors:
            role_error = cls.validate_role(
                data.get("role"), data.get("userType"), cursor
            )
            if role_error:
                errors["role"] = role_error

        return {"isValid": len(errors) == 0, "is_valid": len(errors) == 0, "errors": errors}

  
    @classmethod
    def validate_update(cls, data: dict, existing_user: dict, cursor) -> dict:
        errors: dict[str, str] = {}

        # Email uniqueness (only if changed)
        if data.get("email") and data["email"].lower() != (existing_user.get("email") or "").lower():
            email_uniq = cls.validate_email_uniqueness(
                data["email"], cursor, exclude_user_id=existing_user["user_id"]
            )
            if email_uniq:
                errors["email"] = email_uniq

        # Phone uniqueness (only if changed)
        if data.get("phone") and data["phone"] != existing_user.get("phone"):
            phone_uniq = cls.validate_phone_uniqueness(
                data["phone"], cursor, exclude_user_id=existing_user["user_id"]
            )
            if phone_uniq:
                errors["phone"] = phone_uniq

        # Alternate phone uniqueness (only if changed)
        if (
            data.get("alternate_phone")
            and data["alternate_phone"] != existing_user.get("alternate_phone")
        ):
            alt_uniq = cls.validate_alternate_phone_uniqueness(
                data["alternate_phone"], cursor, exclude_user_id=existing_user["user_id"]
            )
            if alt_uniq:
                errors["alternate_phone"] = alt_uniq

        # Role (only if provided)
        if data.get("role"):
            role_error = cls.validate_role(
                data["role"], existing_user["user_type"], cursor
            )
            if role_error:
                errors["role"] = role_error

        return {"isValid": len(errors) == 0, "is_valid": len(errors) == 0, "errors": errors}