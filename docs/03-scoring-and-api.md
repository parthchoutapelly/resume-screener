# PHASE 3 of 5 — Scoring Engine, Recruiter API & Reliability
### Project: AI-Powered Resume Screener & Talent Acquisition Pipeline

| | |
|---|---|
| **Covers** | `Tasks.md` E5 (T-050–T-052), E6 (T-060–T-069), E7 (T-070–T-073) |
| **Owner** | Allen |
| **Prerequisites** | Phase 2 DoD fully checked: real `jobs`/`candidates` records and ScoringQueue messages exist |
| **Read first** | `Architecture.md` §3.3–3.5, §5, §7, §8, §11 · `Rules.md` §2, §4, §5, §7 · `Design.md` §6 (status copy the API must support) |
| **Produces** | Scoring with a stored explanation; the complete REST API (10 routes) behind Cognito + CORS; dlqHandler; alarms; a deploy runbook |
| **Hands off to** | `04-frontend-dashboard.md` |

> **Agent instructions.** Scoring and the API operate only on structured DynamoDB records and never know which extraction/NLP engine produced them. That independence is what keeps the Textract/Comprehend migration path open (`Details.md` §2). Every handler is thin: `authorize → validate → call rs_common → respond`. Put logic in `rs_common` so it's unit-testable and shared. Where `Implementation.md` or older text differs, this file wins (`Memory.md` §7).

---

## 1. Guardrails for this phase

- **R-BUS-04/D-18:** scoring never retries because a job isn't ready. It acknowledges, and the JD fan-out or a PATCH re-triggers it.
- **R-BUS-06/07/08:** only a human decision sends email, at most once, and email failure never fails the decision.
- **R-BUS-09:** scoring reads only skills, titles, and experience.
- **R-AUTH-01..07:** group required on every route; job ownership with 404; Admin-only failures.
- **R-DATA-01/02:** Decimal in, float math, Decimal out; never write NULL scores.
- **R-SEC-07/09:** CORS allowlist; CSV formula escaping.

## 2. Permissions to add this phase

- **Deploy user:** `apigateway:*` on this stack's APIs (`arn:aws:apigateway:ap-south-1::/restapis*`), `ses:GetAccount`, `ses:GetEmailIdentity`, `cloudwatch:PutMetricAlarm`/`DeleteAlarms` (if not already present).
- **Execution roles:** exactly the `Architecture.md` §8.1 matrix. §9 shows the SES specifics.

## 3. `rs_common` additions (T-025–T-029, T-052)

### 3.1 `requirements.py`
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Effective:
    skills: list[str]; titles: list[str]; min_experience_years: float

def effective(job) -> Effective:
    skills = list(job["required_skills"]) if job.get("required_skills") else list(job.get("derived_skills", []))
    titles = list(job["required_titles"]) if "required_titles" in job else list(job.get("derived_titles", []))
    if "min_experience_years" in job:           min_exp = job["min_experience_years"]
    else:                                       min_exp = job.get("derived_min_experience_years", 0)
    return Effective(sorted(skills), sorted(titles), float(min_exp))

def sources(job) -> dict:
    def src(explicit_present, derived_present): return "recruiter" if explicit_present else ("jd" if derived_present else None)
    return {"skills": src(bool(job.get("required_skills")), bool(job.get("derived_skills"))),
            "titles": src("required_titles" in job, "derived_titles" in job),
            "min_experience_years": src("min_experience_years" in job, "derived_min_experience_years" in job)}

def blocking_reason(job) -> str | None:
    confirmed = bool(job.get("requirements_confirmed"))
    status = job.get("parse_status")
    if status == "pending" and not confirmed: return "awaiting_jd"
    if status == "error" and not confirmed:   return "jd_failed"
    if not effective(job).skills:             return "no_required_skills"
    return None

def scorable(job) -> bool:
    return blocking_reason(job) is None
```

### 3.2 `scoring.py` (pure; version `v1`)
```python
from dataclasses import dataclass
from rs_common import normalization as norm
from rs_common.requirements import effective

W_SKILLS, W_TITLE, W_EXP = 0.5, 0.3, 0.2
SCORING_VERSION = "v1"

@dataclass(frozen=True)
class ScoreResult:
    match_score: float; skills_score: float; title_score: float; experience_score: float
    matched_skills: list[str]; missing_skills: list[str]
    title_match_type: str; title_match_held: str | None; title_match_required: str | None
    recommended: bool

