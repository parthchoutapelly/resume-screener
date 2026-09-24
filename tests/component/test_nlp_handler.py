"""Component tests for nlpProcessing (docs/02-ingestion-pipeline.md §10),
run against the REAL spaCy `en_core_web_sm` model — not a stub, per R-HON-03.
"""

from __future__ import annotations

import boto3
import pytest
from conftest import CANDIDATES_TABLE, JOBS_TABLE, create_core_tables
from moto import mock_aws

from rs_common.errors import EmptyDocumentError, OrphanRecordError


def _candidate_event(job_id, candidate_id, text, meta=None):
    return {
        "doc_type": "resume",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "extracted_text": text,
        "extraction_metadata": meta or {"file_type": "pdf_native", "page_count": 1, "ocr_pages": 0},
    }


def _jd_event(job_id, text):
    return {
        "doc_type": "jd",
        "job_id": job_id,
        "extracted_text": text,
        "extraction_metadata": {"file_type": "pdf_native"},
    }


@mock_aws
def test_resume_extracts_name_skills_titles_employer(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_1", "parse_status": "pending"}
    )
    sqs = boto3.client("sqs", region_name="ap-south-1")
    import os

    sqs.create_queue(QueueName="scoring")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring2")["QueueUrl"]

    # Prose sentences, not resume-fragment bullet style: en_core_web_sm's ORG
    # recognition on compact "Company - Title - Date" lines is unreliable
    # (verified empirically — a known, documented model limitation,
    # Memory.md §9), but it reliably tags a well-known company in a normal
    # sentence. R-HON-03 means this test must reflect what the real model
    # actually does, not an idealized extraction.
    text = (
        "Jane Doe\n"
        "jane.doe@example-mail.test\n\n"
        "Professional Experience\n"
        "Jane worked at Google as a Backend Developer from January 2021 to the present, "
        "building REST APIs in Python on AWS, and using SQL databases.\n\n"
        "Skills\nPython, AWS, SQL\n"
    )
    result = nlp_module.lambda_handler(_candidate_event("job_1", "cand_1", text), None)
    assert result == {"status": "parsed"}

    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_1"})["Item"]
    assert item["name"] == "Jane Doe"
    assert item["email"] == "jane.doe@example-mail.test"
    assert "python" in item["skills"]
    assert "aws" in item["skills"]
    assert "sql" in item["skills"]
    assert "Google" in item["employers"]
    assert item["parse_status"] == "parsed"
    assert item["file_type"] == "pdf_native"


@mock_aws
def test_employers_exclude_things_that_are_really_skills(nlp_module):
    """R-DATA-10: an ORG entity that normalizes to a known skill (e.g. a
    company named after a technology) is dropped from employers."""
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_2", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring3")["QueueUrl"]

    # "Kubernetes" verified (empirically) to tag reliably as ORG in prose —
    # a clean case to prove the R-DATA-10 filter itself, independent of the
    # small model's inconsistent tagging of "Docker" specifically (it tags
    # bare "Docker" as PERSON, not ORG, regardless of surrounding context).
    text = (
        "Alex Kim worked at Kubernetes as a Software Engineer from January 2019 to "
        "December 2021, using Docker extensively.\n\nSkills\nDocker, Kubernetes, Python\n"
    )
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_2", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_2"})["Item"]
    assert "kubernetes" in item["skills"]
    assert all("kubernetes" not in e.lower() for e in item.get("employers", []))


@mock_aws
def test_k8s_synonym_matches_and_normalizes_to_kubernetes(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_3", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring4")["QueueUrl"]

    text = "Sam Lee\n\nExperience\nAcme - Engineer - Jan 2020 to Dec 2021\n\nSkills\nk8s, Python, AWS\n"
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_3", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_3"})["Item"]
    assert "kubernetes" in item["skills"]
    assert "k8s" not in item["skills"]  # normalized, not left verbatim


@mock_aws
def test_bare_go_inside_prose_is_not_matched_as_a_skill(nlp_module):
    """Case-sensitive skill matcher: bare lowercase 'go' inside an ordinary
    sentence ('go to market') must NOT be matched as the Go language."""
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_4", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring5")["QueueUrl"]

    text = (
        "Taylor Swan\n\nExperience\nAcme - Marketing Manager - Jan 2019 to Dec 2020\n"
        "Helped the company go to market with new products.\n\nSkills\nMarketing, Sales\n"
    )
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_4", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_4"})["Item"]
    assert "go" not in item["skills"]


