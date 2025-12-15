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

# -------------------------
# Zeit-Phasen
# -------------------------
def day_phase(dt):
    h = dt.hour
    if 5 <= h < 9:
        return "morning"
    if 9 <= h < 17:
        return "day"
    if 17 <= h < 23:
        return "evening"
    return "night"


# -------------------------
# Recorder History
# -------------------------
def fetch_history(entity_id, days):
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


# -------------------------
# Laufzeiten aus Historie
# -------------------------
def extract_on_durations(history):
    """
    Liefert:
    {
      "morning": [12, 8, 15],
      "evening": [45, 62, 30]
    }
    """
    durations = defaultdict(list)
    last_on = None
    last_phase = None

    for e in history:
        state = e["state"]
        ts = datetime.fromisoformat(e["last_changed"])

        if state == "on":
            last_on = ts
            last_phase = day_phase(ts)

        if state == "off" and last_on:
            minutes = int((ts - last_on).total_seconds() / 60)
            if 1 <= minutes <= 300:  # Plausibilitätsfilter
                durations[last_phase].append(minutes)
            last_on = None
            last_phase = None

    return durations


# -------------------------
# Statistische Laufzeit
# -------------------------
def learned_runtime(durations, phase):
    """
    Gibt eine realistische Laufzeit in Minuten zurück
    """
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
