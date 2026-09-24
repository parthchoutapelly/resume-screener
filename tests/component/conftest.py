"""Shared scaffolding for component tests (docs/02-ingestion-pipeline.md §10).

The extraction and NLP handlers live outside any Python package (each
directory has its own handler.py, loaded by SAM per-function), so they're
imported here by file path with unique module names — the same pattern
tests/unit/test_scaffold.py uses for the stub handlers.

Both handlers read required config from os.environ at IMPORT time (table
names, the NLP function name, etc.), so those must be set before either
module is first imported. nlpProcessing additionally makes a real DynamoDB
call at import time (the nlp_engine_mode check), so it's imported inside an
active moto mock with a config table already seeded.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REPO_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("JOBS_TABLE", "jobs-test")
os.environ.setdefault("CANDIDATES_TABLE", "candidates-test")
os.environ.setdefault("FAILED_JOBS_TABLE", "failed_jobs-test")
os.environ.setdefault("CONFIG_TABLE", "config-test")
os.environ.setdefault("SCORING_QUEUE_URL", "https://sqs.ap-south-1.amazonaws.com/000000000000/scoring-test")
os.environ.setdefault("NLP_FUNCTION_NAME", "rs-nlp-test")
os.environ.setdefault("RS_DATA_DIR", str(REPO_ROOT / "backend" / "data"))

JOBS_TABLE = os.environ["JOBS_TABLE"]
CANDIDATES_TABLE = os.environ["CANDIDATES_TABLE"]
FAILED_JOBS_TABLE = os.environ["FAILED_JOBS_TABLE"]
CONFIG_TABLE = os.environ["CONFIG_TABLE"]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Must be registered in sys.modules BEFORE exec: dataclasses with
    # `from __future__ import annotations` resolves string annotations via
    # sys.modules[cls.__module__], which is None (and AttributeErrors) for a
    # module that was never registered under its own __module__ name.
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def extraction_module():
    """No AWS calls happen at import time for extraction, so a plain import
    (outside any mock) is fine — matches how SAM actually loads it."""
    return _load_module("extraction_handler", REPO_ROOT / "backend/ingestion/extraction/app/handler.py")


@pytest.fixture(scope="session")
def nlp_module():
    """nlpProcessing checks config.nlp_engine_mode at cold start (D-13), so it
    must be imported with a mocked DynamoDB already serving that row. Loading
    spaCy is slow, so this is session-scoped — imported once for the whole run."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-south-1")
        ddb.create_table(
            TableName=CONFIG_TABLE,
            KeySchema=[{"AttributeName": "config_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "config_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.Table(CONFIG_TABLE).put_item(
            Item={"config_key": "nlp_engine_mode", "config_value": "spacy_hybrid"}
        )
        module = _load_module("nlp_handler", REPO_ROOT / "backend/ingestion/nlp/handler.py")
    return module


def create_core_tables(ddb) -> None:
    """Creates jobs/candidates/failed_jobs tables matching template.yaml's
    key schema (Architecture.md §6) — used by every test that needs a fresh
    moto backend (each @mock_aws invocation starts empty)."""
    ddb.create_table(
        TableName=JOBS_TABLE,
        KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName=CANDIDATES_TABLE,
        KeySchema=[
            {"AttributeName": "job_id", "KeyType": "HASH"},
            {"AttributeName": "candidate_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "job_id", "AttributeType": "S"},
            {"AttributeName": "candidate_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName=FAILED_JOBS_TABLE,
        KeySchema=[
            {"AttributeName": "job_id", "KeyType": "HASH"},
            {"AttributeName": "failure_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "job_id", "AttributeType": "S"},
            {"AttributeName": "failure_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "resumes"
JDS_DIR = REPO_ROOT / "tests" / "fixtures" / "jds"
