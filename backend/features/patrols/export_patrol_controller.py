# ==============================================================================
# FILE: backend/features/patrols/controllers/export_patrol_controller.py
#
# Pure-Python PDF export — uses ReportLab only, zero system dependencies.
# Install:  pip install reportlab
#
#  POST /patrol/export/list    — full patrol list (active / upcoming / completed)
#  POST /patrol/export/detail  — single patrol detail (map + patrollers + timetable)
# ==============================================================================

import io
import base64
from datetime import datetime, date, timedelta

from flask import request, g, jsonify, make_response

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Table, TableStyle, Spacer, Image, HRFlowable,
    NextPageTemplate, KeepTogether,
)
from reportlab.platypus.flowables import PageBreak
from reportlab.lib.utils import ImageReader

from shared.utils.audit_logger import log_audit

DARK  = colors.HexColor("#1E3A5F")
LIGHT = colors.HexColor("#D9E4F0")
WHITE = colors.white
GRAY  = colors.HexColor("#F3F4F6")
RED   = colors.HexColor("#DC2626")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#B45309")
MUTED = colors.HexColor("#9CA3AF")
MED   = colors.HexColor("#6B7280")

PAGE_W, PAGE_H = A4                        
MARGIN         = 2 * cm
CONTENT_W      = PAGE_W - 2 * MARGIN       


def _style(name, **kw):
    defaults = dict(fontName="Helvetica", fontSize=9, leading=12,
                    textColor=colors.black, spaceAfter=4)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

S_TITLE       = _style("title",   fontName="Helvetica-Bold", fontSize=20,
                        textColor=DARK,  spaceAfter=14, spaceBefore=0, alignment=TA_CENTER)
S_SUBTITLE    = _style("sub",     fontName="Helvetica",      fontSize=10,
                        textColor=MUTED, spaceAfter=14, alignment=TA_CENTER)
S_SECTION     = _style("sec",     fontName="Helvetica-Bold", fontSize=13,
                        textColor=DARK,  spaceAfter=6,  spaceBefore=14)
S_SUBSECTION  = _style("subsec",  fontName="Helvetica-Bold", fontSize=10,
                        textColor=DARK,  spaceAfter=4,  spaceBefore=8)
S_BODY        = _style("body",    fontSize=9, spaceAfter=4)
S_HEADER_TEXT = _style("hdr",     fontSize=7, textColor=MUTED, alignment=TA_RIGHT)
S_FOOTER_TEXT = _style("ftr",     fontSize=7, textColor=MUTED, alignment=TA_CENTER)



def _fmt_date(d) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = datetime.strptime(d[:10], "%Y-%m-%d").date()
    # Use d.day (int) to avoid platform-specific %-d directive
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _fmt_time(t) -> str:
    """Accept HH:MM or HH:MM:SS string."""
    if not t:
        return "—"
    parts = str(t)[:5].split(":")
    hh, mm_ = int(parts[0]), int(parts[1])
    period = "AM" if hh < 12 else "PM"
    h12    = hh % 12 or 12
    return f"{h12:02d}:{mm_:02d} {period}"


def _fmt_now() -> str:
    """Cross-platform current datetime string, e.g. 'June 4, 2026 at 5:30 PM'."""
    now = datetime.now()
    time_part = now.strftime("%I:%M %p").lstrip("0")
    return f"{now.strftime('%B')} {now.day}, {now.year} at {time_part}"


