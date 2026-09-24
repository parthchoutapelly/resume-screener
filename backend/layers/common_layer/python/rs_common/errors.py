"""Error taxonomy shared across extraction, NLP, and scoring (docs/Architecture.md
§7.4, docs/Rules.md §7). Two dimensions:

  - ErrorCode: the public, recruiter-visible reason shown on a candidate/job row.
  - Stage: the internal, Admin-only location a failure happened in.

TerminalError (deterministic, never retried) vs TransientError (possibly
recoverable, re-raised so SQS retries) is the D-19 split that keeps a corrupt
file from sitting in "Processing..." for ~36 minutes before showing an error.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Recruiter-visible failure reason (Architecture.md §7.4)."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    UNREADABLE_DOCUMENT = "unreadable_document"
    PROCESSING_FAILED = "processing_failed"
    SCORING_FAILED = "scoring_failed"


class Stage(StrEnum):
    """Internal failure location, Admin-only (failed_jobs.stage)."""

    ORPHAN_OBJECT = "orphan_object"
    UNSUPPORTED_FORMAT = "unsupported_format"
    S3_DOWNLOAD = "s3_download"
    PDF_EXTRACT = "pdf_extract"
    DOCX_EXTRACT = "docx_extract"
    OCR = "ocr"
    NLP = "nlp"
    SCORING = "scoring"
    API = "api"
    INGESTION_EXHAUSTED = "ingestion_exhausted"
    SCORING_EXHAUSTED = "scoring_exhausted"


class TerminalError(Exception):
    """Deterministic failure: record once, mark the item `error`, ACK the
    message (do not re-raise — retrying could never succeed, R-ERR-02).
    `code` is the public ErrorCode shown to recruiters; it is None for
    failures that have no item to mark (e.g. an orphan S3 object)."""

    def __init__(self, code: ErrorCode | None, stage: Stage, detail: str):
        super().__init__(detail)
        self.code = code
        self.stage = stage


class TransientError(Exception):
    """Possibly recoverable failure: record the attempt, re-raise so SQS's
    redrive policy retries it (R-ERR-03)."""

    def __init__(self, stage: Stage, detail: str):
        super().__init__(detail)
        self.stage = stage


class EmptyDocumentError(Exception):
    """Raised by nlpProcessing when the extracted text has no real tokens.
    Surfaces to documentExtraction as a Lambda FunctionError with this exact
    class name, which extraction classifies as terminal `unreadable_document`."""


class OrphanRecordError(Exception):
    """Raised by nlpProcessing when the DynamoDB placeholder item it expected
    to update no longer exists. Surfaces as a FunctionError classified as
    terminal (Architecture.md §7.4: no item to mark, stage=orphan_object)."""


def safe_message(exc: BaseException, limit: int = 500) -> str:
    """Exception type + our own detail string only — never document content
    (R-PRIV-02). Callers must never put extracted/candidate text into an
    exception's `detail`; this function has no way to filter that out after
    the fact, so the discipline has to hold at the raise site."""
    return f"{type(exc).__name__}: {exc}"[:limit]
