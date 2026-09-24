# AI-Powered Resume Screener & Talent Acquisition Pipeline

Serverless pipeline (AWS SAM, Python 3.12, ap-south-1): a recruiter uploads a job
description and a batch of resumes; the system extracts and scores candidates using
genuine document extraction/OCR and NLP (spaCy), and surfaces an explainable, ranked
shortlist in a recruiter dashboard.

**Full specification:** [`docs/`](docs/) — start with [`docs/Memory.md`](docs/Memory.md) §1
for the document map, or [`docs/PRD.md`](docs/PRD.md) for what/why.

**Build order:** [`docs/01-infrastructure-setup.md`](docs/01-infrastructure-setup.md) →
[`02-ingestion-pipeline.md`](docs/02-ingestion-pipeline.md) →
[`03-scoring-and-api.md`](docs/03-scoring-and-api.md) →
[`04-frontend-dashboard.md`](docs/04-frontend-dashboard.md) →
[`05-integration-testing-and-delivery.md`](docs/05-integration-testing-and-delivery.md).

## Quick start

```bash
make venv              # creates .venv, installs dev/test deps
make lint               # ruff + black --check
make test                # pytest + coverage
make build ENV=dev      # sam build --use-container
make deploy ENV=dev     # sam deploy --config-env dev
make seed ENV=dev       # seeds the config table's nlp_engine_mode row
```

See [`infra/README.md`](infra/README.md) for prerequisites, platform validation results,
manual one-time setup steps, and the operational runbook.

## Status

**Phases 1–2 — deployed to `dev` and verified end-to-end on real AWS infrastructure.**

- **Phase 1 (infrastructure):** `resume-screener-dev` stack live — 4 DynamoDB tables, 4 SQS
  queues, Cognito pool + test users, SNS, all core Lambda functions. CloudFront/frontend hosting
  is deliberately deferred pending an AWS account verification (not needed before phase 4) — see
  `infra/README.md` "CloudFront deferred".
- **Phase 2 (ingestion — extraction + NLP):** real document extraction (native/scanned/mixed PDF,
  DOCX, image, multi-page TIFF) and real NLP (spaCy NER + hybrid skill/title matching +
  deterministic experience) both deployed. Verified with a live end-to-end run: 6/6 real resumes
  parsed correctly with genuine extracted names/skills/experience, 4/4 deliberate failure cases
  hit the exact right terminal error, zero DLQ traffic. `nlpProcessing` runs as a container image,
  not zip+layers, after the real built layer measured 310 MB (over Lambda's 250 MB limit) — see
  `infra/README.md` "Phase 2 deployment result" for the full checklist and the three real
  problems (two infra, one code) found and fixed along the way.

Next: phase 3 (`docs/03-scoring-and-api.md`) — scoring engine, the recruiter REST API,
`dlqHandler`, and alarms.
