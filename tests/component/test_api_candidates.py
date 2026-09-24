"""Candidate-level API routes: list, decision + email, resume-url, export, failed-jobs,
and the cross-route authorization matrix (docs/03 §6, §10; DoD)."""

import json
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from conftest import (
    CANDIDATES_TABLE,
    FAILED_JOBS_TABLE,
    JOB_A,
    api_event,
    call,
    cid,
    put_candidate,
    put_job,
)
from moto.ses.models import ses_backends

BUCKET = "rs-test-bucket"


def sent_emails():
    return ses_backends["123456789012"]["ap-south-1"].sent_messages


def cand(aws, n=1):
    return aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(n)})["Item"]


def decide(handler, decision, n=1, sub="sub-a", groups="Recruiter", job=JOB_A):
    return call(
        handler("update_candidate_decision"),
        api_event(
            sub=sub, groups=groups, path={"job_id": job, "candidate_id": cid(n)}, body={"decision": decision}
        ),
    )


def scored(aws, n=1, score="80.0", **kw):
    fields = {
        "score_status": "scored",
        "match_score": Decimal(score),
        "skills_score": Decimal("66.7"),
        "title_score": Decimal("60.0"),
        "experience_score": Decimal("100.0"),
        "matched_skills": ["aws"],
        "missing_skills": ["dynamodb"],
        "title_match_type": "related",
        "title_match_held": "backend developer",
        "title_match_required": "backend engineer",
        "shortlist_candidate": True,
        "total_experience_years": Decimal("4.0"),
        "email": f"c{n}@example.com",
    }
    return put_candidate(aws.ddb, n, **{**fields, **kw})


@pytest.fixture(autouse=True)
def _clear_sent():
    sent_emails().clear()
    yield
    sent_emails().clear()


# ------------------------------------------------------- getCandidatesByJob
def test_lists_every_candidate_with_display_status_and_sort(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, "71.3")
    scored(aws, 2, "90.0")
    put_candidate(aws.ddb, 3, parse_status="parsed", score_status="pending")  # -> scoring
    put_candidate(
        aws.ddb, 4, parse_status="pending", upload_expires_at="2020-01-01T00:00:00Z"
    )  # upload_missing
    put_candidate(aws.ddb, 5, parse_status="pending", ingest_started_at="2099-01-01T00:00:00Z")  # processing
    put_candidate(aws.ddb, 6, parse_status="error", error_code="unreadable_document")
    put_candidate(aws.ddb, 7, parse_status="parsed", score_status="error")
    s, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    assert s == 200 and b["job_id"] == JOB_A
    rows = b["candidates"]
    assert [r["candidate_id"] for r in rows] == [
        cid(2),
        cid(1),
        cid(3),
        cid(5),
        cid(4),
        cid(6),
        cid(7),
    ]
    assert [r["display_status"] for r in rows] == [
        "scored",
        "scored",
        "scoring",
        "processing",
        "upload_missing",
        "error",
        "error",
    ]
    by_id = {r["candidate_id"]: r for r in rows}
    assert (
        by_id[cid(6)]["error_code"] == "unreadable_document"
        and by_id[cid(7)]["error_code"] == "scoring_failed"
    )
    assert rows[0]["match_score"] == 90.0 and rows[1]["match_score"] == 71.3


