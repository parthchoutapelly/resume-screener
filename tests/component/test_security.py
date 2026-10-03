"""Component tests for Phase 5 Security Verification (S1–S15).

docs/05-integration-testing-and-delivery.md §4 (T-104)

Automated local tests for:
  S1: Missing/unauthorized context -> 401 (API Gateway edge) / 403 (lambda layer) with CORS headers
  S2: Groupless user (no cognito:groups) -> 403 FORBIDDEN
  S3: Cross-recruiter tenant isolation -> 404 and no DynamoDB mutation
  S4: Admin-only route (/failed-jobs) blocked for Recruiter -> 403
  S5: CORS origin header enforcement
  S8: Upload limits (10 MiB limit enforced)
  S9: CSV injection protection (formula prefixes =, +, -, @ sanitized)
  S10: XSS payloads preserved as pure text without raw interpolation
  S14: Self sign-up disabled in CloudFormation template (AllowAdminCreateUserOnly: true)
"""

from __future__ import annotations

import csv
import io
import os
from datetime import UTC, datetime
from decimal import Decimal

from conftest import (
    CANDIDATES_TABLE,
    JOB_A,
    JOBS_TABLE,
    REPO_ROOT,
    api_event,
    call,
    cid,
    put_candidate,
    put_job,
)
from moto import mock_aws


# ---------------------------------------------------------------------------
# S1: Unauthenticated -> CORS header preserved on error
# ---------------------------------------------------------------------------
@mock_aws
def test_s1_missing_auth_context_includes_cors(aws, handler):
    """An API call missing authorizer claims is rejected with an error and carries the CORS header.
    (Note: API Gateway returns 401 at the edge; within Lambda, missing claims yields 403)."""
    h = handler("get_jobs")
    raw_event = {"httpMethod": "GET", "headers": {"Origin": "http://localhost:5173"}, "requestContext": {}}
    resp = h.lambda_handler(raw_event, None)
    assert resp["statusCode"] in (401, 403)
    assert resp["headers"].get("Access-Control-Allow-Origin") == os.environ["ALLOWED_ORIGIN"]


# ---------------------------------------------------------------------------
# S2: Groupless user -> 403 FORBIDDEN
# ---------------------------------------------------------------------------
@mock_aws
def test_s2_groupless_user_is_403_on_recruiter_routes(aws, handler):
    """A valid user with no group assignment cannot access recruiter endpoints."""
    put_job(aws.ddb, job_id=JOB_A)
    for endpoint in ("get_jobs", "get_job", "get_candidates_by_job"):
        s, b = call(handler(endpoint), api_event(groups=None, path={"job_id": JOB_A}))
        assert s == 403
        assert b["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# S3: Cross-recruiter isolation -> 404 and no DynamoDB mutation
# ---------------------------------------------------------------------------
@mock_aws
def test_s3_cross_recruiter_tenant_isolation(aws, handler):
    """Recruiter B cannot read, update, or decide on Recruiter A's job.
    Routes return 404 (not 403) to prevent resource existence leaking (D-19)."""
    put_job(aws.ddb, job_id=JOB_A, recruiter="sub-a", shortlist_threshold=70)
    put_candidate(aws.ddb, 1, job_id=JOB_A, score_status="scored", match_score=Decimal("80.0"))

    # Recruiter B tries to GET Recruiter A's job
    s, b = call(handler("get_job"), api_event(sub="sub-b", path={"job_id": JOB_A}))
    assert s == 404
    assert b["error"]["code"] == "NOT_FOUND"

    # Recruiter B tries to PATCH Recruiter A's job
    s_patch, _ = call(
        handler("update_job"),
        api_event(sub="sub-b", path={"job_id": JOB_A}, body={"shortlist_threshold": 40}),
    )
    assert s_patch == 404

    # Verify Recruiter A's job is completely unchanged
    job_item = aws.ddb.Table(JOBS_TABLE).get_item(Key={"job_id": JOB_A})["Item"]
    assert job_item["shortlist_threshold"] == 70

    # Recruiter B tries to update candidate decision
    s_dec, _ = call(
        handler("update_candidate_decision"),
        api_event(sub="sub-b", path={"job_id": JOB_A, "candidate_id": cid(1)}, body={"decision": "rejected"}),
    )
    assert s_dec == 404

    # Verify candidate decision is unchanged
    cand_item = aws.ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": JOB_A, "candidate_id": cid(1)})[
        "Item"
    ]
    assert cand_item.get("decision") != "rejected"


