# ================================================================================
# FILE: backend/features/crime_map/crime_map_controller.py
# ================================================================================

import httpx
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

import config.database as db


AI_SERVICE_URL = "http://localhost:8000"

CRIME_WEIGHTS = {
    "MURDER": 1.0,
    "HOMICIDE": 1.0,
    "SPECIAL COMPLEX CRIME": 1.0,
    "RAPE": 0.7,
    "ROBBERY": 0.5,
    "CARNAPPING - MV": 0.3,
    "CARNAPPING - MC": 0.3,
    "PHYSICAL INJURY": 0.2,
    "THEFT": 0.1,
}

COLOR_MAP = {
    "ROBBERY": "#ef4444",
    "THEFT": "#f97316",
    "PHYSICAL INJURIES": "#eab308",
    "PHYSICAL INJURY": "#eab308",
    "HOMICIDE": "#8b5cf6",
    "MURDER": "#7c3aed",
    "RAPE": "#ec4899",
    "CARNAPPING - MC": "#3b82f6",
    "CARNAPPING - MV": "#0ea5e9",
    "SPECIAL COMPLEX CRIME": "#14b8a6",
}

DAYS_OF_WEEK = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

VALID_STATUSES = (
    "cleared", "cce", "solved", "cse",
    "under investigation", "ui",
    "for investigation", "active", "ongoing",
)


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


def _today() -> str:
    return date.today().isoformat()


# ── Incidence helpers ─────────────────────────────────────────────────────────

def _get_incidence_thresholds(date_from: str, date_to: str):
    days = (
        datetime.fromisoformat(date_to) - datetime.fromisoformat(date_from)
    ).days + 1
    if days <= 29:
        return 1, 2
    if days <= 91:
        return 1, 3
    if days <= 364:
        return 2, 5
    return 3, 8


def _get_incidence_color(crime_count: int, date_from: str, date_to: str):
    low_max, med_max = _get_incidence_thresholds(date_from, date_to)
    if crime_count == 0:
        return "#ffffff", "None"
    if crime_count <= low_max:
        return "#eab308", "Low Incidence"
    if crime_count <= med_max:
        return "#f97316", "Moderate Incidence"
    return "#b91c1c", "High Incidence"


def _incidence_min_count(date_from: str, date_to: str) -> int:
    low_max, _ = _get_incidence_thresholds(date_from, date_to)
    return low_max + 1


def _high_incidence_min_count(date_from: str, date_to: str) -> int:
    _, med_max = _get_incidence_thresholds(date_from, date_to)
    return med_max + 1


# ── Patrol barangay helper ────────────────────────────────────────────────────

async def get_patrol_user_barangays(user_id) -> list[str]:
    try:
        rows = await get_pool().fetch(
            """
            SELECT DISTINCT par.barangay
            FROM patrol_assignment pa
            JOIN patrol_assignment_patroller pap ON pa.patrol_id = pap.patrol_id
            JOIN active_patroller ap ON pap.active_patroller_id = ap.active_patroller_id
            JOIN patrol_assignment_route par ON pa.patrol_id = par.patrol_id
            WHERE ap.officer_id = $1
              AND pa.start_date <= CURRENT_DATE
              AND pa.end_date >= CURRENT_DATE
              AND par.stop_order <= 0
              AND par.barangay IS NOT NULL
            """,
            user_id,
        )
        return [r["barangay"].upper() for r in rows]
    except Exception as e:
        print(f"get_patrol_user_barangays error: {e}")
        return []


# ── Query builder helpers ─────────────────────────────────────────────────────

