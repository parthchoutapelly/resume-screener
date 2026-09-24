"""POST /jobs — create a job and hand back presigned upload credentials.

Ordering is the point of this handler (docs/03 §6): the job row and every
candidate placeholder are written BEFORE any upload credential or jd.txt
exists, so extraction can never see an object without its placeholder and
misclassify it as an orphan.
"""

import os

import boto3

from rs_common import clock, ids, log, uploads, validate
from rs_common.authz import Caller
from rs_common.ddb import to_decimal
from rs_common.http import api_handler, json_body

_ddb = boto3.resource("dynamodb")
JOBS, CANDIDATES = _ddb.Table(os.environ["JOBS_TABLE"]), _ddb.Table(os.environ["CANDIDATES_TABLE"])


@api_handler
def lambda_handler(event, caller: Caller):
    body = validate.create_job(json_body(event))
    now = clock.now_iso()
    expires_at = clock.iso_in_seconds(uploads.UPLOAD_TTL_SECONDS)
    job_id = ids.job_id()
    jd = body["jd"]

    job = {
        "job_id": job_id,
        "recruiter_id": caller.sub,
        "job_title": body["job_title"],
        "jd_source": jd["source"],
        "parse_status": "pending" if jd["source"] in ("file", "text") else "not_applicable",
        "requirements_confirmed": False,
        "shortlist_threshold": body["shortlist_threshold"],
        "created_at": now,
        "updated_at": now,
        **body["requirements"],
    }
    jd_upload = None
    if jd["source"] == "file":
        job["jd_s3_key"] = uploads.jd_key(job_id, jd["ext"])
        job["jd_original_filename"] = jd["filename"]
    elif jd["source"] == "text":
        job["jd_s3_key"] = uploads.jd_key(job_id, "txt")
    JOBS.put_item(Item=to_decimal(job), ConditionExpression="attribute_not_exists(job_id)")

    placeholders = [
        uploads.new_placeholder(job_id, fn, validate.ext_of(fn), now, expires_at)
        for fn in body["resume_filenames"]
    ]
    with CANDIDATES.batch_writer() as batch:
        for p in placeholders:
            batch.put_item(Item=p)

    # Only now may anything trigger extraction.
    if jd["source"] == "text":
        try:
            uploads.s3().put_object(
                Bucket=uploads.bucket(),
                Key=job["jd_s3_key"],
                Body=jd["text"].encode("utf-8"),
                ContentType="text/plain",
            )
        except Exception:
            # Don't leave a job "pending" forever waiting for a JD that will never arrive.
            JOBS.put_item(
                Item=to_decimal(
                    {
                        **job,
                        "parse_status": "error",
                        "error_code": "processing_failed",
                        "updated_at": clock.now_iso(),
                    }
                )
            )
            raise
    elif jd["source"] == "file":
        jd_upload = uploads.presign_post(job["jd_s3_key"], jd["ext"])

    resumes = [
        {
            "candidate_id": p["candidate_id"],
            "filename": p["original_filename"],
            "upload": uploads.presign_post(p["resume_s3_key"], validate.ext_of(p["original_filename"])),
        }
        for p in placeholders
    ]
    log.info("job_created", stage="api", job_id=job_id, resumes=len(resumes), jd_source=jd["source"])
    return 201, {"job_id": job_id, "jd_upload": jd_upload, "resumes": resumes}
