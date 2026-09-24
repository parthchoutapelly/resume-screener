"""Public API shapes (Architecture.md §5.1). These are the ONLY place stored
items are turned into responses, so internal attributes (resume_s3_key,
ingest_started_at, upload_expires_at, recruiter internals) can't leak by
accident (R-AUTH-07)."""

from __future__ import annotations

from datetime import datetime

from rs_common import requirements as req
from rs_common import status as st


def job_row(job: dict, admin: bool = False) -> dict:
    row = {
        "job_id": job["job_id"],
        "job_title": job.get("job_title"),
        "jd_source": job.get("jd_source"),
        "parse_status": job.get("parse_status"),
        "scorable": req.scorable(job),
        "blocking_reason": req.blocking_reason(job),
        "created_at": job.get("created_at"),
    }
    if admin:
        row["recruiter_id"] = job.get("recruiter_id")
    return row


def job_view(job: dict) -> dict:
    eff = req.effective(job)
    return {
        "job_id": job["job_id"],
        "job_title": job.get("job_title"),
        "jd_source": job.get("jd_source"),
        "parse_status": job.get("parse_status"),
        "error_code": job.get("error_code"),
        "effective": {
            "skills": eff.skills,
            "titles": eff.titles,
            "min_experience_years": eff.min_experience_years,
        },
        "sources": req.sources(job),
        "derived": {
            "skills": list(job.get("derived_skills", [])),
            "titles": list(job.get("derived_titles", [])),
            "min_experience_years": job.get("derived_min_experience_years"),
        },
        "shortlist_threshold": job.get("shortlist_threshold", 70),
        "requirements_confirmed": bool(job.get("requirements_confirmed")),
        "scorable": req.scorable(job),
        "blocking_reason": req.blocking_reason(job),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


def experience_basis(c: dict) -> str:
    if c.get("total_experience_years") is None:
        return "unknown"
    return "estimated" if c.get("experience_estimated") else "computed"


def candidate_view(c: dict, job: dict, now: datetime) -> dict:
    display, error_code = st.display_status(c, job, now)
    scored = c.get("score_status") == "scored"
    return {
        "candidate_id": c["candidate_id"],
        "original_filename": c.get("original_filename"),
        "display_status": display,
        "error_code": error_code,
        "name": c.get("name"),
        "email": c.get("email"),
        "skills": list(c.get("skills", [])),
        "titles_held": list(c.get("titles_held", [])),
        "employers": list(c.get("employers", [])),
        "total_experience_years": c.get("total_experience_years"),
        "experience_basis": experience_basis(c),
        "match_score": c.get("match_score") if scored else None,
        "skills_score": c.get("skills_score") if scored else None,
        "title_score": c.get("title_score") if scored else None,
        "experience_score": c.get("experience_score") if scored else None,
        "matched_skills": list(c.get("matched_skills", [])) if scored else [],
        "missing_skills": list(c.get("missing_skills", [])) if scored else [],
        "title_match": (
            {
                "type": c.get("title_match_type"),
                "held": c.get("title_match_held"),
                "required": c.get("title_match_required"),
            }
            if scored
            else None
        ),
        "recommended": bool(c.get("shortlist_candidate")) if scored else None,
        "decision": c.get("decision", "pending"),
        "notification_status": c.get("notification_status"),
        "file_type": c.get("file_type"),
        "updated_at": c.get("updated_at"),
    }
