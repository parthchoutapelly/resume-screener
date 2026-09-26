# Resume Screener — Technical Deliverables & Architecture Report

> Phase 5 §9 (T-111) System Deliverables, Architecture & Technical Design Documentation  
> Version: `v1` | Target Region: `ap-south-1` | Environment: `dev`  
> Baseline Release: 2026-09-26

---

## 1. Candidate Matching & Scoring Engine (§1)

The Resume Screener ranking engine computes deterministic, explainable match scores ($0.0 \dots 100.0$) evaluated against job description requirements. All scoring is versioned (`scoring_version = v1`) to guarantee reproducibility and auditability.

### Formula & Weight Distribution

$$\text{Match Score} = (0.50 \times \text{Skills Score}) + (0.30 \times \text{Title Score}) + (0.20 \times \text{Experience Score})$$

```
+-----------------------------------------------------------------------+
|                         FINAL MATCH SCORE (100%)                     |
+-----------------------------------+-------------------+---------------+
|       Skills Score (50%)          | Title Score (30%) | Exp Score (20%)|
+-----------------------------------+-------------------+---------------+
```

#### Component Calculations:
1. **Skills Sub-Score ($50\%$ weight):**
   $$\text{Skills Score} = \left(\frac{|\text{Matched Skills}|}{|\text{Required Skills}|}\right) \times 100$$
   - Matched against controlled skills taxonomy (`skills_dictionary.json` + `synonyms.json`).
   - Case-insensitive hybrid PhraseMatcher (with case-sensitive handling for acronyms like `C`, `R`, `Go`).
   - If $|\text{Required Skills}| = 0$, the job is flagged with `blocking_reason = no_required_skills` and candidates are held in `awaiting_requirements` until requirements are supplied.
2. **Title Sub-Score ($30\%$ weight):**
   - **Exact Match:** $100\%$ (e.g. `Backend Engineer` == `Backend Engineer`).
   - **Family Match:** $60\%$ (e.g. `Backend Developer` matches `Backend Engineer` within the `software_backend` title family).
   - **No Match:** $0\%$ (no related title held).
3. **Experience Sub-Score ($20\%$ weight):**
   - If candidate computed experience $\ge$ required minimum years: $100\%$.
   - If candidate experience $<$ required minimum years:
     $$\text{Experience Score} = \left(\frac{\text{Candidate Years}}{\text{Required Years}}\right) \times 100$$
   - If candidate experience basis is `unknown`: defaults to $50\%$.

### Worked Example Verification (SC2)

The system includes a pinned ground-truth worked example (`worked_example_native.pdf` evaluated against `backend_engineer_jd.pdf`):
- **Required Skills:** `python`, `aws`, `dynamodb`
- **Candidate Extracted Skills:** `python`, `aws`, `sql`, `rest api` (Matched: `python`, `aws`; Missing: `dynamodb`)
- **Required Minimum Experience:** $3.0$ years | Candidate Experience: $4.0$ years
- **Required Title:** `Backend Engineer` | Candidate Held Title: `Backend Developer` (Title Family match)
- **Sub-Scores:**
  - Skills: $\frac{2}{3} \times 100 = 66.67 \approx 66.7$
  - Title: $60.0$ (Title family match)
  - Experience: $\min(1.0, \frac{4.0}{3.0}) \times 100 = 100.0$
- **Total Composite Score:**
  $$(0.50 \times 66.67) + (0.30 \times 60.0) + (0.20 \times 100.0) = 33.33 + 18.0 + 20.0 = \mathbf{71.3}$$
- **Verification Status:** Verified live in AWS `dev` environment returning exactly `71.3`.

---

## 2. Extraction & NLP Pipeline Architecture (§2)

The Resume Screener data plane is 100% open-source, cost-optimized, and free of proprietary AI service lock-in.

```
[Candidate / Recruiter]
       │ (Direct S3 Presigned POST)
       ▼
 [S3 Upload Bucket]
       │
       │ (S3 ObjectCreated Event)
       ▼
[Ingestion SQS Queue] ──(Dead-Letter)──> [Ingestion DLQ]
       │
       ▼
[Extraction Lambda] (Container / PyPDF2 / pdfplumber / python-docx / Tesseract)
       │
       │ (Synchronous Lambda:Invoke)
       ▼
  [NLP Lambda] (Container / spaCy en_core_web_sm / PhraseMatcher)
       │
       ▼
[DynamoDB Candidates Table]
       │
       ▼ (Fanout on parsed state)
[Scoring SQS Queue] ──(Dead-Letter)──> [Scoring DLQ]
       │
       ▼
[ScoreMatch Lambda]
       │
       ▼
[DynamoDB Candidates Table (score_status=scored, match_score)]
```

