---
name: verify
description: Verify immich-album-export changes end-to-end by running the CLI and Flask app against a stub Immich v3 server. Use when confirming export/API changes work without a live Immich instance.
---

# Verifying immich-album-export

No tests exist; verify by running the app against a stub Immich server.

## Setup

```sh
python3 -m venv /tmp/iae-venv && /tmp/iae-venv/bin/pip install -r requirements.txt
```

Write a stub Immich v3 server (plain `http.server`) implementing:
- `GET /api/server/version` → `{"major": 3, "minor": 0, "patch": 0}` (set major=2 to test the version gate)
- `GET /api/albums/{id}` → album metadata incl. `albumName`/`description`/`order` (no `assets` field in v3), 404 for unknown ids
- `POST /api/search/metadata` → `{"assets": {"items": [...], "nextPage": "<str|null>", ...}}`; cap page size at ~3 so a 7-asset album forces 3 pages; give assets `checksum` for backup mode
- `GET /api/assets/{id}/original` → image bytes (Pillow-generated PNG)
- `POST /api/albums` and `PUT /api/albums/{id}/assets` → log received bodies, return an album id (for `restore_album.py`)

All endpoints check the `x-api-key` header.

## Drive

CLI:
```sh
IMMICH_URL=http://127.0.0.1:21283 IMMICH_API_KEY=test-key \
  /tmp/iae-venv/bin/python export_album.py <album-uuid> /tmp/out [--format jpeg]
```

Web (port 5000 is taken by macOS AirPlay; `flask run` avoids the hardcoded port in `__main__`):
```sh
IMMICH_URL=... IMMICH_API_KEY=... EXPORT_DIR=/tmp/webexport \
  /tmp/iae-venv/bin/flask --app app.py run --port 5001
curl -X POST :5001/export -H 'Content-Type: application/json' -d '{"album_id": "...", "subfolder": "x"}'
curl :5001/status/<job_id>   # poll until state is done/error
```

## Worth checking

- Pagination: stub log should show multiple `POST /api/search/metadata` bodies with incrementing integer `page`.
- Bad album id → 404 error (exit 1 / job state `error`), not a silent 0-file export.
- v2 server → clear "requires Immich v3+" RuntimeError.
- `--format jpeg` conversion path (exercises Pillow temp-file flow).
- Differential: run export twice into the same dir — second run reports "0 new, N skipped" with no `/original` requests; delete one file → only that one refetches (`.export-manifest.json` drives this).
- `--mode filenames` → `filenames.txt`; `--mode backup` → `album-backup.json` with name/description/order + per-asset id/checksum/filename.
- Restore: `restore_album.py <backup.json> [--name X]`; a backup with >500 assets exercises chunked `PUT /albums/{id}/assets` (500 per request). Non-backup JSON → clean error, exit 1.
- UI screenshot: Playwright MCP wants Google Chrome (not installed); use `~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell --headless --screenshot=out.png --window-size=900,760 <url>` instead.
