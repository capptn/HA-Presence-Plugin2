from flask import Flask, jsonify, request, send_from_directory
import os
import json
import threading
import time
import requests
from collections import defaultdict
from datetime import datetime, timedelta
from scheduler import plan_day, planned_actions


app = Flask(__name__, static_folder="web", static_url_path="")

HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")
CFG_PATH = "/data/config.json"

DEFAULT_CONFIG = {
    "entities": [],
    "slot_minutes": 15,
    "lookback_days": 14,
    "window_start": "06:00",
    "window_end": "23:30",
    "min_on_minutes": 10,
    "max_on_minutes": 45
}

STATE_PATH = "/data/state.json"

simulation_running = False
simulation_started_at = None


# -----------------------------
# Helper
# -----------------------------
def load_config():
    cfg = DEFAULT_CONFIG.copy()

    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, "r") as f:
                stored = json.load(f)
                cfg.update(stored)
        except Exception as e:
            print("Config load error:", e)

    return cfg


def save_config(cfg):
    os.makedirs("/data", exist_ok=True)
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f)


def get_headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

def save_state():
    os.makedirs("/data", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({
            "running": simulation_running,
            "started_at": simulation_started_at
        }, f)

def load_state():
    global simulation_running, simulation_started_at
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
            simulation_running = state.get("running", False)
            simulation_started_at = state.get("started_at")
# -----------------------------
# Simulation Loop
# -----------------------------
def simulation_loop():
    global simulation_running

    while simulation_running:
        now = datetime.now().replace(second=0, microsecond=0)
        print("Simulation tick at", now.strftime("%H:%M"));
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

    allowed = ("light", "switch", "fan", "input_boolean", "cover")
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
    global simulation_running, simulation_thread, simulation_started_at

    if simulation_running:
        return jsonify({"running": True})

    cfg = load_config()
    plan_day(cfg)

    simulation_running = True
    simulation_started_at = datetime.now().strftime("%H:%M")
    save_state()

    simulation_thread = threading.Thread(
        target=simulation_loop, daemon=True
    )
    simulation_thread.start()
    

    return jsonify({"running": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global simulation_running, simulation_started_at

    simulation_running = False
    simulation_started_at = None
    save_state()

    return jsonify({"running": False})



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
        for a in sorted(planned_actions, key=lambda x: x["time"])[:20]
    ])

@app.route("/api/timeline")
def api_timeline():
    timeline = defaultdict(list)

    for a in planned_actions:
        timeline[a["entity"]].append({
            "time": a["time"].strftime("%H:%M"),
            "action": a["action"]
        })

    return jsonify(timeline)

@app.route("/api/heatmap")
def api_heatmap():
    heat = defaultdict(int)

    for a in planned_actions:
        slot = a["time"].strftime("%H:%M")
        if a["action"] == "turn_on":
            heat[slot] += 1

    return jsonify([
        {"time": k, "value": v}
        for k, v in sorted(heat.items())
    ])
@app.route("/api/status")
def api_status():
    return jsonify({
        "running": simulation_running,
        "started_at": simulation_started_at
    })

if __name__ == "__main__":
    load_state()
    app.run(host="0.0.0.0", port=8099)
