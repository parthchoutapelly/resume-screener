"""Job-level API routes: create, add resumes, list, get, patch (docs/03 §6)."""

import json
from decimal import Decimal

from conftest import (
    CANDIDATES_TABLE,
    FAILED_JOBS_TABLE,
    JOB_A,
    JOB_B,
    JOBS_TABLE,
    api_event,
    call,
    cid,
    put_candidate,
    put_job,
)

BUCKET = "rs-test-bucket"


def create(aws, handler, body, **ev):
    return call(handler("create_job_posting"), api_event(body=body, **ev))


def candidates(aws, job_id):
    from boto3.dynamodb.conditions import Key

    return aws.ddb.Table(CANDIDATES_TABLE).query(KeyConditionExpression=Key("job_id").eq(job_id))["Items"]


def queue_messages(aws):
    out = []
    while True:
        r = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=10)
        if not r.get("Messages"):
            return out
        out += [json.loads(m["Body"]) for m in r["Messages"]]
        for m in r["Messages"]:
            aws.sqs.delete_message(QueueUrl=aws.queue_url, ReceiptHandle=m["ReceiptHandle"])


# ---------------------------------------------------------------- createJobPosting
def test_create_with_file_jd_and_resumes(aws, handler):
    status, body = create(
        aws,
        handler,
        {
            "job_title": "  Backend   Engineer ",
            "jd": {"source": "file", "filename": "jd.pdf"},
            "required_skills": ["Python", "AWS"],
            "resume_filenames": ["a.pdf", "b.DOCX", "../../evil name.png"],
        },
    )
    assert status == 201
    job_id = body["job_id"]
    assert job_id.startswith("job_") and len(job_id) == 36

    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": job_id})["Item"]
    assert job["job_title"] == "Backend Engineer"
    assert (job["recruiter_id"], job["jd_source"], job["parse_status"]) == ("sub-a", "file", "pending")
    assert job["requirements_confirmed"] is False and job["shortlist_threshold"] == 70
    assert job["required_skills"] == ["aws", "python"]
    assert "min_experience_years" not in job and "required_titles" not in job  # only when supplied
    assert job["jd_s3_key"] == f"jd-uploads/{job_id}/jd.pdf"

    assert body["jd_upload"]["fields"]["key"] == f"jd-uploads/{job_id}/jd.pdf"
    assert body["jd_upload"]["expires_at"].endswith("Z")
    assert len(body["resumes"]) == 3
    rows = {c["candidate_id"]: c for c in candidates(aws, job_id)}
    for r in body["resumes"]:
        row = rows[r["candidate_id"]]
        # Server-chosen key: the user's filename never appears in it (R-SEC-04).
        assert (
            row["resume_s3_key"]
            == f"resume-uploads/{job_id}/{r['candidate_id']}/resume.{row['original_filename'].rsplit('.', 1)[-1].lower()}"
        )
        assert "evil" not in row["resume_s3_key"] and ".." not in row["resume_s3_key"]
        assert r["upload"]["fields"]["key"] == row["resume_s3_key"]
        assert (row["parse_status"], row["score_status"], row["decision"]) == (
            "pending",
            "pending",
            "pending",
        )
        assert row["upload_expires_at"].endswith("Z")


def test_presigned_post_policy_pins_key_size_and_type(aws, handler):
    import base64

    _, body = create(
        aws,
        handler,
        {
            "job_title": "x",
            "jd": {"source": "none"},
            "required_skills": ["python"],
            "resume_filenames": ["a.pdf"],
        },
    )
    up = body["resumes"][0]["upload"]
    policy = json.loads(base64.b64decode(up["fields"]["policy"]))
    conds = policy["conditions"]
    assert ["content-length-range", 1, 10485760] in conds
    assert {"Content-Type": "application/pdf"} in conds
    assert {"key": up["fields"]["key"]} in conds
    assert up["url"].startswith("https://") and "s3" in up["url"]


