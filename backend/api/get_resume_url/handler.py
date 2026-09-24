"""GET /jobs/{job_id}/candidates/{candidate_id}/resume-url — 60 s presigned view link (OQ8, behind a flag)."""

import os

import boto3

from rs_common import uploads
from rs_common.authz import Caller, load_job_for
from rs_common.http import HttpError, api_handler, path_id

_CANDIDATES = boto3.resource("dynamodb").Table(os.environ["CANDIDATES_TABLE"])


@api_handler
def lambda_handler(event, caller: Caller):
    if os.environ.get("FEATURE_RESUME_VIEW", "false").lower() != "true":
        raise HttpError(404, "NOT_FOUND", "Not found.")
    job_id = path_id(event, "job_id", "job")
    candidate_id = path_id(event, "candidate_id", "cand")
    load_job_for(caller, job_id)
    cand = _CANDIDATES.get_item(Key={"job_id": job_id, "candidate_id": candidate_id}).get("Item")
    if not cand:
        raise HttpError(404, "NOT_FOUND", "Candidate not found.")
    name = uploads.safe_download_name(cand.get("original_filename", "resume"))
    url = uploads.presign_get(cand["resume_s3_key"], uploads.RESUME_URL_TTL, f'inline; filename="{name}"')
    return 200, {"url": url, "expires_in": uploads.RESUME_URL_TTL}
