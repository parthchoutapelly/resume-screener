# PHASE 5 of 5 — Integration Testing, Hardening, Deliverables & Demo
### Project: AI-Powered Resume Screener & Talent Acquisition Pipeline

| | |
|---|---|
| **Covers** | `Tasks.md` E10 (T-100–T-107), E11 (T-110–T-113) |
| **Owners** | Allen + Tejesh (testing), Gaurav (deliverables), Parth (sign-off) |
| **Prerequisites** | Phases 1–4 DoD checked on `dev`; T-007 fixtures and `truth.json` exist |
| **Read first** | `PRD.md` §9 (success criteria), §12 (edge cases) · `Rules.md` §10 (never-violate list) · `Architecture.md` §11 |
| **Produces** | Evidence that SC1–SC7 hold; the mentor deliverables; a rehearsed demo; a go/no-go decision |

> **Agent instructions.** This phase proves the system; it doesn't add features. Every check produces a stored artifact: a test report, a JSON output, or a screenshot under `docs/evidence/`, so results can be audited. If a test fails, fix it in the owning phase's code, cite the task ID, and re-run the whole affected section. Don't weaken a test to make it pass.

---

## 1. Automated test gates (T-100, T-101)

| Gate | Command | Pass |
|---|---|---|
| Lint | `make lint` (ruff, black --check, eslint) | 0 findings |
| Python unit | `pytest tests/unit --cov=rs_common` | green; `rs_common` ≥ 90% lines; experience ≥ 15 cases; scoring worked example = 71.3 |
| Python component | `pytest tests/component` (moto; extraction inside its image) | green |
| Frontend | `npm test -- --run` | green; status-mapping completeness test present |
| Data | `python scripts/validate_data.py` | green |

## 2. End-to-end integration (T-102)

`tests/integration/run.py --env dev` (Python, `requests` + `boto3`):
1. Authenticates as Recruiter A through Cognito SRP (test user; the password is read from the environment and **never** committed). Uses the ID token as `Authorization`.
2. `POST /jobs` with JD source `file` and the resume fixtures: 2 native PDF, 1 scanned PDF, 1 mixed PDF, 1 DOCX, 1 PNG, plus one "unsupported" case (a text file renamed `.pdf`, which passes API extension validation and exercises the magic-byte check).
3. Uploads every file through the returned presigned POSTs, **resumes first, then the JD after a 30 s delay** (exercises D-18).
4. Polls `GET /jobs/{id}/candidates` every 5 s, up to 15 min, until no row is in `processing|scoring|awaiting_jd`.
5. Asserts:
   - 6 rows `scored`, 1 row `error/unsupported_format`
   - each scored row has sub-scores, `matched_skills`, `scoring_version = v1`
   - `failed_jobs` has **no** `scoring` or `scoring_exhausted` rows
   - the "worked example" fixture scores 71.3
6. Shortlists the top candidate (whose fixture email is SES-verified), rejects them, and shortlists them again. Asserts `notification_status = sent`, and that the verified inbox received **exactly one** message (manual check or SES sending statistics).
7. `GET /jobs/{id}/export` → downloads the CSV → asserts it has 1 data row with the expected columns.
8. Writes `docs/evidence/integration-<date>.json` (timings per candidate, statuses, counts).

## 3. Failure-path matrix (T-103)

Each case gets its own small job so the results are unambiguous. Record the observed state and a screenshot of the job detail row.