### Key Architectural Decisions:
1. **Zero Textract / Zero Comprehend Dependency:**
   - Text extraction is executed in Lambda container images using open-source libraries (`PyPDF2`, `pdfplumber`, `python-docx`) with `tesseract-ocr` for scanned images.
   - Entity recognition and matching use `spaCy en_core_web_sm` with curated phrase matchers.
   - Eliminates per-page Textract costs ($1.50/1k pages) and per-unit Comprehend fees ($0.0001/unit), keeping infrastructure completely within AWS free-tier and low-cost serverless allocations.
2. **Method-Honesty Separation (R-HON-06):**
   - **Name:** spaCy Statistical Named Entity Recognition (`PERSON` entity label).
   - **Skills:** spaCy Tokenizer + `PhraseMatcher` over normalized dictionary taxonomy.
   - **Titles:** spaCy Tokenizer + `PhraseMatcher` over job titles dictionary.
   - **Experience:** Deterministic employment interval parser with date arithmetic, header detection, and overlap deduplication.
   - **Email:** Deterministic RFC-compliant regex.
3. **Resilience & Idempotency:**
   - SQS queues backed by Dead Letter Queues (DLQ) with exponential backoff and maximum receive count limits.
   - Idempotent event processing via conditional DynamoDB updates; duplicate delivery does not trigger duplicate candidate notifications.

---

## 3. Future Enhancements Roadmap (§3)

The following three roadmap capabilities are designed for subsequent releases:

### F1: Custom Fine-Tuned NER for Domain Entities
- **Current Limitation:** Off-the-shelf `en_core_web_sm` can struggle on international name ordering or stylized resumes without explicit labels.
- **Future Enhancement:** Train a custom spaCy / RoBERTa token-classification model fine-tuned on resume corpora (annotated with BIO tags for `CANDIDATE_NAME`, `DEGREE`, `INSTITUTION`, `CLEARANCE_LEVEL`).

### F2: Cover-Letter Sentiment & Tone Analysis
- **Current Limitation:** The scoring engine only processes objective skills and work histories.
- **Future Enhancement:** Implement an asynchronous sentiment and intentionality analysis pipeline for optional cover letters to gauge candidate enthusiasm, professional tone, and company alignment, providing recruiter insights without biasing quantitative match scores.

### F3: Blind Screening & Demographic Parity Dashboard
- **Current Limitation:** Recruiters currently view names and contact information during candidate review.
- **Future Enhancement:**
  - Anonymized Review Mode: Automatically redact candidate names, emails, phone numbers, and educational institution names until initial shortlist decisions are recorded.
  - Demographic Parity Analytics: Track selection ratios across anonymized demographic indicators to guarantee EEOC / OFCCP compliance and flag algorithmic scoring bias.

---

## 4. Licenses, Dependencies & Operational Limitations (§4)

### Third-Party Licenses
- **spaCy & en_core_web_sm:** MIT License (Commercial and private use permitted).
- **Tesseract OCR:** Apache License 2.0 (Permissive open-source license).
- **pdfplumber / pdfminer.six:** MIT License.
- **PyPDF2 / pypdf:** BSD-3-Clause License.
- **python-docx:** MIT License.
- **PyMuPDF Consideration:** The project explicitly uses BSD/MIT-licensed `PyPDF2` and `pdfplumber` rather than `PyMuPDF` (`fitz`), avoiding AGPL-3.0 copyleft viral licensing constraints.

### System Limitations & Boundaries
1. **Document Size Limits:** Maximum upload file size is capped at 10 MB per document; resumes exceeding 10 pages are rejected with `error_code = too_many_pages`.
2. **Supported Formats:** Native PDF, Scanned PDF, Single-page PNG images, and Microsoft Word (`.docx`). Text files renamed with `.pdf` extensions are cleanly detected via magic byte inspection and rejected (`unsupported_format`).
3. **Language Scope:** The current dictionary and NER models are optimized for English-language resumes. Multilingual extraction requires additional language packs.
