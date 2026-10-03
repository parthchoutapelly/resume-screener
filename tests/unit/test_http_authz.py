"""http.py envelope/tokens and authz.caller group parsing (R-AUTH-02, R-ERR-05)."""

import json

import pytest

from rs_common import authz, http
from rs_common.http import HttpError


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://app.example")


def claims_event(groups="Recruiter", sub="u1"):
    claims = {"sub": sub}
    if groups is not None:
        claims["cognito:groups"] = groups
    return {"requestContext": {"authorizer": {"claims": claims}}}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Recruiter", {"Recruiter"}),
        ("[Recruiter]", {"Recruiter"}),
        ("[Admin Recruiter]", {"Admin", "Recruiter"}),
        ("Admin,Recruiter", {"Admin", "Recruiter"}),
        (["Admin"], {"Admin"}),
    ],
)
def test_group_claim_formats(raw, expected):
    c = authz.caller(claims_event(raw))
    assert c.groups == frozenset(expected) and c.sub == "u1"


@pytest.mark.parametrize("raw", [None, "", "[]", "Viewer", "[Viewer Guest]", "Recruiters", "SuperAdmin"])
def test_groupless_or_foreign_groups_are_403(raw):
    with pytest.raises(HttpError) as ei:
        authz.caller(claims_event(raw))
    assert ei.value.status == 403 and ei.value.code == "FORBIDDEN"


def test_missing_claims_fail_closed():
    for ev in ({}, {"requestContext": {}}, {"requestContext": {"authorizer": {"claims": {}}}}):
        with pytest.raises(HttpError) as ei:
            authz.caller(ev)
        assert ei.value.status == 403


def test_admin_flag_and_require_admin():
    assert authz.caller(claims_event("[Admin]")).is_admin
    r = authz.caller(claims_event("Recruiter"))
    assert not r.is_admin
    with pytest.raises(HttpError) as ei:
        authz.require_admin(r)
    assert ei.value.status == 403


def test_respond_shape_cors_and_decimal():
    from decimal import Decimal

    r = http.respond(201, {"score": Decimal("71.3"), "n": [Decimal("2")]})
    assert r["statusCode"] == 201
    assert r["headers"]["Access-Control-Allow-Origin"] == "https://app.example"
    assert r["headers"]["Cache-Control"] == "no-store" and r["headers"]["Vary"] == "Origin"
    assert json.loads(r["body"]) == {"score": 71.3, "n": [2.0]}


@pytest.mark.parametrize("body", [None, "", "{oops", "[1]", '"s"', "5"])
def test_json_body_rejects_non_objects(body):
    with pytest.raises(HttpError) as ei:
        http.json_body({"body": body})
    assert ei.value.status == 400


def test_json_body_base64_and_ok():
    import base64

    assert http.json_body({"body": '{"a":1}'}) == {"a": 1}
    b = base64.b64encode(b'{"a":2}').decode()
    assert http.json_body({"body": b, "isBase64Encoded": True}) == {"a": 2}
    with pytest.raises(HttpError):
        http.json_body({"body": "!!!", "isBase64Encoded": True})


def test_path_id_shapes():
    good = "job_" + "0" * 32
    assert http.path_id({"pathParameters": {"job_id": good}}, "job_id", "job") == good
    for bad in ("job_123", "JOB_" + "0" * 32, "job_" + "g" * 32, "", "cand_" + "0" * 32):
        with pytest.raises(HttpError) as ei:
            http.path_id({"pathParameters": {"job_id": bad}}, "job_id", "job")
        assert ei.value.status == 404
    with pytest.raises(HttpError):
        http.path_id({}, "job_id", "job")


def test_token_roundtrip_and_hardening():
    key = {"job_id": "job_1", "created_at": "2026-01-01T00:00:00Z"}
    assert http.decode_token(http.encode_token(key), {"job_id", "created_at"}) == key
    for bad in ("!!!", "e30", http.encode_token({"x": "1"}), http.encode_token({"job_id": 5})):
        with pytest.raises(HttpError) as ei:
            http.decode_token(bad, {"job_id"})
        assert ei.value.status == 400
    with pytest.raises(HttpError):
        http.decode_token(http.encode_token(["job_id"]), {"job_id"})


def test_api_handler_maps_errors_and_hides_internals(monkeypatch):
    monkeypatch.setattr(http, "_audit_api_failure", lambda e, x: None)
    ev = claims_event("Recruiter")

    @http.api_handler
    def ok(event, c):
        return 200, {"sub": c.sub}

    @http.api_handler
    def denied(event, c):
        raise HttpError(409, "NOT_SCORED", "nope", [{"field": "f", "issue": "i"}])

    @http.api_handler
    def boom(event, c):
        raise RuntimeError("table jobs-dev exploded with secret text")

    assert json.loads(ok(ev, None)["body"]) == {"sub": "u1"}
    r = denied(ev, None)
    assert r["statusCode"] == 409
    assert json.loads(r["body"])["error"] == {
        "code": "NOT_SCORED",
        "message": "nope",
        "details": [{"field": "f", "issue": "i"}],
    }
    r = boom(ev, None)
    assert r["statusCode"] == 500 and r["headers"]["Access-Control-Allow-Origin"] == "https://app.example"
    assert json.loads(r["body"]) == {
        "error": {"code": "INTERNAL", "message": "Something went wrong. Please try again."}
    }


def test_api_handler_403_carries_cors_headers():
    @http.api_handler
    def h(event, c):
        return 200, {}

    r = h(claims_event(None), None)
    assert r["statusCode"] == 403
    assert r["headers"]["Access-Control-Allow-Origin"] == "https://app.example"


def test_load_job_for_uses_consistent_read(monkeypatch):
    calls = []

    class FakeTable:
        def get_item(self, **kwargs):
            calls.append(kwargs)
            return {"Item": {"job_id": "job_1", "recruiter_id": "u1"}}

    monkeypatch.setattr(authz, "_JOBS", FakeTable())
    c = authz.Caller("u1", frozenset({"Recruiter"}))
    job = authz.load_job_for(c, "job_1")
    assert job["job_id"] == "job_1"
    assert len(calls) == 1
    assert calls[0].get("ConsistentRead") is True
