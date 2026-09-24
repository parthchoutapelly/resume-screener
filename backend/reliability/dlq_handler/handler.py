"""dlqHandler — turns exhausted retries into visible terminal states (docs/03 §7).

Idempotent under redelivery and never regresses a successful state (R-ERR-07):
every status write carries a condition that refuses to overwrite `parsed` /
`scored`. Terminal-failure metrics go out as CloudWatch Embedded Metric Format
lines on stdout, so no PutMetricData permission is needed (D-49).
"""

import json
import os
import time
from urllib.parse import unquote_plus

import boto3

from rs_common import clock, ids
from rs_common.ddb import conditional_update
from rs_common.errors import ErrorCode, Stage

_ddb = boto3.resource("dynamodb")
JOBS, CANDIDATES = _ddb.Table(os.environ["JOBS_TABLE"]), _ddb.Table(os.environ["CANDIDATES_TABLE"])
FAILED = _ddb.Table(os.environ["FAILED_JOBS_TABLE"])
INGESTION_DLQ_ARN = os.environ["INGESTION_DLQ_ARN"]  # compare ARNs exactly - no substring matching


def lambda_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        if record["eventSourceARN"] == INGESTION_DLQ_ARN:
            if body.get("Event") == "s3:TestEvent":
                continue
            for rec in body.get("Records", []):
                on_ingestion_exhausted(unquote_plus(rec["s3"]["object"]["key"]), record["body"])
        else:
            on_scoring_exhausted(body.get("job_id"), body.get("candidate_id"), record["body"])


def audit(job_id, cand_id, stage, max_receive, raw):
    item = {
        "job_id": job_id or "unknown",
        "failure_id": ids.failure_id(),
        "stage": str(stage),
        "terminal": True,
        "error_type": "RetriesExhausted",
        "error_message": f"Exceeded maxReceiveCount={max_receive}; see earlier attempt rows",
        "retry_count": max_receive,
        "raw_payload": raw,
        "created_at": clock.now_iso(),
        "expires_at": clock.epoch_in_days(90),
    }
    if cand_id:
        item["candidate_id"] = cand_id
    FAILED.put_item(Item=item)
    emit_metric("ingestion" if stage == Stage.INGESTION_EXHAUSTED else "scoring")


def on_ingestion_exhausted(key, raw):
    parts = key.split("/")
    if parts[0] == "jd-uploads" and len(parts) == 3:
        job_id, cand_id = parts[1], None
    elif parts[0] == "resume-uploads" and len(parts) == 4:
        job_id, cand_id = parts[1], parts[2]
    else:
        job_id, cand_id = None, None
    audit(job_id, cand_id, Stage.INGESTION_EXHAUSTED, 3, raw)
    if job_id:
        table, k = (
            (CANDIDATES, {"job_id": job_id, "candidate_id": cand_id})
            if cand_id
            else (JOBS, {"job_id": job_id})
        )
        conditional_update(
            table,
            Key=k,
            UpdateExpression="SET parse_status=:e, error_code=:c, updated_at=:t",
            ConditionExpression="attribute_exists(job_id) AND (attribute_not_exists(parse_status) OR parse_status <> :p)",  # never regress (D-40)
            ExpressionAttributeValues={
                ":e": "error",
                ":c": str(ErrorCode.PROCESSING_FAILED),
                ":p": "parsed",
                ":t": clock.now_iso(),
            },
        )


def on_scoring_exhausted(job_id, cand_id, raw):
    audit(job_id, cand_id, Stage.SCORING_EXHAUSTED, 5, raw)
    if job_id and cand_id:
        conditional_update(
            CANDIDATES,
            Key={"job_id": job_id, "candidate_id": cand_id},
            UpdateExpression="SET score_status=:e, error_code=:c, updated_at=:t",  # score_status, NOT parse_status (D-17)
            ConditionExpression="attribute_exists(candidate_id) AND (attribute_not_exists(score_status) OR score_status <> :s)",
            ExpressionAttributeValues={
                ":e": "error",
                ":c": str(ErrorCode.SCORING_FAILED),
                ":s": "scored",
                ":t": clock.now_iso(),
            },
        )


def emit_metric(queue):
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "ResumeScreener",
                            "Dimensions": [["Queue"]],
                            "Metrics": [{"Name": "TerminalFailures", "Unit": "Count"}],
                        }
                    ],
                },
                "Queue": queue,
                "TerminalFailures": 1,
            }
        )
    )
