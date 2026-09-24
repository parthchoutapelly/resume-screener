"""scoreMatch component tests (docs/03 §10): ack-when-not-ready, full write as
Decimal, conditional skip, audit-and-raise, and R-BUS-05 (decision untouched)."""

import json
from decimal import Decimal

import pytest
from conftest import CANDIDATES_TABLE, FAILED_JOBS_TABLE, JOB_A, cid, put_candidate, put_job


def sqs_event(cand_n=1, job_id=JOB_A, reason="candidate_parsed", receive_count="1"):
    return {
        "Records": [
            {
                "body": json.dumps({"job_id": job_id, "candidate_id": cid(cand_n), "reason": reason}),
                "attributes": {"ApproximateReceiveCount": receive_count},
            }
        ]
    }


def cand_row(aws, n=1):
    return aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(n)})["Item"]


def failures(aws):
    return aws.ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]


def test_candidate_not_parsed_is_acked_without_writes(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, parse_status="pending")
    handler("score_match").lambda_handler(sqs_event(), None)
    row = cand_row(aws)
    assert "match_score" not in row and row["score_status"] == "pending"
    assert failures(aws) == []


def test_missing_candidate_or_job_is_acked(aws, handler):
    h = handler("score_match")
    put_job(aws.ddb)
    h.lambda_handler(sqs_event(cand_n=9), None)  # no such candidate
    put_candidate(aws.ddb, n=2, job_id="job_" + "c" * 32)  # candidate whose job doesn't exist
    h.lambda_handler(sqs_event(cand_n=2, job_id="job_" + "c" * 32), None)
    assert failures(aws) == []


@pytest.mark.parametrize(
    "job_kw",
    [
        {"parse_status": "pending"},  # JD still parsing
        {"parse_status": "error"},  # JD failed, unconfirmed
        {"required_skills": [], "parse_status": "parsed"},  # no skills anywhere
    ],
)
def test_job_not_scorable_is_acked_and_writes_nothing(aws, handler, job_kw):
    put_job(aws.ddb, **job_kw)
    put_candidate(aws.ddb)
    handler("score_match").lambda_handler(sqs_event(), None)
    assert "match_score" not in cand_row(aws)
    assert failures(aws) == []  # R-ERR-04: "not ready" is never an audit row


def test_scorable_writes_every_field_as_decimal(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, total_experience_years=Decimal("4.0"))
    handler("score_match").lambda_handler(sqs_event(), None)
    row = cand_row(aws)
    assert row["match_score"] == Decimal("71.3")
    assert (row["skills_score"], row["title_score"], row["experience_score"]) == (
        Decimal("66.7"),
        Decimal("60.0"),
        Decimal("100.0"),
    )
    assert row["matched_skills"] == ["aws", "python"] and row["missing_skills"] == ["dynamodb"]
    assert (row["title_match_type"], row["title_match_held"], row["title_match_required"]) == (
        "related",
        "backend developer",
        "backend engineer",
    )
    assert row["shortlist_candidate"] is True
    assert row["score_status"] == "scored" and row["scoring_version"] == "v1" and row["scored_at"]
    assert isinstance(row["match_score"], Decimal)


def test_unknown_experience_scores_zero_and_never_writes_years(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb)  # no total_experience_years
    handler("score_match").lambda_handler(sqs_event(), None)
    row = cand_row(aws)
    assert row["experience_score"] == Decimal("0.0")
    assert "total_experience_years" not in row


def test_rescore_never_touches_decision_or_notification(aws, handler):
    put_job(aws.ddb)
    put_candidate(
        aws.ddb,
        score_status="scored",
        match_score=Decimal("10"),
        decision="shortlisted",
        decided_by="sub-a",
        notification_status="sent",
    )
    handler("score_match").lambda_handler(sqs_event(reason="requirements_changed"), None)
    row = cand_row(aws)
    assert row["match_score"] != Decimal("10")  # rescored
    assert (row["decision"], row["decided_by"], row["notification_status"]) == (
        "shortlisted",
        "sub-a",
        "sent",
    )


def test_rescore_removes_stale_title_explanation(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb)
    h = handler("score_match")
    h.lambda_handler(sqs_event(), None)
    assert "title_match_held" in cand_row(aws)
    # Recruiter now says "no title requirement": the earlier held/required pair must not linger.
    aws.ddb.Table("jobs-test").update_item(
        Key={"job_id": JOB_A},
        UpdateExpression="SET required_titles = :e",
        ExpressionAttributeValues={":e": []},
    )
    h.lambda_handler(sqs_event(reason="requirements_changed"), None)
    row = cand_row(aws)
    assert row["title_match_type"] == "not_required"
    assert "title_match_held" not in row and "title_match_required" not in row


def test_threshold_controls_recommended_flag(aws, handler):
    put_job(aws.ddb, shortlist_threshold=Decimal("90"))
    put_candidate(aws.ddb, total_experience_years=Decimal("4"))
    handler("score_match").lambda_handler(sqs_event(), None)
    assert cand_row(aws)["shortlist_candidate"] is False


def test_state_changed_midflight_is_a_conditional_skip(aws, handler, monkeypatch):
    put_job(aws.ddb)
    put_candidate(aws.ddb)
    h = handler("score_match")
    real = h.scoring.score

    def flip_then_score(c, j):
        aws.ddb.Table(CANDIDATES_TABLE).update_item(
            Key={"job_id": JOB_A, "candidate_id": cid(1)},
            UpdateExpression="SET parse_status = :e",
            ExpressionAttributeValues={":e": "error"},
        )
        return real(c, j)

    monkeypatch.setattr(h.scoring, "score", flip_then_score)
    h.lambda_handler(sqs_event(), None)  # must not raise
    row = cand_row(aws)
    assert "match_score" not in row and row["parse_status"] == "error"
    assert failures(aws) == []


def test_exception_is_audited_then_reraised_for_sqs_retry(aws, handler, monkeypatch):
    put_job(aws.ddb)
    put_candidate(aws.ddb)
    h = handler("score_match")

    def boom(c, j):
        raise RuntimeError("scoring blew up")

    monkeypatch.setattr(h.scoring, "score", boom)
    with pytest.raises(RuntimeError):
        h.lambda_handler(sqs_event(receive_count="3"), None)
    (f,) = failures(aws)
    assert f["stage"] == "scoring" and f["terminal"] is False and f["retry_count"] == 3
    assert f["job_id"] == JOB_A and f["candidate_id"] == cid(1) and f["error_type"] == "RuntimeError"
    assert "raw_payload" not in f
    assert cand_row(aws)["score_status"] == "pending"  # no status change until DLQ exhaustion


def test_duplicate_delivery_is_idempotent(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, total_experience_years=Decimal("4"))
    h = handler("score_match")
    h.lambda_handler(sqs_event(), None)
    first = cand_row(aws)
    h.lambda_handler(sqs_event(), None)
    second = cand_row(aws)
    for k in ("match_score", "skills_score", "matched_skills", "score_status"):
        assert first[k] == second[k]
