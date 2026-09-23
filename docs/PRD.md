# PRD — AI-Powered Resume Screener & Talent Acquisition Pipeline

**Status:** Specification (pre-build) · **Region:** ap-south-1 · **Team:** Parth (lead), Tejesh, Allen, Gaurav
**Doc set:** `PRD.md` (what/why) · `Architecture.md` (structure) · `Rules.md` (invariants) · `Design.md` (experience) · `Memory.md` (decisions & context) · `Tasks.md` (execution plan)
**Companion docs:** `Details.md` (narrative & rationale), `Implementation.md` (developer handbook), phase files `01`–`05` (build instructions). All were revised on 2026-09-23 to match this spec set; the history of what changed is in `Memory.md` §7.

---

## 1. Problem & Motivation

Recruiters screen resumes by hand: open each PDF/DOCX, skim for keywords, guess at fit. It is slow, inconsistent between reviewers, and impossible to audit afterwards ("why was this person rejected?"). Keyword-based ATS filters are fast but opaque and brittle — they reward phrasing, not substance, and they hide their reasoning.

The mentor brief asks for **genuine NLP/ML**, not a regex scanner relabelled as AI, and the AWS account available is on the Free plan, which cannot call Amazon Textract or Amazon Comprehend (`Details.md` §2). The product must therefore deliver real extraction and real NER on open-source components, and be honest about exactly which fields come from a model and which come from deterministic rules.

## 2. Product Vision

> A recruiter hands the system one job description and a stack of resumes, and within minutes gets back an **explainable, ranked shortlist**. Every score can be traced to text that is actually in the resume, every failure is visible, and every action that reaches a candidate is taken by a human.

Three properties define the product and must survive every future change:

1. **Explainable** — a score is never just a number. The recruiter can see matched/missing skills, the title match, and how experience was computed.
2. **Honest** — no fabricated entities, confidences, or "AI" labels on deterministic logic (`Rules.md` §1).
3. **Human-in-the-loop** — the system *recommends*; only a recruiter *decides*. No automated outbound communication.

## 3. Goals & Non-Goals

### Goals
| ID | Goal |
|---|---|
| G1 | End-to-end automated pipeline: upload JD + resumes → structured, scored, ranked candidates with no manual step |
| G2 | Genuine NLP: statistical NER (spaCy) for person/org/date entities; clearly labelled hybrid/deterministic methods for skills, titles, experience, email |
| G3 | Explainable ranking: sub-scores and matched/missing evidence per candidate |
| G4 | Every document ends in a visible terminal state (scored, or an error with a reason); nothing spins forever |
| G5 | Secure by default: authenticated, per-recruiter data isolation, private storage, HTTPS end to end |
| G6 | Demoable from a clean Free-plan AWS account within the internship timeline |

### Non-Goals (MVP)
| ID | Non-goal | Why |
|---|---|---|
| NG1 | Multi-language resumes | `en_core_web_sm` is English-only |
| NG2 | Trained custom NER for SKILL/JOB_TITLE | Flagship future enhancement (`Tasks.md` §F1) |
| NG3 | Interview scheduling beyond a placeholder email | Out of brief scope |
| NG4 | ATS / job-board integrations | Out of brief scope |
| NG5 | Candidate-facing portal or self-application | Recruiters upload on candidates' behalf |
| NG6 | Automatic rejection or automatic emails based on score | Violates human-in-the-loop principle (`Rules.md` R-BUS-06) |
| NG7 | Textract/Comprehend integration | Account-plan constraint; migration path preserved (`Details.md` §2) |
| NG8 | Multi-JD re-matching of one resume pool | One JD per job posting (see OQ3) |
| NG9 | High availability / multi-region / SLA | Internship demo system |

## 4. Users & Use Cases

| Persona | Description | Access |
|---|---|---|
| **Recruiter** | Creates job postings, uploads documents, reviews ranked candidates, decides, exports | Own jobs only |
| **Admin** | Everything a Recruiter can do, across all jobs, plus the failure/audit view | All jobs + `failed_jobs` |
| **Candidate** (passive) | Never logs in. Receives a shortlist email if a recruiter shortlists them | None |
| **Evaluator** (mentor) | Judges genuineness of NLP, reliability, security, deliverables | Demo + docs |

