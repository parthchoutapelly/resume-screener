#!/usr/bin/env python3
"""Deployed integration test for phase 3 (docs/03-scoring-and-api.md §10 "Deployed" row
and the Definition of Done). Everything here goes through the REAL deployed stack:
API Gateway + Cognito authorizer, the real Lambdas, S3 presigned POSTs, the real
S3 -> SQS -> extraction -> NLP -> scoring pipeline, SES, and CloudWatch.

Test identities are the four synthetic Cognito users from infra/README.md step 4
(recruiter.a / recruiter.b / admin / noaccess @example.com). Passwords are random,
generated per run, applied with the admin API, and never stored anywhere.

Two things are seeded directly into DynamoDB and then processed by the REAL deployed
scoring Lambda (they cannot be produced deterministically by real NLP):
  - the documented worked example candidate (must score 71.3),
  - a candidate with a malformed attribute, to force a genuine scoring exception.
Emails are only ever sent to the SES mailbox simulator (success@simulator.amazonses.com),
so nothing reaches a real inbox.

Usage: python tests/integration/phase3_run.py [env]
"""

from __future__ import annotations

import io
import json
import secrets
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import boto3
import requests
from pycognito import Cognito

REGION = "ap-south-1"
REPO = Path(__file__).resolve().parents[2]
RESUMES = REPO / "tests" / "fixtures" / "resumes"
JDS = REPO / "tests" / "fixtures" / "jds"
SIM_OK = "success@simulator.amazonses.com"

RESULTS: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> bool:
    RESULTS.append((bool(cond), label))
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}" + (f"  -- {detail}" if detail and not cond else ""))
    return bool(cond)


def wait(fn, timeout=600, interval=8, what="condition"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    print(f"  [..] timed out waiting for {what}")
    return last


class Ctx:
    pass


def setup() -> Ctx:
    c = Ctx()
    env = sys.argv[1] if len(sys.argv) > 1 else "dev"
    c.env = env
    cf = boto3.client("cloudformation", region_name=REGION)
    out = {
        o["OutputKey"]: o["OutputValue"]
        for o in cf.describe_stacks(StackName=f"resume-screener-{env}")["Stacks"][0]["Outputs"]
    }
    c.out = out
    c.api = out["ApiBaseUrl"].rstrip("/")
    c.bucket = out["UploadBucketName"]
    c.origin = "http://localhost:5173"
    c.ddb = boto3.resource("dynamodb", region_name=REGION)
    c.jobs = c.ddb.Table(out["JobsTableName"])
    c.cands = c.ddb.Table(out["CandidatesTableName"])
    c.failed = c.ddb.Table(out["FailedJobsTableName"])
    c.sqs = boto3.client("sqs", region_name=REGION)
    idp = boto3.client("cognito-idp", region_name=REGION)
    c.tokens = {}
    for key, email in (
        ("A", "recruiter.a@example.com"),
        ("B", "recruiter.b@example.com"),
        ("admin", "admin@example.com"),
        ("none", "noaccess@example.com"),
    ):
        pw = secrets.token_urlsafe(18) + "aA1!"
        idp.admin_set_user_password(UserPoolId=out["UserPoolId"], Username=email, Password=pw, Permanent=True)
        u = Cognito(out["UserPoolId"], out["UserPoolClientId"], username=email, user_pool_region=REGION)
        u.authenticate(password=pw)
        c.tokens[key] = u.id_token
    c.started = time.time()
    return c


def req(c: Ctx, method, path, who=None, body=None, params=None, raw_token=None):
    headers = {"Content-Type": "application/json", "Origin": c.origin}
    tok = raw_token if raw_token is not None else (c.tokens[who] if who else None)
    if tok:
        headers["Authorization"] = tok  # raw ID token, no "Bearer " (D-47)
    r = requests.request(
        method,
        c.api + path,
        headers=headers,
        params=params,
        data=None if body is None else json.dumps(body),
        timeout=30,
    )
    try:
        j = r.json()
    except ValueError:
        j = {}
    return r.status_code, j, r.headers


def upload(up: dict, data: bytes, name="file") -> requests.Response:
    return requests.post(up["url"], data=up["fields"], files={"file": (name, io.BytesIO(data))}, timeout=60)


def candidates(c, who, job_id):
    s, b, _ = req(c, "GET", f"/jobs/{job_id}/candidates", who)
    return b.get("candidates", []) if s == 200 else []


def job_view(c, who, job_id):
    return req(c, "GET", f"/jobs/{job_id}", who)[1]


def seed_candidate(c: Ctx, job_id: str, **fields) -> str:
    cid = f"cand_{uuid.uuid4().hex}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    item = {
        "job_id": job_id,
        "candidate_id": cid,
        "original_filename": "seeded.pdf",
        "resume_s3_key": f"resume-uploads/{job_id}/{cid}/resume.pdf",
        "parse_status": "parsed",
        "score_status": "pending",
        "decision": "pending",
        "created_at": now,
        "updated_at": now,
        **fields,
    }
    c.cands.put_item(Item=item)
    return cid


