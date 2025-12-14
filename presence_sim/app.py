from flask import Flask, jsonify, request, send_from_directory
import os
import json
import threading
import time
import requests
from datetime import datetime, timedelta
from engine import build_probability_map
from scheduler import plan_day, planned_actions

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

    while simulation_running:
        now = datetime.now().replace(second=0, microsecond=0)

        for action in planned_actions[:]:
            if action["time"] <= now:
                domain = action["entity"].split(".")[0]
                try:
                    requests.post(
                        f"{HA_URL}/services/{domain}/{action['action']}",
                        headers=get_headers(),
                        json={"entity_id": action["entity"]},
                        timeout=10,
                    )
                except:
                    pass
                planned_actions.remove(action)

        time.sleep(30)


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

    cfg = load_config()
    prob_maps = {}

    for e in cfg["entities"]:
        prob_maps[e] = build_probability_map(
            e, cfg.get("lookback_days", 14), cfg["slot_minutes"]
        )

    plan_day(cfg["entities"], prob_maps, cfg)

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

@app.route("/api/preview")
def api_preview():
    return jsonify([
        {
            "time": a["time"].strftime("%H:%M"),
            "entity": a["entity"],
            "action": a["action"]
        }
        for a in planned_actions[:10]
    ])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
