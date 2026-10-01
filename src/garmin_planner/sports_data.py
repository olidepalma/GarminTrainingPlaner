"""Catálogo de pruebas y selección mínima de referencias Garmin."""

import math
from datetime import UTC, datetime, timedelta

DISTANCES = {
    "running": {
        "5k": ("5 km", "5 km"),
        "10k": ("10 km", "10 km"),
        "15k": ("15 km", "15 km"),
        "half": ("Media maratón", "21.0975 km"),
        "marathon": ("Maratón", "42.195 km"),
    },
    "triathlon": {
        "sprint": ("Sprint", "Natación 750 m / bici 20 km / carrera 5 km"),
        "olympic": ("Olímpico", "Natación 1500 m / bici 40 km / carrera 10 km"),
        "middle": ("Media distancia 70.3", "Natación 1900 m / bici 90 km / carrera 21.1 km"),
        "full": ("Larga distancia 140.6", "Natación 3800 m / bici 180 km / carrera 42.2 km"),
    },
    "swimming": {
        "400m": ("400 m", "400 m"),
        "800m": ("800 m", "800 m"),
        "1500m": ("1500 m", "1500 m"),
        "3000m": ("3000 m", "3000 m"),
    },
}

FIELDS = {
    "hr_zones": {
        **{f"zone{i}Floor": (f"Z{i} límite inferior", "ppm") for i in range(1, 6)},
        "maxHeartRate": ("FC máxima", "ppm"),
        "lactateThresholdHeartRate": ("FC umbral", "ppm"),
        "restingHeartRate": ("FC en reposo configurada", "ppm"),
    },
    "power_zones": {
        f"zone{i}Floor": (f"Z{i} límite inferior (valor Garmin)", "") for i in range(1, 8)
    },
    "ftp": {"functionalThresholdPower": ("FTP ciclismo", "W"), "ftp": ("FTP ciclismo", "W")},
    "threshold": {
        "heartRate": ("FC umbral de carrera", "ppm"),
        "heartRateCycling": ("FC umbral ciclismo", "ppm"),
    },
    "predictions": {
        "time5K": ("5 km", "s"),
        "raceTime5K": ("5 km", "s"),
        "time10K": ("10 km", "s"),
        "raceTime10K": ("10 km", "s"),
        "timeHalfMarathon": ("Media maratón", "s"),
        "raceTimeHalf": ("Media maratón", "s"),
        "timeMarathon": ("Maratón", "s"),
        "raceTimeMarathon": ("Maratón", "s"),
    },
    "vo2": {
        "vo2MaxPreciseValue": ("VO₂ máx.", "ml/kg/min"),
        "vo2MaxValue": ("VO₂ máx.", "ml/kg/min"),
    },
}


def extract_metrics(raw, category):
    """No conservar identificadores, rutas ni campos personales del proveedor."""
    rows = []

    def walk(value, inherited=None, depth=0):
        if depth > 8 or len(rows) >= 1000:
            return
        if isinstance(value, list):
            for item in value[:100]:
                walk(item, inherited, depth + 1)
        elif isinstance(value, dict):
            metadata = dict(inherited or {})
            sport = value.get("sport") or value.get("sportType") or value.get("sportTypeKey")
            if isinstance(sport, str):
                metadata["sport"] = sport[:40]
            for key in ("calendarDate", "date", "effectiveDate"):
                if isinstance(value.get(key), str):
                    metadata["measured_on"] = value[key][:10]
            for key, (label, unit) in FIELDS[category].items():
                number = value.get(key)
                if (
                    isinstance(number, (int, float))
                    and not isinstance(number, bool)
                    and math.isfinite(number)
                    and number > 0
                ):
                    rows.append(
                        {"field": key, "label": label, "value": number, "unit": unit, **metadata}
                    )
            for key, item in value.items():
                child = metadata
                if key in ("generic", "running", "cycling", "swimming"):
                    child = {**metadata, "sport": key}
                if isinstance(item, (dict, list)):
                    walk(item, child, depth + 1)

    walk(raw)
    if category == "predictions":
        unique = {}
        for row in rows:
            key = (row["label"], row.get("measured_on"), row.get("sport"))
            unique.setdefault(key, row)
        rows = list(unique.values())
    # Cuando Garmin incluye valor entero y preciso, preferir el preciso del mismo registro.
    if category == "vo2":
        rows = [
            r
            for r in rows
            if r["field"] != "vo2MaxValue"
            or not any(
                p["field"] == "vo2MaxPreciseValue"
                and p.get("sport") == r.get("sport")
                and p.get("measured_on") == r.get("measured_on")
                for p in rows
            )
        ]
    return sorted(rows, key=lambda r: r.get("measured_on", ""), reverse=True)[:60]


def sync_references(client, store, today):
    previous = store.get("garmin_references", {"groups": {}})
    groups = previous["groups"]
    requests = {
        "hr_zones": lambda: client.get_heart_rate_zones(),
        "power_zones": lambda: client.get_power_zones(),
        "ftp": lambda: client.get_cycling_ftp(),
        "threshold": lambda: client.get_lactate_threshold(),
        "predictions": lambda: client.get_race_predictions(),
        "vo2": lambda: client.get_max_metrics_range(
            (today - timedelta(days=30)).isoformat(), today.isoformat()
        ),
    }
    at = datetime.now(UTC).isoformat()
    failed = []
    for name, fetch in requests.items():
        try:
            raw = fetch()
            rows = extract_metrics(raw, name)
            groups[name] = {
                "rows": rows,
                "at": at,
                "status": "available" if rows else "unrecognized" if raw else "empty",
            }
        except Exception:
            groups[name] = {**groups.get(name, {"rows": [], "at": None}), "status": "failed"}
            failed.append(name)
    store.set("garmin_references", {"groups": groups, "attempt_at": at})
    return ["Algunas referencias deportivas de Garmin no se pudieron actualizar."] if failed else []


def coach_references(store):
    data = store.get("garmin_references", {"groups": {}})
    result = {}
    for name in ("hr_zones", "power_zones", "ftp", "threshold", "vo2", "predictions"):
        group = data["groups"].get(name, {"rows": [], "at": None, "status": "missing"})
        rows = group["rows"][:20]
        if name == "vo2":
            counts, rows = {}, []
            for row in group["rows"]:
                profile = row.get("sport", "unknown")
                if counts.get(profile, 0) < 2:
                    rows.append(row)
                    counts[profile] = counts.get(profile, 0) + 1
                if len(rows) == 12:
                    break
        result[name] = {**group, "rows": rows}
    return result
