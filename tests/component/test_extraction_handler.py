"""Component tests for the extraction Lambda (docs/02-ingestion-pipeline.md
§10). S3 and DynamoDB are mocked with moto; the NLP invoke is stubbed (a
fake lambda_client) since nlpProcessing's own behaviour is tested separately
in test_nlp_handler.py — these tests are about extraction's own branching:
per-format extraction, per-page OCR fallback, and terminal-vs-transient
classification.
"""

from __future__ import annotations

import io
import json

import boto3
import pytest
from conftest import (
    CANDIDATES_TABLE,
    FAILED_JOBS_TABLE,
    FIXTURES_DIR,
    JDS_DIR,
    JOBS_TABLE,
    create_core_tables,
)
from moto import mock_aws
from PIL import Image
from pypdf import PdfWriter

BUCKET = "rs-test-bucket"


class FakeLambdaClient:
    """Stands in for boto3's lambda client so tests control nlpProcessing's
    response without actually invoking it."""

    def __init__(self, response=None, raise_exc=None):
        self.response = response or {}
        self.raise_exc = raise_exc
        self.calls = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return self.response


def _sqs_event(bucket: str, key: str, receive_count: int = 1) -> dict:
    s3_event = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
    return {
        "Records": [
            {
                "body": json.dumps(s3_event),
                "attributes": {"ApproximateReceiveCount": str(receive_count)},
            }
        ]
    }


def _upload(s3, bucket, key, path):
    with open(path, "rb") as f:
        s3.put_object(Bucket=bucket, Key=key, Body=f.read())


def _setup(monkeypatch, module, lambda_client):
    """Creates the bucket + tables + placeholder items this test needs, and
    points the already-imported module's boto3 handles at the moto backend."""
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)

    monkeypatch.setattr(module, "s3", s3)
    monkeypatch.setattr(module, "lambda_client", lambda_client)
    monkeypatch.setattr(module, "_ddb", ddb)
    monkeypatch.setattr(module, "JOBS", ddb.Table(JOBS_TABLE))
    monkeypatch.setattr(module, "CANDIDATES", ddb.Table(CANDIDATES_TABLE))
    monkeypatch.setattr(module, "FAILED", ddb.Table(FAILED_JOBS_TABLE))
    return s3, ddb


def _make_candidate_placeholder(ddb, job_id, candidate_id):
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": job_id, "candidate_id": candidate_id, "parse_status": "pending"}
    )


def _make_job_placeholder(ddb, job_id):
    ddb.Table(JOBS_TABLE).put_item(Item={"job_id": job_id, "parse_status": "pending"})


# ---------------------------------------------------------------------------
# parse_key
# ---------------------------------------------------------------------------


def test_parse_key_resume(extraction_module):
    ref = extraction_module.parse_key("resume-uploads/job_x/cand_y/resume.pdf")
    assert ref.doc_type == "resume"
    assert ref.job_id == "job_x"
    assert ref.candidate_id == "cand_y"
    assert ref.ext == "pdf"


def test_parse_key_jd(extraction_module):
    ref = extraction_module.parse_key("jd-uploads/job_x/jd.pdf")
    assert ref.doc_type == "jd"
    assert ref.job_id == "job_x"
    assert ref.candidate_id is None


def test_parse_key_unknown_prefix_returns_none(extraction_module):
    assert extraction_module.parse_key("exports/job_x/report.csv") is None


def test_parse_key_wrong_depth_returns_none(extraction_module):
    assert extraction_module.parse_key("resume-uploads/job_x/resume.pdf") is None  # missing candidate segment


# ---------------------------------------------------------------------------
# Successful extraction paths
# ---------------------------------------------------------------------------


@mock_aws
def test_native_pdf_success(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})  # no FunctionError key = success
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "worked_example_native.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    assert len(lam.calls) == 1
    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["doc_type"] == "resume"
    assert payload["job_id"] == "job_1"
    assert payload["candidate_id"] == "cand_1"
    assert "Jane Doe" in payload["extracted_text"]
    assert payload["extraction_metadata"]["file_type"] == "pdf_native"
    assert payload["extraction_metadata"]["ocr_pages"] == 0

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert "ingest_started_at" in item
    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert failures == []


