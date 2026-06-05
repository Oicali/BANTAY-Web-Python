# # ================================================================================
# # FILE: backend/features/notifications/notification_routes.py
# # ================================================================================

# from fastapi import APIRouter, HTTPException, Request

# import config.database as db
# from shared.middleware.token_middleware import authenticate

# router = APIRouter()


# def get_pool():
#     if db.pool is None:
#         raise RuntimeError("Database pool is not initialized")
#     return db.pool


# @router.patch("/read-all")
# async def read_all(request: Request):
#     try:
#         user_id = request.state.user["user_id"]
#         await get_pool().execute(
#             "UPDATE notifications SET is_read = TRUE WHERE recipient_user_id = $1",
#             user_id,
#         )
#         return {"success": True}
#     except Exception as err:
#         raise HTTPException(status_code=500, detail={"success": False, "message": str(err)})


# @router.get("/")
# async def get_notifications(request: Request):
#     try:
#         user_id = request.state.user["user_id"]
#         rows = await get_pool().fetch(
#             """
#             SELECT
#               n.id, n.sender_name, n.type, n.title, n.message,
#               n.link_to, n.is_read, n.created_at,
#               u.profile_picture AS sender_avatar
#             FROM notifications n
#             LEFT JOIN users u ON n.sender_user_id = u.user_id
#             WHERE n.recipient_user_id = $1
#             ORDER BY n.created_at DESC
#             LIMIT 50
#             """,
#             user_id,
#         )
#         data   = [dict(r) for r in rows]
#         unread = sum(1 for n in data if not n["is_read"])
#         return {"success": True, "data": data, "unread": unread}
#     except Exception as err:
#         raise HTTPException(status_code=500, detail={"success": False, "message": str(err)})


# @router.patch("/{notification_id}/read")
# async def mark_read(notification_id: int, request: Request):
#     try:
#         user_id = request.state.user["user_id"]
#         await get_pool().execute(
#             "UPDATE notifications SET is_read = TRUE WHERE id = $1 AND recipient_user_id = $2",
#             notification_id, user_id,
#         )
#         return {"success": True}
#     except Exception as err:
#         raise HTTPException(status_code=500, detail={"success": False, "message": str(err)})


# @router.post("/push-token")
# async def save_push_token(request: Request):
#     try:
#         user_id = request.state.user["user_id"]
#         body    = await request.json()
#         await get_pool().execute(
#             "UPDATE users SET push_token = $1 WHERE user_id = $2",
#             body.get("push_token"), user_id,
#         )
#         return {"success": True}
#     except Exception as err:
#         raise HTTPException(status_code=500, detail={"success": False, "message": str(err)})