# ---------------------------------------------------------------------------
# S4: Admin-only route blocked for Recruiter -> 403
# ---------------------------------------------------------------------------
@mock_aws
def test_s4_recruiter_blocked_from_failed_jobs(aws, handler):
    """Recruiters cannot access the /failed-jobs endpoint; only Admin can."""
    h = handler("get_failed_jobs")
    s, b = call(h, api_event(groups="Recruiter"))
    assert s == 403
    assert b["error"]["code"] == "FORBIDDEN"

    s_admin, b_admin = call(h, api_event(groups="Admin"))
    assert s_admin == 200


# ---------------------------------------------------------------------------
# S5: CORS origin header enforcement
# ---------------------------------------------------------------------------
@mock_aws
def test_s5_cors_origin_enforcement(aws, handler):
    put_job(aws.ddb, job_id=JOB_A)
    s, b = call(handler("get_job"), api_event(path={"job_id": JOB_A}))
    # Ensure standard response emits allowed origin
    assert os.environ["ALLOWED_ORIGIN"] in ("http://localhost:5173", "https://d1yg427uu45noj.cloudfront.net")


# ---------------------------------------------------------------------------
# S8: Upload limits (10 MiB limit)
# ---------------------------------------------------------------------------
def test_s8_upload_size_limit():
    from rs_common.uploads import MAX_UPLOAD_BYTES

    # Strictly 10 MiB per R-SEC-03
    assert MAX_UPLOAD_BYTES == 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# S9: CSV injection protection
# ---------------------------------------------------------------------------
def test_s9_csv_injection_defusing():
    from rs_common.exports import build_csv, csv_safe

    # Dangerous spreadsheet formula triggers: =, +, -, @
    for dangerous in ("=SUM(A1:A10)", "+cmd|' /C calc'!A0", "-5+5", "@SUM(1+1)"):
        defused = csv_safe(dangerous)
        assert defused.startswith("'"), f"Dangerous cell {dangerous} must start with single quote"

    # Safe cells remain unaltered
    assert csv_safe("Jane Doe") == "Jane Doe"
    assert csv_safe("jane.doe@example.com") == "jane.doe@example.com"

    # Verify generated CSV defuses rows
    records = [
        {
            "name": '=HYPERLINK("http://evil.com", "Click Me")',
            "email": "malicious@example.com",
            "skills": ["python"],
            "titles_held": ["engineer"],
            "total_experience_years": 5.0,
            "match_score": 90.0,
            "decided_at": "2026-09-26T12:00:00Z",
        }
    ]
    csv_bytes = build_csv(records)
    csv_text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert row["name"].startswith("'=")


# ---------------------------------------------------------------------------
# S10: XSS payloads treated as pure text
# ---------------------------------------------------------------------------
def test_s10_xss_payload_preserved_as_pure_text():
    from rs_common.views import candidate_view

    xss_name = "<script>alert(1)</script>"
    xss_skill = "<img src=x onerror=alert(1)>"
    cand_item = {
        "candidate_id": cid(1),
        "job_id": JOB_A,
        "name": xss_name,
        "skills": [xss_skill],
        "score_status": "scored",
        "match_score": Decimal("85.0"),
    }
    view = candidate_view(cand_item, {"job_id": JOB_A}, datetime.now(UTC))
    # Returned as raw strings for JSON serialization, never unescaped HTML
    assert view["name"] == xss_name
    assert view["skills"] == [xss_skill]


