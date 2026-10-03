"""Hand-written request validation (R-VAL-01..03, R-VAL-08/09) — no schema
library, per the "no new dependency without a decision entry" rule. Every
validator returns a normalized dict or raises HttpError(400) whose `details`
lists each offending field, so the UI can mark fields individually.

Explicit skills/titles are normalized with the SAME rs_common.normalization
functions the NLP uses (R-VAL-08), so an explicit "JS" and a resume's
"javascript" compare equal in scoring.
"""

from __future__ import annotations

import math
import re
from typing import Any

from rs_common import normalization as norm
from rs_common.http import HttpError

RESUME_EXT = {"pdf", "docx", "png", "jpg", "jpeg", "tiff"}
MAX_FILES_PER_REQUEST = 50
MAX_CANDIDATES_PER_JOB = 200
DEFAULT_THRESHOLD = 70

_CREATE_FIELDS = {
    "job_title",
    "jd",
    "required_skills",
    "required_titles",
    "min_experience_years",
    "shortlist_threshold",
    "resume_filenames",
}
_PATCH_FIELDS = {"required_skills", "required_titles", "min_experience_years", "shortlist_threshold"}
DECISIONS = {"shortlisted", "rejected", "pending"}


def _fail(details: list[dict]) -> HttpError:
    return HttpError(400, "VALIDATION_FAILED", "Some fields are invalid.", details)


def _has_control(s: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in s)


_PHISHING_RE = re.compile(
    r"(?i)(?:"
    r"https?://\S+"
    r"|ftp://\S+"
    r"|\bwww\.[a-z0-9.-]+\.[a-z]{2,}\b"
    r"|\b[a-z0-9.-]+\.[a-z]{2,}/[^\s]*"
    r"|\b[a-z0-9.-]+\.(?:com|org|biz|info|xyz|site|top|online)\b"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r")"
)


def _has_url_or_email(s: str) -> bool:
    return bool(_PHISHING_RE.search(s))


def ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _number(v: Any, lo: float, hi: float) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


def _text_list(v: Any, field: str, max_items: int, max_len: int, details: list[dict]) -> list[str] | None:
    if not isinstance(v, list):
        details.append({"field": field, "issue": "must_be_a_list"})
        return None
    if len(v) > max_items:
        details.append({"field": field, "issue": f"max_{max_items}_items"})
        return None
    out: list[str] = []
    for i, item in enumerate(v):
        if not isinstance(item, str) or not item.strip() or _has_control(item):
            details.append({"field": f"{field}[{i}]", "issue": "must_be_a_non_empty_string"})
        elif len(item.strip()) > max_len:
            details.append({"field": f"{field}[{i}]", "issue": f"max_{max_len}_chars"})
        else:
            out.append(item)
    return out


def _filename(v: Any, field: str, details: list[dict]) -> bool:
    if not isinstance(v, str) or not (1 <= len(v) <= 255) or _has_control(v):
        details.append({"field": field, "issue": "invalid_filename"})
        return False
    if ext_of(v) not in RESUME_EXT:
        details.append({"field": field, "issue": "unsupported_extension"})
        return False
    return True


def _requirements(body: dict, details: list[dict]) -> dict:
    """Shared by create and PATCH: the four recruiter-editable requirement fields."""
    out: dict = {}
    if "required_skills" in body:
        skills = _text_list(body["required_skills"], "required_skills", 50, 60, details)
        if skills is not None:
            out["required_skills"] = norm.normalize_list(norm.normalize_skill(s) for s in skills)
    if "required_titles" in body:
        titles = _text_list(body["required_titles"], "required_titles", 20, 80, details)
        if titles is not None:
            out["required_titles"] = norm.normalize_list(norm.normalize_title(t) for t in titles)
    if "min_experience_years" in body:
        v = body["min_experience_years"]
        if _number(v, 0, 50):
            out["min_experience_years"] = round(float(v), 1)
        else:
            details.append({"field": "min_experience_years", "issue": "must_be_0_to_50"})
    if "shortlist_threshold" in body:
        v = body["shortlist_threshold"]
        if _number(v, 0, 100):
            out["shortlist_threshold"] = round(float(v), 1)
        else:
            details.append({"field": "shortlist_threshold", "issue": "must_be_0_to_100"})
    return out


