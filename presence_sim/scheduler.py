# Scheduler placeholder
import random
from datetime import datetime, timedelta

planned_actions = []

def plan_day(entities, prob_maps, cfg):
    planned_actions.clear()

    start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    end = datetime.strptime(cfg["window_end"], "%H:%M").time()
    slot = cfg["slot_minutes"]

    now = datetime.now().replace(second=0, microsecond=0)
    t = now.replace(hour=start.hour, minute=start.minute)
    end_dt = now.replace(hour=end.hour, minute=end.minute)

    min_on = cfg.get("min_on_minutes", 10)
    max_on = cfg.get("max_on_minutes", 45)

    while t <= end_dt:
        for entity in entities:
            slot_id = (t.hour * 60 + t.minute) // slot
            weight = prob_maps.get(entity, {}).get(slot_id, 0)

            if weight > 0 and random.random() < min(0.8, weight / 10):
                on_time = t
                duration = random.randint(min_on, max_on)
                off_time = on_time + timedelta(minutes=duration)

                planned_actions.append({
                    "time": on_time,
                    "entity": entity,
                    "action": "turn_on"
                })
                planned_actions.append({
                    "time": off_time,
                    "entity": entity,
                    "action": "turn_off"
                })
        t += timedelta(minutes=slot)

    # Fallback: mindestens eine Aktion
    if not planned_actions:
        base = datetime.now().replace(second=0, microsecond=0)
        for i, entity in enumerate(entities):
            planned_actions.append({
                "time": base + timedelta(minutes=5*(i+1)),
                "entity": entity,
                "action": "turn_on"
            })
            planned_actions.append({
                "time": base + timedelta(minutes=20*(i+1)),
                "entity": entity,
                "action": "turn_off"
            })