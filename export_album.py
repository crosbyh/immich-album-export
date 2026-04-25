#!/usr/bin/env python3
"""Export photos from an Immich album to a local folder."""

import os
import sys
from pathlib import Path

import requests

IMMICH_URL = os.environ.get("IMMICH_URL", "").rstrip("/")
API_KEY = os.environ.get("IMMICH_API_KEY", "")


def get_album_assets(album_id):
    """Fetch asset list for an album."""
    resp = requests.get(
        f"{IMMICH_URL}/api/albums/{album_id}",
        headers={"x-api-key": API_KEY},
    )
    resp.raise_for_status()
    return resp.json()["assets"]


def download_asset(asset_id):
    """Download the original asset file."""
    resp = requests.get(
        f"{IMMICH_URL}/api/assets/{asset_id}/original",
        headers={"x-api-key": API_KEY},
        stream=True,
    )
    resp.raise_for_status()
    return resp


def convert_image(src_path, dest_path):
    """Convert an image to the target format using Pillow."""
    from PIL import Image

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        img.save(dest_path)


def export_album(album_id, output_dir, convert_to=None, progress_callback=None):
    """Export all assets in an album to output_dir.

    progress_callback(current, total, filename) is called per asset if provided.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    assets = get_album_assets(album_id)
    total = len(assets)

    for i, asset in enumerate(assets, 1):
        original_name = asset["originalFileName"]
        asset_id = asset["id"]

        if convert_to:
            stem = Path(original_name).stem
            dest_name = f"{stem}.{convert_to}"
        else:
            dest_name = original_name

        dest_file = output_path / dest_name

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

    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export an Immich album to disk.")
    parser.add_argument("album_id", help="Immich album ID")
    parser.add_argument("output_dir", help="Directory to export photos to")
    parser.add_argument(
        "--format",
        help="Convert images to this format (e.g. jpeg, png, tiff)",
        default=None,
    )
    args = parser.parse_args()

    if not IMMICH_URL or not API_KEY:
        print("Error: Set IMMICH_URL and IMMICH_API_KEY environment variables.", file=sys.stderr)
        sys.exit(1)

    def print_progress(current, total, filename):
        print(f"[{current}/{total}] {filename}")

    count = export_album(args.album_id, args.output_dir, convert_to=args.format, progress_callback=print_progress)
    print(f"\nExported {count} file(s) to {args.output_dir}")
