# MONILite HTTP API

The HTTP service exposes a compact REST-style API plus static assets for the dashboard.

## Base URL

```
http://<host>:<port>
```

Default host is `0.0.0.0`, default port is `8000`.

## Endpoints

### `GET /api/v1/live`

Returns the latest snapshot that the background collector gathered (roughly every 5 seconds by default). The collector runs independently, so this endpoint is fast and does not trigger sampling itself.

```json
{
  "timestamp": "2024-06-01T12:34:56.123456+00:00",
  "cpu": {
    "utilization_pct": 42.3,
    "load_avg": [0.51, 0.48, 0.52],
    "count": 8
  },
  "memory": {
    "used_mb": 3120,
    "available_mb": 4700,
    "total_mb": 7820,
    "utilization_pct": 39.9
  },
  "disk": {
    "path": "/",
    "used_mb": 420000,
    "free_mb": 360000,
    "total_mb": 780000,
    "utilization_pct": 53.8,
    "message": null
  },
  "gpu": {
    "available": true,
    "devices": [
      {
        "index": 0,
        "name": "RTX 3070",
        "utilization_pct": 11.5,
        "memory": {"used_mb": 512, "total_mb": 8192},
        "temperature_c": 45.2,
        "power_w": 45.0
      }
    ],
    "message": null
  }
}
```

If GPU readings are disabled or unavailable, `gpu.available` is `false` and a `message` string explains the reason while keeping the rest of the payload intact. When disk usage cannot be collected, the `disk` object contains `null` values and an explanatory `message`.

### `GET /api/v1/settings`

Returns the current sampling interval used by the collector (in seconds):

```json
{
  "interval": 5
}
```

The dashboard uses this endpoint to render the drop-down selector.

### `POST /api/v1/settings`

Updates the sampling interval at runtime. Body must be JSON with a positive `interval` value, for example:

```json
{
  "interval": 2
}
```

The response mirrors the `GET` payload. The collector applies the change without restarting the process, so the dashboard updates immediately.

### `GET /api/v1/history`

Query params:

- `window` – `1h`, `24h`, or `7d`.

The endpoint returns down-sampled data from the tiered SQLite tables:

```json
{
  "window": "24h",
  "points": [
    {
      "timestamp": "2024-06-01T12:00:00Z",
      "cpu": {"utilization_pct": 23.1},
      "memory": {"utilization_pct": 40.2, "used_mb": 3120, "total_mb": 7820},
      "disk": {"utilization_pct": 55.3},
      "gpu": {"utilization_pct": 17.5}
    }
  ]
}
```

These points feed the dashboard's trend charts for CPU, memory, disk, and GPU utilization. The tiers map windows to sampling granularity (`1h` → 5-second samples, `24h` → 1-minute, `7d` → 5-minute).

### `GET /`

Serves the bundled HTML dashboard, plus inline JS that polls `/api/v1/live` every few seconds and updates the page.

### Planned endpoints

The following routes are specified here for continuity with the long-term design, but they are **not implemented yet**:

- `GET /api/v1/metrics` – latest CPU, memory, GPU values + metadata direct from storage.

## Status Codes

- `200` success
- `400` invalid query params
- `404` unknown endpoint
- `500` unexpected errors from collectors/storage

## Authentication

Not implemented yet. Short-term, rely on network access controls (bind to localhost or firewall rules).
