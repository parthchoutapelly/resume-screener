# AI-Powered Resume Screener & Talent Acquisition Pipeline
### Details.md — Project Narrative & Rationale
**Team:** Parth Choutapelly (Lead), Tejesh, Allen, Gaurav · **Region:** ap-south-1 (Mumbai) · **IaC:** AWS SAM
**Status:** Specification complete, build not started (2026-09-23)

> **What this file is for:** the story of the project: the problem, the constraint that shaped it, and the reasoning behind its biggest choices, written for the mentor, new teammates, and the final write-up. It is deliberately **not** the place for requirements, schemas, or API shapes. Those live in the spec set, and this file links to them rather than copying them, so the two can't drift apart:
>
> | Need | Go to |
> |---|---|
> | Requirements, success criteria, edge cases, open questions | `PRD.md` |
> | Components, data model, API, IAM, failure handling | `Architecture.md` |
> | Invariants and forbidden behaviour | `Rules.md` |
> | Screens, flows, states, copy | `Design.md` |
> | Decision log, glossary, pitfalls, superseded items | `Memory.md` |
> | Build plan | `Tasks.md` + phase files `01`–`05` |
> | Build/run/debug handbook | `Implementation.md` |

---

## 1. The Problem

Recruiters screen resumes by hand: open each PDF or DOCX, skim for keywords, guess at fit. It's slow, inconsistent between reviewers, and leaves no record of *why* someone was passed over. Keyword-based ATS filters are fast but opaque: they reward phrasing, not substance, and hide their reasoning.

This project builds a serverless pipeline in which a recruiter uploads a job description and a batch of resumes, and gets back a **ranked, explainable shortlist**. Real document extraction and real named-entity recognition turn each resume into structured data, a transparent weighted formula scores it, and a dashboard lets the recruiter make the actual decision. The one action that reaches a candidate, the shortlist email, is always taken by a human.

## 2. The Constraint That Shaped Everything

The mentor brief originally specified **Amazon Textract** (OCR) and **Amazon Comprehend** (NER). The AWS account this project deploys into is on the **Free plan**, and AWS Support confirmed that both services require the Paid plan. That's a limitation of this account's plan, not a verdict on the services.

The response is a genuine substitution, not a downgrade:

| Original | Replacement | Genuinely equivalent capability? |
|---|---|---|
| Textract `DetectDocumentText` | `pypdf` for text-native PDF pages; PyMuPDF rendering + **Tesseract** OCR for scanned pages and images; `python-docx` for DOCX | Yes: real text extraction and real OCR |
| Comprehend `DetectEntities` | **spaCy** `en_core_web_sm` statistical NER (`PERSON`, `ORG`, `DATE`) | Yes: a trained model working from linguistic features |

Everything runs inside this AWS account's own Lambda functions, so no candidate data goes to any third-party API. The extraction → NLP → scoring boundaries are explicit contracts, so if the account is ever upgraded, swapping either stage for a managed service is a scoped follow-on project rather than a redesign (future enhancement F4). Scoring, the API, and the UI never know which engine produced the data.

## 3. What "Genuine NLP" Means Here — Stated Honestly

The mentor's brief pushed for real ML, not a regex scanner relabelled as AI. The trap is that **no general-purpose NER model has `SKILL` or `JOB_TITLE` entity types**: Comprehend's `TITLE` means the title of a creative work, and spaCy has no such types at all. They're domain concepts, not linguistic ones.

So the project is precise about which field comes from which method, and says so in its code, UI, and write-up:

| Field | Method | Is it NLP? |
|---|---|---|
| Candidate name | spaCy `PERSON` entities, preferring the top of the document | Yes |
| Employers | spaCy `ORG` entities (minus things that are really skills, like "AWS") | Yes |
| Date mentions | spaCy `DATE` entities — used to corroborate employment ranges | Yes |
| Skills, job titles | spaCy tokenizer + `PhraseMatcher` against curated dictionaries, then synonym normalization | Hybrid: tokenizer-aware matching, controlled vocabulary |
| Years of experience | Deterministic date-range parsing within the experience section, overlapping jobs merged | No — arithmetic on top of the text |
| Email, JD minimum years | Regex | No |

Dictionaries only **normalize** ("k8s" → "kubernetes") or **detect a phrase that is present**. They never invent an entity, and nothing ever keys off a filename. Where the system doesn't know something (no dates found, no name found), it says "Unknown" rather than guessing. The flagship enhancement, a custom-trained NER model for skills and titles (F1), is the principled way to move those fields from "hybrid" to "learned".

