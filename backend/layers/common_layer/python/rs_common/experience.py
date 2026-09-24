"""Deterministic experience-years computation (docs/02-ingestion-pipeline.md
§8.3, decision D-27). Pure and spaCy-free by design, so it's unit-testable
without loading a model — the caller (nlpProcessing) supplies spaCy's DATE
entity spans only as a corroboration signal for text outside a detected
"Experience" section.

This is arithmetic ON TOP of NLP output, not NLP itself (Details.md §6 /
R-HON-06): the section/date-range detection here is regex, not a learned
model. It replaced an earlier "pair consecutive DATE entities" heuristic that
broke on a single "2019-2021" entity, a missing "Present", overlapping jobs,
and education-section dates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_EXP_HEADERS = {
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "employment history",
    "work history",
    "career history",
}
_STOP_HEADERS = {
    "education",
    "academic",
    "qualifications",
    "projects",
    "skills",
    "certifications",
    "achievements",
    "awards",
    "publications",
    "interests",
    "summary",
    "profile",
    "references",
}

_MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_MONTH_YEAR = rf"{_MONTH_RE}\s*'?\d{{2,4}}"
_NUMERIC_MONTH_YEAR = r"\d{1,2}[/.\-]\d{4}"
_SHORT_YEAR = r"'\d{2}(?!\d)"
_YEAR_ONLY = r"(?<!\d)\d{4}(?!\d)"
_DATE_TOKEN = rf"(?:{_MONTH_YEAR}|{_NUMERIC_MONTH_YEAR}|{_SHORT_YEAR}|{_YEAR_ONLY})"
_PRESENT = r"(?:present|current|now|till\s+date|to\s+date|ongoing)"
_SEP = r"(?:-|–|—|to|until|till)"

_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*{_SEP}\s*(?P<end>{_DATE_TOKEN}|{_PRESENT})",
    re.IGNORECASE,
)
_PRESENT_WORDS = {"present", "current", "now", "till date", "to date", "ongoing"}

MAX_SPAN_DAYS = 50 * 365.25
MIN_START_YEAR = 1960


@dataclass(frozen=True)
class Experience:
    years: float | None
    basis: str  # "computed" | "estimated" | "unknown"


@dataclass(frozen=True)
class _ParsedToken:
    year: int
    month: int | None  # None => year-only precision


def _expand_year(year_str: str, today: date) -> int:
    if len(year_str) == 4:
        return int(year_str)
    yy = int(year_str)
    current_yy = today.year % 100
    return 2000 + yy if yy <= current_yy else 1900 + yy


def _parse_token(token: str, today: date) -> _ParsedToken | None:
    token = " ".join(token.strip().split())
    m = re.match(rf"^(?P<mon>{_MONTH_RE})\s*'?(?P<year>\d{{2,4}})$", token, re.IGNORECASE)
    if m:
        mon = MONTH_NAMES.get(m.group("mon")[:3].lower())
        if mon is None:
            return None
        return _ParsedToken(_expand_year(m.group("year"), today), mon)

    m = re.match(r"^(\d{1,2})[/.\-](\d{4})$", token)
    if m:
        mon, year = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12:
            return _ParsedToken(year, mon)
        return None

    m = re.match(r"^'(\d{2})$", token)
    if m:
        return _ParsedToken(_expand_year(m.group(1), today), None)

    m = re.match(r"^(\d{4})$", token)
    if m:
        return _ParsedToken(int(m.group(1)), None)

    return None


def _to_start_date(pt: _ParsedToken) -> tuple[date, str]:
    if pt.month:
        return date(pt.year, pt.month, 1), "month"
    return date(pt.year, 1, 1), "year"


def _to_end_date(pt: _ParsedToken) -> tuple[date, str]:
    if pt.month:
        return date(pt.year, pt.month, 1), "month"
    return date(pt.year, 12, 31), "year"


def _find_headers(text: str) -> list[tuple[int, int, str]]:
    """Returns (header_start, header_end, 'exp'|'stop') for each header LINE,
    in document order. A header is a line of <=4 words that, once stripped of
    surrounding whitespace and a trailing colon, exactly matches one of the
    known header phrases (case-insensitive)."""
    headers: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.endswith(":"):
            stripped = stripped[:-1].strip()
        words = stripped.split()
        if stripped and len(words) <= 4:
            low = stripped.lower()
            if low in _EXP_HEADERS:
                headers.append((offset, offset + len(line), "exp"))
            elif low in _STOP_HEADERS:
                headers.append((offset, offset + len(line), "stop"))
        offset += len(line)
    return headers


def _experience_section_span(headers: list[tuple[int, int, str]], text_len: int) -> tuple[int, int] | None:
    exp_headers = [h for h in headers if h[2] == "exp"]
    if not exp_headers:
        return None
    first = exp_headers[0]
    later = [h for h in headers if h[0] > first[0]]
    end = later[0][0] if later else text_len
    return first[1], end


def _stop_spans(headers: list[tuple[int, int, str]], text_len: int) -> list[tuple[int, int]]:
    spans = []
    for h in headers:
        if h[2] != "stop":
            continue
        later = [o for o in headers if o[0] > h[0]]
        end = later[0][0] if later else text_len
        spans.append((h[1], end))
    return spans


def _span_within(a_start: int, a_end: int, span: tuple[int, int]) -> bool:
    return span[0] <= a_start and a_end <= span[1]


def _span_overlaps_any(a_start: int, a_end: int, spans: list[tuple[int, int]]) -> bool:
    return any(not (a_end <= s or a_start >= e) for s, e in spans)


def compute_experience(
    text: str,
    date_spans: list[tuple[int, int]],
    today: date,
) -> Experience:
    """Contract (docs/02-ingestion-pipeline.md §8.3): scans `text` for
    employment date ranges, scoped to a detected "Experience" section when
    one exists, or to spaCy-DATE-corroborated ranges outside education/other
    sections otherwise. Merges overlapping intervals and sums the total.
    """
    headers = _find_headers(text)
    exp_span = _experience_section_span(headers, len(text))
    section_found = exp_span is not None
    excluded_spans = [] if section_found else _stop_spans(headers, len(text))

    def in_scope(m_start: int, m_end: int) -> bool:
        if section_found:
            return _span_within(m_start, m_end, exp_span)  # type: ignore[arg-type]
        if _span_overlaps_any(m_start, m_end, excluded_spans):
            return False
        return _span_overlaps_any(m_start, m_end, date_spans)

    kept: list[tuple[date, date]] = []
    precisions: list[str] = []

    for m in _RANGE_RE.finditer(text):
        if not in_scope(m.start(), m.end()):
            continue

        start_pt = _parse_token(m.group("start"), today)
        if start_pt is None:
            continue
        start_date, start_prec = _to_start_date(start_pt)

        end_raw = " ".join(m.group("end").strip().lower().split())
        if end_raw in _PRESENT_WORDS:
            end_date, end_prec = today, "month"
        else:
            end_pt = _parse_token(m.group("end"), today)
            if end_pt is None:
                continue
            end_date, end_prec = _to_end_date(end_pt)

        # Sanity filters (step 5) — clamp end to today, drop nonsense ranges.
        if end_date > today:
            end_date = today
        if start_date > today:
            continue
        if end_date < start_date:
            continue
        if start_date.year < MIN_START_YEAR:
            continue
        if (end_date - start_date).days > MAX_SPAN_DAYS:
            continue

        kept.append((start_date, end_date))
        precisions.append("month" if start_prec == "month" and end_prec == "month" else "year")

    if not kept:
        return Experience(years=None, basis="unknown")

    merged = _merge_intervals(kept)
    total_days = sum((e - s).days for s, e in merged)
    years = round(total_days / 365.25, 1)

    basis = "computed" if section_found and all(p == "month" for p in precisions) else "estimated"
    return Experience(years=years, basis=basis)


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged: list[list[date]] = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]