def test_candidate_shape_is_public_only_and_honest_about_unknowns(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    put_candidate(aws.ddb, 2, parse_status="parsed")  # unscored, no experience, no name
    aws.ddb.Table(CANDIDATES_TABLE).update_item(
        Key={"job_id": JOB_A, "candidate_id": cid(2)},
        UpdateExpression="REMOVE #n",
        ExpressionAttributeNames={"#n": "name"},
    )
    _, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    a, u = b["candidates"]
    assert a["title_match"] == {
        "type": "related",
        "held": "backend developer",
        "required": "backend engineer",
    }
    assert (
        a["recommended"] is True
        and a["experience_basis"] == "computed"
        and a["total_experience_years"] == 4.0
    )
    assert u["display_status"] == "scoring"
    assert u["total_experience_years"] is None and u["experience_basis"] == "unknown"  # never 0 (R-HON-09)
    assert (
        u["name"] is None
        and u["match_score"] is None
        and u["title_match"] is None
        and u["recommended"] is None
    )
    for r in (a, u):
        assert not {"resume_s3_key", "ingest_started_at", "upload_expires_at", "job_id", "decided_by"} & set(
            r
        )


def test_estimated_experience_basis(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, experience_estimated=True)
    _, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    assert b["candidates"][0]["experience_basis"] == "estimated"


def test_awaiting_states_follow_the_job(aws, handler):
    put_job(aws.ddb, parse_status="pending", jd_source="file")
    put_candidate(aws.ddb, 1, parse_status="parsed")
    _, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    assert b["candidates"][0]["display_status"] == "awaiting_jd"
    aws.ddb.Table("jobs-test").update_item(
        Key={"job_id": JOB_A},
        UpdateExpression="SET parse_status = :p REMOVE required_skills",
        ExpressionAttributeValues={":p": "parsed"},
    )
    _, b = call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))
    assert b["candidates"][0]["display_status"] == "awaiting_requirements"


def test_empty_job_lists_nothing(aws, handler):
    put_job(aws.ddb)
    assert call(handler("get_candidates_by_job"), api_event(path={"job_id": JOB_A}))[1]["candidates"] == []


# ------------------------------------------------------- decision + email
def test_decision_on_unscored_candidate_is_409(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, 1, parse_status="parsed", email="a@example.com")
    s, b = decide(handler, "shortlisted")
    assert (s, b["error"]["code"]) == (409, "NOT_SCORED")
    assert cand(aws)["decision"] == "pending" and sent_emails() == []


