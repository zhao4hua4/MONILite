# MONILite Architecture Notes

## Goals

- Focus on system essentials: CPU, memory, disk, and GPU metrics.
- Operate as a single-node daemon with minimal configuration.
- Remain self-contained: SQLite for data, bundled dashboard + API.

## Components

### Collector

- Runs a scheduler loop that fires every 5 seconds for high-resolution samples.
- Uses `psutil` for CPU, memory, and disk stats (root filesystem by default).
- Uses NVML bindings (if present) for NVIDIA GPU utilization, memory usage, temperatures, and power draw.
- Emits structured samples that include precise timestamps and host metadata.

### Storage

- SQLite database with tiered retention tables: `samples_5s`, `samples_1m`, `samples_5m`.
- Promotion jobs aggregate data from fine-grained tables to coarse tables to extend history without bloating the database.
- Pruning logic keeps ~1 hour of 5-second points, ~24 hours of 1-minute points, and multi-day (configurable) coverage for 5-minute points.
- `/api/v1/history` queries the appropriate tier depending on the requested window (1h → 5s, 24h → 1m, 7d → 5m) and the dashboard renders them as line charts.

### HTTP Layer

- Small Flask application that exposes:
  - `/api/v1/live` for the most recent collector snapshot (no sampling on-demand).
  - `/api/v1/settings` so the dashboard can read/update the collector interval without restarting the daemon.
  - `/` serving an inline HTML/JS dashboard that polls the live endpoint every few seconds.
- Future endpoints (`/api/v1/metrics`, `/api/v1/history`, etc.) will hang off the same app once SQLite-backed history lands.
- Includes a simple pathway for adding auth/CORS later (not implemented yet).

### CLI / Daemon Supervisor

- Entry point `monilite serve` spins up the collector thread and Flask app in-process.
- Flags expose host/port, log level, and a `--no-gpu` switch to skip NVML entirely. Sampling interval is controlled at runtime via `/api/v1/settings`.
- History toggles are deferred until the persistence layer is available; additional commands (e.g., `monilite check`) remain on the roadmap.

## Data Model

Each sample record stores:

- Timestamp (UTC)
- Metric type (CPU, memory, disk, GPU)
- Numeric payload (simple floats for utilization %, memory MB, watts)
- JSON blob for auxiliary metadata (e.g., per-GPU breakdowns)

Aggregations roll up averages and peak values over fixed windows.

## Future Considerations

- Config file support (likely TOML) to persist daemon options.
- Optional TLS for the HTTP server.
- Export hooks for external tooling, but only when they do not inflate dependencies.
