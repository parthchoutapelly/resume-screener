"""Candidate display_status derivation and ordering (docs/Architecture.md §7.2).

Stored status fields (`parse_status`, `score_status`) are the raw truth; this
derives the single value the recruiter sees. It is evaluated top to bottom, so
the order of the branches below IS the specification (D-17/D-35).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rs_common import clock
from rs_common.requirements import blocking_reason

UPLOAD_GRACE = timedelta(minutes=2)
STALL_AFTER = timedelta(minutes=60)

ORDER = [
    "scored",
    "scoring",
    "awaiting_jd",
    "awaiting_requirements",
    "processing",
    "stalled",
    "upload_missing",
    "error",
]


def display_status(candidate: dict, job: dict, now: datetime) -> tuple[str, str | None]:
    parse = candidate.get("parse_status", "pending")
    if parse == "error":
        return "error", candidate.get("error_code")
    if parse == "pending":
        started = candidate.get("ingest_started_at")
        if not started:
            expires = candidate.get("upload_expires_at")
            if expires and now > clock.parse_iso(expires) + UPLOAD_GRACE:
                return "upload_missing", None
        elif now - clock.parse_iso(started) > STALL_AFTER:
            return "stalled", None
        return "processing", None
    # parsed
    score_status = candidate.get("score_status", "pending")
    if score_status == "error":
        return "error", "scoring_failed"
    if score_status == "scored":
        return "scored", None
    reason = blocking_reason(job)
    if reason == "awaiting_jd":
        return "awaiting_jd", None
    if reason is not None:
        return "awaiting_requirements", None
    return "scoring", None


def sort_key(row: dict) -> tuple:
    """Scored rows by match_score desc then candidate_id; every other status
    grouped in ORDER, stable by candidate_id."""
    status = row["display_status"]
    rank = ORDER.index(status)
    if status == "scored":
        return (rank, -float(row["match_score"]), row["candidate_id"])
    return (rank, 0.0, row["candidate_id"])
