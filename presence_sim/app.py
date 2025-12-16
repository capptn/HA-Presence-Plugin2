import os
import json
import time
import threading
from datetime import datetime
import requests

from flask import Flask, jsonify, request, send_from_directory

from scheduler import extend_plan, STATE

# =================================================
# Flask App
# =================================================
app = Flask(__name__, static_folder="web", static_url_path="")

# =================================================
# Home Assistant API
# =================================================
HA_URL = "http://supervisor/core/api"
TOKEN = os.environ.get("SUPERVISOR_TOKEN")

def ha_headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

# =================================================
# Paths
# =================================================
DATA_DIR = "/data"
CFG_PATH = f"{DATA_DIR}/config.json"
STATE_PATH = f"{DATA_DIR}/state.json"
ACTION_HISTORY_PATH = f"{DATA_DIR}/action_history.json"

# =================================================
# Defaults
# =================================================
DEFAULT_CONFIG = {
    "entities": [],
    "window_start": "05:30",
    "window_end": "23:30",
    "lookback_days": 14,
    "slot_minutes": 15,

    # Rolling Planner
    "plan_horizon_minutes": 240,
    "refill_threshold_minutes": 60,
    "sessions_per_entity": 2,
    "max_future_actions": 400,
}

# =================================================
# Runtime State
# =================================================
simulation_running = False
simulation_started_at = None
simulation_thread = None

# =================================================
# Helper: Config
# =================================================
def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, "r") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print("Config load error:", e)
    return cfg


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f)


# =================================================
# Helper: Simulation State
# =================================================
def save_state():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({
            "running": simulation_running,
            "started_at": simulation_started_at
        }, f)


def load_state():
    global simulation_running, simulation_started_at
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                s = json.load(f)
                simulation_running = s.get("running", False)
                simulation_started_at = s.get("started_at")
        except Exception as e:
            print("State load error:", e)

# =================================================
# Helper: Action History
# =================================================
MAX_HISTORY_ENTRIES = 500

def load_action_history():
    if os.path.exists(ACTION_HISTORY_PATH):
        try:
            with open(ACTION_HISTORY_PATH) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def log_action(entity, action):
    history = load_action_history()
    history.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entity": entity,
        "action": action,
        "source": "simulation"
    })
    history = history[-MAX_HISTORY_ENTRIES:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ACTION_HISTORY_PATH, "w") as f:
        json.dump(history, f)

# =================================================
# Simulation Loop (Rolling Planner)
# =================================================
def simulation_loop():
    global simulation_running

    print("Simulation loop started")

    while simulation_running:
        now = datetime.now().replace(second=0, microsecond=0)

        # Rolling planning
        try:
            cfg = load_config()
            extend_plan(cfg, now=now)
        except Exception as e:
            print("extend_plan error:", e)

        # Execute due actions
        for action in STATE.actions[:]:
            if action["time"] <= now:
                domain = action["entity"].split(".")[0]
                try:
                    requests.post(
                        f"{HA_URL}/services/{domain}/{action['action']}",
                        headers=ha_headers(),
                        json={"entity_id": action["entity"]},
                        timeout=10,
                    )
                    log_action(action["entity"], action["action"])
                except Exception as e:
                    print("execute error:", e)

                STATE.actions.remove(action)

        time.sleep(30)

    print("Simulation loop stopped")

# =================================================
# API: Config
# =================================================
@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.json or {}
        save_config(data)
        return jsonify({"ok": True})

    return jsonify(load_config())

# =================================================
# API: Status
# =================================================
@app.route("/api/status")
def api_status():
    return jsonify({
        "running": simulation_running,
        "started_at": simulation_started_at
    })

# =================================================
# API: Start / Stop
# =================================================
@app.route("/api/start", methods=["POST"])
def api_start():
    global simulation_running, simulation_thread, simulation_started_at

    if simulation_running:
        return jsonify({"running": True})

    cfg = load_config()
    extend_plan(cfg)

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

# =================================================
# API: Preview / Timeline / Heatmap
# =================================================
@app.route("/api/preview")
def api_preview():
    return jsonify([
        {
            "time": a["time"].strftime("%H:%M"),
            "entity": a["entity"],
            "action": a["action"]
        }
        for a in STATE.actions[:20]
    ])


@app.route("/api/timeline")
def api_timeline():
    out = {}
    for a in STATE.actions:
        out.setdefault(a["entity"], []).append({
            "time": a["time"].strftime("%H:%M"),
            "action": a["action"]
        })
    return jsonify(out)


@app.route("/api/heatmap")
def api_heatmap():
    heat = {}
    for a in STATE.actions:
        if a["action"] == "turn_on":
            k = a["time"].strftime("%H:%M")
            heat[k] = heat.get(k, 0) + 1
    return jsonify([
        {"time": k, "value": v}
        for k, v in sorted(heat.items())
    ])

# =================================================
# API: Action History
# =================================================
@app.route("/api/history")
def api_history():
    return jsonify(list(reversed(load_action_history())))

# =================================================
# Ingress UI
# =================================================
@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/<path:path>")
def catch_all(path):
    return send_from_directory("web", path)

# =================================================
# App Startup
# =================================================
load_state()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