def create_job(body: dict) -> dict:
    details: list[dict] = [
        {"field": k, "issue": "unknown_field"} for k in sorted(set(body) - _CREATE_FIELDS)  # R-VAL-09
    ]
    title = body.get("job_title")
    if not isinstance(title, str) or not (1 <= len(title.strip()) <= 200) or _has_control(title):
        details.append({"field": "job_title", "issue": "must_be_1_to_200_chars"})
    elif _has_url_or_email(title):
        details.append({"field": "job_title", "issue": "must_not_contain_urls_or_emails"})

    jd_out: dict = {}
    jd = body.get("jd")
    if not isinstance(jd, dict):
        details.append({"field": "jd", "issue": "required_object"})
    else:
        source = jd.get("source")
        allowed = (
            {"source", "filename"}
            if source == "file"
            else {"source", "text"} if source == "text" else {"source"}
        )
        details += [{"field": f"jd.{k}", "issue": "unknown_field"} for k in sorted(set(jd) - allowed)]
        if source == "file":
            if _filename(jd.get("filename"), "jd.filename", details):
                jd_out = {"source": "file", "filename": jd["filename"], "ext": ext_of(jd["filename"])}
        elif source == "text":
            text = jd.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 50_000:
                details.append({"field": "jd.text", "issue": "must_be_1_to_50000_chars"})
            else:
                jd_out = {"source": "text", "text": text}
        elif source == "none":
            jd_out = {"source": "none"}
        else:
            details.append({"field": "jd.source", "issue": "must_be_file_text_or_none"})

    req = _requirements(body, details)

    filenames: list[str] = []
    raw_files = body.get("resume_filenames", [])
    if not isinstance(raw_files, list):
        details.append({"field": "resume_filenames", "issue": "must_be_a_list"})
    elif len(raw_files) > MAX_FILES_PER_REQUEST:
        raise HttpError(400, "LIMIT_EXCEEDED", f"At most {MAX_FILES_PER_REQUEST} files per request.")
    else:
        for i, fn in enumerate(raw_files):
            if _filename(fn, f"resume_filenames[{i}]", details):
                filenames.append(fn)

    if details:
        raise _fail(details)
    if jd_out["source"] == "none" and not req.get("required_skills"):
        raise HttpError(
            400,
            "REQUIREMENTS_REQUIRED",
            "Provide at least one required skill when no job description is given.",
        )
    if not req.get("required_skills"):
        req.pop("required_skills", None)  # an empty list means "not supplied": fall back to the JD
    return {
        "job_title": " ".join(title.split()),
        "jd": jd_out,
        "shortlist_threshold": req.pop("shortlist_threshold", DEFAULT_THRESHOLD),
        "requirements": req,
        "resume_filenames": filenames,
    }


def update_job(body: dict) -> dict:
    details: list[dict] = [{"field": k, "issue": "unknown_field"} for k in sorted(set(body) - _PATCH_FIELDS)]
    if not (set(body) & _PATCH_FIELDS):
        details.append({"field": "body", "issue": "at_least_one_field_required"})
    out = _requirements(body, details)
    if "required_skills" in body and not out.get("required_skills") and not details:
        details.append({"field": "required_skills", "issue": "must_not_be_empty"})
    if details:
        raise _fail(details)
    return out


def add_resumes(body: dict) -> list[str]:
    details: list[dict] = [
        {"field": k, "issue": "unknown_field"} for k in sorted(set(body) - {"resume_filenames"})
    ]
    raw = body.get("resume_filenames")
    if not isinstance(raw, list) or not raw:
        details.append({"field": "resume_filenames", "issue": "required_non_empty_list"})
        raise _fail(details)
    if len(raw) > MAX_FILES_PER_REQUEST:
        raise HttpError(400, "LIMIT_EXCEEDED", f"At most {MAX_FILES_PER_REQUEST} files per request.")
    names = []
    for i, fn in enumerate(raw):
        if _filename(fn, f"resume_filenames[{i}]", details):
            names.append(fn)
    if details:
        raise _fail(details)
    return names


def decision(body: dict) -> str:
    details = [{"field": k, "issue": "unknown_field"} for k in sorted(set(body) - {"decision"})]
    if not isinstance(body.get("decision"), str) or body["decision"] not in DECISIONS:
        details.append({"field": "decision", "issue": "must_be_shortlisted_rejected_or_pending"})
    if details:
        raise _fail(details)
    return body["decision"]
