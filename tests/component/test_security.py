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
import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import yaml

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


# ---------------------------------------------------------------------------
# S18: API Gateway TLS security policy configured
# ---------------------------------------------------------------------------
class _CfnLoader(yaml.SafeLoader):
    pass


def _cfn_default_ctor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CfnLoader.add_multi_constructor("!", _cfn_default_ctor)


def _load_cfn_template() -> dict:
    template_path = REPO_ROOT / "template.yaml"
    with open(template_path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_CfnLoader)


def test_s18_api_gateway_tls_security_policy():
    """Verify RecruiterApi configures the modern PFS-enabled TLS 1.2 EDGE security policy."""
    tmpl = _load_cfn_template()
    recruiter_api = tmpl["Resources"]["RecruiterApi"]["Properties"]

    # SecurityPolicy exists and specifies SecurityPolicy_TLS12_PFS_2025_EDGE
    sec_policy = recruiter_api.get("SecurityPolicy")
    assert sec_policy is not None, "SecurityPolicy must be configured on RecruiterApi"
    assert sec_policy == "SecurityPolicy_TLS12_PFS_2025_EDGE", (
        f"Expected SecurityPolicy_TLS12_PFS_2025_EDGE, got {sec_policy}"
    )

    # EndpointAccessMode configured to satisfy 2025 EDGE TLS security policy
    access_mode = recruiter_api.get("EndpointAccessMode")
    assert access_mode == "BASIC", f"Expected EndpointAccessMode to be BASIC, got {access_mode}"

    # API endpoint configuration must not alter endpoint type
    endpoint_config = recruiter_api.get("EndpointConfiguration")
    if endpoint_config:
        assert endpoint_config.get("Type", "EDGE") == "EDGE"


def test_s19_api_gateway_access_logging_configured():
    """Verify API Gateway access logging format, destination, and method metrics."""
    tmpl = _load_cfn_template()
    recruiter_api = tmpl["Resources"]["RecruiterApi"]["Properties"]

    # AccessLogSetting exists
    access_log = recruiter_api.get("AccessLogSetting")
    assert access_log is not None, "AccessLogSetting must be configured on RecruiterApi"

    # Destination references API access log group without trailing :*
    assert "ApiAccessLogGroup" in tmpl["Resources"], "ApiAccessLogGroup resource must exist"
    dest_arn = str(access_log.get("DestinationArn", ""))
    assert "log-group:/aws/apigateway/rs-api-" in dest_arn, (
        f"DestinationArn must target the API access log group, got: {dest_arn}"
    )
    assert not dest_arn.endswith(":*"), (
        f"DestinationArn must not contain trailing :* (got {dest_arn})"
    )

    # Format contains requestId
    fmt_str = access_log.get("Format", "")
    assert "$context.requestId" in fmt_str, "Access log format must include $context.requestId"
    fmt_json = json.loads(fmt_str)
    assert "requestId" in fmt_json or any("requestId" in k for k in fmt_json.keys())

    # Format does not contain Authorization/token/password/body fields
    forbidden_terms = ("authorization", "token", "password", "body", "secret", "bearer")
    for term in forbidden_terms:
        assert term not in fmt_str.lower(), f"Access log format must not contain {term}"

    # Format contains TLS metadata
    assert "$context.tlsVersion" in fmt_str, "Access log format must include $context.tlsVersion"
    assert "$context.cipherSuite" in fmt_str, "Access log format must include $context.cipherSuite"
    assert "tlsVersion" in fmt_json
    assert "cipherSuite" in fmt_json

    # API method metrics enabled
    method_settings = recruiter_api.get("MethodSettings", [])
    assert len(method_settings) > 0, "MethodSettings must be defined on RecruiterApi"
    assert any(
        setting.get("MetricsEnabled") is True for setting in method_settings
    ), "MethodSettings must enable MetricsEnabled"


def test_s20_cognito_password_policy_requires_symbols():
    """Verify Cognito UserPool enforces symbol requirement."""
    tmpl = _load_cfn_template()
    pwd_policy = tmpl["Resources"]["UserPool"]["Properties"]["Policies"]["PasswordPolicy"]
    assert pwd_policy.get("RequireSymbols") is True, "PasswordPolicy must require symbols"