| # | Case | How | Expected final state | Expected audit |
|---|---|---|---|---|
| F1 | Renamed text file | `.pdf` containing plain text | `error / unsupported_format`, immediately | 1 row, `terminal=true`, no redelivery |
| F2 | Corrupt PDF | Truncated PDF bytes | `error / unreadable_document`, immediately | 1 terminal row |
| F3 | Encrypted PDF | PDF with a user password | `error / unreadable_document` | 1 terminal row |
| F4 | Blank scan | A scanned blank page | `error / unreadable_document` | 1 terminal row (`ocr`) |
| F5 | Too many pages | 11-page PDF | `error / too_many_pages` | 1 terminal row |
| F6 | Never uploaded | Create a job with 1 filename, don't upload | `upload_missing` after 17 min | none |
| F7 | JD fails | Corrupt JD PDF + 2 good resumes | Job `blocking_reason=jd_failed`; rows `awaiting_requirements` → PATCH requirements → both `scored` | JD terminal row only |
| F8 | No skills in JD | JD text with no dictionary skills, no explicit skills | `no_required_skills` banner; nothing scored → PATCH → scored | none |
| F9 | Forced transient ingestion failure | Temporarily remove `s3:GetObject` from the extraction role, upload, restore after ~40 min | `error / processing_failed` | 3 `s3_download` rows + 1 `ingestion_exhausted`; alarm email |
| F10 | Forced scoring failure | Temporarily deny `UpdateItem` on candidates for scoreMatch | `error / scoring_failed`; `parse_status` still `parsed` | 5 `scoring` rows + 1 `scoring_exhausted`; alarm email |
| F11 | Duplicate event | `aws s3 cp` the same object onto itself (metadata-replace) after scoring | State unchanged (`scored`); decision unchanged; no second email | none |
| F12 | Decision on unscored | `POST decision` on a `processing` row | 409 `NOT_SCORED` | none |
| F13 | Missing email | Resume fixture without an email → shortlist | `notification_status = skipped_no_email`, decision saved | none |

## 4. Security verification (T-104)

Produce `docs/evidence/security-checklist.md` with a pass/fail result and the command output for each item.

| # | Check | Method | Pass |
|---|---|---|---|
| S1 | Unauthenticated | `curl` every route without a token | 401, **with** `Access-Control-Allow-Origin` header |
| S2 | Groupless user | Valid token, no group, every route | 403 |
| S3 | Cross-recruiter | Recruiter B hits every Recruiter A job-scoped route (GET job, PATCH, candidates, decision, resumes, resume-url, export) | 404 on all; DynamoDB unchanged |
| S4 | Admin-only | Recruiter on `/failed-jobs` | 403 |
| S5 | CORS | Preflight from the CloudFront origin → 200; from `https://evil.example` → no ACAO header | as stated |
| S6 | Buckets private | `get-public-access-block` both buckets; anonymous `curl` to an object URL | all true; 403 |
| S7 | TLS only | `aws s3api get-object --endpoint-url http://s3.ap-south-1.amazonaws.com …` | denied |
| S8 | Upload limits | POST an 11 MiB file with valid credentials; POST to a different key with the same policy | both rejected by S3 |
| S9 | CSV injection | Fixture name `=HYPERLINK("http://x","y")` → shortlist → export | cell starts with `'` |
| S10 | XSS | Fixture skill/name containing `<img src=x onerror=alert(1)>` | rendered as text everywhere, incl. Failures `raw_payload` |
| S11 | PII in logs | CloudWatch Logs Insights over all groups for a fixture email, name, and a distinctive resume phrase | 0 matches |
| S12 | IAM | Export each role policy; diff against the `Architecture.md` §8.1 matrix; search for `"Resource": "*"` | matches; only documented exceptions |
| S13 | Managed-AI references | `grep -rni "textract\|comprehend" backend/ frontend/src template.yaml` | 0 matches |
| S14 | Self sign-up | `aws cognito-idp sign-up …` | `NotAuthorizedException` |
| S15 | Headers | `curl -I https://<dist>/` | HSTS, CSP, nosniff, frame DENY present |

## 5. Quality evaluation — "is the NLP genuinely good enough?" (T-105)

`scripts/evaluate.py --env dev` compares stored candidate items with `tests/fixtures/truth.json` for all ≥10 fixture resumes and writes `docs/evaluation.md`:

| Metric | Definition | Target (SC3) |
|---|---|---|
| Skill precision | \|extracted ∩ truth\| / \|extracted\| (micro-avg) | ≥ 0.80 |
| Skill recall | \|extracted ∩ truth\| / \|truth\| | ≥ 0.70 |
| Name accuracy | exact match after whitespace/case normalization | ≥ 8/10 |
| Experience accuracy | \|computed − truth\| ≤ 1.0 year (unknown counts as a miss) | ≥ 7/10 |
| Title hit rate | ≥1 truth title in `titles_held` | report only |

For each miss, record the cause (dictionary gap, OCR noise, NER miss, section detection) and the fix. Fixes go into the data files or the experience rules, and never into fixture-specific code (R-HON-02). Re-run after the fixes and report both runs honestly.

