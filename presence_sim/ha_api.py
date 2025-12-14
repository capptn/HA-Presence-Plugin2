import os
import requests

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def get_switchable_entities():
    r = requests.get(f"{HA_URL}/states", headers=HEADERS, timeout=10)
    r.raise_for_status()

    entities = []
    for s in r.json():
        entity_id = s["entity_id"]
        domain = entity_id.split(".")[0]

        if domain in ("light", "switch", "fan"):
            entities.append({
                "id": entity_id,
                "name": s["attributes"].get("friendly_name", entity_id)
            })

    return entities
