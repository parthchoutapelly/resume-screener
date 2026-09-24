"""dlqHandler: ARN routing, terminal states, no regression, idempotent, EMF metric (docs/03 §7, R-ERR-07)."""

import json
from urllib.parse import quote_plus

from conftest import (
    CANDIDATES_TABLE,
    FAILED_JOBS_TABLE,
    JOB_A,
    JOBS_TABLE,
    cid,
    put_candidate,
    put_job,
)

INGESTION_ARN = "arn:aws:sqs:ap-south-1:123456789012:ingest-dlq-test"
SCORING_ARN = "arn:aws:sqs:ap-south-1:123456789012:scoring-dlq-test"


def s3_event(key):
    return json.dumps({"Records": [{"s3": {"object": {"key": quote_plus(key)}}}]})


def sqs(body, arn):
    return {"Records": [{"eventSourceARN": arn, "body": body}]}


def rows(aws):
    return aws.ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]


def cand(aws, n=1):
    return aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(n)})["Item"]


def resume_key(n=1):
    return f"resume-uploads/{JOB_A}/{cid(n)}/resume.pdf"


def test_ingestion_exhausted_resume_becomes_processing_failed(aws, handler, capsys):
    put_job(aws.ddb)
    put_candidate(aws.ddb, parse_status="pending")
    handler("dlq_handler").lambda_handler(sqs(s3_event(resume_key()), INGESTION_ARN), None)
    c = cand(aws)
    assert c["parse_status"] == "error" and c["error_code"] == "processing_failed"
    (f,) = rows(aws)
    assert f["stage"] == "ingestion_exhausted" and f["terminal"] is True and f["retry_count"] == 3
    assert f["candidate_id"] == cid(1) and "resume.pdf" in f["raw_payload"]
    emf = json.loads([ln for ln in capsys.readouterr().out.splitlines() if "_aws" in ln][0])
    assert emf["Queue"] == "ingestion" and emf["TerminalFailures"] == 1
    assert emf["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "ResumeScreener"


def test_ingestion_exhausted_jd_marks_the_job(aws, handler):
    put_job(aws.ddb, parse_status="pending")
    handler("dlq_handler").lambda_handler(sqs(s3_event(f"jd-uploads/{JOB_A}/jd.pdf"), INGESTION_ARN), None)
    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": JOB_A})["Item"]
    assert job["parse_status"] == "error" and job["error_code"] == "processing_failed"
    (f,) = rows(aws)
    assert f["job_id"] == JOB_A and "candidate_id" not in f


def test_never_regresses_a_parsed_candidate_or_job(aws, handler):
    put_job(aws.ddb, parse_status="parsed")
    put_candidate(aws.ddb, parse_status="parsed")
    h = handler("dlq_handler")
    h.lambda_handler(sqs(s3_event(resume_key()), INGESTION_ARN), None)
    h.lambda_handler(sqs(s3_event(f"jd-uploads/{JOB_A}/jd.pdf"), INGESTION_ARN), None)
    assert cand(aws)["parse_status"] == "parsed" and "error_code" not in cand(aws)
    assert aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": JOB_A})["Item"]["parse_status"] == "parsed"
    assert len(rows(aws)) == 2  # the audit rows are still written


def test_unparseable_key_is_audited_under_unknown_and_touches_nothing(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, parse_status="pending")
    handler("dlq_handler").lambda_handler(sqs(s3_event("weird/key.pdf"), INGESTION_ARN), None)
    (f,) = rows(aws)
    assert f["job_id"] == "unknown" and f["stage"] == "ingestion_exhausted"
    assert cand(aws)["parse_status"] == "pending"


def test_s3_test_event_is_ignored(aws, handler):
    handler("dlq_handler").lambda_handler(sqs(json.dumps({"Event": "s3:TestEvent"}), INGESTION_ARN), None)
    assert rows(aws) == []


def test_key_with_url_encoding_is_decoded(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, parse_status="pending")
    body = json.dumps({"Records": [{"s3": {"object": {"key": resume_key().replace("/", "%2F")}}}]})
    handler("dlq_handler").lambda_handler(sqs(body, INGESTION_ARN), None)
    assert cand(aws)["parse_status"] == "error"


def test_scoring_exhausted_sets_score_status_not_parse_status(aws, handler, capsys):
    put_job(aws.ddb)
    put_candidate(aws.ddb)
    msg = json.dumps({"job_id": JOB_A, "candidate_id": cid(1), "reason": "candidate_parsed"})
    handler("dlq_handler").lambda_handler(sqs(msg, SCORING_ARN), None)
    c = cand(aws)
    assert c["score_status"] == "error" and c["error_code"] == "scoring_failed"
    assert c["parse_status"] == "parsed"  # D-17
    (f,) = rows(aws)
    assert f["stage"] == "scoring_exhausted" and f["retry_count"] == 5
    assert '"Queue": "scoring"' in capsys.readouterr().out


def test_scoring_exhausted_never_overwrites_scored(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, score_status="scored")
    msg = json.dumps({"job_id": JOB_A, "candidate_id": cid(1)})
    handler("dlq_handler").lambda_handler(sqs(msg, SCORING_ARN), None)
    assert cand(aws)["score_status"] == "scored"


def test_redelivery_is_safe_and_appends_audit_rows_only(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, parse_status="pending")
    h = handler("dlq_handler")
    ev = sqs(s3_event(resume_key()), INGESTION_ARN)
    h.lambda_handler(ev, None)
    h.lambda_handler(ev, None)
    assert cand(aws)["parse_status"] == "error"
    assert len(rows(aws)) == 2  # append-only audit log (R-DATA-08)


def test_missing_placeholder_does_not_create_an_item(aws, handler):
    put_job(aws.ddb)
    handler("dlq_handler").lambda_handler(sqs(s3_event(resume_key(7)), INGESTION_ARN), None)
    assert "Item" not in aws.ddb.Table(CANDIDATES_TABLE).get_item(
        Key={"job_id": JOB_A, "candidate_id": cid(7)}
    )
