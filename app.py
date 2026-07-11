#!/usr/bin/env python3
"""
Flask Web UI for Website Cloner.

Provides a web interface for cloning websites with live progress tracking.
Runs each clone in a background thread, tracks jobs in an in-memory JOBS dict,
polls /status/<id> for live progress, and zips the output folder for /download/<id>.
"""

import io
import os
import threading
import zipfile
from datetime import datetime

from flask import Flask, Response, jsonify, request

from cloner import clone_website_job

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Cloner</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { font-size: 2rem; margin-bottom: 0.5rem; color: #38bdf8; }
        .subtitle { color: #94a3b8; margin-bottom: 2rem; }
        .card { background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }
        label { display: block; font-weight: 500; margin-bottom: 0.5rem; color: #cbd5e1; }
        input[type="text"], input[type="number"] { width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 8px; background: #0f172a; color: #e2e8f0; font-size: 1rem; margin-bottom: 1rem; }
        input:focus { outline: none; border-color: #38bdf8; }
        .row { display: flex; gap: 1rem; }
        .row > div { flex: 1; }
        .checkbox { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
        .checkbox input { width: auto; }
        button { background: #2563eb; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 8px; font-size: 1rem; cursor: pointer; font-weight: 500; width: 100%; }
        button:hover { background: #1d4ed8; }
        button:disabled { background: #475569; cursor: not-allowed; }
        .progress-bar { width: 100%; height: 8px; background: #334155; border-radius: 4px; overflow: hidden; margin: 1rem 0; }
        .progress-fill { height: 100%; background: #2563eb; transition: width 0.3s ease; border-radius: 4px; }
        .status { font-size: 0.875rem; color: #94a3b8; margin-top: 0.5rem; }
        .job-card { background: #0f172a; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; border: 1px solid #334155; }
        .job-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
        .job-url { font-weight: 500; color: #38bdf8; word-break: break-all; }
        .job-status { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; }
        .status-running { background: #1e3a5f; color: #38bdf8; }
        .status-done { background: #14532d; color: #4ade80; }
        .status-error { background: #7f1d1d; color: #fca5a5; }
        .job-actions { margin-top: 0.75rem; }
        .job-actions a { color: #38bdf8; text-decoration: none; font-weight: 500; margin-right: 1rem; }
        .job-actions a:hover { text-decoration: underline; }
        .empty { text-align: center; color: #64748b; padding: 2rem; }
        .error { color: #f87171; background: #450a0a; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Website Cloner</h1>
        <p class="subtitle">Download entire websites for offline viewing</p>

        <div class="card">
            <div id="error" class="error"></div>
            <label for="url">Website URL</label>
            <input type="text" id="url" placeholder="https://example.com" required>

            <div class="row">
                <div>
                    <label for="output">Output Directory</label>
                    <input type="text" id="output" value="cloned_sites" placeholder="cloned_sites">
                </div>
                <div>
                    <label for="maxPages">Max Pages</label>
                    <input type="number" id="maxPages" value="100" min="1" max="10000">
                </div>
            </div>

            <div class="row">
                <div>
                    <label for="delay">Delay (seconds)</label>
                    <input type="number" id="delay" value="0.2" min="0" max="10" step="0.1">
                </div>
                <div>
                    <label for="timeout">Timeout (seconds)</label>
                    <input type="number" id="timeout" value="30" min="5" max="120">
                </div>
            </div>

            <div class="checkbox">
                <input type="checkbox" id="renderJs">
                <label for="renderJs" style="margin: 0;">Enable JavaScript rendering (requires Playwright)</label>
            </div>

            <div class="checkbox">
                <input type="checkbox" id="allDomains">
                <label for="allDomains" style="margin: 0;">Follow links to other domains</label>
            </div>

            <button id="startBtn" onclick="startClone()">Start Cloning</button>
        </div>

        <h2 style="margin-bottom: 1rem; font-size: 1.25rem;">Jobs</h2>
        <div id="jobs">
            <div class="empty">No jobs yet. Enter a URL above to start cloning.</div>
        </div>
    </div>

    <script>
        let pollInterval = null;

        function startClone() {
            const url = document.getElementById('url').value.trim();
            if (!url) {
                showError('Please enter a valid URL');
                return;
            }

            hideError();
            const btn = document.getElementById('startBtn');
            btn.disabled = true;
            btn.textContent = 'Starting...';

            const config = {
                url: url,
                output: document.getElementById('output').value || 'cloned_sites',
                max_pages: parseInt(document.getElementById('maxPages').value) || 100,
                delay: parseFloat(document.getElementById('delay').value) || 0.2,
                timeout: parseInt(document.getElementById('timeout').value) || 30,
                render_js: document.getElementById('renderJs').checked,
                follow_domains: document.getElementById('allDomains').checked,
            };

            fetch('/api/clone', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    btn.disabled = false;
                    btn.textContent = 'Start Cloning';
                    return;
                }
                addJob(data.id, config.url);
                btn.disabled = false;
                btn.textContent = 'Start Cloning';
                startPolling();
            })
            .catch(err => {
                showError('Failed to start clone: ' + err.message);
                btn.disabled = false;
                btn.textContent = 'Start Cloning';
            });
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }

        function addJob(id, url) {
            const jobsDiv = document.getElementById('jobs');
            const empty = jobsDiv.querySelector('.empty');
            if (empty) empty.remove();

            const jobHtml = `
                <div class="job-card" id="job-${id}">
                    <div class="job-header">
                        <span class="job-url">${escapeHtml(url)}</span>
                        <span class="job-status status-running" id="status-${id}">Running</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-${id}" style="width: 0%"></div>
                    </div>
                    <div class="status" id="detail-${id}">Starting...</div>
                    <div class="job-actions" id="actions-${id}" style="display: none;">
                        <a href="/download/${id}">Download ZIP</a>
                        <a href="/output/${id}" target="_blank">View Files</a>
                    </div>
                </div>
            `;
            jobsDiv.insertAdjacentHTML('afterbegin', jobHtml);
        }

        function updateJob(id, data) {
            const statusEl = document.getElementById('status-' + id);
            const progressEl = document.getElementById('progress-' + id);
            const detailEl = document.getElementById('detail-' + id);
            const actionsEl = document.getElementById('actions-' + id);

            if (!statusEl) return;

            if (data.status === 'running') {
                const pct = data.max_pages > 0 ? (data.pages_cloned / data.max_pages * 100) : 0;
                progressEl.style.width = pct + '%';
                detailEl.textContent = `Cloned ${data.pages_cloned}/${data.max_pages} pages`;
            } else if (data.status === 'done') {
                statusEl.textContent = 'Done';
                statusEl.className = 'job-status status-done';
                progressEl.style.width = '100%';
                detailEl.textContent = `Completed: ${data.pages_cloned} pages`;
                actionsEl.style.display = 'block';
                stopPolling();
            } else if (data.status === 'error') {
                statusEl.textContent = 'Error';
                statusEl.className = 'job-status status-error';
                detailEl.textContent = data.error || 'Unknown error';
                stopPolling();
            }
        }

        function startPolling() {
            if (pollInterval) return;
            pollInterval = setInterval(pollJobs, 1000);
        }

        function stopPolling() {
            if (pollInterval) {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        }

        function pollJobs() {
            fetch('/api/jobs')
                .then(r => r.json())
                .then(data => {
                    let allDone = true;
                    for (const [id, job] of Object.entries(data)) {
                        updateJob(id, job);
                        if (job.status === 'running') allDone = false;
                    }
                    if (allDone) stopPolling();
                })
                .catch(() => {});
        }

        function showError(msg) {
            const el = document.getElementById('error');
            el.textContent = msg;
            el.style.display = 'block';
        }

        function hideError() {
            document.getElementById('error').style.display = 'none';
        }
    </script>
</body>
</html>"""


def run_clone_job(job_id: str, config: dict):
    """Run a clone job in a background thread."""

    def progress(cloned, total, url):
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["pages_cloned"] = cloned
                JOBS[job_id]["max_pages"] = total
                JOBS[job_id]["current_url"] = url

    try:
        clone_website_job(config, progress_callback=progress)

        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["output_dir"] = config["output"]

    except Exception as e:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)


@app.route("/")
def index():
    return Response(PAGE, content_type="text/html")


@app.route("/api/clone", methods=["POST"])
def api_clone():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "URL is required"}), 400

    url = data["url"].strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data["url"] = url

    # Validate output directory to prevent path traversal
    output_dir = data.get("output", "cloned_sites")
    safe_base = os.path.abspath("cloned_sites")
    resolved = os.path.abspath(output_dir)
    if os.path.commonpath([resolved, safe_base]) != safe_base:
        output_dir = f"cloned_sites/{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data["output"] = output_dir

    job_id = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "url": url,
            "status": "running",
            "pages_cloned": 0,
            "max_pages": data.get("max_pages", 100),
            "current_url": "",
            "output_dir": "",
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

    thread = threading.Thread(target=run_clone_job, args=(job_id, data), daemon=True)
    thread.start()

    return jsonify({"id": job_id, "status": "started"})


@app.route("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        return jsonify(JOBS)


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(JOBS[job_id])


@app.route("/download/<job_id>")
def download_zip(job_id):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "Job not found"}), 404
        output_dir = JOBS[job_id].get("output_dir", "")

    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found"}), 404

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                zf.write(file_path, arcname)

    zip_buffer.seek(0)
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{os.path.basename(output_dir)}.zip"'
        },
    )


@app.route("/output/<job_id>")
def view_output(job_id):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return jsonify({"error": "Job not found"}), 404
        output_dir = JOBS[job_id].get("output_dir", "")

    if not output_dir or not os.path.exists(output_dir):
        return jsonify({"error": "Output directory not found"}), 404

    index_path = os.path.join(output_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(
            content,
            content_type="text/html",
            headers={"Content-Security-Policy": "script-src 'none'; sandbox"},
        )

    files = []
    for root, dirs, fnames in os.walk(output_dir):
        for fname in fnames:
            rel = os.path.relpath(os.path.join(root, fname), output_dir)
            files.append(rel)
    files.sort()

    html = f"<html><head><title>{output_dir}</title></head><body>"
    html += f"<h1>{output_dir}</h1><ul>"
    for f in files:
        html += f"<li>{f}</li>"
    html += "</ul></body></html>"
    return Response(
        html,
        content_type="text/html",
        headers={"Content-Security-Policy": "script-src 'none'; sandbox"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
