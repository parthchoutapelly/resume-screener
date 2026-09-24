"""Time helpers, kept in one place so tests can inject a fixed "now" instead
of monkeypatching datetime everywhere (R-DATA-05: UTC, ISO-8601, 'Z' suffix,
never utcnow()).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def now_iso() -> str:
    """Current UTC time as ISO-8601 with a 'Z' suffix, e.g. 2026-09-24T10:15:30Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> date:
    """Current UTC date. Experience computation resolves "Present"/"Current" to this."""
    return datetime.now(UTC).date()


def epoch_in_days(n: int) -> int:
    """Unix epoch seconds n days from now — used for DynamoDB TTL attributes
    (failed_jobs.expires_at, R-DATA-08's 90-day audit retention)."""
    return int((datetime.now(UTC) + timedelta(days=n)).timestamp())
