# backend\features\dashboard\crime_dashboard_controller.py

from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
import config.database as db

# ── Constants ─────────────────────────────────────────────────────────────────
INDEX_CRIMES = [
    "MURDER",
    "HOMICIDE",
    "PHYSICAL INJURY",
    "RAPE",
    "ROBBERY",
    "THEFT",
    "CARNAPPING - MC",
    "CARNAPPING - MV",
    "SPECIAL COMPLEX CRIME",
]

DAYS_OF_WEEK = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

# ── Barangay alias map ────────────────────────────────────────────────────────
BARANGAY_ALIASES: dict[str, str] = {
    "ALIMA":        "SINEGUELASAN",
    "BANALO":       "SINEGUELASAN",
    "CAMPOSANTO":   "KAINGIN (POB.)",
    "DAANG BUKID":  "KAINGIN (POB.)",
    "TABING DAGAT": "KAINGIN (POB.)",
    "KAINGIN":      "KAINGIN DIGMAN",
    "DIGMAN":       "KAINGIN DIGMAN",
    "PANAPAAN":     "P.F. ESPIRITU I (PANAPAAN)",
    "PANAPAAN 2":   "P.F. ESPIRITU II",
    "PANAPAAN 4":   "P.F. ESPIRITU IV",
    "PANAPAAN 5":   "P.F. ESPIRITU V",
    "PANAPAAN 6":   "P.F. ESPIRITU VI",
    "MABOLO 1":     "MABOLO",
    "MABOLO 2":     "MABOLO",
    "MABOLO 3":     "MABOLO",
    "ANIBAN 3":     "ANIBAN I",
    "ANIBAN 4":     "ANIBAN II",
    "ANIBAN 5":     "ANIBAN I",
    "MALIKSI 3":    "MALIKSI II",
    "MAMBOG 5":     "MAMBOG II",
    "NIOG 2":       "NIOG",
    "NIOG 3":       "NIOG",
    "REAL 2":       "REAL",
    "SALINAS 3":    "SALINAS II",
    "SALINAS 4":    "SALINAS II",
    "TALABA 4":     "TALABA III",
    "TALABA 7":     "TALABA I",
}

# Build reverse map: current_name -> [legacy_names]
REVERSE_ALIASES: dict[str, list[str]] = {}
for legacy, current in BARANGAY_ALIASES.items():
    REVERSE_ALIASES.setdefault(current, []).append(legacy)


def expand_barangays(names: list[str]) -> list[str]:
    expanded = set(names)
    for name in names:
        for alias in REVERSE_ALIASES.get(name, []):
            expanded.add(alias)
    return list(expanded)


# ── Shared WHERE builder ──────────────────────────────────────────────────────
def build_where(query: dict) -> tuple[str, list, int]:
    """
    Returns (where_clause, params_list, next_param_index).
    asyncpg uses $1, $2, ... positional params.
    """
    date_from   = query.get("date_from")
    date_to     = query.get("date_to")
    crime_types = query.get("crime_types")
    barangays   = query.get("barangays")

    conditions: list[str] = []
    params:     list      = []
    p = 1

    if date_from:
        conditions.append(f"be.date_time_commission >= ${p}")
        params.append(date_from)
        p += 1

    if date_to:
        conditions.append(f"be.date_time_commission < (${p}::date + interval '1 day')")
        params.append(date_to)
        p += 1

    if crime_types:
        types = [t.strip().upper() for t in crime_types.split(",") if t.strip()]
        if types:
            conditions.append(f"UPPER(be.incident_type) = ANY(${p}::text[])")
            params.append(types)
            p += 1

    if barangays:
        brgy_list = [b.strip().upper() for b in barangays.split(",") if b.strip()]
        if brgy_list:
            expanded = expand_barangays(brgy_list)
            conditions.append(f"UPPER(TRIM(be.place_barangay)) = ANY(${p}::text[])")
            params.append(expanded)
            p += 1

    conditions.append(
        "LOWER(TRIM(be.status)) IN "
        "('cleared','cce','solved','cse','under investigation','ui','for investigation','active','ongoing')"
    )

    where = "WHERE " + " AND ".join(conditions)
    return where, params, p


# ── Individual query helpers ──────────────────────────────────────────────────

