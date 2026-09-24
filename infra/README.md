# Infrastructure — Prerequisites, Platform Validation, Manual Steps, Runbook

Companion to `docs/01-infrastructure-setup.md`. This file is the living record of what was
actually checked/decided when phase 1 was run, per that doc's Definition of Done.

## Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| AWS CLI | 2.36.34 | `aws sts get-caller-identity` must resolve before anything else |
| SAM CLI | 1.165.0 | |
| Docker (or Finch) | via Colima 0.10.3 + QEMU (not Docker Desktop) | See "Docker on this machine" below |
| Python | 3.12.0 (`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`) | For `make venv` — the system default `python3` on this Mac is 3.14, which is NOT what Lambda runs |
| Node | 22.23.2 | Phase 4 (frontend) |

### Docker on this machine (Apple Silicon, no admin password available to the agent)

Docker Desktop's Homebrew cask requires an interactive `sudo` prompt (to symlink
`docker-credential-osxkeychain`) that a non-interactive session cannot supply. Installed
**Colima** instead — a lightweight Docker daemon in a Lima VM, entirely in user space, no
sudo required for any of its formulae:

```bash
brew install colima docker docker-buildx qemu lima-additional-guestagents
mkdir -p ~/.docker && cat > ~/.docker/config.json <<'EOF'
{ "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"] }
EOF
colima start --cpu 2 --memory 4 --arch x86_64
```

`--arch x86_64` matters: it makes the **entire VM** x86_64 via QEMU emulation, so every
image built inside it is genuinely `linux/amd64` — no per-build `--platform` flag needed,
and it matches D-33 (x86_64 everywhere) exactly. `lima-additional-guestagents` is required
for a foreign-architecture (x86_64-on-arm64) VM to boot at all; without it, `colima start`
fails with "guest agent binary could not be found for Linux-x86_64".

**SAM needs `DOCKER_HOST` set explicitly** — it doesn't read the active `docker context`:
```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
sam build --use-container
```
Put that export in your shell profile, or prefix every `sam build`/`docker` command with it.

Colima persists across reboots only if started again (`colima start`); check with `colima status`.

**Expected, benign warning:** `sam build --use-container` prints "Cross-architecture
build detected: Building x86_64 function '...' on arm64 host" for every function.
This is SAM checking the *host* CPU, not whether emulation is available — since
Colima's VM itself is x86_64 (QEMU), the build happens fully natively from
Docker's point of view inside the VM. Safe to ignore.

**Transient error to retry, not debug:** occasionally a build fails with
`Error: lease does not exist: not found` (a buildkit/containerd race, especially
if a `docker image prune` or another build ran concurrently). Just re-run
`sam build --use-container` — it isn't a real problem with the template or
Dockerfile.

## Platform validation (T-001–T-006)

Run 2026-09-23 against AWS account `331262815638`, region `ap-south-1`.