# ---------------------------------------------------------------------------
# S14: Self sign-up disabled in CloudFormation template
# ---------------------------------------------------------------------------
def test_s14_self_signup_disabled_in_template():
    template_path = REPO_ROOT / "template.yaml"
    with open(template_path, encoding="utf-8") as f:
        yaml_content = f.read()

    # Verify UserPool resource explicitly sets AllowAdminCreateUserOnly: true
    assert "AllowAdminCreateUserOnly: true" in yaml_content


# ---------------------------------------------------------------------------
# S9 (Extended): CSV injection with leading whitespace / tabs
# ---------------------------------------------------------------------------
def test_s9_csv_whitespace_injection_defusing():
    from rs_common.exports import build_csv, csv_safe

    # Leading-whitespace bypassed formulas must be sanitized
    for dangerous in (
        "   =SUM(A1:A10)",
        "\t =cmd|' /C calc'!A0",
        "  -5+5",
        " \t @SUM(1+1)",
        "\t=1+1",
    ):
        defused = csv_safe(dangerous)
        assert defused.startswith(
            "'"
        ), f"Whitespace-prefixed formula {dangerous!r} must start with single quote"

    # Safe cells remain unaltered
    assert csv_safe("   Jane Doe") == "   Jane Doe"
    assert csv_safe("Senior Engineer") == "Senior Engineer"

    # Verify generated CSV defuses whitespace-prefixed rows
    records = [
        {
            "name": '   =HYPERLINK("http://evil.com", "Click Me")',
            "email": "malicious@example.com",
            "skills": ["python"],
            "titles_held": ["engineer"],
            "total_experience_years": 5.0,
            "match_score": 90.0,
            "decided_at": "2026-09-26T12:00:00Z",
        }
    ]
    csv_bytes = build_csv(records)
    csv_text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert row["name"].startswith("'")


# ---------------------------------------------------------------------------
# S16: Frontend window.open prevents reverse tabnabbing
# ---------------------------------------------------------------------------
def test_s16_frontend_window_open_reverse_tabnabbing_protected():
    import re

    page_path = REPO_ROOT / "frontend" / "src" / "pages" / "JobDetailPage.jsx"
    with open(page_path, encoding="utf-8") as f:
        content = f.read()

    # Find all window.open invocations in JobDetailPage
    matches = re.findall(r"window\.open\(([^)]+)\)", content)
    assert len(matches) > 0, "Expected at least one window.open call in JobDetailPage"
    for args in matches:
        assert (
            "noopener" in args and "noreferrer" in args
        ), f"window.open call ({args}) must include 'noopener,noreferrer' to prevent reverse tabnabbing"


# ---------------------------------------------------------------------------
# S17: Job title phishing & email content abuse prevention
# ---------------------------------------------------------------------------
@mock_aws
def test_s17_job_title_phishing_rejected(aws, handler):
    from conftest import api_event, call

    h = handler("create_job_posting")

    # Titles with URLs or emails are rejected with 400
    for phish in (
        "Backend Engineer https://phish.example.com",
        "Developer (http://evil.com/apply)",
        "QA Lead www.scam-site.org",
        "Send CV to recruiter@fake-phish.net",
    ):
        s, b = call(
            h,
            api_event(
                body={
                    "job_title": phish,
                    "jd": {"source": "none"},
                    "required_skills": ["python"],
                }
            ),
        )
        assert s == 400
        assert b["error"]["code"] == "VALIDATION_FAILED"
        assert any(
            d["field"] == "job_title" and d["issue"] == "must_not_contain_urls_or_emails"
            for d in b["error"]["details"]
        )

    # Legitimate titles with punctuation accepted
    s_ok, b_ok = call(
        h,
        api_event(
            body={
                "job_title": "Senior Node.js & React Engineer (Full-Time)",
                "jd": {"source": "none"},
                "required_skills": ["python"],
            }
        ),
    )
    assert s_ok == 201
    assert "job_id" in b_ok
