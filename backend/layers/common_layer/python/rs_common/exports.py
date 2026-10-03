"""Shortlist CSV (Rules R-BUS-12, R-SEC-09). Every cell is candidate-controlled
text, so any cell that a spreadsheet could interpret as a formula is defused."""

from __future__ import annotations

import csv
import io

COLUMNS = ["name", "email", "skills", "titles_held", "total_experience_years", "match_score", "decided_at"]


def csv_safe(v) -> str:
    s = "" if v is None else str(v)
    stripped = s.lstrip()
    return "'" + s if stripped[:1] in ("=", "+", "-", "@") or s[:1] in ("\t", "\r") else s


def build_csv(rows: list[dict]) -> bytes:
    """UTF-8 with a BOM so Excel renders non-ASCII names correctly."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for c in rows:
        w.writerow(
            [
                csv_safe(c.get("name")),
                csv_safe(c.get("email")),
                csv_safe("; ".join(c.get("skills", []))),
                csv_safe("; ".join(c.get("titles_held", []))),
                csv_safe(c.get("total_experience_years")),
                csv_safe(c.get("match_score")),
                csv_safe(c.get("decided_at")),
            ]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