def score(candidate: dict, job: dict) -> ScoreResult:
    """Precondition: scorable(job). Reads ONLY skills, titles_held, total_experience_years (R-BUS-09)."""
    eff = effective(job)
    req, have = set(eff.skills), set(candidate.get("skills", []))
    matched, missing = sorted(req & have), sorted(req - have)
    s_skills = len(matched) / len(req) * 100
    s_title, t_type, t_held, t_req = score_title(candidate.get("titles_held", []), eff.titles)
    yrs = candidate.get("total_experience_years")
    s_exp = score_experience(None if yrs is None else float(yrs), eff.min_experience_years)
    match = W_SKILLS * s_skills + W_TITLE * s_title + W_EXP * s_exp       # from UNROUNDED sub-scores
    match_r = round(match, 1)
    return ScoreResult(match_r, round(s_skills, 1), round(s_title, 1), round(s_exp, 1), matched, missing,
                       t_type, t_held, t_req, match_r >= float(job.get("shortlist_threshold", 70)))

def score_title(held, required):
    if not required:
        return 100.0, "not_required", None, None
    held_n = sorted({norm.normalize_title(t) for t in held}); req_n = sorted({norm.normalize_title(t) for t in required})
    for r in req_n:
        if r in held_n:
            return 100.0, "exact", r, r
    for r in req_n:
        for h in held_n:
            if any(h in fam and r in fam for fam in norm.title_families()):
                return 60.0, "related", h, r
    return 0.0, "none", None, None

def score_experience(years: float | None, min_years: float) -> float:
    if min_years <= 0:  return 100.0
    if years is None:   return 0.0              # UI shows "Unknown" (R-HON-09)
    return min(100.0, years / min_years * 100)
```
**Worked example (must be a unit test):** required skills `[python, aws, dynamodb]`, title `backend engineer`, 3 years; candidate skills `[python, aws, sql]`, titles `[backend developer]`, 4.0 years → skills 66.7, title 60 (related, via `title_families.json`), experience 100 → **71.3**, recommended at threshold 70.

### 3.3 `status.py`
Implements `Architecture.md` §7.2 exactly: `display_status(candidate, job, now) -> (status, error_code | None)` and `sort_key(row)`. One unit test per table row, plus boundary tests at `upload_expires_at + 2 min` and `ingest_started_at + 60 min`.

### 3.4 `authz.py` + `http.py`
```python
# authz.py
import os, re, boto3
from dataclasses import dataclass
from rs_common.http import HttpError
_JOBS = boto3.resource("dynamodb").Table(os.environ.get("JOBS_TABLE", "unset"))

@dataclass(frozen=True)
class Caller:
    sub: str; groups: frozenset[str]
    @property
    def is_admin(self): return "Admin" in self.groups

def caller(event) -> Caller:
    claims = event["requestContext"]["authorizer"]["claims"]
    raw = claims.get("cognito:groups", "")
    groups = frozenset(raw) if isinstance(raw, list) else frozenset(re.findall(r"[A-Za-z0-9_-]+", raw))  # tolerant parsing
    c = Caller(claims["sub"], groups)
    if not c.groups & {"Recruiter", "Admin"}:
        raise HttpError(403, "FORBIDDEN", "Your account has no access. Contact an administrator.")      # R-AUTH-02
    return c

def require_admin(c: Caller):
    if not c.is_admin:
        raise HttpError(403, "FORBIDDEN", "Admin access required.")                                   # R-AUTH-05

def load_job_for(c: Caller, job_id: str) -> dict:
    job = _JOBS.get_item(Key={"job_id": job_id}).get("Item")
    if not job or (job["recruiter_id"] != c.sub and not c.is_admin):
        raise HttpError(404, "NOT_FOUND", "Job not found.")                                           # R-AUTH-03/04
    return job
```
```python
# http.py
import json, os, traceback
from rs_common import log
from rs_common.ddb import from_decimal

class HttpError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message); self.status, self.code, self.message, self.details = status, code, message, details

def respond(status: int, body: dict) -> dict:
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json", "Cache-Control": "no-store",
                        "Access-Control-Allow-Origin": os.environ["ALLOWED_ORIGIN"], "Vary": "Origin"},
            "body": json.dumps(from_decimal(body))}

