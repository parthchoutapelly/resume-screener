"""scoreMatch — SQS-triggered scoring (docs/03 §4, Architecture.md §3.3, D-18).

"Not ready" is not an error: an unparsed candidate or a non-scorable job is
ACKED (R-ERR-04) because the JD-parsed fan-out or a PATCH re-triggers scoring.
Only a genuine exception is recorded and re-raised for SQS to retry.
"""

import json
import os

import boto3

from rs_common import clock, ids, log, scoring
from rs_common.ddb import conditional_update, to_decimal
from rs_common.errors import Stage, safe_message
from rs_common.requirements import scorable

_ddb = boto3.resource("dynamodb")
JOBS, CANDIDATES = _ddb.Table(os.environ["JOBS_TABLE"]), _ddb.Table(os.environ["CANDIDATES_TABLE"])
FAILED = _ddb.Table(os.environ["FAILED_JOBS_TABLE"])


def lambda_handler(event, context):
    for record in event["Records"]:  # BatchSize = 1
        msg = json.loads(record["body"])
        job_id, cand_id = msg["job_id"], msg["candidate_id"]
        try:
            score_one(job_id, cand_id, msg.get("reason"))
        except Exception as e:  # noqa: BLE001 - genuine failure: audit + SQS retry (<=5), R-ERR-03
            FAILED.put_item(
                Item={
                    "job_id": job_id,
                    "failure_id": ids.failure_id(),
                    "candidate_id": cand_id,
                    "stage": str(Stage.SCORING),
                    "error_type": type(e).__name__,
                    "error_message": safe_message(e),
                    "terminal": False,
                    "retry_count": int(record.get("attributes", {}).get("ApproximateReceiveCount", "1")),
                    "created_at": clock.now_iso(),
                    "expires_at": clock.epoch_in_days(90),
                }
            )
            raise


def score_one(job_id: str, cand_id: str, reason: str | None) -> None:
    job = JOBS.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
    cand = CANDIDATES.get_item(Key={"job_id": job_id, "candidate_id": cand_id}, ConsistentRead=True).get(
        "Item"
    )
    if not cand or cand.get("parse_status") != "parsed":
        log.info("skip_not_parsed", stage="scoring", job_id=job_id, candidate_id=cand_id)
        return
    if not job or not scorable(job):
        log.info("skip_job_not_scorable", stage="scoring", job_id=job_id, candidate_id=cand_id)
        return

    r = scoring.score(cand, job)
    has_title = r.title_match_held is not None
    values = {
        ":m": to_decimal(r.match_score),
        ":s": to_decimal(r.skills_score),
        ":ti": to_decimal(r.title_score),
        ":e": to_decimal(r.experience_score),
        ":ms": r.matched_skills,
        ":mi": r.missing_skills,
        ":tt": r.title_match_type,
        ":rec": r.recommended,
        ":v": scoring.SCORING_VERSION,
        ":t": clock.now_iso(),
        ":ss": "scored",
        ":parsed": "parsed",
    }
    expr = (
        "SET match_score=:m, skills_score=:s, title_score=:ti, experience_score=:e, "
        "matched_skills=:ms, missing_skills=:mi, title_match_type=:tt, shortlist_candidate=:rec, "
        "scoring_version=:v, scored_at=:t, score_status=:ss, updated_at=:t"
    )
    if has_title:
        expr += ", title_match_held=:th, title_match_required=:tr"
        values |= {":th": r.title_match_held, ":tr": r.title_match_required}
    else:
        expr += " REMOVE title_match_held, title_match_required"  # don't keep a stale earlier explanation
    # Never touches decision / notification_* (R-BUS-05).
    ok = conditional_update(
        CANDIDATES,
        Key={"job_id": job_id, "candidate_id": cand_id},
        UpdateExpression=expr,
        ConditionExpression="parse_status = :parsed",
        ExpressionAttributeValues=values,
    )
    log.info(
        "scored" if ok else "score_skipped_state_changed",
        stage="scoring",
        job_id=job_id,
        candidate_id=cand_id,
        reason=reason,
        match_score=r.match_score,
    )
