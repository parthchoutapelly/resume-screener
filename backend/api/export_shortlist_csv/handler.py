"""GET /jobs/{job_id}/export — CSV of the shortlisted candidates only (R-BUS-12)."""

import os
from datetime import UTC, datetime

import boto3
from boto3.dynamodb.conditions import Key

from rs_common import exports, log, uploads
from rs_common.authz import Caller, load_job_for
from rs_common.http import api_handler, path_id

_CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATES_TABLE"])


@api_handler
def lambda_handler(event, caller: Caller):
    job_id = path_id(event, "job_id", "job")
    load_job_for(caller, job_id)

    items, kwargs = [], {"KeyConditionExpression": Key("job_id").eq(job_id), "ConsistentRead": True}
    while True:
        page = _CANDIDATES.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    rows = [c for c in items if c.get("decision") == "shortlisted"]
    rows.sort(key=lambda c: (-float(c.get("match_score", 0)), c["candidate_id"]))

    key = f"exports/{job_id}/{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.csv"
    uploads.s3().put_object(
        Bucket=uploads.bucket(), Key=key, Body=exports.build_csv(rows), ContentType="text/csv; charset=utf-8"
    )
    url = uploads.presign_get(key, uploads.EXPORT_URL_TTL, f'attachment; filename="shortlist-{job_id}.csv"')
    log.info("exported", stage="api", job_id=job_id, row_count=len(rows))
    return 200, {"download_url": url, "row_count": len(rows)}
