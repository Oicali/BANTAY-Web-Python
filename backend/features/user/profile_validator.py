# ================================================================================
# FILE: backend/features/user/profile_validator.py
# ================================================================================

import re
from typing import Optional


class ProfileValidator:

    @staticmethod
    def validate_name(
        name: Optional[str],
        field_name: str,
        max_length: int = 50,
        required: bool = True,
    ) -> Optional[str]:
        if not name or name.strip() == "":
            if required:
                return f"{field_name} is required"
            return None

        if len(name) > max_length:
            return f"{field_name} must not exceed {max_length} characters"

        if not re.match(r"^[a-zA-Z\s'\-.]+$", name.strip()):
            return f"{field_name} can only contain letters, spaces, hyphens, apostrophes, and periods"

        return None


    @staticmethod
    def validate_suffix(suffix: Optional[str]) -> Optional[str]:
        if not suffix or suffix.strip() == "":
            return None

        if len(suffix) > 5:
            return "Suffix must not exceed 5 characters"

        if not re.match(r"^(Jr\.?|Sr\.?|I{1,3}|IV|V)$", suffix.strip(), re.IGNORECASE):
            return "Valid suffixes: Jr., Sr., I, II, III, IV, V"

        return None


    @staticmethod
    def validate_phone(
        phone: Optional[str],
        field_name: str = "Phone number",
        required: bool = True,
    ) -> Optional[str]:
        if not phone or phone.strip() == "":
            if required:
                return f"{field_name} is required"
            return None

        clean_phone = re.sub(r"[^\d+]", "", phone)

        if not clean_phone.startswith("+63"):
            return f"{field_name} must start with +63"

        number_part = clean_phone[3:]

        if len(number_part) != 10:
            return f"{field_name} must have exactly 10 digits after +63"

        if not number_part.startswith("9"):
            return f"{field_name} must start with +639"

        return None

    @staticmethod
    def validate_gender(gender: Optional[str]) -> Optional[str]:
        if not gender:
            return "Gender is required"

        if gender not in ("Male", "Female"):
            return "Gender must be Male or Female"

        return None


    @staticmethod
    def validate_address_line(address_line: Optional[str]) -> Optional[str]:
        if not address_line or address_line.strip() == "":
            return None  # optional

        if len(address_line) > 255:
            return "Address line must not exceed 255 characters"

        return None

    @staticmethod
    def validate_psgc_code(code: Optional[str], field_name: str) -> Optional[str]:
        if not code or code.strip() == "":
            return None  # optional

        if not re.match(r"^\d+$", code.strip()):
            return f"{field_name} must contain only numbers"

        if len(code.strip()) > 30:
            return f"{field_name} must not exceed 30 characters"

        return None


    @staticmethod
    def validate_password(password: Optional[str]) -> list[str]:
        errors = []

        if not password or password.strip() == "":
            errors.append("Password is required")
            return errors

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        if not re.search(r"(?=.*[a-z])", password):
            errors.append("Password must contain at least one lowercase letter")

        if not re.search(r"(?=.*[A-Z])", password):
            errors.append("Password must contain at least one uppercase letter")

        if not re.search(r"(?=.*\d)", password):
            errors.append("Password must contain at least one number")

        if not re.search(r"(?=.*[@$!%*?&#])", password):
            errors.append("Password must contain at least one special character (@$!%*?&#)")

        return errors


    @classmethod
    def validate_profile_update(cls, data: dict) -> dict:
        errors = {}

        # Name fields
        first_name_err = cls.validate_name(data.get("first_name"), "First name", 50, True)
        if first_name_err:
            errors["first_name"] = first_name_err

        last_name_err = cls.validate_name(data.get("last_name"), "Last name", 50, True)
        if last_name_err:
            errors["last_name"] = last_name_err

        if data.get("middle_name"):
            middle_name_err = cls.validate_name(data["middle_name"], "Middle name", 50, False)
            if middle_name_err:
                errors["middle_name"] = middle_name_err

        if data.get("suffix"):
            suffix_err = cls.validate_suffix(data["suffix"])
            if suffix_err:
                errors["suffix"] = suffix_err

        if data.get("gender"):
            gender_err = cls.validate_gender(data["gender"])
            if gender_err:
                errors["gender"] = gender_err

        # Phone fields (expects +63 prefix)
        phone_err = cls.validate_phone(data.get("phone"), "Phone number", False)
        if phone_err:
            errors["phone"] = phone_err

        if data.get("alternate_phone"):
            alt_phone_err = cls.validate_phone(data["alternate_phone"], "Alternate phone number", False)
            if alt_phone_err:
                errors["alternate_phone"] = alt_phone_err

        if (
            data.get("phone")
            and data.get("alternate_phone")
            and data["phone"] == data["alternate_phone"]
        ):
            errors["alternate_phone"] = "Alternate phone cannot be the same as primary phone"

        # Structured address fields (all optional)
        for code_field, label in (
            ("region_code",       "Region code"),
            ("province_code",     "Province code"),
            ("municipality_code", "Municipality code"),
            ("barangay_code",     "Barangay code"),
        ):
            err = cls.validate_psgc_code(data.get(code_field), label)
            if err:
                errors[code_field] = err

        address_line_err = cls.validate_address_line(data.get("address_line"))
        if address_line_err:
            errors["address_line"] = address_line_err

        return {"is_valid": len(errors) == 0, "errors": errors}

    @classmethod
    def validate_password_change(cls, data: dict) -> dict:
        errors = {}

        if not data.get("currentPassword"):
            errors["currentPassword"] = "Current password is required"

        if not data.get("newPassword"):
            errors["newPassword"] = "New password is required"
        else:
            pw_errors = cls.validate_password(data["newPassword"])
            if pw_errors:
                errors["newPassword"] = pw_errors[0]

        if not data.get("confirmPassword"):
            errors["confirmPassword"] = "Please confirm your new password"
        elif data.get("newPassword") != data.get("confirmPassword"):
            errors["confirmPassword"] = "Passwords do not match"

        if (
            data.get("currentPassword")
            and data.get("newPassword")
            and data["currentPassword"] == data["newPassword"]
        ):
            errors["newPassword"] = "New password must be different from current password"

        return {"is_valid": len(errors) == 0, "errors": errors}