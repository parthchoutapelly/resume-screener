"""Presigned S3 uploads/downloads and candidate placeholders (Architecture.md
§3.1, Rules R-SEC-03/04, D-21).

Object keys are always server-generated: the user's filename is stored only as
`original_filename` for display and never becomes part of a key or path.
"""

from __future__ import annotations

import os
import re
from functools import cache

import boto3
from botocore.config import Config

from rs_common import clock, ids

UPLOAD_TTL_SECONDS = 900  # R-SEC-03
MAX_UPLOAD_BYTES = 10_485_760
EXPORT_URL_TTL = 300
RESUME_URL_TTL = 60

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


@cache
def s3():
    # Regional virtual-host endpoint so presigned URLs match the CSP and the bucket CORS rules.
    region = os.environ.get("AWS_REGION") or os.environ["AWS_DEFAULT_REGION"]
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def bucket() -> str:
    return os.environ["UPLOAD_BUCKET"]


def jd_key(job_id: str, ext: str) -> str:
    return f"jd-uploads/{job_id}/jd.{ext}"


def resume_key(job_id: str, candidate_id: str, ext: str) -> str:
    return f"resume-uploads/{job_id}/{candidate_id}/resume.{ext}"


def presign_post(key: str, ext: str) -> dict:
    ctype = CONTENT_TYPES[ext]
    post = s3().generate_presigned_post(
        Bucket=bucket(),
        Key=key,
        Fields={"Content-Type": ctype},
        Conditions=[{"Content-Type": ctype}, ["content-length-range", 1, MAX_UPLOAD_BYTES]],
        ExpiresIn=UPLOAD_TTL_SECONDS,
    )
    return {
        "url": post["url"],
        "fields": post["fields"],
        "expires_at": clock.iso_in_seconds(UPLOAD_TTL_SECONDS),
    }


def safe_download_name(name: str) -> str:
    """Filename for Content-Disposition: ASCII letters/digits/._- only, so a
    hostile original filename can't inject header syntax."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "resume"
    return cleaned[:100]


def presign_get(key: str, ttl: int, disposition: str) -> str:
    return s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket(), "Key": key, "ResponseContentDisposition": disposition},
        ExpiresIn=ttl,
    )


def new_placeholder(job_id: str, filename: str, ext: str, now: str, expires_at: str) -> dict:
    """The candidate row that exists BEFORE any upload credential does, so
    extraction can never race ahead and classify the object as an orphan."""
    cid = ids.candidate_id()
    return {
        "job_id": job_id,
        "candidate_id": cid,
        "original_filename": filename,
        "resume_s3_key": resume_key(job_id, cid, ext),
        "upload_expires_at": expires_at,
        "parse_status": "pending",
        "score_status": "pending",
        "decision": "pending",
        "created_at": now,
        "updated_at": now,
    }
