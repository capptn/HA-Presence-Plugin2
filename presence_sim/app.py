from flask import Flask, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

# Wichtig: Catch-All für Ingress
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory("web", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