def new_job(c, who, **body):
    s, b, _ = req(c, "POST", "/jobs", who, body)
    assert s == 201, (s, b)
    return b


def enqueue_score(c, job_id, cid):
    c.sqs.send_message(
        QueueUrl=c.out["ScoringQueueUrl"],
        MessageBody=json.dumps({"job_id": job_id, "candidate_id": cid, "reason": "candidate_parsed"}),
    )


# --------------------------------------------------------------------------------------
def s1_edge_auth(c):
    print("\n[S1] Edge: authentication, CORS, groupless access")
    s, b, h = req(c, "GET", "/jobs")
    check(s == 401, "no token -> 401", str(s))
    check(h.get("Access-Control-Allow-Origin") == c.origin, "401 carries the CORS header", str(dict(h)))
    s, b, h = req(c, "GET", "/jobs", raw_token="not.a.jwt")
    check(s == 401 and h.get("Access-Control-Allow-Origin") == c.origin, "bad token -> 401 with CORS header")
    r = requests.options(
        c.api + "/jobs",
        headers={
            "Origin": c.origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
        timeout=30,
    )
    check(
        r.status_code == 200 and r.headers.get("Access-Control-Allow-Origin") == c.origin,
        "preflight without a token -> 200 + CORS",
        f"{r.status_code} {dict(r.headers)}",
    )
    check(
        "GET" in r.headers.get("Access-Control-Allow-Methods", "")
        and "Authorization" in r.headers.get("Access-Control-Allow-Headers", ""),
        "preflight advertises methods and Authorization header",
    )
    r = requests.options(
        c.api + "/jobs",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        timeout=30,
    )
    check(
        r.headers.get("Access-Control-Allow-Origin") != "https://evil.example"
        and r.headers.get("Access-Control-Allow-Origin") != "*",
        "foreign origin is not allowed",
    )

    fake_job, fake_cand = "job_" + "0" * 32, "cand_" + "0" * 32
    routes = [
        ("POST", "/jobs", {"job_title": "x", "jd": {"source": "none"}, "required_skills": ["a"]}),
        ("GET", "/jobs", None),
        ("GET", f"/jobs/{fake_job}", None),
        ("PATCH", f"/jobs/{fake_job}", {"shortlist_threshold": 5}),
        ("POST", f"/jobs/{fake_job}/resumes", {"resume_filenames": ["a.pdf"]}),
        ("GET", f"/jobs/{fake_job}/candidates", None),
        ("POST", f"/jobs/{fake_job}/candidates/{fake_cand}/decision", {"decision": "rejected"}),
        ("GET", f"/jobs/{fake_job}/candidates/{fake_cand}/resume-url", None),
        ("GET", f"/jobs/{fake_job}/export", None),
        ("GET", "/failed-jobs", None),
    ]
    bad = [f"{m} {p}" for m, p, b in routes if req(c, m, p, "none", b)[0] != 403]
    check(not bad, f"groupless user -> 403 on all {len(routes)} routes", str(bad))
    s, b, h = req(c, "GET", "/jobs", "none")
    check(
        b.get("error", {}).get("code") == "FORBIDDEN" and h.get("Access-Control-Allow-Origin") == c.origin,
        "403 uses the error envelope and carries CORS",
    )
    check(req(c, "GET", "/failed-jobs", "A")[0] == 403, "Recruiter on /failed-jobs -> 403")


def s2_resumes_before_jd(c):
    print("\n[S2] Resumes uploaded BEFORE the JD (JD-after-resumes ordering, D-18)")
    good = ["worked_example_native.pdf", "alice_johnson_native.pdf", "bob_kumar.docx", "jordan_rivera.png"]
    bad = {"corrupt.pdf": "unreadable_document", "renamed_text_file.pdf": "unsupported_format"}
    body = new_job(
        c,
        "A",
        job_title="Backend Engineer (itest)",
        jd={"source": "file", "filename": "jd.pdf"},
        resume_filenames=good + list(bad),
        shortlist_threshold=60,
    )
    job_id = c.s2_job = body["job_id"]
    check(
        body["jd_upload"] is not None and len(body["resumes"]) == 6,
        "POST /jobs 201 with 1 JD upload + 6 resume uploads",
    )
    check(job_view(c, "A", job_id)["blocking_reason"] == "awaiting_jd", "job starts blocked as awaiting_jd")

    by_name = {r["filename"]: r for r in body["resumes"]}
    for name in good + list(bad):
        r = upload(by_name[name]["upload"], (RESUMES / name).read_bytes())
        assert r.status_code in (200, 201, 204), (name, r.status_code, r.text[:200])
    print("  uploaded 6 resumes; JD withheld")

    seen = set()

    def resumes_settled():
        rows = candidates(c, "A", job_id)
        seen.update(r["display_status"] for r in rows)
        st = {r["original_filename"]: r["display_status"] for r in rows}
        return (
            all(st.get(n) == "awaiting_jd" for n in good) and all(st.get(n) == "error" for n in bad) and rows
        )

    rows = wait(resumes_settled, 600, 8, "resumes to parse and wait for the JD")
    check(bool(rows), "good resumes reach awaiting_jd, bad ones reach error (no JD yet)")
    check(
        "awaiting_jd" in seen and ("processing" in seen or "awaiting_jd" in seen),
        f"statuses observed while waiting: {sorted(seen)}",
    )
    if rows:
        codes = {r["original_filename"]: r["error_code"] for r in rows if r["display_status"] == "error"}
        check(codes == bad, "error rows carry the exact public error_code", str(codes))
        check(all(r["match_score"] is None for r in rows), "nothing is scored while the JD is missing")
    check(
        not [
            f
            for f in req(c, "GET", "/failed-jobs", "admin", params={"job_id": job_id})[1].get("failures", [])
            if f["stage"].startswith("scoring")
        ],
        "no scoring failure rows while waiting",
    )

    r = upload(body["jd_upload"], (JDS / "backend_engineer_jd.pdf").read_bytes())
    check(r.status_code in (200, 201, 204), "JD upload accepted", f"{r.status_code} {r.text[:120]}")

    def all_scored():
        rows = candidates(c, "A", job_id)
        return (
            rows
            if rows
            and all(r["display_status"] == "scored" for r in rows if r["original_filename"] in good)
            and all(r["display_status"] == "error" for r in rows if r["original_filename"] in bad)
            else None
        )

    rows = wait(all_scored, 600, 8, "all resumes to be scored after the JD parsed")
    check(bool(rows), "after the JD parses, every good resume is scored automatically")
    if rows:
        c.s2_rows = rows
        scored = [r for r in rows if r["display_status"] == "scored"]
        check(
            [r["match_score"] for r in scored] == sorted((r["match_score"] for r in scored), reverse=True),
            "scored rows sorted by match_score desc",
        )
        check(
            [r["display_status"] for r in rows] == ["scored"] * 4 + ["error"] * 2,
            "listing returns EVERY candidate, scored first, errors last",
        )
        check(
            all(
                r["matched_skills"] is not None and r["title_match"] and "type" in r["title_match"]
                for r in scored
            ),
            "each score ships its explanation (matched/missing/title match)",
        )
        check(all(0 <= r["match_score"] <= 100 for r in scored), "scores within 0..100")
        check(
            not ({"resume_s3_key", "ingest_started_at", "upload_expires_at"} & set(rows[0])),
            "internal fields are not exposed",
        )
        print("   scores:", {r["name"]: r["match_score"] for r in scored})
    jv = job_view(c, "A", job_id)
    check(
        jv["scorable"] and jv["derived"]["skills"] and jv["sources"]["skills"] == "jd",
        "job now scorable with JD-derived skills",
        str(jv["derived"]),
    )
    fails = req(c, "GET", "/failed-jobs", "admin", params={"job_id": job_id})[1].get("failures", [])
    check(
        not [f for f in fails if f["stage"] in ("scoring", "scoring_exhausted")],
        "failed_jobs has NO scoring rows for JD-after-resumes",
    )


def s3_none_jd_scores_immediately(c):
    print("\n[S3] jd.source=none with explicit skills scores immediately (no PATCH)")
    body = new_job(
        c,
        "A",
        job_title="Explicit only (itest)",
        jd={"source": "none"},
        required_skills=["Python", "AWS", "DynamoDB"],
        required_titles=["backend engineer"],
        min_experience_years=3,
        resume_filenames=["alice_johnson_native.pdf"],
    )
    job_id = c.s3_job = body["job_id"]
    jv = job_view(c, "A", job_id)
    check(
        jv["scorable"]
        and jv["parse_status"] == "not_applicable"
        and jv["effective"]["skills"] == ["aws", "dynamodb", "python"],
        "job is scorable at creation; skills normalized",
    )
    upload(body["resumes"][0]["upload"], (RESUMES / "alice_johnson_native.pdf").read_bytes())
    c.s3_cid = body["resumes"][0]["candidate_id"]
    rows = wait(
        lambda: [r for r in candidates(c, "A", job_id) if r["display_status"] == "scored"], 400, 8, "scoring"
    )
    check(bool(rows), "resume scored without any PATCH")
    if rows:
        r = rows[0]
        # Alice has python/aws/dynamodb, held "senior backend engineer" (related), ~6.9y vs 3y required
        check(
            r["skills_score"] == 100.0 and r["experience_score"] == 100.0,
            "explicit requirements applied",
            f"skills={r['skills_score']} exp={r['experience_score']}",
        )
        print("   alice:", r["match_score"], r["title_match"], r["experience_basis"])
    s, b, _ = req(c, "POST", "/jobs", "A", {"job_title": "x", "jd": {"source": "none"}})
    check(
        s == 400 and b["error"]["code"] == "REQUIREMENTS_REQUIRED",
        "none-JD without skills -> 400 REQUIREMENTS_REQUIRED",
    )


def s4_no_skill_jd_then_patch(c):
    print("\n[S4] A JD that yields no skills blocks scoring until PATCHed")
    text = "We are looking for a friendly, motivated and reliable colleague to join our growing team. You will be working with great people in a supportive environment and will help us make every day better for our customers and each other."
    body = new_job(
        c,
        "A",
        job_title="Vague role (itest)",
        jd={"source": "text", "text": text},
        resume_filenames=["bob_kumar.docx"],
    )
    job_id = c.s4_job = body["job_id"]
    check(body["jd_upload"] is None, "text JD: no JD upload credential (server wrote jd.txt)")
    upload(body["resumes"][0]["upload"], (RESUMES / "bob_kumar.docx").read_bytes())
    jv = wait(
        lambda: (lambda v: v if v.get("parse_status") == "parsed" else None)(job_view(c, "A", job_id)),
        400,
        8,
        "JD parse",
    )
    check(
        bool(jv) and jv["blocking_reason"] == "no_required_skills" and not jv["scorable"],
        "JD parsed but blocking_reason=no_required_skills",
        str(jv and jv.get("blocking_reason")),
    )
    rows = wait(
        lambda: [r for r in candidates(c, "A", job_id) if r["display_status"] == "awaiting_requirements"],
        400,
        8,
        "resume parse",
    )
    check(bool(rows), "candidate shows awaiting_requirements and is not scored")
    s, b, _ = req(c, "PATCH", f"/jobs/{job_id}", "A", {"required_skills": ["python", "aws"]})
    check(
        s == 200 and b["scorable"] and b["rescore_enqueued"] == 1,
        "PATCH makes it scorable and enqueues 1 rescore",
        str(b)[:200],
    )
    rows = wait(
        lambda: [r for r in candidates(c, "A", job_id) if r["display_status"] == "scored"], 300, 6, "rescore"
    )
    check(bool(rows), "candidate is scored after the PATCH")


def s5_decisions_and_rescore(c):
    print("\n[S5] Decisions, rescoring invariants, SES failure path")
    rows = getattr(c, "s2_rows", [])
    scored = [r for r in rows if r["display_status"] == "scored"]
    if not scored:
        check(False, "S2 produced scored candidates to decide on")
        return
    job_id, cand = c.s2_job, scored[0]["candidate_id"]
    unscored = next((r for r in rows if r["display_status"] == "error"), None)
    if unscored:
        s, b, _ = req(
            c,
            "POST",
            f"/jobs/{job_id}/candidates/{unscored['candidate_id']}/decision",
            "A",
            {"decision": "shortlisted"},
        )
        check(
            s == 409 and b["error"]["code"] == "NOT_SCORED",
            "decision on an unscored candidate -> 409 NOT_SCORED",
        )
    s, b, _ = req(c, "POST", f"/jobs/{job_id}/candidates/{cand}/decision", "A", {"decision": "shortlisted"})
    check(s == 200 and b["decision"] == "shortlisted", "shortlist -> 200", str(b))
    # Fixture addresses are unverified in the SES sandbox -> SES rejects -> failed, but the decision stands (R-BUS-08).
    check(
        b.get("notification_status") == "failed",
        "SES sandbox rejects an unverified recipient -> notification_status=failed, decision kept",
        str(b),
    )
    row = next(r for r in candidates(c, "A", job_id) if r["candidate_id"] == cand)
    check(row["decision"] == "shortlisted" and row["notification_status"] == "failed", "stored state matches")
    fails = req(c, "GET", "/failed-jobs", "admin", params={"job_id": job_id})[1].get("failures", [])
    api_rows = [f for f in fails if f["stage"] == "api" and f.get("candidate_id") == cand]
    check(
        len(api_rows) == 1 and "example-mail" not in json.dumps(api_rows),
        "one stage=api audit row, with no email address in it",
        str(api_rows)[:200],
    )

    before = {
        r["candidate_id"]: (r["decision"], r["notification_status"]) for r in candidates(c, "A", job_id)
    }
    s, b, _ = req(c, "PATCH", f"/jobs/{job_id}", "A", {"shortlist_threshold": 95})
    check(
        s == 200 and b["rescore_enqueued"] == 4,
        "PATCH threshold -> rescore enqueued for the 4 parsed candidates",
        str(b.get("rescore_enqueued")),
    )
    time.sleep(25)
    rows2 = candidates(c, "A", job_id)
    after = {r["candidate_id"]: (r["decision"], r["notification_status"]) for r in rows2}
    check(before == after, "rescore left every decision and notification_status unchanged (R-BUS-05)")
    scored2 = [r for r in rows2 if r["display_status"] == "scored"]
    check(
        scored2
        and all(r["recommended"] is (r["match_score"] >= 95) for r in scored2)
        and any(r["recommended"] is False for r in scored2),
        "recommended flag follows the new threshold (95): recommended <=> match_score >= 95",
        str([(r["match_score"], r["recommended"]) for r in scored2]),
    )
    s, b, _ = req(
        c, "POST", f"/jobs/{job_id}/candidates/{cand}/decision", "A", {"decision": "shortlisted", "extra": 1}
    )
    check(s == 400 and b["error"]["code"] == "VALIDATION_FAILED", "unknown request field -> 400")


def s6_email_at_most_once(c):
    print("\n[S6] Exactly one email: shortlist -> reject -> shortlist (SES mailbox simulator)")
    job_id = c.s3_job
    cid = seed_candidate(
        c,
        job_id,
        name="=cmd|' /C calc'!A0",
        email=SIM_OK,
        skills=["python"],
        titles_held=["backend engineer"],
        total_experience_years=Decimal("4.0"),
    )
    enqueue_score(c, job_id, cid)
    ok = wait(
        lambda: c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid}, ConsistentRead=True)[
            "Item"
        ].get("score_status")
        == "scored",
        120,
        4,
        "seeded candidate scored",
    )
    check(bool(ok), "seeded candidate scored by the deployed Lambda")
    path = f"/jobs/{job_id}/candidates/{cid}/decision"
    s, b1, _ = req(c, "POST", path, "A", {"decision": "shortlisted"})
    check(s == 200 and b1["notification_status"] == "sent", "first shortlist -> email sent", str(b1))
    sent_at = c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid})["Item"].get(
        "notification_sent_at"
    )
    s, b2, _ = req(c, "POST", path, "A", {"decision": "rejected"})
    s, b3, _ = req(c, "POST", path, "A", {"decision": "shortlisted"})
    item = c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid})["Item"]
    check(
        b2["notification_status"] == "sent"
        and b3["notification_status"] == "sent"
        and item["notification_sent_at"] == sent_at,
        "reject then re-shortlist sends nothing new (notification_sent_at unchanged)",
    )
    check(item["decision"] == "shortlisted" and item["decided_by"], "final decision recorded with decided_by")
    # missing email -> skipped_no_email
    cid2 = seed_candidate(
        c, job_id, name="No Email", skills=["python"], titles_held=[], total_experience_years=Decimal("1")
    )
    enqueue_score(c, job_id, cid2)
    wait(
        lambda: c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid2}, ConsistentRead=True)[
            "Item"
        ].get("score_status")
        == "scored",
        120,
        4,
        "scored",
    )
    s, b, _ = req(c, "POST", f"/jobs/{job_id}/candidates/{cid2}/decision", "A", {"decision": "shortlisted"})
    check(
        s == 200 and b["notification_status"] == "skipped_no_email",
        "no email on file -> skipped_no_email, decision still 200",
        str(b),
    )
    c.s6_cid = cid


