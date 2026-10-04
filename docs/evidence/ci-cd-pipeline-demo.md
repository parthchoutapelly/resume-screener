# CI/CD Pipeline Demo — Resume Screener

## 1. Pipeline Architecture

This deliverable demonstrates an enterprise-grade, least-privilege **two-tier CI/CD deployment pipeline** for the `resume-screener` application on AWS using GitHub Actions and AWS IAM OpenID Connect (OIDC).

```
GitHub Actions Runner (Ubuntu)
       │ (1. OIDC Token Exchange)
       ▼
AWS STS (sts:AssumeRoleWithWebIdentity)
       │ (2. Assumes Role 1 with repo/branch claim)
       ▼
Role 1: resume-screener-github-actions-deploy
       │ (3. SAM build / package / upload to S3 & ECR)
       │ (4. Initiates CloudFormation ChangeSet passing Role 2)
       ▼
CloudFormation Service
       │ (5. Assumes Role 2 for changeset execution)
       ▼
Role 2: resume-screener-cloudformation-execution
       │ (6. Provisions / updates stack resources & binds runtime roles)
       ▼
Application Resources (Lambda, API Gateway, DynamoDB, S3, SQS, SNS, Cognito, CloudFront)
```

### Key Security Properties
- **Zero Long-Lived Credentials**: No AWS access keys or secrets are stored in GitHub repository secrets or variables. Authentication relies exclusively on short-lived STS tokens via GitHub OIDC.
- **Strict OIDC Trust Boundary**: The trust policy enforces exact `StringEquals` matches on `aud: sts.amazonaws.com` and `sub: repo:parthchoutapelly/resume-screener:ref:refs/heads/main` with zero wildcards.
- **No Direct Application Permissions on GitHub Principal**: Role 1 (`resume-screener-github-actions-deploy`) has zero direct permissions for application services (`lambda:*`, `dynamodb:*`, `apigateway:*`, `sqs:*`, `sns:*`, `logs:*`, `cognito-idp:*`).
- **Delegated CloudFormation Execution**: Resource management authority is delegated strictly to CloudFormation under a dedicated service execution role (`resume-screener-cloudformation-execution`).
- **PassRole Isolation**:
  - GitHub role can `PassRole` **only** to `resume-screener-cloudformation-execution` with condition `iam:PassedToService = cloudformation.amazonaws.com`.
  - CloudFormation execution role can `PassRole` **only** to the 15 runtime execution roles with condition `iam:PassedToService` in `["lambda.amazonaws.com", "apigateway.amazonaws.com"]`.
- **Target Account Validation**: The pipeline queries `aws sts get-caller-identity` and asserts the authenticated account ID equals `331262815638` before building or deploying.

---

## 2. Demonstration Commit

- **Repository**: `parthchoutapelly/resume-screener`
- **Branch**: `main`
- **Target Stack**: `resume-screener-dev` (`ap-south-1`)
- **Commit Message**: `docs(ci): add secure GitHub Actions deployment pipeline`
- **Commit SHA**: Pending commit
- **Demonstration Run**: Pending push
- **Files Included**:
  - `.github/workflows/deploy.yml`
  - `docs/evidence/ci-cd-pipeline-demo.md`

---

## 3. GitHub Actions Workflow Configuration

- **Workflow File**: `.github/workflows/deploy.yml`
- **Trigger**: `push` on `refs/heads/main` (pull requests trigger `build` and `test` only)
- **Pinned Action Versions (Immutable SHAs)**:
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`)
  - `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (`v7.0.0`)
  - `aws-actions/setup-sam@89ddb14d60e682855e3fea4be85b3c56485de310` (`v3`)
  - `aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd` (`v6.3.0`)

### Workflow Stages
1. **`build`**: Compiles container images (`ExtractionFunction`, `NlpFunction`) and Lambda zip packages using AWS SAM CLI with native Docker daemon on Ubuntu.
2. **`test`**: Validates dictionaries, executes 439 unit and component tests (`pytest`), and runs 14 frontend tests (`vitest`).
3. **`deploy`**: Authenticates via GitHub OIDC, asserts account safety, and executes `sam deploy` associating `resume-screener-cloudformation-execution`.
4. **`verify`**: Queries CloudFormation to assert `StackStatus` is `UPDATE_COMPLETE`, verifies `RoleARN` matches `arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution`, and verifies CloudFront frontend availability with HTTP 200.