| ID | Use case |
|---|---|
| UC1 | Recruiter creates a job from a JD file, pasted JD text, or explicit requirements only, and uploads up to 50 resumes |
| UC2 | Recruiter watches rows move from "Processing" to scored without refreshing the page |
| UC3 | Recruiter reviews the ranked list, opens a candidate's score breakdown, and shortlists or rejects |
| UC4 | Recruiter corrects the job's requirements or threshold after seeing results; candidates are re-scored automatically, decisions preserved |
| UC5 | Recruiter adds more resumes to an existing job, or re-uploads one that failed |
| UC6 | Recruiter exports the human-shortlisted candidates as CSV |
| UC7 | Admin triages failures: which stage failed, why, and for which job |
| UC8 | Evaluator inspects sample extraction + NLP output for 3 resume types and reads the method-honesty table |

## 5. Core Functionality

1. **Job posting management** — create, list, view, and edit requirements/threshold.
2. **Direct-to-S3 upload** — size-limited, short-lived presigned POST; the browser never streams file bytes through the API.
3. **Document extraction** — native PDF text, DOCX paragraphs + tables, OCR for scanned PDF pages and standalone images.
4. **NLP entity extraction** — spaCy NER + `PhraseMatcher` dictionaries + deterministic experience computation.
5. **Weighted scoring** — 50% skills / 30% title / 20% experience, with a stored explanation.
6. **Recruiter dashboard** — ranked table with live status, score breakdown, decisions, CSV export.
7. **Notifications** — one shortlist email per candidate, triggered only by a human decision.
8. **Failure visibility** — audit log for Admins, plain-language error states for Recruiters.

## 6. Functional Requirements

Priority: **M** = MVP (must ship), **S** = should ship if time permits, needed for a smooth demo. IDs FR1–FR17 keep the meanings they had in the original `Details.md` (pre-2026-09-23). Rows marked *(mod)* tighten or correct the original; FR18+ are new.

