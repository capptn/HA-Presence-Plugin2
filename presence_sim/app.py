from flask import Flask, jsonify, send_from_directory
import os
import requests

app = Flask(__name__, static_folder="web", static_url_path="")

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

ALLOWED_DOMAINS = (
    "light",
    "switch",
    "fan",
    "input_boolean",
    "scene",
    "script"
)

@app.route("/api/entities")
def api_entities():
    if not TOKEN:
        return jsonify([])  # 👈 IMMER Array zurückgeben

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.get(f"{HA_URL}/states", headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        # 👇 FEHLER LOGGEN, aber FRONTEND NICHT CRASHEN
        print("API ERROR:", e)
        return jsonify([])

    entities = []
    for s in r.json():
        eid = s.get("entity_id", "")
        if "." not in eid:
            continue
        domain = eid.split(".", 1)[0]
        if domain in ALLOWED_DOMAINS:
            print("FOUND ENTITY:", eid)
            entities.append({
                "id": eid,
                "name": s.get("attributes", {}).get("friendly_name", eid)
            })

    return jsonify(entities)

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/<path:path>")
def catch_all(path):
    return send_from_directory("web", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
