"""Every Lambda entry point in the layout from docs/01 §3 exists and exposes
`lambda_handler` (the 501 stubs were all replaced by real code in phases 2-3)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

HANDLERS = [
    "backend/ingestion/extraction/app/handler.py",
    "backend/ingestion/nlp/handler.py",
    "backend/scoring/score_match/handler.py",
    "backend/reliability/dlq_handler/handler.py",
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
]


def test_every_handler_location_exists_and_defines_lambda_handler():
    assert len(HANDLERS) == 14
    for rel in HANDLERS:
        path = REPO_ROOT / rel
        assert path.is_file(), f"missing {rel}"
        assert "def lambda_handler" in path.read_text(), rel


def test_no_stub_501_handlers_remain():
    for rel in HANDLERS:
        assert "NOT_IMPLEMENTED" not in (REPO_ROOT / rel).read_text(), rel
