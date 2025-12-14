from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os, requests

def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

@dataclass
class HAClient:
    base_url: str
    token: str
    timeout: int = 20

    @staticmethod
    def from_env() -> "HAClient":
        base_url = os.environ.get("HA_URL", "http://supervisor/core/api")
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            raise RuntimeError("SUPERVISOR_TOKEN missing (Supervisor required).")
        return HAClient(base_url=base_url, token=token)

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get_states(self) -> List[Dict[str, Any]]:
        r = requests.get(f"{self.base_url}/states", headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        r = requests.get(f"{self.base_url}/states/{entity_id}", headers=self.headers, timeout=self.timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> None:
        r = requests.post(f"{self.base_url}/services/{domain}/{service}", headers=self.headers, json=data, timeout=self.timeout)
        r.raise_for_status()

    def history_period(self, start: datetime, end: datetime, entity_ids: List[str]) -> List[Any]:
        params = {"end_time": _iso(end), "filter_entity_id": ",".join(entity_ids), "minimal_response": "0"}
        url = f"{self.base_url}/history/period/{_iso(start)}"
        r = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
