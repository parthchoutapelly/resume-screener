"""Unit tests for the small rs_common utility modules: clock, ids, log."""

import json
import re
from datetime import date

from rs_common import clock, ids, log


def test_now_iso_format():
    s = clock.now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s)


def test_today_returns_a_date():
    d = clock.today()
    assert isinstance(d, date)


def test_epoch_in_days_is_in_the_future():
    import time

    now = int(time.time())
    ttl = clock.epoch_in_days(90)
    assert ttl > now
    assert ttl - now == 90 * 86400 or abs((ttl - now) - 90 * 86400) < 5  # allow test-run skew


def test_job_id_format():
    j = ids.job_id()
    assert j.startswith("job_")
    assert len(j) == len("job_") + 32  # full uuid4 hex, not truncated (D-37)


def test_candidate_id_format():
    c = ids.candidate_id()
    assert c.startswith("cand_")
    assert len(c) == len("cand_") + 32


def test_failure_id_format():
    f = ids.failure_id()
    assert f.startswith("fail_")
    assert len(f) == len("fail_") + 32


def test_ids_are_unique():
    assert ids.job_id() != ids.job_id()
    assert ids.candidate_id() != ids.candidate_id()


def test_log_emits_valid_json_line(capsys):
    log.info("test event", job_id="job_123", count=5)
    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["level"] == "INFO"
    assert record["msg"] == "test event"
    assert record["job_id"] == "job_123"
    assert record["count"] == 5
    assert "timestamp" in record


def test_log_drops_forbidden_keys(capsys):
    log.warning(
        "should not leak",
        job_id="job_1",
        text="the whole resume body goes here",
        email="jane@example.com",
        name="Jane Doe",
    )
    captured = capsys.readouterr()
    record = json.loads(captured.out.strip())
    assert record["job_id"] == "job_1"
    assert "text" not in record
    assert "email" not in record
    assert "name" not in record


def test_log_error_level(capsys):
    log.error("bad thing happened", stage="nlp")
    record = json.loads(capsys.readouterr().out.strip())
    assert record["level"] == "ERROR"
    assert record["stage"] == "nlp"
