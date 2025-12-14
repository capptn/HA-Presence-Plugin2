from flask import Flask, jsonify
from ha_api import get_switchable_entities

app = Flask(__name__)

@app.route("/api/entities")
def entities():
    return jsonify(get_switchable_entities())

@app.route("/")
def index():
    return app.send_static_file("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