def s7_export_and_resume_url(c):
    print("\n[S7] Export + resume view")
    job_id = c.s3_job
    s, b, _ = req(c, "GET", f"/jobs/{job_id}/export", "A")
    check(s == 200 and b["row_count"] == 2, "export lists only shortlisted candidates", str(b)[:120])
    if s == 200:
        r = requests.get(b["download_url"], timeout=30)
        text = r.content.decode("utf-8-sig")
        check(
            r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf"),
            "download works and starts with a UTF-8 BOM",
        )
        lines = text.strip().splitlines()
        check(
            lines[0] == "name,email,skills,titles_held,total_experience_years,match_score,decided_at",
            "CSV columns exactly per R-BUS-12",
        )
        check(
            any(ln.startswith("'=cmd") for ln in lines),
            "a name beginning '=' is exported as '= (formula defused)",
            str(lines)[:200],
        )
    cid = c.s3_cid
    s, b, _ = req(c, "GET", f"/jobs/{job_id}/candidates/{cid}/resume-url", "A")
    check(s == 200 and b["expires_in"] == 60, "resume-url -> 200 (60 s)")
    if s == 200:
        r = requests.get(b["url"], timeout=30)
        check(
            r.status_code == 200
            and r.content[:5] == b"%PDF-"
            and "inline" in r.headers.get("Content-Disposition", ""),
            "presigned URL serves the actual PDF inline",
        )