@mock_aws
def test_scanned_pdf_uses_real_ocr(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "daniel_kim_scanned.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["extraction_metadata"]["file_type"] == "pdf_scanned"
    assert payload["extraction_metadata"]["ocr_pages"] == 1
    assert "Daniel Kim" in payload["extracted_text"]  # genuinely OCR'd, not fabricated


@mock_aws
def test_mixed_pdf_only_ocrs_the_scanned_page(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "maya_bennett_mixed.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["extraction_metadata"]["file_type"] == "pdf_mixed"
    assert payload["extraction_metadata"]["ocr_pages"] == 1
    assert payload["extraction_metadata"]["page_count"] == 2
    assert "Maya Bennett" in payload["extracted_text"]
    assert "Oscorp" in payload["extracted_text"]  # from the OCR'd page


@mock_aws
def test_docx_with_tables(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.docx"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "bob_kumar.docx")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["extraction_metadata"]["file_type"] == "docx"
    assert "Bob Kumar" in payload["extracted_text"]
    assert "Available on request" in payload["extracted_text"]  # from the table


@mock_aws
def test_standalone_png_image(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.png"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "jordan_rivera.png")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["extraction_metadata"]["file_type"] == "image"
    assert "Jordan Rivera" in payload["extracted_text"]


@mock_aws
def test_multipage_tiff(monkeypatch, extraction_module, tmp_path):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")

    # Build a 2-page TIFF on the fly (no such fixture on disk). Needs >=100
    # combined usable chars across both pages to clear MIN_USABLE_CHARS.
    page1 = Image.new("RGB", (400, 300), "white")
    page2 = Image.new("RGB", (400, 300), "white")
    from PIL import ImageDraw

    d1 = ImageDraw.Draw(page1)
    d1.text((10, 10), "Alex Rivera", fill="black")
    d1.text((10, 40), "Experience", fill="black")
    d1.text((10, 70), "Acme Corp - Backend Engineer", fill="black")
    d2 = ImageDraw.Draw(page2)
    d2.text((10, 10), "Skills", fill="black")
    d2.text((10, 40), "Python, AWS, DynamoDB, SQL", fill="black")
    d2.text((10, 70), "Additional experience details here", fill="black")
    tiff_path = tmp_path / "multi.tiff"
    page1.save(tiff_path, save_all=True, append_images=[page2])

    key = "resume-uploads/job_1/cand_1/resume.tiff"
    _upload(s3, BUCKET, key, tiff_path)

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["extraction_metadata"]["file_type"] == "image"
    assert payload["extraction_metadata"]["page_count"] == 2
    assert payload["extraction_metadata"]["ocr_pages"] == 2


@mock_aws
def test_jd_pasted_text_file(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_job_placeholder(ddb, "job_1")
    key = "jd-uploads/job_1/jd.txt"
    _upload(s3, BUCKET, key, JDS_DIR / "backend_engineer_jd.txt")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    payload = json.loads(lam.calls[0]["Payload"])
    assert payload["doc_type"] == "jd"
    assert payload["candidate_id"] is None
    assert payload["extraction_metadata"]["file_type"] == "text"


# ---------------------------------------------------------------------------
# Terminal failures — recorded once, item marked error, no re-raise
# ---------------------------------------------------------------------------


@mock_aws
def test_renamed_text_file_is_terminal_unsupported_format(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "renamed_text_file.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)  # must not raise

    assert lam.calls == []  # never got as far as invoking NLP
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unsupported_format"
    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is True
    assert failures[0]["stage"] == "unsupported_format"


@mock_aws
def test_corrupt_pdf_is_terminal(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "corrupt.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unreadable_document"
    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is True


@mock_aws
def test_encrypted_pdf_is_terminal(monkeypatch, extraction_module, tmp_path):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret", owner_password="different-owner-secret")
    enc_path = tmp_path / "encrypted.pdf"
    with open(enc_path, "wb") as f:
        writer.write(f)

    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, enc_path)

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unreadable_document"


@mock_aws
def test_blank_scan_is_terminal_unreadable(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "blank_scan.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unreadable_document"
    assert lam.calls == []


@mock_aws
def test_eleven_page_pdf_is_terminal_too_many_pages(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "eleven_pages.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "too_many_pages"


@mock_aws
def test_oversized_canvas_pdf_is_terminal_unreadable(monkeypatch, extraction_module, tmp_path):
    import fitz

    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")

    # Create a 1-page PDF with canvas dimensions > 3,000 pt (e.g. 4,000 x 4,000 pt)
    # with text < 40 chars so it hits the OCR path
    pdf_path = tmp_path / "oversized.pdf"
    doc = fitz.open()
    page = doc.new_page(width=4000, height=4000)
    page.insert_text((50, 50), "scan")
    doc.save(str(pdf_path))
    doc.close()

    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, pdf_path)

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unreadable_document"
    assert lam.calls == []


@mock_aws
def test_orphan_object_key_no_placeholder(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    # No placeholder candidate item created.
    key = "resume-uploads/job_1/cand_missing/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "worked_example_native.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)  # must not raise

    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is True
    assert failures[0]["stage"] == "orphan_object"


@mock_aws
def test_key_matching_no_prefix_is_orphan(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    key = "exports/job_1/report.csv"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"a,b,c")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["job_id"] == "unknown"
    assert failures[0]["stage"] == "orphan_object"


# ---------------------------------------------------------------------------
# NLP FunctionError classification
# ---------------------------------------------------------------------------


@mock_aws
def test_nlp_empty_document_error_is_terminal(monkeypatch, extraction_module):
    fake_payload = io.BytesIO(json.dumps({"errorType": "EmptyDocumentError"}).encode())
    lam = FakeLambdaClient(response={"FunctionError": "Unhandled", "Payload": fake_payload})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "worked_example_native.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)  # must not raise

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "error"
    assert item["error_code"] == "unreadable_document"
    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["stage"] == "nlp"
    assert failures[0]["terminal"] is True


@mock_aws
def test_nlp_unexpected_error_is_transient_and_reraises(monkeypatch, extraction_module):
    fake_payload = io.BytesIO(json.dumps({"errorType": "RuntimeError"}).encode())
    lam = FakeLambdaClient(response={"FunctionError": "Unhandled", "Payload": fake_payload})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "worked_example_native.pdf")

    with pytest.raises(Exception, match="nlpProcessing raised RuntimeError"):
        extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "pending"  # NOT marked error — transient, will retry
    failures = ddb.Table(FAILED_JOBS_TABLE).scan()["Items"]
    assert len(failures) == 1
    assert failures[0]["terminal"] is False
    assert failures[0]["stage"] == "nlp"


# ---------------------------------------------------------------------------
# Idempotency: duplicate S3 event causes no regression
# ---------------------------------------------------------------------------


@mock_aws
def test_duplicate_event_after_success_causes_no_regression(monkeypatch, extraction_module):
    lam = FakeLambdaClient(response={})
    s3, ddb = _setup(monkeypatch, extraction_module, lam)
    _make_candidate_placeholder(ddb, "job_1", "cand_1")
    key = "resume-uploads/job_1/cand_1/resume.pdf"
    _upload(s3, BUCKET, key, FIXTURES_DIR / "worked_example_native.pdf")

    extraction_module.lambda_handler(_sqs_event(BUCKET, key), None)
    # Simulate NLP having since marked it parsed (extraction doesn't do this itself).
    ddb.Table(CANDIDATES_TABLE).update_item(
        Key={"job_id": "job_1", "candidate_id": "cand_1"},
        UpdateExpression="SET parse_status = :p",
        ExpressionAttributeValues={":p": "parsed"},
    )

    extraction_module.lambda_handler(_sqs_event(BUCKET, key, receive_count=2), None)  # redelivered

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["parse_status"] == "parsed"  # unchanged — extraction never touches parse_status on success
    assert len(lam.calls) == 2  # NLP invoked again, but that's NLP's own idempotency concern
