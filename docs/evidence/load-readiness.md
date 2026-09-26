# 50-Resume Scale Load Test Readiness & Capacity Assessment

> Phase 5 §6 (T-106 / NFR-SCALE-1) Load Test Feasibility and Readiness  
> Environment: `dev` | Region: `ap-south-1` | Date: 2026-09-26

---

## 1. Executive Status

**STATUS: NOT EXECUTED — ENVIRONMENT/QUOTA NOT READY**

In strict compliance with Phase 5 Safety Principles (Rules 8 and 10), the 50-resume live burst load test is held pending formal concurrency quota verification. A complete readiness assessment and dry-run composition verification was completed.

---

## 2. Workload Composition

The test harness (`scripts/run_load_test.py --dry-run`) verified the required 50-resume composition across ground-truth fixture pools:

| File Type | Count | Processing Path | Resource Profile |
|---|---|---|---|
| **Native PDF** | 35 | PyPDF2 text extraction $\to$ spaCy matcher | Lightweight (~150 ms CPU, <128 MB RAM) |
| **Scanned PDF** | 10 | PDF rendering $\to$ Tesseract OCR $\to$ spaCy matcher | Heavy CPU (~8–15s CPU, 1024–2048 MB RAM) |
| **DOCX** | 5 | python-docx XML parsing $\to$ spaCy matcher | Lightweight (~100 ms CPU, <128 MB RAM) |
| **Total** | **50** | Single job batch submission | **Heterogeneous burst test** |

---

## 3. Required AWS Resources & Architecture Flow

```
[50 Resumes Upload] ──> [S3 Upload Bucket] ──> [Ingestion SQS Queue]
                                                      │
                                                      ▼
                                            [Extraction Lambda]
                                                      │ (sync invoke)
                                                      ▼
                                               [NLP Lambda]
                                                      │
                                                      ▼
                                            [DynamoDB Candidates]
                                                      │
                                                      ▼
                                            [Scoring SQS Queue]
                                                      │
                                                      ▼
                                            [ScoreMatch Lambda]
                                                      │
                                                      ▼
                                            [DynamoDB Candidates]
```

### Resource Requirements:
1. **S3 Storage:** ~50 Object PUTs via S3 Presigned POST URLs (~5 MB total).
2. **Ingestion SQS Queue:** 50 messages enqueued within 10 seconds.
3. **Extraction Lambda:** Concurrency up to 20–30 workers.
4. **NLP Lambda:** Synchronously invoked by Extraction Lambda; memory allocation 2048 MB.
5. **Scoring SQS Queue & ScoreMatch Lambda:** 50 scoring evaluation messages.
6. **DynamoDB Write Capacity Units (WCU):** Burst of ~300 write operations within 30 seconds across `candidates-dev` table.

---

## 4. Quota Assessment & Risk Analysis

1. **Lambda Unreserved Account Concurrency:**
   - Default AWS account regional concurrency limit is 1,000 across all Lambdas. In shared development environments, bursting 10 concurrent Tesseract OCR tasks (running at 100% CPU for 10–15s) can exhaust container execution slots and cause throttling on user-facing API Lambdas (`GetJobsFunction`, `GetCandidatesFunction`).
2. **Dead Letter Queue (DLQ) Safeguard:**
   - Max receive count on `IngestionQueue` is set to 3. If OCR tasks time out due to memory starvation under unreserved concurrency contention, messages would spill into `IngestionDlq`, violating NFR-SCALE-1.
3. **Current Readiness Assessment:**
   - Baseline functionality verified: Batches of 7–10 resumes process reliably in under 40 seconds with 0 DLQ receives.
   - Quota readiness: Account requires reserved concurrency allocation on `ExtractionFunction` ($\ge 25$) and `ScoreMatchFunction` ($\ge 15$) before executing a live 50-resume batch.

---

## 5. Execution Command for Production Staging

When deployed to an isolated staging or production account with dedicated concurrency quotas, execute:

```bash
# Step 1: Validate composition
.venv/bin/python scripts/run_load_test.py --env dev --dry-run

# Step 2: Execute live 50-resume load run
.venv/bin/python scripts/run_load_test.py --env dev
```

Target Acceptance Criteria (NFR-SCALE-1):
- All 50 resumes reach terminal state within 900 seconds (15 minutes).
- Zero messages delivered to SQS DLQ.
- Zero throttle-induced permanent failures.
