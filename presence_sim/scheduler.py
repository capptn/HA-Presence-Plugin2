from datetime import datetime, timedelta
import random

from engine import (
    fetch_history,
    extract_on_durations,
    learned_runtime,
    day_phase,
)

planned_actions = []


def in_window(t, start, end):
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def plan_day(cfg):
    planned_actions.clear()

    now = datetime.now().replace(second=0, microsecond=0)
    w_start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    w_end = datetime.strptime(cfg["window_end"], "%H:%M").time()

    for entity in cfg["entities"]:
        history = fetch_history(entity, cfg["lookback_days"])
        durations = extract_on_durations(history)

        # -------- Muster-Replay --------
        on_events = [
            datetime.fromisoformat(e["last_changed"]).time()
            for e in history
            if e["state"] == "on"
        ]

        if on_events:
            sampled = random.sample(
                on_events, min(len(on_events), 2)
            )

            for t in sampled:
                if not in_window(t, w_start, w_end):
                    continue

                dt_on = now.replace(hour=t.hour, minute=t.minute)
                phase = day_phase(dt_on)

                runtime = learned_runtime(durations, phase)
                dt_off = dt_on + timedelta(minutes=runtime)

                planned_actions.append({
                    "time": dt_on,
                    "entity": entity,
                    "action": "turn_on"
                })
                planned_actions.append({
                    "time": dt_off,
                    "entity": entity,
                    "action": "turn_off"
                })

            continue

        # -------- Fallback --------
        base = now.replace(
            hour=w_start.hour,
            minute=w_start.minute
        ) + timedelta(minutes=random.randint(10, 60))

        runtime = learned_runtime({}, "evening")

        planned_actions.append({
            "time": base,
            "entity": entity,
            "action": "turn_on"
        })
        planned_actions.append({
            "time": base + timedelta(minutes=runtime),
            "entity": entity,
            "action": "turn_off"
        })

    planned_actions.sort(key=lambda x: x["time"])