def _date_range(start: str, end: str) -> list[str]:
    dates, cur = [], datetime.strptime(start, "%Y-%m-%d").date()
    last       = datetime.strptime(end,   "%Y-%m-%d").date()
    while cur <= last:
        dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def _to_date_str(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        if "T" in d or "Z" in d:
            return datetime.fromisoformat(d.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        return d[:10]
    if isinstance(d, (datetime, date)):
        return d.strftime("%Y-%m-%d")
    return None


def _patrol_status(patrol: dict) -> str:
    today = date.today()
    s     = datetime.strptime(patrol["start_date"][:10], "%Y-%m-%d").date()
    e     = datetime.strptime(patrol["end_date"][:10],   "%Y-%m-%d").date()
    if today < s:
        return "upcoming"
    if today > e:
        return "completed"
    return "active"


def _status_color(status: str):
    return {
        "active":    GREEN,
        "upcoming":  DARK,
        "completed": MED,
    }.get(status, MED)



def _get_ip() -> str:
    return request.remote_addr or "unknown"



def _header_ts(col_count: int) -> list:
    """TableStyle commands for a header row."""
    return [
        ("BACKGROUND",   (0, 0), (-1, 0),  DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  8),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  6),
        ("TOPPADDING",   (0, 0), (-1, 0),  6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]


def _body_row_ts(row_count: int, alt_start: int = 1) -> list:
    """Alternating row shading for data rows."""
    cmds = []
    for i in range(alt_start, row_count):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), GRAY))
        else:
            cmds.append(("BACKGROUND", (0, i), (-1, i), WHITE))
    return cmds


def _make_header_footer(title: str, subtitle: str = ""):
    """Returns (onFirstPage, onLaterPages) functions for BaseDocTemplate."""

    def _draw(canvas, doc):
        canvas.saveState()
        # Header
        header_y = PAGE_H - MARGIN + 6 * mm
        label    = title + (f"  ·  {subtitle}" if subtitle else "")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(PAGE_W - MARGIN, header_y, label)
        canvas.setStrokeColor(DARK)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, header_y - 2 * mm, PAGE_W - MARGIN, header_y - 2 * mm)

        # Footer
        footer_y = MARGIN - 8 * mm
        canvas.setStrokeColor(colors.HexColor("#D1D5DB"))
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, footer_y + 4 * mm, PAGE_W - MARGIN, footer_y + 4 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        page_str = f"Page {doc.page}  ·  For Official Use Only"
        canvas.drawCentredString(PAGE_W / 2, footer_y, page_str)
        canvas.restoreState()

    return _draw, _draw



def _section_heading(text: str) -> list:
    return [
        Paragraph(text, S_SECTION),
        HRFlowable(width=CONTENT_W, thickness=1, color=DARK, spaceAfter=6),
    ]


def _patrol_list_table(patrols: list) -> list:
    if not patrols:
        return [Paragraph("No patrols in this category.", S_BODY)]

    col_w = [
        CONTENT_W * 0.05,   # #
        CONTENT_W * 0.22,   # Patrol Name
        CONTENT_W * 0.17,   # Mobile Unit
        CONTENT_W * 0.20,   # Duration
        CONTENT_W * 0.10,   # Patrollers
        CONTENT_W * 0.26,   # Barangays
    ]

    header = ["#", "Patrol Name", "Mobile Unit", "Duration", "Patrollers", "Barangays"]

    def _row(p, i):
        barangays = ", ".join(sorted({
            r["barangay"]
            for r in (p.get("routes") or [])
            if (r.get("stop_order") or 0) <= 0 and r.get("barangay")
        })) or "—"
        count    = len({pt["active_patroller_id"] for pt in (p.get("patrollers") or [])})
        duration = f"{_fmt_date(p['start_date'])} – {_fmt_date(p['end_date'])}"
        return [str(i + 1), p["patrol_name"], p.get("mobile_unit_name") or "—",
                duration, str(count), barangays]

    data = [header] + [_row(p, i) for i, p in enumerate(patrols)]

    ts = (
        _header_ts(len(col_w))
        + _body_row_ts(len(data))
        + [
            ("ALIGN",    (0, 0), (0, -1),  "CENTER"),
            ("ALIGN",    (4, 0), (4, -1),  "CENTER"),
            ("FONTNAME", (1, 1), (1, -1),  "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0),  "Helvetica-Bold"),
        ]
    )

    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle(ts))
    return [t]


