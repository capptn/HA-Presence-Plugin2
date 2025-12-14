from __future__ import annotations
import json, os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict
from flask import Flask, jsonify, request, send_from_directory, Response
from ha_api import HAClient
from engine import PresenceSimEngine, SimConfig
from scheduler import SimScheduler

DATA_DIR = "/data"
CFG_PATH = os.path.join(DATA_DIR, "config.json")

app = Flask(__name__, static_folder="web")
ha = HAClient.from_env()
engine = PresenceSimEngine(ha=ha)

def load_options() -> Dict[str, Any]:
    p = os.path.join(DATA_DIR, "options.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_saved() -> Dict[str, Any]:
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def merged() -> Dict[str, Any]:
    d = load_options()
    d.update(load_saved())
    return d

def apply_config(d: Dict[str, Any]) -> SimConfig:
    cfg = SimConfig(
        entities=list(d.get("entities") or []),
        training_days=int(d.get("training_days", 14)),
        slot_minutes=int(d.get("slot_minutes", 15)),
        interval_min=int(d.get("interval_min", 5)),
        start_time=str(d.get("start_time", "18:00")),
        end_time=str(d.get("end_time", "23:30")),
        randomness=float(d.get("randomness", 0.15)),
        darkness_mode=str(d.get("darkness_mode", "sun")),
        darkness_entity=str(d.get("darkness_entity", "sun.sun")),
        dark_state=str(d.get("dark_state", "below_horizon")),
        lux_threshold=int(d.get("lux_threshold", 30)),
    )
    engine.set_config(cfg)
    return cfg

cfg_current = apply_config(merged())

def on_step(now: datetime):
    return engine.step(now)

scheduler = SimScheduler(on_step=on_step)

@app.route("/")
def ui_root():
    return send_from_directory("web", "index.html")

@app.route("/web/<path:path>")
def web_static(path: str):
    return send_from_directory("web", path)

@app.route("/api/entities")
def api_entities():
    states = ha.get_states()
    allowed = {"light", "switch", "fan", "input_boolean"}
    out = []
    for s in states:
        eid = s.get("entity_id","")
        if "." not in eid:
            continue
        domain = eid.split(".",1)[0]
        if domain in allowed:
            out.append({
                "entity_id": eid,
                "name": (s.get("attributes") or {}).get("friendly_name") or eid,
                "domain": domain
            })
    out.sort(key=lambda x: (x["domain"], x["name"].lower()))
    return jsonify(out)

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    global cfg_current
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        cfg_current = apply_config(merged())
        return jsonify({"ok": True, "config": asdict(cfg_current)})
    return jsonify({"config": asdict(cfg_current)})

@app.route("/api/train", methods=["POST"])
def api_train():
    now = datetime.now().astimezone()
    return jsonify(engine.train(now))

@app.route("/api/start", methods=["POST"])
def api_start():
    scheduler.start(interval_min=int(cfg_current.interval_min))
    return jsonify({"ok": True, "running": True, "next_run": scheduler.state.next_run})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    scheduler.stop()
    return jsonify({"ok": True, "running": False})

@app.route("/api/step", methods=["POST"])
def api_step():
    now = datetime.now().astimezone()
    return jsonify(engine.step(now))

@app.route("/api/status")
def api_status():
    now = datetime.now().astimezone()
    return jsonify({
        "running": scheduler.state.running,
        "next_run": scheduler.state.next_run,
        "last_run": scheduler.state.last_run,
        "last_step": engine.last_step,
        "last_train": engine.last_train,
        "preview": engine.preview_next_runs(now, count=10),
    })

@app.route("/health")
def health():
    return Response("ok", mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
