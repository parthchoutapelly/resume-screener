"""Structured JSON logging (Architecture.md §11.5). One JSON line per event to
stdout — CloudWatch Logs picks up stdout automatically, and Lambda's
LoggingConfig.LogFormat=JSON in template.yaml keeps the platform's own
runtime lines in the same shape.

Safety net (R-PRIV-01): forbidden keys are dropped before serialization, not
just "please don't pass them" — a caller that accidentally does
`log.info(..., extracted_text=text)` gets the key silently stripped rather
than leaking resume content into CloudWatch.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

_FORBIDDEN_KEYS = frozenset(
    {
        "text",
        "extracted_text",
        "email",
        "name",
        "phone",
        "phone_number",
        "raw_text",
        "body",
        "skills",
        "titles_held",
        "employers",
    }
)


def _emit(level: str, msg: str, **fields: Any) -> None:
    record: dict[str, Any] = {
        "level": level,
        "msg": msg,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    for k, v in fields.items():
        if k in _FORBIDDEN_KEYS:
            continue
        record[k] = v
    print(json.dumps(record, default=str), file=sys.stdout)


def info(msg: str, **fields: Any) -> None:
    _emit("INFO", msg, **fields)


def warning(msg: str, **fields: Any) -> None:
    _emit("WARNING", msg, **fields)


def error(msg: str, **fields: Any) -> None:
    _emit("ERROR", msg, **fields)