| ID | Requirement | Pri | Trace |
|---|---|---|---|
| FR1 *(mod)* | Recruiter creates a job posting with title, JD source (`file` \| `text` \| `none`), optional explicit required skills/titles/min experience, shortlist threshold (0–100, default 70). With `jd.source = none`, at least one required skill is mandatory. | M | Arch §5, R-VAL-01 |
| FR2 *(mod)* | Recruiter uploads a JD file and up to 50 resumes per request. Allowed: `pdf, docx, png, jpg, jpeg, tiff`. Max 10 MiB per file. Invalid files are rejected **before** upload. | M | R-VAL-02..04 |
| FR3 | Every uploaded document is processed automatically. | M | Arch §3.2 |
| FR4 | The structured candidate record holds name, email, employers, titles held, skills, and total experience years (or "unknown"). | M | Arch §6.2 |
| FR5 *(mod)* | The JD goes through the same pipeline. JD-derived requirements **only fill fields the recruiter did not supply explicitly**; both values are stored. | M | R-BUS-03 |
| FR5a *(mod)* | Scanned content is detected **per page**: a page with too little native text is OCR'd; mixed PDFs work. Detection never uses filename or user flags. | M | R-HON-04 |
| FR6 *(mod)* | Each parsed candidate gets a 0–100 score once the job is **scorable** (JD no longer processing, ≥1 effective required skill). | M | R-BUS-04 |
| FR7 | Score = 0.5·skills + 0.3·title + 0.2·experience (`Details.md` §6; exact rules in `Architecture.md` §7.3). | M | |
| FR8 *(mod)* | Candidates with `match_score ≥ threshold` are flagged **Recommended**. This flag triggers nothing. | M | R-BUS-06 |
| FR9 | Scoring never blocks ingestion; one bad document never blocks others. | M | |
| FR10 | Dashboard lists the caller's jobs (Admin: all jobs). | M | R-AUTH-03 |
| FR11 *(mod)* | Job detail lists **all** candidates: scored rows by score descending, then non-scored rows grouped by status. Skill tags visible. | M | Design §4.4 |
| FR12 *(mod)* | One-click Reject; Shortlist opens a confirmation showing the address the email will go to. Decisions can be changed. | M | Design §5.3 |
| FR13 *(mod)* | Shortlisting sends one email per candidate, ever (at most once). If sending fails, the decision is still saved and the failure is shown. | M | R-BUS-07/08 |
| FR14 | CSV export of human-shortlisted candidates. | M | R-SEC-09 |
| FR14a *(mod)* | Every candidate reaches a visible terminal or explicitly-flagged state: `scored`, `error`, `upload_missing`, `stalled`, `awaiting_requirements`. No indefinite spinner. | M | Arch §7.2 |
| FR15 | Every failure is recorded with stage and reason; nothing is silently dropped. | M | R-ERR-01 |
| FR16 *(mod)* | Genuine scoring errors retry automatically (up to 5). "JD not ready yet" is **not** an error: scoring is re-triggered when the JD finishes. | M | D-18 |
| FR17 | Every API route requires a valid Cognito token **and** membership of `Recruiter` or `Admin`. | M | R-AUTH-01/02 |
| FR18 | Recruiter can add resumes to an existing job (also the recovery path for failed or missing uploads). | M | Arch §5 |
| FR19 | Recruiter can edit requirements/threshold; affected candidates are re-scored automatically; decisions and sent emails are untouched. | M | R-BUS-05 |
| FR20 | Job detail shows the **effective** requirements and where each came from (recruiter vs derived from JD). | M | Design §4.4 |
| FR21 | Per-candidate explanation: matched skills, missing skills, matched title (exact/related/none), sub-scores, experience basis (computed/estimated/unknown). | M | D-41 |
| FR22 | Recruiter can open the original resume through a 60-second link, after an ownership check. | S | OQ8 |
| FR23 | A recruiter can never see or act on another recruiter's jobs or candidates. | M | R-AUTH-03 |
| FR24 | Admin failure view, filterable by job, newest first, with a stage legend. | M | Design §4.5 |
| FR25 | Upload screen shows progress per file, per-file failures, and retry. | M | Design §5.1 |
| FR26 | Job detail refreshes automatically while any row is not terminal. | M | D-44 |
| FR27 | A job with no scorable requirements is flagged prominently and never scored with "free" points. | M | D-30 |

## 7. Non-Functional Requirements

Targets marked † are demo targets to be validated in E10 testing (`Tasks.md`), not guarantees.

| ID | Category | Requirement |
|---|---|---|
| NFR-SEC-1 | Security | No public buckets; Block Public Access on every bucket; frontend served over HTTPS only (CloudFront + OAC) |
| NFR-SEC-2 | Security | Least-privilege IAM role per Lambda, scoped by ARN/prefix; no `*` resources; no `textract:*`/`comprehend:*` anywhere |
| NFR-SEC-3 | Security | Self sign-up disabled; accounts are created by Admins |
| NFR-PRIV-1 | Privacy | Resume text, emails, and phone numbers never appear in logs or `failed_jobs.error_message` |
| NFR-PRIV-2 | Privacy | Candidate data never leaves the AWS account, except the shortlist email to the candidate |
| NFR-PERF-1† | Latency | A single native PDF/DOCX resume is scored ≤ 90 s after the upload completes (warm) |
| NFR-PERF-2† | Latency | A 2-page scanned resume is scored ≤ 3 min after upload |
| NFR-PERF-3† | API | p95 ≤ 1 s for read endpoints, excluding cold starts |
| NFR-SCALE-1† | Throughput | A batch of 50 mixed resumes reaches terminal states within 15 min at the configured concurrency |
| NFR-REL-1 | Reliability | Every candidate reaches a terminal or flagged display state within 60 min of creation |
| NFR-REL-2 | Reliability | Duplicate S3/SQS deliveries cause no duplicate emails and no state regression |
| NFR-COST-1 | Cost | Pay-per-use only; monthly AWS Budget alert (amount: OQ10, suggested USD 10); CloudWatch log retention 30 days |
| NFR-OBS-1 | Observability | Structured JSON logs with `job_id`, `candidate_id`, `stage`, `request_id`; alarms on terminal failures, Lambda errors/throttles, API 5xx |
| NFR-A11Y-1 | Accessibility | WCAG 2.1 AA for dashboard screens (`Design.md` §8) |
| NFR-MAINT-1 | Maintainability | Scoring and normalization are pure functions with unit tests; extraction/NLP boundary contract stable (`Implementation.md` §4.2) |
| NFR-DEMO-1 | Demo-ability | Deployable from clean with `sam build --use-container && sam deploy` plus the documented manual steps |

