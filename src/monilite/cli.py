"""Command-line interface for MONILite."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from .metrics import MetricsCollector
from .server import create_app
from .storage import HistoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monilite",
        description="Lightweight system monitoring daemon with built-in dashboard.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices={"serve"},
        help="Operation to run (default: serve).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Interface/IP for the HTTP server (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP server port to bind (default: 8000).",
    )
    parser.add_argument(
        "--no-gpu",
        dest="gpu",
        action="store_false",
        help="Skip GPU/NVML probing entirely.",
    )
    parser.add_argument(
        "--db-path",
        default="monilite_history.db",
        help="SQLite database file used for historical metrics (default: monilite_history.db).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Python logging level (default: INFO).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(args=argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "serve":
        return _serve(args)
    parser.error(f"Unknown command: {args.command}")
    return 1


def _serve(args: argparse.Namespace) -> int:
    enable_gpu = bool(getattr(args, "gpu", True))
    history_store = HistoryStore(args.db_path)
    collector = MetricsCollector(enable_gpu=enable_gpu, history_store=history_store)
    collector.start()
    app = create_app(collector, history_store=history_store)

    try:
        app.run(host=args.host, port=args.port, use_reloader=False)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Received interrupt, shutting down…")
        return 130
    finally:
        collector.stop()
        history_store.close()

    return 0
