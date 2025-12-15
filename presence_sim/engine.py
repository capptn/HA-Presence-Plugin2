import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict
import random

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

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


def group_by_day(history):
    days = defaultdict(list)
    for e in history:
        ts = datetime.fromisoformat(e["last_changed"])
        day = ts.date()
        days[day].append({
            "time": ts.time(),
            "state": e["state"]
        })
    return days


def pick_random_day_pattern(history):
    days = group_by_day(history)
    if not days:
        return None

    day = random.choice(list(days.keys()))
    return days[day]


def jitter_time(base_time, minutes=10):
    offset = random.randint(-minutes, minutes)
    return (datetime.combine(datetime.today(), base_time)
            + timedelta(minutes=offset)).time()
