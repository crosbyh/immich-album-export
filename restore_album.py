#!/usr/bin/env python3
"""Recreate an Immich album from an album-backup.json written by export_album.py.

Same-server restore: the backup's asset IDs must still exist on the server.
"""

import argparse
import json
import sys

import requests

from export_album import API_KEY, IMMICH_URL, check_server_version

ADD_CHUNK_SIZE = 500


def restore_album(backup, name_override=None):
    """Create an album from a backup dict. Returns the new album's response JSON."""
    check_server_version()

    asset_ids = [a["id"] for a in backup.get("assets", [])]
    first_chunk, rest = asset_ids[:ADD_CHUNK_SIZE], asset_ids[ADD_CHUNK_SIZE:]

    resp = requests.post(
        f"{IMMICH_URL}/api/albums",
        headers={"x-api-key": API_KEY},
        json={
            "albumName": name_override or backup["albumName"],
            "description": backup.get("description", ""),
            "assetIds": first_chunk,
        },
        timeout=30,
    )
    resp.raise_for_status()
    album = resp.json()

    for start in range(0, len(rest), ADD_CHUNK_SIZE):
        chunk = rest[start:start + ADD_CHUNK_SIZE]
        resp = requests.put(
            f"{IMMICH_URL}/api/albums/{album['id']}/assets",
            headers={"x-api-key": API_KEY},
            json={"ids": chunk},
            timeout=30,
        )
        resp.raise_for_status()

    return album


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recreate an Immich album from a backup file.")
    parser.add_argument("backup_file", help="Path to album-backup.json")
    parser.add_argument("--name", help="Override the album name from the backup", default=None)
    args = parser.parse_args()

    if not IMMICH_URL or not API_KEY:
        print("Error: Set IMMICH_URL and IMMICH_API_KEY environment variables.", file=sys.stderr)
        sys.exit(1)

    with open(args.backup_file) as f:
        backup = json.load(f)

    if backup.get("version") != 1 or "albumName" not in backup:
        print(f"Error: {args.backup_file} is not a recognized album backup file.", file=sys.stderr)
        sys.exit(1)

    album = restore_album(backup, name_override=args.name)
    print(f"Created album '{album['albumName']}' (id {album['id']}) with {len(backup['assets'])} asset(s)")
