# ================================================================================
# FILE: backend/features/patrols/patrol_routes.py
# ================================================================================

from flask import Blueprint
from shared.middleware.token_middleware import authenticate
from features.patrols.patrol_controller import (
    get_patrol_stats,
    get_active_patrollers,
    get_available_patrollers,
    get_available_mobile_units,
    get_mobile_units,
    create_mobile_unit,
    update_mobile_unit,
    delete_mobile_unit,
    get_my_patrols,
    get_patrols,
    create_patrol,
    update_patrol,
    delete_patrol,
    update_patrollers_for_date,
    update_route_notes,
    update_route_task,
    add_route_task,
    remove_route_task,
    submit_after_patrol_report,
    get_after_patrol_reports,
    get_my_after_patrol_reports,
    delete_after_patrol_report,
    update_officer_location,
    upload_after_patrol_photos,
    delete_after_patrol_photo,
)
from features.patrols.export_patrol_controller import (
    export_patrol_list,
    export_patrol_detail,
)

patrol_bp = Blueprint("patrol", __name__)

# ── Stats & listings ──────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/stats",                  view_func=authenticate(get_patrol_stats),         methods=["GET"])
patrol_bp.add_url_rule("/active",                 view_func=authenticate(get_active_patrollers),    methods=["GET"])
patrol_bp.add_url_rule("/available-patrollers",   view_func=authenticate(get_available_patrollers), methods=["GET"])
patrol_bp.add_url_rule("/available-mobile-units", view_func=get_available_mobile_units,             methods=["GET"])

# ── Mobile units ──────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/mobile-units",      view_func=authenticate(get_mobile_units),   methods=["GET"])
patrol_bp.add_url_rule("/mobile-units",      view_func=authenticate(create_mobile_unit), methods=["POST"])
patrol_bp.add_url_rule("/mobile-units/<id>", view_func=authenticate(update_mobile_unit), methods=["PUT"])
patrol_bp.add_url_rule("/mobile-units/<id>", view_func=authenticate(delete_mobile_unit), methods=["DELETE"])

# ── Patrols ───────────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/my-patrols",   view_func=authenticate(get_my_patrols),  methods=["GET"])
patrol_bp.add_url_rule("/patrols",      view_func=authenticate(get_patrols),     methods=["GET"])
patrol_bp.add_url_rule("/patrols",      view_func=authenticate(create_patrol),   methods=["POST"])
patrol_bp.add_url_rule("/patrols/<id>", view_func=authenticate(update_patrol),   methods=["PUT"])
patrol_bp.add_url_rule("/patrols/<id>", view_func=authenticate(delete_patrol),   methods=["DELETE"])

# ── Patrollers per date ───────────────────────────────────────────────────────
patrol_bp.add_url_rule("/patrols/<id>/patrollers/<date>", view_func=authenticate(update_patrollers_for_date), methods=["PATCH"])

# ── Routes / tasks ────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/routes/<route_id>/notes", view_func=authenticate(update_route_notes), methods=["PATCH"])
patrol_bp.add_url_rule("/routes/<route_id>/task",  view_func=authenticate(update_route_task),  methods=["PATCH"])
patrol_bp.add_url_rule("/routes/add",              view_func=authenticate(add_route_task),     methods=["POST"])
patrol_bp.add_url_rule("/routes/<route_id>",       view_func=authenticate(remove_route_task),  methods=["DELETE"])

# ── Export ────────────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/export/list",   view_func=authenticate(export_patrol_list),   methods=["POST"])
patrol_bp.add_url_rule("/export/detail", view_func=authenticate(export_patrol_detail), methods=["POST"])

# ── After patrol reports ──────────────────────────────────────────────────────
patrol_bp.add_url_rule("/patrols/<id>/after-report",       view_func=authenticate(submit_after_patrol_report),  methods=["POST"])
patrol_bp.add_url_rule("/patrols/<id>/after-reports",      view_func=authenticate(get_after_patrol_reports),    methods=["GET"])
patrol_bp.add_url_rule("/patrols/<id>/after-reports/mine", view_func=authenticate(get_my_after_patrol_reports), methods=["GET"])
patrol_bp.add_url_rule("/after-reports/<report_id>",       view_func=authenticate(delete_after_patrol_report),  methods=["DELETE"])

# ── Photos ────────────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/after-reports/<report_id>/photos", view_func=authenticate(upload_after_patrol_photos), methods=["POST"])
patrol_bp.add_url_rule("/after-reports/<report_id>/photos", view_func=authenticate(delete_after_patrol_photo),  methods=["DELETE"])

# ── Location ──────────────────────────────────────────────────────────────────
patrol_bp.add_url_rule("/location", view_func=authenticate(update_officer_location), methods=["POST"])