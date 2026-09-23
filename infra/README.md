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
| T-006 | NLP layer size (spaCy 3.8 + `en_core_web_sm` 3.8.0 + `python-dateutil`) | **137 MB** unzipped (`pip install --target`, matching the real layer build method) — comfortably under the 250 MB zip-Layer limit. Biggest contributors: numpy 34 MB, spacy 28 MB, the model 15 MB. No need to package NLP as a container image (D-03 holds) |

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

## Runbook

- **Re-deploy after a template change**: `make build && make deploy ENV=dev`.
- **Check stack outputs**: `aws cloudformation describe-stacks --stack-name resume-screener-dev --query 'Stacks[0].Outputs'`.
- **Tail a function's logs**: `sam logs -n <LogicalId> --stack-name resume-screener-dev --tail`.
- **Manual replay of a terminal ingestion failure** (phase 2+): see `docs/Architecture.md` §11.6.
- **Teardown**: empty both buckets, then `sam delete --stack-name resume-screener-dev`. DynamoDB
  tables and log groups are deleted with the stack (no `DeletionPolicy: Retain` is set anywhere).
- **Docker not responding after a reboot**: `colima start` (it does not auto-start on login by
  default); re-`export DOCKER_HOST=...` in any new shell.
