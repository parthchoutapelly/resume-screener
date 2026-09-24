"""POST /jobs/{job_id}/resumes — add more resumes to an existing job."""

import os

import boto3
from boto3.dynamodb.conditions import Key

from rs_common import clock, log, uploads, validate
from rs_common.authz import Caller, load_job_for
from rs_common.http import HttpError, api_handler, json_body, path_id

_ddb = boto3.resource("dynamodb")
CANDIDATES = _ddb.Table(os.environ["CANDIDATES_TABLE"])


def count_candidates(job_id: str) -> int:
    kwargs = {"KeyConditionExpression": Key("job_id").eq(job_id), "Select": "COUNT", "ConsistentRead": True}
    total = 0
    while True:
        page = CANDIDATES.query(**kwargs)
        total += page["Count"]
        if "LastEvaluatedKey" not in page:
            return total
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


@api_handler
def lambda_handler(event, caller: Caller):
    job_id = path_id(event, "job_id", "job")
    load_job_for(caller, job_id)
    filenames = validate.add_resumes(json_body(event))
    if count_candidates(job_id) + len(filenames) > validate.MAX_CANDIDATES_PER_JOB:
        raise HttpError(
            400, "LIMIT_EXCEEDED", f"A job can have at most {validate.MAX_CANDIDATES_PER_JOB} candidates."
        )

    now = clock.now_iso()
    expires_at = clock.iso_in_seconds(uploads.UPLOAD_TTL_SECONDS)
    placeholders = [
        uploads.new_placeholder(job_id, fn, validate.ext_of(fn), now, expires_at) for fn in filenames
    ]
    with CANDIDATES.batch_writer() as batch:
        for p in placeholders:
            batch.put_item(Item=p)

    resumes = [
        {
            "candidate_id": p["candidate_id"],
            "filename": p["original_filename"],
            "upload": uploads.presign_post(p["resume_s3_key"], validate.ext_of(p["original_filename"])),
        }
        for p in placeholders
    ]
    log.info("resumes_added", stage="api", job_id=job_id, count=len(resumes))
    return 201, {"job_id": job_id, "resumes": resumes}
