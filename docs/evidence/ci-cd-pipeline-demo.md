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

## 4. Deployment Verification & Status

- **CloudFormation Stack**: `resume-screener-dev` (`ap-south-1`)
- **Pre-Push Baseline Status**: `UPDATE_COMPLETE` (execution role `arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution` bound to stack)
- **Verification Gates**:
  - **CloudFormation Stack Status**: Verified (`UPDATE_COMPLETE` / `CREATE_COMPLETE`).
  - **CloudFormation Execution Role**: Verified (`RoleARN` matches `arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution`).
  - **CloudFront Frontend Availability**: Verified with HTTP 200 (`https://d1yg427uu45noj.cloudfront.net`).
  - **API Health**: Not probed because all API routes require Cognito authentication and no public health endpoint exists.
- **Demonstration Run**: Pending push
- **Workflow Result**: Pending
- **Deployment Verification**: Pending

---

## 5. Evidence Artifacts

- **CI01 — Git Commit**: Demonstration commit introducing `.github/workflows/deploy.yml` and pipeline documentation to `origin/main` (Commit SHA: pending commit).
- **CI02 — GitHub Actions Pipeline Run**: Demonstration run: pending push (workflow result: pending).
- **CI03 — Deployment & IAM Verification**: Deployment verification: pending (post-run verification will record final stack state, RoleARN confirmation, and CloudFront availability).