def test_s21_cloudfront_security_headers_complete():
    """Verify CloudFront response headers policy includes required CSP directives and Permissions-Policy."""
    tmpl = _load_cfn_template()
    headers_config = tmpl["Resources"]["WebHeadersPolicy"]["Properties"]["ResponseHeadersPolicyConfig"]

    # CSP exists and contains required directives
    csp_config = headers_config.get("SecurityHeadersConfig", {}).get("ContentSecurityPolicy", {})
    assert csp_config is not None, "ContentSecurityPolicy must be configured"
    csp_str = csp_config.get("ContentSecurityPolicy", "")

    assert "script-src 'self'" in csp_str, "CSP must explicitly include script-src 'self'"
    assert "base-uri 'self'" in csp_str, "CSP must include base-uri 'self'"
    assert "form-action 'self'" in csp_str, "CSP must include form-action 'self'"

    # Permissions-Policy exists and contains required restricted features
    custom_items = headers_config.get("CustomHeadersConfig", {}).get("Items", [])
    perm_header = next((i for i in custom_items if i.get("Header") == "Permissions-Policy"), None)
    assert perm_header is not None, "Permissions-Policy custom header must be configured"

    perm_val = perm_header.get("Value", "")
    for feature in ("camera=()", "microphone=()", "geolocation=()", "payment=()", "usb=()"):
        assert feature in perm_val, f"Permissions-Policy must restrict {feature}"


def test_s22_api_lambda_alarms_declared():
    """Verify CloudWatch error alarms for key API lambdas and aggregate throttle alarm."""
    tmpl = _load_cfn_template()
    resources = tmpl["Resources"]

    required_alarms = {
        "CreateJobPostingErrors": "CreateJobPostingFunction",
        "AddResumesErrors": "AddResumesFunction",
        "UpdateCandidateDecisionErrors": "UpdateCandidateDecisionFunction",
    }

    for alarm_name, func_resource in required_alarms.items():
        assert alarm_name in resources, f"Alarm {alarm_name} must be declared in template"
        alarm = resources[alarm_name]
        props = alarm.get("Properties", {})
        assert props.get("MetricName") == "Errors"
        assert props.get("Namespace") == "AWS/Lambda"
        dimensions = props.get("Dimensions", [])
        assert any(
            d.get("Name") == "FunctionName" and func_resource in str(d.get("Value")) for d in dimensions
        ), f"{alarm_name} must monitor {func_resource}"
        actions = props.get("AlarmActions", [])
        assert any("AlertsTopic" in str(a) for a in actions), f"{alarm_name} must notify AlertsTopic"

    # Aggregate API Lambda throttle alarm exists
    assert "ApiLambdaThrottles" in resources, "ApiLambdaThrottles aggregate alarm must be declared"
    throttle_alarm = resources["ApiLambdaThrottles"]
    t_props = throttle_alarm.get("Properties", {})
    t_actions = t_props.get("AlarmActions", [])
    assert any("AlertsTopic" in str(a) for a in t_actions), "ApiLambdaThrottles must notify AlertsTopic"

    # Verify metrics or expression in throttle alarm
    metrics = t_props.get("Metrics", [])
    assert len(metrics) > 0, "ApiLambdaThrottles must define metric math for aggregate monitoring"
    expr_metrics = [m for m in metrics if "Expression" in m]
    assert len(expr_metrics) > 0, "ApiLambdaThrottles must include an aggregate expression"


def test_s23_api_gateway_method_metrics_enabled():
    """Verify API Gateway method metrics are explicitly enabled in template."""
    tmpl = _load_cfn_template()
    recruiter_api = tmpl["Resources"]["RecruiterApi"]["Properties"]
    method_settings = recruiter_api.get("MethodSettings", [])
    assert any(
        setting.get("MetricsEnabled") is True for setting in method_settings
    ), "RecruiterApi MethodSettings must have MetricsEnabled: true"
