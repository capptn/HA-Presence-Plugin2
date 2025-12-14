# Scheduler placeholder
import random
from datetime import datetime, timedelta

planned_actions = []

def plan_day(entities, prob_maps, cfg):
    planned_actions.clear()

    start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    end = datetime.strptime(cfg["window_end"], "%H:%M").time()

    now = datetime.now().replace(second=0, microsecond=0)
    t = now.replace(hour=start.hour, minute=start.minute)

    end_dt = now.replace(hour=end.hour, minute=end.minute)
    slot = cfg["slot_minutes"]

    while t <= end_dt:
        for entity in entities:
            slot_id = (t.hour * 60 + t.minute) // slot
            weight = prob_maps.get(entity, {}).get(slot_id, 0)

            if weight > 0 and random.random() < min(0.8, weight / 10):
                planned_actions.append({
                    "time": t,
                    "entity": entity,
                    "action": "turn_on"
                })

        t += timedelta(minutes=slot)