| # | Check | Result |
|---|---|---|
| T-001a | Comprehend (`detect-entities`) | **`SubscriptionRequiredException`** — confirms the account cannot call it. D-02 holds. |
| T-001b | Textract (`get-document-text-detection`) | **`SubscriptionRequiredException`** — same conclusion. |
| T-001c | CloudFront | `list-distributions` (read) succeeds — but **creating** one is blocked, see "CloudFront deferred" below. The read-only check in this row was not sufficient to catch that; a create/delete probe (as was done for the other services) would have. |
| T-001d | SES | Enabled; sandbox mode (0 verified identities initially) |
| T-001e | ECR | Accessible (`describe-repositories` succeeds, 0 existing) |
| T-001f | Cognito IdP | Accessible (other projects' pools visible) |
| T-001g | Budgets | Accessible — **an account-wide budget already exists** (`DocVault-Cost-Alert`, $5/mo, from another project). Decision: `CreateBudget=false` for resume-screener; rely on the existing alert. |
| T-002 | Build toolchain (zip + image function via `sam build --use-container`) | **Pass** (after switching from Docker Desktop to Colima, see above) |
| T-003 | Tesseract on the Lambda Python 3.12 base image (AL2023, `dnf`/`microdnf`) | See "D-34 outcome" below |
| T-004 | SES sender verification | **Verified** — `parth.choutapelly@gmail.com`, `VerificationStatus: Success` |
| T-005 | Lambda concurrent-execution quota | **10** (account default, ap-south-1) — matches the `MaximumConcurrency: 3/2` design (D-25) with headroom for the API and other projects' functions sharing the same quota |
| T-006 | NLP layer size (spaCy 3.8 + `en_core_web_sm` 3.8.0) | **INVALIDATED, then corrected during phase 2 deploy.** Original spike measured 137 MB via a plain `pip install --target` on macOS arm64, with no `--platform`/`--only-binary` constraints — that silently resolved different (smaller, non-Linux) wheels than the real build. The actual `sam build --use-container` output (matching `--platform manylinux2014_x86_64 --only-binary=:all:`, what SAM's makefile build method actually runs) measured **310 MB** — over the 250 MB function+layers combined limit, and the deploy failed with exactly that error. **Result: NlpFunction switched to a container image (D-56)**, the pre-agreed D-03 fallback. Lesson for future spikes: reproduce the exact build command, don't approximate it locally. |

### D-34 outcome: extraction base image

**Candidate A (`public.ecr.aws/lambda/python:3.12`, `dnf`/`microdnf`) — FAILED.**
Tested directly (not just build-time): `microdnf install -y tesseract` resolves
metadata (fast, <1s) then reports `error: No package matches 'tesseract'` after
~2m21s of real work (1m53s user CPU — genuinely resolving, not hung; just slow
under x86_64 QEMU emulation). The AL2023 minimal repo configured in this base
image simply does not carry a `tesseract` package. This was flagged as
"unverified" risk in the original doc; now confirmed negative.

**Candidate B (`python:3.12-slim-bookworm` + `apt-get tesseract-ocr` +
`awslambdaric`) — PASSED.** `apt-get install tesseract-ocr tesseract-ocr-eng`
installs cleanly (Tesseract 5.3.0, ~30 MB of packages, ~49s build time under
x86_64 emulation). Functional test: invoked the handler directly inside the
built image against a real fixture image (`tests/fixtures/resumes/jordan_rivera.png`)
and got back genuine OCR'd text — all 139 characters recovered correctly,
including the name, email, and skill list — proving this is real Tesseract
output, not a stub.

**Addendum (phase 2 build):** `python:3.12-slim-bookworm` does not bundle
`boto3`/`botocore` the way the official AWS Lambda base images do — `boto3`
had to be added explicitly to `backend/ingestion/extraction/requirements.txt`.
Easy to miss, since every other function (zip-packaged, on the AWS Lambda
Python runtime) gets boto3 for free.

**Decision (D-34): `backend/ingestion/extraction/Dockerfile` uses Candidate B.**
This also means the extraction function does **not** use the official
`public.ecr.aws/lambda/python` base image; it uses `python:3.12-slim-bookworm`
+ the `awslambdaric` runtime interface client, which is AWS's documented
pattern for building Lambda container images from non-AWS base images. A
consequence: the image doesn't include the Lambda Runtime Interface Emulator
(RIE), so it can't be invoked with a bare `docker run -p 9000:8080` locally —
`sam local invoke` handles this correctly on its own (SAM provides its own
local invoke mechanism for image functions), which is how local testing is
actually done from phase 2 onward.

### Existing colliding resources — cleaned up before deploying

An earlier, abandoned iteration of this project had already deployed a stack literally named
`resume-screener-dev` in this same account, built around calling Textract/Comprehend directly
(which, per T-001a/b above, cannot work on this account — presumably why it was abandoned).
It owned the exact resource names this phase's `template.yaml` needs (bucket, 4 tables, 4
queues, Cognito pool, `AlertsTopic-dev`). Before deploying:

1. Verified its S3 bucket held only synthetic test fixtures (repeated fake names — Bob Kumar,
   Alice Johnson, Carol Singh — across several jobs), no real candidate data.
2. `aws s3 rm s3://resume-screener-dev-331262815638/ --recursive`
3. `aws cloudformation delete-stack --stack-name resume-screener-dev` (confirmed deleted).

If you ever see `AlreadyExists`/`already in use` on a fresh deploy, check for stray leftovers
the same way before assuming the template is wrong.

## CloudFront deferred

The first full deploy attempt failed: CloudFormation rolled back the **entire**
stack (DynamoDB, SQS, Cognito, all 14 functions — none of which had anything
wrong with them) because `WebDistribution` came back:

> Access denied for operation 'AWS::CloudFront::Distribution: Your account
> must be verified before you can add new CloudFront resources. To verify
> your account, please contact AWS Support ...' (Service: CloudFront, Status
> Code: 403, HandlerErrorCode: AccessDenied)