## 6. Load & accessibility (T-106, T-107)

- **Load:** one job, 50 resumes (a 35 native / 10 scanned / 5 DOCX mix). Record the time for all to reach a terminal state, the maximum concurrent executions, `Throttles`, and DLQ receives in `docs/evidence/load-<date>.md`. Pass: all 50 terminal within 15 min, 0 DLQ receives, 0 throttle-induced failures (NFR-SCALE-1). If it fails, tune `MaximumConcurrency` (only within the quota) and record the new values in `Memory.md`.
- **Accessibility:** axe on the 5 screens (0 serious/critical), a keyboard-only walkthrough of Design §5 flows, and a contrast check on the badges and bars. Record the results in `docs/evidence/a11y.md`.

## 7. Deliverables (T-110, T-111)

| Deliverable | Path | Content | Source |
|---|---|---|---|
| Sample extraction + NLP output, 3 types | `docs/sample-nlp-output/{native_pdf,scanned_pdf,docx}.json` | `extracted_text` (from the same extraction image), `extraction_metadata`, entities from the deployed run, `method` per field (`ner` / `hybrid_phrase_matcher` / `deterministic`) | `scripts/capture_sample_output.py` — generated, not hand-edited |
| Matching logic write-up | `docs/deliverables.md` §1 | Formula, worked example, the title-family rule, experience rules and their honest limits, why empty skill requirements block scoring | `Architecture.md` §7.3, `Rules.md` §2 |
| Extraction/NLP architecture | `docs/deliverables.md` §2 | Free-plan constraint, open-source substitution, container vs zip, method-honesty table, provider boundary and migration path | `Details.md` §2–3, `02` §8.1 |
| Evaluation | `docs/evaluation.md` | §5 metrics and error analysis | T-105 |
| 3 enhancement ideas | `docs/deliverables.md` §3 | F1 custom NER, F2 cover-letter sentiment (soft signal), F3 blind screening + parity dashboard | `Tasks.md` Future |
| Licences & limitations | `docs/deliverables.md` §4 | PyMuPDF AGPL note; the `Memory.md` §9 limitations | — |

## 8. Demo script (T-112) — `docs/demo.md`, ~12 minutes

1. **Context (1 min):** problem, the Free-plan constraint, and "genuine NLP, honestly labelled".
2. **Create a job (2 min):** JD file + explicit threshold; upload 5 resumes (native, scanned, DOCX, image, renamed text file) and show the per-file progress.
3. **Live pipeline (2 min):** rows go Processing → Scoring → ranked. The renamed file turns into a clear error row. Point out that "Waiting for job description" rows resolved on their own.
4. **Explainability (2 min):** expand the top candidate and walk through the sub-scores × weights, matched/missing skills, the related-title 60 points, and the experience basis. Open `docs/sample-nlp-output/scanned_pdf.json` to show real OCR text and the `method` per field.
5. **Human-in-the-loop (2 min):** Recommended ≠ Shortlisted. Shortlist (the confirmation shows the email) → show the inbox. Reject → shortlist again → no second email.
6. **Recruiter control (1 min):** edit requirements → rescore; decisions unchanged. Export the CSV.
7. **Operations (1 min):** Admin → Failures view, stage legend, terminal vs retried rows; mention the alarms.
8. **Close (1 min):** evaluation numbers, limitations, the three enhancements, and the migration path if the account is upgraded.

Backup: a pre-recorded screen capture of steps 2–5, plus a pre-populated job, in case of network problems or cold starts during the demo.

## 9. Go / No-Go (T-113)

**Go** only if all of these hold:
- [ ] §1 gates green
- [ ] §2 integration passes on the stack that will be demoed
- [ ] §3 F1–F13 observed as expected
- [ ] §4 S1–S15 all pass (these cover every `Rules.md` §10 item)
- [ ] §5 metrics recorded (targets met, or misses explained in `docs/evaluation.md`)
- [ ] §6 load and accessibility recorded
- [ ] §7 deliverables present and generated from real runs
- [ ] Demo rehearsed live once end to end; backup recording exists
- [ ] `Memory.md` updated: D-34 outcome, final `MaximumConcurrency`, any new decisions; §7 errata show no open items
- [ ] SES recipients verified on the demo stack; budget alert not triggered

The project is complete when this checklist is signed off by the lead.
