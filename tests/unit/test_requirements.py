"""Effective requirements + scorability (Architecture.md §7.1, R-BUS-03/04)."""

import itertools
from decimal import Decimal

import pytest

from rs_common.requirements import blocking_reason, effective, scorable, sources


def job(**kw):
    return {"job_id": "j", **kw}


def test_explicit_wins_field_by_field():
    j = job(
        required_skills=["python"],
        derived_skills=["java", "aws"],
        required_titles=["data engineer"],
        derived_titles=["backend engineer"],
        min_experience_years=Decimal("2"),
        derived_min_experience_years=Decimal("5"),
    )
    e = effective(j)
    assert (e.skills, e.titles, e.min_experience_years) == (["python"], ["data engineer"], 2.0)
    assert sources(j) == {"skills": "recruiter", "titles": "recruiter", "min_experience_years": "recruiter"}


def test_fallback_to_derived_and_sorting():
    e = effective(
        job(derived_skills=["sql", "aws"], derived_titles=["b", "a"], derived_min_experience_years=4)
    )
    assert e.skills == ["aws", "sql"] and e.titles == ["a", "b"] and e.min_experience_years == 4.0
    assert sources(job(derived_skills=["x"]))["skills"] == "jd"


def test_empty_required_skills_falls_back_but_empty_required_titles_means_no_requirement():
    j = job(
        required_skills=[], derived_skills=["python"], required_titles=[], derived_titles=["backend engineer"]
    )
    e = effective(j)
    assert e.skills == ["python"]  # [] skills = not supplied
    assert e.titles == []  # [] titles = explicitly no title requirement
    assert sources(j)["titles"] == "recruiter"


def test_nothing_anywhere():
    e = effective(job())
    assert (e.skills, e.titles, e.min_experience_years) == ([], [], 0.0)
    assert sources(job()) == {"skills": None, "titles": None, "min_experience_years": None}


@pytest.mark.parametrize(
    "parse_status,confirmed,has_skills,expected",
    [
        (status, confirmed, skills, None)  # placeholder, real expectation computed below
        for status, confirmed, skills in itertools.product(
            ["pending", "parsed", "error", "not_applicable", None], [False, True], [False, True]
        )
    ],
)
def test_blocking_reason_full_matrix(parse_status, confirmed, has_skills, expected):
    j = job(requirements_confirmed=confirmed, derived_skills=["python"] if has_skills else [])
    if parse_status:
        j["parse_status"] = parse_status
    if parse_status == "pending" and not confirmed:
        want = "awaiting_jd"
    elif parse_status == "error" and not confirmed:
        want = "jd_failed"
    elif not has_skills:
        want = "no_required_skills"
    else:
        want = None
    assert blocking_reason(j) == want
    assert scorable(j) is (want is None)


def test_recruiter_skills_on_pending_jd_still_wait_for_the_jd():
    # Explicit skills alone don't make a job scorable while its JD is still parsing.
    assert blocking_reason(job(parse_status="pending", required_skills=["python"])) == "awaiting_jd"


def test_confirming_rescues_a_failed_jd():
    j = job(parse_status="error", required_skills=["python"], requirements_confirmed=True)
    assert scorable(j)
