# Engine placeholder – replace with full simulation logic
import requests
from datetime import datetime, timedelta
import os
from collections import defaultdict

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

def fetch_history(entity_id, days):
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    url = f"{HA_URL}/history/period/{start.isoformat()}"
    r = requests.get(url, headers=HEADERS, params={
        "filter_entity_id": entity_id,
        "minimal_response": "1"
    }, timeout=15)
    r.raise_for_status()
    return r.json()[0] if r.json() else []


def build_probability_map(entity_id, days, slot_minutes):
    history = fetch_history(entity_id, days)
    slots = defaultdict(int)

    for entry in history:
        if entry["state"] not in ("on", "off"):
            continue
        ts = datetime.fromisoformat(entry["last_changed"])
        slot = (ts.hour * 60 + ts.minute) // slot_minutes
        slots[slot] += 1

    return slots