def _parse_list_param(raw) -> list[str]:
    """Accept a single string, comma-separated string, or list."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else raw.split(",")
    return [i.strip().upper() for i in items if i.strip()]


def _build_base_where(
    params: list,
    date_from: Optional[str],
    date_to: Optional[str],
    incident_types: list[str],
    barangay_list: list[str],
) -> tuple[str, int]:
    """
    Build the shared WHERE clause used by all four endpoints.
    Returns (where_sql, next_param_index).
    """
    status_list = ", ".join(f"'{s}'" for s in VALID_STATUSES)
    where = f"WHERE lat IS NOT NULL AND LOWER(TRIM(status)) IN ({status_list})"
    p = len(params) + 1

    if date_from:
        where += f" AND date_time_commission >= ${p}"
        params.append(date_from)
        p += 1
    if date_to:
        where += f" AND date_time_commission < (${p}::date + interval '1 day')"
        params.append(date_to)
        p += 1
    if incident_types:
        where += f" AND UPPER(TRIM(incident_type)) = ANY(${p}::text[])"
        params.append(incident_types)
        p += 1
    if barangay_list:
        where += f" AND UPPER(TRIM(place_barangay)) = ANY(${p}::text[])"
        params.append(barangay_list)
        p += 1

    return where, p


async def _apply_role_filter(
    where: str,
    params: list,
    p: int,
    role_name: Optional[str],
    user_id,
    include_lng: bool = False,
) -> tuple[str, int]:
    """
    Appends barangay restriction based on the user's role.
    Returns updated (where_sql, next_param_index).
    """
    if role_name == "Patrol":
        assigned = await get_patrol_user_barangays(user_id)
        if assigned:
            where += f" AND UPPER(TRIM(place_barangay)) = ANY(${p}::text[])"
            params.append(assigned)
            p += 1

    return where, p


# =============================================================================
# HANDLERS
# =============================================================================

async def get_boundaries(request: Request):
    try:
        q = request.query_params
        date_from = q.get("date_from")
        date_to   = q.get("date_to")

        incident_types = _parse_list_param(
            q.getlist("incident_type") or q.get("incident_type")
        )
        barangay_list = _parse_list_param(
            q.getlist("barangays") or q.getlist("barangay")
            or q.get("barangays") or q.get("barangay")
        )

        params: list = []
        where, p = _build_base_where(
            params, date_from, date_to, incident_types, barangay_list
        )

        role_name = (request.state.user or {}).get("role_name")
        user_id   = (request.state.user or {}).get("user_id")

        where, p = await _apply_role_filter(where, params, p, role_name, user_id)

        crime_sql = (
            "SELECT UPPER(TRIM(place_barangay)) as barangay, COUNT(*) as crime_count "
            f"FROM blotter_analytics_view {where} "
            "GROUP BY UPPER(TRIM(place_barangay))"
        )

        pool = get_pool()
        crime_rows, barangay_rows = await pool.fetch(
            crime_sql, *params
        ), await pool.fetch(
            "SELECT name_db, name_kml, centroid_lat, centroid_lng "
            "FROM barangay_map_data ORDER BY name_db"
        )

        crime_map = {r["barangay"]: int(r["crime_count"]) for r in crime_rows}

        eff_from = date_from or "2000-01-01"
        eff_to   = date_to   or _today()

        boundaries = [
            {
                "name_db":      b["name_db"],
                "name_kml":     b["name_kml"],
                "centroid_lat": float(b["centroid_lat"]),
                "centroid_lng": float(b["centroid_lng"]),
                "crime_count":  crime_map.get(b["name_db"].upper(), 0),
                "color":        _get_incidence_color(
                    crime_map.get(b["name_db"].upper(), 0), eff_from, eff_to
                )[0],
                "risk":         _get_incidence_color(
                    crime_map.get(b["name_db"].upper(), 0), eff_from, eff_to
                )[1],
            }
            for b in barangay_rows
        ]

        return {"success": True, "data": boundaries}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_boundaries error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": str(e)})


async def get_pins(request: Request):
    try:
        q = request.query_params
        date_from     = q.get("date_from")
        date_to       = q.get("date_to")
        modus         = q.get("modus")
        hour          = q.get("hour")
        day           = q.get("day")

        incident_types = _parse_list_param(
            q.getlist("incident_type") or q.get("incident_type")
        )
        barangay_list = _parse_list_param(
            q.getlist("barangays") or q.getlist("barangay")
            or q.get("barangays") or q.get("barangay")
        )

        params: list = []
        where, p = _build_base_where(
            params, date_from, date_to, incident_types, barangay_list
        )
        where += " AND lng IS NOT NULL"

        if modus:
            where += (
                f" AND EXISTS ("
                f"  SELECT 1 FROM crime_modus cm"
                f"  JOIN crime_modus_reference cmr ON cm.modus_reference_id = cmr.id"
                f"  WHERE cm.blotter_id = blotter_analytics_view.blotter_id"
                f"  AND UPPER(cmr.modus_name) = UPPER(${p})"
                f")"
            )
            params.append(modus)
            p += 1

        if hour is not None and hour != "":
            where += f" AND EXTRACT(HOUR FROM date_time_commission) = ${p}"
            params.append(int(hour))
            p += 1

        if day:
            where += f" AND TRIM(TO_CHAR(date_time_commission, 'Day')) = ${p}"
            params.append(day)
            p += 1

        role_name = (request.state.user or {}).get("role_name")
        user_id   = (request.state.user or {}).get("user_id")

        pool = get_pool()

        if role_name == "Barangay Official":
            row = await pool.fetchrow(
                "SELECT bd.barangay_code FROM barangay_details bd WHERE bd.user_id = $1",
                user_id,
            )
            if row:
                where += f" AND UPPER(TRIM(place_barangay)) = UPPER(${p})"
                params.append(row["barangay_code"])
                p += 1
        else:
            where, p = await _apply_role_filter(where, params, p, role_name, user_id)

        sql = (
            "SELECT blotter_id, blotter_entry_number, incident_type, place_barangay,"
            "       place_street, type_of_place, modus, status,"
            "       date_time_commission, lat, lng "
            f"FROM blotter_analytics_view {where} "
            "ORDER BY date_time_commission DESC"
        )

        rows = await pool.fetch(sql, *params)

        pins = []
        for r in rows:
            dt = r["date_time_commission"]
            pins.append(
                {
                    **dict(r),
                    "lat":         float(r["lat"]),
                    "lng":         float(r["lng"]),
                    "color":       COLOR_MAP.get((r["incident_type"] or "").upper(), "#6b7280"),
                    "time":        dt.strftime("%I:%M %p") if dt else None,
                    "day_of_week": DAYS_OF_WEEK[dt.weekday()] if dt else None,
                }
            )

        return {"success": True, "count": len(pins), "data": pins}

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_pins error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": str(e)})


async def get_statistics(request: Request):
    try:
        q = request.query_params
        date_from = q.get("date_from")
        date_to   = q.get("date_to")

        incident_types = _parse_list_param(
            q.getlist("incident_type") or q.get("incident_type")
        )
        barangay_list = _parse_list_param(
            q.getlist("barangays") or q.getlist("barangay")
            or q.get("barangays") or q.get("barangay")
        )

        params: list = []
        where, p = _build_base_where(
            params, date_from, date_to, incident_types, barangay_list
        )

        role_name = (request.state.user or {}).get("role_name")
        user_id   = (request.state.user or {}).get("user_id")
        where, p  = await _apply_role_filter(where, params, p, role_name, user_id)

        eff_from         = date_from or "2000-01-01"
        eff_to           = date_to   or _today()
        high_inc_min     = _high_incidence_min_count(eff_from, eff_to)

        pool = get_pool()

        (
            total_pins_row,
            by_type_rows,
            incidence_rows,
            high_incidence_rows,
            recent_rows,
            total_blotters_row,
        ) = await pool.fetchrow(
            f"SELECT COUNT(*) FROM blotter_analytics_view {where}", *params
        ), await pool.fetch(
            f"SELECT incident_type, COUNT(*) as count "
            f"FROM blotter_analytics_view {where} "
            f"GROUP BY incident_type ORDER BY count DESC",
            *params,
        ), await pool.fetch(
            f"SELECT UPPER(TRIM(place_barangay)) as barangay, COUNT(*) as count "
            f"FROM blotter_analytics_view {where} "
            f"GROUP BY UPPER(TRIM(place_barangay)) "
            f"HAVING COUNT(*) >= 1 "
            f"ORDER BY count DESC, barangay ASC",
            *params,
        ), await pool.fetch(
            f"SELECT UPPER(TRIM(place_barangay)) as barangay, COUNT(*) as count "
            f"FROM blotter_analytics_view {where} "
            f"GROUP BY UPPER(TRIM(place_barangay)) "
            f"HAVING COUNT(*) >= ${p}::int "
            f"ORDER BY count DESC, barangay ASC",
            *params, high_inc_min,
        ), await pool.fetch(
            f"SELECT blotter_entry_number, incident_type, place_barangay, date_time_commission "
            f"FROM blotter_analytics_view {where} "
            f"ORDER BY date_time_commission DESC LIMIT 5",
            *params,
        ), await pool.fetchrow(
            "SELECT COUNT(*) FROM blotter_analytics_view "
            f"WHERE LOWER(TRIM(status)) IN ({', '.join(repr(s) for s in VALID_STATUSES)})"
        )

        incidence_with_level = [
            {
                "barangay": r["barangay"],
                "count":    int(r["count"]),
                "risk":     _get_incidence_color(int(r["count"]), eff_from, eff_to)[1],
            }
            for r in incidence_rows
        ]

        return {
            "success": True,
            "data": {
                "total_pins":            int(total_pins_row["count"]),
                "total_blotters":        int(total_blotters_row["count"]),
                "barangays_with_crimes": len(incidence_with_level),
                "incidence_count":       len(incidence_with_level),
                "high_incidence_count":  len(high_incidence_rows),
                "top_crime":             by_type_rows[0]["incident_type"] if by_type_rows else None,
                "top_barangay":          incidence_with_level[0]["barangay"] if incidence_with_level else None,
                "by_incident_type":      [dict(r) for r in by_type_rows],
                "incidence_barangays":   incidence_with_level,
                "recent_incidents":      [dict(r) for r in recent_rows],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_statistics error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": str(e)})


async def get_heatmap(request: Request):
    try:
        q = request.query_params
        date_from = q.get("date_from")
        date_to   = q.get("date_to")

        incident_types = _parse_list_param(
            q.getlist("incident_type") or q.get("incident_type")
        )
        barangay_list = _parse_list_param(
            q.getlist("barangays") or q.getlist("barangay")
            or q.get("barangays") or q.get("barangay")
        )

        params: list = []
        where, p = _build_base_where(
            params, date_from, date_to, incident_types, barangay_list
        )
        where += " AND lng IS NOT NULL"

        role_name = (request.state.user or {}).get("role_name")
        user_id   = (request.state.user or {}).get("user_id")

        pool = get_pool()

        if role_name == "Barangay Official":
            row = await pool.fetchrow(
                "SELECT barangay_code FROM barangay_details WHERE user_id = $1",
                user_id,
            )
            if row:
                where += f" AND UPPER(TRIM(place_barangay)) = UPPER(${p})"
                params.append(row["barangay_code"].upper())
                p += 1
        else:
            where, p = await _apply_role_filter(where, params, p, role_name, user_id)

        points_sql = (
            "SELECT blotter_id, "
            "       UPPER(TRIM(incident_type))   AS incident_type, "
            "       UPPER(TRIM(place_barangay))  AS place_barangay, "
            "       date_time_commission, "
            "       lat::float, lng::float "
            f"FROM blotter_analytics_view {where} "
            "ORDER BY date_time_commission DESC"
        )

        points_rows = await pool.fetch(points_sql, *params)

        # ── DBSCAN clusters from AI service ──────────────────────────────────
        ai_payload = {
            "date_from":   date_from or "2000-01-01",
            "date_to":     date_to   or _today(),
            "crime_types": incident_types,
            "barangays":   barangay_list,
        }

        dbscan_clusters = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                ai_res = await client.post(
                    f"{AI_SERVICE_URL}/clusters",
                    json=ai_payload,
                )
                dbscan_clusters = ai_res.json().get("clusters", [])
        except Exception as ai_err:
            print(f"DBSCAN service unavailable, skipping clusters: {ai_err}")

        # ── Build GeoJSON features ────────────────────────────────────────────
        point_features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["lng"], r["lat"]],
                },
                "properties": {
                    "weight":        CRIME_WEIGHTS.get((r["incident_type"] or "").upper(), 0.1),
                    "incident_type": r["incident_type"],
                    "barangay":      r["place_barangay"],
                    "date":          r["date_time_commission"].isoformat()
                                     if r["date_time_commission"] else None,
                },
            }
            for r in points_rows
        ]

        max_count = max((c["count"] for c in dbscan_clusters), default=1)

        cluster_features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [c["centroid_lng"], c["centroid_lat"]],
                },
                "properties": {
                    "cluster":           True,
                    "count":             c["count"],
                    "dominant_crime":    c["dominant_crime"],
                    "dominant_barangay": c.get("dominant_barangay", "Unknown"),
                    "intensity":         min(1.0, c["count"] / max_count),
                    "rank":              i + 1,
                    "crime_types":       c["crime_types"],
                    "dominant_modus":    c["dominant_modus"],
                    "radius_m":          c.get("radius_m", 100),
                },
            }
            for i, c in enumerate(dbscan_clusters)
        ]

        return {
            "success":        True,
            "total_points":   len(point_features),
            "total_clusters": len(cluster_features),
            "points":         {"type": "FeatureCollection", "features": point_features},
            "clusters":       {"type": "FeatureCollection", "features": cluster_features},
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"get_heatmap error: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "message": str(e)})