from datetime import datetime, timedelta
import random
from engine import fetch_history, pick_random_day_pattern

planned_actions = []

def plan_day(cfg):
    planned_actions.clear()

    now = datetime.now().replace(second=0, microsecond=0)
    window_start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    window_end = datetime.strptime(cfg["window_end"], "%H:%M").time()

    for entity in cfg["entities"]:
        history = fetch_history(entity, cfg["lookback_days"])

        # -------- Ebene 1: Muster-Replay --------
        pattern = pick_random_day_pattern(history)

        if pattern:
            for p in pattern:
                if p["state"] not in ("on", "off"):
                    continue

                t = jitter_time(p["time"], 10)
                dt = now.replace(hour=t.hour, minute=t.minute)

                if window_start <= t <= window_end:
                    planned_actions.append({
                        "time": dt,
                        "entity": entity,
                        "action": "turn_" + p["state"]
                    })
            continue

        # -------- Ebene 2: Statistik (Fallback) --------
        base = now.replace(
            hour=window_start.hour,
            minute=window_start.minute
        )

        planned_actions.append({
            "time": base + timedelta(minutes=random.randint(10, 60)),
            "entity": entity,
            "action": "turn_on"
        })

        planned_actions.append({
            "time": base + timedelta(minutes=random.randint(90, 180)),
            "entity": entity,
            "action": "turn_off"
        })

    planned_actions.sort(key=lambda x: x["time"])
