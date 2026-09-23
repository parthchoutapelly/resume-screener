# Rules — Invariants & Behavioural Constraints

> **MUST / MUST NOT** statements that every component, test, and future change has to satisfy. Each rule has a stable ID, so code comments, tests, and reviews can cite it (e.g. `# R-DATA-02`). Rationale and mechanics live in `Architecture.md`; the decisions behind the rules live in `Memory.md` §3. If a rule blocks a legitimate requirement, change the rule here first (with a decision entry), then the code — never the reverse.

---

## 1. Honesty Rules (the project's core promise)

| ID | Rule |
|---|---|
| R-HON-01 | Entities MUST come only from the document's own extracted text. No field may be populated from the filename, the S3 key, upload order, request metadata, or canned/sample text. |
| R-HON-02 | Code MUST NOT branch on specific filenames, candidate names, or sample fixtures (`if "john_resume" in key` is forbidden in any form). |
| R-HON-03 | OCR output MUST come from Tesseract running on a rendered page or image. NLP entities MUST come from running the spaCy pipeline on the actual extracted text. There are no shortcuts, caches keyed by filename, or stubs in deployed code. |
| R-HON-04 | Whether a page is scanned MUST be decided from that page's extracted-text length, never from user input or name. |
| R-HON-05 | No confidence score, probability, or accuracy figure may be shown or stored unless a library actually produced it. None are displayed in the MVP. |
| R-HON-06 | The method for each field is fixed and documented (`Details.md` §3, `02` §8.1): NER for name/employers/dates; PhraseMatcher + dictionary for skills/titles; deterministic for experience, email, and JD minimum years. UI copy, docs, and deliverables MUST NOT call deterministic outputs "AI" or "NLP". |
| R-HON-07 | Dictionaries MAY only normalize ("js" → "javascript") or detect a phrase that is present. They MUST NOT add an entity that doesn't appear in the text. |
| R-HON-08 | No code, IAM policy, doc, or UI copy may claim Textract or Comprehend is a working dependency. `textract`/`comprehend` MUST NOT appear in `backend/` or in IAM statements. |
| R-HON-09 | Unknown is shown as unknown: missing experience is "Unknown" (not `0`), and a missing name is "Name not found" (not a guess). |

## 2. Business Rules

| ID | Rule |
|---|---|
| R-BUS-01 | One JD per job posting. A job has 0..200 candidates. |
| R-BUS-02 | `match_score = round(0.5·skills + 0.3·title + 0.2·experience, 1)`, computed from the **unrounded** sub-scores (each in [0, 100]); the sub-scores are rounded to 1 dp only for storage. Weights change only via a new `scoring_version`. |
| R-BUS-03 | Requirement precedence: an explicit recruiter value always wins over a JD-derived one, field by field. JD NLP writes only `derived_*` and MUST NOT overwrite `required_*`/`min_experience_years`. |
| R-BUS-04 | A candidate is scored only when the job is scorable: ≥1 effective required skill AND (`parse_status ∈ {parsed, not_applicable}` OR `requirements_confirmed`). An empty skill requirement MUST NOT produce a skills score of 100. |
| R-BUS-05 | Re-scoring (after a requirements/threshold change or a duplicate event) updates scores, explanation, and `shortlist_candidate` only. It MUST NOT change `decision`, `notification_status`, or send email. |
| R-BUS-06 | `shortlist_candidate` (UI: "Recommended") is advisory. It MUST NOT trigger emails, decisions, exports, or any other side effect. Only a human `decision` does. |
| R-BUS-07 | A shortlist email is sent **at most once per candidate, ever**, enforced by a conditional claim on `notification_status` before calling SES. Changing the decision back and forth sends nothing new. A `failed` status may be retried by shortlisting again. |
| R-BUS-08 | A decision write MUST succeed or fail on its own merits. Email failure or a missing email sets `notification_status` (`failed` / `skipped_no_email`); it never rolls back or blocks the decision. |
| R-BUS-09 | Scoring reads only `skills`, `titles_held`, `total_experience_years`, and job requirements. It MUST NOT read name, email, employers, contact details, filename, or any demographic proxy. |
| R-BUS-10 | Title matching: exact → 100; same family in `title_families.json` → 60; else 0. Take the best across all `titles_held`. No effective title requirement → 100, labelled "not required". |
| R-BUS-11 | Experience: merge overlapping employment intervals; exclude the education section when it can be detected; "Present/Current/Till date/Now" = today (UTC); discard intervals that are in the future, reversed, or longer than 50 years. Nothing found → unknown (attribute absent). |
| R-BUS-12 | Export contains only `decision = shortlisted` candidates of one job, with columns `name, email, skills, titles_held, total_experience_years, match_score, decided_at`. |
| R-BUS-13 | The Recommended threshold comparison is `match_score >= shortlist_threshold`, using the stored 1-dp values. |

