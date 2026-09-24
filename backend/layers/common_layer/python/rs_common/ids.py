"""ID generation. Full uuid4 hex, never truncated (D-37 — the original design's
`job_{uuid4().hex[:12]}` gave up too many collision-resistance bits for no
real benefit)."""

from __future__ import annotations

import uuid


def job_id() -> str:
    return f"job_{uuid.uuid4().hex}"


def candidate_id() -> str:
    return f"cand_{uuid.uuid4().hex}"


def failure_id() -> str:
    return f"fail_{uuid.uuid4().hex}"