## 4. How It Works (one paragraph per stage)

`Architecture.md` §1 has the diagram and §3 has the sequences.

1. **Create & upload.** The recruiter creates a job from a JD file, pasted JD text, or explicit requirements alone. The API creates placeholder records and returns short-lived, size-limited presigned POST credentials, and the browser uploads straight to a private S3 bucket.
2. **Extraction.** S3 events land on one queue for both JDs and resumes. A container-image Lambda checks each file is what it claims to be, extracts native text page by page, and OCRs only the pages that need it.
3. **NLP.** Extraction synchronously invokes the NLP Lambda, which runs spaCy once per document and writes structured entities. A resume then queues itself for scoring. A JD writes its *derived* requirements (never overwriting what the recruiter typed) and re-queues every resume already waiting on it.
4. **Scoring.** A small pure function computes 50% skills + 30% title + 20% experience and stores the explanation alongside the score. If the job isn't ready yet, scoring simply stands down; the JD's completion triggers it again.
5. **Review.** The dashboard polls while work is in flight, shows every candidate in a named state, and lets the recruiter expand any score into its evidence. Shortlisting shows exactly which address will be emailed, and each candidate is emailed at most once.
6. **When things fail.** Deterministic failures (wrong format, corrupt, unreadable, too long) are recorded once and shown immediately. Transient ones retry automatically and, if they never recover, end in a visible error with an audit trail and an alarm.

## 5. Why the Architecture Looks Like This

The decisions below are logged with "revisit only if" conditions in `Memory.md` §3; this section gives the reasoning.

- **Serverless + SQS.** Load is spiky (a batch of 50 uploads, then silence), so pay-per-use fits. Queues give burst smoothing, free retries, and fault isolation: one bad resume never blocks the batch. The queues are no longer justified by Textract/Comprehend rate limits, which don't apply; they remain because of those other properties.
- **Container image for extraction only.** Tesseract is a native binary. A container image installs it through an OS package manager, which is far more reliable than a hand-assembled Lambda layer. NLP needs no OS packages, so it stays a lighter zip function with faster cold starts.
- **A synchronous hand-off between extraction and NLP, not a third queue.** It keeps two independently deployable, independently permissioned functions without extra queue infrastructure. An NLP failure still flows back through the ingestion queue's retry policy.
- **Scoring waits by being re-triggered, not by retrying.** An earlier draft had scoring throw "JD not ready" and let SQS retry. A JD that needed a single slow retry would have exhausted every resume's scoring attempts and marked healthy candidates as failed. Re-triggering on JD completion is race-free and simpler to reason about (`Architecture.md` §3.3).
- **Terminal vs transient errors.** Retrying a corrupt PDF three times can never succeed; it only delays the error by ~36 minutes. Classifying errors lets the dashboard show a real reason within seconds.
- **HTTPS everywhere.** The SPA is served by CloudFront from a private bucket. The earlier plan of S3 static website hosting would have needed a public bucket and served login pages over plain HTTP.
- **Per-recruiter isolation, enforced server-side.** Every job-scoped route checks ownership. The earlier API only filtered the job list, which meant any recruiter could read any job by guessing its ID.
- **Bounded concurrency.** New AWS accounts can have a Lambda concurrency quota as low as 10. When Lambda throttles an SQS consumer, the messages' receive counts climb, so a burst could push healthy resumes to the dead-letter queue. `MaximumConcurrency` on each queue trigger prevents that.

## 6. Scoring, Explained

```
match_score = 0.5 × skills_score + 0.3 × title_score + 0.2 × experience_score
```
- **Skills:** the share of the job's required skills found in the resume, after synonym normalization. A job with **no** required skills can't be scored at all: the recruiter is asked to add some, rather than everyone being handed 50 free points.
- **Title:** 100 for an exact match with any title the candidate has held; 60 if it's in the same *title family* (e.g. backend developer ~ backend engineer); otherwise 0. With no title requirement the dimension counts as met. It uses the best match across all titles held because "most recent title" can't be extracted reliably from free text.
- **Experience:** the candidate's years divided by the required years, capped at 100. Unknown experience scores 0 and is displayed as "Unknown", never as "0 years".
- **Recommended** means the score is at or above the job's threshold (default 70). It is advice for the recruiter; it triggers nothing.