def test_shortlist_reject_shortlist_sends_exactly_one_email(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    s, b = decide(handler, "shortlisted")
    assert (s, b) == (200, {"candidate_id": cid(1), "decision": "shortlisted", "notification_status": "sent"})
    s, b = decide(handler, "rejected")
    assert b["notification_status"] == "sent" and cand(aws)["decision"] == "rejected"
    s, b = decide(handler, "shortlisted")
    assert (s, b["notification_status"]) == (200, "sent")
    assert len(sent_emails()) == 1  # R-BUS-07
    row = cand(aws)
    assert row["decision"] == "shortlisted" and row["decided_by"] == "sub-a" and row["notification_sent_at"]


def test_email_content_is_plain_text_from_verified_sender(aws, handler):
    put_job(aws.ddb, job_title="Backend Engineer")
    scored(aws, 1, name="Jane Doe")
    decide(handler, "shortlisted")
    (m,) = sent_emails()
    assert m.source == "sender@example.com" and m.destinations["ToAddresses"] == ["c1@example.com"]
    assert m.subject == "You've been shortlisted — Backend Engineer"
    assert m.body.startswith("Hi Jane Doe,")


def test_greeting_falls_back_and_sanitizes_hostile_name(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    aws.ddb.Table(CANDIDATES_TABLE).update_item(
        Key={"job_id": JOB_A, "candidate_id": cid(1)},
        UpdateExpression="REMOVE #n",
        ExpressionAttributeNames={"#n": "name"},
    )
    decide(handler, "shortlisted")
    assert sent_emails()[0].body.startswith("Hello,")
    sent_emails().clear()
    scored(aws, 2, name="Eve\r\nBcc: attacker@evil.com")
    decide(handler, "shortlisted", n=2)
    body = sent_emails()[0].body
    assert "\r" not in body.split("\n")[0] and body.startswith("Hi Eve Bcc: attacker@evil.com,")


def test_reject_and_pending_never_email(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    assert decide(handler, "rejected")[1]["notification_status"] is None
    assert decide(handler, "pending")[1]["notification_status"] is None
    assert sent_emails() == [] and cand(aws)["decision"] == "pending"


def test_missing_email_is_skipped_not_failed(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    aws.ddb.Table(CANDIDATES_TABLE).update_item(
        Key={"job_id": JOB_A, "candidate_id": cid(1)}, UpdateExpression="REMOVE email"
    )
    s, b = decide(handler, "shortlisted")
    assert (s, b["notification_status"]) == (200, "skipped_no_email")
    assert (
        cand(aws)["decision"] == "shortlisted" and sent_emails() == []
    )  # decision still succeeded (R-BUS-08)


def test_invalid_stored_email_is_treated_as_missing(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, email="not an email")
    assert decide(handler, "shortlisted")[1]["notification_status"] == "skipped_no_email"


def test_ses_failure_records_failed_keeps_decision_and_retry_can_succeed(aws, handler, monkeypatch):
    put_job(aws.ddb)
    scored(aws, 1)
    d = __import__("rs_common.decisions", fromlist=["x"])
    real = d._sesv2()

    class Failing:
        def send_email(self, **kw):
            raise ClientError(
                {
                    "Error": {
                        "Code": "MessageRejected",
                        "Message": "Email address c1@example.com not verified",
                    }
                },
                "SendEmail",
            )

    monkeypatch.setattr(d, "_sesv2", lambda: Failing())
    s, b = decide(handler, "shortlisted")
    assert (s, b["notification_status"]) == (200, "failed")  # R-BUS-08: never fails the decision
    assert cand(aws)["decision"] == "shortlisted" and sent_emails() == []
    (f,) = aws.ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert f["stage"] == "api" and f["candidate_id"] == cid(1)
    assert "c1@example.com" not in json.dumps(f, default=str)  # R-PRIV-02: no address in the audit row
    # Re-shortlisting a `failed` candidate retries the send.
    monkeypatch.setattr(d, "_sesv2", lambda: real)
    decide(handler, "rejected")
    s, b = decide(handler, "shortlisted")
    assert b["notification_status"] == "sent" and len(sent_emails()) == 1


def test_sending_claim_blocks_duplicates_after_a_crash(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, notification_status="sending")  # a previous invocation died mid-send
    s, b = decide(handler, "shortlisted")
    assert (s, b["notification_status"]) == (200, "sending") and sent_emails() == []


def test_already_sent_or_skipped_is_final(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, notification_status="sent")
    assert decide(handler, "shortlisted")[1]["notification_status"] == "sent" and sent_emails() == []


def test_decision_validation_and_lookup_errors(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    h = handler("update_candidate_decision")

    def ev(body, n=1):
        return api_event(path={"job_id": JOB_A, "candidate_id": cid(n)}, body=body)

    assert call(h, ev({"decision": "maybe"}))[0] == 400
    assert call(h, ev({"decision": "pending", "extra": 1}))[0] == 400
    assert call(h, ev({"decision": "pending"}, n=99))[0] == 404  # candidate doesn't exist
    assert (
        call(h, api_event(path={"job_id": JOB_A, "candidate_id": "bad"}, body={"decision": "pending"}))[0]
        == 404
    )


# ------------------------------------------------------- resume-url
def test_resume_url_is_short_lived_inline_and_key_matches(aws, handler):
    put_job(aws.ddb)
    put_candidate(aws.ddb, 1, original_filename='Jane "Doe" CV; rm -rf.pdf')
    s, b = call(handler("get_resume_url"), api_event(path={"job_id": JOB_A, "candidate_id": cid(1)}))
    assert s == 200 and b["expires_in"] == 60
    url = b["url"]
    assert f"resume-uploads/{JOB_A}/{cid(1)}/resume.pdf" in url and "X-Amz-Expires=60" in url
    from urllib.parse import parse_qs, urlparse

    disposition = parse_qs(urlparse(url).query)["response-content-disposition"][0]
    # Quotes/semicolons/spaces from the hostile filename cannot inject header syntax.
    assert disposition == 'inline; filename="Jane_Doe_CV_rm_-rf.pdf"'


def test_resume_url_flag_off_and_missing_candidate(aws, handler, monkeypatch):
    put_job(aws.ddb)
    put_candidate(aws.ddb, 1)
    h = handler("get_resume_url")
    assert call(h, api_event(path={"job_id": JOB_A, "candidate_id": cid(9)}))[0] == 404
    monkeypatch.setenv("FEATURE_RESUME_VIEW", "false")
    assert call(h, api_event(path={"job_id": JOB_A, "candidate_id": cid(1)}))[0] == 404


# ------------------------------------------------------- export
def test_export_contains_only_shortlisted_sorted_and_defused(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1, "71.3", decision="shortlisted", decided_at="2026-09-24T11:00:00Z", name="=HYPERLINK(evil)")
    scored(aws, 2, "90.0", decision="shortlisted", decided_at="2026-09-24T11:05:00Z", name="Zoë")
    scored(aws, 3, "99.0", decision="rejected")
    scored(aws, 4, "50.0", decision="pending")
    put_candidate(aws.ddb, 5, parse_status="parsed", decision="pending")
    s, b = call(handler("export_shortlist_csv"), api_event(path={"job_id": JOB_A}))
    assert s == 200 and b["row_count"] == 2
    assert "X-Amz-Expires=300" in b["download_url"] and "attachment" in b["download_url"]
    (obj,) = aws.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"exports/{JOB_A}/")["Contents"]
    assert obj["Key"].endswith("Z.csv")
    raw = aws.s3.get_object(Bucket=BUCKET, Key=obj["Key"])
    assert raw["ContentType"] == "text/csv; charset=utf-8"
    data = raw["Body"].read()
    assert data.startswith(b"\xef\xbb\xbf")
    lines = data.decode("utf-8-sig").strip().split("\r\n")
    assert lines[0] == "name,email,skills,titles_held,total_experience_years,match_score,decided_at"
    assert (
        len(lines) == 3
        and lines[1].startswith("Zoë,c2@example.com")
        and lines[2].startswith("'=HYPERLINK(evil),c1@example.com")
    )


def test_export_with_no_shortlisted_is_header_only(aws, handler):
    put_job(aws.ddb)
    scored(aws, 1)
    s, b = call(handler("export_shortlist_csv"), api_event(path={"job_id": JOB_A}))
    assert s == 200 and b["row_count"] == 0


# ------------------------------------------------------- failed-jobs
def seed_failures(aws):
    t = aws.ddb.Table(FAILED_JOBS_TABLE)
    t.put_item(
        Item={
            "job_id": JOB_A,
            "failure_id": "fail_2",
            "stage": "ocr",
            "terminal": False,
            "retry_count": 1,
            "error_message": "m",
            "created_at": "2026-09-24T10:00:00Z",
            "internal_extra": "hidden",
        }
    )
    t.put_item(
        Item={
            "job_id": JOB_A,
            "failure_id": "fail_1",
            "stage": "scoring_exhausted",
            "terminal": True,
            "retry_count": 5,
            "raw_payload": "{}",
            "created_at": "2026-09-24T11:00:00Z",
        }
    )
    t.put_item(
        Item={
            "job_id": "unknown",
            "failure_id": "fail_3",
            "stage": "orphan_object",
            "terminal": True,
            "created_at": "2026-09-24T09:00:00Z",
        }
    )


def test_failed_jobs_admin_only(aws, handler):
    seed_failures(aws)
    h = handler("get_failed_jobs")
    s, b = call(h, api_event(groups="Recruiter"))
    assert (s, b["error"]["code"]) == (403, "FORBIDDEN")
    s, b = call(h, api_event(groups="Admin"))
    assert s == 200 and b["next_token"] is None
    assert [f["failure_id"] for f in b["failures"]] == [
        "fail_1",
        "fail_2",
        "fail_3",
    ]  # by created_at desc, not failure_id
    assert "internal_extra" not in b["failures"][1]
    assert b["failures"][0]["raw_payload"] == "{}" and b["failures"][0]["terminal"] is True


def test_failed_jobs_filter_and_pagination(aws, handler, monkeypatch):
    seed_failures(aws)
    h = handler("get_failed_jobs")
    s, b = call(h, api_event(groups="Admin", query={"job_id": JOB_A}))
    assert {f["failure_id"] for f in b["failures"]} == {"fail_1", "fail_2"}
    assert call(h, api_event(groups="Admin", query={"job_id": "xx"}))[0] == 400
    monkeypatch.setattr(h, "PAGE", 2)
    _, first = call(h, api_event(groups="Admin"))
    assert len(first["failures"]) == 2 and first["next_token"]
    _, second = call(h, api_event(groups="Admin", query={"next_token": first["next_token"]}))
    assert len(second["failures"]) == 1
    assert call(h, api_event(groups="Admin", query={"next_token": "%%%"}))[0] == 400


# ------------------------------------------------------- authorization matrix (R-AUTH-01..05)
ROUTES = [
    ("create_job_posting", None, {"job_title": "x", "jd": {"source": "none"}, "required_skills": ["a"]}),
    ("add_resumes", "job", {"resume_filenames": ["a.pdf"]}),
    ("get_jobs", None, None),
    ("get_job", "job", None),
    ("update_job", "job", {"shortlist_threshold": 50}),
    ("get_candidates_by_job", "job", None),
    ("update_candidate_decision", "cand", {"decision": "rejected"}),
    ("get_resume_url", "cand", None),
    ("export_shortlist_csv", "job", None),
    ("get_failed_jobs", None, None),
]


def route_event(kind, body, **kw):
    path = None
    if kind == "job":
        path = {"job_id": JOB_A}
    elif kind == "cand":
        path = {"job_id": JOB_A, "candidate_id": cid(1)}
    return api_event(path=path, body=body, **kw)


@pytest.mark.parametrize("name,kind,body", ROUTES)
def test_groupless_user_is_403_on_every_route(aws, handler, name, kind, body):
    put_job(aws.ddb)
    scored(aws, 1)
    for groups in (None, "", "[]", "Viewer"):
        s, b = call(handler(name), route_event(kind, body, groups=groups))
        assert (s, b["error"]["code"]) == (403, "FORBIDDEN")


@pytest.mark.parametrize("name,kind,body", [r for r in ROUTES if r[1]])
def test_other_recruiter_gets_404_on_every_job_scoped_route_and_nothing_changes(
    aws, handler, name, kind, body
):
    put_job(aws.ddb)
    scored(aws, 1)
    before_job = aws.ddb.Table("jobs-test").scan()["Items"]
    before_cands = aws.ddb.Table(CANDIDATES_TABLE).scan()["Items"]
    s, b = call(handler(name), route_event(kind, body, sub="sub-b"))
    assert (s, b["error"]["code"]) == (404, "NOT_FOUND")
    assert aws.ddb.Table("jobs-test").scan()["Items"] == before_job
    assert aws.ddb.Table(CANDIDATES_TABLE).scan()["Items"] == before_cands
    assert sent_emails() == []


@pytest.mark.parametrize("name,kind,body", [r for r in ROUTES if r[1] and r[0] != "get_failed_jobs"])
def test_admin_can_reach_any_job(aws, handler, name, kind, body):
    put_job(aws.ddb)
    scored(aws, 1)
    s, _ = call(handler(name), route_event(kind, body, sub="admin-sub", groups="[Admin]"))
    assert s in (200, 201)


def test_recruiter_cannot_use_a_candidate_id_from_another_job(aws, handler):
    put_job(aws.ddb, JOB_A, "sub-a")
    put_job(aws.ddb, "job_" + "b" * 32, "sub-b")
    put_candidate(aws.ddb, 1, job_id="job_" + "b" * 32, score_status="scored")
    # sub-a owns JOB_A but asks for a candidate that lives under sub-b's job: not found under JOB_A (R-AUTH-03).
    s, _ = decide(handler, "rejected")
    assert s == 404
