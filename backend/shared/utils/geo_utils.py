# ================================================================================
# FILE: backend/shared/utils/geo_utils.py
# ================================================================================

import json
import math
import os
import time
import asyncio
from typing import Optional

import httpx


# ── GeoJSON loader ────────────────────────────────────────────────────────────

_barangay_geojson       = None
_geojson_load_error     = False

_POSSIBLE_PATHS = [
    os.path.join(os.path.dirname(__file__), "../../src/bacoor_barangays.geojson"),
    os.path.join(os.path.dirname(__file__), "../../../frontend/public/bacoor_barangays.geojson"),
    os.path.join(os.path.dirname(__file__), "../../bacoor_barangays.geojson"),
    os.path.join(os.getcwd(), "frontend/public/bacoor_barangays.geojson"),
    os.path.join(os.getcwd(), "bacoor_barangays.geojson"),
    os.path.join(os.path.dirname(__file__), "../../../public/bacoor_barangays.geojson"),
]


def load_barangay_geojson() -> Optional[dict]:
    global _barangay_geojson, _geojson_load_error

    if _barangay_geojson:
        return _barangay_geojson
    if _geojson_load_error:
        return None

    geojson_path = next((p for p in _POSSIBLE_PATHS if os.path.exists(p)), None)

    if not geojson_path:
        print(f"GeoJSON file not found. Tried: {', '.join(_POSSIBLE_PATHS)}")
        _geojson_load_error = True
        return None

    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            _barangay_geojson = json.load(f)
    except Exception as e:
        print(f"Error loading GeoJSON: {e}")
        _geojson_load_error = True
        return None

    return _barangay_geojson


# ── Point-in-polygon (ray casting) ────────────────────────────────────────────

def _is_point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    x, y   = point[0], point[1]
    inside = False
    j      = len(polygon) - 1

    for i in range(len(polygon)):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


# ── Basic barangay lookup (no cache, no index) ─────────────────────────────────

def get_barangay_from_coordinates(lng: float, lat: float) -> Optional[str]:
    try:
        geojson = load_barangay_geojson()
        if not geojson:
            return None

        point = [lng, lat]

        for feature in geojson["features"]:
            geometry     = feature["geometry"]
            props        = feature.get("properties") or {}
            barangay_name = props.get("name_db") or props.get("name_kml")

            if not barangay_name:
                continue

            if geometry["type"] == "Polygon":
                if _is_point_in_polygon(point, geometry["coordinates"][0]):
                    return barangay_name

            elif geometry["type"] == "MultiPolygon":
                for polygon in geometry["coordinates"]:
                    if _is_point_in_polygon(point, polygon[0]):
                        return barangay_name

        return None

    except Exception as e:
        print(f"Error resolving barangay: {e}")
        return None


# ── Nominatim reverse-geocode cache ───────────────────────────────────────────
# Keyed by "lng,lat" rounded to 3 decimal places (~111 m precision).

_city_cache: dict[str, dict] = {}
_CITY_CACHE_TTL = 60 * 60 * 1000  # 1 hour in ms


async def get_city_from_coordinates(lng: float, lat: float) -> Optional[str]:
    if not lng or not lat or math.isnan(lng) or math.isnan(lat):
        return None

    r_lng = round(lng * 1e3) / 1e3
    r_lat = round(lat * 1e3) / 1e3
    key   = f"{r_lng},{r_lat}"

    now_ms = int(time.time() * 1000)
    cached = _city_cache.get(key)
    if cached and now_ms - cached["ts"] < _CITY_CACHE_TTL:
        return cached["value"]

    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?format=json&lat={lat}&lon={lng}&zoom=10&addressdetails=1"
    )

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "BacoorPatrolSystem/1.0"},
            timeout=3.0,
        ) as client:
            response = await client.get(url)
            data     = response.json()

        addr     = data.get("address") or {}
        city     = (
            addr.get("city")
            or addr.get("town")
            or addr.get("municipality")
            or addr.get("county")
            or addr.get("state")
        )
        province = addr.get("state") or addr.get("region")
        label    = (
            (f"{city}, {province}" if province and province != city else city)
            if city else None
        )

        _city_cache[key] = {"value": label, "ts": now_ms}
        return label

    except Exception:
        _city_cache[key] = {"value": None, "ts": now_ms}
        return None


# ── Barangay lookup with short-lived sync cache ────────────────────────────────

