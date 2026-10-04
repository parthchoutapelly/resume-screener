# Operations Runbook — Project 4: AI-Powered Resume Screener Pipeline

## 1. Purpose
The AI-Powered Resume Screener Pipeline (`resume-screener-dev`) automates candidate resume ingestion, OCR document parsing, explainable NLP skill and experience scoring, recruiter candidate evaluation, and automated notifications within a zero-trust multi-tenant architecture.

## 2. Architecture / Components
- **Frontend & CDN**: Amazon CloudFront (`https://d1yg427uu45noj.cloudfront.net`, Origin Access Control) backed by S3 Web Bucket.
- **API Ingress**: Amazon API Gateway (REST API `rs-api-dev`, Stage `dev`, Cognito Authorizer, `ApiGatewayCloudWatchRole`).
- **Identity & Access**: Amazon Cognito User Pool (Recruiter user authentication), GitHub Actions OIDC.
- **Object Storage**: Amazon S3 (`UploadBucket`, SSE-S3, Versioning Enabled, functional prefix isolation).
- **Asynchronous Queues**: Amazon SQS (`IngestionQueue`, `ScoringQueue`, `IngestionDlq`, `ScoringDlq`).
- **Compute**: 14 AWS Lambda functions (including 2 custom container Lambdas for Tesseract OCR and spaCy NLP) with shared `CommonLayer`.
- **Datastores**: Amazon DynamoDB (`JobsTable`, `CandidatesTable`, `FailedJobsTable`, `ConfigTable`, On-Demand, PITR Enabled).
- **Notifications & Alerts**: Amazon SES (Verified sender identity), Amazon SNS (`rs-alerts-dev`).

## 3. Normal Operation
- CloudFormation stack `resume-screener-dev` in `UPDATE_COMPLETE` or `CREATE_COMPLETE`.
- CloudFront frontend returns `HTTP 200` at `https://d1yg427uu45noj.cloudfront.net`.
- SQS queues `rs-ingestion-dev` and `rs-scoring-dev` maintain near-zero message backlogs during idle periods.
- Dead Letter Queues (`rs-ingestion-dlq-dev`, `rs-scoring-dlq-dev`) have **0 visible messages**.
- Candidate resumes progress from `processing` $\to$ `scoring` $\to$ `scored` in under 40 seconds (native PDF) or ~60 seconds (scanned PDF requiring OCR).

## 4. Key Health Checks

```bash
# 1. Verify CloudFormation Stack State & Execution Role
aws cloudformation describe-stacks --stack-name resume-screener-dev --region ap-south-1 \
  --query "Stacks[0].[StackName,StackStatus,RoleARN]" --output table

# 2. Check CloudFront Frontend Availability
curl -sS -o /dev/null -w "CloudFront HTTP Status: %{http_code}\n" https://d1yg427uu45noj.cloudfront.net

# 3. Check SQS Pipeline Queues and Dead Letter Queues
for q in rs-ingestion-dev rs-scoring-dev rs-ingestion-dlq-dev rs-scoring-dlq-dev; do
  echo -n "$q: "
  aws sqs get-queue-attributes --queue-url https://sqs.ap-south-1.amazonaws.com/331262815638/$q \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --region ap-south-1 \
    --query "Attributes" --output json | tr -d '\n' && echo ""
done

# 4. Check DynamoDB Point-in-Time Recovery Status
for t in jobs-dev candidates-dev failed_jobs-dev config-dev; do
  echo -n "$t PITR: "
  aws dynamodb describe-continuous-backups --table-name $t --region ap-south-1 \
    --query "ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus" --output text
done

# 5. Check Active CloudWatch Alarms
aws cloudwatch describe-alarms --alarm-name-prefix "rs-" --state-value ALARM --region ap-south-1
```

## 5. Common Failure Scenarios

