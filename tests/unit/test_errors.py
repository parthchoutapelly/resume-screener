"""Unit tests for rs_common.errors."""

import pytest

from rs_common.errors import (
    EmptyDocumentError,
    ErrorCode,
    OrphanRecordError,
    Stage,
    TerminalError,
    TransientError,
    safe_message,
)


def test_terminal_error_carries_code_and_stage():
    e = TerminalError(ErrorCode.UNREADABLE_DOCUMENT, Stage.PDF_EXTRACT, "empty pdf")
    assert e.code == ErrorCode.UNREADABLE_DOCUMENT
    assert e.stage == Stage.PDF_EXTRACT
    assert str(e) == "empty pdf"


def test_terminal_error_code_can_be_none():
    e = TerminalError(None, Stage.ORPHAN_OBJECT, "no placeholder")
    assert e.code is None


def test_transient_error_carries_stage():
    e = TransientError(Stage.S3_DOWNLOAD, "network blip")
    assert e.stage == Stage.S3_DOWNLOAD


def test_empty_document_and_orphan_record_are_plain_exceptions():
    with pytest.raises(EmptyDocumentError):
        raise EmptyDocumentError("no tokens")
    with pytest.raises(OrphanRecordError):
        raise OrphanRecordError("item vanished")


def test_safe_message_includes_type_and_detail():
    try:
        raise ValueError("bad input")
    except ValueError as e:
        msg = safe_message(e)
    assert msg == "ValueError: bad input"


def test_safe_message_truncates_to_limit():
    try:
        raise RuntimeError("x" * 1000)
    except RuntimeError as e:
        msg = safe_message(e, limit=50)
    assert len(msg) == 50


def test_error_code_values_match_public_contract():
    assert ErrorCode.UNSUPPORTED_FORMAT == "unsupported_format"
    assert ErrorCode.FILE_TOO_LARGE == "file_too_large"
    assert ErrorCode.TOO_MANY_PAGES == "too_many_pages"
    assert ErrorCode.UNREADABLE_DOCUMENT == "unreadable_document"
    assert ErrorCode.PROCESSING_FAILED == "processing_failed"
    assert ErrorCode.SCORING_FAILED == "scoring_failed"


def test_stage_values_match_internal_contract():
    assert Stage.ORPHAN_OBJECT == "orphan_object"
    assert Stage.INGESTION_EXHAUSTED == "ingestion_exhausted"
    assert Stage.SCORING_EXHAUSTED == "scoring_exhausted"