def s8_cross_recruiter(c):
    print("\n[S8] Recruiter B against Recruiter A's job (R-AUTH-03/04) + Admin")
    job_id, cid = c.s3_job, c.s3_cid
    before = c.jobs.get_item(Key={"job_id": job_id})["Item"]
    probes = [
        ("GET", f"/jobs/{job_id}", None),
        ("PATCH", f"/jobs/{job_id}", {"shortlist_threshold": 1}),
        ("POST", f"/jobs/{job_id}/resumes", {"resume_filenames": ["a.pdf"]}),
        ("GET", f"/jobs/{job_id}/candidates", None),
        ("POST", f"/jobs/{job_id}/candidates/{cid}/decision", {"decision": "rejected"}),
        ("GET", f"/jobs/{job_id}/candidates/{cid}/resume-url", None),
        ("GET", f"/jobs/{job_id}/export", None),
    ]
    codes = [(m, p.split(job_id)[-1] or "/", req(c, m, p, "B", b)[0]) for m, p, b in probes]
    check(all(code == 404 for *_, code in codes), "B gets 404 on every one of A's job routes", str(codes))
    missing = req(c, "GET", "/jobs/job_" + "9" * 32, "B")
    other = req(c, "GET", f"/jobs/{job_id}", "B")
    check(missing[1] == other[1], "not-owned and non-existent produce identical bodies")
    after = c.jobs.get_item(Key={"job_id": job_id})["Item"]
    check(before == after, "B's writes changed nothing in DynamoDB")
    _, jb, _ = req(c, "GET", "/jobs", "B")
    check(all(j["job_id"] != job_id for j in jb["jobs"]), "GET /jobs for B does not list A's jobs")
    _, ja, _ = req(c, "GET", "/jobs", "A")
    check(
        job_id in {j["job_id"] for j in ja["jobs"]}
        and {c.s2_job, c.s4_job} <= {j["job_id"] for j in ja["jobs"]},
        "GET /jobs for A lists A's jobs",
    )
    check(
        all(
            ja["jobs"][i]["created_at"] >= ja["jobs"][i + 1]["created_at"] for i in range(len(ja["jobs"]) - 1)
        ),
        "jobs listed newest first",
    )
    s, ad, _ = req(c, "GET", "/jobs", "admin")
    check(
        s == 200
        and job_id in {j["job_id"] for j in ad["jobs"]}
        and all("recruiter_id" in j for j in ad["jobs"]),
        "Admin sees all jobs, with recruiter_id",
    )
    check(req(c, "GET", f"/jobs/{job_id}", "admin")[0] == 200, "Admin can open any job")
    s, fj, _ = req(c, "GET", "/failed-jobs", "admin")
    check(s == 200 and isinstance(fj["failures"], list), "Admin GET /failed-jobs -> 200")