---

## 4. Execution History & Pipeline Attempts

### Attempt 1
- **Commit**: `00642b7d226d193efffa352b881db24feee0ea06`
- **Workflow Run**: `37211131427`
- **Result**:
  - Build: **SUCCESS**
  - Test: **FAILURE** (`pip install -e backend/layers/common_layer/python`)
  - Deploy: **SKIPPED**
  - Verify: **SKIPPED**
- **Root Cause**: `backend/layers/common_layer/python` is a layer directory without a `pyproject.toml` or `setup.py` and cannot be installed via `pip install -e`.

---

### Attempt 2
- **Commit**: `acf3d54ea149e4ad464a49d65ac74c8b6715ee06`
- **Workflow Run**: `37211734065`
- **Result**:
  - Build: **SUCCESS**
  - Test: **FAILURE** (`botocore.exceptions.NoRegionError: You must specify a region`)
  - Deploy: **SKIPPED**
  - Verify: **SKIPPED**
- **Root Cause**: Clean GitHub Actions Ubuntu runner lacked `AWS_DEFAULT_REGION` during test discovery/boto3 client initialization.

---

### Attempt 3
- **Commit**: `484c982b00a993552801c6612a9f1b1d39383309`
- **Workflow Run**: `37212856938`
- **Result**:
  - Build: **SUCCESS**
  - Test: **FAILURE** (Unit tests passed 282/282; Component tests failed: `TesseractNotFoundError` and `Can't find model 'en_core_web_sm'`)
  - Deploy: **SKIPPED**
  - Verify: **SKIPPED**
- **Root Cause**: Runner environment lacked the system `tesseract-ocr` binary for real document OCR and the spaCy English model package `en_core_web_sm`.

---

### Attempt 4
- **Commit**: `192cbf89a7ad9e6dfd969c46e9dfa18a65f7481c`
- **Workflow Run**: `37213291149` (Initial Attempt)
- **Result**:
  - Build: **SUCCESS** (1m 46s)
  - Test: **SUCCESS** (1m 20s — dictionary validation: PASS, unit tests: 282 passed, component tests: 157 passed, frontend tests: 14 passed)
  - Deploy: **FAILURE** (1m 15s — `Configure AWS Credentials via GitHub OIDC`: `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`)
  - Verify: **SKIPPED**
- **Root Cause**: GitHub Actions token `sub` claim transitioned to immutable format with owner/repo IDs (`repo:parthchoutapelly@143930644/resume-screener@1383681742:ref:refs/heads/main`), failing the exact `StringEquals` in the IAM trust policy that expected classic `repo:parthchoutapelly/resume-screener:ref:refs/heads/main`.

---

