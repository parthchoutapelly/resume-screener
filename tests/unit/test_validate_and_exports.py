"""Request validation (R-VAL-01..03/08/09) and CSV formula escaping (R-SEC-09)."""

import pytest

from rs_common import exports, validate
from rs_common.http import HttpError


def ok(**kw):
    return {"job_title": "Backend Engineer", "jd": {"source": "none"}, "required_skills": ["python"], **kw}


def fields(err: HttpError) -> set[str]:
    return {d["field"] for d in err.details}


def test_minimal_valid_none_jd():
    out = validate.create_job(ok())
    assert out["jd"] == {"source": "none"}
    assert out["shortlist_threshold"] == 70
    assert out["requirements"] == {"required_skills": ["python"]}
    assert out["resume_filenames"] == []


def test_explicit_lists_are_normalized_deduped_sorted_r_val_08():
    out = validate.create_job(
        ok(required_skills=["  Python ", "python", "AWS"], required_titles=["Backend  Engineer"])
    )
    assert out["requirements"]["required_skills"] == ["aws", "python"]
    assert out["requirements"]["required_titles"] == ["backend engineer"]


def test_file_and_text_jd():
    f = validate.create_job(ok(jd={"source": "file", "filename": "JD.PDF"}))
    assert f["jd"] == {"source": "file", "filename": "JD.PDF", "ext": "pdf"}
    t = validate.create_job(ok(jd={"source": "text", "text": "We need a Python dev"}))
    assert t["jd"]["source"] == "text"


@pytest.mark.parametrize(
    "body,field",
    [
        (ok(surprise=1), "surprise"),  # R-VAL-09
        (ok(job_title=""), "job_title"),
        (ok(job_title="x" * 201), "job_title"),
        (ok(job_title="a\nb"), "job_title"),
        (ok(jd="file"), "jd"),
        (ok(jd={"source": "ftp"}), "jd.source"),
        (ok(jd={"source": "file"}), "jd.filename"),
        (ok(jd={"source": "file", "filename": "x.exe"}), "jd.filename"),
        (ok(jd={"source": "file", "filename": "x.pdf", "extra": 1}), "jd.extra"),
        (ok(jd={"source": "text", "text": "   "}), "jd.text"),
        (ok(jd={"source": "text", "text": "x" * 50_001}), "jd.text"),
        (ok(shortlist_threshold=101), "shortlist_threshold"),
        (ok(shortlist_threshold=-1), "shortlist_threshold"),
        (ok(shortlist_threshold=True), "shortlist_threshold"),
        (ok(min_experience_years=51), "min_experience_years"),
        (ok(min_experience_years="3"), "min_experience_years"),
        (ok(min_experience_years=float("nan")), "min_experience_years"),
        (ok(required_skills="python"), "required_skills"),
        (ok(required_skills=["x"] * 51), "required_skills"),
        (ok(required_skills=["x" * 61]), "required_skills[0]"),
        (ok(required_skills=[""]), "required_skills[0]"),
        (ok(required_skills=[5]), "required_skills[0]"),
        (ok(required_titles=["t"] * 21), "required_titles"),
        (ok(required_titles=["t" * 81]), "required_titles[0]"),
        (ok(resume_filenames=["a.pdf", "b.exe"]), "resume_filenames[1]"),
        (ok(resume_filenames=["x" * 252 + ".pdf"]), "resume_filenames[0]"),
        (ok(resume_filenames="a.pdf"), "resume_filenames"),
        ({"jd": {"source": "none"}, "required_skills": ["python"]}, "job_title"),
        ({"job_title": "x", "required_skills": ["python"]}, "jd"),
    ],
)
def test_create_validation_rejects(body, field):
    with pytest.raises(HttpError) as ei:
        validate.create_job(body)
    assert ei.value.status == 400 and ei.value.code == "VALIDATION_FAILED"
    assert field in fields(ei.value)


def test_multiple_errors_reported_together():
    with pytest.raises(HttpError) as ei:
        validate.create_job(ok(job_title="", shortlist_threshold=500))
    assert {"job_title", "shortlist_threshold"} <= fields(ei.value)