def test_create_text_jd_writes_object_after_placeholders_exist(aws, handler, monkeypatch):
    up = __import__("rs_common.uploads", fromlist=["x"])
    seen = {}
    real = up.s3()

    class Spy:
        def __getattr__(self, name):
            return getattr(real, name)

        def put_object(self, **kw):
            seen["placeholders_at_put"] = len(candidates(aws, seen["job_id"]))
            seen["job_at_put"] = "Item" in aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": seen["job_id"]})
            return real.put_object(**kw)

    orig_new = up.new_placeholder

    def track(job_id, *a, **k):
        seen["job_id"] = job_id
        return orig_new(job_id, *a, **k)

    monkeypatch.setattr(up, "s3", lambda: Spy())
    monkeypatch.setattr(up, "new_placeholder", track)
    status, body = create(
        aws,
        handler,
        {
            "job_title": "Dev",
            "jd": {"source": "text", "text": "Need Python and AWS"},
            "resume_filenames": ["a.pdf", "b.pdf"],
        },
    )
    assert status == 201 and body["jd_upload"] is None
    assert seen["job_at_put"] and seen["placeholders_at_put"] == 2  # ordering guarantee
    obj = aws.s3.get_object(Bucket=BUCKET, Key=f"jd-uploads/{body['job_id']}/jd.txt")
    assert obj["Body"].read() == b"Need Python and AWS"
    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": body["job_id"]})["Item"]
    assert job["jd_source"] == "text" and job["parse_status"] == "pending"


def test_text_jd_s3_failure_marks_job_error_and_returns_500(aws, handler, monkeypatch):
    up = __import__("rs_common.uploads", fromlist=["x"])

    class Broken:
        def put_object(self, **kw):
            raise RuntimeError("s3 down")

    monkeypatch.setattr(up, "s3", lambda: Broken())
    status, body = create(aws, handler, {"job_title": "Dev", "jd": {"source": "text", "text": "hello"}})
    assert status == 500 and body["error"]["code"] == "INTERNAL" and "s3 down" not in json.dumps(body)
    (job,) = aws.ddb.Table(JOBS_TABLE).scan()["Items"]
    assert job["parse_status"] == "error" and job["error_code"] == "processing_failed"
    assert aws.ddb.Table(FAILED_JOBS_TABLE).scan()["Items"][0]["stage"] == "api"


def test_create_none_jd_is_immediately_scorable_with_explicit_skills(aws, handler):
    status, body = create(
        aws, handler, {"job_title": "x", "jd": {"source": "none"}, "required_skills": ["python"]}
    )
    assert status == 201 and body["jd_upload"] is None
    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": body["job_id"]})["Item"]
    assert job["parse_status"] == "not_applicable"
    _, view = call(handler("get_job"), api_event(path={"job_id": body["job_id"]}))
    assert view["scorable"] is True and view["blocking_reason"] is None


def test_create_error_envelopes(aws, handler):
    s, b = create(aws, handler, {"job_title": "x", "jd": {"source": "none"}})
    assert (s, b["error"]["code"]) == (400, "REQUIREMENTS_REQUIRED")
    s, b = create(
        aws, handler, {"job_title": "x", "jd": {"source": "none"}, "required_skills": ["a"], "bogus": 1}
    )
    assert (s, b["error"]["code"]) == (400, "VALIDATION_FAILED")
    assert {"field": "bogus", "issue": "unknown_field"} in b["error"]["details"]
    s, b = create(
        aws,
        handler,
        {
            "job_title": "x",
            "jd": {"source": "none"},
            "required_skills": ["a"],
            "resume_filenames": ["a.pdf"] * 51,
        },
    )
    assert (s, b["error"]["code"]) == (400, "LIMIT_EXCEEDED")
    s, b = call(handler("create_job_posting"), {**api_event(), "body": "{not json"})
    assert s == 400
    assert aws.ddb.Table(JOBS_TABLE).scan()["Items"] == []  # nothing written on validation failure


def test_create_explicit_numbers_stored_as_decimal(aws, handler):
    _, body = create(
        aws,
        handler,
        {
            "job_title": "x",
            "jd": {"source": "none"},
            "required_skills": ["a"],
            "min_experience_years": 2.5,
            "shortlist_threshold": 65,
        },
    )
    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": body["job_id"]})["Item"]
    assert job["min_experience_years"] == Decimal("2.5") and job["shortlist_threshold"] == 65


# ---------------------------------------------------------------- addResumes
def test_add_resumes_happy_and_ownership(aws, handler):
    put_job(aws.ddb)
    h = handler("add_resumes")
    s, b = call(h, api_event(path={"job_id": JOB_A}, body={"resume_filenames": ["x.pdf", "y.png"]}))
    assert s == 201 and len(b["resumes"]) == 2
    assert len(candidates(aws, JOB_A)) == 2
    s, b = call(h, api_event(sub="sub-b", path={"job_id": JOB_A}, body={"resume_filenames": ["x.pdf"]}))
    assert (s, b["error"]["code"]) == (404, "NOT_FOUND")
    assert len(candidates(aws, JOB_A)) == 2
    s, _ = call(
        h,
        api_event(sub="sub-b", groups="Admin", path={"job_id": JOB_A}, body={"resume_filenames": ["z.pdf"]}),
    )
    assert s == 201  # Admin may add to any job


