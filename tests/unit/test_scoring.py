"""Scoring engine v1 (Architecture.md §7.3, R-BUS-02/09/10/13)."""

from decimal import Decimal

import pytest

from rs_common import scoring
from rs_common.scoring import score, score_experience, score_title

JOB = {
    "required_skills": ["python", "aws", "dynamodb"],
    "required_titles": ["backend engineer"],
    "min_experience_years": 3,
    "shortlist_threshold": 70,
}


def cand(**kw):
    return {
        "skills": ["python", "aws", "sql"],
        "titles_held": ["backend developer"],
        "total_experience_years": 4.0,
        **kw,
    }


def test_worked_example_is_71_3():
    r = score(cand(), JOB)
    assert (r.skills_score, r.title_score, r.experience_score) == (66.7, 60.0, 100.0)
    assert r.match_score == 71.3
    assert r.matched_skills == ["aws", "python"] and r.missing_skills == ["dynamodb"]
    assert (r.title_match_type, r.title_match_held, r.title_match_required) == (
        "related",
        "backend developer",
        "backend engineer",
    )
    assert r.recommended is True


def test_match_is_computed_from_unrounded_subscores():
    # skills 2/3 = 66.666...; 0.5*66.666 + 18 + 20 = 71.333 -> 71.3; had we used the
    # rounded 66.7 the sum would be 71.35 and round to 71.4 (banker's) / 71.3 — pin the intent.
    unrounded = 0.5 * (2 / 3 * 100) + 0.3 * 60 + 0.2 * 100
    assert score(cand(), JOB).match_score == round(unrounded, 1)


@pytest.mark.parametrize(
    "have,expected",
    [([], 0.0), (["python"], 33.3), (["python", "aws"], 66.7), (["python", "aws", "dynamodb", "x"], 100.0)],
)
def test_skill_overlap_zero_partial_full(have, expected):
    r = score(cand(skills=have, titles_held=[], total_experience_years=0), {**JOB, "required_titles": []})
    assert r.skills_score == expected


@pytest.mark.parametrize(
    "held,required,want",
    [
        (["backend engineer"], ["backend engineer"], (100.0, "exact")),
        (["backend developer"], ["backend engineer"], (60.0, "related")),
        (["chef"], ["backend engineer"], (0.0, "none")),
        ([], ["backend engineer"], (0.0, "none")),
        (["chef"], [], (100.0, "not_required")),
        (["swe"], ["software engineer"], (100.0, "exact")),  # abbreviation normalized via synonyms
    ],
)
def test_title_exact_related_none_not_required(held, required, want):
    s, t, _, _ = score_title(held, required)
    assert (s, t) == want


def test_title_uses_best_match_across_all_held_titles():
    s, t, held, _ = score_title(["chef", "backend engineer", "backend developer"], ["backend engineer"])
    assert (s, t, held) == (100.0, "exact", "backend engineer")


def test_no_title_requirement_leaves_held_and_required_none():
    assert score_title(["x"], []) == (100.0, "not_required", None, None)


def test_experience_rules():
    assert score_experience(4.0, 0) == 100.0  # no minimum
    assert score_experience(None, 0) == 100.0  # no minimum beats unknown
    assert score_experience(None, 3) == 0.0  # unknown never counts as met
    assert score_experience(1.5, 3) == 50.0
    assert score_experience(10, 3) == 100.0  # capped


def test_unknown_years_absent_attribute():
    c = cand()
    c.pop("total_experience_years")
    assert score(c, JOB).experience_score == 0.0


def test_decimal_inputs_from_dynamodb():
    c = cand(total_experience_years=Decimal("1.5"))
    j = {**JOB, "min_experience_years": Decimal("3"), "shortlist_threshold": Decimal("70")}
    r = score(c, j)
    assert r.experience_score == 50.0
    assert isinstance(r.match_score, float)


@pytest.mark.parametrize("threshold,rec", [(71.3, True), (71.4, False), (0, True), (100, False)])
def test_recommended_uses_stored_one_dp_value_with_gte(threshold, rec):
    assert score(cand(), {**JOB, "shortlist_threshold": threshold}).recommended is rec


def test_threshold_defaults_to_70():
    j = {k: v for k, v in JOB.items() if k != "shortlist_threshold"}
    assert score(cand(), j).recommended is True


def test_scoring_reads_only_permitted_fields():
    # R-BUS-09: name/email/employers must not influence the result.
    base = score(cand(), JOB)
    noisy = score(cand(name="Zed", email="z@z.com", employers=["Google"], original_filename="x.pdf"), JOB)
    assert base == noisy


def test_scoring_version_constant():
    assert scoring.SCORING_VERSION == "v1"
