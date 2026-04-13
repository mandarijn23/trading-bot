"""Tests for JSON structured event logger."""

from __future__ import annotations

import json

from observability.json_logger import JsonEventLogger


def test_json_logger_writes_parseable_jsonl(tmp_path):
    path = tmp_path / "events.jsonl"
    logger = JsonEventLogger(str(path))

    logger.log_event(
        {
            "event": "order_submitted",
            "symbol": "SPY",
            "qty": 5,
        },
        level="INFO",
        component="OrderExecution",
    )

    content = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1

    payload = json.loads(content[0])
    assert payload["event"] == "order_submitted"
    assert payload["symbol"] == "SPY"
    assert payload["qty"] == 5
    assert payload["level"] == "INFO"
    assert payload["component"] == "OrderExecution"
    assert "timestamp" in payload