@mock_aws
def test_capitalized_go_is_matched_as_the_language(nlp_module):
    """The case-sensitive matcher catches 'Go' as a standalone capitalized
    token — the positive counterpart to the lowercase-prose test above."""
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_go", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring_go")["QueueUrl"]

    text = (
        "Morgan Reyes\n\nExperience\nAcme - Backend Engineer - Jan 2020 to Dec 2021\n"
        "Built microservices in Go and Python.\n\nSkills\nGo, Python, AWS\n"
    )
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_go", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_go"})["Item"]
    assert "go" in item["skills"]


@mock_aws
def test_jd_writes_only_derived_fields_not_required(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(JOBS_TABLE).put_item(
        Item={
            "job_id": "job_2",
            "parse_status": "pending",
            "required_skills": ["python", "aws"],  # explicit — must survive untouched
        }
    )
    text = "Backend Engineer\n\nWe are hiring a Backend Engineer with at least 3 years of experience.\nRequired skills: Python, AWS, DynamoDB.\n"
    result = nlp_module.lambda_handler(_jd_event("job_2", text), None)
    assert result == {"status": "parsed"}

    item = ddb.Table(JOBS_TABLE).get_item(Key={"job_id": "job_2"})["Item"]
    assert item["required_skills"] == ["python", "aws"]  # untouched (R-BUS-03, D-29)
    assert "dynamodb" in item["derived_skills"]
    assert item.get("derived_min_experience_years") == 3
    assert item["parse_status"] == "parsed"


@mock_aws
def test_jd_fanout_enqueues_only_parsed_candidates(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(JOBS_TABLE).put_item(Item={"job_id": "job_3", "parse_status": "pending"})
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_3", "candidate_id": "cand_a", "parse_status": "parsed"}
    )
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_3", "candidate_id": "cand_b", "parse_status": "pending"}
    )

    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    queue_url = sqs.create_queue(QueueName="scoring6")["QueueUrl"]
    os.environ["SCORING_QUEUE_URL"] = queue_url

    nlp_module.lambda_handler(_jd_event("job_3", "Backend Engineer\n\nRequired skills: Python.\n"), None)

    msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get("Messages", [])
    import json

    bodies = [json.loads(m["Body"]) for m in msgs]
    ids = {b["candidate_id"] for b in bodies}
    assert ids == {"cand_a"}  # only the already-parsed one


@mock_aws
def test_empty_document_raises_empty_document_error(nlp_module):
    with pytest.raises(EmptyDocumentError):
        nlp_module.lambda_handler(_candidate_event("job_x", "cand_x", "     \n\n\t  "), None)


@mock_aws
def test_missing_candidate_placeholder_raises_orphan_record_error(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    # No placeholder item created for cand_missing.
    with pytest.raises(OrphanRecordError):
        nlp_module.lambda_handler(
            _candidate_event("job_1", "cand_missing", "Some real resume text here."), None
        )


@mock_aws
def test_missing_job_placeholder_raises_orphan_record_error(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    with pytest.raises(OrphanRecordError):
        nlp_module.lambda_handler(_jd_event("job_missing", "Some job description text here."), None)


@mock_aws
def test_no_email_found_removes_attribute_not_writes_empty_string(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_5", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring7")["QueueUrl"]

    text = "Jordan Blake\n\nExperience\nAcme - Analyst - Jan 2020 to Dec 2021\n\nSkills\nExcel, SQL\n"
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_5", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_5"})["Item"]
    assert "email" not in item


@mock_aws
def test_unknown_experience_omits_attribute_not_zero(nlp_module):
    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    create_core_tables(ddb)
    ddb.Table(CANDIDATES_TABLE).put_item(
        Item={"job_id": "job_1", "candidate_id": "cand_6", "parse_status": "pending"}
    )
    import os

    sqs = boto3.client("sqs", region_name="ap-south-1")
    os.environ["SCORING_QUEUE_URL"] = sqs.create_queue(QueueName="scoring8")["QueueUrl"]

    text = "Riley Chen\n\nSummary\nA passionate professional.\n\nSkills\nPython\n"
    nlp_module.lambda_handler(_candidate_event("job_1", "cand_6", text), None)
    item = ddb.Table(CANDIDATES_TABLE).get_item(Key={"job_id": "job_1", "candidate_id": "cand_6"})["Item"]
    assert "total_experience_years" not in item  # R-HON-09: unknown, never 0
