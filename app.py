"""Minimal web UI for exporting Immich albums."""

import os
import threading

from flask import Flask, render_template_string, request, jsonify

from export_album import export_album, IMMICH_URL, API_KEY

app = Flask(__name__)

EXPORT_DIR = os.environ.get("EXPORT_DIR", "/export")

# Simple in-memory job state
jobs = {}
jobs_lock = threading.Lock()

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Immich Album Export</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { background: #16213e; padding: 2rem; border-radius: 12px; width: 100%; max-width: 480px; box-shadow: 0 4px 24px rgba(0,0,0,0.3); }
        h1 { font-size: 1.4rem; margin-bottom: 1.5rem; color: #a8dadc; }
        label { display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 0.3rem; }
        input, select { width: 100%; padding: 0.6rem 0.8rem; border: 1px solid #333; border-radius: 6px; background: #0f3460; color: #eee; font-size: 1rem; margin-bottom: 1rem; }
        input:focus, select:focus { outline: none; border-color: #a8dadc; }
        button { width: 100%; padding: 0.7rem; border: none; border-radius: 6px; background: #a8dadc; color: #1a1a2e; font-size: 1rem; font-weight: 600; cursor: pointer; }
        button:hover { background: #81b8bd; }
        button:disabled { background: #555; cursor: not-allowed; }
        .status { margin-top: 1rem; padding: 0.8rem; border-radius: 6px; background: #0f3460; font-size: 0.9rem; min-height: 2.5rem; }
        .status.error { background: #4a1525; color: #f8a4a4; }
        .status.success { background: #153a2a; color: #a8f0c8; }
        .info { margin-bottom: 1rem; font-size: 0.8rem; color: #666; }
        .info span { color: #a8dadc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Immich Album Export</h1>
        <div class="info">Server: <span>{{ immich_url }}</span></div>
        <div class="info">Export to: <span>{{ export_dir }}</span></div>

        <label for="album_id">Album ID</label>
        <input type="text" id="album_id" placeholder="paste album UUID here">

        <label for="subfolder">Subfolder (optional)</label>
        <input type="text" id="subfolder" placeholder="e.g. vacation-2024">

        <label for="format">Convert format (optional)</label>
        <select id="format">
            <option value="">Original (no conversion)</option>
            <option value="jpeg">JPEG</option>
            <option value="png">PNG</option>
            <option value="tiff">TIFF</option>
            <option value="webp">WebP</option>
        </select>

        <button id="export_btn" onclick="startExport()">Export Album</button>
        <div class="status" id="status"></div>
    </div>
    <script>
        function startExport() {
            const albumId = document.getElementById('album_id').value.trim();
            const subfolder = document.getElementById('subfolder').value.trim();
            const format = document.getElementById('format').value;
            const btn = document.getElementById('export_btn');
            const status = document.getElementById('status');

            if (!albumId) { status.textContent = 'Please enter an album ID.'; status.className = 'status error'; return; }

            btn.disabled = true;
            status.textContent = 'Starting export...';
            status.className = 'status';

            fetch('/export', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({album_id: albumId, subfolder: subfolder, format: format || null})
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    status.textContent = 'Error: ' + data.error;
                    status.className = 'status error';
                    btn.disabled = false;
                } else {
                    status.textContent = 'Export started...';
                    pollStatus(data.job_id);
                }
            })
            .catch(err => {
                status.textContent = 'Request failed: ' + err;
                status.className = 'status error';
                btn.disabled = false;
            });
        }

        function pollStatus(jobId) {
            const status = document.getElementById('status');
            const btn = document.getElementById('export_btn');

            const interval = setInterval(() => {
                fetch('/status/' + jobId)
                .then(r => r.json())
                .then(data => {
                    if (data.state === 'running') {
                        status.textContent = data.message;
                    } else if (data.state === 'done') {
                        status.textContent = data.message;
                        status.className = 'status success';
                        btn.disabled = false;
                        clearInterval(interval);
                    } else if (data.state === 'error') {
                        status.textContent = 'Error: ' + data.message;
                        status.className = 'status error';
                        btn.disabled = false;
                        clearInterval(interval);
                    }
                });
            }, 1000);
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML, immich_url=IMMICH_URL, export_dir=EXPORT_DIR)


@app.route("/export", methods=["POST"])
def start_export():
    data = request.get_json()
    album_id = data.get("album_id", "").strip()
    subfolder = data.get("subfolder", "").strip()
    convert_to = data.get("format")

    if not album_id:
        return jsonify({"error": "album_id is required"}), 400

    if not IMMICH_URL or not API_KEY:
        return jsonify({"error": "IMMICH_URL and IMMICH_API_KEY not configured"}), 500

    output_dir = os.path.join(EXPORT_DIR, subfolder) if subfolder else EXPORT_DIR

    import uuid
    job_id = str(uuid.uuid4())

    with jobs_lock:
        jobs[job_id] = {"state": "running", "message": "Starting..."}

    def run_export():
        def progress(current, total, filename):
            with jobs_lock:
                jobs[job_id]["message"] = f"[{current}/{total}] {filename}"

        try:
            count = export_album(album_id, output_dir, convert_to=convert_to, progress_callback=progress)
            with jobs_lock:
                jobs[job_id] = {"state": "done", "message": f"Exported {count} file(s) to {output_dir}"}
        except Exception as e:
            with jobs_lock:
                jobs[job_id] = {"state": "error", "message": str(e)}

    thread = threading.Thread(target=run_export, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"state": "error", "message": "Unknown job"}), 404
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
