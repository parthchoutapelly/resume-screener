"""Recruiter decision + the one-time shortlist email (docs/03 §6.1, D-28,
Rules R-BUS-05..08).

The email is at-most-once, enforced by a conditional CLAIM on
`notification_status` made BEFORE calling SES. That ordering is deliberate: a
crash between claim and send leaves `sending` ("status unknown" in the UI)
rather than risking a duplicate, and a duplicate email to a candidate is worse
than an unknown status (Architecture.md §3.4).
"""

from __future__ import annotations

import os
import re
from functools import cache

import boto3
from botocore.exceptions import ClientError

from rs_common import clock, ids, log
from rs_common import normalization as norm
from rs_common.errors import Stage
from rs_common.http import HttpError


@cache
def _sesv2():
    return boto3.client("sesv2")


def _tables():
    ddb = boto3.resource("dynamodb")
    return ddb.Table(os.environ["CANDIDATES_TABLE"]), ddb.Table(os.environ["FAILED_JOBS_TABLE"])


def _greeting(name) -> str:
    # The name comes from a resume (tainted): plain text only, no control characters, bounded.
    clean = re.sub(r"[\x00-\x1f\x7f]+", " ", name or "").strip()[:100]
    return f"Hi {clean}," if clean else "Hello,"


def _body(name, job_title: str) -> str:
    return (
        f"{_greeting(name)}\n\n"
        f"Good news: you have been shortlisted for the {job_title} position. "
        "A member of the recruiting team may contact you about next steps.\n\n"
        "Thank you for your interest.\n"
    )


def _set_notification(
    table, key, status, *, sent: bool = False, condition: str | None = None, values=None
) -> bool:
    expr = "SET notification_status = :n, updated_at = :t" + (", notification_sent_at = :t" if sent else "")
    kwargs = {
        "Key": key,
        "UpdateExpression": expr,
        "ExpressionAttributeValues": {":n": status, ":t": clock.now_iso(), **(values or {})},
    }
    if condition:
        kwargs["ConditionExpression"] = condition
    try:
        table.update_item(**kwargs)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def apply_decision(job: dict, candidate_id: str, decision: str, sub: str) -> dict:
    candidates, failed = _tables()
    key = {"job_id": job["job_id"], "candidate_id": candidate_id}
    if not candidates.get_item(Key=key, ConsistentRead=True).get("Item"):
        raise HttpError(404, "NOT_FOUND", "Candidate not found.")

    now = clock.now_iso()
    try:
        cand = candidates.update_item(
            Key=key,
            UpdateExpression="SET decision = :d, decided_by = :by, decided_at = :t, updated_at = :t",
            ConditionExpression="attribute_exists(candidate_id) AND score_status = :scored",
            ExpressionAttributeValues={":d": decision, ":by": sub, ":t": now, ":scored": "scored"},
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HttpError(409, "NOT_SCORED", "This candidate hasn't been scored yet.") from e
        raise

    def result(status):
        return {"candidate_id": candidate_id, "decision": decision, "notification_status": status}

    current = cand.get("notification_status")
    if decision != "shortlisted":
        return result(current)  # only shortlisting can email (R-BUS-06)

    email = cand.get("email")
    if not email or norm.extract_email(email) != email:
        if _set_notification(
            candidates, key, "skipped_no_email", condition="attribute_not_exists(notification_status)"
        ):
            return result("skipped_no_email")
        return result(current)

    claimed = _set_notification(
        candidates,
        key,
        "sending",
        condition="attribute_not_exists(notification_status) OR notification_status = :failed",
        values={":failed": "failed"},
    )
    if not claimed:
        return result(current)  # already sent / sending / skipped: no email (R-BUS-07)

    try:
        _sesv2().send_email(
            FromEmailAddress=os.environ["SES_SENDER_ADDRESS"],
            Destination={"ToAddresses": [email]},
            Content={
                "Simple": {
                    "Subject": {"Data": f"You've been shortlisted — {job['job_title']}", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": _body(cand.get("name"), job["job_title"]), "Charset": "UTF-8"}},
                }
            },
        )
    except Exception as e:  # noqa: BLE001 - email failure must never fail the decision (R-BUS-08)
        # Only the SES error CODE is recorded: SES messages can echo the recipient address (R-PRIV-02).
        code = e.response["Error"]["Code"] if isinstance(e, ClientError) else type(e).__name__
        _set_notification(candidates, key, "failed")
        log.error(
            "shortlist_email_failed",
            stage="api",
            job_id=job["job_id"],
            candidate_id=candidate_id,
            error_type=code,
        )
        try:
            failed.put_item(
                Item={
                    "job_id": job["job_id"],
                    "failure_id": ids.failure_id(),
                    "candidate_id": candidate_id,
                    "stage": str(Stage.API),
                    "error_type": type(e).__name__,
                    "error_message": f"SES send_email failed: {code}",
                    "terminal": False,
                    "retry_count": 0,
                    "created_at": clock.now_iso(),
                    "expires_at": clock.epoch_in_days(90),
                }
            )
        except Exception as audit_exc:  # noqa: BLE001 - audit is best-effort here
            log.warning("email_audit_failed", stage="api", error_type=type(audit_exc).__name__)
        return result("failed")

    _set_notification(candidates, key, "sent", sent=True)
    return result("sent")
