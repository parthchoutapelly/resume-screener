# Design — Recruiter Dashboard Experience & Frontend Structure

> How the product is experienced and how the frontend is built. The data it shows is defined in `Architecture.md` §5–7, and the behaviour it must respect in `Rules.md`. This supersedes the page descriptions in `04-frontend-dashboard.md` §5–6. The stack is unchanged (React + Vite + Amplify Auth); hosting changes to CloudFront (D-22).

---

## 1. UX Principles

1. **Show the why.** Every score opens into its evidence: matched and missing skills, the title comparison, and the experience basis. A bare number is never the final UI.
2. **Nothing spins forever.** Every row always shows a named state. Spinners appear only for states that are actually in progress (`processing`, `scoring`), and time-based states (`upload_missing`, `stalled`) take over when progress stops.
3. **Recommend, don't decide.** "Recommended" is a quiet badge. Only the recruiter's Shortlist and Reject buttons carry weight, and only Shortlist reaches the candidate. That one irreversible action (an email) gets a confirmation; everything else is one click and reversible.
4. **Honest labels.** Copy never says "AI detected" for deterministic fields. The breakdown says "Skills matched from our skills dictionary", and experience is labelled "calculated from dates" or "estimated".
5. **Fail loudly, specifically, and recoverably.** Errors name the file, give the reason in plain language, and offer the next action (re-upload, edit requirements).
6. **Boring and fast.** This is a table-and-form tool. Density beats decoration, and keyboard use should be first-class.

## 2. Information Architecture

```
/login
/jobs                         Job list + "New job" button
/jobs/new                     Create job + upload
/jobs/:jobId                  Job detail: header, requirements panel, candidate table
/admin/failures               Admin only (nav link hidden for others)
*                             Not found
```
Every route except `/login` sits behind `ProtectedRoute`; `/admin/*` also sits behind `AdminRoute`. After login, the user lands on `/jobs` (or the originally requested URL).

## 3. Layout & Visual System

No component library is needed. Use plain CSS with custom properties in `src/styles/tokens.css`.

| Token | Value / guidance |
|---|---|
| Font | System UI stack; 14 px base for tables, 16 px for forms; tabular numerals for scores |
| Spacing | 4-px scale (4, 8, 12, 16, 24, 32) |
| Layout | Top bar (product name, Jobs, Failures [Admin], user menu) + content max-width 1280 px |
| Colour | Neutral greys + one accent (blue) for primary actions. Semantic colours: success (green) for Shortlisted, danger (red) for Error/Reject, warning (amber) for Stalled/Needs requirements, info (blue-grey) for Processing |
| Status never by colour alone | Every badge has text plus an icon (R-A11Y, §8) |
| Score display | Number to 1 dp, plus a thin 0–100 bar; a threshold tick on the bar in the expanded view |
| Dark mode | Not required |

## 4. Screens

