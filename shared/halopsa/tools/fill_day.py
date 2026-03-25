"""
TimeKeeper Day Fill Tool

Takes a confirmed day plan (array of time blocks) and executes all
the necessary Halo API calls to fill the timesheet in one shot.

This is the "do it" tool. The agent calls reconstruct_day first to
get the picture, confirms the plan with the user, then calls fill_day
to execute everything at once.
"""

import logging
from typing import Optional

from bifrost import tool, UserError
from modules import halopsa

from shared.halopsa.tools.timeentry import (
    _resolve_caller_agent,
    _agent_fields,
    _extract_result,
)

logger = logging.getLogger(__name__)


@tool(
    description=(
        "Fill a timesheet by executing a confirmed day plan in one shot. Takes an "
        "array of time blocks, each specifying what to log. Handles work entries "
        "(via QuickTime), break/lunch entries, appointment completions, and time "
        "adjustments to existing entries. Call reconstruct_day first to build the "
        "plan, confirm it with the user, then pass the confirmed blocks here.\n\n"
        "Each block needs: action (one of 'log', 'break', 'lunch', 'complete', "
        "'adjust'), start, end, and note. Optional fields: client_id (for client-"
        "facing work), appointment_id (for 'complete' action), action_id + ticket_id "
        "(for 'adjust' action).\n\n"
        "The calling agent is resolved automatically."
    ),
)
async def fill_day(
    blocks: list[dict],
) -> dict:
    """Execute a day plan by creating all time entries at once.

    Args:
        blocks: Array of time block objects. Each block has:
            - action: "log" | "break" | "lunch" | "complete" | "adjust"
            - start: Start time ISO string (e.g. "2026-03-18T14:00:00.000Z")
            - end: End time ISO string
            - note: Description of the work
            - client_id: (optional) Halo client ID for client-facing work
            - appointment_id: (optional) Required for "complete" action
            - action_id: (optional) Required for "adjust" action
            - ticket_id: (optional) Required for "adjust" action
            - timetaken: (optional) Override for "adjust" action duration in hours
    """
    if not blocks:
        raise UserError("No blocks provided. Nothing to do.")

    agent = await _resolve_caller_agent()
    agent_id_str = str(agent["id"])
    agent_name = agent["name"]

    results = []
    errors = []

    for i, block in enumerate(blocks):
        action = block.get("action", "log")
        start = block.get("start", "")
        end = block.get("end", "")
        note = block.get("note", "")
        client_id = block.get("client_id")
        appointment_id = block.get("appointment_id")
        action_id = block.get("action_id")
        ticket_id = block.get("ticket_id")
        timetaken_override = block.get("timetaken")

        try:
            if action == "complete":
                # Complete appointment + log quicktime
                if not appointment_id:
                    errors.append({"index": i, "error": "complete action requires appointment_id"})
                    continue

                # Calculate timetaken from start/end
                from datetime import datetime
                s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                e = datetime.fromisoformat(end.replace("Z", "+00:00"))
                timetaken = timetaken_override or (e - s).total_seconds() / 3600

                # Fetch and complete the appointment
                try:
                    appt = await halopsa.get_appointment(str(appointment_id))
                    appt = appt if isinstance(appt, dict) else dict(appt) if appt else {}
                except Exception:
                    appt = {}

                note_html = f"<p>{note}</p>" if note and not note.strip().startswith("<") else (note or "")

                appt_payload = {
                    "id": appointment_id,
                    "subject": appt.get("subject", note),
                    "start_date": appt.get("start_date"),
                    "end_date": appt.get("end_date"),
                    "allday": appt.get("allday", False),
                    "is_private": appt.get("is_private", False),
                    "agents": [{"id": agent["id"], "name": agent_name, "use": "agent"}],
                    "user_id": appt.get("user_id", -1),
                    "ticket_id": appt.get("ticket_id", -1),
                    "reminderminutes": 0,
                    "agent_status": 1,
                    "note_html": appt.get("note_html") or "",
                    "is_task": appt.get("is_task", False),
                    "appointment_type_id": appt.get("appointment_type_id", 0),
                    "shift_type_id": appt.get("shift_type_id", 0),
                    "followup_start_date": appt.get("start_date"),
                    "followup_end_date": appt.get("end_date"),
                    "followup_allday": appt.get("allday", False),
                    "followup_is_private": appt.get("is_private", False),
                    "followup_user_id": appt.get("user_id", -1),
                    "followup_reminderminutes": 0,
                    "followup_agent_status": 1,
                    "followup_note_html": appt.get("note_html") or "",
                    "followup_agent_id": agent["id"],
                    "complete_status": "0",
                    "chargerate": "0",
                    "complete_date": end.replace(".000Z", "").replace("Z", ""),
                    "complete_timetaken": timetaken,
                    "complete_notehtml": note_html,
                    "complete_agent_id": agent["id"],
                    "utcoffset": 240,
                    "apfaultidremoved": appt.get("ticket_id") in (None, -1),
                    "agent_id": agent["id"],
                }

                await halopsa.create_appointment([appt_payload])

                # Also log the quicktime entry for the timesheet
                qt_data = {
                    "end_date": end,
                    "start_date": start,
                    "ticket_id": None,
                    "tickettype_id": None,
                    "lognewticket": False,
                    "client_id": client_id,
                    "agent_id": agent_id_str,
                    "agents": [{"id": agent_id_str, "name": agent_name}],
                    "event_type": 0,
                    "charge_rate": 0,
                    "note": note,
                    "subject": f"Quick Time - {agent_name} - {note[:50]}",
                }
                await halopsa.create_timesheet_event([qt_data])

                results.append({"index": i, "action": "complete", "note": note, "hours": round(timetaken, 2)})

            elif action in ("break", "lunch"):
                break_type = "2" if action == "lunch" else "1"
                label = "Lunch" if action == "lunch" else "Break"

                event_data = {
                    "end_date": end,
                    "start_date": start,
                    "ticket_id": None,
                    "tickettype_id": None,
                    "lognewticket": False,
                    "client_id": None,
                    "agent_id": agent_id_str,
                    "agents": [{"id": agent_id_str, "name": agent_name}],
                    "event_type": 1,
                    "break_type": break_type,
                    "break_note": note or label,
                    "subject": f"{label} - {agent_name}",
                }
                await halopsa.create_timesheet_event([event_data])

                results.append({"index": i, "action": action, "note": note or label})

            elif action == "adjust":
                if not action_id or not ticket_id:
                    errors.append({"index": i, "error": "adjust action requires action_id and ticket_id"})
                    continue

                from datetime import datetime
                s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                e = datetime.fromisoformat(end.replace("Z", "+00:00"))
                timetaken = timetaken_override or (e - s).total_seconds() / 3600

                action_data = {
                    "id": action_id,
                    "ticket_id": ticket_id,
                    **_agent_fields(agent),
                    "timetaken": timetaken,
                    "actionarrivaldate": start,
                    "actioncompletiondate": end,
                }
                await halopsa.create_actions([action_data])

                results.append({"index": i, "action": "adjust", "note": note, "hours": round(timetaken, 2)})

            else:
                # Default: log work via quicktime
                event_data = {
                    "end_date": end,
                    "start_date": start,
                    "ticket_id": None,
                    "tickettype_id": None,
                    "lognewticket": False,
                    "client_id": client_id,
                    "agent_id": agent_id_str,
                    "agents": [{"id": agent_id_str, "name": agent_name}],
                    "event_type": 0,
                    "charge_rate": 0,
                    "note": note,
                    "subject": f"Quick Time - {agent_name} - {note[:50]}",
                }
                await halopsa.create_timesheet_event([event_data])

                results.append({"index": i, "action": "log", "note": note, "client_id": client_id})

        except Exception as e:
            logger.error(f"Failed to execute block {i} ({action}): {e}")
            errors.append({"index": i, "action": action, "note": note, "error": str(e)[:200]})

    return {
        "completed": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors if errors else None,
    }
