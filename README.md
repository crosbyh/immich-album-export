# immich-album-export

A small web service that exports albums from an [Immich](https://immich.app) instance to a local directory.

> **Requires Immich server v3.0.0 or newer.** Immich v3 removed the embedded
> asset list from the albums API, so older servers are not supported. If your
> server is still on v2.x, pin an older image of this tool (the last v2-compatible
> release is tagged prior to the v3 migration commit).

## Running with Docker

Pull the prebuilt image from GitHub Container Registry:

```sh
docker pull ghcr.io/crosbyh/immich-album-export:latest
```

Or use the provided `docker-compose.yml`:

```sh
docker compose up -d
```

## Export modes

The web UI (and the CLI's `--mode` flag) supports three exports, all written to
the export directory (plus optional subfolder):

- **Export Album** (`--mode images`, default) — downloads original files.
  Exports are **differential**: a `.export-manifest.json` in the output
  directory records which assets have already been exported, and re-exports
  skip them. Delete a file (or the manifest) to force it to be fetched again.
- **Export Filename List** (`--mode filenames`) — writes `filenames.txt` with
  one original filename per line, no images.
- **Export Album Backup** (`--mode backup`) — writes `album-backup.json`
  containing the album name, description, sort order, and each asset's ID,
  checksum, and filename.

## Restoring an album from a backup

`restore_album.py` recreates an album on the **same server** from a backup file
(the assets must still exist on the server — e.g. the album was deleted, the
photos weren't):

```sh
IMMICH_URL=... IMMICH_API_KEY=... python restore_album.py album-backup.json [--name "New Name"]
```

## Configuration

| Variable          | Description                          |
| ----------------- | ------------------------------------ |
| `IMMICH_URL`      | Base URL of your Immich instance     |
| `IMMICH_API_KEY`  | Immich API key                       |
| `EXPORT_DIR`      | Directory inside the container to write exports to |
