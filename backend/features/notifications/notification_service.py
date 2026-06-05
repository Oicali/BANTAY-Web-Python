# # ================================================================================
# # FILE: backend/features/notifications/notification_service.py
# # ================================================================================

# import asyncio
# import json
# import os
# import re
# from datetime import date

# import firebase_admin
# from firebase_admin import credentials, messaging

# import config.database as db


# # ── Firebase init ─────────────────────────────────────────────────────────────

# if not firebase_admin._apps:
#     sa_env = os.getenv("FIREBASE_SERVICE_ACCOUNT")
#     if sa_env:
#         print("✅ Firebase init from environment variable")
#         cred = credentials.Certificate(json.loads(sa_env))
#     else:
#         print("⚠️ Firebase init from local file")
#         cred = credentials.Certificate("firebase-service-account.json")
#     firebase_admin.initialize_app(cred)


# def get_pool():
#     if db.pool is None:
#         raise RuntimeError("Database pool is not initialized")
#     return db.pool


# # ── Push notification ─────────────────────────────────────────────────────────

# async def send_push_notification(fcm_token: str, title: str, message: str, link_to: str = None):
#     if not fcm_token:
#         return
#     try:
#         msg = messaging.Message(
#             token=fcm_token,
#             notification=messaging.Notification(title=title, body=message),
#             data={"title": title, "body": message, "linkTo": link_to or ""},
#             apns=messaging.APNSConfig(
#                 payload=messaging.APNSPayload(
#                     aps=messaging.Aps(sound="default", badge=1)
#                 )
#             ),
#         )
#         loop = asyncio.get_event_loop()
#         result = await loop.run_in_executor(None, lambda: messaging.send(msg))
#         print(f"FCM send result: {result}")
#     except Exception as err:
#         print(f"FCM send error: {err}")


# # ── Core notification creator ─────────────────────────────────────────────────

# async def create_notification(
#     recipient_id,
#     sender_id=None,
#     sender_name: str = None,
#     sender_avatar: str = None,
#     type: str = None,
#     title: str = None,
#     message: str = None,
#     link_to: str = None,
# ):
#     try:
#         pool = get_pool()
#         await pool.execute(
#             """
#             INSERT INTO notifications
#               (recipient_user_id, sender_user_id, sender_name, sender_avatar,
#                type, title, message, link_to)
#             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
#             """,
#             recipient_id, sender_id, sender_name, sender_avatar,
#             type, title, message, link_to,
#         )

#         row = await pool.fetchrow(
#             "SELECT push_token FROM users WHERE user_id = $1", recipient_id
#         )
#         push_token = row["push_token"] if row else None
#         if push_token:
#             await send_push_notification(push_token, title, message, link_to)

#     except Exception as err:
#         print(f"create_notification error: {err}")


# # ── Role-based broadcast ──────────────────────────────────────────────────────

# async def notify_all_by_role(roles: list[str], payload: dict, exclude_user_id=None):
#     try:
#         rows = await get_pool().fetch(
#             """
#             SELECT u.user_id FROM users u
#             JOIN roles r ON u.role_id = r.role_id
#             WHERE r.role_name = ANY($1) AND u.status = 'verified'
#             """,
#             roles,
#         )

#         await asyncio.gather(*[
#             create_notification(**payload, recipient_id=row["user_id"])
#             for row in rows
#             if not exclude_user_id or row["user_id"] != exclude_user_id
#         ])

#     except Exception as err:
#         print(f"notify_all_by_role error: {err}")


# # ── Referral responder queries ────────────────────────────────────────────────

# async def get_responder_for_referral(blotter_id):
#     try:
#         row = await get_pool().fetchrow(
#             """
#             SELECT sender_name, sender_user_id, created_at
#             FROM notifications
#             WHERE type = 'REFERRAL_RESPONDED'
#               AND link_to = $1
#             ORDER BY created_at DESC LIMIT 1
#             """,
#             f"/e-blotter?referral={blotter_id}",
#         )
#         return dict(row) if row else None
#     except Exception:
#         return None


# async def get_responders_for_referrals(blotter_ids: list) -> dict:
#     if not blotter_ids:
#         return {}
#     try:
#         links = [f"/e-blotter?referral={bid}" for bid in blotter_ids]
#         rows = await get_pool().fetch(
#             """
#             SELECT DISTINCT ON (n.link_to)
#               n.link_to,
#               n.sender_name,
#               n.sender_user_id,
#               n.created_at,
#               u.first_name,
#               u.last_name,
#               u.profile_picture,
#               pr.abbreviation AS rank_abbreviation
#             FROM notifications n
#             LEFT JOIN users u ON n.sender_user_id = u.user_id
#             LEFT JOIN pnp_ranks pr ON u.rank_id = pr.rank_id
#             WHERE n.type = 'REFERRAL_RESPONDED'
#               AND n.link_to = ANY($1::text[])
#             ORDER BY n.link_to, n.created_at DESC
#             """,
#             links,
#         )

#         result = {}
#         for row in rows:
#             match = re.search(r"referral=(\d+)$", row["link_to"])
#             if match:
#                 result[match.group(1)] = {
#                     "sender_name":       row["sender_name"],
#                     "sender_user_id":    row["sender_user_id"],
#                     "first_name":        row["first_name"],
#                     "last_name":         row["last_name"],
#                     "profile_picture":   row["profile_picture"],
#                     "rank_abbreviation": row["rank_abbreviation"],
#                     "created_at":        row["created_at"],
#                 }
#         return result

#     except Exception as err:
#         print(f"get_responders_for_referrals error: {err}")
#         return {}


# # ── Patrol targeting ──────────────────────────────────────────────────────────

# async def get_patrol_users_for_barangay(barangay: str) -> list:
#     try:
#         today = date.today().isoformat()
#         rows = await get_pool().fetch(
#             """
#             SELECT DISTINCT u.user_id
#             FROM users u
#             JOIN roles r ON u.role_id = r.role_id
#             JOIN active_patroller ap ON ap.officer_id = u.user_id
#             JOIN patrol_assignment_patroller pap ON pap.active_patroller_id = ap.active_patroller_id
#             JOIN patrol_assignment pa ON pa.patrol_id = pap.patrol_id
#             JOIN patrol_assignment_route par ON par.patrol_id = pa.patrol_id
#             WHERE r.role_name = 'Patrol'
#               AND u.status = 'verified'
#               AND pa.start_date <= $1
#               AND pa.end_date >= $1
#               AND par.stop_order <= 0
#               AND UPPER(par.barangay) = UPPER($2)
#             """,
#             today, barangay,
#         )
#         return [r["user_id"] for r in rows]
#     except Exception as err:
#         print(f"get_patrol_users_for_barangay error: {err}")
#         return []


# async def notify_patrols_for_referral(barangay: str, payload: dict, exclude_user_id=None):
#     try:
#         assigned_ids = await get_patrol_users_for_barangay(barangay)

#         if assigned_ids:
#             target_ids = assigned_ids
#         else:
#             rows = await get_pool().fetch(
#                 """
#                 SELECT u.user_id FROM users u
#                 JOIN roles r ON u.role_id = r.role_id
#                 WHERE r.role_name = 'Patrol' AND u.status = 'verified'
#                 """
#             )
#             target_ids = [r["user_id"] for r in rows]

#         await asyncio.gather(*[
#             create_notification(**payload, recipient_id=uid)
#             for uid in target_ids
#             if not exclude_user_id or uid != exclude_user_id
#         ])

#     except Exception as err:
#         print(f"notify_patrols_for_referral error: {err}")