# ================================================================================
# FILE: backend/features/audit/audit_controller.py
# ================================================================================

import math
from fastapi import HTTPException, Request

import config.database as db


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


RESTRICTED_ROLES = {"Brgy. Captain", "Brgy. Official", "Investigator", "Patrol"}


async def get_audit_logs(request: Request):
    try:
        params = request.query_params

        page  = max(1, int(params.get("page",  1)))
        limit = min(100, int(params.get("limit", 15)))
        offset = (page - 1) * limit

        search   = (params.get("search")   or "").strip()
        action   = (params.get("action")   or "").strip()
        status   = (params.get("status")   or "").strip()
        date_from = params.get("dateFrom")
        date_to   = params.get("dateTo")

        current_user  = request.state.user
        is_restricted = current_user.get("role") in RESTRICTED_ROLES

        # ── Build WHERE clauses dynamically ──
        conditions: list[str] = []
        values:     list      = []

        def p() -> str:
            """Next positional placeholder."""
            return f"${len(values)}"

        if is_restricted:
            values.append(current_user["user_id"])
            conditions.append(f"al.user_id = {p()}")

        if search:
            values.append(f"%{search}%")
            n = p()
            conditions.append(
                f"(al.username ILIKE {n} OR al.ip_address ILIKE {n} "
                f"OR al.description ILIKE {n} OR al.event_name ILIKE {n})"
            )

        if action and action != "all":
            values.append(action.upper())
            conditions.append(f"al.action = {p()}")

        if status and status != "all":
            values.append(status.lower())
            conditions.append(f"al.status = {p()}")

        if date_from:
            values.append(date_from)
            conditions.append(f"al.created_at >= {p()}::date")

        if date_to:
            values.append(date_to)
            conditions.append(f"al.created_at < ({p()}::date + INTERVAL '1 day')")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        pool = get_pool()

        # ── Count query ──
        count_row = await pool.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM audit_logs al {where}",
            *values,
        )
        total = int(count_row["cnt"])

        # ── Data query ──
        data_rows = await pool.fetch(
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
                LIMIT  ${len(values) + 1}
                OFFSET ${len(values) + 2}""",
            *values, limit, offset,
        )

        # ── Stats ──
        if is_restricted:
            stats_row = await pool.fetchrow(
                """SELECT
                       COUNT(*)                                            AS total,
                       COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today,
                       COUNT(DISTINCT user_id)                            AS unique_users,
                       COUNT(*) FILTER (WHERE status = 'failed')          AS failed
                   FROM audit_logs
                   WHERE user_id = $1""",
                current_user["user_id"],
            )
        else:
            stats_row = await pool.fetchrow(
                """SELECT
                       COUNT(*)                                            AS total,
                       COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today,
                       COUNT(DISTINCT user_id)                            AS unique_users,
                       COUNT(*) FILTER (WHERE status = 'failed')          AS failed
                   FROM audit_logs"""
            )

        # ── Shape log rows ──
        logs = []
        for row in data_rows:
            row = dict(row)
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
            # asyncpg returns datetime objects — keep as-is; FastAPI serialises them
            logs.append(row)

        return {
            "logs": logs,
            "pagination": {
                "total":      total,
                "page":       page,
                "limit":      limit,
                "totalPages": math.ceil(total / limit) if total else 1,
            },
            "stats": {
                "total":       int(stats_row["total"]),
                "today":       int(stats_row["today"]),
                "uniqueUsers": int(stats_row["unique_users"]),
                "failed":      int(stats_row["failed"]),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_audit_logs error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Failed to fetch audit logs"},
        )