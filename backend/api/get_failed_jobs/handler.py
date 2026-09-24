"""GET /failed-jobs — Admin-only audit log (R-AUTH-05/07)."""

import os

import boto3
from boto3.dynamodb.conditions import Key

from rs_common.authz import Caller, require_admin
from rs_common.http import HttpError, api_handler, decode_token, encode_token, query_param

_FAILED = boto3.resource("dynamodb").Table(os.environ["FAILED_JOBS_TABLE"])
PAGE = 100
FIELDS = (
    "job_id",
    "failure_id",
    "candidate_id",
    "stage",
    "terminal",
    "retry_count",
    "error_type",
    "error_message",
    "raw_payload",
    "created_at",
)


@api_handler
def lambda_handler(event, caller: Caller):
    require_admin(caller)
    token = query_param(event, "next_token")
    job_id = query_param(event, "job_id")
    kwargs = {"Limit": PAGE}
    if token:
        kwargs["ExclusiveStartKey"] = decode_token(token, {"job_id", "failure_id"})
    if job_id:
        if not job_id.startswith("job_") and job_id != "unknown":
            raise HttpError(400, "VALIDATION_FAILED", "Invalid job_id.")
        page = _FAILED.query(KeyConditionExpression=Key("job_id").eq(job_id), **kwargs)
    else:
        page = _FAILED.scan(**kwargs)

    rows = [{k: f[k] for k in FIELDS if k in f} for f in page["Items"]]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)  # failure_id order isn't chronological
    next_token = encode_token(page["LastEvaluatedKey"]) if "LastEvaluatedKey" in page else None
    return 200, {"failures": rows, "next_token": next_token}
