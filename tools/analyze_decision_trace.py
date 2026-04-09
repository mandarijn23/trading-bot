#!/usr/bin/env python3
"""Analyze structured decision traces from logs/decision_trace.jsonl."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _pct(num: int, den: int) -> float:
    return (num / den * 100.0) if den else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze bot decision trace events")
    parser.add_argument("--file", default="logs/decision_trace.jsonl", help="Path to decision trace jsonl")
    parser.add_argument("--symbol", default="", help="Optional symbol filter (e.g. SPY)")
    args = parser.parse_args()

    path = Path(args.file)
    events = list(_iter_events(path))
    if args.symbol:
        sym = args.symbol.strip().upper()
        events = [e for e in events if str(e.get("symbol", "")).upper() == sym]

    if not events:
        print("No decision trace events found.")
        return 0

    by_stage = Counter(str(e.get("stage", "unknown")) for e in events)
    by_decision = Counter(f"{e.get('stage', 'unknown')}:{e.get('decision', 'unknown')}" for e in events)

    exits = [e for e in events if str(e.get("stage", "")) == "exit" and str(e.get("decision", "")) == "filled"]
    wins = sum(1 for e in exits if bool(e.get("was_right", False)))
    losses = len(exits) - wins

    reason_stats: Dict[str, List[bool]] = defaultdict(list)
    for e in exits:
        ctx = e.get("entry_context", {}) or {}
        reason = str(ctx.get("signal_reason", "unknown"))
        reason_stats[reason].append(bool(e.get("was_right", False)))

    block_reason_counts = Counter()
    for e in events:
        if str(e.get("decision", "")) == "blocked":
            block_reason_counts[str(e.get("reason", "unknown"))] += 1

    print("=== Decision Trace Summary ===")
    print(f"events={len(events)}")
    if args.symbol:
        print(f"symbol={args.symbol.strip().upper()}")

    print("\n--- Stage counts ---")
    for k, v in by_stage.most_common():
        print(f"{k}: {v}")

    print("\n--- Stage+decision counts ---")
    for k, v in by_decision.most_common():
        print(f"{k}: {v}")

    print("\n--- Exit outcomes ---")
    print(f"closed_trades={len(exits)}")
    print(f"wins={wins} ({_pct(wins, len(exits)):.1f}%)")
    print(f"losses={losses} ({_pct(losses, len(exits)):.1f}%)")

    print("\n--- Win rate by entry reason ---")
    ranked: List[Tuple[str, int, float]] = []
    for reason, vals in reason_stats.items():
        total = len(vals)
        wr = _pct(sum(1 for x in vals if x), total)
        ranked.append((reason, total, wr))
    ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
    for reason, total, wr in ranked:
        print(f"{reason}: trades={total} win_rate={wr:.1f}%")

    print("\n--- Top block reasons ---")
    for reason, count in block_reason_counts.most_common(15):
        print(f"{reason}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
