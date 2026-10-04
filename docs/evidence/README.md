# AWS Internship Portfolio — Evidence Artifacts & Deliverables Index

This directory contains the verified audit evidence and technical artifacts for the **Six Required Deliverables** of the four-project AWS serverless internship portfolio.

---

## Portfolio Deliverables Index

### Deliverable 1 — CloudWatch Portfolio Dashboard
- **Artifacts**:
  - Full Overview: [`01_cloudwatch_portfolio_dashboard.png`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01_cloudwatch_portfolio_dashboard.png)
  - Top Half (Alarms & Projects 1–2): [`01a_portfolio_overview_top.png`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01a_portfolio_overview_top.png)
  - Bottom Half (Projects 3–4 & Reliability): [`01b_portfolio_overview_bottom.png`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/01b_portfolio_overview_bottom.png)
- **Deployed Dashboard**: `internship-portfolio-overview-dev` (`ap-south-1`)
- **Demonstrates**: Unified cross-project observability across all 4 applications, tracking critical alarms, API Gateway traffic, Lambda compute health, DynamoDB throughput, asynchronous queues, and security authorization rejections.
- **Status**: **Complete**

---

### Deliverable 2 — IAM Before/After Policy Comparison
- **Artifacts**:
  - Project 1 (CloudGuard / DocVault): [`iam-comparison-project1-cloudguard-docvault.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project1-cloudguard-docvault.md)
  - Project 2 (VEYRA Onboarding): [`iam-comparison-project2-veyra-onboarding.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project2-veyra-onboarding.md)
  - Project 3 (Smart Leave): [`iam-comparison-project3-smart-leave.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project3-smart-leave.md)
  - Project 4 (Resume Screener): [`iam-comparison-project4-resume-screener.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/iam-comparison-project4-resume-screener.md)
- **Demonstrates**: Rigorous, evidence-based comparative audits of historical versus hardened IAM policies across all 4 projects. Documents the elimination of wildcard resources, strict functional S3 prefix isolation, condition-scoped SES sending, and separates IAM changes from CDN/database resilience configurations.
- **Status**: **Complete**

---

### Deliverable 3 — Cost Estimation Sheet (3-Tier Scaling Analysis)
- **Artifacts**:
  - Primary Excel Model: [`cost-estimation-3-tier-all-projects.xlsx`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.xlsx)
  - Comprehensive Report: [`cost-estimation-3-tier-all-projects.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/cost-estimation-3-tier-all-projects.md)
- **Workbook Sheets**: `Executive Summary`, `Project 1 - CloudGuard`, `Project 2 - VEYRA`, `Project 3 - Smart Leave`, `Project 4 - Resume Screener`, `Pricing Sources`, `Assumptions`.
- **Demonstrates**: Transparent gross list-price monthly cost modeling across three realistic scaling tiers (Tier 1: Dev/Low, Tier 2: Moderate/Team, Tier 3: High Scale) in `ap-south-1`. Explicitly documents the active deployed baseline using Cognito Essentials ($120.55/mo T2 / $2,521.99/mo T3) and compares it with the Cognito Lite architectural optimization scenario ($45.55/mo T2 / $971.99/mo T3).
- **Status**: **Complete**

---

### Deliverable 4 — Secure CI/CD Pipeline Demonstration
- **Artifact**: [`ci-cd-pipeline-demo.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md)
- **GitHub Actions Workflow**: `.github/workflows/deploy.yml` (Run `37216166088`)
- **Demonstrates**: Two-tier least-privilege CI/CD deployment using GitHub Actions OIDC without long-lived credentials. Details the progressive hardening journey across 10 discrete attempts and documents the final end-to-end successful run where all 4 stages (`BUILD` $\to$ `TEST` $\to$ `DEPLOY` $\to$ `VERIFY`) passed with final `UPDATE_COMPLETE` status, verified execution RoleARN, and CloudFront HTTP 200 availability.
- **Status**: **Complete**

---

### Deliverable 5 — Artillery Load Test Report
- **Artifact**: [`load-test-report.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-test-report.md)
- **Tooling**: Artillery Core (`v2.0.21`) against deployed API Gateway (`onboarding-service-dev`)
- **Demonstrates**: Empirical performance under sustained 50 req/sec load (3,000 requests), capturing exact latency metrics (p50 = 47.0 ms, p95 = 73.0 ms, p99 = 111.1 ms), CloudWatch correlation demonstrating how a regional Lambda account limit of 10 caused 53 burst-phase throttles in the opening 8.8s, and proof of 100% steady-state recovery across 2,568 subsequent requests.
- **Status**: **Complete**

---

### Deliverable 6 — One-Page Operations Runbooks
- **Artifacts**:
  - Project 1 (CloudGuard / DocVault): [`runbook-project1-cloudguard.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project1-cloudguard.md)
  - Project 2 (VEYRA Onboarding): [`runbook-project2-veyra-onboarding.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project2-veyra-onboarding.md)
  - Project 3 (Smart Leave): [`runbook-project3-smart-leave.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project3-smart-leave.md)
  - Project 4 (Resume Screener): [`runbook-project4-resume-screener.md`](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/runbook-project4-resume-screener.md)
- **Demonstrates**: Practical, one-page operational runbooks for each of the four projects detailing architecture components, normal operating thresholds, critical health check commands, failure diagnostics, security boundary verification, and rollback procedures.
- **Status**: **Complete**

---

## Supporting Project 4 Technical Evidence Files

In addition to the six portfolio deliverables above, this directory preserves the internal test evidence files generated during the implementation of Project 4 (Resume Screener):
- `load-readiness.md` & `load-2026-09-25.md`: 50-resume scale load testing readiness and concurrency assessment.
- `failure-matrix.json`: Automated evaluation of failure scenarios F1–F13.
- `security-checklist.md`: Live security control audit (S1–S15).
- `a11y.md` & `a11y-browser.json`: Accessibility evaluation across 5 frontend screens.
- `nlp-skill-error-analysis.md`: Detailed skill matching and NLP parsing precision analysis.
