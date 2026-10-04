# AWS Cloud Engineering Internship Portfolio

An enterprise-oriented suite of four serverless cloud architectures deployed in **AWS Asia Pacific (Mumbai) `ap-south-1`**, hardened for security least-privilege, cross-project observability, transparent 3-tier cost modeling, automated OIDC CI/CD deployment, empirical load testing, and operational runbook reliability.

[![CI/CD Pipeline](https://github.com/parthchoutapelly/resume-screener/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088)
[![AWS](https://img.shields.io/badge/AWS-Serverless-orange.svg?logo=amazon-aws)](https://aws.amazon.com/)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://www.python.org/)
[![React](https://img.shields.io/badge/Frontend-React_18-61DAFB.svg?logo=react)](https://react.dev/)
[![Infrastructure](https://img.shields.io/badge/IaC-AWS_SAM_%2F_CloudFormation-red.svg)](https://aws.amazon.com/serverless/sam/)

---

## Table of Contents

- [1. Portfolio Overview](#1-portfolio-overview)
- [2. The Four Portfolio Projects](#2-the-four-portfolio-projects)
  - [Project 1: AWS Cloud Security Analyzer / CloudGuard ULTRA](#project-1-aws-cloud-security-analyzer--cloudguard-ultra)
  - [Project 2: VEYRA / Smart Employee Onboarding & Identity Service](#project-2-veyra--smart-employee-onboarding--identity-service)
  - [Project 3: Smart Leave & Absence Management Engine](#project-3-smart-leave--absence-management-engine)
  - [Project 4: AI-Powered Resume Screener Pipeline](#project-4-ai-powered-resume-screener-pipeline)
- [3. Architecture & Serverless Design Patterns](#3-architecture--serverless-design-patterns)
- [4. Security Controls & Hardening](#4-security-controls--hardening)
- [5. Observability & Telemetry](#5-observability--telemetry)
- [6. Enterprise CI/CD Automation](#6-enterprise-cicd-automation)
- [7. Cost Estimation & 3-Tier Scaling Analysis](#7-cost-estimation--3-tier-scaling-analysis)
- [8. Testing & Load Performance](#8-testing--load-performance)
- [9. Six Required Internship Deliverables](#9-six-required-internship-deliverables)
- [10. Repository Structure](#10-repository-structure)
- [11. Local Development & Deployment](#11-local-development--deployment)
- [12. Further Documentation & Verification](#12-further-documentation--verification)

---

## 1. Portfolio Overview

This portfolio synthesizes four production-style cloud engineering projects designed and hardened during the AWS Cloud Engineering Internship. Rather than relying on simple toy examples or monolithic patterns, every project implements an event-driven, decoupled serverless architecture adhering to the AWS Well-Architected Framework:

- **Security & IAM Least Privilege**: Elimination of wildcard permissions, strict resource ARN scoping, functional S3 prefix isolation, condition-scoped SES sending, and zero static credentials via GitHub Actions OIDC.
- **Unified Observability**: A cross-project CloudWatch dashboard (`internship-portfolio-overview-dev`) delivering single-pane visibility across critical alarms, API ingress, Lambda compute health, database operations, and dead-letter queues.
- **Transparent Cost Modeling**: Comprehensive 3-tier scaling financial models (Dev, Team, High Scale) calculated on gross list prices before account-level free tiers, distinguishing active deployed baselines from architectural optimization scenarios.
- **Automated Delivery**: Enterprise two-tier OIDC deployment pipeline enforcing build compilation, 453 automated tests, and CloudFormation service role execution.
- **Empirical Validation**: Measured load testing using Artillery Core to stress concurrency ceilings and uncover architectural scaling bottlenecks.
- **Operational Readiness**: Practical one-page operational runbooks for each project with real CLI health checks, failure diagnostic trees, and safe rollback procedures.

---

## 2. The Four Portfolio Projects

| Project | Primary Stack Name | Architecture Pattern | Key AWS Services | Key Engineering Outcome |
|---|---|---|---|---|
| **Project 1: Cloud Security Analyzer / CloudGuard ULTRA** | `employee-document-vault-dev` | REST Microservices + Secure Storage | API Gateway, Lambda, S3, DynamoDB, KMS CMK, X-Ray | Dedicated customer-managed KMS key encryption, strict `/documents/*` presigned URL scoping, immutable audit logging. |
| **Project 2: VEYRA** | `onboarding-service-dev` | Workflow Orchestration + Identity | API Gateway, Step Functions, Lambda, Cognito, DynamoDB, SES, SNS | Multi-stage onboarding state machine, identity provisioning, 3,000-request Artillery load-tested API. |
| **Project 3: Smart Leave** | `smart-leave-management-dev` | High-Efficiency HTTP API + Approval | HTTP API v2, Step Functions, Lambda, Secrets Manager, DynamoDB, SES | 71% ingress cost reduction via HTTP APIs, cryptographic token signing for manager email approvals, atomic balance ledgers. |
| **Project 4: Resume Screener** | `resume-screener-dev` | Asynchronous Event-Driven Pipeline | CloudFront OAC, REST API, SQS, Container Lambdas, DynamoDB, SES | Containerized Tesseract OCR & spaCy NLP parsing, explainable scoring, zero-credential GitHub Actions OIDC CI/CD. |

---

### Project 1: AWS Cloud Security Analyzer / CloudGuard ULTRA
*Context: Deployed within the Employee Document Workspace / DocVault architecture (`employee-document-vault-dev`).*

- **Purpose**: Provides cryptographically isolated, auditable document storage for sensitive employee records, combining zero-trust presigned access with continuous cloud security inspection.
- **Architecture Highlights**: Amazon API Gateway REST API invokes 7 dedicated Lambda functions (`Upload`, `Download`, `Delete`, `ListFiles`, `UpdateTags`, `Versions`, `Activity`). Documents are stored in Amazon S3 encrypted under a dedicated AWS KMS Customer Managed Key (`alias/docvault-cmk-dev`) with automated key rotation.
- **Key Security Controls**: Enforces S3 functional prefix isolation (`/documents/{employee_id}/*`), S3 Public Access Block, bucket policy requiring TLS transport (`DenyInsecureTransport`), and immutable change tracking in `AuditLogTable`.
- **Evidence Reference**: [Project 1 IAM Audit](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project1-cloudguard-docvault.md) | [Project 1 Runbook](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project1-cloudguard.md)

---

### Project 2: VEYRA / Smart Employee Onboarding & Identity Service
*Context: Deployed as `onboarding-service-dev`.*

- **Purpose**: Coordinates the multi-step employee onboarding lifecycle across identity creation, document collection, IT asset provisioning, and compliance sign-offs.
- **Architecture Highlights**: Uses AWS Step Functions (`OnboardingStateMachine`) to orchestrate 13 Lambda microservices, managing state transitions and sending event-driven email notifications via Amazon SES. User identity is managed through an Amazon Cognito User Pool.
- **Key Security Controls**: Amazon SES email sending is strictly scoped to the verified sender identity ARN. Amazon S3 presigned upload generation enforces tenant-isolated prefixes.
- **Evidence Reference**: [Project 2 IAM Audit](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project2-veyra-onboarding.md) | [Artillery Load Test](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-test-report.md) | [Project 2 Runbook](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project2-veyra-onboarding.md)

---

### Project 3: Smart Leave & Absence Management Engine
*Context: Deployed as `smart-leave-management-dev`.*

- **Purpose**: Automates employee leave requests, quota deduction, cryptographically signed manager approval routing, team availability conflict detection, and HR SLA escalations.
- **Architecture Highlights**: Leverages **Amazon API Gateway HTTP APIs (v2)** to achieve a 71% cost reduction over Regional REST APIs. Coordinates 12 Lambda functions and a Step Functions approval workflow. Uses **AWS Secrets Manager** to store an `ApprovalSecret` that generates tamper-proof HMAC tokens for one-click email approvals.
- **Key Security Controls**: 13 newly codified least-privilege IAM roles. Secrets Manager access is restricted exclusively to the token processing Lambdas. DynamoDB balance deductions enforce atomic conditional expressions to prevent overdrafts.
- **Evidence Reference**: [Project 3 IAM Audit](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project3-smart-leave.md) | [Project 3 Runbook](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project3-smart-leave.md)

---

### Project 4: AI-Powered Resume Screener Pipeline
*Context: Deployed as `resume-screener-dev`.*

- **Purpose**: Automates candidate resume parsing, OCR text extraction, deterministic experience calculation, explainable NLP skill matching, and recruiter decision management.
- **Architecture Highlights**:
  - **CDN & Frontend**: Single Page Application hosted on Amazon S3 and distributed via **Amazon CloudFront** (`https://d1yg427uu45noj.cloudfront.net`) with **Origin Access Control (OAC)**.
  - **API Ingress**: Amazon API Gateway with dedicated `ApiGatewayCloudWatchRole` and Cognito User Pool authorization.
  - **Asynchronous Processing**: Decoupled via **Amazon SQS** queues (`IngestionQueue`, `ScoringQueue`) backed by Dead Letter Queues (`IngestionDlq`, `ScoringDlq`).
  - **High-Performance Compute**: Custom containerized Lambda functions running **Tesseract OCR** and **spaCy NLP** (1536 MB RAM) alongside 12 zip-packaged microservices and a shared `CommonLayer`.
  - **Data Resilience**: Four DynamoDB tables (`JobsTable`, `CandidatesTable`, `FailedJobsTable`, `ConfigTable`) operating on-demand with **Point-in-Time Recovery (PITR)** and Deletion Protection enabled.
- **Evidence Reference**: [Project 4 IAM Audit](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project4-resume-screener.md) | [CI/CD Demonstration](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md) | [Project 4 Runbook](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project4-resume-screener.md)

---

## 3. Architecture & Serverless Design Patterns

The portfolio demonstrates five core serverless design patterns across the AWS ecosystem:

```
Pattern A: Asynchronous Ingestion & Queued Processing (Resume Screener)
[CloudFront / S3] ──> [API Gateway] ──> [S3 Upload Bucket] ──> [SQS Ingestion] ──> [OCR Lambda] ──> [NLP Lambda] ──> [DynamoDB] ──> [SQS Scoring] ──> [ScoreMatch Lambda]

Pattern B: State Machine Orchestration (VEYRA & Smart Leave)
[API Ingress] ──> [Step Functions State Machine] ──> [Worker Lambdas] ──> [DynamoDB / S3 / SES]
                           │
                           └──> [Task Token Wait State] ──> (Manager One-Click Action) ──> [Task Completion]

Pattern C: High-Efficiency HTTP API Ingress (Smart Leave)
[Client] ──> [API Gateway HTTP API v2 ($1/M)] ──> [Lambda Handlers] ──> [Secrets Manager / DynamoDB]

Pattern D: Cryptographic Enclave & KMS Key Isolation (CloudGuard / DocVault)
[Client] ──> [API Gateway] ──> [Lambda] ──> [S3 Bucket (SSE-KMS Customer Managed Key)] ──> [DynamoDB Audit Ledger]

Pattern E: Two-Tier Least-Privilege CI/CD (GitHub Actions OIDC)
[GitHub Runner] ──(OIDC)──> [Role 1: deploy] ──(PassRole)──> [CloudFormation] ──(Assumes)──> [Role 2: execution] ──> [Stack Resources]
```

---

## 4. Security Controls & Hardening

Security hardening is enforced through concrete infrastructure-as-code controls:

1. **Zero Long-Lived Credentials**: CI/CD pipelines use short-lived AWS STS tokens via **GitHub Actions OIDC** (`sts:AssumeRoleWithWebIdentity`). No access keys or secrets are stored in GitHub repository secrets.
2. **Strict OIDC Subject Constraints**: The trust policy on `resume-screener-github-actions-deploy` enforces exact `StringEquals` matching against the immutable GitHub repository and branch identifier:
   `repo:parthchoutapelly@143930644/resume-screener@1383681742:ref:refs/heads/main`.
3. **Two-Tier IAM Separation & Delegated Execution**:
   - `resume-screener-github-actions-deploy` (Deployment Role): Zero direct application infrastructure permissions (`lambda:*`, `dynamodb:*`, `s3:CreateBucket`). Authorized only to upload deployment artifacts and initiate ChangeSets.
   - `resume-screener-cloudformation-execution` (Service Execution Role): CloudFormation service-assumed role strictly bound to the application stack ARN (`arn:aws:cloudformation:ap-south-1:331262815638:stack/resume-screener-dev/*`) and the SAM Serverless Transform macro (`arn:aws:cloudformation:ap-south-1:aws:transform/Serverless-2016-10-31`).
4. **Restricted `iam:PassRole` Boundaries**:
   - Deployment role can only pass `resume-screener-cloudformation-execution` to `cloudformation.amazonaws.com`.
   - Execution role can only pass the 15 runtime roles to `lambda.amazonaws.com` and `apigateway.amazonaws.com`.
5. **Functional S3 Prefix Isolation**:
   - Upload functions: Restricted to `/jd-uploads/*` and `/resume-uploads/*`.
   - Resume download URLs: Restricted to `/resume-uploads/*`.
   - Shortlist CSV exports: Restricted to `/exports/*`.
6. **Condition-Scoped Email Sending**:
   - In Amazon SES sandbox, `ses:SendEmail` is constrained by IAM Condition `StringEquals: "ses:FromAddress": !Ref SesSenderAddress` to prevent unauthorized sender spoofing.
7. **CloudFront Origin Access Control (OAC)**: S3 web hosting buckets deny public access and accept requests exclusively from the designated CloudFront distribution ARN via HTTPS (`DenyInsecureTransport`).
8. **IAM Access Analyzer Verification**: All IAM policies and resource policies validate with **0 ERROR findings** in AWS IAM Access Analyzer.

---

## 5. Observability & Telemetry

Cross-project operational visibility is centralized in the CloudWatch dashboard:

### Dashboard: `internship-portfolio-overview-dev` (`ap-south-1`)

The dashboard provides 13 dedicated widgets structured across four operational tiers:
1. **Critical Portfolio Alarms Status**: Consolidated view of all active metric alarms across the four projects.
2. **Fleetwide Regional Lambda Activity**: Regional execution counts, error rates, and duration tracking across all serverless compute.
3. **Project-Specific Workload Tracking**:
   - *Project 1*: DocVault API Gateway call volume, 4xx/5xx errors, latency, and DynamoDB read/write units.
   - *Project 2*: VEYRA Step Functions execution rates (ExecutionsStarted, ExecutionsSucceeded, ExecutionsFailed) and API Gateway latency.
   - *Project 3*: Smart Leave HTTP API request volume, status codes, and manager approval SLA timings.
   - *Project 4*: Resume Screener recruiter API latency, SQS ingestion queue depth, and scoring queue backlogs.
4. **Security & Reliability**:
   - 4xx client and authorization rejections (Cognito/API Gateway auth failures).
   - Dead Letter Queue messages received (`rs-ingestion-dlq-dev`, `rs-scoring-dlq-dev`) and Lambda throttling events.

*Evidence Artifacts*: [Full Dashboard (PNG)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01_cloudwatch_portfolio_dashboard.png) | [Top Section (PNG)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01a_portfolio_overview_top.png) | [Bottom Section (PNG)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01b_portfolio_overview_bottom.png)

---

## 6. Enterprise CI/CD Automation

Continuous Integration and Continuous Deployment are implemented using GitHub Actions and AWS SAM:

### Pipeline Architecture (`.github/workflows/deploy.yml`)

```
GitHub Commit (main)
        │
        ├──> [1. BUILD Stage]
        │       ├── Container image build (ExtractionFunction, NlpFunction)
        │       └── Zip artifact packaging (12 Lambdas + CommonLayer)
        │
        ├──> [2. TEST Stage]
        │       ├── Dictionary & skill taxonomy validation
        │       ├── 282 Unit tests (pytest)
        │       ├── 157 Component tests (OCR & spaCy)
        │       └── 14 Frontend tests (Vitest)
        │
        ├──> [3. DEPLOY Stage]
        │       ├── OIDC authentication to resume-screener-github-actions-deploy
        │       ├── AWS account ID safety check (assert 331262815638)
        │       ├── S3 artifact upload (aws-sam-cli-managed-default-samclisourcebucket-*)
        │       ├── ECR container image push (explicit repositories)
        │       ├── CloudFormation ChangeSet creation (passing execution role)
        │       └── CloudFormation deployment execution
        │
        └──> [4. VERIFY Stage]
                ├── Assert StackStatus == UPDATE_COMPLETE
                ├── Assert RoleARN == arn:aws:iam::...:role/resume-screener-cloudformation-execution
                └── Assert CloudFront frontend availability (HTTP 200)
```

### Verified Successful Pipeline Run
- **Workflow Run**: **[37216166088](https://github.com/parthchoutapelly/resume-screener/actions/runs/37216166088)**
- **Commit**: `8a006f1483104c1885634b4c409dcf1ce60158bb`
- **Results**: `BUILD` = **SUCCESS** (2m 15s) | `TEST` = **SUCCESS** (1m 28s) | `DEPLOY` = **SUCCESS** (4m 05s) | `VERIFY` = **SUCCESS** (10s)
- **Live Status**: CloudFormation stack `resume-screener-dev` in **`UPDATE_COMPLETE`**, attached role verified, CloudFront frontend returning **`HTTP 200`**.
- **Audit History**: [Complete 10-Attempt Pipeline Hardening Evidence](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md).

---

## 7. Cost Estimation & 3-Tier Scaling Analysis

A comprehensive 3-tier financial model was constructed to evaluate monthly AWS expenditures in **`ap-south-1`**:
- **Primary Model Workbook**: [`docs/evidence/cost-estimation-3-tier-all-projects.xlsx`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.xlsx)
- **Supporting Technical Report**: [`docs/evidence/cost-estimation-3-tier-all-projects.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.md)

### Monthly Cost Summary (Gross List-Price Basis, ap-south-1)

| Project | Stack Name | Tier 1 (Dev / Low) | Tier 2 (Moderate / Team) | Tier 3 (High Scale) | Key Cost Driver |
|---|---|---:|---:|---:|---|
| **Project 1: DocVault** | `employee-document-vault-dev` | $2.01 | $4.74 | $43.62 | Fixed KMS CMK ($1.00); S3 storage & logs at scale |
| **Project 2: VEYRA** | `onboarding-service-dev` | $1.87 | **$99.63** | **$2,315.90** | Cognito Essentials MAUs ($0.015/MAU after 10k free) |
| **Project 3: Smart Leave** | `smart-leave-management-dev` | **$1.35** | **$6.25** | **$67.12** | Lowest API cost ($1.00/M via HTTP API); Secrets Manager ($0.40) |
| **Project 4: Resume Screener** | `resume-screener-dev` | $1.73 | $9.93 | $95.36 | Containerized Lambda compute (1536MB OCR/NLP) & S3 |
| **Portfolio Total (Current Deployed Baseline — Cognito Essentials)** | *All 4 Projects* | **$6.96** | **$120.55** | **$2,521.99** | *Reflects active deployed configuration across all projects* |

### Cost Sensitivity & Optimization Scenario (Cognito Lite)
- **Current Deployed Configuration**: Project 2 currently runs **Cognito Essentials** (the default when `UserPoolTier` is unspecified).
- **Architectural Optimization (Cognito Lite)**: Configuring `UserPoolTier: LITE` ($0.0055/MAU after 50,000 free) reduces Project 2 to **$24.63/mo** (Tier 2) and **$765.90/mo** (Tier 3), bringing the **Portfolio Total to $45.55/month (Tier 2)** and **$971.99/month (Tier 3)** — saving over **$1,550/month** at enterprise scale.
- **Pure Infrastructure Spend**: Excluding end-user identity licensing, the four projects consume only **$45.55/mo** at Tier 2 and **$421.99/mo** at Tier 3 in pure serverless infrastructure.

---

## 8. Testing & Load Performance

### Quality Gates (453 Automated Tests)
- **Unit Tests (`pytest`)**: **282 tests passing** covering schemas, extraction algorithms, parsing utilities, and scoring models.
- **Component Tests (`pytest`)**: **157 tests passing** validating live Tesseract OCR execution, spaCy NER tokenization, SQS message packaging, and DynamoDB transactions.
- **Frontend Tests (`vitest`)**: **14 tests passing** verifying React UI views, candidate list rendering, and recruiter review workflows.
- **Data Validation**: Automated schema validation against dictionary taxonomy fixtures.

### Empirical Load Testing (Artillery Core)
- **Measured Target**: Executed against Project 2 (`onboarding-service-dev`) REST API Gateway (`https://5goe29bglh.execute-api.ap-south-1.amazonaws.com/dev`).
- **Load Profile**: Un-ramped step arrival of **50 requests/second** across 60 seconds (total **3,000 requests** executed, 3,000 VUs completed).
- **Measured Response Latencies (Artillery)**:
  - **Median (p50)**: **47.0 ms**
  - **p95**: **73.0 ms**
  - **p99**: **111.1 ms**
  - **Minimum**: **36.2 ms**
- **HTTP Status Distribution**:
  - **HTTP 200 OK**: **2,947 requests (98.23%)**
  - **HTTP 4xx**: **0 requests (0.00%)**
  - **HTTP 5xx**: **53 requests (1.77%)**
- **Root Cause & Concurrency Governance**:
  - All 53 errors occurred strictly within the first **8.8 seconds** of traffic injection.
  - Correlating CloudWatch metrics revealed application `Errors: 0` across all functions, while `Throttles` accounted for exactly 53 dropped invocations.
  - Root cause was proven to be the AWS account regional concurrency limit of **10 concurrent executions** (`AccountLimit.ConcurrentExecutions = 10`) under a 50 req/sec step arrival.
  - Following container warm-up, the system achieved a **100% success rate across 2,568 consecutive requests** for the remainder of the test.
- *Detailed Evidence*: [Deliverable 5 Load Test Report](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-test-report.md).

---

## 9. Six Required Internship Deliverables

All six deliverables have been completed, audited, and indexed in [`docs/evidence/README.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/README.md):

| Deliverable | Key Artifact File | Description & Demonstrated Competency | Status |
|---|---|---|---|
| **1. CloudWatch Dashboard** | [`01_cloudwatch_portfolio_dashboard.png`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01_cloudwatch_portfolio_dashboard.png) | Unified operational dashboard (`internship-portfolio-overview-dev`) covering all 4 projects across alarms, compute, APIs, and databases. | **COMPLETE** |
| **2. IAM Comparison** | [`iam-comparison-project4-resume-screener.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project4-resume-screener.md) | Evidence-based before/after policy audits for each project (4 total), documenting least-privilege scoping and zero wildcards. | **COMPLETE** |
| **3. Cost Estimation** | [`cost-estimation-3-tier-all-projects.xlsx`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.xlsx) | 7-sheet Excel workbook and report analyzing monthly cloud spend across 3 scaling tiers in `ap-south-1`. | **COMPLETE** |
| **4. CI/CD Demonstration** | [`ci-cd-pipeline-demo.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md) | GitHub Actions OIDC pipeline (Run `37216166088`) executing Build $\to$ Test $\to$ Deploy $\to$ Verify end-to-end. | **COMPLETE** |
| **5. Load Test Report** | [`load-test-report.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-test-report.md) | Measured Artillery load test report (3,000 requests at 50 req/s, p50 = 47ms, p95 = 73ms, concurrency analysis). | **COMPLETE** |
| **6. Operations Runbooks** | [`runbook-project4-resume-screener.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project4-resume-screener.md) | Practical one-page operational runbooks for each project (4 total) with CLI health checks, diagnostics, and recovery trees. | **COMPLETE** |

---

## 10. Repository Structure

```text
.
├── backend/                  # Lambda function handlers, NLP extractors, schemas, and layers
│   ├── functions/            # 14 serverless function implementations
│   └── layers/               # Shared common dependencies and utilities
├── frontend/                 # React 18 / Vite recruiter web dashboard application
├── infra/                    # Architecture documentation and infrastructure specifications
├── docs/                     # Engineering design specifications and deliverables
│   └── evidence/             # The Six Portfolio Deliverables and audit artifacts
├── tests/                    # Unit, component, and frontend test suites
│   ├── unit/                 # 282 unit tests
│   ├── component/            # 157 component tests
│   └── fixtures/             # Evaluation datasets, sample resumes, and job descriptions
├── scripts/                  # Operational, testing, and evaluation utility scripts
├── template.yaml             # Primary AWS SAM / CloudFormation infrastructure specification
├── samconfig.toml            # SAM CLI deployment parameters and environment configuration
├── Makefile                  # Local automation targets for linting, testing, and building
└── .github/                  # GitHub Actions CI/CD workflows
    └── workflows/
        └── deploy.yml        # Enterprise two-tier OIDC deployment pipeline
```

---

## 11. Local Development & Deployment

### Prerequisites
- Python 3.12 & virtual environment (`.venv`)
- Node.js v20+ & npm
- Docker Desktop or Colima (for container Lambda compilation)
- AWS CLI v2 configured for `ap-south-1`
- AWS SAM CLI v1.120+

### Local Testing & Quality Gates
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run unit tests
pytest tests/unit/ -v

# 3. Run component tests (requires Tesseract and spaCy)
pytest tests/component/ -v

# 4. Run frontend tests
cd frontend && npm test -- --run && cd ..

# 5. Build SAM application with container compilation
sam build --use-container
```

### Production Deployment
Production deployments are fully automated through GitHub Actions. Pushing to `main` executes the hardened two-tier OIDC pipeline:
```bash
git push origin main
```
For manual break-glass deployment using authenticated AWS credentials:
```bash
sam deploy --config-file samconfig.toml --role-arn arn:aws:iam::331262815638:role/resume-screener-cloudformation-execution
```

---

## 12. Further Documentation & Verification

- **Evidence Manifest & Deliverables Index**: [`docs/evidence/README.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/README.md)
- **CI/CD Evidence & 10-Attempt Audit History**: [`docs/evidence/ci-cd-pipeline-demo.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md)
- **3-Tier Cost Estimation Report**: [`docs/evidence/cost-estimation-3-tier-all-projects.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.md)
- **Artillery Load Test Report**: [`docs/evidence/load-test-report.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-test-report.md)
- **Project Runbooks**:
  - [Project 1 Runbook (DocVault / CloudGuard)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project1-cloudguard.md)
  - [Project 2 Runbook (VEYRA Onboarding)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project2-veyra-onboarding.md)
  - [Project 3 Runbook (Smart Leave)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project3-smart-leave.md)
  - [Project 4 Runbook (Resume Screener)](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project4-resume-screener.md)
