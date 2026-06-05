# ================================================================================
# FILE: backend/features/user/user.py
# ================================================================================

from typing import Optional


class User:
    def __init__(self, pool):
        """
        pool: a mysql.connector.pooling.MySQLConnectionPool instance.
              Obtain one via pooling.MySQLConnectionPool(...) in config/database.py.
        """
        self.pool = pool

    # ── internal helpers ──────────────────────────────────────────────────────

    def _conn(self):
        """Get a connection from the pool."""
        return self.pool.get_connection()

    # =====================================================
    # GET CURRENT USER PROFILE
    # =====================================================
    def get_profile(self, user_id: int) -> Optional[dict]:
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    u.user_id, u.username, u.email,
                    u.first_name, u.last_name, u.middle_name, u.suffix,
                    u.phone, u.alternate_phone,
                    u.gender,
                    DATE_FORMAT(u.date_of_birth, '%%Y-%%m-%%d') AS date_of_birth,
                    u.profile_picture, u.user_type, u.status, u.created_at,
                    u.rank_id,
                    r.role_name  AS role,
                    pr.rank_name AS `rank`,
                    pr.abbreviation AS rank_abbreviation,
                    ua.region_code, ua.province_code,
                    ua.municipality_code, ua.barangay_code,
                    ua.address_line,
                    bd.barangay_code AS assigned_barangay_code
                FROM users u
                LEFT JOIN roles r          ON u.role_id = r.role_id
                LEFT JOIN pnp_ranks pr     ON u.rank_id = pr.rank_id
                LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                WHERE u.user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
        except Exception as error:
            print(f"Get profile error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # CHECK PHONE AVAILABILITY
    # =====================================================
    def check_phone_availability(
        self, phone: str, exclude_user_id: Optional[int] = None
    ) -> bool:
        if not phone or phone.strip() == "":
            return True

        normalized_phone = phone.strip()
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)

            if exclude_user_id:
                cursor.execute(
                    "SELECT phone, alternate_phone FROM users WHERE user_id = %s",
                    (exclude_user_id,),
                )
                current_user = cursor.fetchone()
                if current_user and normalized_phone in (
                    current_user["phone"],
                    current_user["alternate_phone"],
                ):
                    cursor.close()
                    return True

            if exclude_user_id:
                cursor.execute(
                    """
                    SELECT user_id FROM users
                    WHERE (phone = %s OR alternate_phone = %s)
                      AND user_id != %s
                    """,
                    (normalized_phone, normalized_phone, exclude_user_id),
                )
            else:
                cursor.execute(
                    "SELECT user_id FROM users WHERE phone = %s OR alternate_phone = %s",
                    (normalized_phone, normalized_phone),
                )

            result = cursor.fetchone()
            cursor.close()
            return result is None
        except Exception as error:
            print(f"Check phone error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # UPDATE USER PROFILE
    # =====================================================
    def update_profile(self, user_id: int, profile_data: dict) -> Optional[dict]:
        first_name        = profile_data.get("first_name")
        last_name         = profile_data.get("last_name")
        middle_name       = profile_data.get("middle_name")
        suffix            = profile_data.get("suffix")
        gender            = profile_data.get("gender")
        phone             = profile_data.get("phone")
        alternate_phone   = profile_data.get("alternate_phone")
        email             = profile_data.get("email")
        region_code       = profile_data.get("region_code")
        province_code     = profile_data.get("province_code")
        municipality_code = profile_data.get("municipality_code")
        barangay_code     = profile_data.get("barangay_code")
        address_line      = profile_data.get("address_line")

        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)

            # Update users table (MySQL has no RETURNING — fetch separately)
            cursor.execute(
                """
                UPDATE users
                SET first_name      = %s,
                    last_name       = %s,
                    middle_name     = %s,
                    suffix          = %s,
                    gender          = %s,
                    phone           = %s,
                    alternate_phone = %s,
                    email           = COALESCE(%s, email)
                WHERE user_id = %s
                """,
                (
                    first_name,
                    last_name,
                    middle_name or None,
                    suffix or None,
                    gender or None,
                    phone or None,
                    alternate_phone or None,
                    email or None,
                    user_id,
                ),
            )

            # Upsert address — MySQL syntax
            cursor.execute(
                """
                INSERT INTO user_addresses
                    (user_id, region_code, province_code, municipality_code, barangay_code, address_line)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    region_code       = VALUES(region_code),
                    province_code     = VALUES(province_code),
                    municipality_code = VALUES(municipality_code),
                    barangay_code     = VALUES(barangay_code),
                    address_line      = VALUES(address_line)
                """,
                (
                    user_id,
                    region_code or None,
                    province_code or None,
                    municipality_code or None,
                    barangay_code or None,
                    address_line or None,
                ),
            )

            conn.commit()

            # Fetch the updated row (replaces RETURNING *)
            cursor.execute(
                "SELECT * FROM users WHERE user_id = %s",
                (user_id,),
            )
            user_row = cursor.fetchone()
            cursor.close()
            return dict(user_row) if user_row else None

        except Exception as error:
            conn.rollback()
            print(f"Update profile error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # GET USER BY ID (with password)
    # =====================================================
    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT user_id, password, status, email_changed_at, password_changed_at
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
        except Exception as error:
            print(f"Get user by ID error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # UPDATE PASSWORD
    # =====================================================
    def update_password(self, user_id: int, hashed_password: str) -> bool:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET password               = %s,
                    failed_login_attempts  = 0,
                    lockout_until          = NULL,
                    updated_at             = NOW()
                WHERE user_id = %s
                """,
                (hashed_password, user_id),
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as error:
            conn.rollback()
            print(f"Update password error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # FIND USER BY USERNAME OR EMAIL
    # =====================================================
    def find_by_username_or_email(self, username_or_email: str) -> Optional[dict]:
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM users WHERE username = %s OR email = %s",
                (username_or_email, username_or_email),
            )
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
        except Exception as error:
            print(f"Find user error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # GET ALL USERS
    # =====================================================
    def get_all_users(self) -> list[dict]:
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    u.user_id, u.username, u.email,
                    u.first_name, u.last_name, u.middle_name, u.suffix,
                    u.phone, u.status, u.last_login, u.created_at, u.user_type,
                    u.rank_id,
                    r.role_name  AS role,
                    pr.rank_name AS `rank`,
                    pr.abbreviation AS rank_abbreviation,
                    bd.barangay_code AS assigned_barangay_code,
                    ua.region_code, ua.province_code, ua.municipality_code,
                    ua.barangay_code, ua.address_line
                FROM users u
                LEFT JOIN roles r           ON u.role_id = r.role_id
                LEFT JOIN pnp_ranks pr      ON u.rank_id = pr.rank_id
                LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                ORDER BY u.created_at DESC
                """
            )
            rows = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in rows]
        except Exception as error:
            print(f"Get all users error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # GET USER DETAILS BY ID
    # =====================================================
    def get_user_details_by_id(self, user_id: int) -> Optional[dict]:
        conn = self._conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    u.user_id, u.username, u.email,
                    u.first_name, u.last_name, u.middle_name, u.suffix,
                    u.phone, u.status, u.last_login, u.created_at, u.user_type,
                    u.rank_id,
                    r.role_name  AS role,
                    pr.rank_name AS `rank`,
                    pr.abbreviation AS rank_abbreviation,
                    bd.barangay_code AS assigned_barangay_code,
                    ua.region_code, ua.province_code, ua.municipality_code,
                    ua.barangay_code, ua.address_line
                FROM users u
                LEFT JOIN roles r           ON u.role_id = r.role_id
                LEFT JOIN pnp_ranks pr      ON u.rank_id = pr.rank_id
                LEFT JOIN user_addresses ua ON u.user_id = ua.user_id
                LEFT JOIN barangay_details bd ON u.user_id = bd.user_id
                WHERE u.user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            return dict(row) if row else None
        except Exception as error:
            print(f"Get user details error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # UPDATE PROFILE PICTURE
    # =====================================================
    def update_profile_picture(self, user_id: int, profile_picture: str) -> bool:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET profile_picture = %s, updated_at = NOW() WHERE user_id = %s",
                (profile_picture, user_id),
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as error:
            conn.rollback()
            print(f"Update profile picture error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # SET email_changed_at
    # =====================================================
    def update_email_changed_at(self, user_id: int) -> bool:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET email_changed_at = NOW() WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as error:
            conn.rollback()
            print(f"update_email_changed_at error: {error}")
            raise
        finally:
            conn.close()

    # =====================================================
    # SET password_changed_at
    # =====================================================
    def update_password_changed_at(self, user_id: int) -> bool:
        conn = self._conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_changed_at = NOW() WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()
            cursor.close()
            return True
        except Exception as error:
            conn.rollback()
            print(f"update_password_changed_at error: {error}")
            raise
        finally:
            conn.close()