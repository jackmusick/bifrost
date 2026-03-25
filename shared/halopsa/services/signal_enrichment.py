"""
Signal Enrichment Service for TimeKeeper

Deterministic matching and correlation logic for building a day's picture.
This is service code, not a tool. It gets called by the reconstruct_day tool
or by the agent to enrich raw signals with Halo context.

Key responsibilities:
- Build domain-to-client lookup from Halo users
- Match email senders/recipients to Halo clients
- Correlate timesheet entries against appointments
- Group emails by conversation thread
- Identify gaps, anomalies, and uncovered time blocks
- Normalize time to 5-minute increments
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from modules import halopsa

logger = logging.getLogger(__name__)


# =============================================================================
# Domain / Client Matching
# =============================================================================


async def build_domain_client_map(exclude_domains: Optional[list[str]] = None) -> dict[str, dict]:
    """Build a mapping of email domains to Halo clients.

    Queries all active Halo users and groups them by email domain.
    Internal domains are excluded by default (configure INTERNAL_DOMAINS below).

    Returns:
        Dict of domain -> {"client_id": int, "client_name": str}
    """
    exclude = set(d.lower() for d in (exclude_domains or list(INTERNAL_DOMAINS)))

    try:
        result = await halopsa.list_users(
            pageinate=True,
            page_size=500,
            page_no=1,
        )
    except Exception as e:
        logger.warning(f"Failed to fetch users for domain map: {e}")
        return {}

    users = []
    if isinstance(result, dict):
        users = result.get("users", [])
    elif hasattr(result, "users"):
        users = result.users or []

    domain_map = {}
    for user in users:
        user = user if isinstance(user, dict) else dict(user)
        email = (user.get("emailaddress") or "").lower()
        client_id = user.get("client_id")
        client_name = user.get("client_name", "")

        if not email or not client_id or "@" not in email:
            continue

        domain = email.split("@")[1]
        if domain in exclude:
            continue

        # First match wins per domain
        if domain not in domain_map:
            domain_map[domain] = {
                "client_id": client_id,
                "client_name": client_name,
            }

    logger.info(f"Built domain-client map with {len(domain_map)} domains")
    return domain_map


async def lookup_user_by_email(email: str) -> dict | None:
    """Look up a Halo user by exact email address.

    Uses the advanced_search filter on the users endpoint.

    Returns user dict with client_id, client_name, etc. or None.
    """
    try:
        result = await halopsa.list_users(
            advanced_search=f'[{{"filter_name":"emailaddress","filter_type":4,"filter_value":"{email}"}}]',
        )
    except Exception as e:
        logger.warning(f"Failed to look up user by email {email}: {e}")
        return None

    users = []
    if isinstance(result, dict):
        users = result.get("users", [])
    elif hasattr(result, "users"):
        users = result.users or []
    elif isinstance(result, list):
        users = result

    for user in users:
        user = user if isinstance(user, dict) else dict(user)
        user_email = (user.get("emailaddress") or "").lower()
        if user_email == email.lower():
            return user

    return None


# =============================================================================
# Time Helpers
# =============================================================================


def round_to_increment(hours: float, increment_minutes: int = 5) -> float:
    """Round time to nearest increment in hours.

    Args:
        hours: Time in hours.
        increment_minutes: Rounding increment in minutes. Default 5.

    Returns:
        Rounded time in hours. Returns 0 if rounding down from less than half an increment.
    """
    total_minutes = hours * 60
    rounded_minutes = round(total_minutes / increment_minutes) * increment_minutes
    return rounded_minutes / 60


def parse_dt(dt_str: str) -> datetime | None:
    """Parse an ISO datetime string, handling common formats."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def time_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """Check if two time ranges overlap."""
    s1, e1 = parse_dt(start1), parse_dt(end1)
    s2, e2 = parse_dt(start2), parse_dt(end2)
    if not all([s1, e1, s2, e2]):
        return False
    return s1 < e2 and s2 < e1


# =============================================================================
# Enrichment Functions
# =============================================================================


# Configure with your organization's internal email domains
INTERNAL_DOMAINS: set[str] = set()  # e.g., {"yourmsp.com", "yourdomain.net"}


def classify_email(email_entry: dict, domain_map: dict, user_lookups: dict | None = None) -> dict:
    """Classify a single email with client context.

    Args:
        email_entry: Email metadata from list_emails.
        domain_map: Domain-to-client mapping from build_domain_client_map.
        user_lookups: Optional dict of email -> user lookup results for
            addresses that weren't in the domain map. Populated by the
            caller after doing targeted lookups.

    Adds: client_match, is_internal, is_automated, thread_key
    """
    from_email = (email_entry.get("from_email") or "").lower()
    to_list = [t.lower() for t in (email_entry.get("to") or [])]
    subject = email_entry.get("subject") or ""
    user_lookups = user_lookups or {}

    # Determine if automated (newsletters, notifications, noreply)
    automated_indicators = [
        "noreply@", "no-reply@", "notifications@", "updates@",
        "mailer@", "newsletter@", "donotreply@",
    ]
    is_automated = any(ind in from_email for ind in automated_indicators)

    # Calendar accepts aren't real work
    if subject.startswith("Accepted:") or subject.startswith("Declined:") or subject.startswith("Tentative:"):
        is_automated = True

    # Check if all participants are internal
    all_addresses = [from_email] + to_list
    all_internal = all(
        any(addr.endswith(f"@{d}") for d in INTERNAL_DOMAINS)
        for addr in all_addresses if addr
    )

    # Try to match external domains to clients (domain map first, then user lookups)
    client_match = None
    for addr in all_addresses:
        if "@" not in addr:
            continue
        domain = addr.split("@")[1]
        if domain in INTERNAL_DOMAINS:
            continue
        if domain in domain_map:
            client_match = domain_map[domain]
            break
        if addr in user_lookups and user_lookups[addr]:
            u = user_lookups[addr]
            client_match = {
                "client_id": u.get("client_id"),
                "client_name": u.get("client_name", ""),
            }
            break

    return {
        **email_entry,
        "client_match": client_match,
        "is_internal": all_internal,
        "is_automated": is_automated,
        "thread_key": email_entry.get("conversation_id"),
    }


def group_email_threads(classified_emails: list[dict]) -> list[dict]:
    """Group emails by conversation thread into activity blocks.

    Returns one entry per thread with the time span and participant info.
    """
    threads = {}
    for email in classified_emails:
        if email.get("is_automated"):
            continue

        key = email.get("thread_key") or email.get("id")
        if key not in threads:
            threads[key] = {
                "subject": email.get("subject", ""),
                "first_time": email.get("sent") or email.get("received"),
                "last_time": email.get("sent") or email.get("received"),
                "email_count": 0,
                "client_match": email.get("client_match"),
                "is_internal": email.get("is_internal", False),
                "participants": set(),
            }

        thread = threads[key]
        thread["email_count"] += 1

        ts = email.get("sent") or email.get("received")
        if ts:
            if ts < thread["first_time"]:
                thread["first_time"] = ts
            if ts > thread["last_time"]:
                thread["last_time"] = ts

        for addr in [email.get("from_email")] + (email.get("to") or []):
            if addr:
                thread["participants"].add(addr.lower())

    # Convert sets to lists for serialization
    result = []
    for key, thread in threads.items():
        thread["participants"] = list(thread["participants"])
        thread["thread_key"] = key
        result.append(thread)

    result.sort(key=lambda t: t.get("first_time", ""))
    return result


def assess_timesheet(timesheet: dict) -> dict:
    """Analyze a timesheet for completeness and anomalies.

    Returns assessment with coverage_level, anomalies, and whether
    further signal investigation is needed.
    """
    target = timesheet.get("target_hours", 8.0)
    actual = timesheet.get("actual_hours", 0)
    unlogged = timesheet.get("unlogged_hours", target)
    events = timesheet.get("events", [])

    # Filter out obvious test entries (optional, could be configurable)
    anomalies = []

    for ev in events:
        tt = ev.get("timetaken", 0)
        # Runaway timer: anything over 10 hours on a single entry
        if tt > 10:
            anomalies.append({
                "type": "runaway_timer",
                "ticket_id": ev.get("ticket_id"),
                "subject": ev.get("subject"),
                "timetaken": tt,
                "message": f"Entry has {tt:.1f} hours logged, which seems excessive.",
            })
        # Micro entry: under 3 minutes (0.05 hours) that could be noise
        if 0 < tt < 0.05:
            anomalies.append({
                "type": "micro_entry",
                "ticket_id": ev.get("ticket_id"),
                "subject": ev.get("subject"),
                "timetaken": tt,
                "message": f"Entry is only {tt * 60:.0f} minutes. Consider absorbing into adjacent work.",
            })

    # Check for overlapping entries
    for i, ev1 in enumerate(events):
        for ev2 in events[i + 1:]:
            if time_overlap(
                ev1.get("start_date", ""), ev1.get("end_date", ""),
                ev2.get("start_date", ""), ev2.get("end_date", ""),
            ):
                anomalies.append({
                    "type": "overlap",
                    "entries": [ev1.get("subject"), ev2.get("subject")],
                    "message": "These time entries overlap.",
                })

    coverage = actual / target if target > 0 else 0

    if coverage >= 0.9:
        coverage_level = "complete"
        needs_signals = False
    elif coverage >= 0.5:
        coverage_level = "partial"
        needs_signals = True
    else:
        coverage_level = "sparse"
        needs_signals = True

    return {
        "coverage_level": coverage_level,
        "coverage_percent": round(coverage * 100, 1),
        "target_hours": target,
        "actual_hours": round(actual, 2),
        "unlogged_hours": round(unlogged, 2),
        "event_count": len(events),
        "anomalies": anomalies,
        "needs_signal_investigation": needs_signals,
    }


def correlate_appointments_to_timesheet(
    appointments: list[dict],
    timesheet_events: list[dict],
) -> list[dict]:
    """Check which appointments already have time logged on the timesheet.

    For each appointment, checks if a timesheet event covers the same
    time window (by overlapping start/end times). An appointment being
    marked complete (complete_status != -1) does NOT mean time is logged.
    The API completion doesn't reliably create timesheet events.

    Returns appointments enriched with coverage info.
    """
    enriched = []
    for appt in appointments:
        appt_start = appt.get("start_date", "")
        appt_end = appt.get("end_date", "")

        covered = False
        covering_event = None

        # Check if any timesheet event overlaps this appointment's window
        for ev in timesheet_events:
            if ev.get("event_type") == 1:
                continue  # Skip break/lunch entries
            if time_overlap(
                appt_start, appt_end,
                ev.get("start_date", ""), ev.get("end_date", ""),
            ):
                covered = True
                covering_event = ev.get("subject")
                break

        enriched.append({
            **appt,
            "time_covered": covered,
            "covered_by": covering_event,
            "is_completed": appt.get("complete_status") not in (-1, None),
        })

    return enriched


# =============================================================================
# Day Proposal / Normalization
# =============================================================================

# Gaps shorter than this (minutes) between blocks are treated as transition
# time and absorbed into the adjacent block rather than flagged as a break.
TRANSITION_GAP_THRESHOLD_MIN = 20

# Entries under this threshold (minutes) are considered micro entries.
MICRO_ENTRY_THRESHOLD_MIN = 5

# All durations round to this increment.
ROUND_INCREMENT_MIN = 5

# Provider org name for identifying internal work.
# Configure with your MSP's name as it appears in HaloPSA
PROVIDER_ORG = ""  # e.g., "Your MSP, Inc."


def _is_client_facing(block: dict) -> bool:
    """Return True if a block is billable or client-facing (not internal)."""
    customer = (block.get("customer") or "").strip()
    charge_type = (block.get("charge_type") or "").strip()
    # If it has a non-provider customer, it's client-facing
    if customer and customer != PROVIDER_ORG:
        return True
    # If charge type is explicitly billable
    if charge_type and charge_type not in ("No Charge", ""):
        return True
    # If it's a proposed block with a client name
    if block.get("client_name"):
        return True
    return False


def propose_day(reconstruct_result: dict) -> dict:
    """Build a proposed timeline from reconstruct_day output.

    Takes the raw signals (timesheet, appointments, emails) and produces
    an ordered list of time blocks that, if executed, would fill the day
    cleanly with no overlaps, no gaps, and proper rounding.

    The proposal includes:
    - actions: list of concrete steps to execute (complete_appointment,
      log_quicktime, adjust_time_entry, delete_break_entry, etc.)
    - timeline: the proposed final timeline for display
    - questions: anything ambiguous that needs human input

    This is pure logic. No API calls.
    """
    ts_events = reconstruct_result.get("timesheet_events", [])
    appts_data = reconstruct_result.get("appointments", {}) or {}
    uncovered_appts = appts_data.get("uncovered", [])
    email_threads = reconstruct_result.get("email_threads", []) or []
    assessment = reconstruct_result.get("assessment", {})
    target_hours = assessment.get("target_hours", 8.0)

    # Build a unified list of all time blocks (existing + proposed)
    blocks = []

    # Existing timesheet events become fixed blocks
    for ev in ts_events:
        start = parse_dt(ev.get("start_date", ""))
        end = parse_dt(ev.get("end_date", ""))
        if not start or not end:
            continue
        blocks.append({
            "source": "existing",
            "type": "break" if ev.get("event_type") == 1 else "work",
            "subject": ev.get("subject", ""),
            "start": start,
            "end": end,
            "timetaken": ev.get("timetaken", 0),
            "ticket_id": ev.get("ticket_id"),
            "action_number": ev.get("action_number"),
            "event_id": ev.get("id"),
            "customer": ev.get("customer", ""),
            "break_type": ev.get("break_type", 0),
        })

    # Uncovered appointments become proposed blocks
    for appt in uncovered_appts:
        start = parse_dt(appt.get("start_date", ""))
        end = parse_dt(appt.get("end_date", ""))
        if not start or not end:
            continue
        duration_hrs = (end - start).total_seconds() / 3600
        blocks.append({
            "source": "proposed",
            "type": "work",
            "subject": appt.get("subject", ""),
            "start": start,
            "end": end,
            "timetaken": round_to_increment(duration_hrs),
            "appointment_id": appt.get("id"),
            "client_name": appt.get("client_name"),
            "attendees": appt.get("attendees", ""),
        })

    # Sort by start time
    blocks.sort(key=lambda b: b["start"])

    # --- Normalization pass ---
    actions = []
    questions = []
    normalized = []

    for i, block in enumerate(blocks):
        # Round all durations to 5-min increments
        original_time = block["timetaken"]
        rounded_time = round_to_increment(original_time)
        is_client = _is_client_facing(block)

        # Client-facing entries always round UP to at least 5 min
        if is_client and rounded_time < ROUND_INCREMENT_MIN / 60:
            rounded_time = ROUND_INCREMENT_MIN / 60

        # Micro entries (under 5 min actual) in transition gaps
        actual_minutes = original_time * 60
        if 0 < actual_minutes < MICRO_ENTRY_THRESHOLD_MIN and block["source"] == "existing":
            prev_end = normalized[-1]["end"] if normalized else None
            next_start = blocks[i + 1]["start"] if i + 1 < len(blocks) else None

            if prev_end and next_start:
                gap_before = (block["start"] - prev_end).total_seconds() / 60
                gap_after = (next_start - block["end"]).total_seconds() / 60
                total_gap = gap_before + gap_after + actual_minutes

                if total_gap <= TRANSITION_GAP_THRESHOLD_MIN:
                    # Round the micro entry up to 5 min minimum
                    if rounded_time < ROUND_INCREMENT_MIN / 60:
                        rounded_time = ROUND_INCREMENT_MIN / 60

                    if block.get("action_number") and block.get("ticket_id"):
                        actions.append({
                            "action": "adjust_time_entry",
                            "reason": f"Round {actual_minutes:.0f}-min entry to {rounded_time * 60:.0f} min",
                            "params": {
                                "action_id": block["action_number"],
                                "ticket_id": block["ticket_id"],
                                "timetaken": rounded_time,
                            },
                        })

                    # Close the gap. Who absorbs the transition cost?
                    if gap_before > 0 and normalized:
                        prev = normalized[-1]
                        if is_client and not _is_client_facing(prev):
                            # Client-facing micro entry: internal block absorbs gap
                            new_prev_time = round_to_increment(
                                prev["timetaken"] + gap_before / 60
                            )
                            if prev["source"] == "existing" and prev.get("action_number") and prev.get("ticket_id"):
                                actions.append({
                                    "action": "adjust_time_entry",
                                    "reason": f"Extend internal '{prev['subject']}' by {gap_before:.0f} min (transition to client work)",
                                    "params": {
                                        "action_id": prev["action_number"],
                                        "ticket_id": prev["ticket_id"],
                                        "timetaken": new_prev_time,
                                    },
                                })
                            prev["end"] = block["start"]
                            prev["timetaken"] = new_prev_time
                        elif not is_client:
                            # Internal micro entry: extend previous block
                            new_prev_time = round_to_increment(
                                prev["timetaken"] + gap_before / 60
                            )
                            if prev["source"] == "existing" and prev.get("action_number") and prev.get("ticket_id"):
                                actions.append({
                                    "action": "adjust_time_entry",
                                    "reason": f"Extend '{prev['subject']}' by {gap_before:.0f} min to close transition gap",
                                    "params": {
                                        "action_id": prev["action_number"],
                                        "ticket_id": prev["ticket_id"],
                                        "timetaken": new_prev_time,
                                    },
                                })
                            prev["end"] = block["start"]
                            prev["timetaken"] = new_prev_time
                        else:
                            # Both client-facing (different clients): ask
                            questions.append({
                                "type": "billable_transition",
                                "start": prev["end"].strftime("%Y-%m-%dT%H:%M:%S"),
                                "end": block["start"].strftime("%Y-%m-%dT%H:%M:%S"),
                                "duration_minutes": gap_before,
                                "from_customer": prev.get("customer", ""),
                                "to_customer": block.get("customer", ""),
                                "message": (
                                    f"{gap_before:.0f}-min gap between two client entries. "
                                    f"Which client should absorb the transition?"
                                ),
                            })

                    block["timetaken"] = rounded_time
                    normalized.append(block)
                    continue

        # Normal rounding for everything else
        if rounded_time != original_time and block["source"] == "existing":
            if block.get("action_number") and block.get("ticket_id"):
                actions.append({
                    "action": "adjust_time_entry",
                    "reason": f"Round from {original_time * 60:.1f} min to {rounded_time * 60:.0f} min",
                    "params": {
                        "action_id": block["action_number"],
                        "ticket_id": block["ticket_id"],
                        "timetaken": rounded_time,
                    },
                })

        block["timetaken"] = rounded_time

        # For proposed blocks (uncovered appointments), generate actions
        if block["source"] == "proposed":
            actions.append({
                "action": "complete_appointment",
                "reason": f"Mark '{block['subject']}' as done",
                "params": {
                    "appointment_id": block["appointment_id"],
                    "timetaken": block["timetaken"],
                    "note": block["subject"],
                },
            })
            actions.append({
                "action": "log_quicktime",
                "reason": f"Log {block['timetaken']:.2f} hrs for '{block['subject']}'",
                "params": {
                    "start_date": block["start"].strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "end_date": block["end"].strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "note": block["subject"],
                    "entry_type": "work",
                },
            })

        normalized.append(block)

    # --- Gap detection pass ---
    # Walk the normalized timeline and find gaps that need filling
    for i in range(len(normalized) - 1):
        current_end = normalized[i]["end"]
        next_start = normalized[i + 1]["start"]
        gap_minutes = (next_start - current_end).total_seconds() / 60

        if gap_minutes <= 0:
            continue  # No gap or overlap

        if gap_minutes <= TRANSITION_GAP_THRESHOLD_MIN:
            # Small gap, extend the previous block
            prev = normalized[i]
            new_time = round_to_increment(prev["timetaken"] + gap_minutes / 60)
            if prev["source"] == "existing" and prev.get("action_number") and prev.get("ticket_id"):
                actions.append({
                    "action": "adjust_time_entry",
                    "reason": f"Extend '{prev['subject']}' by {gap_minutes:.0f} min to close small gap",
                    "params": {
                        "action_id": prev["action_number"],
                        "ticket_id": prev["ticket_id"],
                        "timetaken": new_time,
                    },
                })
            prev["end"] = next_start
            prev["timetaken"] = new_time
        else:
            # Larger gap, need human input
            gap_hours = round_to_increment(gap_minutes / 60)
            questions.append({
                "type": "unaccounted_gap",
                "start": current_end.strftime("%Y-%m-%dT%H:%M:%S"),
                "end": next_start.strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_hours": gap_hours,
                "after": normalized[i]["subject"],
                "before": normalized[i + 1]["subject"],
                "message": (
                    f"{gap_minutes:.0f}-minute gap between "
                    f"'{normalized[i]['subject']}' and '{normalized[i + 1]['subject']}'. "
                    f"Was this a break, lunch, or other work?"
                ),
            })

    # Build the display timeline
    timeline = []
    for block in normalized:
        timeline.append({
            "start": block["start"].strftime("%Y-%m-%dT%H:%M:%S"),
            "end": block["end"].strftime("%Y-%m-%dT%H:%M:%S"),
            "subject": block["subject"],
            "hours": block["timetaken"],
            "type": block["type"],
            "source": block["source"],
            "customer": block.get("customer", ""),
        })

    total_proposed = sum(b["timetaken"] for b in normalized if b["type"] == "work")
    total_break = sum(b["timetaken"] for b in normalized if b["type"] == "break")

    return {
        "timeline": timeline,
        "actions": actions,
        "questions": questions,
        "summary": {
            "total_work_hours": round(total_proposed, 2),
            "total_break_hours": round(total_break, 2),
            "target_hours": target_hours,
            "action_count": len(actions),
            "question_count": len(questions),
        },
    }