def s9_upload_limits(c):
    print("\n[S9] S3 enforces the presigned-POST policy")
    body = new_job(
        c,
        "A",
        job_title="Upload limits (itest)",
        jd={"source": "none"},
        required_skills=["python"],
        resume_filenames=["big.pdf", "wrongtype.pdf"],
    )
    up_big = body["resumes"][0]["upload"]
    r = upload(up_big, b"%PDF-" + b"0" * (11 * 1024 * 1024))
    check(
        r.status_code == 400 and "EntityTooLarge" in r.text,
        "an 11 MB upload is rejected by S3 (EntityTooLarge)",
        f"{r.status_code} {r.text[:150]}",
    )
    up = body["resumes"][1]["upload"]
    fields = {**up["fields"], "Content-Type": "text/html"}
    r = requests.post(up["url"], data=fields, files={"file": ("x", io.BytesIO(b"%PDF-x"))}, timeout=30)
    check(r.status_code == 403, "changing the Content-Type breaks the POST policy", f"{r.status_code}")
    fields = {**up["fields"], "key": up["fields"]["key"].replace("resume.pdf", "other.pdf")}
    r = requests.post(up["url"], data=fields, files={"file": ("x", io.BytesIO(b"%PDF-x"))}, timeout=30)
    check(r.status_code == 403, "changing the key breaks the POST policy", f"{r.status_code}")
    s, b, _ = req(
        c,
        "POST",
        "/jobs",
        "A",
        {
            "job_title": "x",
            "jd": {"source": "none"},
            "required_skills": ["a"],
            "resume_filenames": ["../../etc/passwd.exe"],
        },
    )
    check(s == 400 and b["error"]["code"] == "VALIDATION_FAILED", "unsupported extension rejected by the API")


