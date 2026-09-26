"""Unit tests for rs_common.decisions — email at-most-once logic and decision apply.

Covers:
  - apply_decision when candidate not found -> 404
  - apply_decision when not scored -> 409 NOT_SCORED
  - decision != shortlisted -> returns current notification_status unchanged
  - shortlisted, no email -> skipped_no_email
  - shortlisted, invalid email format -> skipped_no_email
  - shortlisted, valid email, already sent -> returns current (no double-send)
  - shortlisted, valid email, SES succeeds -> sent
  - shortlisted, valid email, SES fails -> failed + audit row written
  - _greeting: name sanitisation (control characters, long name, empty)
  - _set_notification: conditional check failure returns False
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# The module under test depends on env vars at import time via lazy boto3 clients
# and clock/ids.  Patch the required env vars before importing.
os.environ.setdefault("CANDIDATES_TABLE", "candidates-test")
os.environ.setdefault("FAILED_JOBS_TABLE", "failed-jobs-test")
os.environ.setdefault("SES_SENDER_ADDRESS", "no-reply@example.com")
os.environ.setdefault("ALLOWED_ORIGIN", "http://localhost:5173")


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def _make_tables(cand_item=None, update_attrs=None, cond_fail=False):
    """Return (candidates_mock, failed_mock) with sensible defaults."""
    candidates = MagicMock()
    failed = MagicMock()

    if cand_item is None:
        # get_item returns nothing -> candidate not found
        candidates.get_item.return_value = {}
    else:
        candidates.get_item.return_value = {"Item": cand_item}

    if cond_fail:
        candidates.update_item.side_effect = _client_error("ConditionalCheckFailedException")
    elif update_attrs is not None:
        candidates.update_item.return_value = {"Attributes": update_attrs}
    else:
        candidates.update_item.return_value = {"Attributes": cand_item or {}}

    return candidates, failed


JOB = {"job_id": "job_" + "a" * 32, "job_title": "Backend Engineer"}
CAND_ID = "cand_" + "b" * 32
KEY = {"job_id": JOB["job_id"], "candidate_id": CAND_ID}


# ---------------------------------------------------------------------------
# _greeting
# ---------------------------------------------------------------------------


def test_greeting_normal_name():
    from rs_common.decisions import _greeting

    assert _greeting("Alice") == "Hi Alice,"


def test_greeting_empty_or_none():
    from rs_common.decisions import _greeting

    assert _greeting(None) == "Hello,"
    assert _greeting("") == "Hello,"
    assert _greeting("   ") == "Hello,"


def test_greeting_strips_control_characters():
    from rs_common.decisions import _greeting

    result = _greeting("Alice\x00\x01\x1f")
    assert "\x00" not in result
    assert result.startswith("Hi ")


def test_greeting_truncates_long_name():
    from rs_common.decisions import _greeting

    long_name = "A" * 200
    assert len(_greeting(long_name)) <= len("Hi ,") + 100


# ---------------------------------------------------------------------------
# apply_decision: candidate not found -> 404
# ---------------------------------------------------------------------------


def test_apply_decision_candidate_not_found():
    from rs_common import decisions
    from rs_common.http import HttpError

    cands, failed = _make_tables(cand_item=None)
    with patch.object(decisions, "_tables", return_value=(cands, failed)), pytest.raises(HttpError) as ei:
        decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")
    assert ei.value.status == 404
    assert ei.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# apply_decision: not scored -> 409 NOT_SCORED
# ---------------------------------------------------------------------------


def test_apply_decision_not_scored_raises_409():
    from rs_common import decisions
    from rs_common.http import HttpError

    cands, failed = _make_tables(
        cand_item={"candidate_id": CAND_ID, "job_id": JOB["job_id"], "notification_status": None},
        cond_fail=True,
    )
    with patch.object(decisions, "_tables", return_value=(cands, failed)), pytest.raises(HttpError) as ei:
        decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")
    assert ei.value.status == 409
    assert ei.value.code == "NOT_SCORED"


# ---------------------------------------------------------------------------
# apply_decision: rejected -> returns current notification_status, no email
# ---------------------------------------------------------------------------


def test_apply_decision_rejected_returns_current_status():
    from rs_common import decisions

    cand = {
        "candidate_id": CAND_ID,
        "job_id": JOB["job_id"],
        "notification_status": "sent",
        "score_status": "scored",
    }
    cands, failed = _make_tables(cand_item=cand, update_attrs={**cand, "decision": "rejected"})

    with patch.object(decisions, "_tables", return_value=(cands, failed)):
        result = decisions.apply_decision(JOB, CAND_ID, "rejected", "sub-123")

    assert result["decision"] == "rejected"
    assert result["notification_status"] == "sent"  # unchanged


# ---------------------------------------------------------------------------
# apply_decision: shortlisted, no email -> skipped_no_email
# ---------------------------------------------------------------------------


def test_apply_decision_shortlisted_no_email_skips():
    from rs_common import decisions

    cand = {"candidate_id": CAND_ID, "job_id": JOB["job_id"], "score_status": "scored"}  # no email field
    updated = {**cand, "decision": "shortlisted"}
    cands, failed = _make_tables(cand_item=cand, update_attrs=updated)

    # _set_notification for the first conditional write returns True (claimed)
    set_notif_results = iter([True])

    with (
        patch.object(decisions, "_tables", return_value=(cands, failed)),
        patch.object(decisions, "_set_notification", side_effect=set_notif_results),
    ):
        result = decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")

    assert result["notification_status"] == "skipped_no_email"


def test_apply_decision_shortlisted_invalid_email_skips():
    from rs_common import decisions

    cand = {
        "candidate_id": CAND_ID,
        "job_id": JOB["job_id"],
        "score_status": "scored",
        "email": "not-an-email",  # extract_email returns None for this
    }
    updated = {**cand, "decision": "shortlisted"}
    cands, failed = _make_tables(cand_item=cand, update_attrs=updated)

    with (
        patch.object(decisions, "_tables", return_value=(cands, failed)),
        patch.object(decisions, "_set_notification", return_value=True),
    ):
        result = decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")

    assert result["notification_status"] == "skipped_no_email"


# ---------------------------------------------------------------------------
# apply_decision: shortlisted, already sent -> no new email
# ---------------------------------------------------------------------------


def test_apply_decision_shortlisted_already_sent_no_double_email():
    from rs_common import decisions

    cand = {
        "candidate_id": CAND_ID,
        "job_id": JOB["job_id"],
        "score_status": "scored",
        "email": "alice@example-mail.test",
        "notification_status": "sent",
    }
    updated = {**cand, "decision": "shortlisted"}
    cands, failed = _make_tables(cand_item=cand, update_attrs=updated)

    # _set_notification returns False -> claim not acquired -> no email
    with (
        patch.object(decisions, "_tables", return_value=(cands, failed)),
        patch.object(decisions, "_set_notification", return_value=False),
    ):
        result = decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")

    assert result["notification_status"] == "sent"


# ---------------------------------------------------------------------------
# apply_decision: shortlisted, SES succeeds -> sent
# ---------------------------------------------------------------------------


def test_apply_decision_shortlisted_ses_success():
    from rs_common import decisions

    cand = {
        "candidate_id": CAND_ID,
        "job_id": JOB["job_id"],
        "score_status": "scored",
        "email": "alice@example-mail.test",
        "name": "Alice",
    }
    updated = {**cand, "decision": "shortlisted"}
    cands, failed = _make_tables(cand_item=cand, update_attrs=updated)

    ses_mock = MagicMock()

    with (
        patch.object(decisions, "_tables", return_value=(cands, failed)),
        patch.object(decisions, "_set_notification", side_effect=[True, True]),
        patch.object(decisions, "_sesv2", return_value=ses_mock),
    ):
        result = decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")

    ses_mock.send_email.assert_called_once()
    assert result["notification_status"] == "sent"


# ---------------------------------------------------------------------------
# apply_decision: shortlisted, SES fails -> failed + audit row
# ---------------------------------------------------------------------------


def test_apply_decision_ses_failure_records_failed_not_raises():
    from rs_common import decisions

    cand = {
        "candidate_id": CAND_ID,
        "job_id": JOB["job_id"],
        "score_status": "scored",
        "email": "bob@example-mail.test",
        "name": "Bob",
    }
    updated = {**cand, "decision": "shortlisted"}
    cands, failed = _make_tables(cand_item=cand, update_attrs=updated)

    ses_mock = MagicMock()
    ses_mock.send_email.side_effect = _client_error("MessageRejected")

    with (
        patch.object(decisions, "_tables", return_value=(cands, failed)),
        patch.object(decisions, "_set_notification", side_effect=[True, True]),
        patch.object(decisions, "_sesv2", return_value=ses_mock),
    ):
        result = decisions.apply_decision(JOB, CAND_ID, "shortlisted", "sub-123")

    # Decision still succeeds — SES failure must not fail the decision (R-BUS-08)
    assert result["decision"] == "shortlisted"
    assert result["notification_status"] == "failed"
    failed.put_item.assert_called_once()
    # Confirm the audit row never contains the email address (R-PRIV-02)
    put_item_kwargs = failed.put_item.call_args[1]["Item"]
    assert "bob@example-mail.test" not in json.dumps(put_item_kwargs)


# ---------------------------------------------------------------------------
# _set_notification: ConditionalCheckFailedException returns False
# ---------------------------------------------------------------------------


def test_set_notification_conditional_failure_returns_false():
    from rs_common import decisions

    table = MagicMock()
    table.update_item.side_effect = _client_error("ConditionalCheckFailedException")
    result = decisions._set_notification(
        table, KEY, "sending", condition="attribute_not_exists(notification_status)"
    )
    assert result is False


def test_set_notification_other_client_error_reraises():
    from rs_common import decisions

    table = MagicMock()
    table.update_item.side_effect = _client_error("ProvisionedThroughputExceededException")
    with pytest.raises(ClientError):
        decisions._set_notification(table, KEY, "sending")


import json  # noqa: E402 — imported at bottom to keep test readability