def export_patrol_list():
    try:
        body    = request.get_json(silent=True) or {}
        patrols = body.get("patrols") or []

        active    = [p for p in patrols if _patrol_status(p) == "active"]
        upcoming  = [p for p in patrols if _patrol_status(p) == "upcoming"]
        completed = [p for p in patrols if _patrol_status(p) == "completed"]

        now_str = _fmt_now()

        story = []

        # Cover
        story.append(Paragraph("PATROL SCHEDULING REPORT", S_TITLE))
        story.append(Paragraph(f"Generated: {now_str}", S_SUBTITLE))
        story.append(HRFlowable(width=CONTENT_W, thickness=2, color=DARK,
                                spaceBefore=8, spaceAfter=16))

        story += _section_heading("Summary")

        stat_w = [CONTENT_W * 0.65, CONTENT_W * 0.35]
        stat_data = [
            ["Total Patrols",  str(len(patrols))],
            ["Active",         str(len(active))],
            ["Upcoming",       str(len(upcoming))],
            ["Completed",      str(len(completed))],
        ]
        stat_ts = [
            ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("BACKGROUND",   (0, 1), (-1, 1),  GRAY),
            ("BACKGROUND",   (0, 3), (-1, 3),  GRAY),
            ("ALIGN",        (1, 0), (1, -1),  "CENTER"),
            ("FONTNAME",     (1, 0), (1, -1),  "Helvetica-Bold"),
            ("TEXTCOLOR",    (1, 1), (1, 1),   GREEN),   # active count
            ("TEXTCOLOR",    (1, 2), (1, 2),   DARK),    # upcoming count
            ("TEXTCOLOR",    (1, 3), (1, 3),   MED),     # completed count
        ]
        stat_t = Table(stat_data, colWidths=stat_w)
        stat_t.setStyle(TableStyle(stat_ts))
        story.append(stat_t)
        story.append(Spacer(1, 12))

        for label, subset in [
            (f"Active Patrols  ({len(active)})",    active),
            (f"Upcoming Patrols  ({len(upcoming)})", upcoming),
            (f"Completed Patrols  ({len(completed)})", completed),
        ]:
            story += _section_heading(label)
            story += _patrol_list_table(subset)
            story.append(Spacer(1, 12))

        buf       = io.BytesIO()
        on_page, _ = _make_header_footer("PATROL SCHEDULING REPORT")

        frame = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN - 18 * mm,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        tmpl  = PageTemplate(id="main", frames=[frame],
                              onPage=on_page, onPageEnd=on_page)
        doc   = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[tmpl],
                                 leftMargin=MARGIN, rightMargin=MARGIN,
                                 topMargin=MARGIN - 50 * mm,
                                 bottomMargin=MARGIN + 8 * mm)
        doc.build(story)

        pdf_bytes = buf.getvalue()
        date_str  = date.today().isoformat()

        log_audit(
            user_id  =g.user.get("user_id"),
            username =g.user.get("username"),
            event_name="Patrol List Exported",
            description=(
                f"Exported patrol list — {len(patrols)} patrol(s) "
                f"({len(active)} active, {len(upcoming)} upcoming, {len(completed)} completed)"
            ),
            action="EXPORT", status="success",
            source="Web Portal", ip_address=_get_ip(),
        )

        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"]        = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="patrol_list_{date_str}.pdf"'
        return resp

    except Exception as e:
        print(f"export_patrol_list error: {e}")
        try:
            log_audit(
                user_id  =g.user.get("user_id"),
                username =g.user.get("username"),
                event_name="Patrol List Export Failed",
                description=str(e),
                action="EXPORT", status="failed",
                source="Web Portal", ip_address=_get_ip(),
            )
        except Exception:
            pass
        return jsonify({"success": False, "message": str(e)}), 500


