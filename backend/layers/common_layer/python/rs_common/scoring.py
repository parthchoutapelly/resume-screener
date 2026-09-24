"""Scoring engine, version v1 (docs/Architecture.md §7.3, Rules R-BUS-02/09/10).

Pure functions: no I/O, no clock. Reads ONLY a candidate's skills,
titles_held and total_experience_years plus the job's effective requirements
(R-BUS-09) — never name, email, employers, or filename. Inputs may carry
DynamoDB Decimals; everything is converted to float for arithmetic and the
caller converts back with to_decimal() before writing (R-DATA-01).
"""

from __future__ import annotations

from dataclasses import dataclass

from rs_common import normalization as norm
from rs_common.requirements import effective

W_SKILLS, W_TITLE, W_EXP = 0.5, 0.3, 0.2
SCORING_VERSION = "v1"


@dataclass(frozen=True)
class ScoreResult:
    match_score: float
    skills_score: float
    title_score: float
    experience_score: float
    matched_skills: list[str]
    missing_skills: list[str]
    title_match_type: str
    title_match_held: str | None
    title_match_required: str | None
    recommended: bool


def score(candidate: dict, job: dict) -> ScoreResult:
    """Precondition: scorable(job) — an empty skill requirement must never
    yield a skills score of 100 (R-BUS-04)."""
    eff = effective(job)
    req, have = set(eff.skills), set(candidate.get("skills", []))
    matched, missing = sorted(req & have), sorted(req - have)
    s_skills = len(matched) / len(req) * 100
    s_title, t_type, t_held, t_req = score_title(candidate.get("titles_held", []), eff.titles)
    yrs = candidate.get("total_experience_years")
    s_exp = score_experience(None if yrs is None else float(yrs), eff.min_experience_years)
    # Weighted from the UNROUNDED sub-scores; rounding is for storage only (R-BUS-02).
    match = W_SKILLS * s_skills + W_TITLE * s_title + W_EXP * s_exp
    match_r = round(match, 1)
    return ScoreResult(
        match_r,
        round(s_skills, 1),
        round(s_title, 1),
        round(s_exp, 1),
        matched,
        missing,
        t_type,
        t_held,
        t_req,
        match_r >= float(job.get("shortlist_threshold", 70)),  # R-BUS-13: stored 1-dp value
    )


def score_title(held, required):
    if not required:
        return 100.0, "not_required", None, None
    held_n = sorted({norm.normalize_title(t) for t in held})
    req_n = sorted({norm.normalize_title(t) for t in required})
    for r in req_n:
        if r in held_n:
            return 100.0, "exact", r, r
    for r in req_n:
        for h in held_n:
            if any(h in fam and r in fam for fam in norm.title_families()):
                return 60.0, "related", h, r
    return 0.0, "none", None, None


def score_experience(years: float | None, min_years: float) -> float:
    if min_years <= 0:
        return 100.0
    if years is None:
        return 0.0  # shown as "Unknown" in the UI, never as a real 0 (R-HON-09)
    return min(100.0, years / min_years * 100)
