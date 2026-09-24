"""API response envelope, error type, and the decorator every API Lambda uses
(docs/03-scoring-and-api.md §3.4; Rules R-ERR-05, R-AUTH-06).

Handlers stay thin: authorize -> validate -> call rs_common -> respond. The
decorator turns HttpError into the documented error envelope and any other
exception into a generic 500 that never leaks internals (R-ERR-05).
"""

from __future__ import annotations

import base64
import binascii
import functools
import json
import os
import re

import boto3

from rs_common import clock, ids, log
from rs_common.ddb import from_decimal
from rs_common.errors import Stage

_ID_RE = {
    "job": re.compile(r"^job_[0-9a-f]{32}$"),
    "cand": re.compile(r"^cand_[0-9a-f]{32}$"),
}


class HttpError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": os.environ["ALLOWED_ORIGIN"],
            "Vary": "Origin",
        },
        "body": json.dumps(from_decimal(body)),
    }


def json_body(event) -> dict:
    """Parses the request body as a JSON object; anything else is a 400."""
    raw = event.get("body")
    if raw is None or raw == "":
        raise HttpError(400, "VALIDATION_FAILED", "Request body is required.")
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as e:
            raise HttpError(400, "VALIDATION_FAILED", "Request body is not valid.") from e
    try:
        body = json.loads(raw)
    except ValueError as e:
        raise HttpError(400, "VALIDATION_FAILED", "Request body must be valid JSON.") from e
    if not isinstance(body, dict):
        raise HttpError(400, "VALIDATION_FAILED", "Request body must be a JSON object.")
    return body


def path_id(event, name: str, kind: str) -> str:
    """Path IDs must have the exact server-generated shape; anything else is
    indistinguishable from 'not found' (R-AUTH-04) and never reaches DynamoDB."""
    value = (event.get("pathParameters") or {}).get(name, "")
    if not _ID_RE[kind].match(value):
        raise HttpError(404, "NOT_FOUND", "Not found.")
    return value


def query_param(event, name: str) -> str | None:
    return (event.get("queryStringParameters") or {}).get(name)


def encode_token(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_token(token: str, allowed_keys: set[str]) -> dict:
    """Pagination tokens are opaque to clients but still client-supplied, so
    the decoded key must be a flat dict of string values over an allowed key set."""
    try:
        padded = token + "=" * (-len(token) % 4)
        key = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, binascii.Error) as e:
        raise HttpError(400, "VALIDATION_FAILED", "Invalid next_token.") from e
    if not (
        isinstance(key, dict)
        and key
        and set(key) <= allowed_keys
        and all(isinstance(v, str) for v in key.values())
    ):
        raise HttpError(400, "VALIDATION_FAILED", "Invalid next_token.")
    return key


def _audit_api_failure(event, exc: Exception) -> None:
    """Best-effort failed_jobs row (stage=api). Never raises: a broken audit
    path must not turn one failure into two. Only the exception TYPE is
    recorded — request content is never included (R-PRIV-02)."""
    try:
        table = boto3.resource("dynamodb").Table(os.environ["FAILED_JOBS_TABLE"])
        job_id = (event.get("pathParameters") or {}).get("job_id") or "unknown"
        table.put_item(
            Item={
                "job_id": job_id,
                "failure_id": ids.failure_id(),
                "stage": str(Stage.API),
                "error_type": type(exc).__name__,
                "error_message": f"{type(exc).__name__} in {event.get('resource', 'api')}",
                "terminal": False,
                "retry_count": 0,
                "created_at": clock.now_iso(),
                "expires_at": clock.epoch_in_days(90),
            }
        )
    except Exception as audit_exc:  # noqa: BLE001 - deliberately swallowed, see docstring
        log.warning("api_audit_failed", stage="api", error_type=type(audit_exc).__name__)


def api_handler(fn):
    """authz -> fn(event, caller) -> (status, body) -> envelope."""

    @functools.wraps(fn)
    def wrapper(event, context):
        from rs_common.authz import caller

        try:
            return respond(*fn(event, caller(event)))
        except HttpError as e:
            err = {"code": e.code, "message": e.message}
            if e.details:
                err["details"] = e.details
            return respond(e.status, {"error": err})
        except Exception as e:  # noqa: BLE001 - the API's last line of defence
            log.error("unhandled", stage="api", error_type=type(e).__name__, path=event.get("resource"))
            _audit_api_failure(event, e)
            return respond(
                500, {"error": {"code": "INTERNAL", "message": "Something went wrong. Please try again."}}
            )

    return wrapper
