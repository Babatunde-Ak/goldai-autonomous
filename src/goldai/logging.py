from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Small structured formatter that excludes secrets by design."""

    def format(self, record: logging.LogRecord) -> str:
        value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("event_id", "correlation_id", "strategy_id"):
            if hasattr(record, key):
                value[key] = getattr(record, key)
        return json.dumps(value, sort_keys=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