def test_add_resumes_enforces_200_per_job(aws, handler):
    put_job(aws.ddb)
    with aws.ddb.Table(CANDIDATES_TABLE).batch_writer() as bw:
        for i in range(199):
            bw.put_item(Item={"job_id": JOB_A, "candidate_id": cid(i), "parse_status": "pending"})
    h = handler("add_resumes")
    s, b = call(h, api_event(path={"job_id": JOB_A}, body={"resume_filenames": ["a.pdf", "b.pdf"]}))
    assert (s, b["error"]["code"]) == (400, "LIMIT_EXCEEDED")
    assert len(candidates(aws, JOB_A)) == 199
    s, _ = call(h, api_event(path={"job_id": JOB_A}, body={"resume_filenames": ["a.pdf"]}))
    assert s == 201


# ---------------------------------------------------------------- getJobs
def test_get_jobs_scoped_sorted_and_admin_view(aws, handler):
    put_job(aws.ddb, JOB_A, "sub-a", created_at="2026-09-24T10:00:00Z")
    put_job(aws.ddb, "job_" + "1" * 32, "sub-a", created_at="2026-09-25T10:00:00Z")
    put_job(aws.ddb, JOB_B, "sub-b", created_at="2026-09-26T10:00:00Z")
    h = handler("get_jobs")
    s, b = call(h, api_event(sub="sub-a"))
    assert s == 200 and b["next_token"] is None
    assert [j["job_id"] for j in b["jobs"]] == ["job_" + "1" * 32, JOB_A]  # newest first, own only
    assert set(b["jobs"][0]) == {
        "job_id",
        "job_title",
        "jd_source",
        "parse_status",
        "scorable",
        "blocking_reason",
        "created_at",
    }
    s, b = call(h, api_event(sub="sub-z", groups="Admin"))
    assert [j["job_id"] for j in b["jobs"]][0] == JOB_B and len(b["jobs"]) == 3
    assert {j["recruiter_id"] for j in b["jobs"]} == {"sub-a", "sub-b"}


def test_get_jobs_pagination_and_token_hardening(aws, handler, monkeypatch):
    h = handler("get_jobs")
    monkeypatch.setattr(h, "PAGE", 2)
    for i in range(5):
        put_job(aws.ddb, "job_" + f"{i:032x}", "sub-a", created_at=f"2026-09-2{i}T10:00:00Z")
    seen, token = [], None
    for _ in range(5):
        s, b = call(h, api_event(sub="sub-a", query={"next_token": token} if token else None))
        assert s == 200
        seen += [j["job_id"] for j in b["jobs"]]
        token = b["next_token"]
        if not token:
            break
    assert len(seen) == 5 and len(set(seen)) == 5
    s, b = call(h, api_event(sub="sub-a", query={"next_token": "garbage!!"}))
    assert (s, b["error"]["code"]) == (400, "VALIDATION_FAILED")
    # A token minted for recruiter A must not be replayable by recruiter B.
    s, b = call(h, api_event(sub="sub-a", query=None))
    _, first = call(h, api_event(sub="sub-a"))
    assert first["next_token"]
    s, b = call(h, api_event(sub="sub-b", query={"next_token": first["next_token"]}))
    assert s == 400


def test_get_jobs_row_shows_blocking_reason(aws, handler):
    put_job(aws.ddb, parse_status="pending", jd_source="file")
    _, b = call(handler("get_jobs"), api_event())
    assert (b["jobs"][0]["scorable"], b["jobs"][0]["blocking_reason"]) == (False, "awaiting_jd")


# ---------------------------------------------------------------- getJob
def test_get_job_effective_sources_and_derived(aws, handler):
    put_job(
        aws.ddb,
        parse_status="parsed",
        jd_source="file",
        required_skills=["python"],
        derived_skills=["aws", "python", "sql"],
        derived_titles=["backend engineer"],
        derived_min_experience_years=Decimal("2"),
    )
    aws.ddb.Table(JOBS_TABLE).update_item(
        Key={"job_id": JOB_A}, UpdateExpression="REMOVE required_titles, min_experience_years"
    )
    s, b = call(handler("get_job"), api_event(path={"job_id": JOB_A}))
    assert s == 200
    assert b["effective"] == {
        "skills": ["python"],
        "titles": ["backend engineer"],
        "min_experience_years": 2.0,
    }
    assert b["sources"] == {"skills": "recruiter", "titles": "jd", "min_experience_years": "jd"}
    assert b["derived"] == {
        "skills": ["aws", "python", "sql"],
        "titles": ["backend engineer"],
        "min_experience_years": 2.0,
    }
    assert b["scorable"] is True and b["blocking_reason"] is None and b["requirements_confirmed"] is False
    assert "recruiter_id" not in b and "jd_s3_key" not in b


