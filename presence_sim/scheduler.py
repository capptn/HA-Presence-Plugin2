from datetime import datetime, timedelta, time
import random

from engine import (
    fetch_history,
    extract_on_durations,
    learned_runtime,
    day_phase,
)

# =================================================
# ZENTRALER PLANNER STATE (WICHTIG!)
# =================================================
class PlannerState:
    def __init__(self):
        self.actions = []

STATE = PlannerState()

# =================================================
# Helper
# =================================================
def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m), 0)


def in_window(t: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _existing_keys():
    return {
        (a["entity"], a["time"].isoformat())
        for a in STATE.actions
    }


# =================================================
# ROLLING PLANNER
# =================================================
def extend_plan(cfg: dict, now: datetime | None = None):
    now = (now or datetime.now()).replace(second=0, microsecond=0)

    entities = cfg.get("entities", [])
    if not entities:
        return

    w_start = _parse_hhmm(cfg.get("window_start", "05:30"))
    w_end = _parse_hhmm(cfg.get("window_end", "23:30"))

    lookback_days = int(cfg.get("lookback_days", 14))
    horizon_min = int(cfg.get("plan_horizon_minutes", 240))
    refill_threshold = int(cfg.get("refill_threshold_minutes", 60))
    sessions_per_entity = int(cfg.get("sessions_per_entity", 2))

    # alte Aktionen entfernen
    STATE.actions[:] = [
        a for a in STATE.actions
        if a["time"] >= now - timedelta(minutes=5)
    ]
    STATE.actions.sort(key=lambda x: x["time"])

    if STATE.actions:
        farthest = max(a["time"] for a in STATE.actions)
        minutes_ahead = int((farthest - now).total_seconds() / 60)
        if minutes_ahead >= refill_threshold:
            return

    target_end = now + timedelta(minutes=horizon_min)
    existing = _existing_keys()
    added = 0

    for entity in entities:
        history = fetch_history(entity, lookback_days)
        durations = extract_on_durations(history)

        # historische ON-Zeiten sammeln
        on_times = []
        for e in history:
            if e["state"] == "on":
                try:
                    ts = datetime.fromisoformat(e["last_changed"])
                    on_times.append(ts.time())
                except Exception:
                    pass

        candidates = []

        # ---- Historische Zeiten nutzen
        for t in random.sample(on_times, min(len(on_times), 6)):
            dt = datetime.combine(now.date(), t).replace(second=0, microsecond=0)

            # in den Horizont schieben
            while dt < now:
                dt += timedelta(days=1)
            while dt > target_end:
                dt -= timedelta(days=1)

            if now <= dt <= target_end and in_window(dt.time(), w_start, w_end):
                candidates.append(dt)

        # ---- Fallback, falls Historie nichts liefert
        if not candidates:
            base = now + timedelta(minutes=random.randint(10, 60))
            if in_window(base.time(), w_start, w_end):
                candidates.append(base)

        # ---- Aktionen erzeugen
        for dt_on in candidates[:sessions_per_entity]:
            key = (entity, dt_on.isoformat())
            if key in existing:
                continue

            phase = day_phase(dt_on)
            runtime = learned_runtime(durations, phase)
            dt_off = dt_on + timedelta(minutes=runtime)

            STATE.actions.append({
                "time": dt_on,
                "entity": entity,
                "action": "turn_on"
            })
            STATE.actions.append({
                "time": dt_off,
                "entity": entity,
                "action": "turn_off"
            })

            existing.add(key)
            added += 2

    # ---- NOTFALL-FALLBACK (nie leer!)
    if not STATE.actions:
        print("⚠️ Rolling Planner Emergency Fallback")
        base = now + timedelta(minutes=10)
        for entity in entities:
            STATE.actions.append({
                "time": base,
                "entity": entity,
                "action": "turn_on"
            })
            STATE.actions.append({
                "time": base + timedelta(minutes=20),
                "entity": entity,
                "action": "turn_off"
            })

    STATE.actions.sort(key=lambda x: x["time"])
