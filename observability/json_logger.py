"""Structured JSON event logger."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class JsonEventLogger:
    """Write newline-delimited JSON events for machine parsing."""

    def __init__(self, file_path: str = "logs/events.jsonl") -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_event(
        self,
        event: Mapping[str, Any],
        level: str = "INFO",
        component: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": str(level).upper(),
            **dict(event),
        }
        if component is not None and "component" not in payload:
            payload["component"] = component

        line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        with self._lock:
            with self.file_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return payload

    def info(self, event: Mapping[str, Any], component: str | None = None) -> dict[str, Any]:
        return self.log_event(event=event, level="INFO", component=component)

    def warning(self, event: Mapping[str, Any], component: str | None = None) -> dict[str, Any]:
        return self.log_event(event=event, level="WARNING", component=component)

    def error(self, event: Mapping[str, Any], component: str | None = None) -> dict[str, Any]:
        return self.log_event(event=event, level="ERROR", component=component)
