"""DynamoDB helpers. boto3's resource API requires Decimal for Number
attributes (a bare float raises TypeError) — R-DATA-01. `conditional_update`
turns a failed ConditionExpression into a plain `False` return instead of an
exception, since "the condition didn't hold" is frequently the expected,
non-error outcome (Rules.md §5's status-transition table)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def to_decimal(x: Any) -> Any:
    """Recursively converts float -> Decimal (rounded to 1 dp, matching the
    precision every score/experience value is stored at). Ints, strings,
    bools, and None pass through unchanged."""
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return Decimal(str(round(x, 1)))
    if isinstance(x, list):
        return [to_decimal(v) for v in x]
    if isinstance(x, dict):
        return {k: to_decimal(v) for k, v in x.items()}
    return x


def from_decimal(x: Any) -> Any:
    """Recursively converts Decimal -> float, e.g. before JSON-serializing an
    API response (json.dumps chokes on Decimal)."""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, list):
        return [from_decimal(v) for v in x]
    if isinstance(x, dict):
        return {k: from_decimal(v) for k, v in x.items()}
    return x


def conditional_update(table, **kwargs) -> bool:
    """Wraps table.update_item(**kwargs). Returns True on success, False
    (not raising) when the ConditionExpression fails — that's the expected
    "someone else already moved this forward" / "no item to mark" path
    (Rules.md §5), not a real error. Any other exception still propagates."""
    try:
        table.update_item(**kwargs)
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
