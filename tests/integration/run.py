#!/usr/bin/env python3
"""Phase 5 end-to-end integration test runner.

docs/05-integration-testing-and-delivery.md §2

Usage:
    python tests/integration/run.py [--env dev]

Authenticates as Recruiter A through Cognito SRP (per-run ephemeral random
password — never committed). Creates a single job with:
    2 native PDF + 1 scanned PDF + 1 mixed PDF + 1 DOCX + 1 PNG + 1 renamed-text-as-PDF
Uploads resumes FIRST, then uploads the JD after a 30-second delay (D-18).
Polls every 5 s up to 15 min until all candidates reach a terminal state.

Asserts:
  - 6 rows scored, 1 row error/unsupported_format
  - each scored row has sub-scores, matched_skills, scoring_version = v1
  - failed_jobs has no scoring or scoring_exhausted rows
  - the worked-example fixture scores 71.3 (seeded into DynamoDB, scored by the
    real deployed Lambda — NLP cannot produce this deterministically)
  - shortlist -> reject -> shortlist at-most-once email cycle
  - SES mailbox simulator (success@simulator.amazonses.com) receives exactly one email
  - CSV export has correct columns and formula-defused rows

On success writes docs/evidence/integration-<date>.json.
"""

from __future__ import annotations

import argparse
import io
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
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
EVIDENCE_DIR = REPO / "docs" / "evidence"

RESULTS: list[tuple[bool, str]] = []
TIMINGS: dict = {}


def check(cond: bool, label: str, detail: str = "") -> bool:
    RESULTS.append((bool(cond), label))
    print(f"  [{'OK  ' if cond else 'FAIL'}] {label}" + (f"  -- {detail}" if detail and not cond else ""))
    return bool(cond)


