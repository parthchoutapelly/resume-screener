# Implementation.md — Developer Handbook
### AI-Powered Resume Screener & Talent Acquisition Pipeline

> **What this file is for:** the practical "how do I build, run, test, and debug this" reference for developers and agents working in the repo. Structure and contracts are defined in `Architecture.md`, invariants in `Rules.md`, and step-by-step build instructions (with reference code) in phase files `01`–`05`. This file doesn't restate them. It ties them together into daily workflows and keeps the reference payloads in one place.

---

## 1. Repository Layout

```
resume-screener/
├── template.yaml                 # all AWS resources (01 §4, 02 §5.3/§6.3/§7/§8.4, 03 §4–§8)
├── samconfig.toml                # [dev] / [prod]
├── Makefile                      # lint | test | build | deploy ENV= | seed ENV= | frontend ENV= | evaluate ENV=
├── pyproject.toml                # ruff, black, pytest, coverage config
├── infra/README.md               # prerequisites, spike results, manual steps, runbook
├── scripts/
│   ├── seed-config.sh  create-user.sh  gen-frontend-env.sh  deploy-frontend.sh
│   ├── validate_data.py  capture_sample_output.py  evaluate.py
├── backend/
│   ├── Makefile                  # build-CommonLayer (makefile build method)
│   ├── data/                     # skills_dictionary, case_sensitive_skills, job_titles_dictionary, synonyms, title_families (.json)
│   ├── layers/
│   │   ├── common_layer/python/rs_common/   # shared package (02 §5, 03 §3)
│   │   └── nlp_layer/{Makefile, requirements.txt}
│   ├── ingestion/
│   │   ├── extraction/{Dockerfile, requirements.txt, app/handler.py}   # image; Docker context = backend/
│   │   └── nlp/handler.py
│   ├── scoring/score_match/handler.py
│   ├── api/<route>/handler.py    # 10 routes (03 §6)
│   └── reliability/dlq_handler/handler.py
├── frontend/                     # 04; structure per Design.md §7
├── tests/
│   ├── unit/  component/  integration/
│   └── fixtures/{resumes/, jds/, truth.json}     # synthetic only (R-PRIV-04)
└── docs/                         # spec set, deliverables.md, evaluation.md, demo.md, sample-nlp-output/, evidence/
```

## 2. Local Development Workflow

| Task | Command | Notes |
|---|---|---|
| One-time setup | `python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt` | dev deps: pytest, moto[all], ruff, black, boto3, spacy + model (for component tests), pypdf, python-docx, Pillow |
| Unit tests | `RS_DATA_DIR=backend/data PYTHONPATH=backend/layers/common_layer/python pytest tests/unit` | No AWS, no network |
| Component tests | `pytest tests/component` | moto mocks DynamoDB/S3/SQS; NLP tests load the real spaCy model |
| Extraction in its real image | `sam build --use-container ExtractionFunction && sam local invoke ExtractionFunction -e tests/events/s3_resume_pdf.json` | Needs Docker; set env vars via `--env-vars tests/events/env.json`. S3/DynamoDB calls hit the **dev** account unless you point them at moto server |
| Full build | `sam build --use-container` | Always use a container build: layer wheels must be Linux x86_64 (D-33) |
| Deploy | `sam deploy --config-env dev` | Uses samconfig; confirm the changeset |
| Seed config | `make seed ENV=dev` | Idempotent |
| Frontend dev | `scripts/gen-frontend-env.sh dev && cd frontend && npm run dev` | API via the Vite proxy at `/api`; uploads go directly to S3 (localhost allowed in dev bucket CORS) |
| Frontend with mocks | `VITE_USE_MOCKS=true npm run dev` | No backend needed |
| Tail logs | `sam logs -n ExtractionFunction --stack-name resume-screener-dev --tail` | JSON logs; filter by `job_id` |

Handler tests don't need a separate "local mode". Handlers read everything from env vars (R-DATA-03), so tests set env vars and mock boto3.

## 3. Environment Variables