def s10_worked_example(c):
    print("\n[S10] Worked example scores 71.3 on the deployed scoring Lambda")
    body = new_job(
        c,
        "A",
        job_title="Worked example (itest)",
        jd={"source": "none"},
        required_skills=["python", "aws", "dynamodb"],
        required_titles=["backend engineer"],
        min_experience_years=3,
    )
    job_id = body["job_id"]
    cid = seed_candidate(
        c,
        job_id,
        skills=["aws", "python", "sql"],
        titles_held=["backend developer"],
        total_experience_years=Decimal("4.0"),
        name="Worked Example",
    )
    enqueue_score(c, job_id, cid)
    item = wait(
        lambda: (lambda i: i if i.get("score_status") == "scored" else None)(
            c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid}, ConsistentRead=True)["Item"]
        ),
        120,
        4,
        "scoring",
    )
    check(
        bool(item) and item["match_score"] == Decimal("71.3"),
        "match_score == 71.3",
        str(item and item.get("match_score")),
    )
    if item:
        check(
            (item["skills_score"], item["title_score"], item["experience_score"])
            == (Decimal("66.7"), Decimal("60.0"), Decimal("100.0")),
            "sub-scores 66.7 / 60 / 100",
        )
        check(
            item["shortlist_candidate"] is True
            and item["title_match_type"] == "related"
            and item["missing_skills"] == ["dynamodb"],
            "recommended, related title, dynamodb missing",
        )
        check(isinstance(item["match_score"], Decimal), "stored as a DynamoDB Number (Decimal)")


