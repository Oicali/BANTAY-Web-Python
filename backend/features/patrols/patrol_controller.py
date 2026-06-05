# ================================================================================
# FILE: backend/features/patrols/patrol_controller.py
# ================================================================================

import json
import os
import uuid
from datetime import date, datetime, timedelta
from flask import request, g, jsonify
from config.database import get_db
from shared.utils.audit_logger import log_audit
from shared.utils.geo_utils import get_barangay_or_city_optimized


def get_client_ip() -> str:
    return request.remote_addr or "unknown"


def format_date_only(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        return d[:10]
    return d.strftime("%Y-%m-%d")


def get_date_range(start: str, end: str) -> list[str]:
    dates = []
    cur  = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end,   "%Y-%m-%d").date()
    while cur <= last:
        dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def check_patroller_conflicts(
    cursor, patroller_ids: list, start_date: str, end_date: str, exclude_patrol_id=None
) -> list:
    if not patroller_ids:
        return []
    fmt            = ",".join(["%s"] * len(patroller_ids))
    exclude_clause = "AND pa.patrol_id != %s" if exclude_patrol_id else ""
    params         = patroller_ids + [end_date, start_date]
    if exclude_patrol_id:
        params.append(exclude_patrol_id)
    cursor.execute(
        f"""SELECT
                pap.active_patroller_id,
                TRIM(CONCAT_WS(' ', u.first_name, u.middle_name, u.last_name)) AS officer_name,
                pa.patrol_name,
                pa.start_date,
                pa.end_date
            FROM patrol_assignment_patroller pap
            JOIN patrol_assignment pa ON pap.patrol_id = pa.patrol_id
            JOIN active_patroller  ap ON pap.active_patroller_id = ap.active_patroller_id
            JOIN users             u  ON ap.officer_id = u.user_id
            WHERE pap.active_patroller_id IN ({fmt})
              AND pa.start_date <= %s
              AND pa.end_date   >= %s
              {exclude_clause}
            LIMIT 1""",
        params,
    )
    return cursor.fetchall()


def fmt_date_display(d) -> str:
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()
    return f"{d.strftime('%b')} {d.day}, {d.year}"



_PATROL_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "patrol_reports",
)

_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

_MAX_PHOTOS = 10


def _save_patrol_photo(file, report_id) -> str:
    """Save a patrol photo locally and return its public URL path."""
    os.makedirs(_PATROL_UPLOAD_DIR, exist_ok=True)

    original_filename = file.filename or ""
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "jpg"

    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: .{ext}")

    filename    = f"report_{report_id}_{uuid.uuid4().hex}.{ext}"
    destination = os.path.join(_PATROL_UPLOAD_DIR, filename)
    file.save(destination)
    return f"/uploads/patrol_reports/{filename}"


