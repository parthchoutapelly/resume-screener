"""Unit tests for rs_common.uploads and rs_common.views.

uploads.py covers:
  - jd_key / resume_key: deterministic key construction
  - safe_download_name: hostile filename sanitisation
  - new_placeholder: correct initial field values
  - CONTENT_TYPES: all expected extensions present
  - UPLOAD_TTL_SECONDS / MAX_UPLOAD_BYTES / RESUME_URL_TTL constants

views.py covers:
  - job_row: base shape + admin flag adds recruiter_id
  - job_view: effective/sources/derived/scorable shape
  - experience_basis: computed / estimated / unknown branches
  - candidate_view: pre-score vs scored shapes, internal field exclusion
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

os.environ.setdefault("UPLOAD_BUCKET", "test-bucket")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("CANDIDATES_TABLE", "candidates-test")
os.environ.setdefault("FAILED_JOBS_TABLE", "failed-jobs-test")
os.environ.setdefault("SES_SENDER_ADDRESS", "no-reply@example.com")
os.environ.setdefault("ALLOWED_ORIGIN", "http://localhost:5173")
os.environ.setdefault("RS_DATA_DIR", "backend/data")


# ===========================================================================
# uploads.py
# ===========================================================================


def test_jd_key_shape():
    from rs_common.uploads import jd_key

    k = jd_key("job_" + "a" * 32, "pdf")
    assert k.startswith("jd-uploads/")
    assert k.endswith(".pdf")
    assert "job_" + "a" * 32 in k


def test_resume_key_shape():
    from rs_common.uploads import resume_key

    k = resume_key("job_" + "a" * 32, "cand_" + "b" * 32, "docx")
    assert k.startswith("resume-uploads/")
    assert k.endswith(".docx")
    assert "resume" in k


def test_content_types_has_expected_extensions():
    from rs_common.uploads import CONTENT_TYPES

    for ext in ("pdf", "png", "jpg", "jpeg", "tiff", "docx", "txt"):
        assert ext in CONTENT_TYPES, f"CONTENT_TYPES missing extension: {ext}"


def test_upload_constants_within_bounds():
    from rs_common.uploads import EXPORT_URL_TTL, MAX_UPLOAD_BYTES, RESUME_URL_TTL, UPLOAD_TTL_SECONDS

    assert 60 <= UPLOAD_TTL_SECONDS <= 3600
    assert MAX_UPLOAD_BYTES == 10_485_760, "Max 10 MiB per R-SEC-03"
    assert RESUME_URL_TTL == 60, "Resume URL TTL must be 60 s (Architecture §3.1)"
    assert EXPORT_URL_TTL > 0


def test_safe_download_name_strips_hostile_chars():
    from rs_common.uploads import safe_download_name

    # Path traversal, header injection, unicode
    assert safe_download_name("../../etc/passwd") == "etc_passwd"
    # Trailing separators are stripped; the exact output depends on strip("._")
    result = safe_download_name("resume; rm -rf /")
    assert result.startswith("resume")
    assert ";" not in result and "/" not in result
    assert safe_download_name("José Résumé.pdf") == "Jos_R_sum_.pdf"


def test_safe_download_name_truncates():
    from rs_common.uploads import safe_download_name

    long = "a" * 200 + ".pdf"
    assert len(safe_download_name(long)) <= 100


def test_safe_download_name_empty_fallback():
    from rs_common.uploads import safe_download_name

    assert safe_download_name("....") == "resume"
    assert safe_download_name("") == "resume"


def test_new_placeholder_shape():
    from rs_common.uploads import new_placeholder

    now = "2026-09-24T12:00:00Z"
    expires = "2026-09-24T12:15:00Z"
    p = new_placeholder("job_" + "a" * 32, "resume.pdf", "pdf", now, expires)
    assert p["original_filename"] == "resume.pdf"
    assert p["parse_status"] == "pending"
    assert p["score_status"] == "pending"
    assert p["decision"] == "pending"
    assert p["created_at"] == now
    assert p["upload_expires_at"] == expires
    assert p["resume_s3_key"].endswith(".pdf")
    # Internal fields must be present (used by extraction fan-out)
    assert "candidate_id" in p
    assert "job_id" in p


def test_new_placeholder_different_ext():
    from rs_common.uploads import new_placeholder

    now = expires = "2026-09-24T12:00:00Z"
    p = new_placeholder("job_" + "a" * 32, "cv.docx", "docx", now, expires)
    assert p["resume_s3_key"].endswith(".docx")


# ===========================================================================
# views.py
# ===========================================================================


def _base_job(**overrides):
    return {
        "job_id": "job_" + "a" * 32,
        "job_title": "Backend Engineer",
        "jd_source": "file",
        "parse_status": "parsed",
        "recruiter_id": "sub-xyz",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:05:00Z",
        "required_skills": ["python", "aws"],
        "required_titles": ["backend engineer"],
        "min_experience_years": 3.0,
        "shortlist_threshold": 70,
        **overrides,
    }


def test_job_row_base_shape():
    from rs_common.views import job_row

    job = _base_job()
    row = job_row(job)
    assert "job_id" in row
    assert "job_title" in row
    assert "scorable" in row
    assert "blocking_reason" in row
    assert "recruiter_id" not in row  # not admin


def test_job_row_admin_adds_recruiter_id():
    from rs_common.views import job_row

    job = _base_job()
    row = job_row(job, admin=True)
    assert row["recruiter_id"] == "sub-xyz"


def test_job_view_shape():
    from rs_common.views import job_view

    job = _base_job()
    view = job_view(job)
    assert "effective" in view
    assert "sources" in view
    assert "derived" in view
    assert "shortlist_threshold" in view
    assert "requirements_confirmed" in view
    assert "scorable" in view
    assert "blocking_reason" in view
    # Internal fields must NOT appear in the view (R-AUTH-07)
    assert "recruiter_id" not in view
    assert "resume_s3_key" not in view
    assert "ingest_started_at" not in view


def test_job_view_effective_skills_from_explicit():
    from rs_common.views import job_view

    job = _base_job(required_skills=["aws", "python"])
    view = job_view(job)
    assert view["effective"]["skills"] == ["aws", "python"]


def test_experience_basis_computed():
    from rs_common.views import experience_basis

    c = {"total_experience_years": Decimal("4.0"), "experience_estimated": False}
    assert experience_basis(c) == "computed"


def test_experience_basis_estimated():
    from rs_common.views import experience_basis

    c = {"total_experience_years": Decimal("2.0"), "experience_estimated": True}
    assert experience_basis(c) == "estimated"


def test_experience_basis_unknown():
    from rs_common.views import experience_basis

    assert experience_basis({}) == "unknown"
    assert experience_basis({"total_experience_years": None}) == "unknown"


def _base_cand(**overrides):
    return {
        "candidate_id": "cand_" + "b" * 32,
        "job_id": "job_" + "a" * 32,
        "original_filename": "alice.pdf",
        "parse_status": "parsed",
        "score_status": "scored",
        "decision": "pending",
        "skills": ["python", "aws"],
        "titles_held": ["backend engineer"],
        "employers": ["Acme Corp"],
        "name": "Alice Johnson",
        "email": "alice@example-mail.test",
        "match_score": Decimal("85.0"),
        "skills_score": Decimal("100.0"),
        "title_score": Decimal("60.0"),
        "experience_score": Decimal("100.0"),
        "matched_skills": ["python", "aws"],
        "missing_skills": ["dynamodb"],
        "title_match_type": "exact",
        "title_match_held": "backend engineer",
        "title_match_required": "backend engineer",
        "shortlist_candidate": True,
        "total_experience_years": Decimal("6.0"),
        "experience_estimated": False,
        "updated_at": "2026-09-01T10:05:00Z",
        **overrides,
    }


NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


def test_candidate_view_scored_shape():
    from rs_common.views import candidate_view

    cand = _base_cand()
    job = _base_job(shortlist_threshold=70)
    view = candidate_view(cand, job, NOW)

    assert view["display_status"] == "scored"
    assert view["match_score"] == Decimal("85.0")
    assert view["skills_score"] == Decimal("100.0")
    assert view["title_score"] == Decimal("60.0")
    assert view["experience_score"] == Decimal("100.0")
    assert view["matched_skills"] == ["python", "aws"]
    assert view["missing_skills"] == ["dynamodb"]
    assert view["title_match"]["type"] == "exact"
    assert view["recommended"] is True
    assert view["experience_basis"] == "computed"


def test_candidate_view_internal_fields_excluded():
    """Internal storage fields must never appear in API views (R-AUTH-07)."""
    from rs_common.views import candidate_view

    cand = {
        **_base_cand(),
        "resume_s3_key": "resume-uploads/xxx",
        "ingest_started_at": "2026-09-01T10:00:00Z",
        "upload_expires_at": "2026-09-01T10:15:00Z",
    }
    job = _base_job()
    view = candidate_view(cand, job, NOW)
    assert "resume_s3_key" not in view
    assert "ingest_started_at" not in view
    assert "upload_expires_at" not in view


def test_candidate_view_pre_score_hides_scores():
    """Before scoring, all score fields must be None / empty."""
    from rs_common.views import candidate_view

    cand = _base_cand(score_status="pending", parse_status="pending")
    job = _base_job()
    view = candidate_view(cand, job, NOW)
    assert view["match_score"] is None
    assert view["skills_score"] is None
    assert view["title_match"] is None
    assert view["recommended"] is None
    assert view["matched_skills"] == []
    assert view["missing_skills"] == []


def test_candidate_view_error_state():
    from rs_common.views import candidate_view

    cand = _base_cand(parse_status="error", score_status="pending", error_code="unreadable_document")
    job = _base_job()
    view = candidate_view(cand, job, NOW)
    assert view["display_status"] == "error"
    assert view["error_code"] == "unreadable_document"


def test_candidate_view_awaiting_jd():
    from rs_common.views import candidate_view

    # parsed but job JD not yet uploaded (no required skills derived yet and awaiting_jd)
    cand = _base_cand(score_status="pending")
    job = _base_job(jd_source="file", parse_status="pending")  # JD parse_status pending = awaiting_jd
    view = candidate_view(cand, job, NOW)
    assert view["display_status"] in ("awaiting_jd", "awaiting_requirements", "scoring")