_barangay_cache: dict[str, dict] = {}
_CACHE_TTL = 5_000  # 5 seconds in ms


def get_barangay_with_cache(lng: float, lat: float) -> Optional[str]:
    if not lng or not lat or math.isnan(lng) or math.isnan(lat):
        return None

    r_lng     = round(lng * 1e6) / 1e6
    r_lat     = round(lat * 1e6) / 1e6
    cache_key = f"{r_lng},{r_lat}"
    now_ms    = int(time.time() * 1000)

    cached = _barangay_cache.get(cache_key)
    if cached and now_ms - cached["timestamp"] < _CACHE_TTL:
        return cached["barangay"]

    barangay = get_barangay_from_coordinates(lng, lat)
    _barangay_cache[cache_key] = {"barangay": barangay, "timestamp": now_ms}

    # Evict stale entries when cache grows large
    if len(_barangay_cache) > 1000:
        for k, v in list(_barangay_cache.items()):
            if now_ms - v["timestamp"] > _CACHE_TTL * 2:
                del _barangay_cache[k]

    return barangay


# ── Spatial index ──────────────────────────────────────────────────────────────

_spatial_index: Optional[list[dict]] = None


def _build_spatial_index() -> None:
    global _spatial_index

    geojson = load_barangay_geojson()
    if not geojson:
        return

    _spatial_index = []

    for feature in geojson["features"]:
        geometry      = feature["geometry"]
        props         = feature.get("properties") or {}
        barangay_name = props.get("name_db") or props.get("name_kml")

        if not barangay_name:
            continue

        min_lng = min_lat =  math.inf
        max_lng = max_lat = -math.inf

        def process_ring(ring):
            nonlocal min_lng, max_lng, min_lat, max_lat
            for pt in ring:
                min_lng = min(min_lng, pt[0])
                max_lng = max(max_lng, pt[0])
                min_lat = min(min_lat, pt[1])
                max_lat = max(max_lat, pt[1])

        if geometry["type"] == "Polygon":
            process_ring(geometry["coordinates"][0])
        elif geometry["type"] == "MultiPolygon":
            for polygon in geometry["coordinates"]:
                process_ring(polygon[0])

        _spatial_index.append({
            "name":     barangay_name,
            "bounds":   {"min_lng": min_lng, "max_lng": max_lng,
                         "min_lat": min_lat, "max_lat": max_lat},
            "geometry": geometry,
        })


def get_barangay_optimized(lng: float, lat: float) -> Optional[str]:
    """Synchronous barangay lookup with spatial index + cache."""
    global _spatial_index

    if not lng or not lat or math.isnan(lng) or math.isnan(lat):
        return None

    r_lng     = round(lng * 1e6) / 1e6
    r_lat     = round(lat * 1e6) / 1e6
    cache_key = f"{r_lng},{r_lat}"
    now_ms    = int(time.time() * 1000)

    cached = _barangay_cache.get(cache_key)
    if cached and now_ms - cached["timestamp"] < _CACHE_TTL:
        return cached["barangay"]

    if _spatial_index is None:
        _build_spatial_index()

    if _spatial_index is None:
        result = get_barangay_from_coordinates(lng, lat)
        _barangay_cache[cache_key] = {"barangay": result, "timestamp": now_ms}
        return result

    point      = [lng, lat]
    candidates = [
        item for item in _spatial_index
        if (item["bounds"]["min_lng"] <= lng <= item["bounds"]["max_lng"]
            and item["bounds"]["min_lat"] <= lat <= item["bounds"]["max_lat"])
    ]

    result = None
    for candidate in candidates:
        geometry = candidate["geometry"]

        if geometry["type"] == "Polygon":
            if _is_point_in_polygon(point, geometry["coordinates"][0]):
                result = candidate["name"]
                break

        elif geometry["type"] == "MultiPolygon":
            for polygon in geometry["coordinates"]:
                if _is_point_in_polygon(point, polygon[0]):
                    result = candidate["name"]
                    break
            if result:
                break

    _barangay_cache[cache_key] = {"barangay": result, "timestamp": now_ms}
    return result


async def get_barangay_or_city_optimized(lng: float, lat: float) -> Optional[str]:
    """
    Returns the barangay name if inside Bacoor, otherwise the city name
    from Nominatim (e.g. 'Imus, Cavite'), or None if everything fails.
    """
    barangay = get_barangay_optimized(lng, lat)
    if barangay:
        return barangay

    return await get_city_from_coordinates(lng, lat)