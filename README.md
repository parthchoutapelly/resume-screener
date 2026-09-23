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

**Phase 1 (infrastructure) — deployed to `dev`.** All platform spikes run, `resume-screener-dev`
stack live (4 DynamoDB tables, 4 SQS queues, Cognito pool + test users, SNS, 14 stub Lambda
functions incl. the real Tesseract-OCR container image), config seeded. CloudFront/frontend
hosting is deliberately deferred pending an AWS account verification — see `infra/README.md`
"CloudFront deferred" and "Phase 1 deployment result" for the full checklist and rationale.

Next: phase 2 (`docs/02-ingestion-pipeline.md`) — `rs_common` shared layer, real document
extraction, real NLP.
