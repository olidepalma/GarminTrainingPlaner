"""Resumen reproducible de semanas completas; volumen no equivale a carga fisiológica."""

from collections import defaultdict
from datetime import date, timedelta

from pydantic import BaseModel, Field


class Feedback(BaseModel):
    week_start: date
    fatigue: int | None = Field(default=None, ge=1, le=5)
    effort: int | None = Field(default=None, ge=1, le=10)
    notes: str = Field(default="", max_length=1500)


def totals(store, begin, end):
    grouped = defaultdict(lambda: {"sessions": 0, "minutes": 0, "km": 0, "elevation_m": 0})
    for a in store.activities(begin.isoformat(), end.isoformat()):
        g = grouped[a["sport"]]
        g["sessions"] += 1
        g["minutes"] += round(a.get("duration_seconds", 0) / 60, 1)
        g["km"] += a.get("distance_m", 0) / 1000
        g["elevation_m"] += a.get("elevation_m", 0)
    return {sport: {k: round(v, 1) for k, v in values.items()} for sport, values in grouped.items()}


def weekly_review(store, today):
    end, begin = today - timedelta(days=1), today - timedelta(days=7)
    actual = totals(store, begin, end)
    planned = defaultdict(lambda: {"sessions": 0, "minutes": 0})
    from garmin_planner.workouts import Workouts

    proposals = store.get("coach_calendar", []) + Workouts(store, None).list(
        begin.isoformat(), end.isoformat()
    )
    for s in proposals:
        if begin.isoformat() <= s["day"] <= end.isoformat():
            planned[s["sport"]]["sessions"] += 1
            planned[s["sport"]]["minutes"] += s["minutes"]
    history = [
        totals(store, begin - timedelta(days=7 * i), end - timedelta(days=7 * i))
        for i in range(1, 5)
    ]
    sports = {}
    for sport in sorted(set(actual) | set(planned) | {s for week in history for s in week}):
        previous = [week[sport]["minutes"] for week in history if sport in week]
        baseline = round(sum(previous) / len(previous), 1) if previous else None
        sports[sport] = {
            "planned": planned.get(sport, {"sessions": 0, "minutes": 0}),
            "actual": actual.get(sport, {"sessions": 0, "minutes": 0, "km": 0, "elevation_m": 0}),
            "prior_active_weeks": len(previous),
            "prior_active_week_mean_minutes": baseline,
            "volume_change_percent": round(
                (actual.get(sport, {}).get("minutes", 0) / baseline - 1) * 100, 1
            )
            if baseline
            else None,
        }
    sync = store.get("sync")
    return {
        "from": begin.isoformat(),
        "through": end.isoformat(),
        "sports": sports,
        "feedback": store.get("coach_feedback", {}).get(begin.isoformat()),
        "last_activity_sync": sync,
        "recent_feedback": [
            v
            for k, v in sorted(store.get("coach_feedback", {}).items())[-4:]
            if (today - timedelta(days=42)).isoformat() <= k < today.isoformat()
        ],
        "limitations": (
            "Volumen registrado, no TSS ni carga fisiológica. La ausencia de una actividad "
            "no demuestra una sesión incumplida. No se emparejan automáticamente sesiones. "
            "La media usa solo semanas con registros de esa disciplina; semanas vacías "
            "pueden ser descanso o datos ausentes."
        ),
    }
