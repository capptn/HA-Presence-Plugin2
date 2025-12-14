from flask import Flask, jsonify, send_from_directory
import os, requests

app = Flask(__name__, static_folder="web", static_url_path="")

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

@app.route("/api/entities")
def api_entities():
    r = requests.get(f"{HA_URL}/states", headers=HEADERS, timeout=10)
    r.raise_for_status()

    entities = []
    for s in r.json():
        eid = s["entity_id"]
        domain = eid.split(".")[0]
        if domain in ("light", "switch", "fan"):
            entities.append({
                "id": eid,
                "name": s["attributes"].get("friendly_name", eid)
            })

    return jsonify(entities)

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

# ⚠️ GANZ WICHTIG: ganz am Ende!
@app.route("/<path:path>")
def catch_all(path):
    return send_from_directory("web", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