def api_handler(fn):
    """Decorator for every API Lambda: authz → fn → envelope. Unexpected errors → generic 500 + best-effort audit."""
    def wrapper(event, context):
        from rs_common.authz import caller
        try:
            return respond(*fn(event, caller(event)))
        except HttpError as e:
            err = {"code": e.code, "message": e.message}
            if e.details: err["details"] = e.details
            return respond(e.status, {"error": err})
        except Exception as e:
            log.error("unhandled", stage="api", error_type=type(e).__name__, path=event.get("resource"))
            _audit_api_failure(event, e)                  # PutItem failed_jobs stage=api; swallow its own errors
            return respond(500, {"error": {"code": "INTERNAL", "message": "Something went wrong. Please try again."}})
    return wrapper
```
Request validation: a small hand-written validator per route in `rs_common/validate.py` (types, lengths, enums, unknown-field rejection, R-VAL-01..03/09). No new dependency.

## 4. `scoreMatch` (T-050–T-051)

```python
# backend/scoring/score_match/handler.py
import json, os, boto3
from rs_common import clock, ids, log, scoring
from rs_common.ddb import conditional_update, to_decimal
from rs_common.errors import Stage, safe_message
from rs_common.requirements import scorable

_ddb = boto3.resource("dynamodb")
JOBS, CANDIDATES = _ddb.Table(os.environ["JOBS_TABLE"]), _ddb.Table(os.environ["CANDIDATES_TABLE"])
FAILED = _ddb.Table(os.environ["FAILED_JOBS_TABLE"])

def lambda_handler(event, context):
    for record in event["Records"]:                                      # BatchSize = 1
        msg = json.loads(record["body"])
        job_id, cand_id = msg["job_id"], msg["candidate_id"]
        try:
            score_one(job_id, cand_id, msg.get("reason"))
        except Exception as e:                                           # genuine failure → audit + SQS retry (≤5)
            FAILED.put_item(Item={"job_id": job_id, "failure_id": ids.failure_id(), "candidate_id": cand_id,
                "stage": str(Stage.SCORING), "error_type": type(e).__name__, "error_message": safe_message(e),
                "terminal": False, "retry_count": int(record["attributes"].get("ApproximateReceiveCount", "1")),
                "created_at": clock.now_iso(), "expires_at": clock.epoch_in_days(90)})
            raise

def score_one(job_id, cand_id, reason):
    job = JOBS.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
    cand = CANDIDATES.get_item(Key={"job_id": job_id, "candidate_id": cand_id}, ConsistentRead=True).get("Item")
    if not cand or cand.get("parse_status") != "parsed":
        log.info("skip_not_parsed", stage="scoring", job_id=job_id, candidate_id=cand_id); return        # ack (R-ERR-04)
    if not job or not scorable(job):
        log.info("skip_job_not_scorable", stage="scoring", job_id=job_id, candidate_id=cand_id); return  # ack — fan-out re-triggers (D-18)
    r = scoring.score(cand, job)
    ok = conditional_update(CANDIDATES, Key={"job_id": job_id, "candidate_id": cand_id},
        UpdateExpression=("SET match_score=:m, skills_score=:s, title_score=:ti, experience_score=:e, "
                          "matched_skills=:ms, missing_skills=:mi, title_match_type=:tt, shortlist_candidate=:rec, "
                          "scoring_version=:v, scored_at=:t, score_status=:ss, updated_at=:t "
                          + ("" if r.title_match_held is None else ", title_match_held=:th, title_match_required=:tr")),
        ConditionExpression="parse_status = :parsed",
        ExpressionAttributeValues={":m": to_decimal(r.match_score), ":s": to_decimal(r.skills_score),
            ":ti": to_decimal(r.title_score), ":e": to_decimal(r.experience_score), ":ms": r.matched_skills,
            ":mi": r.missing_skills, ":tt": r.title_match_type, ":rec": r.recommended, ":v": scoring.SCORING_VERSION,
            ":t": clock.now_iso(), ":ss": "scored", ":parsed": "parsed",
            **({} if r.title_match_held is None else {":th": r.title_match_held, ":tr": r.title_match_required})})
    log.info("scored" if ok else "score_skipped_state_changed", stage="scoring", job_id=job_id,
             candidate_id=cand_id, reason=reason, match_score=r.match_score)