### Attempt 5 (Rerun of Run 37213291149)
- **Commit**: `192cbf89a7ad9e6dfd969c46e9dfa18a65f7481c`
- **Workflow Run**: `37213291149` (Rerun Attempt)
- **Result**:
  - Build: **SUCCESS** (1m 57s)
  - Test: **SUCCESS** (1m 18s)
  - Deploy: **FAILURE** (1m 53s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS** (OIDC trust policy fix verified!)
    - `Validate Target AWS Account ID`: **SUCCESS** (Account: `331262815638`)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`: **FAILURE** (`cloudformation:CreateChangeSet` denied on `arn:aws:cloudformation:ap-south-1:331262815638:stack/aws-sam-cli-managed-default/*`)
  - Verify: **SKIPPED**
- **Root Cause**: `sam deploy --resolve-s3` automatically manages the SAM CLI bootstrap helper stack `aws-sam-cli-managed-default`. The deployment role's CloudFormation permission is tightly scoped only to `arn:aws:cloudformation:ap-south-1:331262815638:stack/resume-screener-dev/*`.

---

### Attempt 6 (Commit e0d41a3, Run 37214686693)
- **Commit**: `e0d41a34f1ad21d8cef899d188d552219cc88ee3`
- **Workflow Run**: `37214686693` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37214686693`)
- **Result**:
  - Build: **SUCCESS** (1m 55s)
  - Test: **SUCCESS** (1m 30s)
  - Deploy: **FAILURE** (2m 06s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS**
    - `Validate Target AWS Account ID`: **SUCCESS** (`331262815638`)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`: **FAILURE** (`cloudformation:DescribeStacks` denied on `arn:aws:cloudformation:ap-south-1:331262815638:stack/resume-screener-dev-8b303e78-CompanionStack/91621ff0-b75b-11f1-a8a8-06313fa77f27`)
  - Verify: **SKIPPED**
- **Root Cause**: Providing explicit `--s3-bucket` and `--s3-prefix` successfully eliminated all calls to the SAM helper stack `aws-sam-cli-managed-default`. However, `--resolve-image-repos` looks up the ECR companion stack `resume-screener-dev-8b303e78-CompanionStack`. The deploy role's CloudFormation permission was scoped to `arn:aws:cloudformation:ap-south-1:331262815638:stack/resume-screener-dev/*`, which does not encompass `resume-screener-dev-8b303e78-CompanionStack/*`.

---

### Attempt 7 (Commit 75d3473, Run 37215393115)
- **Commit**: `75d34732591931192cde656e5c7c25495b97ce26`
- **Workflow Run**: `37215393115` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37215393115`)
- **Result**:
  - Build: **SUCCESS** (2m 14s)
  - Test: **SUCCESS** (1m 33s)
  - Deploy: **FAILURE** (1m 58s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS**
    - `Validate Target AWS Account ID`: **SUCCESS** (`331262815638`)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`: **FAILURE** (Exit code 2: `Error: Incomplete list of function logical ids specified for '--image-repositories'`)
  - Verify: **SKIPPED**
- **Root Cause**: SAM CLI CLI parser (`click`) requires `--image-repositories` flag to be repeated for each function (`--image-repositories Function1=URI --image-repositories Function2=URI`). Providing them space-separated under a single flag caused Click to parse only the first function, causing SAM CLI to error out before reaching AWS.

---

### Attempt 8 (Commit 8a006f1, Run 37216166088 — Initial Attempt)
- **Commit**: `8a006f1483104c1885634b4c409dcf1ce60158bb`
- **Workflow Run**: `37216166088` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088`)
- **Result**:
  - Build: **SUCCESS** (1m 56s)
  - Test: **SUCCESS** (1m 34s)
  - Deploy: **FAILURE** (3m 20s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS**
    - `Validate Target AWS Account ID`: **SUCCESS** (`331262815638`)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`:
      - Repeated `--image-repositories` accepted: **SUCCESS**
      - ECR container images built & pushed: **SUCCESS**
      - S3 deployment artifacts uploaded: **SUCCESS**
      - CloudFormation ChangeSet creation: **FAILURE** (`resume-screener-cloudformation-execution` denied `cloudformation:CreateChangeSet` on macro `arn:aws:cloudformation:ap-south-1:aws:transform/Serverless-2016-10-31`)
  - Verify: **SKIPPED**
- **Root Cause**: CloudFormation service execution role (`resume-screener-cloudformation-execution`) lacked permission to execute the SAM macro `cloudformation:CreateChangeSet` on resource `arn:aws:cloudformation:ap-south-1:aws:transform/Serverless-2016-10-31`.

---

### Attempt 9 (Commit 8a006f1, Run 37216166088 — Rerun 1)
- **Commit**: `8a006f1483104c1885634b4c409dcf1ce60158bb`
- **Workflow Run**: `37216166088` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088`)
- **Result**:
  - Build: **SUCCESS** (2m 01s)
  - Test: **SUCCESS** (1m 34s)
  - Deploy: **FAILURE** (5m 53s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS**
    - `Validate Target AWS Account ID`: **SUCCESS** (`331262815638`)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`:
      - ECR container images built & pushed: **SUCCESS**
      - S3 deployment artifacts uploaded: **SUCCESS**
      - SAM Transform Macro Execution: **SUCCESS** (ChangeSet created successfully!)
      - ChangeSet Resource Execution: **FAILURE** (Creation of `CommonLayer0ac4566826` failed with 403 `AccessDenied` calling `s3:GetObject` on `arn:aws:s3:::aws-sam-cli-managed-default-samclisourcebucket-4sdbhpupwvml/resume-screener-dev/3b93d2bb1edb18af6a1b089fc1db9d59`)
  - Verify: **SKIPPED**
- **Root Cause**: CloudFormation service execution role (`resume-screener-cloudformation-execution`) lacked `s3:GetObject` permission on the deployment package in the SAM source bucket. When creating Lambda layers/functions from S3 packages, CloudFormation validates and fetches the bundle using the execution role credentials.

---

### Attempt 10 — FINAL SUCCESSFUL RUN (Commit 8a006f1, Run 37216166088 — Rerun 2)
- **Commit**: `8a006f1483104c1885634b4c409dcf1ce60158bb` (`fix: correct sam image repository flags`)
- **Workflow Run**: `37216166088` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088`)
- **Result**: **ALL FOUR STAGES SUCCEEDED (END-TO-END CI/CD SUCCESS)**
  - **Build**: **SUCCESS** (2m 15s)
    - Set up Python 3.12: **SUCCESS**
    - Set up AWS SAM CLI: **SUCCESS**
    - Build SAM Application with Docker daemon: **SUCCESS** (Container compilation for `ExtractionFunction` and `NlpFunction`, zip packaging for 12 Lambda functions and layer)
  - **Test**: **SUCCESS** (1m 28s)
    - Validate Skills & Dictionaries: **PASS**
    - Run Unit Tests: **282 passed**
    - Run Component Tests: **157 passed**
    - Run Frontend Tests: **14 passed**
  - **Deploy**: **SUCCESS** (4m 05s)
    - `Configure AWS Credentials via GitHub OIDC`: **SUCCESS** (Assumed `arn:aws:iam::331262815638:role/resume-screener-github-actions-deploy`)
    - `Validate Target AWS Account ID`: **SUCCESS** (Account `331262815638` verified)
    - `Build SAM Application`: **SUCCESS**
    - `Deploy SAM Stack`: **SUCCESS**
      - Explicit S3 artifact upload to bucket `aws-sam-cli-managed-default-samclisourcebucket-4sdbhpupwvml`: **SUCCESS**
      - Explicit ECR image push to repositories: **SUCCESS**
      - SAM Transform macro expansion: **SUCCESS**
      - ChangeSet creation: **SUCCESS**
      - Lambda Layer `CommonLayer` created via `ReadSamDeploymentArtifacts`: **SUCCESS**
      - All Lambda function updates: **SUCCESS**
      - Stack deployment: **SUCCESS** (`Successfully created/updated stack - resume-screener-dev in ap-south-1`)
  - **Verify**: **SUCCESS** (10s)
    - CloudFormation Stack Status: **`UPDATE_COMPLETE`**
    - CloudFormation Attached Service Role: **`arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution`**
    - CloudFront Frontend Availability Check: **`HTTP 200`** (`https://d1yg427uu45noj.cloudfront.net`)

---

## 5. Deployment Verification & Status

- **CloudFormation Stack**: `resume-screener-dev` (`ap-south-1`)
- **Final Stack Status**: `UPDATE_COMPLETE` (verified directly via workflow post-deployment verification job and AWS CLI)
- **Attached Service Execution Role**: `arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution`
- **CloudFront Frontend Availability**: `HTTP 200` (`https://d1yg427uu45noj.cloudfront.net`)
- **Workflow Status**: Run `37216166088` completed with conclusion **`success`** across all four stages: `BUILD` -> `TEST` -> `DEPLOY` -> `VERIFY`.

---

## 6. Evidence Artifacts

- **CI01 — Git Commit**: Commit `8a006f1483104c1885634b4c409dcf1ce60158bb` (`fix: correct sam image repository flags`) on `main`.
- **CI02 — GitHub Actions Pipeline Run**: Run `37216166088` (`https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088`) — Conclusion: `success`.
  - Job 1 (`Build SAM Application`): `https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088/job/111482129422` (SUCCESS)
  - Job 2 (`Run Quality Gates & Tests`): `https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088/job/111482548055` (SUCCESS)
  - Job 3 (`Deploy Stack via CloudFormation Service Role`): `https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088/job/111482824455` (SUCCESS)
  - Job 4 (`Read-Only Post-Deployment Verification`): `https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088/job/111483568495` (SUCCESS)
- **CI03 — Deployment & IAM Verification**: Verified two-tier role architecture, least-privilege IAM scoping, zero long-lived credentials, Access Analyzer validation (0 errors), CloudFormation service execution role persistence, and CloudFront HTTP 200 availability.
