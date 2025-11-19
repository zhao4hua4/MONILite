"""Metric collection utilities for MONILite."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .storage import HistoryStore

import psutil

logger = logging.getLogger(__name__)

try:  # Optional dependency for NVIDIA metrics
    import pynvml  # type: ignore

    _NVML_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - optional dep
    pynvml = None  # type: ignore
    _NVML_IMPORT_ERROR = str(exc)

_NVML_INITIALIZED = False
_NVML_INIT_ERROR: Optional[str] = None
_NVML_FAILURE_LOGGED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bytes_to_mb(value: float) -> float:
    return round(value / (1024 * 1024), 2)


def _ensure_nvml() -> bool:
    """Initialize NVML once; return True when ready."""

    global _NVML_INITIALIZED, _NVML_INIT_ERROR
    if pynvml is None:
        if _NVML_INIT_ERROR is None:
            _set_nvml_error("NVML bindings (pynvml) not installed")
        return False

    if _NVML_INITIALIZED:
        return True

    try:
        pynvml.nvmlInit()  # type: ignore[attr-defined]
        _NVML_INITIALIZED = True
        return True
    except Exception as exc:  # pragma: no cover - depends on hardware
        _set_nvml_error(str(exc))
        return False


def _set_nvml_error(message: str) -> None:
    global _NVML_INIT_ERROR, _NVML_FAILURE_LOGGED
    _NVML_INIT_ERROR = message
    if not _NVML_FAILURE_LOGGED:
        logger.warning("NVML unavailable: %s", message)
        _NVML_FAILURE_LOGGED = True


def _gpu_metrics(enable_gpu: bool) -> Dict[str, Any]:
    if not enable_gpu:
        return {
            "available": False,
            "devices": [],
            "message": "GPU metrics disabled via CLI flag",
        }

    if not _ensure_nvml():
        return {
            "available": False,
            "devices": [],
            "message": _NVML_INIT_ERROR or _NVML_IMPORT_ERROR,
        }

    try:
        count = pynvml.nvmlDeviceGetCount()  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - NVML runtime
        _set_nvml_error(str(exc))
        return {
            "available": False,
            "devices": [],
            "message": _NVML_INIT_ERROR,
        }

    if count == 0:  # pragma: no cover - hardware specific
        return {
            "available": False,
            "devices": [],
            "message": "No NVIDIA GPUs detected",
        }

    devices: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index in range(count):  # pragma: no cover - depends on hardware
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)  # type: ignore[attr-defined]
            raw_name = pynvml.nvmlDeviceGetName(handle)  # type: ignore[attr-defined]
            if isinstance(raw_name, bytes):
                name = raw_name.decode("utf-8", errors="ignore")
            else:
                name = str(raw_name)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)  # type: ignore[attr-defined]
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)  # type: ignore[attr-defined]
            temperature = pynvml.nvmlDeviceGetTemperature(  # type: ignore[attr-defined]
                handle, pynvml.NVML_TEMPERATURE_GPU  # type: ignore[attr-defined]
            )
            power = None
            try:
                power = round(
                    pynvml.nvmlDeviceGetPowerUsage(handle)  # type: ignore[attr-defined]
                    / 1000.0,
                    2,
                )
            except Exception:
                power = None

            devices.append(
                {
                    "index": index,
                    "name": name,
                    "utilization_pct": float(utilization.gpu),
                    "memory": {
                        "used_mb": _bytes_to_mb(memory.used),
                        "total_mb": _bytes_to_mb(memory.total),
                    },
                    "temperature_c": float(temperature),
                    "power_w": power,
                }
            )
        except Exception as exc:
            logger.debug("Failed to collect GPU metrics for index %s: %s", index, exc)
            errors.append(str(exc))

    if devices:
        message = None
    elif errors:
        message = f"NVML error: {errors[-1]}"
    else:
        message = "Failed to read GPU metrics"

    return {
        "available": len(devices) > 0,
        "devices": devices,
        "message": message,
    }


def _cpu_metrics() -> Dict[str, Any]:
    try:
        load_avg = [float(value) for value in os.getloadavg()]
    except (AttributeError, OSError):  # pragma: no cover - platform specific
        load_avg = None

    return {
        "utilization_pct": float(psutil.cpu_percent(interval=None)),
        "load_avg": load_avg,
        "count": psutil.cpu_count(logical=True),
    }


def _memory_metrics() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    return {
        "total_mb": _bytes_to_mb(vm.total),
        "used_mb": _bytes_to_mb(vm.used),
        "available_mb": _bytes_to_mb(vm.available),
        "utilization_pct": float(vm.percent),
    }


def _disk_metrics() -> Dict[str, Any]:
    """Return disk usage information for the root filesystem."""

    try:
        usage = psutil.disk_usage("/")
    except Exception as exc:  # pragma: no cover - environment-specific
        logger.debug("Failed to read disk usage: %s", exc)
        return {
            "path": "/",
            "total_mb": None,
            "used_mb": None,
            "free_mb": None,
            "utilization_pct": None,
            "message": "Disk usage unavailable",
        }

    return {
        "path": "/",
        "total_mb": _bytes_to_mb(usage.total),
        "used_mb": _bytes_to_mb(usage.used),
        "free_mb": _bytes_to_mb(usage.free),
        "utilization_pct": float(usage.percent),
        "message": None,
    }


def collect_once(enable_gpu: bool = True) -> Dict[str, Any]:
    """Collect a single metrics snapshot."""

    return {
        "timestamp": _now_iso(),
        "cpu": _cpu_metrics(),
        "memory": _memory_metrics(),
        "disk": _disk_metrics(),
        "gpu": _gpu_metrics(enable_gpu=enable_gpu),
    }


@dataclass
class MetricsCollector:
    """Background metrics collector that refreshes a snapshot periodically."""

    interval: float = 5.0
    enable_gpu: bool = True
    history_store: "HistoryStore" | None = None
    _snapshot: Dict[str, Any] = field(default_factory=dict, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _interval_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _interval: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.set_interval(self.interval)

    def start(self) -> None:
        """Start the background collector thread."""

        if self._thread and self._thread.is_alive():
            return

        psutil.cpu_percent(interval=None)  # Prime CPU measurement so the first sample is valid
        time.sleep(min(self.get_interval(), 0.2))
        initial_snapshot = collect_once(enable_gpu=self.enable_gpu)
        with self._lock:
            self._snapshot = initial_snapshot
        if self.history_store:
            try:
                self.history_store.record_snapshot(initial_snapshot)
            except Exception as exc:
                logger.warning("Failed to persist history snapshot: %s", exc)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the collector thread."""

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(self.get_interval() * 2, 1.0))

    def get_snapshot(self) -> Dict[str, Any]:
        """Return the latest collected snapshot."""

        with self._lock:
            if self._snapshot:
                return dict(self._snapshot)
        return collect_once(enable_gpu=self.enable_gpu)

    def _run(self) -> None:
        logger.info(
            "Starting metrics collector (interval=%ss, gpu=%s)",
            self.interval,
            self.enable_gpu,
        )
        while not self._stop_event.is_set():
            snapshot = collect_once(enable_gpu=self.enable_gpu)
            with self._lock:
                self._snapshot = snapshot
            if self.history_store:
                try:
                    self.history_store.record_snapshot(snapshot)
                except Exception as exc:  # pragma: no cover - best-effort logging
                    logger.warning("Failed to persist history snapshot: %s", exc)
            if self._stop_event.wait(self.get_interval()):
                break
        logger.info("Metrics collector stopped")

    def set_interval(self, interval: float) -> None:
        if interval <= 0:
            raise ValueError("Interval must be greater than zero")
        with self._interval_lock:
            self._interval = float(interval)

    def get_interval(self) -> float:
        with self._interval_lock:
            return self._interval
