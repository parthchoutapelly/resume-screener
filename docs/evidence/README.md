# Phase 5 Evidence Artifacts Manifest

This directory contains the audit evidence required for Phase 5 Go/No-Go sign-off (`docs/05-integration-testing-and-delivery.md` §1–§6).

## Evidence Families & Manifest

| Family | Expected Artifact | Generating Script / Method | Scope | Status |
|---|---|---|---|---|
| **Integration** | `integration-<date>.json` | `python tests/integration/run.py --env dev` | 7-resume job timings, terminal statuses, worked example 71.3, at-most-once SES email, CSV export | `PENDING EXECUTION` |
| **Failure Matrix** | `failure-matrix.json` | `python tests/integration/failure_matrix.py --env dev` | Terminal states for F1–F13 (F1–F8, F11–F13 automated; F9–F10 manual/destructive) | `PENDING EXECUTION` |
| **Security** | `security-checklist.md` | `tests/component/test_security.py` + AWS CLI checklist | S1–S15 security controls (auth, CORS, tenant isolation, XSS, CSV injection, IAM) | `PENDING LIVE AUDIT` |
| **NLP Quality** | `../evaluation.md` | `python scripts/evaluate.py --env dev` | Precision (≥0.80), Recall (≥0.70), Name (≥8/10), Experience (≥7/10), Title hit rate, miss causes | `PENDING LIVE CANDIDATES` |
| **Sample NLP Output** | `../sample-nlp-output/*.json` | `python scripts/capture_sample_output.py --env dev` | Real extraction output for native PDF, scanned PDF (OCR), and DOCX with field methods | `PENDING LIVE CANDIDATES` |
| **Load Testing** | `load-<date>.md` | `python scripts/run_load_test.py --env dev` | 50-resume load test (35 native / 10 scanned / 5 DOCX); concurrency, throttles, DLQ, latency | `PENDING EXECUTION` |
| **Accessibility** | `a11y.md` | Axe core / keyboard navigation audit | WCAG 2.1 AA audit on 5 screens, contrast, keyboard flow | `PENDING EXECUTION` |

> [!NOTE]
> All artifacts in this directory must be generated from genuine execution results against the target environment. No synthetic or placeholder data is committed.