## 3. Security Rules

| ID | Rule |
|---|---|
| R-SEC-01 | Every S3 bucket has all four Block Public Access flags on, SSE enabled, and a policy denying non-TLS access. Static website hosting MUST NOT be enabled. |
| R-SEC-02 | Every Lambda has its own role, scoped by table/index ARN, S3 prefix, queue ARN, function ARN, and SES identity. `Resource: "*"` is forbidden except where AWS requires it (`ecr:GetAuthorizationToken` for the deploy user; `cloudwatch:PutMetricData` only if the EMF fallback is used, with a namespace condition). SES sending is scoped to the account's identities with a `ses:FromAddress` condition (`03` §9). |
| R-SEC-03 | Upload credentials are presigned POSTs with a policy fixing the exact key, `content-length-range` 1..10,485,760, the Content-Type, and a TTL of 15 min. Download URLs: exports 5 min, resume view 60 s. |
| R-SEC-04 | S3 object keys are server-generated. User-supplied filenames MUST NOT appear in keys or filesystem paths. |
| R-SEC-05 | Document parsers treat input as hostile: enforce size, page (10), pixel (50 MP), and text (100k chars) caps; never execute embedded content; work in a fresh `/tmp/{uuid}` directory that is deleted in `finally`. |
| R-SEC-06 | Secrets MUST NOT be committed. There are none in the MVP; if any are added, they go in SSM Parameter Store / Secrets Manager. The SES sender comes from env `SES_SENDER_ADDRESS`. |
| R-SEC-07 | CORS allowlists exactly the CloudFront origin (plus `http://localhost:5173` in `dev` only). Wildcard origins are forbidden. OPTIONS preflight is unauthenticated; every other method is authenticated. |
| R-SEC-08 | The frontend MUST NOT render candidate-derived content as HTML (`dangerouslySetInnerHTML`, `innerHTML`, markdown rendering). |
| R-SEC-09 | CSV cells whose first character is one of `= + - @ \t \r` MUST be prefixed with `'`. |
| R-SEC-10 | API Gateway stage throttling is on (20 rps, burst 40). The deploy user has no runtime `lambda:InvokeFunction`. |
| R-SEC-11 | Email bodies are plain text; header fields come only from the verified sender and the candidate's regex-validated address. |

## 4. Permission & Access Rules

| ID | Rule |
|---|---|
| R-AUTH-01 | Every route requires a valid Cognito token (API Gateway authorizer). No route overrides the default authorizer. |
| R-AUTH-02 | Every handler requires `cognito:groups` to contain `Recruiter` or `Admin`; otherwise it returns 403. Self sign-up is disabled (`AllowAdminCreateUserOnly`). |
| R-AUTH-03 | Job-scoped routes load the job first. Access is allowed iff `job.recruiter_id == sub` OR the caller is `Admin`. Candidate access derives from job access, and the candidate's `job_id` must equal the path `job_id`. |
| R-AUTH-04 | Missing job and not-owned job both return **404** with the same body, so a job's existence isn't revealed. |
| R-AUTH-05 | `/failed-jobs` is Admin-only (403 otherwise). The UI hides it as well, but the server check is authoritative. |
| R-AUTH-06 | Authorization logic lives in one shared `authorize()` in `CommonLayer`; handlers MUST NOT re-implement it. |
| R-AUTH-07 | Recruiters see public `error_code`s only. Internal `stage`, `error_message`, `raw_payload` are Admin-only. |

## 5. State-Transition Rules

Every status change is a conditional `UpdateItem`. A transition not listed here is forbidden.

### 5.1 `candidates.parse_status`
| From → To | Actor | Condition expression |
|---|---|---|
| ∅ → `pending` | createJobPosting / addResumes | `attribute_not_exists(candidate_id)` |
| `pending` → `parsed` | nlpProcessing | `attribute_exists(candidate_id)` |
| `pending` → `error` | extraction (terminal) / dlqHandler | `parse_status <> :parsed` |
| `error` → `parsed` | nlpProcessing (replay/re-upload only) | `attribute_exists(candidate_id)` |
| `parsed` → `parsed` | nlpProcessing (duplicate event) | idempotent overwrite of entities |
| `parsed` → `error` | **forbidden** | — scoring failures use `score_status` |

