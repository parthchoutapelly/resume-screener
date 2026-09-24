"""Scoring fan-out (D-18): the single implementation shared by nlpProcessing
(when a JD finishes parsing) and, from phase 3, updateJob (when requirements
change). This is what lets scoreMatch simply ACK "job not scorable yet"
instead of retrying until it gives up — completion of the JD (or an edit)
re-triggers scoring for every already-parsed candidate directly, rather than
relying on redelivery timing.
"""

from __future__ import annotations

import json
import os

import boto3
from boto3.dynamodb.conditions import Key

_sqs = boto3.client("sqs")
_ddb = boto3.resource("dynamodb")


def enqueue_one(job_id: str, candidate_id: str, reason: str) -> None:
    _sqs.send_message(
        QueueUrl=os.environ["SCORING_QUEUE_URL"],
        MessageBody=json.dumps({"job_id": job_id, "candidate_id": candidate_id, "reason": reason}),
    )


def enqueue_rescore(job_id: str, reason: str) -> int:
    """Enqueues every PARSED candidate of the job. ConsistentRead is what
    makes the D-18 race argument hold: a candidate's own `parsed` write always
    happens-before this query can see it, so nothing is missed regardless of
    ordering between a resume finishing and the JD finishing."""
    table = _ddb.Table(os.environ["CANDIDATES_TABLE"])
    candidate_ids: list[str] = []
    kwargs = {
        "KeyConditionExpression": Key("job_id").eq(job_id),
        "ConsistentRead": True,
        "ProjectionExpression": "candidate_id, parse_status",
    }
    while True:
        page = table.query(**kwargs)
        candidate_ids += [i["candidate_id"] for i in page["Items"] if i.get("parse_status") == "parsed"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    for i in range(0, len(candidate_ids), 10):
        batch = candidate_ids[i : i + 10]
        entries = [
            {
                "Id": str(n),
                "MessageBody": json.dumps({"job_id": job_id, "candidate_id": c, "reason": reason}),
            }
            for n, c in enumerate(batch)
        ]
        resp = _sqs.send_message_batch(QueueUrl=os.environ["SCORING_QUEUE_URL"], Entries=entries)
        if resp.get("Failed"):
            raise RuntimeError(f"fan-out partial failure: {len(resp['Failed'])} of {len(entries)} entries")

    return len(candidate_ids)