def s11_force_scoring_failure_start(c):
    print("\n[S11a] Forcing a genuine scoring exception (a malformed attribute) — verified at the end")
    body = new_job(
        c, "A", job_title="Forced failure (itest)", jd={"source": "none"}, required_skills=["python"]
    )
    c.s11_job = body["job_id"]
    c.s11_cid = seed_candidate(
        c, c.s11_job, skills=["python"], titles_held=[], total_experience_years="not-a-number"
    )
    enqueue_score(c, c.s11_job, c.s11_cid)
    c.s11_started = time.time()


def s11_force_scoring_failure_verify(c):
    print("\n[S11b] Retry exhaustion -> scoring_exhausted -> score_status=error, parse_status stays parsed")

    def done():
        it = c.cands.get_item(Key={"job_id": c.s11_job, "candidate_id": c.s11_cid}, ConsistentRead=True)[
            "Item"
        ]
        return it if it.get("score_status") == "error" else None

    item = wait(done, 900, 15, "scoring retries to exhaust (5 x 60 s visibility)")
    check(bool(item), "candidate ends with score_status=error", str(item))
    if not item:
        return
    check(
        item["parse_status"] == "parsed" and item["error_code"] == "scoring_failed",
        "parse_status still 'parsed'; error_code=scoring_failed (D-17)",
    )
    fails = req(c, "GET", "/failed-jobs", "admin", params={"job_id": c.s11_job})[1]["failures"]
    scoring = [f for f in fails if f["stage"] == "scoring"]
    exhausted = [f for f in fails if f["stage"] == "scoring_exhausted"]
    check(len(scoring) == 5, "5 'scoring' attempt rows", str(len(scoring)))
    check(
        len(exhausted) == 1 and exhausted[0]["terminal"] is True and exhausted[0].get("raw_payload"),
        "exactly 1 terminal scoring_exhausted row with raw_payload",
    )
    _, rows, _ = req(c, "GET", f"/jobs/{c.s11_job}/candidates", "A")
    r = rows["candidates"][0]
    check(
        r["display_status"] == "error" and r["error_code"] == "scoring_failed",
        "API shows display_status=error / scoring_failed",
    )
    cw = boto3.client("cloudwatch", region_name=REGION)
    m = wait(
        lambda: cw.list_metrics(
            Namespace="ResumeScreener",
            MetricName="TerminalFailures",
            Dimensions=[{"Name": "Queue", "Value": "scoring"}],
        )["Metrics"],
        240,
        15,
        "EMF metric",
    )
    check(
        bool(m),
        "EMF metric ResumeScreener/TerminalFailures{Queue=scoring} exists (JSON log format passes EMF through)",
    )
    name = f"rs-TerminalFailuresScoring-{c.env}"

    def alarm_state():
        a = cw.describe_alarms(AlarmNames=[name])["MetricAlarms"]
        return a and a[0]["StateValue"] == "ALARM"

    check(
        bool(wait(alarm_state, 420, 20, "alarm to fire")),
        f"alarm {name} entered ALARM state (would notify AlertsTopic)",
    )


