"""Phase 1 smoke test: every stub handler returns the documented 501 envelope.

This is intentionally trivial — real unit tests for rs_common land in phase 2
(docs/02-ingestion-pipeline.md T-020-T-029). This just proves the test harness
(pytest, coverage, the Makefile target) works end to end before any real logic
exists, so phase 2 starts from a known-good baseline.
"""

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

STUB_HANDLERS = [
    "backend/ingestion/extraction/app/handler.py",
    "backend/ingestion/nlp/handler.py",
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


def test_all_fourteen_stub_locations_exist():
    assert len(STUB_HANDLERS) == 14
    for rel_path in STUB_HANDLERS:
        assert (REPO_ROOT / rel_path).is_file(), f"missing {rel_path}"


def test_every_stub_returns_the_501_envelope():
    for rel_path in STUB_HANDLERS:
        module = _load_handler(rel_path)
        result = module.lambda_handler({}, None)
        assert result["statusCode"] == 501, rel_path
        body = json.loads(result["body"])
        assert body["error"]["code"] == "NOT_IMPLEMENTED", rel_path