| Function | Variables |
|---|---|
| all | `ENV`, `LOG_LEVEL` |
| all API functions | `ALLOWED_ORIGIN`, `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE` |
| create_job_posting, add_resumes | + `UPLOAD_BUCKET` |
| update_job | + `SCORING_QUEUE_URL` |
| update_candidate_decision | + `SES_SENDER_ADDRESS` |
| get_resume_url | + `UPLOAD_BUCKET`, `FEATURE_RESUME_VIEW` |
| export_shortlist_csv | + `UPLOAD_BUCKET` |
| ExtractionFunction | `NLP_FUNCTION_NAME`, `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE` |
| NlpFunction | `JOBS_TABLE`, `CANDIDATES_TABLE`, `CONFIG_TABLE`, `SCORING_QUEUE_URL` |
| ScoreMatchFunction | `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE` |
| DlqHandlerFunction | `JOBS_TABLE`, `CANDIDATES_TABLE`, `FAILED_JOBS_TABLE`, `INGESTION_DLQ_ARN` |
| tests only | `RS_DATA_DIR` (defaults to `/opt/data` in Lambda) |

## 4. Reference Payloads

### 4.1 S3 event (IngestionQueue body) — note the URL-encoded key
```json
{"Records": [{"s3": {"bucket": {"name": "resume-screener-dev-123456789012"},
                     "object": {"key": "resume-uploads/job_3f9c0d.../cand_8a1e77.../resume.pdf", "size": 184233}}}]}
```
S3 also sends a one-off `{"Event": "s3:TestEvent", ...}` when notifications are configured. Handlers skip it.

### 4.2 Extraction → NLP invoke
```json
{"doc_type": "resume", "job_id": "job_3f9c0d...", "candidate_id": "cand_8a1e77...",
 "extracted_text": "Jane Doe\nSenior Backend Developer\n...",
 "extraction_metadata": {"source_key": "resume-uploads/job_3f9c0d.../cand_8a1e77.../resume.pdf",
                         "file_type": "pdf_mixed", "page_count": 2, "ocr_pages": 1,
                         "char_count": 3184, "text_truncated": false}}
```
For a JD, `doc_type` is `"jd"` and `candidate_id` is `null`. NLP errors come back as a `FunctionError` with `errorType` ∈ `EmptyDocumentError`, `OrphanRecordError` (terminal) or anything else (transient).

### 4.3 ScoringQueue message
```json
{"job_id": "job_3f9c0d...", "candidate_id": "cand_8a1e77...", "reason": "candidate_parsed"}
```
`reason` ∈ `candidate_parsed | job_ready | requirements_changed`, for logs only.

### 4.4 Sample `candidates` item (after scoring)
```json
{
  "job_id": "job_3f9c0d...", "candidate_id": "cand_8a1e77...",
  "original_filename": "jane_doe_resume.pdf",
  "resume_s3_key": "resume-uploads/job_3f9c0d.../cand_8a1e77.../resume.pdf",
  "upload_expires_at": "2026-09-19T10:15:00Z", "ingest_started_at": "2026-09-19T10:01:12Z",
  "file_type": "pdf_native", "page_count": 2, "ocr_pages": 0, "char_count": 3184,
  "parse_status": "parsed", "score_status": "scored",
  "name": "Jane Doe", "email": "jane.doe@example.com",
  "employers": ["Acme Corp", "Globex Inc"], "titles_held": ["backend developer"],
  "skills": ["aws", "python", "sql"],
  "total_experience_years": 4.0, "experience_estimated": false,
  "match_score": 71.3, "skills_score": 66.7, "title_score": 60, "experience_score": 100,
  "matched_skills": ["aws", "python"], "missing_skills": ["dynamodb"],
  "title_match_type": "related", "title_match_held": "backend developer", "title_match_required": "backend engineer",
  "shortlist_candidate": true, "scoring_version": "v1", "scored_at": "2026-09-19T10:02:30Z",
  "decision": "pending",
  "created_at": "2026-09-19T10:00:00Z", "updated_at": "2026-09-19T10:02:30Z"
}
```
Numbers are DynamoDB Numbers (`Decimal` in boto3). `total_experience_years` is absent when unknown; `match_score` and the sub-scores are absent until scored.