async def query_summary(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE LOWER(be.status) IN ('cleared', 'cce')) AS cleared,
              COUNT(*) FILTER (WHERE LOWER(be.status) IN ('solved', 'cse')) AS solved,
              COUNT(*) FILTER (
                WHERE LOWER(be.status) IN ('under investigation', 'ui', 'for investigation', 'active', 'ongoing')
              ) AS under_investigation
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
              AND LOWER(TRIM(be.status)) IN ('cleared','cce','solved','cse','under investigation','ui','for investigation','active','ongoing')
            GROUP BY UPPER(be.incident_type)""",
        *params, INDEX_CRIMES,
    )

    row_map = {r["crime"]: r for r in rows}
    return [
        {
            "crime":             crime,
            "total":             int(row_map[crime]["total"])             if crime in row_map else 0,
            "cleared":           int(row_map[crime]["cleared"])           if crime in row_map else 0,
            "solved":            int(row_map[crime]["solved"])            if crime in row_map else 0,
            "underInvestigation":int(row_map[crime]["under_investigation"])if crime in row_map else 0,
        }
        for crime in INDEX_CRIMES
    ]


async def query_trends(
    conn,
    where: str,
    params: list,
    next_p: int,
    granularity: str = "monthly",
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    date_trunc = {
        "daily":     "day",
        "weekly":    "week",
        "quarterly": "quarter",
    }.get(granularity, "month")

    rows = await conn.fetch(
        f"""SELECT
              TO_CHAR(DATE_TRUNC('{date_trunc}', be.date_time_commission), 'YYYY-MM-DD') AS label,
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
            GROUP BY label, UPPER(be.incident_type)
            ORDER BY label ASC""",
        *params, INDEX_CRIMES,
    )

    # Build DB map
    db_map: dict[str, dict] = {}
    for r in rows:
        label = r["label"]
        if label not in db_map:
            db_map[label] = {"label": label, "Total": 0, **{c: 0 for c in INDEX_CRIMES}}
        db_map[label][r["crime"]] = int(r["count"])
        db_map[label]["Total"] += int(r["count"])

    # Without a date range return raw results
    if not date_from or not date_to:
        return sorted(db_map.values(), key=lambda x: x["label"])

    def to_local_iso(d: datetime) -> str:
        return d.strftime("%Y-%m-%d")

    # Build skeleton cursor
    cursor = datetime.strptime(date_from, "%Y-%m-%d")
    if date_trunc == "month":
        cursor = cursor.replace(day=1)

    end = datetime.strptime(date_to, "%Y-%m-%d")
    if date_trunc == "week":
        end += timedelta(days=6)
    elif date_trunc == "month":
        end += timedelta(days=31)
    elif date_trunc == "quarter":
        end = end.replace(month=end.month + 3 if end.month <= 9 else end.month - 9,
                          year=end.year if end.month <= 9 else end.year + 1)

    # Walk cursor and build skeleton
    skeleton:      dict[str, dict] = {}
    skeleton_keys: list[str]       = []

    cur = datetime(cursor.year, cursor.month, cursor.day)
    while cur <= end:
        label = to_local_iso(cur)
        skeleton[label] = {"label": label, "Total": 0, **{c: 0 for c in INDEX_CRIMES}}
        skeleton_keys.append(label)

        if date_trunc == "day":
            cur += timedelta(days=1)
        elif date_trunc == "week":
            cur += timedelta(weeks=1)
        elif date_trunc == "quarter":
            month = cur.month + 3
            year  = cur.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            cur   = cur.replace(year=year, month=month)
        else:
            month = cur.month + 1
            year  = cur.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            cur   = cur.replace(year=year, month=month, day=1)

    # Merge DB data into skeleton
    if date_trunc == "week":
        for db_label, src in db_map.items():
            best_key = None
            for sk in skeleton_keys:
                if sk <= db_label:
                    best_key = sk
                else:
                    break
            if best_key is not None:
                skeleton[best_key]["Total"] += src["Total"]
                for c in INDEX_CRIMES:
                    skeleton[best_key][c] = skeleton[best_key].get(c, 0) + src.get(c, 0)
    else:
        for label, data in db_map.items():
            if label in skeleton:
                skeleton[label] = data

    # Trim and return
    trimmed = [
        row for row in skeleton.values()
        if (
            (date_trunc in ("week", "quarter") and date_from <= row["label"] <= date_to)
            or (date_trunc not in ("week", "quarter") and row["label"] <= date_to)
        )
    ]
    return sorted(trimmed, key=lambda x: x["label"])


async def query_hourly(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              EXTRACT(HOUR FROM be.date_time_commission)::int AS hour,
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
            GROUP BY hour, UPPER(be.incident_type)
            ORDER BY hour ASC""",
        *params, INDEX_CRIMES,
    )

    hour_map: dict[int, dict] = {}
    for r in rows:
        h = r["hour"]
        if h not in hour_map:
            hour_map[h] = {"total": 0}
        hour_map[h][r["crime"]] = int(r["count"])
        hour_map[h]["total"] += int(r["count"])

    result = []
    for h in range(24):
        period   = "AM" if h < 12 else "PM"
        display_h = 12 if h % 12 == 0 else h % 12
        entry = {
            "hour":  f"{display_h}{period}",
            "count": hour_map.get(h, {}).get("total", 0),
            **{c: hour_map.get(h, {}).get(c, 0) for c in INDEX_CRIMES},
        }
        result.append(entry)
    return result


