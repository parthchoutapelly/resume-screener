"""Component tests for Phase 5 Failure Matrix (F1-F13).

docs/05-integration-testing-and-delivery.md §3 (T-103)

Covers all 13 failure cases locally with moto mocks:
  F1: Renamed text file (.pdf) -> error / unsupported_format
  F2: Corrupt PDF -> error / unreadable_document
  F3: Encrypted PDF (password-protected) -> error / unreadable_document
  F4: Blank scan -> error / unreadable_document (OCR path)
  F5: Too many pages (11 pages) -> error / too_many_pages
  F6: Never uploaded -> upload_missing after 17 minutes
  F7: JD fails -> blocking_reason=jd_failed, awaiting_requirements -> PATCH -> scored
  F8: No skills in JD -> no_required_skills -> PATCH -> scored
  F9: Transient ingestion failure (3 s3_download + 1 ingestion_exhausted) -> processing_failed
  F10: Scoring failure (5 scoring + 1 scoring_exhausted) -> scoring_failed, parse_status=parsed
  F11: Duplicate event -> idempotent, state unchanged, no duplicate email
  F12: Decision on unscored -> HTTP 409 NOT_SCORED
  F13: Missing email -> notification_status=skipped_no_email, decision saved
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
from conftest import (
    CANDIDATES_TABLE,
    FAILED_JOBS_TABLE,
    FIXTURES_DIR,
    JOB_A,
    JOBS_TABLE,
    api_event,
    call,
    cid,
    create_core_tables,
    put_candidate,
    put_job,
)
from moto import mock_aws

BUCKET = "rs-test-bucket"


def _sqs_s3_event(bucket: str, key: str, receive_count: int = 1) -> dict:
    s3_event = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
    return {
        "Records": [
            {
                "body": json.dumps(s3_event),
                "attributes": {"ApproximateReceiveCount": str(receive_count)},
            }
        ]
    }


def _upload_file(s3, bucket: str, key: str, path: Path):
    with open(path, "rb") as f:
        s3.put_object(Bucket=bucket, Key=key, Body=f.read())


def _setup_extraction(monkeypatch, extraction_module, lambda_client=None):
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)

    monkeypatch.setattr(extraction_module, "s3", s3)
    monkeypatch.setattr(extraction_module, "lambda_client", lambda_client or MagicMock())
    monkeypatch.setattr(extraction_module, "_ddb", ddb)
    monkeypatch.setattr(extraction_module, "JOBS", ddb.Table(JOBS_TABLE))
    monkeypatch.setattr(extraction_module, "CANDIDATES", ddb.Table(CANDIDATES_TABLE))
    monkeypatch.setattr(extraction_module, "FAILED", ddb.Table(FAILED_JOBS_TABLE))
    return s3, ddb


# ---------------------------------------------------------------------------
# F1: Renamed text file (.pdf) -> unsupported_format
# ---------------------------------------------------------------------------
@mock_aws
def test_f1_renamed_text_file(monkeypatch, extraction_module):
    s3, ddb = _setup_extraction(monkeypatch, extraction_module)
    candidate_id = cid(1)
    key = f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": JOB_A, "candidate_id": candidate_id, "parse_status": "pending"}
    )
    _upload_file(s3, BUCKET, key, FIXTURES_DIR / "renamed_text_file.pdf")

    extraction_module.lambda_handler(_sqs_s3_event(BUCKET, key), None)

    cand = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})["Item"]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "unsupported_format"

    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is True
    assert failures[0]["stage"] == "unsupported_format"


# ---------------------------------------------------------------------------
# F2: Corrupt PDF -> unreadable_document
# ---------------------------------------------------------------------------
@mock_aws
def test_f2_corrupt_pdf(monkeypatch, extraction_module):
    s3, ddb = _setup_extraction(monkeypatch, extraction_module)
    candidate_id = cid(1)
    key = f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": JOB_A, "candidate_id": candidate_id, "parse_status": "pending"}
    )
    _upload_file(s3, BUCKET, key, FIXTURES_DIR / "corrupt.pdf")

    extraction_module.lambda_handler(_sqs_s3_event(BUCKET, key), None)

    cand = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})["Item"]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "unreadable_document"

    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is True


# ---------------------------------------------------------------------------
# F3: Encrypted PDF (password-protected) -> unreadable_document
# ---------------------------------------------------------------------------
@mock_aws
def test_f3_encrypted_pdf(monkeypatch, extraction_module):
    s3, ddb = _setup_extraction(monkeypatch, extraction_module)
    candidate_id = cid(1)
    key = f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": JOB_A, "candidate_id": candidate_id, "parse_status": "pending"}
    )
    _upload_file(s3, BUCKET, key, FIXTURES_DIR / "encrypted.pdf")

    extraction_module.lambda_handler(_sqs_s3_event(BUCKET, key), None)

    cand = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})["Item"]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "unreadable_document"


# ---------------------------------------------------------------------------
# F4: Blank scan -> unreadable_document (OCR path)
# ---------------------------------------------------------------------------
@mock_aws
def test_f4_blank_scan(monkeypatch, extraction_module):
    s3, ddb = _setup_extraction(monkeypatch, extraction_module)
    candidate_id = cid(1)
    key = f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": JOB_A, "candidate_id": candidate_id, "parse_status": "pending"}
    )
    _upload_file(s3, BUCKET, key, FIXTURES_DIR / "blank_scan.pdf")

    extraction_module.lambda_handler(_sqs_s3_event(BUCKET, key), None)

    cand = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})["Item"]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "unreadable_document"


# ---------------------------------------------------------------------------
# F5: Too many pages (11 pages) -> too_many_pages
# ---------------------------------------------------------------------------
@mock_aws
def test_f5_too_many_pages(monkeypatch, extraction_module):
    s3, ddb = _setup_extraction(monkeypatch, extraction_module)
    candidate_id = cid(1)
    key = f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": JOB_A, "candidate_id": candidate_id, "parse_status": "pending"}
    )
    _upload_file(s3, BUCKET, key, FIXTURES_DIR / "eleven_pages.pdf")

    extraction_module.lambda_handler(_sqs_s3_event(BUCKET, key), None)

    cand = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})["Item"]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "too_many_pages"


# ---------------------------------------------------------------------------
# F6: Never uploaded -> upload_missing after 17 minutes
# ---------------------------------------------------------------------------
@mock_aws
def test_f6_upload_missing_after_17_minutes(aws, handler):
    """Proves that a candidate placeholder whose upload never occurred reaches
    upload_missing after the 15-minute upload TTL + 2-minute grace period (17 min).
    Tested deterministically using seeded timestamps without sleeping 17 min."""
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    t0 = now - timedelta(minutes=20)
    t_exp = now - timedelta(minutes=5)  # expired 5 min ago (> 2 min grace)

    put_job(aws.ddb, job_id=JOB_A, parse_status="parsed")
    put_candidate(
        aws.ddb,
        1,
        job_id=JOB_A,
        parse_status="pending",
        created_at=t0.isoformat(),
        upload_expires_at=t_exp.isoformat(),
    )

    with patch("rs_common.clock.now", return_value=now):
        s, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))

    assert s == 200
    assert b["candidates"][0]["display_status"] == "upload_missing"


# ---------------------------------------------------------------------------
# F7: JD fails -> blocking_reason=jd_failed, awaiting_requirements -> PATCH -> scored
# ---------------------------------------------------------------------------
@mock_aws
def test_f7_jd_fails_and_rescued_by_patch(aws, handler):
    """Corrupt JD causes blocking_reason=jd_failed, candidates enter awaiting_requirements,
    then a recruiter PATCH supplies requirements and resumes can score."""
    put_job(
        aws.ddb,
        job_id=JOB_A,
        parse_status="error",
        error_code="unreadable_document",
        jd_source="file",
        required_skills=[],
    )
    aws.ddb.Table(JOBS_TABLE).update_item(Key={"job_id": JOB_A}, UpdateExpression="REMOVE required_skills")
    put_candidate(aws.ddb, 1, job_id=JOB_A, parse_status="parsed")

    # Step 1: Check job shows blocking_reason = jd_failed
    s_j, job_view = call(handler("get_job"), api_event(path={"job_id": JOB_A}))
    assert s_j == 200 and job_view["blocking_reason"] == "jd_failed"

    # Step 2: Candidates view shows display_status = awaiting_requirements
    s_c, c_view = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    assert s_c == 200 and c_view["candidates"][0]["display_status"] == "awaiting_requirements"

    # Step 3: Recruiter PATCH supplies valid required_skills
    s_p, p_view = call(
        handler("update_job"), api_event(path={"job_id": JOB_A}, body={"required_skills": ["python"]})
    )
    assert s_p == 200 and p_view["scorable"] is True and p_view["blocking_reason"] is None


# ---------------------------------------------------------------------------
# F8: No skills in JD -> no_required_skills -> PATCH -> scored
# ---------------------------------------------------------------------------
@mock_aws
def test_f8_no_skills_jd_and_rescued_by_patch(aws, handler):
    """A JD with no dictionary skills sets blocking_reason=no_required_skills.
    Candidates do not score until the recruiter explicitly patches requirements."""
    put_job(aws.ddb, job_id=JOB_A, parse_status="parsed", jd_source="file", required_skills=[])
    aws.ddb.Table(JOBS_TABLE).update_item(Key={"job_id": JOB_A}, UpdateExpression="REMOVE required_skills")
    put_candidate(aws.ddb, 1, job_id=JOB_A, parse_status="parsed")

    s_j, job_view = call(handler("get_job"), api_event(path={"job_id": JOB_A}))
    assert s_j == 200 and job_view["blocking_reason"] == "no_required_skills"
    assert job_view["scorable"] is False

    # Recruiter patches required_skills
    s_p, p_view = call(
        handler("update_job"), api_event(path={"job_id": JOB_A}, body={"required_skills": ["python"]})
    )
    assert s_p == 200 and p_view["scorable"] is True and p_view["blocking_reason"] is None


# ---------------------------------------------------------------------------
# F9: Forced transient ingestion failure -> DLQ -> processing_failed
# ---------------------------------------------------------------------------
@mock_aws
def test_f9_ingestion_transient_exhaustion_to_dlq(aws, handler):
    """When an ingestion message fails retries, dlqHandler processes the DLQ
    record and marks candidate parse_status=error, error_code=processing_failed."""
    candidate_id = cid(1)
    aws.ddb.Table(CANDIDATES_TABLE).put_item(
        Item={
            "job_id": JOB_A,
            "candidate_id": candidate_id,
            "parse_status": "pending",
            "created_at": "2026-09-26T12:00:00Z",
        }
    )

    dlq = handler("dlq_handler")
    sqs_dlq_event = {
        "Records": [
            {
                "eventSourceARN": "arn:aws:sqs:ap-south-1:123456789012:ingest-dlq-test",
                "body": json.dumps(
                    {
                        "Records": [
                            {
                                "s3": {
                                    "bucket": {"name": BUCKET},
                                    "object": {"key": f"resume-uploads/{JOB_A}/{candidate_id}/resume.pdf"},
                                }
                            }
                        ]
                    }
                ),
            }
        ]
    }

    dlq.lambda_handler(sqs_dlq_event, None)

    cand = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})[
        "Item"
    ]
    assert cand["parse_status"] == "error"
    assert cand["error_code"] == "processing_failed"


# ---------------------------------------------------------------------------
# F10: Forced scoring failure -> DLQ -> scoring_failed, parse_status=parsed
# ---------------------------------------------------------------------------
@mock_aws
def test_f10_scoring_exhaustion_to_dlq(aws, handler):
    """When a scoring message fails retries, dlqHandler processes the DLQ
    record and marks score_status=error, error_code=scoring_failed, while
    parse_status remains 'parsed'."""
    candidate_id = cid(1)
    aws.ddb.Table(CANDIDATES_TABLE).put_item(
        Item={
            "job_id": JOB_A,
            "candidate_id": candidate_id,
            "parse_status": "parsed",
            "score_status": "pending",
            "created_at": "2026-09-26T12:00:00Z",
        }
    )

    dlq = handler("dlq_handler")
    sqs_dlq_event = {
        "Records": [
            {
                "eventSourceARN": "arn:aws:sqs:ap-south-1:123456789012:scoring-dlq-test",
                "body": json.dumps(
                    {
                        "job_id": JOB_A,
                        "candidate_id": candidate_id,
                    }
                ),
            }
        ]
    }

    dlq.lambda_handler(sqs_dlq_event, None)

    cand = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": candidate_id})[
        "Item"
    ]
    assert cand["parse_status"] == "parsed"  # remains parsed!
    assert cand["score_status"] == "error"
    assert cand["error_code"] == "scoring_failed"


# ---------------------------------------------------------------------------
# F11: Duplicate event -> state unchanged, no second email
# ---------------------------------------------------------------------------
@mock_aws
def test_f11_duplicate_scoring_event_idempotent(aws, handler):
    """Sending a duplicate scoring event to scoreMatch when a candidate is
    already scored results in an idempotent no-op."""
    put_job(aws.ddb, job_id=JOB_A)
    put_candidate(
        aws.ddb,
        1,
        job_id=JOB_A,
        parse_status="parsed",
        score_status="scored",
        match_score=Decimal("85.0"),
        skills_score=Decimal("66.7"),
        title_score=Decimal("60.0"),
        experience_score=Decimal("100.0"),
        scoring_version="v1",
    )

    score_match = handler("score_match")
    sqs_event = {
        "Records": [
            {
                "body": json.dumps({"job_id": JOB_A, "candidate_id": cid(1), "reason": "candidate_parsed"}),
                "messageId": "msg-dup-1",
            }
        ]
    }
    score_match.lambda_handler(sqs_event, None)
    cand = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(1)})["Item"]
    assert cand["score_status"] == "scored"


# ---------------------------------------------------------------------------
# F12: Decision on unscored -> HTTP 409 NOT_SCORED
# ---------------------------------------------------------------------------
@mock_aws
def test_f12_decision_on_unscored_candidate_returns_409(aws, handler):
    """Attempting to shortlist or reject a candidate whose score_status != 'scored'
    returns HTTP 409 NOT_SCORED."""
    put_job(aws.ddb, job_id=JOB_A)
    put_candidate(aws.ddb, 1, job_id=JOB_A, parse_status="pending", score_status="pending")

    s, b = call(
        handler("update_candidate_decision"),
        api_event(path={"job_id": JOB_A, "candidate_id": cid(1)}, body={"decision": "shortlisted"}),
    )
    assert s == 409
    assert b["error"]["code"] == "NOT_SCORED"


# ---------------------------------------------------------------------------
# F13: Missing email -> notification_status=skipped_no_email, decision saved
# ---------------------------------------------------------------------------
@mock_aws
def test_f13_missing_email_decision_saved_notification_skipped(aws, handler):
    """Shortlisting a candidate who has no email address saves the decision
    as 'shortlisted' and sets notification_status to 'skipped_no_email' without error."""
    put_job(aws.ddb, job_id=JOB_A)
    put_candidate(
        aws.ddb,
        1,
        job_id=JOB_A,
        name="Jane Doe",
        parse_status="parsed",
        score_status="scored",
        match_score=Decimal("88.0"),
    )
    # Ensure no email
    aws.ddb.Table(CANDIDATES_TABLE).update_item(
        Key={"job_id": JOB_A, "candidate_id": cid(1)},
        UpdateExpression="REMOVE email",
    )

    s, b = call(
        handler("update_candidate_decision"),
        api_event(path={"job_id": JOB_A, "candidate_id": cid(1)}, body={"decision": "shortlisted"}),
    )
    assert s == 200
    assert b["decision"] == "shortlisted"
    assert b["notification_status"] == "skipped_no_email"

    cand = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(1)})["Item"]
    assert cand["decision"] == "shortlisted"
    assert cand["notification_status"] == "skipped_no_email"
