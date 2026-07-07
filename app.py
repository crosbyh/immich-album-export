"""Minimal web UI for exporting Immich albums."""

import os
import threading

from flask import Flask, render_template_string, request, jsonify

from export_album import (
    API_KEY,
    IMMICH_URL,
    export_album,
    export_album_backup,
    export_filename_list,
)

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
        /* Palette from Immich v3 (web/src/app.css): primary #4250AF,
           dark primary #ACCBFA, dark bg #0A0A0A, surface #212121 */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e5e7eb; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { background: #212121; padding: 2rem; border-radius: 12px; width: 100%; max-width: 480px; box-shadow: 0 4px 24px rgba(0,0,0,0.5); }
        h1 { font-size: 1.4rem; margin-bottom: 1.5rem; color: #accbfa; }
        label { display: block; font-size: 0.85rem; color: #9ca3af; margin-bottom: 0.3rem; }
        input, select { width: 100%; padding: 0.6rem 0.8rem; border: 1px solid #333; border-radius: 6px; background: #181818; color: #e5e7eb; font-size: 1rem; margin-bottom: 1rem; }
        input:focus, select:focus { outline: none; border-color: #accbfa; }
        button { width: 100%; padding: 0.7rem; border: none; border-radius: 6px; background: #accbfa; color: #0a0a0a; font-size: 1rem; font-weight: 600; cursor: pointer; }
        button:hover { background: #8fb4f0; }
        button:disabled { background: #444; color: #888; cursor: not-allowed; }
        .secondary-row { display: flex; gap: 0.6rem; margin-top: 0.6rem; }
        button.secondary { background: transparent; border: 1px solid #accbfa; color: #accbfa; font-weight: 500; font-size: 0.9rem; }
        button.secondary:hover { background: rgba(172, 203, 250, 0.12); }
        button.secondary:disabled { border-color: #444; color: #888; background: transparent; }
        .status { margin-top: 1rem; padding: 0.8rem; border-radius: 6px; background: #181818; font-size: 0.9rem; min-height: 2.5rem; }
        .status.error { background: #3a1a1e; color: #f0a4ae; }
        .status.success { background: #16281c; color: #a8e0b8; }
        .info { margin-bottom: 1rem; font-size: 0.8rem; color: #777; }
        .info span { color: #accbfa; }
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

        <button id="export_btn" onclick="startExport('images')">Export Album</button>
        <div class="secondary-row">
            <button id="filenames_btn" class="secondary" onclick="startExport('filenames')">Export Filename List</button>
            <button id="backup_btn" class="secondary" onclick="startExport('backup')">Export Album Backup</button>
        </div>
        <div class="status" id="status"></div>
    </div>
    <script>
        const buttons = () => ['export_btn', 'filenames_btn', 'backup_btn'].map(id => document.getElementById(id));
        const setBusy = (busy) => buttons().forEach(btn => { btn.disabled = busy; });

        function startExport(mode) {
            const albumId = document.getElementById('album_id').value.trim();
            const subfolder = document.getElementById('subfolder').value.trim();
            const format = document.getElementById('format').value;
            const status = document.getElementById('status');

            if (!albumId) { status.textContent = 'Please enter an album ID.'; status.className = 'status error'; return; }

            setBusy(true);
            status.textContent = 'Starting export...';
            status.className = 'status';

            fetch('/export', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({album_id: albumId, subfolder: subfolder, format: mode === 'images' ? (format || null) : null, mode: mode})
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    status.textContent = 'Error: ' + data.error;
                    status.className = 'status error';
                    setBusy(false);
                } else {
                    status.textContent = 'Export started...';
                    pollStatus(data.job_id);
                }
            })
            .catch(err => {
                status.textContent = 'Request failed: ' + err;
                status.className = 'status error';
                setBusy(false);
            });
        }

        function pollStatus(jobId) {
            const status = document.getElementById('status');

            const interval = setInterval(() => {
                fetch('/status/' + jobId)
                .then(r => r.json())
                .then(data => {
                    if (data.state === 'running') {
                        status.textContent = data.message;
                    } else if (data.state === 'done') {
                        status.textContent = data.message;
                        status.className = 'status success';
                        setBusy(false);
                        clearInterval(interval);
                    } else if (data.state === 'error') {
                        status.textContent = 'Error: ' + data.message;
                        status.className = 'status error';
                        setBusy(false);
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
    mode = data.get("mode", "images")

    if not album_id:
        return jsonify({"error": "album_id is required"}), 400

    if mode not in ("images", "filenames", "backup"):
        return jsonify({"error": f"unknown mode: {mode}"}), 400

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
            if mode == "filenames":
                count = export_filename_list(album_id, output_dir)
                message = f"Wrote {count} filename(s) to {output_dir}/filenames.txt"
            elif mode == "backup":
                count = export_album_backup(album_id, output_dir)
                message = f"Backed up album ({count} asset(s)) to {output_dir}/album-backup.json"
            else:
                result = export_album(album_id, output_dir, convert_to=convert_to, progress_callback=progress)
                message = (
                    f"Exported {result['exported']} new file(s), "
                    f"skipped {result['skipped']} to {output_dir}"
                )
            with jobs_lock:
                jobs[job_id] = {"state": "done", "message": message}
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
