"""Calendario local: propuestas aceptadas, actividad real y competiciones."""

import calendar
from datetime import date

from garmin_planner.workouts import session_key


def month_calendar(store, year, month, workouts=None):
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    entries = []
    for activity in store.activities(start.isoformat(), end.isoformat()):
        entries.append(
            {
                "id": "garmin-" + activity["id"],
                "kind": "completed",
                "day": activity["day"],
                "sport": activity["sport"],
                "title": activity["name"],
                "detail": activity,
            }
        )
    if workouts:
        for workout in workouts.list(start.isoformat(), end.isoformat()):
            entries.append(
                {
                    "id": "manual-" + workout["id"],
                    "kind": "planned",
                    "origin": "manual",
                    "day": workout["day"],
                    "sport": workout["sport"],
                    "title": workout["title"],
                    "detail": workout,
                }
            )
    accepted = store.get("coach_accepted")
    profile = (store.get("coach_setup") or {}).get("profile", {})
    for i, session in enumerate(store.get("coach_calendar", [])):
        if start.isoformat() <= session["day"] <= end.isoformat():
            slot = session.get("slot")
            # El perfil vigente puede haber cambiado; no inventar horarios antiguos.
            period = None
            if accepted and session in accepted["plan"]["sessions"] and accepted["setup_hash"]:
                from garmin_planner.coach import fingerprint

                if accepted["setup_hash"] == fingerprint(store.get("coach_setup")):
                    slots = profile.get("slots")
                    if (
                        slots
                        and slot is not None
                        and slot < len(slots[date.fromisoformat(session["day"]).weekday()])
                    ):
                        period = slots[date.fromisoformat(session["day"]).weekday()][slot]["period"]
            entries.append(
                {
                    "id": f"planned-{i}",
                    "kind": "planned",
                    "day": session["day"],
                    "sport": session["sport"],
                    "title": session["title"],
                    "origin": "coach",
                    "detail": {**session, "period": period, "source_key": session_key(session)},
                }
            )
    draft = store.get("coach_draft")
    if draft:
        from garmin_planner.coach import fingerprint

        if draft["setup_hash"] == fingerprint(store.get("coach_setup")):
            for i, session in enumerate(draft["plan"]["sessions"]):
                if start.isoformat() <= session["day"] <= end.isoformat():
                    entries.append(
                        {
                            "id": f"draft-{i}",
                            "kind": "planned",
                            "is_draft": True,
                            "day": session["day"],
                            "sport": session["sport"],
                            "title": session["title"],
                            "detail": {**session, "source_key": session_key(session)},
                        }
                    )
    for event in (store.get("coach_setup") or {}).get("events", []):
        if start.isoformat() <= event["day"] <= end.isoformat():
            entries.append(
                {
                    "id": "race-" + event["id"],
                    "kind": "race",
                    "day": event["day"],
                    "sport": event["sport"],
                    "title": event["name"],
                    "detail": event,
                }
            )
    return {
        "from": start.isoformat(),
        "through": end.isoformat(),
        "entries": sorted(entries, key=lambda e: (e["day"], e["kind"], e["id"])),
    }
