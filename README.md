# MONILite

MONILite is a lightweight system monitoring daemon for Linux that collects CPU, memory, disk, and optional NVIDIA GPU metrics, retains tiered history in SQLite (5-second, 1-minute, and 5-minute buckets), and serves both a JSON API and a bundled dashboard over HTTP. Released under the [MIT License](LICENSE).

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install monilite
monilite serve
# Visit http://localhost:8000 for the dashboard, history charts, and JSON API
```

## Installation

- Python 3.10 or newer is required.
- Linux (Ubuntu tested) is the primary target; other OSes are currently unsupported.
- NVIDIA GPU data is optional and depends on NVML bindings (the `nvidia-ml-py` package is installed automatically, but the NVIDIA driver/NVML libraries still need to be present on the system).

Install MONILite directly from PyPI:

```bash
pip install monilite
```

## Usage

Start the collector + HTTP server with default options:

```bash
monilite serve
```

Common flags:

- `--host` / `--port` to change the listening address (defaults: `0.0.0.0:8000`).
- `--no-gpu` to skip NVIDIA/NVML probing entirely.
- `--db-path` to override the SQLite history database location (`monilite_history.db` by default).
- `--log-level` for verbose debugging output (`INFO` by default).

Change the sampling interval at any time from the dashboard's drop-down selector—no restart required. Historical CPU, memory, disk, and GPU utilization trends are displayed below the live metrics with 1h/24h/7d windows backed by the SQLite tiers.

## Configuration

MONILite keeps configuration intentionally small. Runtime options are exposed through CLI flags. Persistent configuration can later be provided via a simple `.toml` file, but that mechanism is not implemented yet.

History is stored in `monilite_history.db` (SQLite) by default; pass `--db-path /path/to/file` to relocate it (for example, to a tmpfs or persistent mount).

## HTTP API

The built-in HTTP server exposes:

- `GET /api/v1/live` – returns the latest CPU, memory, disk, and GPU snapshot collected in the background loop.
- `GET /api/v1/history?window=1h|24h|7d` – returns down-sampled CPU/memory/disk/GPU series sourced from the SQLite tiers so the dashboard can render trend charts.
- `GET /api/v1/settings` – reads the active sampling interval (used for the dashboard selector).
- `POST /api/v1/settings` – updates the sampling interval in real time.
- `GET /` – serves a lightweight HTML page that polls `/api/v1/live`, renders history charts, and exposes the interval selector.

Additional history endpoints (`/api/v1/metrics`, `/api/v1/history`, etc.) will come online once the SQLite storage layer lands.

See `docs/http-api.md` for full payload samples.

## Architecture

- **Collector daemon:** samples CPU, memory, and disk usage via `psutil` every few seconds. If NVML bindings are available, GPU utilization, memory, temperature, and power draw are collected in the same cadence.
- **Storage:** uses SQLite with tiered retention tables (5-second for ~1h, 1-minute for ~24h, 5-minute for longer history). Background jobs promote data from one tier to the next and prune old rows automatically.
- **HTTP Service:** a small Flask app serves `/api/v1/live` plus a bundled HTML view that auto-refreshes using the same endpoint.
- **History API/UI:** `/api/v1/history` powers the built-in charts (1h/24h/7d windows) rendered via Canvas elements under the live metrics grid.
- **CLI:** `monilite serve` wires together the collector thread, history store, and HTTP server; the dashboard drives runtime interval updates via the `/api/v1/settings` endpoint.

More detail: `docs/architecture.md`.

## FAQ

**Does it support Windows or macOS?**

Linux first. Other operating systems are explicitly out-of-scope for the initial releases.

**Can I plug it into Prometheus, Grafana, or external TSDBs?**

No. MONILite is intentionally self-contained and stores metrics only in its bundled SQLite database.

## Live dashboard

The dashboard shows live cards plus interactive history charts (CPU, memory, disk, GPU). Hover over any point to see the timestamp/value, adjust the sampling interval from the selector, and use the smoothing slider to tame noisy hosts. Everything is bundled directly in the Flask app so there are no external assets or build steps yet.