def _delete_patrol_photo_file(photo_url: str) -> None:
    """Delete a patrol photo from local storage given its URL path."""
    filename    = photo_url.split("/")[-1]
    filepath    = os.path.join(_PATROL_UPLOAD_DIR, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError as e:
            print(f"Failed to delete patrol photo file {filepath}: {e}")


def _serialize_row(r: dict) -> dict:
    """
    Serialize a DB row dict in-place, converting:
      - timedelta  → "HH:MM:SS" string  (MySQL TIME columns)
      - datetime   → str
      - date       → str
    Returns the same dict for convenience.
    """
    for k, v in r.items():
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            r[k] = f"{total // 3600:02}:{(total % 3600) // 60:02}:{total % 60:02}"
        elif isinstance(v, (datetime, date)):
            r[k] = str(v)
    return r

def get_patrol_stats():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT COUNT(*) AS active_patrols_today FROM patrol_assignment "
            "WHERE start_date <= CURDATE() AND end_date >= CURDATE()"
        )
        active = cursor.fetchone()["active_patrols_today"]

        cursor.execute("SELECT COUNT(*) AS mobile_units FROM mobile_unit")
        mobile = cursor.fetchone()["mobile_units"]

        cursor.execute(
            """SELECT COUNT(*) AS total_officers 
               FROM active_patroller ap
               JOIN users u ON ap.officer_id = u.user_id
               WHERE u.role_id = 3"""
        )
        officers = cursor.fetchone()["total_officers"]

        cursor.execute(
            """SELECT COUNT(*) AS unassigned_patrollers FROM active_patroller ap
               JOIN users u ON ap.officer_id = u.user_id
               WHERE u.role_id = 3
               AND ap.active_patroller_id NOT IN (
                   SELECT pap.active_patroller_id FROM patrol_assignment_patroller pap
               )"""
        )
        unassigned = cursor.fetchone()["unassigned_patrollers"]
        cursor.close()

        return jsonify({"success": True, "data": {
            "active_patrols_today": active,
            "mobile_units":         mobile,
            "total_officers":       officers,
            "unassigned_patrollers": unassigned,
        }})
    except Exception as e:
        print(f"get_patrol_stats error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500

def get_active_patrollers():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                ap.active_patroller_id,
                ap.officer_id,
                u.last_login,
                TRIM(CONCAT_WS(' ', u.first_name, u.middle_name, u.last_name)) AS officer_name,
                u.profile_picture,
                ol.latitude,
                ol.longitude,
                ol.location_name  AS last_location_name,
                ol.updated_at     AS last_location_at,
                ol.is_on_duty,
                TIMESTAMPDIFF(SECOND, ol.updated_at, NOW()) AS seconds_ago,
                NULL AS mobile_unit_assigned
            FROM active_patroller ap
            JOIN users u ON ap.officer_id = u.user_id
            LEFT JOIN officer_locations ol ON ap.officer_id = ol.user_id
            WHERE u.role_id = 3
            ORDER BY ap.active_patroller_id
        """)
        rows = cursor.fetchall()
        cursor.close()

        result = []
        for officer in rows:
            location = officer.get("last_location_name")
            if officer.get("latitude") and officer.get("longitude"):
                resolved = get_barangay_or_city_optimized(
                    float(officer["longitude"]), float(officer["latitude"])
                )
                if resolved:
                    location = resolved
                    if resolved != officer.get("last_location_name"):
                        try:
                            upd = db.cursor()
                            upd.execute(
                                "UPDATE officer_locations SET location_name = %s WHERE user_id = %s",
                                (resolved, officer["officer_id"]),
                            )
                            db.commit()
                            upd.close()
                        except Exception as err:
                            print(f"Failed to update location name: {err}")

            last_at   = officer.get("last_location_at")
            is_online = False
            if last_at:
                delta     = (datetime.utcnow() - last_at).total_seconds() * 1000
                is_online = delta <= 30000

            result.append({
                **{k: (str(v) if isinstance(v, (datetime, date)) else v) for k, v in officer.items()},
                "current_barangay":   location,
                "resolved_barangay":  location,
                "last_location_name": location,
                "is_online":          is_online,
            })

        return jsonify({"success": True, "data": result})
    except Exception as e:
        print(f"get_active_patrollers error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500

def get_available_patrollers():
    try:
        start             = request.args.get("start")
        end               = request.args.get("end")
        exclude_patrol_id = request.args.get("exclude_patrol_id")

        db     = get_db()
        cursor = db.cursor(dictionary=True)

        base = """SELECT ap.active_patroller_id, ap.officer_id,
                    TRIM(CONCAT_WS(' ', u.first_name, u.middle_name, u.last_name)) AS officer_name,
                    u.phone AS contact_number, u.profile_picture
                  FROM active_patroller ap
                  JOIN users u ON ap.officer_id = u.user_id
                  WHERE u.role_id = 3"""

        if start and end:
            if exclude_patrol_id:
                cursor.execute(base + """
                    AND ap.active_patroller_id NOT IN (
                        SELECT DISTINCT pap.active_patroller_id
                        FROM patrol_assignment_patroller pap
                        JOIN patrol_assignment pa ON pap.patrol_id = pa.patrol_id
                        WHERE pa.start_date <= %s AND pa.end_date >= %s AND pa.patrol_id != %s
                    ) ORDER BY officer_name ASC""",
                    (end, start, int(exclude_patrol_id)),
                )
            else:
                cursor.execute(base + """
                    AND ap.active_patroller_id NOT IN (
                        SELECT DISTINCT pap.active_patroller_id
                        FROM patrol_assignment_patroller pap
                        JOIN patrol_assignment pa ON pap.patrol_id = pa.patrol_id
                        WHERE pa.start_date <= %s AND pa.end_date >= %s
                    ) ORDER BY officer_name ASC""",
                    (end, start),
                )
        else:
            cursor.execute(base + " ORDER BY officer_name ASC")

        rows = cursor.fetchall()
        cursor.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        print(f"get_available_patrollers error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def get_available_mobile_units():
    try:
        start             = request.args.get("start")
        end               = request.args.get("end")
        exclude_patrol_id = request.args.get("exclude_patrol_id")

        db     = get_db()
        cursor = db.cursor(dictionary=True)

        base = "SELECT mobile_unit_id, mobile_unit_name, vehicle_type, plate_number FROM mobile_unit"

        if start and end:
            if exclude_patrol_id:
                cursor.execute(base + """
                    WHERE mobile_unit_id NOT IN (
                        SELECT mobile_unit_id FROM patrol_assignment
                        WHERE start_date <= %s AND end_date >= %s AND patrol_id != %s
                    ) ORDER BY mobile_unit_name""",
                    (end, start, int(exclude_patrol_id)),
                )
            else:
                cursor.execute(base + """
                    WHERE mobile_unit_id NOT IN (
                        SELECT mobile_unit_id FROM patrol_assignment
                        WHERE start_date <= %s AND end_date >= %s
                    ) ORDER BY mobile_unit_name""",
                    (end, start),
                )
        else:
            cursor.execute(base + " ORDER BY mobile_unit_name")

        rows = cursor.fetchall()
        cursor.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        print(f"get_available_mobile_units error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def get_mobile_units():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT mobile_unit_id, mobile_unit_name, vehicle_type, plate_number, created_at "
            "FROM mobile_unit ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        cursor.close()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        print(f"get_mobile_units error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def create_mobile_unit():
    try:
        body             = request.get_json(silent=True) or {}
        mobile_unit_name = (body.get("mobile_unit_name") or "").strip()
        vehicle_type     = (body.get("vehicle_type")     or "").strip()
        plate_number     = (body.get("plate_number")     or "").strip()
        created_by       = g.user.get("user_id")

        if not mobile_unit_name or not vehicle_type or not plate_number:
            return jsonify({"success": False, "message": "All fields required."}), 400

        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO mobile_unit (mobile_unit_name, vehicle_type, plate_number, created_by) "
            "VALUES (%s, %s, %s, %s)",
            (mobile_unit_name, vehicle_type, plate_number, created_by),
        )
        db.commit()
        cursor.close()

        log_audit(
            user_id=g.user.get("user_id"), username=g.user.get("username"),
            event_name="Mobile Unit Created",
            description=f'Created mobile unit "{mobile_unit_name}" ({vehicle_type} · {plate_number})',
            action="CREATE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Mobile unit created."})
    except Exception as e:
        get_db().rollback()
        if "Duplicate entry" in str(e):
            field = "Plate number" if "plate" in str(e).lower() else "Mobile unit name"
            return jsonify({"success": False, "message": f"{field} already exists."}), 400
        print(f"create_mobile_unit error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def update_mobile_unit(id):
    try:
        body             = request.get_json(silent=True) or {}
        mobile_unit_name = (body.get("mobile_unit_name") or "").strip()
        vehicle_type     = (body.get("vehicle_type")     or "").strip()
        plate_number     = (body.get("plate_number")     or "").strip()

        if not mobile_unit_name or not vehicle_type or not plate_number:
            return jsonify({"success": False, "message": "All fields required."}), 400

        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE mobile_unit SET mobile_unit_name=%s, vehicle_type=%s, plate_number=%s, "
            "updated_at=CURRENT_TIMESTAMP WHERE mobile_unit_id=%s",
            (mobile_unit_name, vehicle_type, plate_number, id),
        )
        db.commit()
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({"success": False, "message": "Not found."}), 404
        cursor.close()

        log_audit(
            user_id=g.user.get("user_id"), username=g.user.get("username"),
            event_name="Mobile Unit Updated",
            description=f'Updated mobile unit ID {id} — "{mobile_unit_name}" ({vehicle_type} · {plate_number})',
            action="UPDATE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Mobile unit updated."})
    except Exception as e:
        if "Duplicate entry" in str(e):
            field = "Plate number" if "plate" in str(e).lower() else "Mobile unit name"
            return jsonify({"success": False, "message": f"{field} already exists."}), 400
        print(f"update_mobile_unit error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def delete_mobile_unit(id):
    try:
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM mobile_unit WHERE mobile_unit_id=%s", (id,))
        db.commit()
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({"success": False, "message": "Not found."}), 404
        cursor.close()

        log_audit(
            user_id=g.user.get("user_id"), username=g.user.get("username"),
            event_name="Mobile Unit Deleted",
            description=f"Deleted mobile unit ID {id}",
            action="DELETE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Mobile unit deleted."})
    except Exception as e:
        print(f"delete_mobile_unit error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def _fetch_patrol_rows(cursor, where_clause: str, params: list) -> list:
    cursor.execute(
        f"""SELECT
                pa.patrol_id, pa.patrol_name, pa.start_date, pa.end_date,
                pa.mobile_unit_id, mu.mobile_unit_name, mu.plate_number
            FROM patrol_assignment pa
            JOIN mobile_unit mu ON pa.mobile_unit_id = mu.mobile_unit_id
            {where_clause}
            ORDER BY pa.start_date DESC, pa.patrol_id DESC""",
        params,
    )
    return cursor.fetchall()


def _enrich_patrols(cursor, patrols: list) -> list:
    if not patrols:
        return []

    from collections import defaultdict

    patrol_ids = [p["patrol_id"] for p in patrols]
    fmt        = ",".join(["%s"] * len(patrol_ids))

    # Patrollers
    cursor.execute(
        f"""SELECT pap.patrol_id, pap.active_patroller_id, ap.officer_id, pap.shift,
                   TRIM(CONCAT_WS(' ', u.first_name, u.middle_name, u.last_name)) AS officer_name,
                   u.phone AS contact_number, u.profile_picture, pap.route_date
            FROM patrol_assignment_patroller pap
            JOIN active_patroller ap ON pap.active_patroller_id = ap.active_patroller_id
            JOIN users u ON ap.officer_id = u.user_id
            WHERE pap.patrol_id IN ({fmt})
            ORDER BY pap.route_date, pap.shift, u.last_name""",
        patrol_ids,
    )
    patroller_rows = cursor.fetchall()

    # Routes
    cursor.execute(
        f"""SELECT patrol_id, route_id, route_date, shift, barangay, notes,
                   time_start, time_end, stop_order
            FROM patrol_assignment_route
            WHERE patrol_id IN ({fmt})
            ORDER BY route_date, shift, stop_order""",
        patrol_ids,
    )
    route_rows = cursor.fetchall()

    patrollers_by_patrol = defaultdict(list)
    detail_by_patrol     = defaultdict(list)
    seen_patroller_shift = defaultdict(set)
    routes_by_patrol     = defaultdict(list)

    for r in patroller_rows:
        pid = r["patrol_id"]
        key = (r["active_patroller_id"], r["shift"])
        if key not in seen_patroller_shift[pid]:
            seen_patroller_shift[pid].add(key)
            patrollers_by_patrol[pid].append({
                "active_patroller_id": r["active_patroller_id"],
                "officer_id":          r["officer_id"],
                "officer_name":        r["officer_name"],
                "contact_number":      r["contact_number"],
                "shift":               r["shift"],
                "profile_picture":     r["profile_picture"],
            })
        detail_by_patrol[pid].append({
            "active_patroller_id": r["active_patroller_id"],
            "officer_id":          r["officer_id"],
            "officer_name":        r["officer_name"],
            "contact_number":      r["contact_number"],
            "profile_picture":     r["profile_picture"],
            "shift":               r["shift"],
            "route_date":          format_date_only(r["route_date"]),
        })

    for r in route_rows:
        routes_by_patrol[r["patrol_id"]].append({
            "route_id":   r["route_id"],
            "route_date": format_date_only(r["route_date"]),
            "shift":      r["shift"],
            "barangay":   r["barangay"],
            "notes":      r["notes"],
            "time_start": str(r["time_start"]) if r.get("time_start") else None,
            "time_end":   str(r["time_end"])   if r.get("time_end")   else None,
            "stop_order": r["stop_order"],
        })

    result = []
    for p in patrols:
        pid = p["patrol_id"]
        result.append({
            **p,
            "start_date":        format_date_only(p["start_date"]),
            "end_date":          format_date_only(p["end_date"]),
            "patrollers":        patrollers_by_patrol[pid],
            "patrollers_detail": detail_by_patrol[pid],
            "routes":            routes_by_patrol[pid],
        })
    return result


def get_patrols():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        patrols = _fetch_patrol_rows(cursor, "", [])
        data    = _enrich_patrols(cursor, patrols)
        cursor.close()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        print(f"get_patrols error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def get_my_patrols():
    user_id = g.user.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        patrols = _fetch_patrol_rows(cursor, """
            WHERE pa.patrol_id IN (
                SELECT DISTINCT pap.patrol_id
                FROM patrol_assignment_patroller pap
                JOIN active_patroller ap ON pap.active_patroller_id = ap.active_patroller_id
                WHERE ap.officer_id = %s
            )""", [user_id])
        data = _enrich_patrols(cursor, patrols)
        cursor.close()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        print(f"get_my_patrols error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def create_patrol():
    body             = request.get_json(silent=True) or {}
    patrol_name      = (body.get("patrol_name")      or "").strip()
    mobile_unit_id   = body.get("mobile_unit_id")
    start_date       = body.get("start_date")
    end_date         = body.get("end_date")
    patroller_ids_am = body.get("patroller_ids_am") or []
    patroller_ids_pm = body.get("patroller_ids_pm") or []
    barangays        = body.get("barangays") or []
    routes           = body.get("routes")   or []
    created_by       = g.user.get("user_id")

    if not patrol_name or not mobile_unit_id or not start_date or not end_date:
        return jsonify({
            "success": False,
            "message": "Patrol name, mobile unit, start and end date are required.",
        }), 400

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        all_ids   = list(set(patroller_ids_am + patroller_ids_pm))
        conflicts = check_patroller_conflicts(cursor, all_ids, start_date, end_date)
        if conflicts:
            c = conflicts[0]
            return jsonify({"success": False, "message": (
                f"{c['officer_name']} is already assigned to \"{c['patrol_name']}\" "
                f"({fmt_date_display(c['start_date'])} – {fmt_date_display(c['end_date'])}) during this period."
            )}), 400

        cursor.execute(
            """SELECT patrol_name, start_date, end_date FROM patrol_assignment
               WHERE mobile_unit_id = %s AND start_date <= %s AND end_date >= %s LIMIT 1""",
            (mobile_unit_id, end_date, start_date),
        )
        mc = cursor.fetchone()
        if mc:
            return jsonify({"success": False, "message": (
                f"This mobile unit is already assigned to \"{mc['patrol_name']}\" "
                f"({fmt_date_display(mc['start_date'])} – {fmt_date_display(mc['end_date'])}) during this period."
            )}), 400

        cursor.execute(
            "INSERT INTO patrol_assignment (patrol_name, mobile_unit_id, start_date, end_date, created_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (patrol_name, mobile_unit_id, start_date, end_date, created_by),
        )
        patrol_id = cursor.lastrowid
        dates     = get_date_range(start_date, end_date)

        for d in dates:
            for pid in patroller_ids_am:
                cursor.execute(
                    "INSERT INTO patrol_assignment_patroller (patrol_id, active_patroller_id, shift, route_date) "
                    "VALUES (%s, %s, 'AM', %s)",
                    (patrol_id, pid, d),
                )
            for pid in patroller_ids_pm:
                cursor.execute(
                    "INSERT INTO patrol_assignment_patroller (patrol_id, active_patroller_id, shift, route_date) "
                    "VALUES (%s, %s, 'PM', %s)",
                    (patrol_id, pid, d),
                )

        for i, bgy in enumerate(barangays):
            cursor.execute(
                "INSERT INTO patrol_assignment_route (patrol_id, route_date, barangay, shift, stop_order) "
                "VALUES (%s, %s, %s, 'AM', %s)",
                (patrol_id, start_date, bgy, -(i + 1)),
            )

        for d in dates:
            for i, task in enumerate(routes):
                cursor.execute(
                    """INSERT INTO patrol_assignment_route
                           (patrol_id, route_date, barangay, shift, time_start, time_end, notes, stop_order)
                       VALUES (%s, %s, NULL, %s, %s, %s, %s, %s)""",
                    (patrol_id, d, task.get("shift"), task.get("time_start"),
                     task.get("time_end"), task.get("notes"), i + 1),
                )

        db.commit()

        log_audit(
            user_id=created_by, username=g.user.get("username"),
            event_name="Patrol Created",
            description=f'Created patrol "{patrol_name}" ({start_date} – {end_date})',
            action="CREATE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        # Notifications
        all_patroller_ids = list(set(patroller_ids_am + patroller_ids_pm))
        if all_patroller_ids:
            fmt_ph = ",".join(["%s"] * len(all_patroller_ids))
            cursor.execute(
                f"SELECT ap.officer_id FROM active_patroller ap "
                f"WHERE ap.active_patroller_id IN ({fmt_ph})",
                all_patroller_ids,
            )
            officer_rows = cursor.fetchall()

        cursor.close()
        return jsonify({"success": True, "message": "Patrol created successfully."})
    except Exception as e:
        db.rollback()
        print(f"create_patrol error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


def update_patrol(id):
    body           = request.get_json(silent=True) or {}
    patrol_name    = (body.get("patrol_name")    or "").strip()
    mobile_unit_id = body.get("mobile_unit_id")
    start_date     = body.get("start_date")
    end_date       = body.get("end_date")
    barangays      = body.get("barangays")

    if not patrol_name or not mobile_unit_id or not start_date or not end_date:
        return jsonify({"success": False, "message": "All required fields must be filled."}), 400

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT patrol_name, start_date, end_date FROM patrol_assignment
               WHERE mobile_unit_id = %s AND start_date <= %s AND end_date >= %s AND patrol_id != %s
               LIMIT 1""",
            (mobile_unit_id, end_date, start_date, id),
        )
        mc = cursor.fetchone()
        if mc:
            cursor.close()
            return jsonify({"success": False, "message": (
                f"This mobile unit is already assigned to \"{mc['patrol_name']}\" "
                f"({fmt_date_display(mc['start_date'])} – {fmt_date_display(mc['end_date'])}) during this period."
            )}), 400

        cursor.execute(
            "SELECT DISTINCT active_patroller_id FROM patrol_assignment_patroller WHERE patrol_id = %s",
            (id,),
        )
        patroller_ids = [r["active_patroller_id"] for r in cursor.fetchall()]
        if patroller_ids:
            conflicts = check_patroller_conflicts(cursor, patroller_ids, start_date, end_date, int(id))
            if conflicts:
                c = conflicts[0]
                cursor.close()
                return jsonify({"success": False, "message": (
                    f"{c['officer_name']} is already assigned to \"{c['patrol_name']}\" "
                    f"({fmt_date_display(c['start_date'])} – {fmt_date_display(c['end_date'])}) during this period."
                )}), 400

        cursor.execute(
            "UPDATE patrol_assignment SET patrol_name=%s, mobile_unit_id=%s, start_date=%s, end_date=%s, "
            "updated_at=CURRENT_TIMESTAMP WHERE patrol_id=%s",
            (patrol_name, mobile_unit_id, start_date, end_date, id),
        )

        if barangays is not None:
            cursor.execute(
                "DELETE FROM patrol_assignment_route WHERE patrol_id=%s AND stop_order <= 0", (id,)
            )
            for i, bgy in enumerate(barangays):
                cursor.execute(
                    "INSERT INTO patrol_assignment_route (patrol_id, route_date, barangay, shift, stop_order) "
                    "VALUES (%s, %s, %s, 'AM', %s)",
                    (id, start_date, bgy, -(i + 1)),
                )

        db.commit()

        log_audit(
            user_id=g.user.get("user_id"), username=g.user.get("username"),
            event_name="Patrol Updated",
            description=f'Updated patrol ID {id} — "{patrol_name}" ({start_date} – {end_date})',
            action="UPDATE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        cursor.close()
        return jsonify({"success": True, "message": "Patrol updated successfully."})
    except Exception as e:
        db.rollback()
        print(f"update_patrol error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

def update_patrollers_for_date(id, date):
    body             = request.get_json(silent=True) or {}
    patroller_ids_am = body.get("patroller_ids_am") or []
    patroller_ids_pm = body.get("patroller_ids_pm") or []

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        all_ids   = list(set(patroller_ids_am + patroller_ids_pm))
        conflicts = check_patroller_conflicts(cursor, all_ids, date, date, int(id))
        if conflicts:
            c = conflicts[0]
            cursor.close()
            return jsonify({"success": False, "message": (
                f"{c['officer_name']} is already assigned to \"{c['patrol_name']}\" "
                f"({fmt_date_display(c['start_date'])} – {fmt_date_display(c['end_date'])}) on this date."
            )}), 400

        cursor.execute(
            "DELETE FROM patrol_assignment_patroller WHERE patrol_id=%s AND route_date=%s", (id, date)
        )
        for pid in patroller_ids_am:
            cursor.execute(
                "INSERT INTO patrol_assignment_patroller (patrol_id, active_patroller_id, shift, route_date) "
                "VALUES (%s, %s, 'AM', %s)",
                (id, pid, date),
            )
        for pid in patroller_ids_pm:
            cursor.execute(
                "INSERT INTO patrol_assignment_patroller (patrol_id, active_patroller_id, shift, route_date) "
                "VALUES (%s, %s, 'PM', %s)",
                (id, pid, date),
            )
        db.commit()
        cursor.close()
        return jsonify({"success": True, "message": "Patrollers updated for date."})
    except Exception as e:
        db.rollback()
        print(f"update_patrollers_for_date error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

def delete_patrol(id):
    try:
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM patrol_assignment WHERE patrol_id=%s", (id,))
        db.commit()
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({"success": False, "message": "Patrol not found."}), 404
        cursor.close()

        log_audit(
            user_id=g.user.get("user_id"), username=g.user.get("username"),
            event_name="Patrol Deleted",
            description=f"Deleted patrol ID {id}",
            action="DELETE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Patrol deleted."})
    except Exception as e:
        print(f"delete_patrol error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def update_route_notes(route_id):
    try:
        body   = request.get_json(silent=True) or {}
        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE patrol_assignment_route SET notes=%s WHERE route_id=%s",
            (body.get("notes"), route_id),
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"update_route_notes error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def update_route_task(route_id):
    try:
        body   = request.get_json(silent=True) or {}
        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE patrol_assignment_route SET time_start=%s, time_end=%s, notes=%s WHERE route_id=%s",
            (body.get("time_start"), body.get("time_end"), body.get("notes"), route_id),
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"update_route_task error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500



def add_route_task():
    try:
        body   = request.get_json(silent=True) or {}
        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO patrol_assignment_route
                   (patrol_id, route_date, barangay, shift, time_start, time_end, notes, stop_order)
               VALUES (%s, %s, NULL, %s, %s, %s, %s, %s)""",
            (
                body.get("patrol_id"), body.get("route_date"), body.get("shift"),
                body.get("time_start"), body.get("time_end"),
                body.get("notes"),     body.get("stop_order"),
            ),
        )
        db.commit()
        route_id = cursor.lastrowid
        cursor.close()
        return jsonify({"success": True, "route_id": route_id})
    except Exception as e:
        print(f"add_route_task error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500



def remove_route_task(route_id):
    try:
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM patrol_assignment_route WHERE route_id=%s", (route_id,))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"remove_route_task error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def submit_after_patrol_report(id):
    patrol_id = id
    user_id   = g.user.get("user_id")
    user_role = g.user.get("role")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    body      = request.get_json(silent=True) or {}
    date      = body.get("date")
    shift     = body.get("shift")
    time_from = body.get("timeFrom")
    time_to   = body.get("timeTo")

    if not date:
        return jsonify({"success": False, "message": "Patrol date is required."}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        if user_role in ("Administrator", "Technical Administrator"):
            if shift:
                cursor.execute(
                    "SELECT report_id, submitted_by, shift FROM after_patrol_reports "
                    "WHERE patrol_id=%s AND patrol_date=%s AND shift=%s LIMIT 1",
                    (patrol_id, date, shift),
                )
            else:
                cursor.execute(
                    "SELECT report_id, submitted_by, shift FROM after_patrol_reports "
                    "WHERE patrol_id=%s AND patrol_date=%s LIMIT 1",
                    (patrol_id, date),
                )
            existing = cursor.fetchone()
            if not existing:
                cursor.close()
                return jsonify({
                    "success": False,
                    "message": "Administrators can only edit existing reports, not create new ones.",
                }), 403
            active_patroller_id = existing["submitted_by"]
            shift               = existing["shift"]
        else:
            cursor.execute(
                "SELECT active_patroller_id FROM active_patroller WHERE officer_id=%s LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                cursor.close()
                return jsonify({"success": False, "message": "You are not registered as an active patroller."}), 403
            active_patroller_id = row["active_patroller_id"]

            cursor.execute(
                "SELECT 1 FROM patrol_assignment_patroller WHERE patrol_id=%s AND active_patroller_id=%s LIMIT 1",
                (patrol_id, active_patroller_id),
            )
            if not cursor.fetchone():
                cursor.close()
                return jsonify({"success": False, "message": "You are not assigned to this patrol."}), 403

            if shift and shift != "AM & PM":
                cursor.execute(
                    "SELECT 1 FROM patrol_assignment_patroller "
                    "WHERE patrol_id=%s AND active_patroller_id=%s AND shift=%s LIMIT 1",
                    (patrol_id, active_patroller_id, shift),
                )
                if not cursor.fetchone():
                    cursor.close()
                    return jsonify({
                        "success": False,
                        "message": f"You are not assigned to the {shift} shift for this patrol.",
                    }), 403

        cursor.execute(
            "SELECT start_date, end_date FROM patrol_assignment WHERE patrol_id=%s", (patrol_id,)
        )
        pd = cursor.fetchone()
        if pd:
            sd = format_date_only(pd["start_date"])
            ed = format_date_only(pd["end_date"])
            if date < sd or date > ed:
                cursor.close()
                return jsonify({
                    "success": False,
                    "message": f"Report date must be within the patrol duration ({sd} – {ed}).",
                }), 400

        cursor.execute(
            """INSERT INTO after_patrol_reports (
                patrol_id, submitted_by, shift, patrol_date, time_from, time_to,
                pre_deployment, action_pre_deployment, incidents, action_incidents,
                safety_concerns, action_safety, other_services, visited_areas,
                persons_visited, num_officials, num_govt_officials,
                sector_beat, must_dos, credit_hours, remarks,
                sig_officer_1, sig_officer_2, sig_supervisor
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                submitted_by=VALUES(submitted_by), time_from=VALUES(time_from), time_to=VALUES(time_to),
                pre_deployment=VALUES(pre_deployment), action_pre_deployment=VALUES(action_pre_deployment),
                incidents=VALUES(incidents), action_incidents=VALUES(action_incidents),
                safety_concerns=VALUES(safety_concerns), action_safety=VALUES(action_safety),
                other_services=VALUES(other_services), visited_areas=VALUES(visited_areas),
                persons_visited=VALUES(persons_visited), num_officials=VALUES(num_officials),
                num_govt_officials=VALUES(num_govt_officials), sector_beat=VALUES(sector_beat),
                must_dos=VALUES(must_dos), credit_hours=VALUES(credit_hours), remarks=VALUES(remarks),
                sig_officer_1=VALUES(sig_officer_1), sig_officer_2=VALUES(sig_officer_2),
                sig_supervisor=VALUES(sig_supervisor), updated_at=NOW()""",
            (
                patrol_id, active_patroller_id, shift, date, time_from, time_to,
                body.get("preDeployment"), body.get("action1"),
                body.get("incidents"),     body.get("action2"),
                body.get("safetyConcerns"), body.get("action3"),
                body.get("otherServices"), body.get("visitedAreas"),
                body.get("personsVisited"),
                int(body["numOfficials"]) if body.get("numOfficials") is not None else None,
                int(body["numGovt"])      if body.get("numGovt")      is not None else None,
                body.get("sector"),  body.get("mustDos"),   body.get("creditHours"),
                body.get("remarks"), body.get("sigOfficer1"), body.get("sigOfficer2"),
                body.get("sigSupervisor"),
            ),
        )
        db.commit()
        report_id = cursor.lastrowid
        cursor.close()

        log_audit(
            user_id=user_id, username=g.user.get("username"),
            event_name="After Patrol Report Submitted",
            description=f"Submitted after patrol report for patrol ID {patrol_id} — {date} {shift or ''}".strip(),
            action="CREATE", status="success",
            source="Web Portal" if user_role == "Administrator" else "Mobile App",
            ip_address=get_client_ip(),
        )

        return jsonify({
            "success": True,
            "message": "After Patrol Report submitted successfully.",
            "report_id": report_id,
        })
    except Exception as e:
        print(f"submit_after_patrol_report error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


def get_after_patrol_reports(id):
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """SELECT apr.*,
                   TRIM(CONCAT_WS(' ', u.first_name, u.middle_name, u.last_name)) AS submitted_by_name,
                   u.phone AS submitted_by_contact
               FROM after_patrol_reports apr
               JOIN active_patroller ap ON apr.submitted_by = ap.active_patroller_id
               JOIN users u ON ap.officer_id = u.user_id
               WHERE apr.patrol_id = %s
               ORDER BY apr.patrol_date DESC, apr.submitted_at DESC""",
            (id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        for r in rows:
            r["patrol_date"] = format_date_only(r.get("patrol_date"))
            if isinstance(r.get("photo_urls"), str):
                try:
                    r["photo_urls"] = json.loads(r["photo_urls"])
                except Exception:
                    r["photo_urls"] = []
            # ── FIX: serialize timedelta (TIME columns) as well as date/datetime ──
            for k, v in r.items():
                if isinstance(v, timedelta):
                    total = int(v.total_seconds())
                    r[k] = f"{total // 3600:02}:{(total % 3600) // 60:02}:{total % 60:02}"
                elif isinstance(v, (datetime, date)):
                    r[k] = str(v)
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        print(f"get_after_patrol_reports error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def get_my_after_patrol_reports(id):
    user_id = g.user.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """SELECT apr.* FROM after_patrol_reports apr
               WHERE apr.patrol_id = %s
                 AND (
                   apr.shift IN (
                       SELECT DISTINCT pap.shift
                       FROM patrol_assignment_patroller pap
                       JOIN active_patroller ap ON pap.active_patroller_id = ap.active_patroller_id
                       WHERE pap.patrol_id = %s AND ap.officer_id = %s AND pap.shift IS NOT NULL
                   )
                   OR apr.submitted_by IN (
                       SELECT active_patroller_id FROM active_patroller WHERE officer_id = %s
                   )
                 )
               ORDER BY apr.patrol_date ASC""",
            (id, id, user_id, user_id),
        )
        rows = cursor.fetchall()
        cursor.close()
        for r in rows:
            r["patrol_date"] = format_date_only(r.get("patrol_date"))
            if isinstance(r.get("photo_urls"), str):
                try:
                    r["photo_urls"] = json.loads(r["photo_urls"])
                except Exception:
                    r["photo_urls"] = []
            # ── FIX: serialize timedelta (TIME columns) as well as date/datetime ──
            for k, v in r.items():
                if isinstance(v, timedelta):
                    total = int(v.total_seconds())
                    r[k] = f"{total // 3600:02}:{(total % 3600) // 60:02}:{total % 60:02}"
                elif isinstance(v, (datetime, date)):
                    r[k] = str(v)
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        print(f"get_my_after_patrol_reports error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def delete_after_patrol_report(report_id):
    user_id   = g.user.get("user_id")
    user_role = g.user.get("role")
    try:
        db     = get_db()
        cursor = db.cursor()
        if user_role in ("Administrator", "Technical Administrator"):
            cursor.execute(
                "DELETE FROM after_patrol_reports WHERE report_id=%s", (report_id,)
            )
        else:
            cursor.execute(
                """DELETE apr FROM after_patrol_reports apr
                   WHERE apr.report_id = %s
                     AND (
                       apr.shift IN (
                           SELECT DISTINCT pap.shift
                           FROM patrol_assignment_patroller pap
                           JOIN active_patroller ap2 ON pap.active_patroller_id = ap2.active_patroller_id
                           WHERE pap.patrol_id = apr.patrol_id AND ap2.officer_id = %s
                       )
                       OR apr.submitted_by IN (
                           SELECT active_patroller_id FROM active_patroller WHERE officer_id = %s
                       )
                     )""",
                (report_id, user_id, user_id),
            )
        db.commit()
        if cursor.rowcount == 0:
            cursor.close()
            return jsonify({
                "success": False,
                "message": "Report not found or you do not have permission to delete it.",
            }), 404
        cursor.close()

        log_audit(
            user_id=user_id, username=g.user.get("username"),
            event_name="After Patrol Report Deleted",
            description=f"Deleted after patrol report ID {report_id}",
            action="DELETE", status="success", source="Web Portal", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Report deleted successfully."})
    except Exception as e:
        print(f"delete_after_patrol_report error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def update_officer_location():
    user_id = g.user.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    body      = request.get_json(silent=True) or {}
    latitude  = body.get("latitude")
    longitude = body.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({"success": False, "message": "latitude and longitude are required."}), 400

    try:
        db     = get_db()
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO officer_locations (user_id, latitude, longitude, location_name, updated_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON DUPLICATE KEY UPDATE
                   latitude=VALUES(latitude), longitude=VALUES(longitude),
                   location_name=VALUES(location_name), updated_at=NOW()""",
            (user_id, latitude, longitude, body.get("location_name")),
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"update_officer_location error: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500


def upload_after_patrol_photos(report_id):
    user_id = g.user.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    files = request.files.getlist("photos")
    if not files:
        return jsonify({"success": False, "message": "No images provided."}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT photo_urls FROM after_patrol_reports WHERE report_id=%s", (report_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return jsonify({"success": False, "message": "Report not found."}), 404

        existing = (
            json.loads(row["photo_urls"])
            if isinstance(row["photo_urls"], str)
            else (row["photo_urls"] or [])
        )

        if len(existing) >= _MAX_PHOTOS:
            cursor.close()
            return jsonify({
                "success": False,
                "message": f"Maximum of {_MAX_PHOTOS} photos allowed per report.",
            }), 400

        uploaded_urls = []
        for f in files:
            url = _save_patrol_photo(f, report_id)
            uploaded_urls.append(url)

        merged = (existing + uploaded_urls)[:_MAX_PHOTOS]

        cursor.execute(
            "UPDATE after_patrol_reports SET photo_urls=%s WHERE report_id=%s",
            (json.dumps(merged), report_id),
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True, "message": "Photos uploaded successfully.", "photo_urls": merged})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        print(f"upload_after_patrol_photos error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500


def delete_after_patrol_photo(report_id):
    user_id = g.user.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    body      = request.get_json(silent=True) or {}
    photo_url = body.get("photo_url")
    if not photo_url:
        return jsonify({"success": False, "message": "photo_url is required."}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT photo_urls FROM after_patrol_reports WHERE report_id=%s", (report_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return jsonify({"success": False, "message": "Report not found."}), 404

        existing = (
            json.loads(row["photo_urls"])
            if isinstance(row["photo_urls"], str)
            else (row["photo_urls"] or [])
        )
        updated = [u for u in existing if u != photo_url]

        _delete_patrol_photo_file(photo_url)

        cursor.execute(
            "UPDATE after_patrol_reports SET photo_urls=%s WHERE report_id=%s",
            (json.dumps(updated), report_id),
        )
        db.commit()
        cursor.close()

        log_audit(
            user_id=user_id, username=g.user.get("username"),
            event_name="Patrol Photo Deleted",
            description=f"Deleted photo from report ID {report_id}",
            action="DELETE", status="success", source="Mobile App", ip_address=get_client_ip(),
        )

        return jsonify({"success": True, "message": "Photo deleted.", "photo_urls": updated})
    except Exception as e:
        print(f"delete_after_patrol_photo error: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500