#!/usr/bin/env python3
"""External signal health check for paper/live readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_config import load_stock_config
from external_signals import ExternalSignalMonitor


def main() -> int:
    parser = argparse.ArgumentParser(description="Check external signal feed health")
    parser.add_argument("--symbols", nargs="*", help="Symbols to probe")
    parser.add_argument("--json-out", default="", help="Optional output path for machine-readable status")
    args = parser.parse_args()

    cfg = load_stock_config()
    symbols = args.symbols or list(cfg.symbols)
    monitor = ExternalSignalMonitor(cfg)

    status = {
        "enabled": bool(getattr(cfg, "external_signals_enabled", False)),
        "symbols": {},
    }

    print("=== External Signal Health ===")
    for symbol in symbols:
        snap = monitor.get_snapshot(symbol)
        status["symbols"][symbol] = {
            "mode": snap.mode,
            "sentiment": snap.sentiment_score,
            "catalyst": snap.catalyst_score,
            "event_risk": snap.event_risk,
            "confidence": snap.confidence,
            "source_status": snap.source_status,
        }
        print(
            f"{symbol}: mode={snap.mode} sentiment={snap.sentiment_score:+.2f} "
            f"catalyst={snap.catalyst_score:.2f} event_risk={snap.event_risk:.2f} confidence={snap.confidence:.2f}"
        )

    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(f"Wrote: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