def _patrollers_table(patrollers: list) -> list:
    if not patrollers:
        return [Paragraph("No patrollers assigned.", S_BODY)]

    col_w = [
        CONTENT_W * 0.06,   # #
        CONTENT_W * 0.47,   # Officer Name
        CONTENT_W * 0.30,   # Contact
        CONTENT_W * 0.17,   # Shift
    ]

    header = ["#", "Officer Name", "Contact", "Shift"]

    def _row(p, i):
        shift = p.get("shift") or "—"
        return [str(i + 1), p.get("officer_name") or "—",
                p.get("contact_number") or "—", shift]

    data = [header] + [_row(p, i) for i, p in enumerate(patrollers)]

    shift_cmds = []
    for i, p in enumerate(patrollers, start=1):
        shift = p.get("shift") or ""
        color = DARK if shift == "AM" else AMBER
        shift_cmds.append(("TEXTCOLOR", (3, i), (3, i), color))

    ts = (
        _header_ts(len(col_w))
        + _body_row_ts(len(data))
        + shift_cmds
        + [
            ("ALIGN",    (0, 0), (0, -1),  "CENTER"),
            ("ALIGN",    (3, 0), (3, -1),  "CENTER"),
            ("FONTNAME", (1, 1), (1, -1),  "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
        ]
    )

    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle(ts))
    return [t]


def _timetable_table(tasks: list) -> list:
    if not tasks:
        return [Paragraph("No tasks scheduled.", S_BODY)]

    col_w = [CONTENT_W * 0.26, CONTENT_W * 0.74]
    header = ["Time", "Task / Notes"]

    def _row(r, i):
        time_str = f"{_fmt_time(r.get('time_start'))} — {_fmt_time(r.get('time_end'))}"
        return [time_str, r.get("notes") or "—"]

    data = [header] + [_row(r, i) for i, r in enumerate(tasks)]

    time_cmds = [("TEXTCOLOR", (0, i + 1), (0, i + 1), DARK) for i in range(len(tasks))]
    bold_time  = [("FONTNAME",  (0, i + 1), (0, i + 1), "Helvetica-Bold") for i in range(len(tasks))]

    ts = (
        _header_ts(len(col_w))
        + _body_row_ts(len(data))
        + time_cmds
        + bold_time
        + [("FONTSIZE", (0, 1), (-1, -1), 8)]
    )

    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle(ts))
    return [t]

