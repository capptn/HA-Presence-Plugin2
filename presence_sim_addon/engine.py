from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple, Optional, Any
import random
from dateutil import parser as dtparser
from ha_api import HAClient

@dataclass
class SimConfig:
    entities: List[str]
    training_days: int = 14
    slot_minutes: int = 15
    interval_min: int = 5
    start_time: str = "18:00"
    end_time: str = "23:30"
    randomness: float = 0.15
    darkness_mode: str = "sun"   # sun|lux|none
    darkness_entity: str = "sun.sun"
    dark_state: str = "below_horizon"
    lux_threshold: int = 30

def _parse_hhmm(s: str) -> time:
    hh, mm = s.strip().split(":")
    return time(int(hh), int(mm), 0)

def _in_window(now: datetime, start: time, end: time) -> bool:
    t = now.time()
    if start <= end:
        return start <= t <= end
    return (t >= start) or (t <= end)

def _slot_index(dt: datetime, slot_minutes: int) -> int:
    return int(((dt.hour * 60) + dt.minute) // slot_minutes)

class PresenceModel:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.slots = int(24 * 60 / cfg.slot_minutes)
        self.p: Dict[str, List[float]] = {}

    def train(self, history: List[Any]) -> None:
        on = {e: [0]*self.slots for e in self.cfg.entities}
        tot = {e: [0]*self.slots for e in self.cfg.entities}

        for entity_states in history:
            if not entity_states or not isinstance(entity_states[0], dict):
                continue
            eid = entity_states[0].get("entity_id")
            if eid not in tot:
                continue
            for item in entity_states:
                st = (item.get("state") or "").lower()
                ts = item.get("last_updated") or item.get("last_changed")
                if not ts:
                    continue
                try:
                    dt = dtparser.isoparse(ts)
                except Exception:
                    continue
                si = _slot_index(dt, self.cfg.slot_minutes)
                if 0 <= si < self.slots:
                    tot[eid][si] += 1
                    if st == "on":
                        on[eid][si] += 1

        self.p = {e: [(on[e][i]/tot[e][i] if tot[e][i] else 0.0) for i in range(self.slots)] for e in self.cfg.entities}

    def p_on(self, eid: str, now: datetime) -> float:
        arr = self.p.get(eid)
        if not arr:
            return 0.0
        si = _slot_index(now, self.cfg.slot_minutes)
        return arr[si] if 0 <= si < len(arr) else 0.0

class PresenceSimEngine:
    def __init__(self, ha: HAClient):
        self.ha = ha
        self.cfg = SimConfig(entities=[])
        self.model = PresenceModel(self.cfg)
        self.last_train: Optional[str] = None
        self.last_step: Optional[Dict[str, Any]] = None

    def set_config(self, cfg: SimConfig):
        self.cfg = cfg
        self.model = PresenceModel(cfg)

    def train(self, now: datetime) -> Dict[str, Any]:
        if not self.cfg.entities:
            self.model.p = {}
            self.last_train = now.isoformat()
            return {"ok": True, "trained_entities": 0, "note": "No entities configured."}
        start = now - timedelta(days=int(self.cfg.training_days))
        history = self.ha.history_period(start=start, end=now, entity_ids=self.cfg.entities)
        self.model.train(history)
        self.last_train = now.isoformat()
        return {"ok": True, "trained_entities": len(self.cfg.entities), "last_train": self.last_train}

    def _is_dark(self) -> Tuple[bool, str]:
        mode = (self.cfg.darkness_mode or "sun").lower()
        if mode == "none":
            return True, "darkness_mode=none"
        st = self.ha.get_state(self.cfg.darkness_entity)
        if not st:
            return True, "darkness_entity not found (allowing)"
        if mode == "sun":
            return st.get("state") == self.cfg.dark_state, f"sun state={st.get('state')}"
        if mode == "lux":
            try:
                lux = float(st.get("state"))
            except Exception:
                return True, "lux unreadable (allowing)"
            return lux <= float(self.cfg.lux_threshold), f"lux={lux} threshold={self.cfg.lux_threshold}"
        return True, "unknown darkness mode (allowing)"

    def step(self, now: datetime) -> Dict[str, Any]:
        st = _parse_hhmm(self.cfg.start_time)
        en = _parse_hhmm(self.cfg.end_time)
        if not _in_window(now, st, en):
            self.last_step = {"time": now.isoformat(), "skipped": True, "reason": "outside_time_window"}
            return self.last_step

        dark_ok, dark_info = self._is_dark()
        if not dark_ok:
            self.last_step = {"time": now.isoformat(), "skipped": True, "reason": "not_dark", "detail": dark_info}
            return self.last_step

        actions = []
        for eid in self.cfg.entities:
            p = self.model.p_on(eid, now)
            jitter = (random.random() - 0.5) * 2 * float(self.cfg.randomness)
            p2 = min(1.0, max(0.0, p + jitter))
            target_on = random.random() < p2
            domain = eid.split(".", 1)[0]
            service = "turn_on" if target_on else "turn_off"
            if domain in ("light", "switch", "fan", "input_boolean"):
                try:
                    self.ha.call_service(domain, service, {"entity_id": eid})
                    actions.append({"entity_id": eid, "service": f"{domain}.{service}", "p_on": p, "p_used": p2})
                except Exception as ex:
                    actions.append({"entity_id": eid, "error": str(ex)})
        self.last_step = {"time": now.isoformat(), "skipped": False, "actions": actions, "darkness": dark_info}
        return self.last_step

    def preview_next_runs(self, now: datetime, count: int = 10) -> List[Dict[str, Any]]:
        st = _parse_hhmm(self.cfg.start_time)
        en = _parse_hhmm(self.cfg.end_time)
        step = timedelta(minutes=int(self.cfg.interval_min))
        seed_base = int(now.timestamp() // 60)
        t = now
        out: List[Dict[str, Any]] = []
        for _ in range(0, int((48*60)/self.cfg.interval_min) + 1):
            t = t + step
            if _in_window(t, st, en):
                rnd = random.Random(seed_base + int(t.timestamp() // 60))
                cand = []
                for eid in self.cfg.entities:
                    p = self.model.p_on(eid, t)
                    jitter = (rnd.random() - 0.5) * 2 * float(self.cfg.randomness)
                    p2 = min(1.0, max(0.0, p + jitter))
                    cand.append((p2, eid))
                cand.sort(reverse=True)
                expected = [{"entity_id": eid, "p": round(p, 3)} for p, eid in cand[:5] if p > 0]
                out.append({"time": t.isoformat(), "expected_top_on": expected})
                if len(out) >= count:
                    break
        return out
