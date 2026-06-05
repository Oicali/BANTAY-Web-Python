# ================================================================================
# FILE: backend/features/modus/modus_controller.py
# ================================================================================

from flask import request, g, jsonify
from shared.utils.audit_logger import log_audit
from config.database import get_db

INDEX_CRIMES = {
    "MURDER",
    "HOMICIDE",
    "PHYSICAL INJURIES",
    "RAPE",
    "ROBBERY",
    "THEFT",
    "CARNAPPING - MC",
    "CARNAPPING - MV",
    "SPECIAL COMPLEX CRIME",
}


def get_client_ip() -> str:
    return request.remote_addr or "unknown"


def get_all_modus():
    try:
        sort_by = request.args.get("sort_by", "")

        if sort_by == "created_at":
            order_by = "created_at DESC"
        elif sort_by == "created_at_asc":
            order_by = "created_at ASC"
        else:
            order_by = "crime_type, modus_name"

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM crime_modus_reference ORDER BY {order_by}")
        rows = cursor.fetchall()
        cursor.close()

        return jsonify({"success": True, "data": rows})

    except Exception as e:
        print(f"get_all_modus error: {e}")
        return jsonify({"success": False, "message": "Failed to fetch modus list"}), 500

def get_modus_by_id(id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM crime_modus_reference WHERE id = %s",
            (int(id),),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return jsonify({"success": False, "message": "Not found"}), 404

        return jsonify({"success": True, "data": row})

    except Exception as e:
        print(f"get_modus_by_id error: {e}")
        return jsonify({"success": False, "message": "Failed to fetch modus"}), 500


def create_modus():
    current_user = g.user

    try:
        body        = request.get_json(silent=True) or {}
        crime_type  = (body.get("crime_type")  or "").strip()
        modus_name  = (body.get("modus_name")  or "").strip()
        description = (body.get("description") or "").strip() or None

        if not crime_type or not modus_name:
            return jsonify({"success": False, "message": "crime_type and modus_name are required"}), 400

        if crime_type.upper() not in INDEX_CRIMES:
            return jsonify({"success": False, "message": "Invalid crime type"}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """SELECT id FROM crime_modus_reference
               WHERE UPPER(crime_type) = %s AND LOWER(modus_name) = LOWER(%s)""",
            (crime_type.upper(), modus_name),
        )
        if cursor.fetchone():
            cursor.close()
            return jsonify({"success": False, "message": "Modus already exists for this crime type"}), 400

        cursor.execute(
            """INSERT INTO crime_modus_reference (crime_type, modus_name, description, is_active)
               VALUES (%s, %s, %s, TRUE)""",
            (crime_type.upper(), modus_name, description),
        )
        db.commit()
        new_id = cursor.lastrowid

        cursor.execute("SELECT * FROM crime_modus_reference WHERE id = %s", (new_id,))
        row = cursor.fetchone()
        cursor.close()

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name="Modus Created",
            description=f'Created modus "{modus_name}" for {crime_type.upper()}',
            action="CREATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "data": row}), 201

    except Exception as e:
        print(f"create_modus error: {e}")
        return jsonify({"success": False, "message": "Failed to create modus"}), 500


def update_modus(id):
    current_user = g.user

    try:
        body        = request.get_json(silent=True) or {}
        crime_type  = body.get("crime_type")
        modus_name  = body.get("modus_name")
        description = body.get("description")
        is_active   = body.get("is_active")

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """UPDATE crime_modus_reference
               SET
                 crime_type  = COALESCE(%s, crime_type),
                 modus_name  = COALESCE(%s, modus_name),
                 description = COALESCE(%s, description),
                 is_active   = COALESCE(%s, is_active),
                 updated_at  = NOW()
               WHERE id = %s""",
            (
                crime_type.upper() if crime_type else None,
                modus_name or None,
                description if description is not None else None,
                is_active   if is_active   is not None else None,
                int(id),
            ),
        )
        db.commit()

        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({"success": False, "message": "Not found"}), 404

        cursor.execute("SELECT * FROM crime_modus_reference WHERE id = %s", (int(id),))
        updated = cursor.fetchone()
        cursor.close()

        if is_active is False:
            event_name = "Modus Deactivated"
        elif is_active is True:
            event_name = "Modus Restored"
        else:
            event_name = "Modus Updated"

        log_audit(
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            event_name=event_name,
            description=f"Changes made with Modus ID {updated['id']}: {updated['modus_name']} ({updated['crime_type']})",
            action="UPDATE",
            status="success",
            source="Web Portal",
            ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "data": updated})

    except Exception as e:
        print(f"update_modus error: {e}")
        return jsonify({"success": False, "message": "Failed to update modus"}), 500