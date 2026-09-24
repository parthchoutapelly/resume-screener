"""PATCH /jobs/{job_id} — edit requirements/threshold, then re-score.

Re-scoring only refreshes scores, explanation and the Recommended flag; it
never touches `decision` or `notification_*` and never emails (R-BUS-05).
"""

import os

import boto3
from botocore.exceptions import ClientError

from rs_common import clock, fanout, log, validate, views
from rs_common.authz import Caller, load_job_for
from rs_common.ddb import to_decimal
from rs_common.http import HttpError, api_handler, json_body, path_id
from rs_common.requirements import scorable

_JOBS = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE"])


@api_handler
def lambda_handler(event, caller: Caller):
    job_id = path_id(event, "job_id", "job")
    load_job_for(caller, job_id)
    fields = validate.update_job(json_body(event))

    names = {f"#f{i}": k for i, k in enumerate(fields)}
    values = {f":v{i}": to_decimal(v) for i, v in enumerate(fields.values())}
    sets = [f"#f{i} = :v{i}" for i in range(len(fields))]
    sets += ["requirements_confirmed = :true", "updated_at = :now"]
    try:
        job = _JOBS.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={**values, ":true": True, ":now": clock.now_iso()},
            ConditionExpression="attribute_exists(job_id)",
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HttpError(404, "NOT_FOUND", "Job not found.") from e
        raise

    enqueued = fanout.enqueue_rescore(job_id, "requirements_changed") if scorable(job) else 0
    log.info("job_updated", stage="api", job_id=job_id, fields=sorted(fields), rescore_enqueued=enqueued)
    return 200, {**views.job_view(job), "rescore_enqueued": enqueued}