async def query_by_day(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              be.day_of_incident AS day,
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
              AND be.day_of_incident IS NOT NULL
            GROUP BY be.day_of_incident, UPPER(be.incident_type)
            ORDER BY count DESC""",
        *params, INDEX_CRIMES,
    )

    day_map: dict[str, dict] = {}
    for r in rows:
        d = r["day"]
        if d not in day_map:
            day_map[d] = {"total": 0}
        day_map[d][r["crime"]] = int(r["count"])
        day_map[d]["total"] += int(r["count"])

    return [
        {
            "day":   day,
            "count": day_map.get(day, {}).get("total", 0),
            **{c: day_map.get(day, {}).get(c, 0) for c in INDEX_CRIMES},
        }
        for day in DAYS_OF_WEEK
    ]


async def query_place(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              TRIM(be.type_of_place) AS place,
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
              AND be.type_of_place IS NOT NULL
              AND TRIM(be.type_of_place) <> ''
            GROUP BY TRIM(be.type_of_place), UPPER(be.incident_type)
            ORDER BY count DESC""",
        *params, INDEX_CRIMES,
    )

    place_map: dict[str, dict] = {}
    for r in rows:
        pl = r["place"]
        if pl not in place_map:
            place_map[pl] = {"place": pl, "count": 0}
        place_map[pl][r["crime"]] = int(r["count"])
        place_map[pl]["count"] += int(r["count"])

    return sorted(place_map.values(), key=lambda x: x["count"], reverse=True)[:50]


async def query_barangay(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              TRIM(be.place_barangay) AS barangay,
              UPPER(be.incident_type) AS crime,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
              AND be.place_barangay IS NOT NULL
              AND TRIM(be.place_barangay) <> ''
            GROUP BY TRIM(be.place_barangay), UPPER(be.incident_type)
            ORDER BY count DESC""",
        *params, INDEX_CRIMES,
    )

    brgy_map: dict[str, dict] = {}
    for r in rows:
        b = r["barangay"]
        if b not in brgy_map:
            brgy_map[b] = {"barangay": b, "count": 0}
        brgy_map[b][r["crime"]] = int(r["count"])
        brgy_map[b]["count"] += int(r["count"])

    return sorted(brgy_map.values(), key=lambda x: x["count"], reverse=True)


async def query_modus(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              UPPER(be.incident_type) AS crime,
              TRIM(be.modus) AS modus,
              COUNT(*) AS count
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
              AND be.modus IS NOT NULL
              AND TRIM(be.modus) <> ''
            GROUP BY UPPER(be.incident_type), TRIM(be.modus)
            ORDER BY count DESC
            LIMIT 50""",
        *params, INDEX_CRIMES,
    )

    return [{"crime": r["crime"], "modus": r["modus"], "count": int(r["count"])} for r in rows]


