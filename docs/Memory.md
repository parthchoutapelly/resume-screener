# Memory — Project Source of Truth

> **Read this first.** This file preserves decisions, vocabulary, conventions, and context so future work — by people or AI agents — doesn't drift from the architecture or re-argue settled questions. It is the long-term source of truth.

---

## 1. Document Precedence

| Question | Authoritative file |
|---|---|
| What are we building, for whom, and what counts as success? | `PRD.md` |
| How is it structured (components, contracts, data model, IAM)? | `Architecture.md` |
| What must always / never happen? | `Rules.md` |
| How does it look and behave for users? | `Design.md` |
| What was decided and why; what not to reconsider | **`Memory.md`** (this file) |
| What to build, in what order, and when it's done | `Tasks.md` |
| Why the project is shaped this way (narrative) | `Details.md` |
| How to build, run, test, debug; reference payloads | `Implementation.md` |
| Step-by-step build instructions with reference code, per phase | `01`–`05` phase files |

**Conflict resolution:** Rules > Memory decisions > Architecture/Design > PRD > phase files > Details/Implementation. On 2026-09-23 every document was revised to agree; §7 records what the original versions said and why each changed. If you find a new conflict, resolve it here with a decision entry. Don't silently pick one side.

**Change protocol:** to change anything in §3, add a new decision row that supersedes the old one (don't delete it), update the affected files, and cite the decision ID in the commit message.

## 2. Project Snapshot

- **Product:** a serverless resume screener. A recruiter uploads a JD + resumes → Python extraction/OCR → spaCy NER + dictionaries → weighted score with explanation → ranked dashboard → human shortlist/reject → one email → CSV export.
- **Team:** Parth (lead; infra + ingestion), Allen (scoring, API, reliability), Tejesh (frontend), Gaurav (docs/deliverables). Ownership is a proposal (`Details.md` §8).
- **Where:** AWS ap-south-1, one account on the **Free plan**, `dev` and `prod` stacks separated by the `EnvName` suffix.
- **Status (2026-09-23):** Phase 1 deployed to `dev` — `resume-screener-dev` stack `CREATE_COMPLETE` (4 DynamoDB tables, 4 SQS queues, Cognito + 4 test users, SNS, all 14 stub Lambdas incl. the real extraction container image). D-34 decided (Debian slim, not AL2023 — see D-34 row). CloudFront/frontend hosting deferred (new-account verification gate; `infra/README.md` "CloudFront deferred"), not blocking — needed only from phase 4. Next step: phase 2 (`02-ingestion-pipeline.md`) — `rs_common` layer, real extraction, real NLP.

## 3. Decision Log

§3.1 = decisions inherited from the original design, still in force. §3.2 = decisions introduced during the 2026-09-23 review; the "Supersedes" column cites section numbers in the **original** (pre-revision) documents, which were overwritten on 2026-09-23 (this folder is not under version control; §7 is the record of what they said).

### 3.1 Foundational (inherited — do not revisit unless the trigger occurs)

| ID | Decision | Why | Revisit only if |
|---|---|---|---|
| D-01 | Serverless on AWS with SAM, Python 3.12, ap-south-1 | Team familiarity, pay-per-use, spiky load | Leaving AWS |
| D-02 | No Textract/Comprehend; open-source extraction (pypdf, python-docx, PyMuPDF, Tesseract) and spaCy NER | Free plan cannot call them (AWS Support confirmed) | The account is upgraded **and** the team opts into migration F4 |
| D-03 | Extraction is a container image; NLP is zip + layers | Tesseract is a native binary; NLP needs no OS packages and gets faster cold starts as zip | Tesseract becomes pip-installable, or NLP exceeds 250 MB (then NLP → image) |
| D-04 | Extraction → NLP via synchronous Lambda invoke, not a third queue | Two deployable units and IAM scopes without extra queue infrastructure | NLP time grows to where the extraction timeout is at risk |
| D-05 | One IngestionQueue for JD and resumes; `doc_type` from the key prefix | Same pipeline after the S3 event | — |
| D-06 | Two SQS stages + DLQs: ingestion maxReceive 3, scoring 5 | Burst smoothing, fault isolation, free retries | — |
| D-07 | DynamoDB on-demand; tables `jobs`, `candidates`, `failed_jobs`, `config` | Spiky, small, key-value access | Relational reporting becomes a requirement |
| D-08 | Score = 50% skills / 30% title / 20% experience; per-job threshold, default 70 | Brief + mentor | Mentor changes weights → new `scoring_version` |
| D-09 | Field-method honesty table (`Details.md` §3, `02` §8.1) | The core "genuine NLP" requirement | Custom NER shipped (F1) — then update the table |
| D-10 | Browser uploads directly to S3 with presigned credentials | Avoids the API Gateway 10 MB / Lambda 6 MB payload limits | — |
| D-11 | `failed_jobs` is an audit log; item status fields are the truth | One failure per attempt ≠ current state | — |
| D-12 | Cognito User Pool, groups `Recruiter` and `Admin`; Amplify Auth only | Managed auth; no custom identity code | — |
| D-13 | `config.nlp_engine_mode = spacy_hybrid` is the only mode; no fallback paths | Keeps the swap seam honest | A second engine is actually implemented |
| D-14 | `en_core_web_sm` model | Layer size and cold start; skills/titles come from dictionaries anyway | Measured NER quality fails SC3 — try `md` in an image |
| D-15 | No self-registration; Admins create users | Internal tool | — |

### 3.2 Introduced by this spec (new / superseding)

| ID | Decision | Why (problem it fixes) | Supersedes |
|---|---|---|---|
| D-16 | List candidates with a base-table `Query(job_id)` + in-Lambda sort; **remove `JobScoreIndex`** | Sparse GSI omitted unscored rows; NULL keys are rejected | `01` §3.5 GSI, `Impl` §3.2/§6.6/§6.8 |
| D-17 | Separate `score_status` from `parse_status` | Scoring failure was flipping a successfully parsed resume to "parse error" | `03` §8 `mark_error` for scoring |
| D-18 | Event-driven scoring readiness: scoreMatch **acks** when the job isn't scorable; NLP (JD parsed) and PATCH fan out re-scoring | Retry-until-ready exhausted in ~5 min while a JD retry takes 12+ min → false `scoring_exhausted` | `Impl` §4, §6.4 step 2–3; `03` §3 |
| D-19 | Terminal vs transient error classes; terminal = record + mark error + ack | Retrying corrupt files wasted ~36 min before showing an error | `Impl` §14 retry column |
| D-20 | Extraction is the single audit writer for ingestion stages; NLP raises typed errors and never writes `failed_jobs` | Every NLP failure was recorded twice | `02` §9 step 10, `Impl` §12 NLP row |
| D-21 | Presigned **POST** (size range, fixed key, content type), 15 min TTL; server-chosen keys `jd.{ext}` / `resume.{ext}` | PUT can't bound size; user filenames in keys caused encoding/path issues | `Impl` §6.1, `04` §4 upload |
| D-22 | Frontend in a **separate private bucket** behind **CloudFront + OAC** | S3 website hosting needs a public bucket and is HTTP-only (Cognito passwords in cleartext) | `04` §7, `Impl` §2 `frontend/` prefix |
| D-23 | Explicit CORS on API (incl. GatewayResponses) and the upload bucket; unauthenticated preflight | Browser calls would fail; not specified anywhere | — (gap) |
| D-24 | Group membership required on all routes; job ownership check with 404 | Any recruiter could read any job by ID; groupless users had access | `03` §6.3–6.5 |
| D-25 | SQS ESM `MaximumConcurrency`: ingestion 3, scoring 2 | Low new-account quota + throttling increments receive count → false DLQ | `Impl` §4 "Concurrency" |
| D-26 | `title_families.json` for the 60-point match; best match across all titles held | Synonym map had abbreviations, not related roles; "most recent title" isn't extractable | `Details` §11 title rule, `03` §3 `SYNONYM_TITLES` |
| D-27 | Experience = date-range detection in the experience section, interval merge, education excluded; unknown ≠ 0 | Consecutive-DATE pairing broke on "2019–2021" single entities, "Present", overlaps, education | `02` §9 `compute_experience_years`, reconciles with `Impl` §10 |
| D-28 | Only human decisions trigger email; at most once per candidate; email failure never fails the decision; auto flag renamed "Recommended" | Duplicate emails on toggling; conflation of the auto flag with the decision | `03` §6.4 |
| D-29 | Explicit requirements win field by field; JD-derived stored as `derived_*` | NLP `write_job` overwrote recruiter input | `02` §9 `write_job` |
| D-30 | A job is scorable only with ≥1 effective required skill | Empty requirements gave everyone 100 skills points | `03` §3 `score_skills` empty case |
| D-31 | New endpoints: `GET /jobs/{id}`, `PATCH /jobs/{id}`, `POST /jobs/{id}/resumes`, `GET …/resume-url` (S) | The detail page had no job data; no recovery for failed uploads, JD failure, or bad requirements | `04` §1 "no new endpoints" |
| D-32 | Alarm on dlqHandler's EMF metric + DLQ `NumberOfMessagesReceived`, not DLQ depth | The consumer drains the DLQ → a depth alarm never fires | `Details` §17 observability |
| D-33 | `x86_64` everywhere; `sam build --use-container`; verify image platform | A Mac-built arm64 image or macOS wheels fail at runtime | — (gap) |
| D-34 | **Extraction base image = Debian slim (`python:3.12-slim-bookworm`) + `apt-get tesseract-ocr` + `awslambdaric`.** Confirmed 2026-09-23: the AL2023 Lambda base image's `dnf`/`microdnf` has no `tesseract` package at all (`error: No package matches 'tesseract'`, confirmed after ~2m21s of genuine metadata resolution, not a hang); Debian's `apt-get install tesseract-ocr tesseract-ocr-eng` installs cleanly and was verified to produce genuine OCR output (Tesseract 5.3.0, tested by invoking the handler inside the built image against a real fixture image) | The original Dockerfile used `yum`, which doesn't exist on AL2023 images; the AL2023 repo doesn't carry tesseract at all regardless of package-manager syntax | `Impl` §8 Dockerfile |
| D-35 | `display_status` derived server-side in `CommonLayer` (incl. `upload_missing`, `stalled`, `awaiting_*`) | Otherwise a never-uploaded or stuck row stays "pending" forever | — (gap) |
| D-36 | GSI `RecruiterJobsIndex` (recruiter_id, created_at) | Scan+filter without pagination | `03` §6.2 |
| D-37 | Names from env vars only; IDs `job_`/`cand_` + full uuid4 hex; Decimal in/float compute; UTC `Z` timestamps | Code hardcoded `f"jobs-{ENV}"`; truncated 48-bit IDs; float writes crash boto3 | `02`/`03` skeletons |
| D-38 | CSV formula-injection escaping | Resume-controlled text opened in Excel | — (gap) |
| D-39 | 30-day log retention; no PII in logs/errors | Unbounded retention of personal data | — (gap) |
| D-40 | All status transitions conditional (`Rules.md` §5) | dlqHandler could overwrite a later success | — (gap) |
| D-41 | Store the explanation at score time (`matched_skills`, `missing_skills`, `title_match_*`, `scoring_version`, `scored_at`) | Explainability requirement; the UI can't recompute | — (gap) |
| D-42 | Per-page OCR fallback; page cap 10; text cap 100k chars; min usable text 100 chars | Mixed PDFs skipped OCR; unbounded work | `02` §8.2 whole-doc 40-char rule |
| D-43 | NLP invoke client: `read_timeout=40`, `retries.max_attempts=0` | botocore retries would double-run NLP | — (gap) |
| D-44 | The frontend polls every 5 s while rows are in progress (visibility-aware, 30 min cap) | "On next poll" was never specified | — (gap) |
| D-45 | Pasted JD text is written by the API as `jd-uploads/{job_id}/jd.txt`; `.txt` accepted only under `jd-uploads/` | FR1 text JDs had no pipeline path | — (gap) |
| D-46 | Scoring never reads identity fields (name, email, employers, contact) | Fairness baseline; enables future blind screening (F3) | — |
| D-47 | The client sends the **raw ID token** in `Authorization` (no `Bearer ` prefix) | Documented form for REST Cognito authorizers; avoids a silent 401 | `04` §4 `Bearer ${token}` |
| D-48 | CORS origin **derived from the CloudFront distribution in-template**; dev API calls go through the Vite proxy; only the dev upload bucket also allows `localhost:5173` | No manual origin parameter to drift; API Gateway CORS supports a single origin | — (gap) |
| D-49 | dlqHandler metrics via CloudWatch Embedded Metric Format (stdout) | No `PutMetricData` permission or `Resource: "*"` needed | — |
| D-50 | Both layers use the SAM **makefile** build method; dictionaries live once in `backend/data/` and are copied to `/opt/data`; the extraction image uses Docker context `backend/` to include `rs_common` | Deterministic layer layout; a single source for data; images can't use layers | `Impl` §1 layout |
| D-51 | Five phase files (`01`–`05`); phase 5 owns integration, security, evaluation, deliverables, and the demo | Testing and delivery had no handoff document | `Impl` §16 |
| D-52 | Ambiguous short skills (`Go`, `R`, `C`) matched **case-sensitively** from `case_sensitive_skills.json` | "go to market" was matching Go | — (gap) |
| D-53 | S3 `s3:TestEvent` messages are skipped by extraction and dlqHandler; unknown-prefix or placeholder-less objects are recorded as stage `orphan_object` with no status write | The test event would otherwise crash `parse_key`; orphans have no item to mark | — (gap) |
| D-54 | CloudFront/`WebBucket`/`WebOAC`/`WebHeadersPolicy`/`WebBucketPolicy` deferred out of `template.yaml` into `template-web-hosting.yaml.deferred`; `UploadBucket` CORS temporarily allows only `http://localhost:5173` | This AWS account requires a one-time AWS-Support account verification before it will create *any* CloudFront distribution (`Access denied ... Your account must be verified`) — unrelated to IAM permissions, and Basic support means it can only be requested via the Console, not the API. Bundling this with core backend infra in one stack meant its failure rolled back DynamoDB/SQS/Cognito/all 14 functions too | Restore via the steps in `template-web-hosting.yaml.deferred` once AWS confirms verification (not needed before phase 4) |

## 4. Glossary

| Term | Meaning |
|---|---|
| **Job / job posting** | One role with one JD; owns candidates. `job_id` = `job_<32 hex>` |
| **Candidate** | One uploaded resume within one job (the same person uploaded to two jobs = two candidates) |
| **JD source** | `file` \| `text` \| `none` — how the requirements originate |
| **Explicit requirements** | Values the recruiter typed (`required_skills`, `required_titles`, `min_experience_years`) |
| **Derived requirements** | Values NLP extracted from the JD (`derived_*`) |
| **Effective requirements** | Explicit if present, else derived (`Architecture.md` §7.1) |
| **Scorable** | The job has ≥1 effective skill and the JD isn't still processing (or requirements were confirmed) |
| **parse_status** | Stored state of extraction + NLP for an item |
| **score_status** | Stored state of scoring for a candidate |
| **display_status** | Server-derived UI state (9 values, `Architecture.md` §7.2) |
| **Recommended** | `shortlist_candidate = true` — system flag, advisory only |
| **Shortlisted / Rejected** | Human `decision` values; Shortlisted may trigger one email |
| **Terminal / transient error** | Deterministic (never retried) vs possibly-recoverable (retried by SQS) |
| **Stage** | Internal failure location in `failed_jobs` (`unsupported_format`, `pdf_extract`, …) |
| **error_code** | Recruiter-safe failure reason on the item (`unreadable_document`, …) |
| **Fan-out** | Enqueuing scoring messages for every parsed candidate of a job |
| **Hybrid NLP** | spaCy tokenizer + `PhraseMatcher` over a controlled dictionary (skills, titles) |
| **Title family** | A group of related job titles that earn a 60-point partial match |

## 5. Conventions

- **Repo layout:** `Implementation.md` §1. Dictionaries live once in `backend/data/` and are copied into the common layer at build time (→ `/opt/data`).
- **Shared code:** `rs_common.{normalization, requirements, status, scoring, authz, errors, ddb, log, ids, clock, http}`. Handlers stay thin: parse → call a `rs_common`/domain function → respond.
- **Python:** 3.12, `ruff` + `black`, type hints on public functions, `pytest`. There are no module-level network calls except boto3 client/resource construction, and spaCy/matcher loading in NLP.
- **Env vars:** `ENV`, `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE`, `CONFIG_TABLE`, `UPLOAD_BUCKET`, `SCORING_QUEUE_URL`, `NLP_FUNCTION_NAME`, `SES_SENDER_ADDRESS`, `ALLOWED_ORIGIN`, `LOG_LEVEL`.
- **Limits (constants in `rs_common`):** `MAX_FILES_PER_REQUEST=50`, `MAX_CANDIDATES_PER_JOB=200`, `MAX_FILE_BYTES=10_485_760`, `UPLOAD_URL_TTL_S=900`, `EXPORT_URL_TTL_S=300`, `RESUME_URL_TTL_S=60`, `MAX_PDF_PAGES=10`, `OCR_DPI=200`, `NATIVE_PAGE_MIN_CHARS=40`, `MIN_USABLE_CHARS=100`, `MAX_TEXT_CHARS=100_000`, `STALE_AFTER_MIN=60`, `UPLOAD_GRACE_MIN=2`, `FAILED_JOBS_TTL_DAYS=90`.
- **Naming:** AWS resources `<name>-${EnvName}`; logical IDs PascalCase (`ExtractionFunction`); Python snake_case; React components PascalCase files.
- **Logging:** one JSON line per event through `rs_common.log`. Required keys: `stage`, `job_id`, `candidate_id` (when known).
- **Commits:** reference a task ID (`T-042`) and any decision (`D-18`) or rule (`R-DATA-02`) affected.

## 6. Technical Context & Pitfalls (hard-won; keep)

1. **S3 event keys are URL-encoded** → `unquote_plus` before use.
2. **boto3 DynamoDB resource rejects `float`**; Decimal ÷ float raises `TypeError`. Use the `rs_common.ddb` helpers.
3. **DynamoDB GSIs are sparse** and index keys can't be NULL.
4. **Lambda throttling on SQS event sources increments `ApproximateReceiveCount`** → use `MaximumConcurrency`. New accounts may have a concurrency quota of 10.
5. **A DLQ drained by a consumer always reads depth 0** — alarm on received count or custom metrics.
6. **Container images can't use Lambda layers** — the extraction image's Docker context is `backend/`, so its Dockerfile copies `layers/common_layer/python/rs_common` straight in (D-50). `rs_common` must never do I/O at import time.
7. **Lambda Python 3.12 images are AL2023** — `dnf`/`microdnf`, not `yum`.
8. **Apple Silicon builds default to arm64** — set `x86_64` and verify.
9. **Layer wheels must be Linux builds** — `sam build --use-container`.
10. **spaCy DATE entities** don't reliably include "Present" and often cover a whole range ("2019 – 2021") as one entity — that's why experience uses range detection (D-27).
11. **PhraseMatcher only finds what's in its patterns** — synonym keys (`k8s`, `js`) must be added as patterns, then normalized; very short ambiguous skills (`go`, `r`, `c`) need case-sensitive or context rules to avoid false positives.
12. **Cognito authorizer passes ID-token claims** at `requestContext.authorizer.claims`; `cognito:groups` arrives as a string. Parse defensively (it may be comma- or space-separated, or bracketed).
13. **SES sandbox** silently blocks unverified recipients — verify test addresses before the demo.
14. **PyMuPDF is AGPL** — fine for the internship; flag it for any commercial reuse.
15. **Free plan:** some services are restricted and the plan has a time/credit limit — validated in T-001.

## 7. Change History — What the Original Docs Said (all applied 2026-09-23)

The original `Details.md`, `Implementation.md`, and `01`–`04` were rewritten to match the spec set. This table preserves what they used to say, so nobody "restores" an old approach from memory or version control without knowing why it was dropped. Section numbers refer to the **original** versions.

| Original location | Original statement | Current version (applied) |
|---|---|---|
| `Details` §5 diagram; `Impl` §3.2; `01` §3.5 | `JobScoreIndex` GSI for sorted listing | Removed; base-table Query (D-16) |
| `Details` §8 step 9; `03` §6.3 | Query GSI to list candidates incl. pending | Base-table Query + `display_status` |
| `Details` §11 | Title uses the "most recent" title; synonym table gives 60 | Best across all titles; `title_families.json` (D-26) |
| `Details` §5/§9; `04` §7 | S3 static website hosting in the same bucket | Separate private bucket + CloudFront OAC (D-22) |
| `Impl` §4 | No concurrency cap on extraction | `MaximumConcurrency` 3/2 (D-25) |
| `Impl` §4; `03` §3 | "JD not parsed" → raise → SQS retry | Ack + fan-out (D-18) |
| `Impl` §6.1; `03` §6.1; `04` §4 | Presigned PUT; `resume-uploads/{job}/{cand}/{filename}` | Presigned POST; `resume.{ext}` (D-21) |
| `03` §6.1 | `job_{uuid4().hex[:12]}` | Full uuid4 hex (D-37) |
| `Impl` §6.2; `02` §8.2 | Retry pdf/docx/ocr errors ×3 | Deterministic → terminal (D-19) |
| `02` §8.2 | `unsupported_format` recorded but status untouched | Also sets `parse_status=error` (the row would otherwise stay pending forever) |
| `02` §8.2 | Whole-document 40-char threshold before OCR | Per-page (D-42) |
| `02` §8.2 | `/tmp/{basename}`; no cleanup; raw key | `/tmp/{uuid}/` + cleanup; `unquote_plus` |
| `02` §8.2 / §9 | Both extraction and NLP write `stage=nlp` rows | Extraction only (D-20) |
| `02` §9 | `write_job` overwrites `required_*` | Writes `derived_*` only (D-29) |
| `02` §9 | Consecutive DATE pairing; returns 0.0 when unknown | Range detection; unknown omitted (D-27) |
| `02` §9, `03` §3 | `f"candidates-{ENV}"` names | Env vars (D-37) |
| `02` §6 | NLP layer lacks `python-dateutil` | Add it |
| `02` §5 | PhraseMatcher patterns = dictionary only | Dictionary ∪ synonym keys |
| `03` §3 | Writes float scores; `float / Decimal` | Decimal writes, float math (R-DATA-01) |
| `03` §3 | `score_skills([]) = 100` | Job not scorable (D-30) |
| `03` §6.4 | Hardcoded SES `Source`; email on every shortlist | Env var; at-most-once (D-28) |
| `03` §6.2–6.5 | Only `get_jobs` checks ownership | All job-scoped routes (D-24) |
| `03` §8 | Scoring exhaustion sets `parse_status=error`; unconditional | `score_status=error`; conditional (D-17, D-40) |
| `Impl` §6.3 | NLP 768 MB | 1024 MB initial; tune after measurement |
| `Impl` §8 | `yum install -y tesseract` | Spike decides (D-34) |
| `Details` §17 | Alarm on DLQ depth > 0 | EMF / received-count alarms (D-32) |
| `04` §1 | "No new endpoints" | Four added (D-31) |
| `04` §5.2 | "Processing…" for all pending rows | 9 display states (D-35) |
| `01` §3.7 | Cognito "defaults are fine" | `AllowAdminCreateUserOnly: true` |
| `02` §13 test 4 | Unsupported test uses `.txt` | Still valid for resumes; the API now rejects it up front, so the extraction-level test uses a renamed file (e.g. `.pdf` containing text) |

## 8. Persistent Assumptions

`PRD.md` §11 (A1–A8) is the list. The two that most affect architecture: **A2** (concurrency quota) and **A3/A4** (packaging fits). If T-001–T-004 disprove any of them, record a new decision here before changing code.

## 9. Known Limitations (accepted for MVP)

- English only; `en_core_web_sm` NER misses some names/orgs, especially in OCR text.
- Skills and titles are limited to the dictionaries (~300 skills, ~150 titles); anything outside is invisible to scoring.
- Experience is heuristic; freelance/gap-heavy/non-standard formats → `estimated`/`unknown`.
- The name heuristic can pick a header or reference name; the filename is shown alongside.
- No dedupe of the same resume uploaded twice.
- No password reset UI; Admins reset users in the console.
- Tokens are held in browser storage (Amplify default); XSS resistance relies on React escaping + CSP.
- A single region with no HA; the demo has no SLA.
- Email status can be "unknown" after a crash mid-send (at-most-once trade-off).
- Recruiters can't delete jobs or candidates (retention via lifecycle only, OQ9).

## 10. Settled — Do Not Reopen Without New Requirements

- "Should we add a third queue between extraction and NLP?" → No (D-04).
- "Should scoring retry until the JD is ready?" → No (D-18).
- "Can we reuse `shortlist_candidate` to send emails automatically?" → No (D-28, R-BUS-06).
- "Can we fall back to regex if spaCy fails?" → No; fail and record (D-13, R-HON-03).
- "Let's host the SPA on the S3 website endpoint, it's simpler." → No (D-22).
- "Put the GSI back for sorting." → No (D-16), unless per-job volume exceeds ~1,000 candidates.
- "Use a bigger spaCy model." → Only if SC3 fails, and then as a container image.