def wait(fn, timeout: int = 900, interval: int = 5, what: str = "condition"):
    """Poll fn() every interval seconds until it returns a truthy value or timeout expires."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    print(f"  [..] timed out after {timeout}s waiting for {what}")
    return last


class Ctx:
    pass


def setup(env: str) -> Ctx:
    c = Ctx()
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

    # Authenticate all test users with ephemeral random passwords (never committed — D-60).
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
        headers["Authorization"] = tok
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


def upload(up: dict, data: bytes, name: str = "file") -> requests.Response:
    return requests.post(up["url"], data=up["fields"], files={"file": (name, io.BytesIO(data))}, timeout=60)


def candidates(c: Ctx, who: str, job_id: str) -> list:
    s, b, _ = req(c, "GET", f"/jobs/{job_id}/candidates", who)
    return b.get("candidates", []) if s == 200 else []


def job_view(c: Ctx, who: str, job_id: str) -> dict:
    return req(c, "GET", f"/jobs/{job_id}", who)[1]


def new_job(c: Ctx, who: str, **body) -> dict:
    s, b, _ = req(c, "POST", "/jobs", who, body)
    assert s == 201, (s, b)
    return b


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


def enqueue_score(c: Ctx, job_id: str, cid: str) -> None:
    c.sqs.send_message(
        QueueUrl=c.out["ScoringQueueUrl"],
        MessageBody=json.dumps({"job_id": job_id, "candidate_id": cid, "reason": "candidate_parsed"}),
    )


# ---------------------------------------------------------------------------
# Test sections
# ---------------------------------------------------------------------------


def s1_core_pipeline(c: Ctx) -> None:
    """Phase 5 §2: 7-resume job — 2 native PDF, 1 scanned PDF, 1 mixed PDF,
    1 DOCX, 1 PNG, 1 renamed text-as-PDF.  Resumes uploaded FIRST, then the JD
    after an explicit 30-second delay (D-18).  Polling: every 5 s, up to 15 min."""
    print("\n[S1] Core pipeline: 7 resumes (6 scorable + 1 unsupported), JD after 30 s")
    t0 = time.time()

    good = [
        "worked_example_native.pdf",  # native PDF #1 (scored to 71.3 by NLP)
        "alice_johnson_native.pdf",  # native PDF #2
        "daniel_kim_scanned.pdf",  # scanned PDF
        "maya_bennett_mixed.pdf",  # mixed PDF
        "bob_kumar.docx",  # DOCX
        "jordan_rivera.png",  # PNG (standalone image, OCR path)
    ]
    bad = {"renamed_text_file.pdf": "unsupported_format"}

    body = new_job(
        c,
        "A",
        job_title="Backend Engineer (phase5-itest)",
        jd={"source": "file", "filename": "backend_engineer_jd.pdf"},
        resume_filenames=good + list(bad),
        shortlist_threshold=60,
    )
    job_id = c.s1_job = body["job_id"]
    check(
        body["jd_upload"] is not None and len(body["resumes"]) == 7,
        "POST /jobs 201 with 1 JD upload + 7 resume presigned posts",
        f"resumes={len(body.get('resumes', []))}",
    )

    # Upload resumes FIRST
    by_name = {r["filename"]: r for r in body["resumes"]}
    for name in good + list(bad):
        r = upload(by_name[name]["upload"], (RESUMES / name).read_bytes())
        assert r.status_code in (200, 201, 204), (name, r.status_code, r.text[:200])
    print(f"  uploaded 7 resumes at t+{time.time()-t0:.0f}s; waiting 30 s before JD upload")

    # Explicit 30-second JD delay (Phase 5 §2 bullet 3)
    time.sleep(30)
    r = upload(body["jd_upload"], (JDS / "backend_engineer_jd.pdf").read_bytes())
    check(r.status_code in (200, 201, 204), "JD upload accepted after 30 s delay", f"{r.status_code}")
    print(f"  JD uploaded at t+{time.time()-t0:.0f}s — polling every 5 s up to 15 min")

    # Poll every 5 s, up to 15 minutes
    terminal = {"scored", "error", "upload_missing"}

    def all_terminal():
        rows = candidates(c, "A", job_id)
        if not rows:
            return None
        return rows if all(r["display_status"] in terminal for r in rows) else None

    rows = wait(all_terminal, timeout=900, interval=5, what="all 7 candidates terminal")
    c.s1_rows = rows or []

    elapsed = time.time() - t0
    TIMINGS["s1_pipeline_seconds"] = round(elapsed, 1)
    check(bool(rows), f"all 7 candidates terminal within 15 min (took {elapsed:.0f}s)")
    if not rows:
        return

    scored = [r for r in rows if r["display_status"] == "scored"]
    errors = [r for r in rows if r["display_status"] == "error"]
    check(len(scored) == 6, f"6 scored rows (got {len(scored)})", str([r["original_filename"] for r in rows]))
    check(len(errors) == 1, f"1 error row (got {len(errors)})")
    if errors:
        check(
            errors[0]["error_code"] == "unsupported_format",
            "unsupported error_code on renamed text file",
            str(errors[0]),
        )

    # Sub-scores, matched_skills, scoring_version
    for row in scored:
        fn = row["original_filename"]
        check(
            row.get("skills_score") is not None
            and row.get("title_score") is not None
            and row.get("experience_score") is not None,
            f"{fn}: has sub-scores",
        )
        check(isinstance(row.get("matched_skills"), list), f"{fn}: matched_skills present")

    # scoring_version via DynamoDB (not exposed in API view)
    ddb_rows = []
    for row in scored:
        item = c.cands.get_item(
            Key={"job_id": job_id, "candidate_id": row["candidate_id"]}, ConsistentRead=True
        ).get("Item", {})
        ddb_rows.append(item)
    check(
        all(item.get("scoring_version") == "v1" for item in ddb_rows),
        "all scored rows have scoring_version = v1",
        str([i.get("scoring_version") for i in ddb_rows]),
    )

    # Sorted by score descending
    check(
        [r["match_score"] for r in scored] == sorted((r["match_score"] for r in scored), reverse=True),
        "scored rows sorted match_score desc",
    )

    # No scoring failures
    fails = req(c, "GET", "/failed-jobs", "admin", params={"job_id": job_id})[1].get("failures", [])
    check(
        not [f for f in fails if f["stage"] in ("scoring", "scoring_exhausted")],
        "failed_jobs has NO scoring rows",
    )


def s2_worked_example(c: Ctx) -> None:
    """71.3 worked example — seeded into DynamoDB, scored by the deployed Lambda."""
    print("\n[S2] Worked example scores 71.3")
    body = new_job(
        c,
        "A",
        job_title="Worked example (phase5-itest)",
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
        timeout=120,
        interval=5,
        what="worked-example scoring",
    )
    check(
        bool(item) and item.get("match_score") == Decimal("71.3"),
        "match_score == 71.3",
        str(item and item.get("match_score")),
    )
    if item:
        check(
            (item.get("skills_score"), item.get("title_score"), item.get("experience_score"))
            == (Decimal("66.7"), Decimal("60.0"), Decimal("100.0")),
            "sub-scores 66.7 / 60 / 100",
        )
        check(item.get("missing_skills") == ["dynamodb"], "dynamodb is missing skill")


def s3_email_at_most_once(c: Ctx) -> None:
    """Shortlist -> reject -> shortlist; only one email ever sent."""
    print("\n[S3] At-most-once email (shortlist -> reject -> shortlist)")
    if not getattr(c, "s1_job", None):
        check(False, "S1 job required for S3")
        return
    job_id = c.s1_job
    # Seed a candidate with the SES simulator email so mail actually sends
    cid = seed_candidate(
        c,
        job_id,
        name="=cmd|' /C calc'!A0",  # CSV-injection candidate name — tests formula defusal
        email=SIM_OK,
        skills=["python"],
        titles_held=["backend engineer"],
        total_experience_years=Decimal("4.0"),
    )
    enqueue_score(c, job_id, cid)
    wait(
        lambda: c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid}, ConsistentRead=True)[
            "Item"
        ].get("score_status")
        == "scored",
        timeout=120,
        interval=5,
        what="seeded candidate scored",
    )

    path = f"/jobs/{job_id}/candidates/{cid}/decision"
    s, b1, _ = req(c, "POST", path, "A", {"decision": "shortlisted"})
    check(s == 200 and b1.get("notification_status") == "sent", "first shortlist -> sent", str(b1))
    sent_at = c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid})["Item"].get(
        "notification_sent_at"
    )

    req(c, "POST", path, "A", {"decision": "rejected"})
    s, b3, _ = req(c, "POST", path, "A", {"decision": "shortlisted"})
    item = c.cands.get_item(Key={"job_id": job_id, "candidate_id": cid})["Item"]
    check(
        b3.get("notification_status") == "sent" and item.get("notification_sent_at") == sent_at,
        "re-shortlist does not send a second email (notification_sent_at unchanged)",
    )


def s4_csv_export(c: Ctx) -> None:
    """CSV export: correct columns, UTF-8 BOM, formula defusal."""
    print("\n[S4] CSV export")
    if not getattr(c, "s1_job", None):
        check(False, "S1 job required for S4")
        return
    job_id = c.s1_job
    s, b, _ = req(c, "GET", f"/jobs/{job_id}/export", "A")
    check(s == 200, f"GET /export -> {s}", str(b)[:80])
    if s == 200 and b.get("download_url"):
        r = requests.get(b["download_url"], timeout=30)
        text = r.content.decode("utf-8-sig")
        check(r.content.startswith(b"\xef\xbb\xbf"), "CSV starts with UTF-8 BOM")
        lines = text.strip().splitlines()
        check(
            lines[0] == "name,email,skills,titles_held,total_experience_years,match_score,decided_at",
            "CSV columns per R-BUS-12",
            str(lines[0]),
        )
        check(any(ln.startswith("'=cmd") for ln in lines), "formula-injection name defused with leading '")


def s5_no_scoring_failures_in_main_job(c: Ctx) -> None:
    """Final confirmation: no scoring failures in the main pipeline job."""
    print("\n[S5] Confirm no scoring failures")
    if not getattr(c, "s1_job", None):
        return
    fails = req(c, "GET", "/failed-jobs", "admin", params={"job_id": c.s1_job})[1].get("failures", [])
    check(
        not [f for f in fails if f["stage"] in ("scoring", "scoring_exhausted")],
        "no scoring/scoring_exhausted rows for the main pipeline job",
    )


def write_evidence(c: Ctx) -> None:
    """Write docs/evidence/integration-<date>.json — only written on a complete run."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    out_path = EVIDENCE_DIR / f"integration-{date_str}.json"

    rows = getattr(c, "s1_rows", [])
    scored = [r for r in rows if r["display_status"] == "scored"]
    errors = [r for r in rows if r["display_status"] == "error"]

    evidence = {
        "run_at": datetime.now(UTC).isoformat(),
        "env": c.env,
        "api_base": c.api,
        "job_id": getattr(c, "s1_job", None),
        "candidate_count": len(rows),
        "scored_count": len(scored),
        "error_count": len(errors),
        "candidates": [
            {
                "original_filename": r.get("original_filename"),
                "display_status": r.get("display_status"),
                "match_score": str(r.get("match_score")) if r.get("match_score") is not None else None,
                "error_code": r.get("error_code"),
            }
            for r in rows
        ],
        "timings": TIMINGS,
        "checks": {
            "total": len(RESULTS),
            "passed": sum(1 for ok, _ in RESULTS if ok),
            "failed": sum(1 for ok, _ in RESULTS if not ok),
        },
    }

    out_path.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(f"\nEvidence written: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 integration test runner")
    parser.add_argument("--env", default="dev", help="Stack environment (default: dev)")
    args = parser.parse_args()

    c = setup(args.env)
    print(f"API: {c.api}  stack: resume-screener-{args.env}")

    s2_worked_example(c)  # seed & score independently; fast (~2 min)
    s1_core_pipeline(c)  # long wait (~10–15 min)
    s3_email_at_most_once(c)
    s4_csv_export(c)
    s5_no_scoring_failures_in_main_job(c)

    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for label in failed:
        print("  FAILED:", label)
    verdict = "PASS" if not failed else "FAIL"
    print(verdict)

    if verdict == "PASS":
        write_evidence(c)
    else:
        print("Evidence NOT written because the run had failures. Fix the failures first.")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
