"""GET /jobs — the caller's jobs (Admin: all jobs), newest first, paginated."""

import os

import boto3
from boto3.dynamodb.conditions import Key

from rs_common import views
from rs_common.authz import Caller
from rs_common.http import HttpError, api_handler, decode_token, encode_token, query_param

_JOBS = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE"])
PAGE = 50


@api_handler
def lambda_handler(event, caller: Caller):
    token = query_param(event, "next_token")
    if caller.is_admin:
        kwargs = {"Limit": PAGE}
        if token:
            kwargs["ExclusiveStartKey"] = decode_token(token, {"job_id"})
        page = _JOBS.scan(**kwargs)
        items = sorted(page["Items"], key=lambda j: j.get("created_at", ""), reverse=True)
    else:
        kwargs = {
            "IndexName": "RecruiterJobsIndex",
            "KeyConditionExpression": Key("recruiter_id").eq(caller.sub),
            "ScanIndexForward": False,
            "Limit": PAGE,
        }
        if token:
            key = decode_token(token, {"job_id", "recruiter_id", "created_at"})
            if key.get("recruiter_id") != caller.sub:  # a token from someone else's listing
                raise HttpError(400, "VALIDATION_FAILED", "Invalid next_token.")
            kwargs["ExclusiveStartKey"] = key
        page = _JOBS.query(**kwargs)
        items = page["Items"]

    body = {"jobs": [views.job_row(j, admin=caller.is_admin) for j in items]}
    body["next_token"] = encode_token(page["LastEvaluatedKey"]) if "LastEvaluatedKey" in page else None
    return 200, body
