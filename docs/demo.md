# Resume Screener — Live Demonstration Script (12 Minutes)

> Phase 5 §10 (T-112) Comprehensive Live System Demo Guide  
> Environment: `dev` (`https://d1yg427uu45noj.cloudfront.net`)  
> Target Duration: ~12 minutes

---

## Pre-Demo Preparation & Fallback Assets

### Prerequisites:
1. Recruiter user account (`recruiter.a@example.com`) provisioned and verified in Cognito.
2. Admin user account (`admin@example.com`) provisioned and verified.
3. Test fixture files prepared in `tests/fixtures/resumes/` and `tests/fixtures/jds/`.
4. CloudFront distribution active (`https://d1yg427uu45noj.cloudfront.net`).

### Backup & Failover Plan:
- **Pre-Populated Backup Job:** If network connectivity fails, navigate directly to existing pre-scored job (`job_1e554452327a4ee7869e743120e06143`).
- **Offline Visual Assets:** Backup screenshots and UI recordings available under `docs/evidence/` and IDE brain artifacts (`func_verify_*.png`).

---

## 12-Minute Demo Narrative Timeline

### Minute 0:00 – 1:00 | Step 1: Context & Problem Statement
- **Narrative:** "Recruiting teams receive hundreds of resumes per job posting. Traditional keyword search misses synonyms, while proprietary AI APIs like Textract and Comprehend cost thousands of dollars and create vendor lock-in. Resume Screener is a 100% open-source, serverless screening platform on AWS that delivers explainable match scoring in under 40 seconds."
- **Action:** Open application landing page (`/login`) in browser. Highlight clean modern layout and dark mode styling.

### Minute 1:00 – 2:00 | Step 2 & 3: Create Job & Upload Job Description
- **Narrative:** "Let's create a new job posting for a Senior Backend Engineer."
- **Action:**
  1. Log in as `recruiter.a@example.com`.
  2. Click **+ New Job**.
  3. Enter Job Title: `Senior Backend Engineer (Production)`.
  4. Drag and drop `tests/fixtures/jds/backend_engineer_jd.pdf` into the JD dropzone.
  5. Set shortlist threshold slider to `70%`.

### Minute 2:00 – 3:30 | Step 4: Multi-Format Resume Upload
- **Narrative:** "Candidates submit resumes in various formats. We will upload 5 heterogeneous files simultaneously:"
  - Native PDF (`alice_johnson_native.pdf`)
  - Scanned PDF (`daniel_kim_scanned.pdf`)
  - Word Document (`bob_kumar.docx`)
  - Image (`jordan_rivera.png`)
  - Unsupported renamed text file (`renamed_text_file.pdf`)
- **Action:** Drag all 5 files into the resume dropzone and click **Create Job & Upload**.
- **Observation:** Presigned POST URLs generated; direct-to-S3 uploads complete with visible progress bars.

### Minute 3:30 – 4:30 | Step 5: Live Ingestion & Extraction
- **Narrative:** "Documents are ingested asynchronously via SQS. Native PDFs use PyPDF2; scanned PDFs invoke Tesseract OCR; DOCX files are parsed via python-docx. NLP Lambda extracts skills and titles via spaCy."
- **Action:** View the Job Detail page. Note candidate row badges transition from `uploading` $\to$ `processing` $\to$ `scoring` $\to$ `scored`.
- **Observation:** `renamed_text_file.pdf` immediately transitions to `error` with copy *"Unsupported file format"*.

### Minute 4:30 – 5:30 | Step 6: Transparent Explainability
- **Narrative:** "Every score is fully explainable. No black-box AI."
- **Action:** Click on `Alice Johnson` to open the Candidate Details Drawer.
- **Observation:** Point out the 3 sub-scores:
  - Skills ($50\%$ weight): matched vs missing skills clearly tagged.
  - Title ($30\%$ weight): exact match badge.
  - Experience ($20\%$ weight): computed employment duration.
  - Overall Composite Score: calculated using `scoring_version = v1`.

### Minute 5:30 – 7:00 | Step 7, 8, 9 & 10: Human Decision & Notification Idempotency
- **Narrative:** "Recruiters maintain complete human-in-the-loop control. Notifications are guaranteed at-most-once."
- **Action:**
  1. Click **Shortlist** on Alice Johnson. Status updates to `Shortlisted`; notification status updates to `sent`.
  2. Click **Reject** on Alice Johnson. Status updates to `Rejected`.
  3. Click **Shortlist** again on Alice Johnson.
- **Observation:** Point out that `notification_status` remains `sent` and `notification_sent_at` timestamp is untouched. The backend suppresses duplicate emails, preventing candidate inbox spam.

### Minute 7:00 – 8:00 | Step 11 & 12: Dynamic Requirements Editing & Rescore
- **Narrative:** "What if the hiring manager adds a new mandatory requirement?"
- **Action:**
  1. Click **Edit Requirements** to open the Requirements Drawer.
  2. Add `Docker` to Required Skills.
  3. Click **Save & Rescore**.
- **Observation:** Candidates re-evaluate instantly via SQS rescore fanout; scores adjust dynamically based on the updated criteria.

### Minute 8:00 – 8:45 | Step 13: CSV Export & Security Hardening
- **Narrative:** "Recruiters can export candidate shortlists to spreadsheet tools with built-in formula injection protection."
- **Action:** Click **Export Shortlist CSV**. Open the downloaded CSV file.
- **Observation:** Point out UTF-8 BOM encoding, standard columns, and single-quote escaping for formula injection characters (`=`, `+`, `-`, `@`).

### Minute 8:45 – 9:30 | Step 14: Operational Resilience & Admin Monitoring
- **Narrative:** "Administrators have full visibility into system failures and Dead Letter Queues."
- **Action:**
  1. Log out and log in as `admin@example.com`.
  2. Navigate to `/failed-jobs`.
- **Observation:** Demonstrate terminal error tracking, diagnostic error codes (`unsupported_format`, `processing_failed`), and retry capabilities.

### Minute 9:30 – 10:30 | Step 15: Evaluation Metrics & Quality Proof
- **Narrative:** "The system is continuously verified against a ground-truth benchmark."
- **Action:** Present `docs/evaluation.md` results:
  - **Skill Precision:** **0.910** ($\ge 0.80$ target)
  - **Skill Recall:** **1.000** ($\ge 0.70$ target)
  - **Name Accuracy:** **10/10 (100%)** ($\ge 8/10$ target)
  - **Experience Accuracy:** **9/9 (100%)** ($\ge 7/9$ target)
  - **Title Hit Rate:** **10/10 (100%)**

### Minute 10:30 – 11:15 | Step 16: System Limitations
- **Discussion Points:**
  - 10-page document limit (resumes $>10$ pages rejected as `too_many_pages`).
  - English language dictionary optimization.
  - PyMuPDF AGPL license avoided in favor of BSD/MIT libraries.

### Minute 11:15 – 12:00 | Step 17 & 18: Roadmap & Future Architecture
- **Discussion Points:**
  - F1: Custom fine-tuned Named Entity Recognition models.
  - F2: Cover-letter sentiment analysis.
  - F3: Blind screening & demographic parity audit dashboard.
  - Migration path to multi-region active-active deployment.