### 4.1 Login
- Email + password; submit; inline error "Incorrect email or password" (Cognito's error is not echoed verbatim).
- `NEW_PASSWORD_REQUIRED` challenge (users are admin-created) → "Set a new password" step, showing the policy hints.
- No sign-up link, and no forgot-password flow in the MVP (Admins reset users). Recorded as a known limitation.

### 4.2 Job list (`/jobs`)
- Table: Title · JD status badge · Created · (Admin: Owner). Clicking a row opens the job detail.
- JD status badges: `Processing JD`, `Ready`, `Needs requirements`, `JD failed`, `No JD`.
- Empty state: "No job postings yet" + a primary "Create your first job" button.
- "Load more" when `next_token` is present.

### 4.3 Create job (`/jobs/new`)

A single form in three sections:

1. **Job** — Title (required).
2. **Requirements** — JD source radio: `Upload JD file` | `Paste JD text` | `No JD — I'll enter requirements`. Then the optional fields: Required skills (chip input; Enter/comma adds a chip; the helper text shows normalization, e.g. "js → javascript"), Required titles (chip input), Minimum years (number), Recommendation threshold (number, default 70, helper text "Candidates scoring at or above this are marked Recommended. It never sends email.").
3. **Resumes** — drop zone + file picker, multi-select. Each file row shows name, size, and a validation result. Unsupported type or >10 MiB is marked invalid inline with the reason, and invalid files are excluded from submission.

- Submit is disabled until the form is valid: title set; a JD file picked when the source is "file"; text present when "text"; ≥1 skill when "none". The total count must be ≤50.
- On submit → §5.1 upload flow. The page swaps to an **Upload progress** panel: per-file progress bar and status (`Queued`, `Uploading 43%`, `Uploaded`, `Failed — Retry`), and an overall "12 of 14 uploaded" count.
- When all uploads are done or failed, a "Go to job" button appears, and navigation happens automatically if there were no failures. Failed files remain retryable from the job detail page (they become `upload_missing` rows, and "Re-upload" issues new URLs via `POST /jobs/{id}/resumes`).
- A `beforeunload` warning is active while uploads are in flight.

### 4.4 Job detail (`/jobs/:jobId`)

**Header:** job title, created date, and actions: `Add resumes`, `Edit requirements`, `Export shortlist (n)` (disabled at 0 with a tooltip saying why).

**Job banner** (shown only when `blocking_reason` is set):
| blocking_reason | Banner (amber) | Action |
|---|---|---|
| `awaiting_jd` | "Reading the job description… candidates will be scored when it's done." | — |
| `jd_failed` | "We couldn't read the job description. Check the requirements below and confirm to start scoring." | `Review requirements` |
| `no_required_skills` | "No required skills were found. Add at least one skill to score candidates." | `Add skills` |

**Requirements panel** (collapsible, open by default when `blocking_reason` is set): effective skills, titles, and min years, each with a source tag (`From you` / `From JD`); the threshold. `Edit` opens the §4.6 drawer.

**Summary strip:** counts by display group: Scored · Recommended · Shortlisted · In progress · Needs attention (error + stalled + upload_missing). Clicking a count filters the table.

**Candidate table**
| Column | Content |
|---|---|
| Rank | 1..n for scored rows; blank otherwise |
| Candidate | Name (or "Name not found"), plus the filename in secondary text; email in secondary text |
| Score | Number + bar; `Recommended` badge if flagged; or the status cell (§6) for unscored rows |
| Skills | Up to 6 chips (matched skills first, highlighted; then other skills), "+n more" |
| Experience | `4.0 yrs` · `≈ 3.5 yrs` (estimated, with a tooltip) · `Unknown` |
| Latest titles | First 2 of `titles_held` |
| Decision | Segmented control `Shortlist` / `Reject`; the selected state is shown; clicking the selected one returns to `pending` |
| ▸ | Expand toggle |

- Rows come pre-sorted from the API. Client-side controls: filter by status group, text search on name/skill, and re-sort by Score / Experience / Name. The default is the API order.
- **Expanded row (score breakdown):** three sub-score bars with weights shown ("Skills 66.7 × 50% = 33.4"); matched skills (green chips) and missing skills (outlined chips); title match line ("Backend Developer ~ Backend Engineer — related role, 60"); experience basis ("Calculated from 2 date ranges" / "Estimated — dates were ambiguous" / "No dates found"); extraction info (`Native PDF`, `Scanned PDF — OCR on 2 pages`, `DOCX`, `Image — OCR`); an `Open original resume` link if FR22 is enabled; employers list.
- Pagination is not needed (≤200 rows). The table header is sticky.

### 4.5 Admin failures (`/admin/failures`)
- Filter: job ID (text or pick from the job list), plus "Terminal only" and "Include retried attempts" toggles.
- Table: Time · Job · Candidate · Stage (badge) · Terminal? · Attempt · Message (truncated, expandable) · `raw_payload` (expandable, monospace, copy button).
- Stage legend (static, collapsible): one line per stage, from `Architecture.md` §7.4.
- Explanatory copy: "Retried attempts that later succeeded also appear here. This is an audit log, not the current status."

### 4.6 Edit requirements (drawer)
- The same chip inputs as creation, pre-filled with the **effective** values, and each field shows its source. Threshold is included.
- Save → `PATCH /jobs/{id}` → toast "Requirements saved. Re-scoring n candidates…" → the table polls. Decisions visibly stay as they were (the drawer notes "Your shortlist/reject decisions won't change.").

### 4.7 Add resumes (modal)
The same drop zone and progress panel as §4.3, calling `POST /jobs/{id}/resumes`. Rows in `upload_missing`/`error` show "Re-upload", which opens this modal limited to one file.

## 5. Key Flows & Interaction Behaviour

### 5.1 Upload
```
validate locally → POST /jobs (or /resumes)
→ for each file (pool of 4): FormData(fields… , file) → POST to url
     success (204) → Uploaded
     network error → retry automatically once, then Failed (manual retry within URL expiry)
     URL expired (403 from S3) → Failed — "Link expired, use Re-upload on the job page"
```
File bytes never go through `api/client.js` (`04-frontend-dashboard.md` §4 intent kept, method changed from PUT to POST).

### 5.2 Live status (D-44)
- Poll `GET /jobs/{id}/candidates` (and `GET /jobs/{id}` while `blocking_reason = awaiting_jd`) **every 5 s** while any row is in `processing | scoring | awaiting_jd`.
- Stop polling when all rows are in any other state, when the tab is hidden (resume on `visibilitychange`), or after 30 min (show "Auto-refresh paused — Refresh").
- Back off to 15 s after 3 consecutive errors, and show a subtle "Having trouble refreshing" note. Never blank the table because a poll failed.
- Merge updates by `candidate_id`. Keep the expanded rows and scroll position. Don't re-sort while the pointer is over the table (defer until it leaves), so rows don't jump under the cursor.

### 5.3 Decisions
- **Reject:** optimistic update → `POST decision` → on error, roll back and show a toast with the reason (e.g. 409 "This candidate isn't scored yet").
- **Shortlist:** a confirmation dialog: "Shortlist Jane Doe? We'll email **jane.doe@example.com** once to let them know. This can't be unsent." If no email was found: "No email address was found in this resume, so no email will be sent." If already `sent`: no dialog (no email will be sent; decision only). Buttons: `Shortlist and email` / `Cancel`.
- After the response, show a notification chip on the row: `Email sent` · `No email found` · `Email failed — shortlist again to retry` · `Email status unknown`.
- Decision controls are disabled with a tooltip on unscored rows.

### 5.4 Export
Click → `GET /jobs/{id}/export` → navigate to `download_url` (browser download) → toast "Exported n candidates". At 0, the button is disabled.

### 5.5 Auth/session
- Tokens are refreshed by Amplify. A 401 from the API triggers one silent refresh and a retry, then redirects to `/login?next=…` with the message "Your session expired."
- A 403 on an Admin route shows a "You don't have access" page; the Admin nav link is hidden unless `groups` includes `Admin`.
- A user with no group sees a full-page "Your account isn't set up yet — contact an administrator", instead of an app full of 403s.
- A 404 on a job shows "Job not found": the same page whether the job doesn't exist or isn't the user's.

## 6. Candidate Status → UI Mapping

| display_status | Score cell | Icon | Colour | Row actions |
|---|---|---|---|---|
| `scored` | score + bar (+ Recommended) | — | neutral | Decide, expand |
| `scoring` | "Scoring…" | spinner | info | expand (partial data) |
| `awaiting_jd` | "Waiting for job description" | clock | info | expand |
| `awaiting_requirements` | "Needs job requirements" | warning | warning | link to banner action |
| `processing` | "Processing…" | spinner | info | — |
| `upload_missing` | "Upload not received" | cloud-off | warning | Re-upload |
| `stalled` | "Taking longer than expected" | warning | warning | Re-upload; (Admin) view failures |
| `error` | Reason text by `error_code` (below) | error | danger | Re-upload; (Admin) view failures |

| error_code | Recruiter-facing text |
|---|---|
| `unsupported_format` | "File type isn't supported. Use PDF, DOCX, PNG, JPG or TIFF." |
| `file_too_large` | "File is larger than 10 MB." |
| `too_many_pages` | "Resume is longer than 10 pages." |
| `unreadable_document` | "We couldn't read any text from this file. It may be blank, password-protected, or too low quality." |
| `processing_failed` | "Something went wrong while processing this file. Try re-uploading." |
| `scoring_failed` | "Scoring failed. An administrator has been alerted." |

Email greeting rule: "Hi {name}," only if `name` is present, otherwise "Hello,". The subject is "You've been shortlisted — {job_title}".

## 7. Component Structure

```
src/
├── main.jsx, App.jsx                 # router, providers
├── config.js                         # reads import.meta.env; fails fast if missing
├── auth/  AuthContext.jsx  ProtectedRoute.jsx  AdminRoute.jsx
├── api/   client.js (JSON, auth header, 401 refresh-retry, error envelope → ApiError)
│          upload.js (presigned POST, pool of 4, progress via XHR)
├── hooks/ usePolling.js  useJob.js  useCandidates.js  useUploadQueue.js
├── domain/ status.js (display_status → label/icon/tone; error_code → copy)
│           format.js (score 1 dp, years, dates)
├── pages/ LoginPage  JobListPage  CreateJobPage  JobDetailPage  FailedJobsPage  NotFoundPage  NoAccessPage
├── components/
│   ├── layout/   TopBar  PageHeader  Banner  Toast(Provider)  ConfirmDialog  Drawer  Modal
│   ├── form/     ChipInput  NumberField  FileDropZone  FileRow  Field (label+help+error)
│   ├── job/      RequirementsPanel  RequirementsEditor  SummaryStrip  JobStatusBadge
│   ├── candidate/ CandidateTable  CandidateRow  ScoreCell  ScoreBreakdown  SkillTagList
│   │              ExperienceCell  DecisionControl  NotificationChip  StatusCell
│   ├── upload/   UploadProgressPanel  AddResumesModal
│   └── admin/    FailuresTable  StageLegend
└── styles/ tokens.css  base.css  components.css
```

- State: React state + context only (auth, toasts). There is no Redux or query library, since the data surface is six endpoints. `usePolling` owns the timers.
- Upload progress needs `XMLHttpRequest` (`fetch` has no upload progress). This is isolated in `upload.js`.
- `domain/status.js` is the only place the UI maps statuses to copy. It mirrors `Architecture.md` §7.2/7.4, and a unit test asserts every enum value is mapped.

## 8. Accessibility (WCAG 2.1 AA)

- Semantic HTML: a real `<table>` with `<th scope>`; the expand toggle is a `<button aria-expanded aria-controls>`; the decision control is a `role="radiogroup"` with labelled options.
- Every form field has a `<label>`; errors are linked with `aria-describedby`; errors are summarized at the top of the form on submit, with focus moved there.
- Status changes from polling are announced through **one** polite live region, with batch summaries ("3 candidates scored") rather than one announcement per row.
- Toasts use `role="status"`; confirmation dialogs trap focus, close on Esc, and return focus to the trigger.
- Contrast ≥ 4.5:1 for text and ≥ 3:1 for bars and badges; status is never conveyed by colour alone.
- Everything is keyboard-reachable; focus rings are visible; the drop zone also works as a regular file input.
- Spinners respect `prefers-reduced-motion`.
- Score bars carry `aria-label="Match score 71.3 out of 100"`.

## 9. Feedback & Copy Guidelines

- Use sentence case and plain words; don't blame the user; say what happened and what to do next.
- Use the vocabulary consistently: **Recommended** (system), **Shortlisted/Rejected** (recruiter), **Processing / Scoring** (system in progress).
- Never mention internal stages, queue names, or AWS services to Recruiters. Admin screens may.
- Numbers: scores to 1 dp; years to 1 dp with the "yrs" suffix; dates in the user's locale with relative time for < 24 h ("5 min ago").
