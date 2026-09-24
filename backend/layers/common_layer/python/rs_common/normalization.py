"""Deterministic dictionary/regex layer (docs/02-ingestion-pipeline.md §5.2,
§8.1's method-honesty table). Dictionaries only *normalize* a phrase already
found in the text, or *detect* whether a known phrase is present — they never
fabricate an entity (R-HON-07). Loaded lazily from RS_DATA_DIR (defaults to
/opt/data, where the CommonLayer build lands them) so importing this module
does no I/O at import time.
"""

from __future__ import annotations

import json
import os
import re
from functools import cache

DATA_DIR = os.environ.get("RS_DATA_DIR", "/opt/data")


@cache
def _load(name: str):
    with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def skills() -> list[str]:
    return _load("skills_dictionary")


def titles() -> list[str]:
    return _load("job_titles_dictionary")


def synonyms() -> dict:
    return _load("synonyms")


def title_families() -> list[list[str]]:
    return _load("title_families")


def case_sensitive_skills() -> dict[str, str]:
    return _load("case_sensitive_skills")


def normalize_skill(s: str) -> str:
    s = " ".join(s.lower().split())
    return synonyms()["skills"].get(s, s)


def normalize_title(t: str) -> str:
    t = " ".join(t.lower().split())
    return synonyms()["titles"].get(t, t)


def normalize_list(values) -> list[str]:
    """Dedupe + sort, dropping falsy entries — makes stored lists deterministic
    and diffable (R-DATA-07)."""
    return sorted({v for v in values if v})


def skill_patterns() -> list[str]:
    """Matcher patterns for the case-insensitive PhraseMatcher: the skills
    dictionary union the synonym keys (so e.g. "k8s" is actually matchable,
    not just normalizable once matched), minus any case-sensitive canonical
    (those are matched only by the separate case-sensitive matcher)."""
    cs = set(case_sensitive_skills().values())
    return sorted((set(skills()) | set(synonyms()["skills"])) - cs)


def title_patterns() -> list[str]:
    return sorted(set(titles()) | set(synonyms()["titles"]))


# Deterministic, NOT NLP (R-HON-06) — documented as such in every caller.
_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")


def extract_email(text: str) -> str | None:
    m = _EMAIL.search(text)
    return m.group(0).lower() if m else None


_MIN_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b",
    re.I,
)


def extract_min_years(text: str) -> int | None:
    """JD minimum-experience fallback when the recruiter didn't type it
    explicitly. Deterministic regex, NOT NLP (R-HON-06). Picks the smallest
    plausible mention (0 < n <= 30) to avoid e.g. "24/7" or a phone number
    fragment producing a nonsensical requirement."""
    vals = [int(m.group(1)) for m in _MIN_YEARS.finditer(text) if 0 < int(m.group(1)) <= 30]
    return min(vals) if vals else None