```
Rescoring **never** touches `decision` or `notification_*` (R-BUS-05). When `title_match_type` is `none` or `not_required`, the stale `title_match_held/required` from an earlier score should be removed: add a `REMOVE` clause in that branch.

```yaml
ScoreMatchFunction:
  Properties:
    CodeUri: backend/scoring/score_match/
    Handler: handler.lambda_handler
    Timeout: 10
    MemorySize: 256
    Layers: [!Ref CommonLayer]
    Environment: {Variables: {JOBS_TABLE: !Ref JobsTable, CANDIDATES_TABLE: !Ref CandidatesTable, FAILED_JOBS_TABLE: !Ref FailedJobsTable}}
    Events:
      Scoring:
        Type: SQS
        Properties: {Queue: !GetAtt ScoringQueue.Arn, BatchSize: 1, ScalingConfig: {MaximumConcurrency: 2}}
```

## 5. API Gateway (T-060)

```yaml
RecruiterApi:
  Type: AWS::Serverless::Api
  Properties:
    StageName: !Ref EnvName
    Cors:
      AllowOrigin: !Sub "'https://${WebDistribution.DomainName}'"      # single origin; dev uses the Vite proxy
      AllowMethods: "'GET,POST,PATCH,OPTIONS'"
      AllowHeaders: "'Authorization,Content-Type'"
      MaxAge: "'600'"
    Auth:
      DefaultAuthorizer: CognitoAuth
      AddDefaultAuthorizerToCorsPreflight: false                        # preflight must not need a token (R-SEC-07)
      Authorizers:
        CognitoAuth: {UserPoolArn: !GetAtt UserPool.Arn, Identity: {Header: Authorization}}
    GatewayResponses:                                                    # 401/403/429/5xx from the gateway still carry CORS
      DEFAULT_4XX: {ResponseParameters: {Headers: {Access-Control-Allow-Origin: !Sub "'https://${WebDistribution.DomainName}'"}}}
      DEFAULT_5XX: {ResponseParameters: {Headers: {Access-Control-Allow-Origin: !Sub "'https://${WebDistribution.DomainName}'"}}}
    MethodSettings:
      - {ResourcePath: "/*", HttpMethod: "*", ThrottlingRateLimit: 20, ThrottlingBurstLimit: 40}