def test_none_jd_without_skills_is_requirements_required():
    for skills in ({}, {"required_skills": []}):
        body = {"job_title": "x", "jd": {"source": "none"}, **skills}
        with pytest.raises(HttpError) as ei:
            validate.create_job(body)
        assert ei.value.code == "REQUIREMENTS_REQUIRED"


def test_empty_skills_with_a_jd_means_not_supplied():
    out = validate.create_job(ok(jd={"source": "file", "filename": "a.pdf"}, required_skills=[]))
    assert "required_skills" not in out["requirements"]


def test_empty_titles_is_kept_as_explicit_no_requirement():
    out = validate.create_job(ok(required_titles=[]))
    assert out["requirements"]["required_titles"] == []


def test_more_than_50_files_is_limit_exceeded():
    with pytest.raises(HttpError) as ei:
        validate.create_job(ok(resume_filenames=[f"{i}.pdf" for i in range(51)]))
    assert ei.value.code == "LIMIT_EXCEEDED"
    assert (
        len(validate.create_job(ok(resume_filenames=[f"{i}.pdf" for i in range(50)]))["resume_filenames"])
        == 50
    )


def test_update_job_subset_and_rules():
    assert validate.update_job({"required_titles": []}) == {"required_titles": []}
    assert validate.update_job({"min_experience_years": 0, "shortlist_threshold": 0}) == {
        "min_experience_years": 0.0,
        "shortlist_threshold": 0.0,
    }
    for bad in ({}, {"required_skills": []}, {"job_title": "x"}, {"shortlist_threshold": 101}):
        with pytest.raises(HttpError) as ei:
            validate.update_job(bad)
        assert ei.value.code == "VALIDATION_FAILED"


def test_add_resumes_and_decision():
    assert validate.add_resumes({"resume_filenames": ["a.docx"]}) == ["a.docx"]
    for bad in ({}, {"resume_filenames": []}, {"resume_filenames": ["a.pdf"], "x": 1}):
        with pytest.raises(HttpError):
            validate.add_resumes(bad)
    with pytest.raises(HttpError) as ei:
        validate.add_resumes({"resume_filenames": ["a.pdf"] * 51})
    assert ei.value.code == "LIMIT_EXCEEDED"
    for d in ("shortlisted", "rejected", "pending"):
        assert validate.decision({"decision": d}) == d
    for bad in ({}, {"decision": "maybe"}, {"decision": ["pending"]}, {"decision": "pending", "x": 1}):
        with pytest.raises(HttpError):
            validate.decision(bad)


def test_ext_of():
    assert validate.ext_of("a.b.PDF") == "pdf" and validate.ext_of("noext") == ""


@pytest.mark.parametrize("cell", ["=1+1", "+SUM(A1)", "-2", "@cmd", "\tx", "\rx"])
def test_csv_safe_prefixes_formula_starters(cell):
    assert exports.csv_safe(cell) == "'" + cell


def test_csv_safe_leaves_normal_values():
    assert exports.csv_safe("Jane Doe") == "Jane Doe"
    assert exports.csv_safe(None) == ""
    assert exports.csv_safe(4.5) == "4.5"


def test_build_csv_columns_bom_and_escaping():
    data = exports.build_csv(
        [
            {
                "name": "=HYPERLINK(evil)",
                "email": "a@b.com",
                "skills": ["aws", "python"],
                "titles_held": ["backend developer"],
                "total_experience_years": 4.0,
                "match_score": 71.3,
                "decided_at": "2026-09-24T10:00:00Z",
            },
            {"name": "José Ñandú", "skills": []},
        ]
    )
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    lines = text.split("\r\n")
    assert lines[0] == "name,email,skills,titles_held,total_experience_years,match_score,decided_at"
    assert lines[1].startswith("'=HYPERLINK(evil),a@b.com,aws; python,backend developer,4.0,71.3,")
    assert "José Ñandú" in lines[2]
