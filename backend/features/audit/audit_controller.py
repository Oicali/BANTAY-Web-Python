# backend/features/audit/audit_controller.py

import math
from flask import request, g, jsonify
from config.database import get_db

RESTRICTED_ROLES = {"Brgy. Captain", "Brgy. Official", "Investigator", "Patrol"}


def get_audit_logs():
    try:
        page   = max(1, int(request.args.get("page",  1)))
        limit  = min(100, int(request.args.get("limit", 15)))
        offset = (page - 1) * limit

        search    = (request.args.get("search")   or "").strip()
        action    = (request.args.get("action")   or "").strip()
        status    = (request.args.get("status")   or "").strip()
        date_from = request.args.get("dateFrom")
        date_to   = request.args.get("dateTo")

        current_user  = g.user
        is_restricted = current_user.get("role") in RESTRICTED_ROLES

        # ── Build WHERE clauses dynamically ──────────────────────────────────
        conditions: list[str] = []
        values:     list      = []

        if is_restricted:
            conditions.append("al.user_id = %s")
            values.append(current_user["user_id"])

        if search:
            conditions.append(
                "(al.username LIKE %s OR al.ip_address LIKE %s "
                "OR al.description LIKE %s OR al.event_name LIKE %s)"
            )
            values.extend([f"%{search}%"] * 4)

        if action and action != "all":
            conditions.append("al.action = %s")
            values.append(action.upper())

        if status and status != "all":
            conditions.append("al.status = %s")
            values.append(status.lower())

        if date_from:
            conditions.append("al.created_at >= %s")
            values.append(date_from)

        if date_to:
            conditions.append("al.created_at < DATE_ADD(%s, INTERVAL 1 DAY)")
            values.append(date_to)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # ── Count query ───────────────────────────────────────────────────────
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM audit_logs al {where}", values)
        total = int(cursor.fetchone()["cnt"])

        # ── Data query ────────────────────────────────────────────────────────
        cursor.execute(
            f"""SELECT
                    al.log_id,
                    al.user_id,
                    al.username,
                    al.event_name,
                    al.description,
                    al.action,
                    al.status,
                    al.source,
                    al.ip_address,
                    al.created_at,
                    u.first_name,
                    u.last_name,
                    u.suffix,
                    r.role_name,
                    pr.abbreviation AS rank_abbr
                FROM audit_logs al
                LEFT JOIN users     u  ON al.user_id = u.user_id
                LEFT JOIN roles     r  ON u.role_id  = r.role_id
                LEFT JOIN pnp_ranks pr ON u.rank_id  = pr.rank_id
                {where}
                ORDER BY al.created_at DESC
                LIMIT %s OFFSET %s""",
            values + [limit, offset],
        )
        data_rows = cursor.fetchall()

        # ── Stats ─────────────────────────────────────────────────────────────
        if is_restricted:
            cursor.execute(
                """SELECT
                       COUNT(*)                                                  AS total,
                       SUM(created_at >= CURDATE())                              AS today,
                       COUNT(DISTINCT user_id)                                   AS unique_users,
                       SUM(status = 'failed')                                    AS failed
                   FROM audit_logs
                   WHERE user_id = %s""",
                (current_user["user_id"],),
            )
        else:
            cursor.execute(
                """SELECT
                       COUNT(*)                                                  AS total,
                       SUM(created_at >= CURDATE())                              AS today,
                       COUNT(DISTINCT user_id)                                   AS unique_users,
                       SUM(status = 'failed')                                    AS failed
                   FROM audit_logs"""
            )
        stats_row = cursor.fetchone()
        cursor.close()

        # ── Shape log rows ────────────────────────────────────────────────────
        logs = []
        for row in data_rows:
            display_name = row.get("username") or ""
            if row.get("first_name"):
                parts = [
                    f"{row['rank_abbr']}." if row.get("rank_abbr") else "",
                    row.get("first_name") or "",
                    row.get("last_name")  or "",
                    row.get("suffix")     or "",
                ]
                full = " ".join(p for p in parts if p)
                display_name = (full[:18] + "…") if len(full) > 18 else full

            row["display_name"] = display_name
            row["role_name"]    = row.get("role_name") or "—"
            # Convert datetime to string for JSON serialization
            if row.get("created_at"):
                row["created_at"] = str(row["created_at"])
            logs.append(row)

        return jsonify({
            "logs": logs,
            "pagination": {
                "total":      total,
                "page":       page,
                "limit":      limit,
                "totalPages": math.ceil(total / limit) if total else 1,
            },
            "stats": {
                "total":       int(stats_row["total"]        or 0),
                "today":       int(stats_row["today"]        or 0),
                "uniqueUsers": int(stats_row["unique_users"] or 0),
                "failed":      int(stats_row["failed"]       or 0),
            },
        }), 200

    except Exception as e:
        print(f"get_audit_logs error: {e}")
        return jsonify({"success": False, "message": "Failed to fetch audit logs"}), 500