def export_patrol_detail():
    try:
        body      = request.get_json(silent=True) or {}
        patrol    = body.get("patrol")
        map_image = body.get("mapImage")   # base64 PNG string (no data-URL prefix)

        if not patrol:
            return jsonify({"success": False, "message": "patrol is required"}), 400

        status       = _patrol_status(patrol)
        status_label = status.capitalize()
        status_color = _status_color(status)

        barangays = list({
            r["barangay"]
            for r in (patrol.get("routes") or [])
            if (r.get("stop_order") or 0) <= 0 and r.get("barangay")
        })

        date_range = _date_range(patrol["start_date"][:10], patrol["end_date"][:10])
        now_str    = _fmt_now()

        story = []

        # Cover
        story.append(Paragraph("PATROL DETAIL REPORT", S_TITLE))
        story.append(Paragraph(patrol["patrol_name"], _style("pname",
            fontName="Helvetica-Bold", fontSize=13, alignment=TA_CENTER,
            textColor=colors.black, spaceAfter=4)))
        story.append(Paragraph(f"Generated: {now_str}", S_SUBTITLE))
        story.append(HRFlowable(width=CONTENT_W, thickness=2, color=DARK,
                                spaceBefore=8, spaceAfter=16))

        story += _section_heading("1. Patrol Information")

        info_col_w = [CONTENT_W * 0.27, CONTENT_W * 0.73]
        info_rows  = [
            ("Patrol Name", patrol["patrol_name"]),
            ("Mobile Unit", patrol.get("mobile_unit_name") or "—"),
            ("Status",      status_label),
            ("Start Date",  _fmt_date(patrol["start_date"])),
            ("End Date",    _fmt_date(patrol["end_date"])),
            ("Barangays",   ", ".join(barangays) or "—"),
        ]

        info_cmds = [
            ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 0), (-1, -1), 9),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME",     (1, 0), (1, 0),   "Helvetica-Bold"),     # patrol name bold
            ("TEXTCOLOR",    (1, 2), (1, 2),   status_color),         # status colour
        ]

        for i in range(len(info_rows)):
            if i % 2 == 1:
                info_cmds.append(("BACKGROUND", (0, i), (-1, i), GRAY))

        info_t = Table([[k, v] for k, v in info_rows], colWidths=info_col_w)
        info_t.setStyle(TableStyle(info_cmds))
        story.append(info_t)
        story.append(Spacer(1, 12))

        story += _section_heading("2. Area of Responsibility")

        if map_image:
            # Strip optional data-URL prefix
            b64 = map_image.split(",", 1)[-1] if "," in map_image else map_image
            img_bytes  = base64.b64decode(b64)
            img_reader = ImageReader(io.BytesIO(img_bytes))
            img = Image(io.BytesIO(img_bytes), width=17 * cm, height=10 * cm)
            img.hAlign = "LEFT"
            story.append(img)
        else:
            story.append(Paragraph("Map image not available.", S_BODY))

        story.append(Paragraph(
            f"Barangays: {', '.join(barangays)}" if barangays else "No barangays assigned.",
            S_BODY,
        ))
        story.append(Spacer(1, 12))

        story += _section_heading("3. Assigned Patrollers")

        seen, unique_patrollers = set(), []
        for p in (patrol.get("patrollers") or []):
            key = (p.get("active_patroller_id"), p.get("shift"))
            if key not in seen:
                seen.add(key)
                unique_patrollers.append(p)

        story += _patrollers_table(unique_patrollers)
        story.append(Spacer(1, 12))

        story += _section_heading("4. Patrol Timetable")

        timetable_added = False
        for d in date_range:
            am_tasks = sorted(
                [r for r in (patrol.get("routes") or [])
                 if _to_date_str(r.get("route_date")) == d
                 and r.get("shift") == "AM"
                 and (r.get("stop_order") or 0) > 0],
                key=lambda r: r.get("stop_order") or 0,
            )
            pm_tasks = sorted(
                [r for r in (patrol.get("routes") or [])
                 if _to_date_str(r.get("route_date")) == d
                 and r.get("shift") == "PM"
                 and (r.get("stop_order") or 0) > 0],
                key=lambda r: r.get("stop_order") or 0,
            )

            if not am_tasks and not pm_tasks:
                continue

            timetable_added = True
            story.append(Paragraph(_fmt_date(d), S_SUBSECTION))

            if am_tasks:
                story.append(Paragraph("AM Shift", S_BODY))
                story += _timetable_table(am_tasks)
                story.append(Spacer(1, 6))
            if pm_tasks:
                story.append(Paragraph("PM Shift", S_BODY))
                story += _timetable_table(pm_tasks)
                story.append(Spacer(1, 6))

        if not timetable_added:
            story.append(Paragraph("No tasks scheduled for this patrol.", S_BODY))

        story.append(Spacer(1, 12))

        buf        = io.BytesIO()
        on_page, _ = _make_header_footer("PATROL DETAIL REPORT", patrol["patrol_name"])

        frame = Frame(MARGIN, MARGIN, CONTENT_W, PAGE_H - 2 * MARGIN - 18 * mm,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        tmpl  = PageTemplate(id="main", frames=[frame],
                              onPage=on_page, onPageEnd=on_page)
        doc   = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[tmpl],
                                 leftMargin=MARGIN, rightMargin=MARGIN,
                                 topMargin=MARGIN + 10 * mm,
                                 bottomMargin=MARGIN + 8 * mm)
        doc.build(story)

        pdf_bytes = buf.getvalue()
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in patrol["patrol_name"]
        )

        log_audit(
            user_id  =g.user.get("user_id"),
            username =g.user.get("username"),
            event_name="Patrol Detail Exported",
            description=f'Exported patrol detail — "{patrol["patrol_name"]}"',
            action="EXPORT", status="success",
            source="Web Portal", ip_address=_get_ip(),
        )

        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"]        = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="patrol_{safe_name}.pdf"'
        return resp

    except Exception as e:
        print(f"export_patrol_detail error: {e}")
        try:
            log_audit(
                user_id  =g.user.get("user_id"),
                username =g.user.get("username"),
                event_name="Patrol Detail Export Failed",
                description=str(e),
                action="EXPORT", status="failed",
                source="Web Portal", ip_address=_get_ip(),
            )
        except Exception:
            pass
        return jsonify({"success": False, "message": str(e)}), 500