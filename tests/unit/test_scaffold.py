"""Smoke test: every handler that is *still a stub* returns the documented
501 envelope. extraction and nlp got real implementations in phase 2
(docs/02-ingestion-pipeline.md) — they're covered by their own component
tests instead (tests/component/), not this list.

Scoring, the API routes, and dlqHandler remain 501 stubs until phase 3
(docs/03-scoring-and-api.md).
"""

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

STUB_HANDLERS = [
    "backend/scoring/score_match/handler.py",
    "backend/api/create_job_posting/handler.py",
    "backend/api/add_resumes/handler.py",
    "backend/api/get_jobs/handler.py",
    "backend/api/get_job/handler.py",
    "backend/api/update_job/handler.py",
    "backend/api/get_candidates_by_job/handler.py",
    "backend/api/update_candidate_decision/handler.py",
    "backend/api/get_resume_url/handler.py",
    "backend/api/export_shortlist_csv/handler.py",
    "backend/api/get_failed_jobs/handler.py",
    "backend/reliability/dlq_handler/handler.py",
]


def _load_handler(rel_path: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(rel_path.replace("/", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_twelve_remaining_stub_locations_exist():
    assert len(STUB_HANDLERS) == 12
    for rel_path in STUB_HANDLERS:
        assert (REPO_ROOT / rel_path).is_file(), f"missing {rel_path}"


def test_every_remaining_stub_returns_the_501_envelope():
    for rel_path in STUB_HANDLERS:
        module = _load_handler(rel_path)
        result = module.lambda_handler({}, None)
        assert result["statusCode"] == 501, rel_path
        body = json.loads(result["body"])
        assert body["error"]["code"] == "NOT_IMPLEMENTED", rel_path


def test_extraction_and_nlp_are_no_longer_stubs():
    """Phase 2 replaced these two — this guards against accidentally leaving
    (or reverting to) the 501 stub for either."""
    for rel_path in ["backend/ingestion/extraction/app/handler.py", "backend/ingestion/nlp/handler.py"]:
        source = (REPO_ROOT / rel_path).read_text()
        assert "NOT_IMPLEMENTED" not in source, f"{rel_path} still looks like a stub"