async def query_complete_data(conn, where: str, params: list, next_p: int) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT
              TRIM(be.place_barangay)                            AS barangay,
              TRIM(be.type_of_place)                             AS type_of_place,
              TO_CHAR(be.date_time_commission, 'MM/DD/YYYY')     AS date,
              TO_CHAR(be.date_time_commission, 'HH12:MI AM')     AS time,
              UPPER(be.incident_type)                            AS crime_offense,
              TRIM(be.modus)                                     AS modus,
              TRIM(be.status)                                    AS case_status
            FROM blotter_analytics_view be
            {where}
            {"AND" if where else "WHERE"} UPPER(be.incident_type) = ANY(${next_p}::text[])
            ORDER BY
              TRIM(be.place_barangay) ASC,
              UPPER(be.incident_type) ASC,
              CASE
                WHEN LOWER(TRIM(be.status)) NOT IN ('cleared','cce','solved','cse','closed') THEN 0
                WHEN LOWER(TRIM(be.status)) IN ('cleared','cce') THEN 1
                WHEN LOWER(TRIM(be.status)) IN ('solved','cse') THEN 2
                ELSE 3
              END ASC""",
        *params, INDEX_CRIMES,
    )

    return [
        {
            "barangay":    r["barangay"]    or "",
            "typeOfPlace": r["type_of_place"] or "",
            "date":        r["date"]        or "",
            "time":        r["time"]        or "",
            "crimeOffense":r["crime_offense"] or "",
            "modus":       r["modus"]       or "",
            "caseStatus":  r["case_status"] or "",
        }
        for r in rows
    ]


# ── Patrol helper ─────────────────────────────────────────────────────────────
async def get_patrol_user_barangays(conn, user_id: str) -> list[str]:
    try:
        rows = await conn.fetch(
            """SELECT DISTINCT par.barangay
               FROM patrol_assignment pa
               JOIN patrol_assignment_patroller pap ON pa.patrol_id = pap.patrol_id
               JOIN active_patroller ap ON pap.active_patroller_id = ap.active_patroller_id
               JOIN patrol_assignment_route par ON pa.patrol_id = par.patrol_id
               WHERE ap.officer_id = $1
                 AND pa.start_date <= CURRENT_DATE
                 AND pa.end_date   >= CURRENT_DATE
                 AND par.stop_order <= 0
                 AND par.barangay IS NOT NULL""",
            user_id,
        )
        return [r["barangay"].upper() for r in rows]
    except Exception as e:
        print(f"get_patrol_user_barangays error: {e}")
        return []


# ── /overview — all queries in one round-trip ─────────────────────────────────
async def get_overview(req: Request):
    try:
        query_params = dict(req.query_params)
        where, params, next_p = build_where(query_params)

        granularity = query_params.get("granularity", "monthly")
        date_from   = query_params.get("date_from")
        date_to     = query_params.get("date_to")
        preset      = query_params.get("preset")

        user      = getattr(req.state, "user", {})
        role_name = user.get("role_name")
        user_id   = user.get("user_id")

        async with db.pool.acquire() as conn:
            # Patrol user barangay restriction
            if role_name == "Patrol":
                assigned = await get_patrol_user_barangays(conn, user_id)
                if assigned:
                    # Remove existing barangay filter (array param) and replace
                    new_params  = [p for p in params if not isinstance(p, list)]
                    new_where   = where  # rebuild cleanly via build_where override
                    # Re-build where from scratch with patrol barangays injected
                    override = {**query_params, "barangays": ",".join(assigned)}
                    where, params, next_p = build_where(override)

            (
                summary,
                trends,
                hourly,
                by_day,
                place,
                barangay,
                modus,
                complete_data,
            ) = await _run_all_queries(conn, where, params, next_p, granularity, date_from, date_to)

            # Previous month summary for "this_month" delta
            prev_summary = None
            if preset == "this_month":
                now_pht = datetime.now(timezone.utc) + timedelta(hours=8)
                first_of_this_month = now_pht.replace(day=1)
                prev_month_last = first_of_this_month - timedelta(days=1)
                prev_month_first = prev_month_last.replace(day=1)

                prev_from = prev_month_first.strftime("%Y-%m-%d")
                prev_to   = prev_month_last.strftime("%Y-%m-%d")

                prev_where, prev_params, prev_next_p = build_where(
                    {**query_params, "date_from": prev_from, "date_to": prev_to}
                )
                prev_summary = await query_summary(conn, prev_where, prev_params, prev_next_p)

        return JSONResponse(content={
            "success":      True,
            "summary":      summary,
            "trends":       trends,
            "hourly":       hourly,
            "byDay":        by_day,
            "place":        place,
            "barangay":     barangay,
            "modus":        modus,
            "completeData": complete_data,
            "prevSummary":  prev_summary,
        })

    except Exception as e:
        print(f"get_overview error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def _run_all_queries(conn, where, params, next_p, granularity, date_from, date_to):
    """Run all 8 queries concurrently inside an already-acquired connection."""
    import asyncio
    return await asyncio.gather(
        query_summary(conn, where, params, next_p),
        query_trends(conn, where, params, next_p, granularity, date_from, date_to),
        query_hourly(conn, where, params, next_p),
        query_by_day(conn, where, params, next_p),
        query_place(conn, where, params, next_p),
        query_barangay(conn, where, params, next_p),
        query_modus(conn, where, params, next_p),
        query_complete_data(conn, where, params, next_p),
    )


# ── Individual endpoints (backwards compatibility) ────────────────────────────
async def get_summary(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_summary(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_summary error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_trends(req: Request):
    try:
        query_params = dict(req.query_params)
        where, params, next_p = build_where(query_params)
        granularity = query_params.get("granularity", "monthly")
        date_from   = query_params.get("date_from")
        date_to     = query_params.get("date_to")
        async with db.pool.acquire() as conn:
            data = await query_trends(conn, where, params, next_p, granularity, date_from, date_to)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_trends error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_hourly(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_hourly(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_hourly error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_by_day(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_by_day(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_by_day error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_by_place(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_place(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_by_place error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_by_barangay(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_barangay(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_by_barangay error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_by_modus(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_modus(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_by_modus error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def get_complete_data(req: Request):
    try:
        where, params, next_p = build_where(dict(req.query_params))
        async with db.pool.acquire() as conn:
            data = await query_complete_data(conn, where, params, next_p)
        return JSONResponse(content={"success": True, "data": data})
    except Exception as e:
        print(f"get_complete_data error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})