def s12_logs_have_no_pii(c):
    print("\n[S12] No candidate PII in any function log (R-PRIV-01)")
    logs = boto3.client("logs", region_name=REGION)
    start = int((c.started - 60) * 1000)
    needles = [
        "example-mail.test",
        "Alice Johnson",
        "Bob Kumar",
        "Jordan Rivera",
        "simulator.amazonses.com",
        "Worked Example",
        "No Email",
    ]
    pattern = " ".join(f'?"{n}"' for n in needles)
    hits = []
    groups = [
        g["logGroupName"]
        for g in logs.describe_log_groups(logGroupNamePrefix="/aws/lambda/rs-")["logGroups"]
        if g["logGroupName"].endswith(f"-{c.env}")
    ]
    for g in groups:
        ev = logs.filter_log_events(logGroupName=g, startTime=start, filterPattern=pattern, limit=5)["events"]
        hits += [(g, e["message"][:160]) for e in ev]
    check(len(groups) >= 14 and not hits, f"0 PII hits across {len(groups)} log groups", str(hits[:3]))
    check(not [g for g in groups if "textract" in g or "comprehend" in g], "no textract/comprehend anywhere")


def main() -> int:
    c = setup()
    print(f"API: {c.api}  stack: resume-screener-{c.env}")
    s1_edge_auth(c)
    s11_force_scoring_failure_start(c)  # starts the ~5 min retry clock; verified at the end
    s10_worked_example(c)
    s2_resumes_before_jd(c)
    s3_none_jd_scores_immediately(c)
    s4_no_skill_jd_then_patch(c)
    s5_decisions_and_rescore(c)
    s6_email_at_most_once(c)
    s7_export_and_resume_url(c)
    s8_cross_recruiter(c)
    s9_upload_limits(c)
    s11_force_scoring_failure_verify(c)
    s12_logs_have_no_pii(c)
    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for label in failed:
        print("  FAILED:", label)
    print("PASS" if not failed else "FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
