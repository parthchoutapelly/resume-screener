"""GET /jobs/{job_id}/candidates — EVERY candidate with a derived display_status.

A base-table Query, not a GSI (D-16): a sparse score index would hide the
pending/error/unscored rows the recruiter most needs to see.
"""

import os

import boto3
from boto3.dynamodb.conditions import Key

from rs_common import clock, views
from rs_common.authz import Caller, load_job_for
from rs_common.http import api_handler, path_id
from rs_common.status import sort_key

_CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATES_TABLE"])


@api_handler
def lambda_handler(event, caller: Caller):
    job_id = path_id(event, "job_id", "job")
    job = load_job_for(caller, job_id)

    items, kwargs = [], {"KeyConditionExpression": Key("job_id").eq(job_id), "ConsistentRead": True}
    while True:
        page = _CANDIDATES.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    now = clock.now()
    rows = sorted((views.candidate_view(c, job, now) for c in items), key=sort_key)
    return 200, {"job_id": job_id, "candidates": rows}