## 8. Key Workflows

Detailed sequences are in `Architecture.md` §3; screen-level flows are in `Design.md` §5.

- **W1 Create & upload:** fill form → client-side validation → `POST /jobs` → presigned POSTs (≤4 concurrent) → navigate to job detail. Failed uploads can be retried from the job detail page (FR18).
- **W2 Processing:** S3 event → IngestionQueue → extraction → NLP → DynamoDB. Resume parsed → ScoringQueue. JD parsed → re-score every parsed candidate of that job.
- **W3 Review & decide:** job detail polls → recruiter expands a row to see the breakdown → Reject (instant) or Shortlist (confirm shows email address) → email sent at most once.
- **W4 Export:** Export → CSV of shortlisted candidates via a presigned GET that expires in 5 min.
- **W5 Fix requirements:** job flagged "needs requirements" or "JD failed" → recruiter edits requirements → re-score fan-out.
- **W6 Admin triage:** failures view → filter by job → read stage + message → recovery through FR18 or a manual replay (runbook in `Architecture.md` §11.6).

## 9. Success Criteria

| ID | Criterion | Measure |
|---|---|---|
| SC1 | Pipeline works end to end | Integration test: JD + 5 resumes (native PDF, scanned PDF, DOCX, image, one unsupported) → 4 scored, 1 error; no manual step |
| SC2 | Genuine NLP, honestly labelled | Deliverable lists the method per field; code review finds no filename branching, canned text, or fabricated confidences |
| SC3 | Extraction quality is acceptable† | On a labelled set of ≥10 synthetic resumes: skill precision ≥ 0.8 and recall ≥ 0.7; name correct ≥ 8/10; experience within ±1 year for ≥ 7/10 |
| SC4 | No stuck rows | Forced-failure tests all show a terminal state on the dashboard |
| SC5 | Isolation holds | Recruiter B gets 404 on every Recruiter A job URL; a user with no group gets 403 everywhere |
| SC6 | Email correctness | Shortlist → reject → shortlist sends exactly one email |
| SC7 | Deliverables complete | `docs/sample-nlp-output/` (3 types), `docs/deliverables.md` (matching logic, extraction/NLP architecture, 3 enhancements) |

## 10. Constraints

| ID | Constraint |
|---|---|
| C1 | The AWS account is on the Free plan: no Textract/Comprehend. Some other services may be restricted (validate — A1) |
| C2 | Region ap-south-1; IaC is AWS SAM; Python 3.12 |
| C3 | Four-person team, internship timeline |
| C4 | SES sandbox: sender and recipients must be verified unless production access is granted |
| C5 | Lambda limits: 6 MB synchronous payload, 250 MB unzipped zip+layers, 10 GB image, 15 min max timeout |
| C6 | English-only NLP model |
| C7 | The build host is macOS (Apple Silicon likely); Lambda artifacts must be Linux x86_64 (D-33) |

## 11. Assumptions (validate — each has an owner task in `Tasks.md` E0)

| ID | Assumption | If wrong |
|---|---|---|
| A1 | CloudFront, SES, ECR, and SQS/Lambda event source mappings are usable on the Free plan | Replace CloudFront with Amplify Hosting or local-only frontend demo; re-plan email |
| A2 | Account Lambda concurrency quota ≥ 10 | Request a quota increase; lower `MaximumConcurrency` to 2/2 |
| A3 | Tesseract can be installed in a Lambda-compatible image (D-34) | Debian-slim + `awslambdaric` fallback |
| A4 | spaCy + `en_core_web_sm` + dateutil fit within 250 MB unzipped for the NLP function | Package NLP as a container image too |
| A5 | Batches are 5–50 resumes; ≤200 candidates per job | Paginate UI; revisit in-Lambda sort |
| A6 | Resumes are ≤10 pages and ≤10 MiB | Raise limits; timeout/memory tuning |
| A7 | Test data is synthetic (no real candidate PII in the repo or demo) | Must get consent; add a retention policy |
| A8 | The free-plan account lifetime covers the internship | Upgrade the plan (which would also unlock the Textract/Comprehend migration) |

