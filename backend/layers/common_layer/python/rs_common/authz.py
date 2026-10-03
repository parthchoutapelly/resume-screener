"""Authorization: the one shared implementation (R-AUTH-01..06). Handlers
call `caller(event)` (done by @api_handler) and `load_job_for(...)`; none
re-implement group or ownership checks."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import boto3

from rs_common.http import HttpError

_JOBS = boto3.resource("dynamodb").Table(os.environ.get("JOBS_TABLE", "unset"))


@dataclass(frozen=True)
class Caller:
    sub: str
    groups: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return "Admin" in self.groups


def caller(event) -> Caller:
    claims = ((event.get("requestContext") or {}).get("authorizer") or {}).get("claims") or {}
    if "sub" not in claims:
        # The gateway authorizer should make this unreachable; fail closed if it isn't.
        raise HttpError(403, "FORBIDDEN", "Your account has no access. Contact an administrator.")
    raw = claims.get("cognito:groups", "")
    # REST authorizers flatten the groups claim to a string like "[Admin Recruiter]"; tolerate lists too.
    groups = frozenset(raw) if isinstance(raw, list) else frozenset(re.findall(r"[A-Za-z0-9_-]+", raw or ""))
    c = Caller(claims["sub"], groups)
    if not c.groups & {"Recruiter", "Admin"}:
        raise HttpError(
            403, "FORBIDDEN", "Your account has no access. Contact an administrator."
        )  # R-AUTH-02
    return c


def require_admin(c: Caller) -> None:
    if not c.is_admin:
        raise HttpError(403, "FORBIDDEN", "Admin access required.")  # R-AUTH-05


def load_job_for(c: Caller, job_id: str) -> dict:
    """Missing and not-owned are the same 404 (R-AUTH-04)."""
    job = _JOBS.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
    if not job or (job["recruiter_id"] != c.sub and not c.is_admin):
        raise HttpError(404, "NOT_FOUND", "Job not found.")
    return job
