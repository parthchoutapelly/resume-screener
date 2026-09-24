"""Unit tests for rs_common.fanout (D-18 scoring readiness fan-out)."""

import json
import os

import boto3
from moto import mock_aws

from rs_common import fanout


@mock_aws
def test_enqueue_one_sends_expected_message():
    sqs = boto3.client("sqs", region_name="ap-south-1")
    queue_url = sqs.create_queue(QueueName="scoring")["QueueUrl"]
    os.environ["SCORING_QUEUE_URL"] = queue_url

    fanout.enqueue_one("job_1", "cand_1", "candidate_parsed")

    msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)["Messages"]
    assert len(msgs) == 1
    body = json.loads(msgs[0]["Body"])
    assert body == {"job_id": "job_1", "candidate_id": "cand_1", "reason": "candidate_parsed"}


@mock_aws
def test_enqueue_rescore_only_includes_parsed_candidates():
    sqs = boto3.client("sqs", region_name="ap-south-1")
    queue_url = sqs.create_queue(QueueName="scoring")["QueueUrl"]
    os.environ["SCORING_QUEUE_URL"] = queue_url

    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    table = ddb.create_table(
        TableName="candidates-test",
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
    os.environ["CANDIDATES_TABLE"] = "candidates-test"

    table.put_item(Item={"job_id": "job_1", "candidate_id": "cand_1", "parse_status": "parsed"})
    table.put_item(Item={"job_id": "job_1", "candidate_id": "cand_2", "parse_status": "pending"})
    table.put_item(Item={"job_id": "job_1", "candidate_id": "cand_3", "parse_status": "parsed"})
    table.put_item(Item={"job_id": "job_1", "candidate_id": "cand_4", "parse_status": "error"})
    table.put_item(Item={"job_id": "job_2", "candidate_id": "cand_5", "parse_status": "parsed"})  # other job

    n = fanout.enqueue_rescore("job_1", "job_ready")
    assert n == 2

    msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)["Messages"]
    bodies = [json.loads(m["Body"]) for m in msgs]
    ids = {b["candidate_id"] for b in bodies}
    assert ids == {"cand_1", "cand_3"}
    assert all(b["job_id"] == "job_1" and b["reason"] == "job_ready" for b in bodies)


@mock_aws
def test_enqueue_rescore_returns_zero_for_no_parsed_candidates():
    sqs = boto3.client("sqs", region_name="ap-south-1")
    queue_url = sqs.create_queue(QueueName="scoring")["QueueUrl"]
    os.environ["SCORING_QUEUE_URL"] = queue_url

    ddb = boto3.resource("dynamodb", region_name="ap-south-1")
    ddb.create_table(
        TableName="candidates-test",
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
    os.environ["CANDIDATES_TABLE"] = "candidates-test"

    n = fanout.enqueue_rescore("job_empty", "job_ready")
    assert n == 0
