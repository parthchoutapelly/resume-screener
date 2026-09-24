"""display_status: one test per row of Architecture.md §7.2, plus the time boundaries."""

from datetime import UTC, datetime, timedelta

import pytest

from rs_common import clock
from rs_common.status import ORDER, display_status, sort_key

NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


SCORABLE_JOB = {"parse_status": "not_applicable", "required_skills": ["python"]}
AWAITING_JD = {"parse_status": "pending", "required_skills": ["python"]}
NO_SKILLS = {"parse_status": "parsed"}


def test_row1_parse_error():
    assert display_status(
        {"parse_status": "error", "error_code": "unreadable_document"}, SCORABLE_JOB, NOW
    ) == (
        "error",
        "unreadable_document",
    )


def test_row2_upload_missing_only_after_grace():
    exp = NOW - timedelta(minutes=2)
    cand = {"parse_status": "pending", "upload_expires_at": iso(exp)}
    assert display_status(cand, SCORABLE_JOB, NOW)[0] == "processing"  # exactly +2 min: not yet
    assert display_status(cand, SCORABLE_JOB, NOW + timedelta(seconds=1))[0] == "upload_missing"


def test_upload_missing_needs_no_ingest_start():
    cand = {
        "parse_status": "pending",
        "upload_expires_at": iso(NOW - timedelta(hours=1)),
        "ingest_started_at": iso(NOW),
    }
    assert display_status(cand, SCORABLE_JOB, NOW)[0] == "processing"


def test_row3_stalled_after_60_minutes():
    started = NOW - timedelta(minutes=60)
    cand = {"parse_status": "pending", "ingest_started_at": iso(started)}
    assert display_status(cand, SCORABLE_JOB, NOW)[0] == "processing"  # exactly 60: not yet
    assert display_status(cand, SCORABLE_JOB, NOW + timedelta(seconds=1))[0] == "stalled"


def test_row4_processing():
    assert display_status({"parse_status": "pending"}, SCORABLE_JOB, NOW) == ("processing", None)
    assert display_status({}, SCORABLE_JOB, NOW) == ("processing", None)  # missing status == pending


def test_row5_scoring_failed_keeps_parse_status_parsed():
    c = {"parse_status": "parsed", "score_status": "error"}
    assert display_status(c, SCORABLE_JOB, NOW) == ("error", "scoring_failed")


def test_row6_scored_wins_even_if_job_later_unscorable():
    c = {"parse_status": "parsed", "score_status": "scored"}
    assert display_status(c, NO_SKILLS, NOW) == ("scored", None)


def test_row7_awaiting_jd():
    assert (
        display_status({"parse_status": "parsed", "score_status": "pending"}, AWAITING_JD, NOW)[0]
        == "awaiting_jd"
    )


def test_row8_awaiting_requirements():
    assert display_status({"parse_status": "parsed"}, NO_SKILLS, NOW)[0] == "awaiting_requirements"
    failed_jd = {"parse_status": "error"}
    assert display_status({"parse_status": "parsed"}, failed_jd, NOW)[0] == "awaiting_requirements"


def test_row9_scoring():
    assert display_status({"parse_status": "parsed", "score_status": "pending"}, SCORABLE_JOB, NOW) == (
        "scoring",
        None,
    )


def test_clock_parse_roundtrip():
    assert clock.parse_iso("2026-09-24T12:00:00Z") == NOW


def test_sort_order():
    rows = [
        {"display_status": s, "candidate_id": f"c{i}", "match_score": 50.0}
        for i, s in enumerate(reversed([o for o in ORDER if o != "scored"]))
    ]
    rows += [
        {"display_status": "scored", "candidate_id": "cZ", "match_score": 90.0},
        {"display_status": "scored", "candidate_id": "cA", "match_score": 90.0},
        {"display_status": "scored", "candidate_id": "cM", "match_score": 95.5},
    ]
    ordered = sorted(rows, key=sort_key)
    assert [r["candidate_id"] for r in ordered[:3]] == ["cM", "cA", "cZ"]  # score desc, id tie-break
    assert [r["display_status"] for r in ordered[3:]] == [s for s in ORDER if s != "scored"]
    assert sorted(ORDER) != ORDER  # ordering is deliberate, not alphabetical


@pytest.mark.parametrize("status", ORDER)
def test_every_status_sortable(status):
    assert sort_key({"display_status": status, "candidate_id": "c", "match_score": 1})
