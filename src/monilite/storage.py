"""SQLite-backed history storage for MONILite."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


class HistoryStore:
    """Tiered history storage with 5s, 1m, and 5m buckets."""

    WINDOWS: Dict[str, Tuple[str, int]] = {
        "1h": ("samples_5s", 60 * 60),
        "24h": ("samples_1m", 24 * 60 * 60),
        "7d": ("samples_5m", 7 * 24 * 60 * 60),
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples_5s (
                    ts INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples_1m (
                    ts INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples_5m (
                    ts INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def record_snapshot(self, snapshot: Dict[str, Any]) -> None:
        ts = self._snapshot_timestamp(snapshot)
        payload = json.dumps(snapshot, separators=(",", ":"))
        now = int(time.time())
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO samples_5s (ts, payload) VALUES (?, ?)",
                    (ts, payload),
                )
                self._maybe_promote_bucket(ts, "samples_5s", "samples_1m", 60)
                self._maybe_promote_bucket(ts, "samples_1m", "samples_5m", 300)
                self._prune(now)

    def fetch_window(self, window: str) -> List[Dict[str, Any]]:
        if window not in self.WINDOWS:
            raise ValueError(f"Unknown window '{window}'")
        table, span = self.WINDOWS[window]
        since = int(time.time()) - span
        with self._lock:
            rows = list(
                self._conn.execute(
                    f"SELECT ts, payload FROM {table} WHERE ts >= ? ORDER BY ts ASC",
                    (since,),
                )
            )
        return [self._row_to_point(row) for row in rows]

    def _row_to_point(self, row: sqlite3.Row) -> Dict[str, Any]:
        ts = datetime.fromtimestamp(row["ts"], tz=timezone.utc).isoformat()
        payload = json.loads(row["payload"])
        return {
            "timestamp": ts,
            "cpu": {
                "utilization_pct": payload.get("cpu", {}).get("utilization_pct"),
            },
            "memory": {
                "utilization_pct": payload.get("memory", {}).get("utilization_pct"),
                "used_mb": payload.get("memory", {}).get("used_mb"),
                "total_mb": payload.get("memory", {}).get("total_mb"),
            },
            "disk": {
                "utilization_pct": payload.get("disk", {}).get("utilization_pct"),
            },
            "gpu": {
                "utilization_pct": self._average_gpu_util(payload.get("gpu")),
            },
        }

    @staticmethod
    def _average_gpu_util(gpu_payload: Dict[str, Any] | None) -> float | None:
        if not gpu_payload:
            return None
        devices = gpu_payload.get("devices") or []
        values: List[float] = []
        for device in devices:
            util = device.get("utilization_pct")
            if isinstance(util, (int, float)):
                values.append(float(util))
        if not values:
            return None
        return sum(values) / len(values)

    def _maybe_promote_bucket(
        self,
        ts: int,
        source_table: str,
        target_table: str,
        bucket_size: int,
    ) -> None:
        bucket = ts - (ts % bucket_size)
        cur = self._conn.execute(
            f"SELECT 1 FROM {target_table} WHERE ts = ?",
            (bucket,),
        )
        if cur.fetchone():
            return
        cur = self._conn.execute(
            f"""
            SELECT payload FROM {source_table}
            WHERE ts >= ? AND ts < ?
            ORDER BY ts DESC LIMIT 1
            """,
            (bucket, bucket + bucket_size),
        )
        row = cur.fetchone()
        if not row:
            return
        self._conn.execute(
            f"INSERT OR IGNORE INTO {target_table} (ts, payload) VALUES (?, ?)",
            (bucket, row["payload"]),
        )

    def _prune(self, now: int) -> None:
        self._conn.execute(
            "DELETE FROM samples_5s WHERE ts < ?",
            (now - 60 * 60,),
        )
        self._conn.execute(
            "DELETE FROM samples_1m WHERE ts < ?",
            (now - 24 * 60 * 60,),
        )

    @staticmethod
    def _snapshot_timestamp(snapshot: Dict[str, Any]) -> int:
        ts_str = snapshot.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                return int(dt.timestamp())
            except ValueError:
                pass
        return int(time.time())