## 12. Important Edge Cases

| Case | Expected behaviour | Ref |
|---|---|---|
| Upload never happens (tab closed) | Row becomes `upload_missing` shortly after URL expiry; recruiter can re-add | Arch §7.2 |
| Unsupported or misnamed file (e.g. `.pdf` that is really text) | Rejected at API by extension; magic-byte mismatch at extraction → terminal `unsupported_format`, no retry | R-VAL-05 |
| Encrypted or corrupt PDF | Terminal `unreadable_document`, immediately, no 3× retry | D-19 |
| Scanned page with near-empty OCR output | Terminal `unreadable_document` if total usable text < 100 chars | R-VAL-07 |
| Mixed PDF (text pages + scanned pages) | Only the scanned pages are OCR'd | D-42 |
| >10 pages | Terminal `too_many_pages` | R-VAL-06 |
| Resume parsed before JD | Row shows "Waiting for JD"; scored automatically when the JD is parsed | D-18 |
| JD fails permanently | Job banner "JD couldn't be processed — confirm requirements"; recruiter confirms/edits → scoring runs | D-29 |
| No required skills after JD parse | Job flagged `no_required_skills`; no scores until fixed | D-30 |
| No email found in resume | Shortlist still allowed; confirmation says no email will be sent; `notification_status=skipped_no_email` | R-BUS-08 |
| NER picks the wrong name ("Curriculum Vitae") | Shown as-is with the filename alongside; email greeting falls back to "Hello," when there's no name | Design §6 |
| Overlapping jobs / education dates | Intervals merged; education section excluded; unknown → shown as "Unknown", not 0 | D-27 |
| Same candidate uploaded twice | Two independent rows (dedupe is future work F5) | Tasks §F |
| Duplicate S3 event | Re-processing is idempotent; no status regression; no second email | R-DATA-04 |
| Candidate-supplied text starting with `=` in CSV | Escaped | R-SEC-09 |
| Recruiter changes threshold after decisions | `Recommended` recomputed; decisions unchanged | R-BUS-05 |
| Groupless Cognito user | 403 on every route | R-AUTH-02 |

## 13. Open Questions

Carried from the original `Details.md` open questions (with the assumption this spec proceeds on), plus new ones.

| ID | Question | Working assumption |
|---|---|---|
| OQ1 | Is a trained custom NER required for the base deliverable? | No — flagship enhancement |
| OQ2 | JD input: file only, or pasted text too? | Both, plus "requirements only" (FR1) |
| OQ3 | Single JD per posting? | Yes |
| OQ4 | Threshold fixed or per-job? | Per-job, default 70, editable (FR19) |
| OQ5 | SES production access or sandbox? | Sandbox with verified test addresses; request production access early only if demoing to real inboxes |
| OQ6 | Batch ceiling? | 50 per request, 200 per job |
| OQ7 | Pursue Textract/Comprehend if the account is upgraded? | Not in this build; stays future F4 |
| OQ8 | **New:** may recruiters view the original resume (FR22)? It relaxes "raw files never served to the frontend" to "served only via 60 s presigned GET after an ownership check" | Yes (S priority) — mentor to confirm |
| OQ9 | **New:** retention for uploaded resumes and candidate records (PII; India's DPDP Act may apply to real data) | Synthetic data only; 180-day lifecycle on upload prefixes proposed |
| OQ10 | **New:** monthly budget alert amount | USD 10 |
| OQ11 | **New:** should title matching use "most recent title" (as the original `Details.md` stated) when recency can't be reliably extracted? | No — best match across all titles held (D-26) |
