# ================================================================================
# FILE: backend/jobs/referral_reminder_job.py
# ================================================================================

import asyncio
from datetime import datetime, timezone

import config.database as db
from features.notifications.notification_service import (
    notify_patrols_for_referral,
    notify_all_by_role,
    get_responder_for_referral,
)


PATROL_REMINDER_MINUTES = 15
ADMIN_REMINDER_MINUTES  = 30


def get_pool():
    if db.pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db.pool


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Reminder tasks ────────────────────────────────────────────────────────────

async def _send_patrol_reminder(blotter_id, blotter_entry_number: str, barangay: str):
    try:
        responder = await get_responder_for_referral(blotter_id)
        if responder:
            return

        link = f"/e-blotter?referral={blotter_id}"
        already_sent = await get_pool().fetchrow(
            "SELECT 1 FROM notifications "
            "WHERE type = 'REFERRAL_AUTO_REMINDER' AND link_to = $1 LIMIT 1",
            link,
        )
        if already_sent:
            return

        await notify_patrols_for_referral(
            barangay,
            {
                "senderId":   None,
                "senderName": "B.A.N.T.A.Y System",
                "type":       "REFERRAL_AUTO_REMINDER",
                "title":      "Unresponded Referral",
                "message":    (
                    f"Referral #{blotter_entry_number} in Brgy. {barangay} "
                    f"has had no response for {PATROL_REMINDER_MINUTES} minutes."
                ),
                "linkTo": link,
            },
        )
        print(f"[ReminderJob] {PATROL_REMINDER_MINUTES}-min patrol reminder sent for {blotter_entry_number}")

    except Exception as err:
        print(f"[ReminderJob] Patrol reminder error: {err}")


async def _send_admin_escalation(blotter_id, blotter_entry_number: str, barangay: str):
    try:
        responder = await get_responder_for_referral(blotter_id)
        if responder:
            return

        link = f"/e-blotter?referral={blotter_id}"
        already_sent = await get_pool().fetchrow(
            "SELECT 1 FROM notifications "
            "WHERE type = 'REFERRAL_ADMIN_ESCALATION' AND link_to = $1 LIMIT 1",
            link,
        )
        if already_sent:
            return

        await notify_all_by_role(
            ["Administrator", "Technical Administrator"],
            {
                "senderId":   None,
                "senderName": "B.A.N.T.A.Y System",
                "type":       "REFERRAL_ADMIN_ESCALATION",
                "title":      "Referral Needs Attention",
                "message":    (
                    f"Referral #{blotter_entry_number} in Brgy. {barangay} "
                    f"still has no responder after {ADMIN_REMINDER_MINUTES} minutes. "
                    f"Please remind a patrol officer."
                ),
                "linkTo": link,
            },
            None,
        )
        print(f"[ReminderJob] {ADMIN_REMINDER_MINUTES}-min admin escalation sent for {blotter_entry_number}")

    except Exception as err:
        print(f"[ReminderJob] Admin escalation error: {err}")


async def _delayed(seconds: float, coro):
    """Wait `seconds` then run `coro`. Negative delays are clamped to 0."""
    if seconds > 0:
        await asyncio.sleep(seconds)
    await coro


# ── Public API ────────────────────────────────────────────────────────────────

def schedule_referral_reminders(
    blotter_id,
    blotter_entry_number: str,
    barangay: str,
    patrol_delay: float | None = None,
    admin_delay:  float | None = None,
):
    patrol_secs = (patrol_delay if patrol_delay is not None else PATROL_REMINDER_MINUTES * 60)
    admin_secs  = (admin_delay  if admin_delay  is not None else ADMIN_REMINDER_MINUTES  * 60)

    loop = asyncio.get_event_loop()

    loop.create_task(
        _delayed(patrol_secs, _send_patrol_reminder(blotter_id, blotter_entry_number, barangay))
    )
    loop.create_task(
        _delayed(admin_secs, _send_admin_escalation(blotter_id, blotter_entry_number, barangay))
    )

    print(f"[ReminderJob] Reminders scheduled for referral {blotter_entry_number}")


async def recover_pending_referrals():
    try:
        rows = await get_pool().fetch(
            f"""
            SELECT blotter_id, blotter_entry_number, place_barangay, created_at
            FROM blotter_entries
            WHERE referred_by_barangay = true
              AND status = 'Pending'
              AND is_deleted = false
              AND created_at >= NOW() - INTERVAL '{ADMIN_REMINDER_MINUTES} minutes'
            """
        )

        now = now_utc()

        for blotter in rows:
            created_at = blotter["created_at"]
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            age_secs     = (now - created_at).total_seconds()
            patrol_delay = max(0.0, PATROL_REMINDER_MINUTES * 60 - age_secs)
            admin_delay  = max(0.0, ADMIN_REMINDER_MINUTES  * 60 - age_secs)

            schedule_referral_reminders(
                blotter["blotter_id"],
                blotter["blotter_entry_number"],
                blotter["place_barangay"],
                patrol_delay,
                admin_delay,
            )
            print(f"[ReminderJob] Recovered referral {blotter['blotter_entry_number']}")

        print(f"[ReminderJob] Recovery complete — {len(rows)} referral(s) recovered")

    except Exception as err:
        print(f"[ReminderJob] Recovery error: {err}")