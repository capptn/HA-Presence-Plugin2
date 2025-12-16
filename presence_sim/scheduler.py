from __future__ import annotations

from datetime import datetime, timedelta, time
import random
from typing import Dict, List, Tuple, Optional

from engine import fetch_history, extract_on_durations, learned_runtime, day_phase

planned_actions: List[dict] = []


def _parse_hhmm(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m), 0)


def in_window(t: time, start: time, end: time) -> bool:
    # supports windows crossing midnight
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _next_window_start(now: datetime, start: time) -> datetime:
    candidate = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if candidate >= now:
        return candidate
    return candidate + timedelta(days=1)


def _existing_keys() -> set[Tuple[str, str]]:
    # (entity, iso-minute)
    keys = set()
    for a in planned_actions:
        keys.add((a["entity"], a["time"].replace(second=0, microsecond=0).isoformat()))
    return keys


def _build_on_candidates(history: list) -> List[time]:
    # collect historical ON times (time-of-day)
    out: List[time] = []
    for e in history:
        if e.get("state") != "on":
            continue
        try:
            ts = datetime.fromisoformat(e["last_changed"])
        except Exception:
            continue
        out.append(ts.time().replace(second=0, microsecond=0))
    return out


def extend_plan(cfg: dict, now: Optional[datetime] = None) -> dict:
    """
    Extend planned_actions to cover at least cfg['plan_horizon_minutes'] ahead.
    Plans only within the configured time window, learns runtimes from history.
    """
    global planned_actions
    now = (now or datetime.now()).replace(second=0, microsecond=0)

    w_start = _parse_hhmm(cfg.get("window_start", "18:00"))
    w_end = _parse_hhmm(cfg.get("window_end", "23:30"))

    horizon_min = int(cfg.get("plan_horizon_minutes", 240))      # plan 4h ahead by default
    refill_threshold = int(cfg.get("refill_threshold_minutes", 60))  # when <60 min remain, extend
    max_future_actions = int(cfg.get("max_future_actions", 400))  # safety cap

    entities = list(cfg.get("entities", []) or [])
    lookback_days = int(cfg.get("lookback_days", 14))

    # clean past actions (keep a tiny buffer)
    keep_after = now - timedelta(minutes=5)
    planned_actions = [a for a in planned_actions if a["time"] >= keep_after]
    planned_actions.sort(key=lambda x: x["time"])

    # determine how far we are currently planned
    if planned_actions:
        farthest = max(a["time"] for a in planned_actions)
        minutes_ahead = int((farthest - now).total_seconds() // 60)
    else:
        minutes_ahead = 0

    if minutes_ahead >= refill_threshold:
        return {"extended": False, "minutes_ahead": minutes_ahead, "planned": len(planned_actions)}

    target_end = now + timedelta(minutes=horizon_min)
    existing = _existing_keys()

    added = 0

    for entity in entities:
        # fetch history & learned runtimes once per extend call
        history = fetch_history(entity, lookback_days)
        durations = extract_on_durations(history)
        on_times = _build_on_candidates(history)

        # If we have few candidates, we still create some times inside the horizon
        # We'll sample from historic ON times but only keep those that fall into window and horizon.
        # We'll also add mild jitter to avoid identical repeats.
        # Number of "sessions" to schedule per entity in this extension:
        sessions = int(cfg.get("sessions_per_entity", 2))  # per extend call/horizon

        candidates: List[datetime] = []

        if on_times:
            # sample a few historic times and map to dates within [now, target_end]
            sampled = random.sample(on_times, min(len(on_times), max(6, sessions * 3)))
            for t in sampled:
                # jitter +/- 10 minutes
                jitter = random.randint(-10, 10)
                dt = datetime.combine(now.date(), t).replace(tzinfo=now.tzinfo) + timedelta(minutes=jitter)

                # If dt already passed, shift by +1 day (and maybe +2) to land in horizon
                while dt < now:
                    dt += timedelta(days=1)
                # If still beyond horizon, try the same time on next day only if within horizon
                if dt <= target_end:
                    candidates.append(dt)

        # fallback: generate some times evenly spread within horizon inside window
        if not candidates:
            start_dt = now
            step = max(15, int(cfg.get("slot_minutes", 15)))
            for i in range(0, horizon_min, step):
                dt = start_dt + timedelta(minutes=i)
                if in_window(dt.time(), w_start, w_end):
                    # thin out to a few sessions
                    if random.random() < 0.25:
                        candidates.append(dt)

        # pick up to 'sessions' unique candidate ON times
        candidates.sort()
        chosen = []
        for dt in candidates:
            if len(chosen) >= sessions:
                break
            if not in_window(dt.time(), w_start, w_end):
                continue
            # avoid duplicates per minute
            k = (entity, dt.isoformat())
            if k in existing:
                continue
            chosen.append(dt)

        for dt_on in chosen:
            phase = day_phase(dt_on)
            runtime = learned_runtime(durations, phase)
            dt_off = dt_on + timedelta(minutes=runtime)

            # Ensure OFF is also within horizon (optional). We'll allow OFF slightly beyond horizon.
            for dt, action in ((dt_on, "turn_on"), (dt_off, "turn_off")):
                dt2 = dt.replace(second=0, microsecond=0)
                k = (entity, dt2.isoformat())
                if k in existing:
                    continue
                planned_actions.append({"time": dt2, "entity": entity, "action": action})
                existing.add(k)
                added += 1
                if len(planned_actions) >= max_future_actions:
                    break

            if len(planned_actions) >= max_future_actions:
                break

        if len(planned_actions) >= max_future_actions:
            break

    planned_actions.sort(key=lambda x: x["time"])

    # recompute planned horizon
    if planned_actions:
        farthest = max(a["time"] for a in planned_actions)
        minutes_ahead = int((farthest - now).total_seconds() // 60)
    else:
        minutes_ahead = 0

    return {"extended": True, "added": added, "minutes_ahead": minutes_ahead, "planned": len(planned_actions)}
