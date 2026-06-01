# backend\features\user\user.py

from typing import Optional
import asyncpg
from datetime import datetime


class User:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # =====================================================
    # GET CURRENT USER PROFILE
    # =====================================================
    async def get_profile(self, user_id: int) -> Optional[dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 
                        u.user_id, u.username, u.email, 
                        u.first_name, u.last_name, u.middle_name, u.suffix, 
                        u.phone, u.alternate_phone,
                        u.gender, 
                        TO_CHAR(u.date_of_birth, 'YYYY-MM-DD') AS date_of_birth,
                        u.profile_picture, u.user_type, u.status, u.created_at,
                        u.rank_id,
                        r.role_name AS role,
                        pr.rank_name AS rank,
                        pr.abbreviation AS rank_abbreviation,
                        ua.region_code, ua.province_code,
                        ua.municipality_code, ua.barangay_code,
                        ua.address_line,
                        bd.barangay_code AS assigned_barangay_code
                    FROM users u
                    LEFT JOIN roles r ON u.role_id = r.role_id
                    LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
                    LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                    LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                    WHERE u.user_id = $1
                    """,
                    user_id,
                )
                return dict(row) if row else None
        except Exception as error:
            print(f"Get profile error: {error}")
            raise

    # =====================================================
    # CHECK PHONE AVAILABILITY
    # =====================================================
    async def check_phone_availability(
        self, phone: str, exclude_user_id: Optional[int] = None
    ) -> bool:
        try:
            if not phone or phone.strip() == "":
                return True

            normalized_phone = phone.strip()

            if exclude_user_id:
                async with self.pool.acquire() as conn:
                    current_user = await conn.fetchrow(
                        "SELECT phone, alternate_phone FROM users WHERE user_id = $1",
                        exclude_user_id,
                    )
                    if current_user:
                        if normalized_phone in (
                            current_user["phone"],
                            current_user["alternate_phone"],
                        ):
                            return True

            async with self.pool.acquire() as conn:
                if exclude_user_id:
                    row = await conn.fetchrow(
                        """
                        SELECT user_id FROM users
                        WHERE (phone = $1 OR alternate_phone = $1)
                          AND user_id != $2
                        """,
                        normalized_phone,
                        exclude_user_id,
                    )
                else:
                    row = await conn.fetchrow(
                        "SELECT user_id FROM users WHERE (phone = $1 OR alternate_phone = $1)",
                        normalized_phone,
                    )
                return row is None
        except Exception as error:
            print(f"Check phone error: {error}")
            raise

    # =====================================================
    # UPDATE USER PROFILE
    # =====================================================
    async def update_profile(self, user_id: int, profile_data: dict) -> Optional[dict]:
        first_name = profile_data.get("first_name")
        last_name = profile_data.get("last_name")
        middle_name = profile_data.get("middle_name")
        suffix = profile_data.get("suffix")
        gender = profile_data.get("gender")
        phone = profile_data.get("phone")
        alternate_phone = profile_data.get("alternate_phone")
        email = profile_data.get("email")
        region_code = profile_data.get("region_code")
        province_code = profile_data.get("province_code")
        municipality_code = profile_data.get("municipality_code")
        barangay_code = profile_data.get("barangay_code")
        address_line = profile_data.get("address_line")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Update users table
                    # NOTE: updated_at is omitted — the DB trigger auto-updates it on every row change.
                    user_row = await conn.fetchrow(
                        """
                        UPDATE users
                        SET first_name = $1, last_name = $2, middle_name = $3, suffix = $4,
                            gender = $5, phone = $6, alternate_phone = $7,
                            email = COALESCE($8, email)
                        WHERE user_id = $9
                        RETURNING *
                        """,
                        first_name,
                        last_name,
                        middle_name or None,
                        suffix or None,
                        gender or None,
                        phone or None,
                        alternate_phone or None,
                        email or None,
                        user_id,
                    )

                    # Always upsert user_addresses when ANY address field is provided.
                    await conn.execute(
                        """
                        INSERT INTO user_addresses 
                            (user_id, region_code, province_code, municipality_code, barangay_code, address_line)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (user_id) DO UPDATE SET
                            region_code       = EXCLUDED.region_code,
                            province_code     = EXCLUDED.province_code,
                            municipality_code = EXCLUDED.municipality_code,
                            barangay_code     = EXCLUDED.barangay_code,
                            address_line      = EXCLUDED.address_line
                        """,
                        user_id,
                        region_code or None,
                        province_code or None,
                        municipality_code or None,
                        barangay_code or None,
                        address_line or None,
                    )

                    return dict(user_row) if user_row else None
                except Exception as error:
                    print(f"Update profile error: {error}")
                    raise

    # =====================================================
    # GET USER BY ID (with password)
    # =====================================================
    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT user_id, password, status, email_changed_at, password_changed_at
                    FROM users
                    WHERE user_id = $1
                    """,
                    user_id,
                )
                return dict(row) if row else None
        except Exception as error:
            print(f"Get user by ID error: {error}")
            raise

    # =====================================================
    # UPDATE PASSWORD
    # =====================================================
    async def update_password(self, user_id: int, hashed_password: str) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    await conn.execute(
                        """
                        UPDATE users 
                        SET password = $1, failed_login_attempts = 0,
                            lockout_until = NULL, updated_at = NOW() 
                        WHERE user_id = $2
                        """,
                        hashed_password,
                        user_id,
                    )
                    return True
                except Exception as error:
                    print(f"Update password error: {error}")
                    raise

    # =====================================================
    # FIND USER BY USERNAME OR EMAIL
    # =====================================================
    async def find_by_username_or_email(self, username_or_email: str) -> Optional[dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE username = $1 OR email = $1",
                    username_or_email,
                )
                return dict(row) if row else None
        except Exception as error:
            print(f"Find user error: {error}")
            raise

    # =====================================================
    # GET ALL USERS
    # =====================================================
    async def get_all_users(self) -> list[dict]:
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        u.user_id, u.username, u.email, 
                        u.first_name, u.last_name, u.middle_name, u.suffix,
                        u.phone, u.status, u.last_login, u.created_at, u.user_type,
                        u.rank_id,
                        r.role_name AS role,
                        pr.rank_name AS rank,
                        pr.abbreviation AS rank_abbreviation,
                        bd.barangay_code AS assigned_barangay_code,
                        ua.region_code, ua.province_code, ua.municipality_code,
                        ua.barangay_code, ua.address_line
                    FROM users u
                    LEFT JOIN roles r ON u.role_id = r.role_id
                    LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
                    LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                    LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                    ORDER BY u.created_at DESC
                    """
                )
                return [dict(row) for row in rows]
        except Exception as error:
            print(f"Get all users error: {error}")
            raise

    # =====================================================
    # GET USER DETAILS BY ID
    # =====================================================
    async def get_user_details_by_id(self, user_id: int) -> Optional[dict]:
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 
                        u.user_id, u.username, u.email, 
                        u.first_name, u.last_name, u.middle_name, u.suffix,
                        u.phone, u.status, u.last_login, u.created_at, u.user_type,
                        u.rank_id,
                        r.role_name AS role,
                        pr.rank_name AS rank,
                        pr.abbreviation AS rank_abbreviation,
                        bd.barangay_code AS assigned_barangay_code,
                        ua.region_code, ua.province_code, ua.municipality_code,
                        ua.barangay_code, ua.address_line
                    FROM users u
                    LEFT JOIN roles r ON u.role_id = r.role_id
                    LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
                    LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                    LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                    WHERE u.user_id = $1
                    """,
                    user_id,
                )
                return dict(row) if row else None
        except Exception as error:
            print(f"Get user details error: {error}")
            raise

    # =====================================================
    # UPDATE PROFILE PICTURE
    # =====================================================
    async def update_profile_picture(
        self, user_id: int, profile_picture: str
    ) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET profile_picture = $1, updated_at = NOW() WHERE user_id = $2",
                    profile_picture,
                    user_id,
                )
                return True
        except Exception as error:
            print(f"Update profile picture error: {error}")
            raise

    # =====================================================
    # SET email_changed_at (persists 24h cooldown across restarts)
    # =====================================================
    async def update_email_changed_at(self, user_id: int) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET email_changed_at = NOW() WHERE user_id = $1",
                    user_id,
                )
                return True
        except Exception as error:
            print(f"update_email_changed_at error: {error}")
            raise

    # =====================================================
    # SET password_changed_at (persists 24h limit across restarts)
    # =====================================================
    async def update_password_changed_at(self, user_id: int) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET password_changed_at = NOW() WHERE user_id = $1",
                    user_id,
                )
                return True
        except Exception as error:
            print(f"update_password_changed_at error: {error}")
            raise