This is a new/lightly-used-account anti-abuse gate, unrelated to IAM
permissions (`docvault-antigravity` has `AdministratorAccess`). This account
has **Basic support only**, so `aws support create-case` isn't available
(`SubscriptionRequiredException`) — the verification request has to be filed
through the AWS Console (Support Center → Create case → Account and billing →
mention wanting to create a CloudFront distribution).

**Decision (with the project owner):** deploy the backend now; defer
CloudFront/web hosting. `WebBucket`, `WebOAC`, `WebHeadersPolicy`,
`WebDistribution`, `WebBucketPolicy` are pulled out of `template.yaml` into
`template-web-hosting.yaml.deferred` (that file has the exact restore steps).
`UploadBucket`'s CORS temporarily allows only `http://localhost:5173`
(unconditionally, not `!If [IsDev, ...]`) until the CloudFront origin exists
again. This doesn't block anything: CloudFront/the frontend isn't needed
until phase 4 (`docs/04-frontend-dashboard.md`), by which point the
verification will very likely have gone through.

**To restore once verified:** follow the numbered steps at the top of
`template-web-hosting.yaml.deferred`, then `sam build --use-container && sam deploy --config-env dev`.

**This is exactly the fallback `docs/PRD.md` §11 assumption A1 anticipated**
("If wrong: Replace CloudFront with Amplify Hosting or local-only frontend
demo") — worth reconsidering Amplify Hosting only if the verification request
turns out to be slow, since Amplify Hosting also provisions a CloudFront
distribution under the hood and may hit the identical gate.

## Deploy user

**Deviates from `docs/01-infrastructure-setup.md` §6**: rather than creating a new dedicated
IAM user, this project deploys as the account's existing `docvault-antigravity` IAM user, which
already carries `AdministratorAccess` (shared across this account's other projects —
`docvault`, `onboarding-service`, `employee-document-vault`). Decision made explicitly with the
project owner rather than following the doc's "isolated deploy user" recommendation, since this
is a personal/shared dev account, not a team-shared one. `docvault-antigravity` therefore has
more than the §6 permission table's scope; the table remains useful as a reference for what
this project *actually* touches, e.g. when reasoning about blast radius.

Never grant `docvault-antigravity` (or any deploy identity) runtime `lambda:InvokeFunction` at
the account level — that permission belongs only inside individual Lambda execution roles
(e.g. `ExtractionFunction`'s role invoking `NlpFunction`, added in phase 2).

## Manual one-time steps

1. **Deploy the stack**: `make build && make deploy ENV=dev` (or `sam build --use-container && sam deploy --config-env dev`).
2. **Seed config**: `make seed ENV=dev`.
3. **Verify SES sender**: already triggered for the sender in `samconfig.toml`
   (`SesSenderAddress`) — click the link AWS emails to that address. Recheck with:
   ```bash
   aws ses get-identity-verification-attributes --region ap-south-1 --identities <address>
   ```
4. **Create Cognito test users** (needed for phase 3+ testing — two Recruiters, one Admin, one
   groupless user):
   ```bash
   scripts/create-user.sh dev recruiter.a@example.com Recruiter
   scripts/create-user.sh dev recruiter.b@example.com Recruiter
   scripts/create-user.sh dev admin@example.com Admin
   scripts/create-user.sh dev noaccess@example.com none
   ```
   All four users sign in with the temporary password `TempPass1234` and are
   challenged to set a permanent one on first login (`NEW_PASSWORD_REQUIRED`).
5. **Frontend config** (phase 4): `scripts/gen-frontend-env.sh dev`.

## Phase 1 deployment result — 2026-09-23

`resume-screener-dev` reached `CREATE_COMPLETE` on the second attempt (first
attempt rolled back on the CloudFront gate above; the stack had to be
`delete-stack`'d before CloudFormation would accept a fresh create — a
`ROLLBACK_COMPLETE` stack can't be updated). Verified against every item in
`docs/01-infrastructure-setup.md` §7 Definition of Done (the two CloudFront-
specific boxes are N/A until CloudFront is restored):

- [x] `sam validate --lint` clean
- [x] `sam build --use-container && sam deploy --config-env dev` succeeds
- [x] `UploadBucket`: all 4 Block Public Access flags `true`; no website config (`NoSuchWebsiteConfiguration`)
- [ ] ~~CloudFront placeholder + HSTS/CSP headers~~ — N/A, deferred
- [x] `UploadBucket` CORS lists `http://localhost:5173` (temporary, see "CloudFront deferred")
- [x] 4 DynamoDB tables; `jobs-dev` has `RecruiterJobsIndex`; `candidates-dev` has **no** GSI; `failed_jobs-dev` TTL enabled on `expires_at`
- [x] Config row `nlp_engine_mode = spacy_hybrid` present (verified via `get-item`)
- [x] 4 SQS queues; redrive policies linked (maxReceiveCount 3 / 5); DLQ retention 1209600s (14d); ingestion/scoring queue retention 345600s (4d)
- [x] Cognito: `sign-up` via the CLI → `NotAuthorizedException` (self sign-up genuinely disabled); `Recruiter`/`Admin` groups exist; 2 Recruiters + 1 Admin + 1 groupless user created
- [x] `rs-extraction-dev` is Package type **Image**, architecture **x86_64**, State **Active**
- [x] All 14 functions live in `list-functions`; spot-checked both `rs-extraction-dev` (`sam local invoke`) and `rs-get-jobs-dev` (real `aws lambda invoke` against the deployed function) — both return the exact 501 envelope
- [x] Every log group has 30-day retention (spot-checked `rs-extraction-dev`'s)
- [x] SNS topic `rs-alerts-dev` exists; no budget created in this stack (`CreateBudget=false`, per the project owner — the account already has one from another project)
- [x] `grep -ri "textract\|comprehend" template.yaml backend/` → no matches
- [x] This file documents prerequisites, spike results, the deploy-user decision, and the user-creation script

**Not yet done (deliberately, not blocking):** CloudFront/`WebBucket` (deferred, see above) — no placeholder `index.html`, no HSTS/CSP check possible until restored.

## Phase 2 deployment result — 2026-09-24

`resume-screener-dev` reached `UPDATE_COMPLETE` after two real, non-trivial problems surfaced during the
actual build/deploy (not caught by review or unit/component tests, since both are infrastructure-level facts
no amount of mocked testing reveals):

1. **NlpLayer measured 310 MB unzipped for real** (built with `--platform manylinux2014_x86_64
   --only-binary=:all:`, exactly what the makefile build method runs), over Lambda's 250 MB function+layers
   limit. The earlier T-006 spike (137 MB) had silently used different, smaller wheels by skipping those
   platform flags. Fixed by switching `nlpProcessing` to a container image (D-56) — the pre-agreed D-03
   fallback. See "D-34 outcome" section above (its addendum) and `docs/Memory.md` D-56.
2. **CloudFormation refused to replace `NlpFunction` in place** when `PackageType` changed Zip → Image,
   because it has a fixed `FunctionName`: *"CloudFormation cannot update a stack when a custom-named resource
   requires replacing. Rename rs-nlp-dev and update the stack again."* Fixed with the two-deploy dance AWS's
   own error message describes: temporarily set `FunctionName: !Sub rs-nlp-tmp-${EnvName}`, deploy (creates
   the new Image-typed function under the temp name, deletes the old Zip one), then revert to
   `!Sub rs-nlp-${EnvName}` and deploy again (renames/replaces to the final name). Needed only for this one
   Zip→Image transition — an ordinary code change to the image doesn't hit this.
3. A **real code bug**, also only visible once actually deployed: `backend/ingestion/nlp/Dockerfile` copied
   `data/` from `layers/common_layer/data/`, which is an *empty placeholder directory* (that path is only
   ever populated as a build ARTIFACT by `CommonLayer`'s makefile build, for zip-packaged functions using the
   layer — it was never a real source tree). The image built successfully (Docker doesn't complain about
   copying an empty directory) but failed at runtime with `FileNotFoundError` on the first dictionary lookup.
   Fixed by copying from the real source, `data/` (i.e. `backend/data/`), directly. The empty placeholder
   directory was deleted.

Verified against `docs/02-ingestion-pipeline.md` §11 Definition of Done, with a real deployed end-to-end run
(`tests/integration/phase2_run.py dev`), not just mocks:

- [x] `rs_common` unit tests green; coverage 93% overall (ddb/errors 100%, normalization 98%, experience 90%,
      fanout 88%) — exceeds the "normalization, experience, ddb, errors ≥ 90%" requirement
- [x] `scripts/validate_data.py` passes: 318 skills, 170 titles, 22 title families (all exceed the minimums)
- [x] Layers build with `sam build --use-container`; `CommonLayer` deploys fine; `NlpLayer` **does not exist**
      (D-56) — `nlpProcessing`'s image measured 280 MB total, comfortably under the 10 GB **image** limit
      (a different, much larger ceiling than the 250 MB zip+layers limit that failed)
- [x] JD upload → `job_itest...` has `derived_skills=[aws, dynamodb, python]`, `parse_status=parsed`;
      explicit `required_*` untouched (none were set on this test job, correctly left absent)
- [x] Native PDF (×2), scanned PDF, mixed PDF, DOCX, and image resumes → all 6 populated from **their own
      text**: real names (Jane Doe, Alice Johnson, Daniel Kim, Maya Bennett, Bob Kumar, Jordan Rivera), real
      skills, correct `file_type` per case (`pdf_native`, `pdf_scanned`, `pdf_mixed`, `docx`, `image`)
- [x] `total_experience_years` confirmed as a real DynamoDB **Number** (`{"N": "5.7"}` in the console/CLI) on
      a real parsed candidate; confirmed **absent** (no attribute at all) on a terminal-error candidate
- [x] Each terminal case (corrupt, renamed-text, blank-scan, 11-page) produced exactly **one** `failed_jobs`
      row (`terminal=true`) with the correct `error_code`; `IngestionQueue`/`IngestionDLQ` both measured 0
      messages after the run — no redelivery for any of them
- [x] Resumes uploaded before their JD were correctly enqueued for scoring by the JD fan-out (all 6 reached
      `parsed` even though the JD finished parsing after some of them, by design — D-18)
- [x] `grep -rn "failed_jobs\|FAILED_JOBS" backend/ingestion/nlp/` → no matches (D-20 holds)
- [x] Log review: real CloudWatch logs for this run contain no candidate names or emails (`filter-log-events`
      for "Jane"/an email fragment → zero matches); structured JSON confirmed (`level`, `msg`, `timestamp`,
      `stage`, `job_id`, `candidate_id`, `doc_type`, `file_type`, `ocr_pages`)
- [x] Code review against §1: no filename branching, canned text, fabricated confidences; `grep -ri
      "textract\|comprehend"` matches only false positives (the substring inside "documentExtraction")

**Two genuine NLP-quality bugs found and fixed during component testing** (before deploying, via the real
`en_core_web_sm` model — not assumed, actually observed): `en_core_web_sm` sometimes merges a candidate's name
with an immediately adjacent unseparated line (e.g. an email right below it, no blank line) into one PERSON
span — `pick_name` now takes only the entity's first line and rejects spans containing `@`/digits. And the
original employer-exclusion check only matched an ORG's exact text against the skills dictionary, so "Docker
Inc" wasn't recognized as normalizing to the skill "docker" — it now also checks the text with common
corporate suffixes (Inc/LLC/Corp/...) stripped. Both are D-55 in `docs/Memory.md`. A pre-existing accuracy
limitation was also confirmed empirically (not assumed): `en_core_web_sm`'s ORG recognition is markedly
weaker on compact single-line "Company - Title - Date" resume bullets than on full prose sentences, and it
tags "Docker" as PERSON rather than ORG regardless of context — recorded in `docs/Memory.md` §9 as a target
for the flagship custom-NER enhancement (F1), not something the dictionary layer can paper over.

## Phase 3 deployment result — 2026-09-24

Deployed to `resume-screener-dev` (`UPDATE_COMPLETE`, first attempt — no CloudFormation
rollbacks this phase). Added: `RecruiterApi` (REST, Cognito authorizer, throttled 20/40),
`ScoreMatchFunction` (SQS, `MaximumConcurrency: 2`), the 10 API functions, `DlqHandlerFunction`
(both DLQs), 12 CloudWatch alarms → `AlertsTopic`, and the `ApiBaseUrl` output. Every function
has its own role with an inline policy scoped exactly as `docs/Architecture.md` §8.1
(verified on the live roles); the only `*` in a resource is the documented SES `identity/*`
(sandbox authorizes the *recipient* identity too) guarded by a `ses:FromAddress` condition.

**API base URL:** `aws cloudformation describe-stacks --stack-name resume-screener-dev --query "Stacks[0].Outputs[?OutputKey=='ApiBaseUrl'].OutputValue" --output text`

**CORS origin (D-57):** the stack parameter `AllowedOrigin` (default `http://localhost:5173`)
is the single allowed browser origin. When CloudFront is restored, deploy with
`AllowedOrigin=https://<distribution-domain>` (add it to `parameter_overrides` in
`samconfig.toml`) — never `*`.

### Verification (`tests/integration/phase3_run.py`, against the live stack)

Run: `.venv/bin/python tests/integration/phase3_run.py dev` (≈25 min; the forced-failure
scenario has to wait out 5 real SQS retries). Signs in through the real Cognito authorizer
with the four synthetic users using **per-run random passwords** (set via the admin API, so
the `TempPass1234` in "Manual one-time steps" no longer applies to those four users).

**80/80 checks passed** on the final run. (The first run was 79/80: the one failure was a wrong
assertion in the test — a candidate scoring 100 is *correctly* `recommended` at a threshold of 95 —
so the assertion was changed to `recommended ⇔ match_score ≥ threshold` and the whole suite re-run;
no product code changed.) Covered, mapped to the `docs/03` Definition of Done:

| DoD item | Evidence (live) |
|---|---|
| Worked example = 71.3 on a deployed candidate | Real `scoreMatch` Lambda → 71.3 (66.7 / 60 / 100), `related` title, `dynamodb` missing, stored as a DynamoDB Number |
| Resumes **before** the JD are scored after it parses; no `scoring` failure rows | 4 real resumes wait as `awaiting_jd` (2 bad files already `error` with exact codes), JD uploaded last → all 4 scored automatically; 0 `scoring` rows |
| `jd.source=none` + explicit skills scores immediately; a JD with no skills blocks until PATCHed | Scored with no PATCH; vague text JD → `blocking_reason=no_required_skills`, candidate `awaiting_requirements`, PATCH → `rescore_enqueued=1` → scored |
| PATCH → rescore, decisions untouched | Threshold PATCH re-queues the 4 parsed candidates; every `decision`/`notification_status` identical afterwards; `recommended ⇔ score ≥ 95` |
| `GET …/candidates` returns every candidate with correct status + sort | `processing`, `awaiting_jd`, `error`, `scored` all observed; scored desc, errors last; no internal fields exposed |
| Shortlist→reject→shortlist = exactly one email; missing email → `skipped_no_email`; unscored → 409 | Mailbox simulator: `sent`, `notification_sent_at` unchanged after reject + re-shortlist; no email → `skipped_no_email`; unscored → 409 `NOT_SCORED`; SES-rejected recipient → `failed` with the decision kept and one PII-free `stage=api` audit row |
| Export only shortlisted; `=` name → `'=` | 2 rows, UTF-8 BOM, exact R-BUS-12 columns, `'=cmd…` |
| 401 with CORS; groupless 403 on every route; B → 404 on all of A's routes; Recruiter → 403 on `/failed-jobs` | 401 (no/garbage token) and 403 both carry `Access-Control-Allow-Origin`; preflight 200 without a token; foreign origin not allowed; 403 on all 10 routes; 7/7 of B's probes 404 with a body identical to a non-existent job and DynamoDB unchanged; Admin sees all jobs + `recruiter_id` |
| Forced scoring failure → 5 `scoring` rows → 1 `scoring_exhausted` → `score_status=error`, `parse_status` still `parsed` → alarm | Exactly that; API shows `error`/`scoring_failed`; EMF metric `ResumeScreener/TerminalFailures{Queue=scoring}` exists (JSON log format passes EMF through, so no `PutMetricData` fallback needed); alarm `rs-TerminalFailuresScoring-dev` reached `ALARM` |
| Oversized / tampered uploads rejected by S3 | 11 MB → `EntityTooLarge`; changed `Content-Type` → 403; changed `key` → 403; unsupported extension → API 400 |
| Roles match §8.1; no `Resource: "*"` | Live roles inspected (one inline policy each); only the documented SES `identity/*` |
| No candidate PII in logs; no Textract/Comprehend | 0 hits for names/emails across all 14 function log groups; static grep clean |
| `infra/README.md` runbook | deploy, seed, users, SES, replay, alarms, teardown (below) |

Two things are seeded straight into DynamoDB and then handled by the **real deployed**
`scoreMatch` Lambda, because real NLP cannot be steered to them on demand: the documented
worked example (skills `[python, aws, sql]`, title `backend developer`, 4.0 y → **71.3**), and
a candidate whose `total_experience_years` is a non-number, which makes scoring raise a
genuine exception (→ 5 attempts → DLQ → `score_status=error`). Emails only ever go to the SES
mailbox simulator (`success@simulator.amazonses.com`); fixture addresses are unverified in the
sandbox, which is what exercises the `failed` path. See D-60.

### Notes / gotchas found this phase

- **Colima does not survive a reboot.** `sam build` then fails with "requires a container
  runtime". Run `colima start --cpu 2 --memory 4 --arch x86_64` and re-export `DOCKER_HOST`.
- **REST authorizer input:** the raw ID token goes in `Authorization` (no `Bearer `). The
  `cognito:groups` claim arrives flattened as a string; `rs_common.authz` parses both that and
  list forms, and the deployed groupless check proves the real format is handled.
- **Read-only API routes don't write `failed_jobs` rows on an unexpected 500** (D-58); check
  the function's CloudWatch log and the `rs-Api5xx-dev` alarm instead.
- Alarms have no e-mail subscriber unless the stack is deployed with `AlertEmail=<address>`
  (then confirm the SNS subscription e-mail). The alarm *state* was verified via
  `describe-alarms`; e-mail delivery itself needs that parameter.

## Runbook

- **Re-deploy after a template change**: `make build && make deploy ENV=dev`.
- **Check stack outputs**: `aws cloudformation describe-stacks --stack-name resume-screener-dev --query 'Stacks[0].Outputs'`.
- **Tail a function's logs**: `sam logs -n <LogicalId> --stack-name resume-screener-dev --tail`.
- **Manual replay of a terminal ingestion failure** (phase 2+): see `docs/Architecture.md` §11.6.
  Short form: fix the cause, then either re-add the resume with `POST /jobs/{id}/resumes`
  (preferred) or `aws sqs send-message` the failed row's `raw_payload` (the original S3
  event) to `IngestionQueueUrl`. A scoring failure (`score_status=error`) is recovered by
  `PATCH /jobs/{id}` (any field), which re-queues every parsed candidate.
- **Create/reset a user**: `scripts/create-user.sh dev <email> <Recruiter|Admin|none>`; a
  permanent password can be set with `aws cognito-idp admin-set-user-password --permanent`.
- **SES**: the account is in the sandbox — only verified recipients receive mail. Verify a
  recipient with `aws ses verify-email-identity --email-address <addr> --region ap-south-1`
  before a demo, or use `success@simulator.amazonses.com` for tests. Check the sender:
  `aws ses get-identity-verification-attributes --identities <SesSenderAddress>`.
- **Get a token for manual curl** (SRP only, no password flow is enabled): use
  `tests/integration/phase3_run.py`'s `setup()` helper (pycognito) or the Amplify UI in phase 4.
- **Alarm e-mails**: redeploy with `AlertEmail=you@example.com` and confirm the SNS subscription.
- **Teardown**: empty both buckets, then `sam delete --stack-name resume-screener-dev`. DynamoDB
  tables and log groups are deleted with the stack (no `DeletionPolicy: Retain` is set anywhere).
- **Docker not responding after a reboot**: `colima start` (it does not auto-start on login by
  default); re-`export DOCKER_HOST=...` in any new shell.