| Symptom | Likely Cause | First Diagnostic Step | Safe Recovery Action |
|---|---|---|---|
| **Candidate stuck in `processing` state** | Unhandled document parsing failure, corrupt image, or OCR memory allocation limit reached. | Query `failed_jobs-dev` table for matching `job_id` and `candidate_id` to inspect error payload. | If temporary failure occurred, DLQ handler logs failure to DynamoDB; candidate is marked `error/processing_failed`. Recruiter can delete row or re-upload. |
| **Visible messages detected in DLQ (`IngestionDlq` or `ScoringDlq`)** | Repeated processing failures exceeded SQS max receive count (`maxReceiveCount = 3`). | Check CloudWatch alarm `rs-dlq-alarm-dev` and inspect messages in DLQ via AWS SQS console. | Run `DlqHandlerFunction` to drain messages into `failed_jobs-dev` audit table. Fix underlying issue (e.g. dictionary gap) and re-trigger scoring. |
| **Recruiter API returns HTTP 401 Unauthorized** | Cognito ID/access token expired (1-hour validity) or client missing Bearer prefix. | Inspect browser developer network tab for `Authorization: Bearer <token>` header. | Re-authenticate through Cognito user pool login interface to obtain a fresh JWT token. |
| **S3 Presigned upload fails with HTTP 403 Forbidden** | Client attempting to upload file with unsupported extension or outside `/resume-uploads/*`. | Verify presigned POST parameters returned by `AddResumesFunction`. | Ensure uploaded file matches allowed extensions (`.pdf`, `.docx`, `.png`, `.jpg`) and key matches presigned contract. |
| **Shortlist notification not received by candidate** | SES sandbox mode active and candidate email is not verified, or sender address mismatch. | Check CloudWatch logs for `UpdateCandidateDecisionFunction` for `MessageRejected` error. | Ensure candidate email is verified in SES console if running in sandbox mode, or request AWS SES production access. |

## 6. Security Checks
- **GitHub Actions OIDC Trust**: Assert trust policy on `resume-screener-github-actions-deploy` contains exact immutable subject: `repo:parthchoutapelly@143930644/resume-screener@1383681742:ref:refs/heads/main`.
- **CloudFormation Service Execution Role**: Verify `resume-screener-cloudformation-execution` is the only role with stack mutation authority.
- **S3 Functional Prefix Isolation**: Confirm `AddResumesFunction` cannot write to `/jd-uploads/*`, and `GetResumeUrlFunction` cannot access `/exports/*`.
- **CloudFront OAC Enforcement**: Confirm `WebBucketPolicy` denies non-CloudFront requests and rejects unencrypted HTTP (`aws:SecureTransport == false`).
- **IAM Access Analyzer**: Assert policy validation returns 0 errors across all deployment and execution roles.

## 7. Deployment / Rollback
- **Automated CI/CD**: Pushing a commit to `main` triggers GitHub Actions workflow `.github/workflows/deploy.yml`:
  1. `build`: Compiles containers and packages artifacts with SAM CLI.
  2. `test`: Runs 453 unit, component, and frontend tests.
  3. `deploy`: Authenticates via OIDC and deploys stack using `resume-screener-cloudformation-execution`.
  4. `verify`: Asserts `UPDATE_COMPLETE`, verifies `RoleARN`, and checks CloudFront HTTP 200.
- **Rollback**: CloudFormation rollback on deployment failure (`UPDATE_ROLLBACK_COMPLETE`). For application rollbacks, revert the git commit on `main`.

## 8. Escalation & Evidence
- **CloudWatch Dashboard**: Inspect `internship-portfolio-overview-dev` (Widgets 10 & 11 for API Gateway calls, SQS queue depth, and terminal failures).
- **Log Groups**:
  - API Gateway: `/aws/apigateway/rs-api-dev`
  - Container OCR/NLP: `/aws/lambda/rs-extraction-dev`, `/aws/lambda/rs-nlp-dev`
  - Scoring Engine: `/aws/lambda/rs-scorematch-dev`
- **CI/CD Evidence**: Check [ci-cd-pipeline-demo.md](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/ci-cd-pipeline-demo.md) for full pipeline audit history and run records.
