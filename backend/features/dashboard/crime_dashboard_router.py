# backend\features\dashboard\crime_dashboard_router.py

from fastapi import APIRouter
from shared.middleware.token_middleware import authenticate
from features.dashboard.crime_dashboard_controller import (
    get_overview,
    get_summary,
    get_trends,
    get_hourly,
    get_by_day,
    get_by_place,
    get_by_barangay,
    get_by_modus,
    get_complete_data,
)
from features.dashboard.export_dashboard_controller import export_dashboard

router = APIRouter()

router.get("/overview")(authenticate(get_overview))
router.get("/summary")(authenticate(get_summary))
router.get("/trends")(authenticate(get_trends))
router.get("/hourly")(authenticate(get_hourly))
router.get("/by-day")(authenticate(get_by_day))
router.get("/by-place")(authenticate(get_by_place))
router.get("/by-barangay")(authenticate(get_by_barangay))
router.get("/by-modus")(authenticate(get_by_modus))
router.get("/complete-data")(authenticate(get_complete_data))

router.post("/export")(authenticate(export_dashboard))  # ← PDF export