**Worked example.** The JD requires `python, aws, dynamodb`, the title *Backend Engineer*, and 3 years. The candidate has `python, aws, sql`, was a *Backend Developer*, and has 4 years.
Skills 2/3 = 66.7 → 33.3 · Title related → 60 → 18.0 · Experience 4/3 capped → 100 → 20.0 · **Total 71.3 → Recommended**

Scoring never reads a candidate's name, email, employers, or contact details. That's a fairness baseline, and it's the foundation for the blind-screening enhancement (F3).

## 7. Security & Privacy Posture (summary)

Private buckets only, TLS only; Cognito login with no self sign-up; group membership plus job ownership checked on every request; least-privilege IAM per function; presigned uploads capped at 10 MiB with server-chosen object names; uploaded documents treated as hostile input (size, page, and pixel caps). Resume content never appears in logs. CSV exports are protected against formula injection. The rules themselves are in `Rules.md` §3–4 and §9.

**Personal data:** resumes contain names, emails, and phone numbers. All test and demo data is synthetic. Retention: uploads 180 days (pending confirmation, OQ9), exports 7 days, logs 30 days, failure audit 90 days.

**SES** starts in sandbox mode, so only verified recipient addresses receive mail. Verify the demo inboxes early, or request production access (approval can take a day).

## 8. Team & Phases

Ownership is a proposal for the team to confirm.

| Phase file | Scope | Owner |
|---|---|---|
| `01-infrastructure-setup.md` | Platform spikes, SAM scaffold, storage, queues, auth, hosting, budget | Parth |
| `02-ingestion-pipeline.md` | Shared library, extraction, NLP | Parth |
| `03-scoring-and-api.md` | Scoring, REST API, reliability, alarms | Allen |
| `04-frontend-dashboard.md` | React dashboard, CloudFront release | Tejesh |
| `05-integration-testing-and-delivery.md` | Integration, failure, security, and quality testing; deliverables; demo | Allen + Tejesh; Gaurav (deliverables) |

## 9. Cost

At internship scale (dozens of resumes, not thousands), everything sits at or near the free allowances. The main variable cost is the extraction Lambda's compute (1.5 GB memory, longer for scanned documents), then NLP, then a small flat ECR storage charge. CloudFront, DynamoDB on-demand, SQS, S3, and SES are effectively free at this volume. There are no per-page AI-service charges, which is a side benefit of the constraint rather than its purpose. A monthly AWS Budget alert (suggested USD 10) is part of phase 1.

## 10. Deliverables (for the mentor)

- [ ] End-to-end demo: upload → extraction → NLP → scoring → decision → email → export
- [ ] Sample extraction + NLP output for 3 resume types (text PDF, scanned PDF, DOCX) in `docs/sample-nlp-output/`, generated from real runs
- [ ] Recruiter dashboard showing ranked matches with skill tags and score breakdowns
- [ ] Written explanation of the matching logic and the extraction/NLP architecture (`docs/deliverables.md`)
- [ ] Measured extraction quality on a labelled synthetic set (`docs/evaluation.md`)
- [ ] 3 enhancement ideas (below)

## 11. Future Enhancements

1. **Custom NER for `SKILL` and `JOB_TITLE`.** Fine-tune spaCy's NER (or a small transformer) on labelled resumes built during evaluation, replacing dictionary detection with a learned model while keeping normalization. This is the direct successor to the brief's "Comprehend Custom Entity Recognizer" idea.
2. **Cover-letter sentiment as a soft signal.** Surface it next to the candidate and never feed it into the score, so writing style isn't penalized over substance. Use an open-source sentiment model now, or Comprehend `DetectSentiment` if the account is upgraded.
3. **Blind screening + fairness dashboard.** Scoring already ignores identity fields. Add a UI mode that hides names and contact details until a decision is made, plus a shortlist-rate parity view across candidate pools.
4. **Textract/Comprehend migration** if the account moves to the Paid plan, as a second `nlp_engine_mode` behind the existing boundary.

Further candidates (duplicate-resume detection, deletion/erasure requests, semantic skill matching) are listed in `Tasks.md` → Future Enhancements.

## 12. Open Questions

These are tracked with their working assumptions in `PRD.md` §13. The ones that most need a mentor answer: whether a trained custom NER is required for the base deliverable (assumed no); whether recruiters may open the original resume through a 60-second link (assumed yes); and the data retention period (assumed 180 days, synthetic data only).