def test_get_job_404_for_missing_foreign_and_malformed(aws, handler):
    put_job(aws.ddb)
    h = handler("get_job")
    bodies = [
        call(h, api_event(sub="sub-b", path={"job_id": JOB_A})),  # not owned
        call(h, api_event(path={"job_id": JOB_B})),  # doesn't exist
        call(h, api_event(path={"job_id": "not-an-id"})),  # malformed
    ]
    assert [s for s, _ in bodies] == [404, 404, 404]
    assert (
        bodies[0][1]["error"]["message"] == bodies[1][1]["error"]["message"]
    )  # existence not revealed (R-AUTH-04)
    assert call(h, api_event(sub="x", groups="Admin", path={"job_id": JOB_A}))[0] == 200


# ---------------------------------------------------------------- updateJob
def test_patch_sets_fields_confirms_and_enqueues_rescore_for_parsed_only(aws, handler):
    put_job(aws.ddb, required_skills=["python"])
    put_candidate(
        aws.ddb,
        1,
        parse_status="parsed",
        score_status="scored",
        decision="shortlisted",
        notification_status="sent",
    )
    put_candidate(aws.ddb, 2, parse_status="parsed")
    put_candidate(aws.ddb, 3, parse_status="pending")
    put_candidate(aws.ddb, 4, parse_status="error")
    s, b = call(
        handler("update_job"),
        api_event(
            path={"job_id": JOB_A},
            body={
                "required_skills": ["Python", "AWS"],
                "required_titles": [],
                "min_experience_years": 5,
                "shortlist_threshold": 65,
            },
        ),
    )
    assert s == 200 and b["rescore_enqueued"] == 2
    assert b["requirements_confirmed"] is True
    assert b["effective"] == {"skills": ["aws", "python"], "titles": [], "min_experience_years": 5.0}
    assert b["shortlist_threshold"] == 65
    msgs = queue_messages(aws)
    assert {m["candidate_id"] for m in msgs} == {cid(1), cid(2)}
    assert all(m["reason"] == "requirements_changed" for m in msgs)
    # R-BUS-05: decisions and notification state are untouched by a requirements change.
    c1 = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(1)})["Item"]
    assert (c1["decision"], c1["notification_status"]) == ("shortlisted", "sent")


def test_patch_confirmation_makes_a_still_parsing_jd_scorable(aws, handler):
    put_job(aws.ddb, parse_status="pending", jd_source="file", required_skills=["python"])
    put_candidate(aws.ddb, 1)
    s, b = call(handler("update_job"), api_event(path={"job_id": JOB_A}, body={"shortlist_threshold": 50}))
    # requirements_confirmed=true makes a still-parsing JD scorable (recruiter override).
    assert s == 200 and b["scorable"] is True and b["rescore_enqueued"] == 1


def test_patch_rescues_a_job_whose_jd_failed_and_has_no_skills(aws, handler):
    put_job(aws.ddb, parse_status="error", jd_source="file", required_skills=[])
    aws.ddb.Table(JOBS_TABLE).update_item(Key={"job_id": JOB_A}, UpdateExpression="REMOVE required_skills")
    put_candidate(aws.ddb, 1)
    _, view = call(handler("get_job"), api_event(path={"job_id": JOB_A}))
    assert view["blocking_reason"] == "jd_failed"
    s, b = call(
        handler("update_job"), api_event(path={"job_id": JOB_A}, body={"required_skills": ["python"]})
    )
    assert s == 200 and b["scorable"] is True and b["blocking_reason"] is None and b["rescore_enqueued"] == 1


def test_patch_validation_and_authorization(aws, handler):
    put_job(aws.ddb)
    h = handler("update_job")
    for bad in (
        {},
        {"required_skills": []},
        {"job_title": "x"},
        {"min_experience_years": 99},
        {"shortlist_threshold": -5},
    ):
        s, b = call(h, api_event(path={"job_id": JOB_A}, body=bad))
        assert (s, b["error"]["code"]) == (400, "VALIDATION_FAILED"), bad
    assert call(h, api_event(sub="sub-b", path={"job_id": JOB_A}, body={"shortlist_threshold": 1}))[0] == 404
    job = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": JOB_A})["Item"]
    assert job["requirements_confirmed"] is False and job["shortlist_threshold"] == 70  # nothing changed
