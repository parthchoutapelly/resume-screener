"""Effective job requirements and scorability (docs/Architecture.md §7.1,
Rules R-BUS-03/04). Single implementation shared by scoreMatch, the API views,
and status derivation, so "is this job scorable?" can never disagree between
the component that scores and the one that explains why nothing was scored.

Attribute *absence* carries meaning here: `required_titles` present-but-empty
means "no title requirement", while absent means "recruiter didn't say, fall
back to what the JD derived". That is why these helpers test membership
(`in job`) rather than truthiness for titles and min experience.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Effective:
    skills: list[str]
    titles: list[str]
    min_experience_years: float


def effective(job: dict) -> Effective:
    skills = (
        list(job["required_skills"]) if job.get("required_skills") else list(job.get("derived_skills", []))
    )
    titles = list(job["required_titles"]) if "required_titles" in job else list(job.get("derived_titles", []))
    if "min_experience_years" in job:
        min_exp = job["min_experience_years"]
    else:
        min_exp = job.get("derived_min_experience_years", 0)
    return Effective(sorted(skills), sorted(titles), float(min_exp))


def sources(job: dict) -> dict:
    def src(explicit_present: bool, derived_present: bool) -> str | None:
        return "recruiter" if explicit_present else ("jd" if derived_present else None)

    return {
        "skills": src(bool(job.get("required_skills")), bool(job.get("derived_skills"))),
        "titles": src("required_titles" in job, "derived_titles" in job),
        "min_experience_years": src("min_experience_years" in job, "derived_min_experience_years" in job),
    }


def blocking_reason(job: dict) -> str | None:
    confirmed = bool(job.get("requirements_confirmed"))
    status = job.get("parse_status")
    if status == "pending" and not confirmed:
        return "awaiting_jd"
    if status == "error" and not confirmed:
        return "jd_failed"
    if not effective(job).skills:
        return "no_required_skills"
    return None


def scorable(job: dict) -> bool:
    return blocking_reason(job) is None