```
- The client sends the **raw ID token** in `Authorization` (no `Bearer ` prefix). That's the form the REST Cognito authorizer is documented to accept. Only switch to `Bearer` if you verify the authorizer accepts it.
- Every API function gets the env vars `ALLOWED_ORIGIN: !Sub "https://${WebDistribution.DomainName}"`, `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE`, plus its route-specific ones, and `Layers: [!Ref CommonLayer]`.
- Output `ApiBaseUrl: !Sub "https://${RecruiterApi}.execute-api.${AWS::Region}.amazonaws.com/${EnvName}"`.
- Optional access logging needs the account-level API Gateway CloudWatch role (`AWS::ApiGateway::Account`). Add it only if you want access logs; function logs already cover the audit needs.

## 6. Routes & handlers (T-061–T-069)

Shapes: `Architecture.md` §5.1. Error codes: §5.2. Every handler is wrapped in `@api_handler`.

| Route | Handler | Logic (in order) | Extra env / IAM |
|---|---|---|---|
| `POST /jobs` | create_job_posting | validate (R-VAL-01..03) → normalize explicit skills/titles → `job_id` → Put job (`parse_status` = `pending` if the JD is file/text, else `not_applicable`; `jd_source`; explicit fields only when supplied; `requirements_confirmed=false`) → batch-write candidate placeholders (`parse_status=pending`, `score_status=pending`, `decision=pending`, `original_filename`, `resume_s3_key`, `upload_expires_at`) → **then** write `jd.txt` if the source is text → presigned POSTs → 201 | `UPLOAD_BUCKET`; S3 Put on `jd-uploads/*`, `resume-uploads/*` |
| `POST /jobs/{job_id}/resumes` | add_resumes | `load_job_for` → count existing (`Select=COUNT`) + new ≤ 200 → placeholders → POSTs → 201 | same |
| `GET /jobs` | get_jobs | Recruiter: Query `RecruiterJobsIndex` desc, Limit 50; Admin: Scan Limit 50 (sort page by `created_at`). Each row: `job_id, job_title, jd_source, parse_status, scorable, blocking_reason, created_at` (+`recruiter_id` for Admin). `next_token` = base64url(JSON `LastEvaluatedKey`) | — |
| `GET /jobs/{job_id}` | get_job | `load_job_for` → job + `effective`, `sources`, `derived`, `scorable`, `blocking_reason` | — |
| `PATCH /jobs/{job_id}` | update_job | `load_job_for` → validate subset (`required_skills` non-empty if present; `required_titles` may be `[]` meaning "no title requirement"; `min_experience_years` 0–50; `shortlist_threshold` 0–100) → normalize → SET fields + `requirements_confirmed=true` → if scorable: `fanout.enqueue_rescore(job_id, "requirements_changed")` → 200 job + `rescore_enqueued` | `SCORING_QUEUE_URL`; Candidates Query, SQS Send |
| `GET /jobs/{job_id}/candidates` | get_candidates_by_job | `load_job_for` → paginated base-table Query → map rows (public fields only: never `resume_s3_key`, `ingest_started_at`) → `display_status` → sort → 200 | — |
| `POST …/decision` | update_candidate_decision | §6.1 | `SES_SENDER_ADDRESS`; SES |
| `GET …/resume-url` | get_resume_url | behind the flag `FEATURE_RESUME_VIEW` (OQ8) → `load_job_for` → candidate exists → presigned GET 60 s with `ResponseContentDisposition=inline; filename="<sanitized original>"` | S3 Get on `resume-uploads/*` |
| `GET /jobs/{job_id}/export` | export_shortlist_csv | `load_job_for` → Query → `decision=shortlisted` → sort by score desc → CSV (§6.2) → Put `exports/{job_id}/{ts}.csv` → presigned GET 5 min → `{download_url, row_count}` | S3 Put/Get on `exports/*` |
| `GET /failed-jobs` | get_failed_jobs | `require_admin` → `?job_id=` Query (desc by `failure_id` is not chronological, so sort by `created_at`) or Scan Limit 100 with `next_token` → rows incl. `raw_payload`, `terminal`, `retry_count` | FailedJobs Query/Scan |

**Presigned POST (R-SEC-03).** Use a regional, virtual-host S3 client, so the URL matches the CSP and the bucket CORS:
```python
s3 = boto3.client("s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                  config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tiff": "image/tiff",
                 "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
post = s3.generate_presigned_post(Bucket=BUCKET, Key=key, Fields={"Content-Type": ctype},
                                  Conditions=[{"Content-Type": ctype}, ["content-length-range", 1, 10_485_760]],
                                  ExpiresIn=900)          # policy pins the exact key automatically
```
**Ordering matters:** items are written **before** any upload credential or `jd.txt` exists. Otherwise extraction can race ahead and classify the object as orphaned.

### 6.1 Decision + email (R-BUS-06..08, D-28)
```
1. body.decision ∈ {shortlisted, rejected, pending}; job = load_job_for(caller, job_id); candidate must exist (else 404)
2. UpdateItem SET decision, decided_by=sub, decided_at   COND score_status = :scored       → fail ⇒ 409 NOT_SCORED
3. if decision != shortlisted → return {decision, notification_status: <current or null>}
4. if no candidate.email → conditional SET notification_status = skipped_no_email (only if attribute_not_exists) → return
5. claim: SET notification_status = sending   COND attribute_not_exists(notification_status) OR notification_status = :failed
      claim fails ⇒ already sent/sending/skipped ⇒ return current status (no email)
6. sesv2.send_email(FromEmailAddress=SES_SENDER_ADDRESS, Destination={ToAddresses:[email]},
      Content={Simple:{Subject:"You've been shortlisted — {job_title}", Body:{Text: greeting + fixed template}}})
      greeting = f"Hi {name}," if name else "Hello,"                       (Design §6)
7. success → SET notification_status = sent, notification_sent_at
   failure → SET notification_status = failed; audit row stage=api (no email address in the message); still 200
```

### 6.2 CSV (R-BUS-12, R-SEC-09)
Columns: `name, email, skills, titles_held, total_experience_years, match_score, decided_at`. Lists are joined with `; `. Every cell goes through:
```python
def csv_safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
```
Upload with `ContentType="text/csv; charset=utf-8"` and write a UTF-8 BOM so Excel renders non-ASCII names correctly.

## 7. dlqHandler (T-070)

```python
# backend/reliability/dlq_handler/handler.py
import json, os, time, boto3
from urllib.parse import unquote_plus
from rs_common import clock, ids, log
from rs_common.ddb import conditional_update
from rs_common.errors import ErrorCode, Stage

_ddb = boto3.resource("dynamodb")
JOBS, CANDIDATES = _ddb.Table(os.environ["JOBS_TABLE"]), _ddb.Table(os.environ["CANDIDATES_TABLE"])
FAILED = _ddb.Table(os.environ["FAILED_JOBS_TABLE"])
INGESTION_DLQ_ARN = os.environ["INGESTION_DLQ_ARN"]           # compare ARNs exactly — no substring matching

def lambda_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        if record["eventSourceARN"] == INGESTION_DLQ_ARN:
            if body.get("Event") == "s3:TestEvent": continue
            for rec in body.get("Records", []):
                on_ingestion_exhausted(unquote_plus(rec["s3"]["object"]["key"]), record["body"])
        else:
            on_scoring_exhausted(body.get("job_id"), body.get("candidate_id"), record["body"])

def audit(job_id, cand_id, stage, max_receive, raw):
    item = {"job_id": job_id or "unknown", "failure_id": ids.failure_id(), "stage": str(stage), "terminal": True,
            "error_type": "RetriesExhausted", "error_message": f"Exceeded maxReceiveCount={max_receive}; see earlier attempt rows",
            "retry_count": max_receive, "raw_payload": raw, "created_at": clock.now_iso(), "expires_at": clock.epoch_in_days(90)}
    if cand_id: item["candidate_id"] = cand_id
    FAILED.put_item(Item=item)
    emit_metric("ingestion" if stage == Stage.INGESTION_EXHAUSTED else "scoring")

def on_ingestion_exhausted(key, raw):
    parts = key.split("/")
    job_id, cand_id = (parts[1], None) if parts[0] == "jd-uploads" and len(parts) == 3 else \
                      (parts[1], parts[2]) if parts[0] == "resume-uploads" and len(parts) == 4 else (None, None)
    audit(job_id, cand_id, Stage.INGESTION_EXHAUSTED, 3, raw)
    if job_id:
        table, k = (CANDIDATES, {"job_id": job_id, "candidate_id": cand_id}) if cand_id else (JOBS, {"job_id": job_id})
        conditional_update(table, Key=k, UpdateExpression="SET parse_status=:e, error_code=:c, updated_at=:t",
            ConditionExpression="attribute_exists(job_id) AND parse_status <> :p",          # never regress (D-40)
            ExpressionAttributeValues={":e": "error", ":c": str(ErrorCode.PROCESSING_FAILED), ":p": "parsed", ":t": clock.now_iso()})

def on_scoring_exhausted(job_id, cand_id, raw):
    audit(job_id, cand_id, Stage.SCORING_EXHAUSTED, 5, raw)
    if job_id and cand_id:
        conditional_update(CANDIDATES, Key={"job_id": job_id, "candidate_id": cand_id},
            UpdateExpression="SET score_status=:e, error_code=:c, updated_at=:t",           # score_status, NOT parse_status (D-17)
            ConditionExpression="attribute_exists(candidate_id) AND score_status <> :s",
            ExpressionAttributeValues={":e": "error", ":c": str(ErrorCode.SCORING_FAILED), ":s": "scored", ":t": clock.now_iso()})

def emit_metric(queue):   # CloudWatch Embedded Metric Format via stdout — no PutMetricData permission needed
    print(json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [{"Namespace": "ResumeScreener",
          "Dimensions": [["Queue"]], "Metrics": [{"Name": "TerminalFailures", "Unit": "Count"}]}]},
          "Queue": queue, "TerminalFailures": 1}))
```
Wire both DLQs as `Events` (BatchSize 1). Env: `INGESTION_DLQ_ARN: !GetAtt IngestionDLQ.Arn`. Verify in T-071 that the EMF metric appears under the Lambda JSON log format. If it doesn't, switch to `cloudwatch:PutMetricData` with a `cloudwatch:namespace = ResumeScreener` condition.

## 8. Alarms (T-071)

All alarms → `AlertsTopic`, period 300 s, `TreatMissingData: notBreaching`.

| Alarm | Metric | Threshold |
|---|---|---|
| TerminalFailures | `ResumeScreener/TerminalFailures` (Sum, per Queue) | ≥ 1 |
| IngestionDLQReceived / ScoringDLQReceived | `AWS/SQS NumberOfMessagesReceived` on each DLQ | ≥ 1 (backup to the above) |
| FunctionErrors | `AWS/Lambda Errors` for Extraction, Nlp, ScoreMatch, DlqHandler | ≥ 1 |
| FunctionThrottles | `AWS/Lambda Throttles` for Extraction, Nlp, ScoreMatch | ≥ 1 |
| Api5xx | `AWS/ApiGateway 5XXError` (ApiName, Stage) | ≥ 1 |

**Do not** alarm on DLQ `ApproximateNumberOfMessagesVisible`: dlqHandler drains the DLQs immediately, so it always reads 0 (D-32).

## 9. SES specifics

- The sender comes from the stack parameter `SesSenderAddress` → env `SES_SENDER_ADDRESS`. It's never hardcoded.
- IAM: `ses:SendEmail` with `Condition: {StringEquals: {"ses:FromAddress": <sender>}}`. In sandbox, SES also authorizes against the **recipient** identities, so scope `Resource` to `arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/*` (account-scoped) rather than only the sender ARN, and keep the `FromAddress` condition as the tight control.
- Sandbox: only verified recipients receive mail (T-004). Test that explicitly before the phase 5 demo run.

## 10. Testing

| Level | Cases |
|---|---|
| Unit (`rs_common`) | scoring: worked example 71.3; 0/partial/full skill overlap; exact/related/none/not-required title; `min_exp = 0`; unknown years; over-qualified capped at 100; Decimal inputs; rounding from unrounded sub-scores · requirements: every `parse_status` × `requirements_confirmed` × skills-present combination → `blocking_reason` · status: each `display_status` row + time boundaries · authz: groupless, Recruiter-own, Recruiter-other (404), Admin, groups-claim formats · csv_safe |
| Component (moto) | scoreMatch: not parsed → ack, no write; not scorable → ack; scorable → all fields written as Decimal; state changed mid-flight → conditional skip; exception → audit + raise · each API handler's happy path + every error code · decision: shortlist→reject→shortlist → exactly 1 SES call; no email → `skipped_no_email`; SES error → `failed`, still 200 · dlqHandler: redelivered message → no regression; ARN routing |
| Deployed (`dev`) | curl with a real ID token for each route; preflight without a token → 200 with CORS headers; bad token → 401 **with** `Access-Control-Allow-Origin`; oversized presigned POST rejected by S3; JD-after-resumes → all scored without any `scoring` failure rows |

## 11. Definition of Done

- [ ] Worked example scores 71.3 in unit tests and on a deployed candidate
- [ ] Resumes uploaded **before** the JD are scored automatically after it parses; `failed_jobs` has **no** `scoring` rows for this
- [ ] A job with `jd.source=none` and explicit skills scores immediately; a job whose JD yields no skills shows `blocking_reason=no_required_skills` and scores nothing until PATCHed
- [ ] PATCH requirements → rescore; `decision` and `notification_status` unchanged on every candidate
- [ ] `GET /jobs/{id}/candidates` returns **every** candidate, including `processing`, `upload_missing`, `error`, with correct `display_status` and sort
- [ ] Shortlist → reject → shortlist sends **exactly one** email; a missing email → `skipped_no_email`; the decision on an unscored candidate → 409
- [ ] Export contains only shortlisted rows; a name beginning `=` is exported as `'=`
- [ ] No token → 401 (with CORS header); groupless user → 403 on every route; Recruiter B → 404 on every one of Recruiter A's job routes; Recruiter on `/failed-jobs` → 403
- [ ] A forced scoring failure (temporarily deny `dynamodb:UpdateItem` on candidates) → 5 `scoring` rows → one `scoring_exhausted` row → `score_status=error`, **`parse_status` still `parsed`** → alarm email received
- [ ] Every API function's role matches `Architecture.md` §8.1; no `Resource: "*"` except where documented
- [ ] `infra/README.md` runbook covers deploy, seed, users, SES, the replay procedure (`Architecture.md` §11.6), and teardown
- [ ] `grep -ri "textract\|comprehend" backend/ template.yaml` → no matches

Once every box is checked, hand off to **`04-frontend-dashboard.md`**.