### 5.2 `candidates.score_status`
| From → To | Actor | Condition |
|---|---|---|
| ∅ → `pending` | creation | — |
| `pending`/`scored`/`error` → `scored` | scoreMatch | `parse_status = :parsed` |
| `pending` → `error` | dlqHandler (scoring_exhausted) | `score_status <> :scored` |

### 5.3 `candidates.decision`
`pending ↔ shortlisted ↔ rejected`, all directions allowed, by a Recruiter/Admin with job access, only while `score_status = scored` (else 409).

### 5.4 `candidates.notification_status`
∅/`failed` → `sending` (conditional claim) → `sent` | `failed`. ∅ → `skipped_no_email`. `sent` is final. `sending` with no follow-up is displayed as "unknown", and nothing ever automatically re-sends it.

### 5.5 `jobs.parse_status`
| From → To | Actor |
|---|---|
| ∅ → `pending` (JD file/text) or `not_applicable` (no JD) | createJobPosting |
| `pending` → `parsed` | nlpProcessing |
| `pending` → `error` | extraction (terminal) / dlqHandler (condition `<> parsed`) |
| `error` → `parsed` | nlpProcessing on replay |
`requirements_confirmed: false → true` (PATCH only, never reset).

## 6. Validation Rules

| ID | Rule |
|---|---|
| R-VAL-01 | `job_title` 1–200 chars; `shortlist_threshold` 0–100 (default 70); `min_experience_years` 0–50; skills ≤50 items (≤60 chars each); titles ≤20 items (≤80 chars each); `jd.text` ≤50k chars; `jd.source=none` requires ≥1 skill. |
| R-VAL-02 | Resume extensions (case-insensitive): `pdf, docx, png, jpg, jpeg, tiff`. The JD accepts the same set via upload, plus `txt` **only** when written server-side from `jd.text`. |
| R-VAL-03 | ≤50 filenames per request; ≤200 candidates per job; filenames 1–255 chars. |
| R-VAL-04 | The browser validates extension, size (≤10 MiB), and count before calling the API, and the API re-validates. |
| R-VAL-05 | Extraction verifies magic bytes: PDF `%PDF-`; DOCX is a ZIP containing `word/document.xml`; images open with Pillow and pass `verify()`. A mismatch is terminal `unsupported_format`. |
| R-VAL-06 | A PDF with >10 pages → terminal `too_many_pages`. |
| R-VAL-07 | Usable extracted text (after stripping whitespace) <100 chars → terminal `unreadable_document`. |
| R-VAL-08 | Explicit skills/titles are normalized (lowercase, trim, synonym map) at API write time, using the same `CommonLayer` functions as NLP. |
| R-VAL-09 | All request bodies are validated against a schema; unknown fields → 400. |

## 7. Error-Handling Rules

| ID | Rule |
|---|---|
| R-ERR-01 | Every failure produces exactly one `failed_jobs` row per failed attempt, written by the component where it is observed: extraction for all ingestion stages (including NLP errors surfaced via `FunctionError`), scoreMatch for scoring, API handlers for `api`, dlqHandler for `*_exhausted`. NLP MUST NOT write its own row (it previously double-recorded). |
| R-ERR-02 | Deterministic failures are **terminal**: record the row, set status `error` with an `error_code`, and ack the message. Re-raising a terminal error is forbidden. |
| R-ERR-03 | Transient failures re-raise so SQS retries; only `dlqHandler` turns them terminal. |
| R-ERR-04 | "Not ready" conditions in scoring are not errors: ack, log at INFO, write nothing to `failed_jobs`. |
| R-ERR-05 | API errors use the envelope `{"error": {code, message, details?}}`. A 500 message is generic and never includes stack traces, table names, or document content. |
| R-ERR-06 | Every catch either handles, records-and-re-raises, or records-and-acks (terminal). Bare `except: pass` is forbidden. |
| R-ERR-07 | `dlqHandler` must be idempotent (redelivery allowed) and must never overwrite a successful state (§5 conditions). |

## 8. Data-Integrity Rules

