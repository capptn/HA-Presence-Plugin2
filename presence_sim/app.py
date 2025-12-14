from flask import Flask, jsonify, request, send_from_directory
import os
import json
import threading
import time
import requests

app = Flask(__name__, static_folder="web", static_url_path="")

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")
CFG_PATH = "/data/config.json"

simulation_running = False
simulation_thread = None


# -----------------------------
# Helper
# -----------------------------
def load_config():
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, "r") as f:
            return json.load(f)
    return {"entities": []}


def save_config(cfg):
    os.makedirs("/data", exist_ok=True)
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f)


def get_headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


# -----------------------------
# Simulation Loop
# -----------------------------
def simulation_loop():
    global simulation_running
    print("Simulation gestartet")

    while simulation_running:
        cfg = load_config()
        entities = cfg.get("entities", [])

        for entity_id in entities:
            domain = entity_id.split(".")[0]
            service = "turn_on"

            try:
                requests.post(
                    f"{HA_URL}/services/{domain}/{service}",
                    headers=get_headers(),
                    json={"entity_id": entity_id},
                    timeout=10,
                )
                print(f"Simulated ON: {entity_id}")
            except Exception as e:
                print("Simulation error:", e)

        time.sleep(60)  # alle 60 Sekunden


# -----------------------------
# API
# -----------------------------
@app.route("/api/entities")
def api_entities():
    r = requests.get(f"{HA_URL}/states", headers=get_headers(), timeout=10)
    r.raise_for_status()

    allowed = ("light", "switch", "fan", "input_boolean")
    out = []

    for s in r.json():
        eid = s["entity_id"]
        domain = eid.split(".", 1)[0]
        if domain in allowed:
            out.append({
                "id": eid,
                "name": s["attributes"].get("friendly_name", eid)
            })

    return jsonify(out)


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.json or {}
        save_config(data)
        return jsonify({"ok": True})

    return jsonify(load_config())


@app.route("/api/start", methods=["POST"])
def api_start():
    global simulation_running, simulation_thread

    if simulation_running:
        return jsonify({"running": True})

    simulation_running = True
    simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
    simulation_thread.start()

    return jsonify({"running": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global simulation_running
    simulation_running = False
    return jsonify({"running": False})


@app.route("/api/status")
def api_status():
    return jsonify({"running": simulation_running})


# -----------------------------
# Ingress UI
# -----------------------------
@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/<path:path>")
def catch_all(path):
    return send_from_directory("web", path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
