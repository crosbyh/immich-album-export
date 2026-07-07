#!/usr/bin/env python3
"""Export photos from an Immich album to a local folder."""

import json
import os
import sys
from pathlib import Path

import requests

IMMICH_URL = os.environ.get("IMMICH_URL", "").rstrip("/")
API_KEY = os.environ.get("IMMICH_API_KEY", "")


SEARCH_PAGE_SIZE = 1000  # spec maximum for /api/search/metadata
MANIFEST_NAME = ".export-manifest.json"


def check_server_version():
    """Fail fast with a clear error if the server is older than Immich v3."""
    resp = requests.get(
        f"{IMMICH_URL}/api/server/version",
        headers={"x-api-key": API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    version = resp.json()
    if version["major"] < 3:
        raise RuntimeError(
            f"This tool requires Immich v3+; server reports "
            f"v{version['major']}.{version['minor']}.{version['patch']}"
        )


def get_album_info(album_id):
    """Fetch album metadata; raises for a missing/inaccessible album
    (the search API silently returns nothing for unknown albums)."""
    resp = requests.get(
        f"{IMMICH_URL}/api/albums/{album_id}",
        headers={"x-api-key": API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_album_assets(album_id):
    """Fetch all assets in an album via the v3 search API (paginated)."""
    assets = []
    page = 1
    while page is not None:
        resp = requests.post(
            f"{IMMICH_URL}/api/search/metadata",
            headers={"x-api-key": API_KEY},
            json={"albumIds": [album_id], "page": page, "size": SEARCH_PAGE_SIZE, "order": "asc"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()["assets"]
        assets.extend(result["items"])
        next_page = result.get("nextPage")
        page = int(next_page) if next_page is not None else None
    return assets


def download_asset(asset_id):
    """Download the original asset file."""
    resp = requests.get(
        f"{IMMICH_URL}/api/assets/{asset_id}/original",
        headers={"x-api-key": API_KEY},
        stream=True,
        timeout=(30, None),
    )
    resp.raise_for_status()
    return resp


def convert_image(src_path, dest_path):
    """Convert an image to the target format using Pillow."""
    from PIL import Image

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        img.save(dest_path)


def load_manifest(output_path):
    """Load the differential-export manifest, tolerating a missing/corrupt file."""
    try:
        with open(output_path / MANIFEST_NAME) as f:
            manifest = json.load(f)
        if isinstance(manifest.get("assets"), dict):
            return manifest
    except (OSError, ValueError):
        pass
    return {"version": 1, "assets": {}}


def save_manifest(output_path, manifest):
    with open(output_path / MANIFEST_NAME, "w") as f:
        json.dump(manifest, f, indent=2)


def export_album(album_id, output_dir, convert_to=None, progress_callback=None):
    """Export all assets in an album to output_dir.

    Differential: assets recorded in the directory's manifest whose files are
    still on disk are skipped. Returns {"exported": n, "skipped": m}.
    progress_callback(current, total, filename) is called per asset if provided.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    check_server_version()
    get_album_info(album_id)
    assets = get_album_assets(album_id)
    total = len(assets)

    manifest = load_manifest(output_path)
    exported = 0
    skipped = 0

    for i, asset in enumerate(assets, 1):
        original_name = asset["originalFileName"]
        asset_id = asset["id"]

        if convert_to:
            stem = Path(original_name).stem
            dest_name = f"{stem}.{convert_to}"
        else:
            dest_name = original_name

        dest_file = output_path / dest_name

        recorded_name = manifest["assets"].get(asset_id)
        if recorded_name is not None and (output_path / recorded_name).exists():
            skipped += 1
            if progress_callback:
                progress_callback(i, total, f"{dest_name} (skipped)")
            continue

        if progress_callback:
            progress_callback(i, total, dest_name)

        resp = download_asset(asset_id)

        if convert_to:
            tmp_file = output_path / f".tmp_{original_name}"
            with open(tmp_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            convert_image(tmp_file, dest_file)
            tmp_file.unlink()
        else:
            with open(dest_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

        exported += 1
        manifest["assets"][asset_id] = dest_name
        save_manifest(output_path, manifest)

    return {"exported": exported, "skipped": skipped}


def export_filename_list(album_id, output_dir):
    """Write the album's original filenames, one per line, to filenames.txt.

    Returns the number of filenames written.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    check_server_version()
    get_album_info(album_id)
    assets = get_album_assets(album_id)

    with open(output_path / "filenames.txt", "w") as f:
        for asset in assets:
            f.write(asset["originalFileName"] + "\n")

    return len(assets)


def export_album_backup(album_id, output_dir):
    """Write album-backup.json: album metadata plus asset IDs/checksums.

    The backup can be restored on the same server with restore_album.py.
    Returns the number of assets recorded.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    check_server_version()
    album = get_album_info(album_id)
    assets = get_album_assets(album_id)

    backup = {
        "version": 1,
        "albumName": album.get("albumName"),
        "description": album.get("description", ""),
        "order": album.get("order"),
        "assets": [
            {
                "id": a["id"],
                "checksum": a.get("checksum"),
                "originalFileName": a.get("originalFileName"),
            }
            for a in assets
        ],
    }

    with open(output_path / "album-backup.json", "w") as f:
        json.dump(backup, f, indent=2)

    return len(assets)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export an Immich album to disk.")
    parser.add_argument("album_id", help="Immich album ID")
    parser.add_argument("output_dir", help="Directory to export photos to")
    parser.add_argument(
        "--format",
        help="Convert images to this format (e.g. jpeg, png, tiff); images mode only",
        default=None,
    )
    parser.add_argument(
        "--mode",
        choices=["images", "filenames", "backup"],
        default="images",
        help="images: download originals (differential); "
        "filenames: write filenames.txt; backup: write album-backup.json",
    )
    args = parser.parse_args()

    if not IMMICH_URL or not API_KEY:
        print("Error: Set IMMICH_URL and IMMICH_API_KEY environment variables.", file=sys.stderr)
        sys.exit(1)

    if args.mode == "filenames":
        count = export_filename_list(args.album_id, args.output_dir)
        print(f"Wrote {count} filename(s) to {args.output_dir}/filenames.txt")
    elif args.mode == "backup":
        count = export_album_backup(args.album_id, args.output_dir)
        print(f"Backed up album ({count} asset(s)) to {args.output_dir}/album-backup.json")
    else:
        def print_progress(current, total, filename):
            print(f"[{current}/{total}] {filename}")

        result = export_album(args.album_id, args.output_dir, convert_to=args.format, progress_callback=print_progress)
        print(f"\nExported {result['exported']} new file(s), skipped {result['skipped']} to {args.output_dir}")
