import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
import random

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# -------------------------------------------------
# Tagesphasen
# -------------------------------------------------
def day_phase(dt: datetime) -> str:
    h = dt.hour
    if 5 <= h < 9:
        return "morning"
    if 9 <= h < 17:
        return "day"
    if 17 <= h < 23:
        return "evening"
    return "night"


# -------------------------------------------------
# Recorder History laden
# -------------------------------------------------
def fetch_history(entity_id: str, days: int):
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    r = requests.get(
        f"{HA_URL}/history/period/{start.isoformat()}",
        headers=HEADERS,
        params={
            "filter_entity_id": entity_id,
            "minimal_response": "1"
        },
        timeout=20
    )
    r.raise_for_status()
    return r.json()[0] if r.json() else []


# -------------------------------------------------
# Laufzeiten aus Historie extrahieren
# -------------------------------------------------
def extract_on_durations(history):
    durations = defaultdict(list)
    last_on = None
    last_phase = None

    for e in history:
        try:
            ts = datetime.fromisoformat(e["last_changed"])
        except Exception:
            continue

        if e["state"] == "on":
            last_on = ts
            last_phase = day_phase(ts)

        elif e["state"] == "off" and last_on:
            minutes = int((ts - last_on).total_seconds() / 60)
            if 1 <= minutes <= 300:
                durations[last_phase].append(minutes)
            last_on = None
            last_phase = None

    return durations


# -------------------------------------------------
# Gelerntes Laufzeit-Modell
# -------------------------------------------------
def learned_runtime(durations, phase: str) -> int:
    values = durations.get(phase, [])

    if len(values) >= 3:
        base = int(statistics.median(values))
        jitter = random.randint(-5, 5)
        return max(3, base + jitter)

    # Fallbacks
    if phase == "morning":
        return random.randint(5, 15)
    if phase == "evening":
        return random.randint(25, 60)

    return random.randint(10, 30)