| ID | Rule |
|---|---|
| R-DATA-01 | Numbers go to DynamoDB as `Decimal(str(x))`, never `float`. Numbers read back are converted to `float` before arithmetic. |
| R-DATA-02 | Index key attributes are never written as NULL; omit the attribute instead. `match_score` and `total_experience_years` are omitted until they are known. |
| R-DATA-03 | Table, queue, and bucket names come only from env vars injected by the template (`JOBS_TABLE`, …). Building names in code (`f"jobs-{ENV}"`) is forbidden. |
| R-DATA-04 | Every consumer is idempotent under duplicate delivery: overwrites are deterministic, status changes are conditional, and email is claim-guarded. |
| R-DATA-05 | Timestamps are ISO-8601 UTC with a `Z` suffix, from `datetime.now(timezone.utc)`. `utcnow()` is forbidden. |
| R-DATA-06 | IDs are `job_` / `cand_` + `uuid4().hex` (32 hex chars). Truncated UUIDs are forbidden. |
| R-DATA-07 | Lists stored on items are normalized, deduplicated, and sorted, so outputs are deterministic and diffable. |
| R-DATA-08 | `failed_jobs` is an append-only audit log with a 90-day TTL. The current truth is `parse_status` / `score_status`, never a count of failure rows. |
| R-DATA-09 | Every write sets `updated_at`; creates set `created_at`. |
| R-DATA-10 | Employers that normalize to a known skill (e.g. "AWS", "Python") are removed from `employers`. |

## 9. Privacy Rules

| ID | Rule |
|---|---|
| R-PRIV-01 | Logs MUST NOT contain extracted text, email addresses, phone numbers, or names. Log IDs, counts, and stages. |
| R-PRIV-02 | `failed_jobs.error_message` ≤500 chars, derived from the exception type and a safe message, never from document content. |
| R-PRIV-03 | Candidate data never leaves the account, except the shortlist email to the candidate's own address. |
| R-PRIV-04 | Repository fixtures and demo data are synthetic. Real resumes are never committed. |
| R-PRIV-05 | Log groups retain 30 days; `exports/` 7 days; upload prefixes 180 days (pending OQ9). |

## 10. Rules That Must Never Be Violated

If any of these fails, the build is not shippable, whatever else passes:

1. R-HON-01..03 — no fabricated or filename-driven output.
2. R-AUTH-01..03 — no unauthenticated access, no cross-recruiter access.
3. R-SEC-01 — no public bucket; the frontend is served over HTTPS.
4. R-BUS-06/07 — no automated candidate contact; at most one email per candidate.
5. R-DATA-02 + R-ERR-02 — no candidate ever stuck without a visible terminal/flagged state.
6. R-PRIV-01 — no resume content in logs.
7. R-HON-08 — no Textract/Comprehend references.

## 11. Anti-Patterns & Forbidden Behaviours

| Forbidden | Why | Do instead |
|---|---|---|
| Querying a GSI keyed on `match_score` to list candidates | Sparse index hides unscored rows | Base-table Query + `display_status` sort |
| Raising in `scoreMatch` because the JD isn't parsed | Exhausts retries during slow JD ingestion | Ack; rely on the fan-out |
| Retrying corrupt/unsupported documents | Delays the error state by ~36 min for no gain | Terminal classification |
| Recording the same failure in both NLP and extraction | Duplicate audit rows | Extraction records |
| Using the raw S3 event key without `unquote_plus` | Encoded characters break `GetObject` | Decode, then parse |
| `/tmp/{basename}` paths | Collisions and `/tmp` exhaustion across warm invocations | `/tmp/{uuid}/` + cleanup |
| Presigned PUT for uploads | Cannot enforce a size range | Presigned POST |
| S3 static website hosting | HTTP only; requires a public bucket | CloudFront + OAC |
| Scan + filter to list a recruiter's jobs | Unpaginated, O(table) | `RecruiterJobsIndex` |
| Trusting `cognito:groups` only in the UI | UI checks are bypassable | Server `authorize()` |
| Adding a second `nlp_engine_mode` "just in case" | Dead code that invites fake fallbacks | Add a mode only with a real implementation + decision entry |
| Loading spaCy or building PhraseMatchers inside the handler | Cold-start cost on every call | Module scope |
| botocore retries on the NLP invoke | Double NLP execution | `max_attempts: 0` |
| Unbounded SQS → Lambda concurrency on a low-quota account | Throttles push healthy messages into the DLQ | `MaximumConcurrency` |
| Emailing based on `shortlist_candidate` | Automated decision-making | Human decision only |
| Showing a score without its breakdown | Unexplainable ranking | Sub-scores + matched/missing |
| Writing `0` for unknown experience | Misrepresents the data | Omit the attribute; show "Unknown" |
| Hardcoding the SES sender, table names, or API URLs | Env drift | Env vars / stack outputs |
| Adding a library or AWS service without a decision entry | Architecture drift | Add a `Memory.md` §3 entry first |