### 4.5 Sample `jobs` item
```json
{
  "job_id": "job_3f9c0d...", "recruiter_id": "<cognito sub>", "job_title": "Backend Engineer",
  "jd_source": "file", "jd_s3_key": "jd-uploads/job_3f9c0d.../jd.pdf", "jd_original_filename": "backend-jd.pdf",
  "parse_status": "parsed",
  "required_skills": ["aws", "dynamodb", "python"], "min_experience_years": 3,
  "derived_skills": ["aws", "python", "sql"], "derived_titles": ["backend engineer"], "derived_min_experience_years": 2,
  "requirements_confirmed": false, "shortlist_threshold": 70,
  "created_at": "2026-09-19T09:59:40Z", "updated_at": "2026-09-19T10:00:31Z"
}
```
The effective requirements here are skills from the recruiter, titles from the JD (no explicit `required_titles`), and min years from the recruiter (`Architecture.md` §7.1).

## 5. Build & Packaging Notes

- **Architecture:** x86_64 for every function and layer. On Apple Silicon, check the image with `docker inspect … --format '{{.Architecture}}'` → `amd64`.
- **Extraction image:** the base is chosen by spike T-003 (`01` §2) and recorded as the D-34 outcome in `Memory.md`. The Docker context is `backend/`, so the image can copy `rs_common` (container functions can't use layers).
- **Common layer:** makefile build copies `rs_common` → `/opt/python/rs_common` and `backend/data/*.json` → `/opt/data/`. Nothing in `rs_common` performs I/O at import time; dictionaries load lazily.
- **NLP layer:** makefile build, `pip install --platform manylinux2014_x86_64 --only-binary=:all:`; spaCy and `en_core_web_sm` pinned to matching minor versions; includes `python-dateutil`. Check that function + layers stay under 250 MB unzipped.
- **Model loading:** spaCy and the PhraseMatchers are built at module scope (once per warm container); config is checked at cold start.
- **Licences:** PyMuPDF is AGPL. That's fine for the academic deliverable; note it in `docs/deliverables.md`.

## 6. Deployment Sequence

```bash
sam build --use-container
sam deploy --config-env dev          # first time: review the changeset carefully
make seed ENV=dev
scripts/create-user.sh dev recruiter.a@example.com Recruiter    # + recruiter.b, admin, and one groupless user
scripts/deploy-frontend.sh dev
```
Promotion: only after `05` §9 Go/No-Go passes on `dev`, deploy `prod` with `--config-env prod` (budget created in exactly one stack).

Teardown: empty both buckets (`aws s3 rm --recursive`), then `sam delete --stack-name resume-screener-dev`. DynamoDB tables and log groups are deleted with the stack. Remove the SES identities manually if they're no longer needed.

## 7. Debugging Runbook

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Row stuck "Processing" < 60 min | Normal (OCR or retries) | Extraction logs by `candidate_id`; `failed_jobs` rows with `terminal=false` |
| Row "Upload not received" | Browser never completed the POST, or the link expired | Re-upload from the job page (FR18) |
| Row "Taking longer than expected" | Messages retrying or stuck | IngestionQueue in-flight count; throttles; DLQ alarms |
| Everything "Waiting for job description" | JD still processing, or its fan-out failed | Job `parse_status`; NLP logs `jd_fanout enqueued=n`; if the job is parsed but nothing was enqueued, PATCH the job (re-triggers the fan-out) |
| `AccessDenied` on HeadObject for a missing key | No `s3:ListBucket` → S3 returns 403 instead of 404 | Expected; treated as transient `s3_download` |
| `TypeError: Float types are not supported` | A float passed to boto3 | Use `rs_common.ddb.to_decimal` |
| `exec format error` on invoke | arm64 image on an x86_64 function | Rebuild for `linux/amd64` |
| Browser CORS error on a 401/403 | GatewayResponses missing CORS headers | `03` §5 |
| Upload 403 "Policy expired" | Presigned POST older than 15 min | Re-upload |
| No email received | SES sandbox recipient not verified; `notification_status` | SES console identities; the decision response's `notification_status` |
| Manual replay needed | Terminal ingestion failure after fixing the cause | `Architecture.md` §11.6 |

## 8. Coding Conventions

See `Memory.md` §5 (naming, IDs, timestamps, limits, logging) and `Rules.md` §8 (data integrity). Handlers stay thin; logic lives in `rs_common` with unit tests. Cite task IDs and decision/rule IDs in commits.
