# immich-album-export

A small web service that exports albums from an [Immich](https://immich.app) instance to a local directory.

## Running with Docker

Pull the prebuilt image from GitHub Container Registry:

```sh
docker pull ghcr.io/crosbyh/immich-album-export:latest
```

Or use the provided `docker-compose.yml`:

```sh
docker compose up -d
```

## Configuration

| Variable          | Description                          |
| ----------------- | ------------------------------------ |
| `IMMICH_URL`      | Base URL of your Immich instance     |
| `IMMICH_API_KEY`  | Immich API key                       |
| `EXPORT_DIR`      | Directory inside the container to write exports to |
