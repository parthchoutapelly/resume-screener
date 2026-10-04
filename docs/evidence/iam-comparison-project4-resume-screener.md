# IAM Before/After Policy Comparison — Project 4: AI-Powered Resume Screener Pipeline

## Executive Summary
This document provides a verified, evidence-based audit of IAM and resource policies in the **AI-Powered Resume Screener Pipeline** (`resume-screener-dev`). By inspecting repository git history across commits `6b9c4cf`, `fe09761`, `69e5d86`, `2843025`, `d6eab6f`, `af16ad2`, and `ff6911c`, this audit validates the authorization model across all 14 serverless functions, the API Gateway service execution role, CloudFront Origin Access Control, and CloudWatch Log Group resource policies.

A key finding of this audit is that runtime Lambda functions in this repository were codified with granular, resource-scoped least privilege from their inception (e.g., S3 functional prefixes, table-specific DynamoDB actions, and SES identity conditions). Furthermore, `ApiGatewayCloudWatchRole` was newly introduced in commit `af16ad2` to eliminate CloudFormation drift on access log delivery rather than as a reduction of an existing overly broad role.

---

## Runtime Roles

The pipeline architecture defines **14 Lambda functions** (with SAM-managed least-privilege execution roles) and **1 dedicated API Gateway service role**.

| Role / Function | Service Type | Inception / Historical State | Hardened Current State (Commit `ff6911c`) |
|---|---|---|---|
| `ApiGatewayCloudWatchRole` | IAM Role (`apigateway.amazonaws.com`) | Did not exist in template (commits `6b9c4cf`–`d6eab6f`); relied on unmanaged account default | **Newly provisioned in commit `af16ad2`**: Managed policy `AmazonAPIGatewayPushToCloudWatchLogs` linked via `AWS::ApiGateway::Account` |
| `ExtractionFunctionRole` | Lambda (`ExtractionFunction`) | Commit `fe09761`: Scoped to `jd-uploads/*` & `resume-uploads/*` | Unchanged: Retains strict S3 prefix scoping, table-specific updates, and `lambda:InvokeFunction` on `NlpFunction` |
| `NlpFunctionRole` | Lambda (`NlpFunction`) | Commit `fe09761`: Scoped DynamoDB updates/queries and SQS send | Retains scoped `dynamodb:UpdateItem` (Jobs/Candidates), `GetItem` (Config), and `sqs:SendMessage` (ScoringQueue) |
| `ScoreMatchFunctionRole` | Lambda (`ScoreMatchFunction`) | Commit `69e5d86`: Scoped DynamoDB reads (Jobs) and writes (Candidates/FailedJobs) | Unchanged: Read-only `dynamodb:GetItem` (Jobs), `UpdateItem` (Candidates), `PutItem` (FailedJobs) |
| `CreateJobPostingFunctionRole` | Lambda (`CreateJobPostingFunction`) | Commit `69e5d86`: Scoped DDB writes, S3 presigned upload on `jd-uploads/*` and `resume-uploads/*` | Unchanged: Scoped `dynamodb:PutItem`/`BatchWriteItem` and S3 `s3:PutObject` strictly on functional upload prefixes |
| `AddResumesFunctionRole` | Lambda (`AddResumesFunction`) | Commit `69e5d86`: Scoped `s3:PutObject` on `resume-uploads/*`, scoped DDB writes | Unchanged: Strictly restricted to `resume-uploads/*` (disallows JD uploads), scoped table writes |
| `GetJobsFunctionRole` | Lambda (`GetJobsFunction`) | Commit `69e5d86`: Scoped `dynamodb:Query`/`Scan` on `JobsTable` and GSI | Unchanged: Restricted to `JobsTable` and `RecruiterJobsIndex` |
| `GetJobFunctionRole` | Lambda (`GetJobFunction`) | Commit `69e5d86`: Scoped `dynamodb:GetItem` on `JobsTable` | Unchanged: Read-only single-item retrieval on `JobsTable` |
| `UpdateJobFunctionRole` | Lambda (`UpdateJobFunction`) | Commit `69e5d86`: Scoped `dynamodb:UpdateItem`, `sqs:SendMessage` on ScoringQueue | Unchanged: Scoped job updates, candidate query, and scoring re-triggering via SQS |
| `GetCandidatesByJobFunctionRole` | Lambda (`GetCandidatesByJobFunction`) | Commit `69e5d86`: Scoped `dynamodb:GetItem` (Jobs), `Query` (Candidates) | Unchanged: Strictly read-only candidate evaluation queries |
| `UpdateCandidateDecisionFunctionRole` | Lambda (`UpdateCandidateDecisionFunction`) | Commit `69e5d86`: Scoped DDB updates, `ses:SendEmail` with FromAddress condition | Unchanged: Scoped DDB updates, `ses:SendEmail` on identity ARN restricted by `ses:FromAddress: !Ref SesSenderAddress` |
| `GetResumeUrlFunctionRole` | Lambda (`GetResumeUrlFunction`) | Commit `69e5d86`: Scoped `s3:GetObject` on `resume-uploads/*` | Unchanged: Restricted exclusively to generating presigned download URLs for `resume-uploads/*` |
| `ExportShortlistCsvFunctionRole` | Lambda (`ExportShortlistCsvFunction`) | Commit `69e5d86`: Scoped `s3:PutObject`/`GetObject` on `exports/*` | Unchanged: Scoped exclusively to the `exports/*` prefix for candidate shortlist CSVs |
| `GetFailedJobsFunctionRole` | Lambda (`GetFailedJobsFunction`) | Commit `69e5d86`: Scoped `dynamodb:Query`/`Scan` on `FailedJobsTable` | Unchanged: Confined strictly to failed job audit records |
| `DlqHandlerFunctionRole` | Lambda (`DlqHandlerFunction`) | Commit `69e5d86`: Scoped `dynamodb:UpdateItem`/`PutItem` on terminal states | Unchanged: Drains SQS DLQs directly into `FailedJobsTable` and terminal candidate statuses |

---

## Policy-by-Policy Comparison

### 1. ApiGatewayCloudWatchRole & ApiGatewayAccount — Access Log Service Role Provisioning

**BEFORE — source**
- **Commit**: `6b9c4cf` through `d6eab6f`
- **File**: `template.yaml`
- **Exact policy scope**:
```text
No dedicated API Gateway CloudWatch execution role was provisioned in the template. API Gateway defaulted to an unmanaged or pre-existing account role, which caused persistent CloudFormation drift on RecruiterApiStage access-log destination ARN normalization.
```

**AFTER — source**
- **Commit**: `af16ad2`
- **File**: `template.yaml` (Lines 642–659)
- **Exact policy scope**:
```yaml
ApiGatewayCloudWatchRole:
  Type: AWS::IAM::Role
  Properties:
    RoleName: !Sub "rs-apigateway-cw-role-${EnvName}"
    AssumeRolePolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            Service: apigateway.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs

ApiGatewayAccount:
  Type: AWS::ApiGateway::Account
  Properties:
    CloudWatchRoleArn: !GetAtt ApiGatewayCloudWatchRole.Arn
```

**Analysis & Justification**
- **Nature of change**: Newly introduced role and account configuration (not a reduction from an existing overly broad role).
- **Actions/resources affected**: Grants `apigateway.amazonaws.com` the managed policy `AmazonAPIGatewayPushToCloudWatchLogs` (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams`, `logs:PutLogEvents`, `logs:GetLogEvents`, `logs:FilterLogEvents`).
- **Security justification**: Establishes an explicit, stack-owned IAM execution identity for API Gateway access logging, ensuring compliance with audit trail standards and completely resolving CloudFormation drift on `AWS::ApiGateway::Stage`.

---

### 2. ApiAccessLogsResourcePolicy — CloudWatch Log Group Resource Policy

**BEFORE — source**
- **Commit**: `6b9c4cf` through `e5fb0f9`
- **File**: `template.yaml`
- **Exact policy scope**: No resource policy was defined on API Gateway CloudWatch log group.

**AFTER — source**
- **Commit**: `d6eab6f`
- **File**: `template.yaml` (Lines 622–640)
- **Exact policy scope**:
```yaml
ApiAccessLogsResourcePolicy:
  Type: AWS::Logs::ResourcePolicy
  Properties:
    PolicyName: !Sub "rs-api-access-logs-policy-${EnvName}"
    PolicyDocument: !Sub |
      {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Principal": {
              "Service": "apigateway.amazonaws.com"
            },
            "Action": [
              "logs:CreateLogStream",
              "logs:PutLogEvents"
            ],
            "Resource": "${ApiAccessLogGroup.Arn}:*"
          }
        ]
      }
```

**Analysis & Justification**
- **Nature of change**: Permissions added.
- **Actions/resources affected**: Explicitly grants `apigateway.amazonaws.com` permission to create log streams and push log events exclusively into `${ApiAccessLogGroup.Arn}:*`.
- **Security justification**: Adheres to AWS least privilege by confining log delivery permissions strictly to the designated API Gateway access log group.

---

### 3. ExtractionFunctionRole — Document Ingestion & S3 Object Read Scoping

**BEFORE — source**
- **Commit**: `fe09761` (Phase 2 inception)
- **File**: `template.yaml` (Lines 354–367)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action: s3:GetObject
        Resource:
          - !Sub "${UploadBucket.Arn}/jd-uploads/*"
          - !Sub "${UploadBucket.Arn}/resume-uploads/*"
      - Effect: Allow
        Action: dynamodb:UpdateItem
        Resource: [!GetAtt JobsTable.Arn, !GetAtt CandidatesTable.Arn]
      - Effect: Allow
        Action: dynamodb:PutItem
        Resource: !GetAtt FailedJobsTable.Arn
      - Effect: Allow
        Action: lambda:InvokeFunction
        Resource: !GetAtt NlpFunction.Arn
```

**AFTER — source**
- **Commit**: `ff6911c`
- **File**: `template.yaml` (Lines 486–500)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action: s3:GetObject
        Resource:
          - !Sub "${UploadBucket.Arn}/jd-uploads/*"
          - !Sub "${UploadBucket.Arn}/resume-uploads/*"
      - Effect: Allow
        Action: dynamodb:UpdateItem
        Resource: [!GetAtt JobsTable.Arn, !GetAtt CandidatesTable.Arn]
      - Effect: Allow
        Action: dynamodb:PutItem
        Resource: !GetAtt FailedJobsTable.Arn
      - Effect: Allow
        Action: lambda:InvokeFunction
        Resource: !GetAtt NlpFunction.Arn
```

**Analysis & Justification**
- **Nature of change**: Granular least privilege enforced from inception.
- **Actions/resources affected**: Repository history confirms that `ExtractionFunction` **never** contained a bucket wildcard (`${UploadBucket.Arn}/*`). It was authored from inception in commit `fe09761` with prefix-restricted access to `jd-uploads/*` and `resume-uploads/*`.
- **Security justification**: Ensures extraction worker can read candidate resumes and job descriptions without possessing access to generated candidate exports (`exports/*`) or static frontend assets.

---

### 4. UpdateCandidateDecisionFunctionRole — SES Sender Identity & FromAddress Scoping

**BEFORE & CURRENT — source**
- **Commit**: `69e5d86` through `ff6911c`
- **File**: `template.yaml` (Lines 934–948)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action: dynamodb:GetItem
        Resource: !GetAtt JobsTable.Arn
      - Effect: Allow
        Action: [dynamodb:GetItem, dynamodb:UpdateItem]
        Resource: !GetAtt CandidatesTable.Arn
      - Effect: Allow
        Action: dynamodb:PutItem
        Resource: !GetAtt FailedJobsTable.Arn
      - Effect: Allow
        Action: ses:SendEmail
        # In SES sandbox the recipient identity is also authorized, so the resource is
        # account-scoped; the FromAddress condition is the tight control (docs/03 §9).
        Resource: !Sub "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/*"
        Condition:
          StringEquals:
            "ses:FromAddress": !Ref SesSenderAddress
```

**Analysis & Justification**
- **Nature of change**: Cryptographic and condition-scoped authorization from inception.
- **Actions/resources affected**: Restricts `ses:SendEmail` within the deploying account and region, guarded by an IAM Condition enforcing that `ses:FromAddress` must equal `!Ref SesSenderAddress` (configured sender address).
- **Security justification**: In SES sandbox mode where recipient identities require authorization, account-level identity scoping combined with the `ses:FromAddress` condition provides the tightest possible least-privilege boundary against sender spoofing.

---

### 5. S3 Functional Prefix Isolation Across Storage & Export Endpoints

**Implementation Analysis Across Commits `69e5d86` through `ff6911c`**
- **`CreateJobPostingFunctionRole`** (Lines 726–731):
  ```yaml
  Action: s3:PutObject
  Resource:
    - !Sub "${UploadBucket.Arn}/jd-uploads/*"
    - !Sub "${UploadBucket.Arn}/resume-uploads/*"
  ```
  *Isolation*: Authorized to generate upload presigned URLs only for job postings and initial resumes.
- **`AddResumesFunctionRole`** (Lines 767–769):
  ```yaml
  Action: s3:PutObject
  Resource: !Sub "${UploadBucket.Arn}/resume-uploads/*"
  ```
  *Isolation*: Strictly confined to `/resume-uploads/*`. Disallows modifying job descriptions.
- **`GetResumeUrlFunctionRole`** (Lines 980–982):
  ```yaml
  Action: s3:GetObject
  Resource: !Sub "${UploadBucket.Arn}/resume-uploads/*"
  ```
  *Isolation*: Strictly confined to generating presigned download URLs for candidate resumes.
- **`ExportShortlistCsvFunctionRole`** (Lines 1017–1020):
  ```yaml
  Action: [s3:PutObject, s3:GetObject]
  Resource: !Sub "${UploadBucket.Arn}/exports/*"
  ```
  *Isolation*: Strictly confined to writing and reading candidate shortlist CSVs under `/exports/*`.

---

## Infrastructure & CDN Policies (Separated from IAM Hardening)
- **CloudFront Origin Access Control (OAC)**: Implemented in commit `2843025` (`Phase 4: add frontend dashboard and production deployment`). `WebBucketPolicy` restricts `s3:GetObject` to `cloudfront.amazonaws.com` matching the distribution ARN condition `AWS:SourceArn: !Sub "arn:aws:cloudfront::${AWS::AccountId}:distribution/${WebDistribution}"`, along with an explicit `DenyInsecureTransport` statement. This was an architectural design choice of Phase 4 frontend provisioning rather than an IAM hardening sprint modification.
- **S3 Versioning & Lifecycle Retention**: Codified in commit `ff6911c` (Phase 3 hardening). `UploadBucket` has `VersioningConfiguration: Status: Enabled`, 180-day retention on uploads, 7-day retention on `/exports/*`, and 30-day noncurrent version expiration.
- **DynamoDB Point-in-Time Recovery & Deletion Protection**: Codified across all 4 DynamoDB tables (`JobsTable`, `CandidatesTable`, `FailedJobsTable`, `ConfigTable`) in commit `ff6911c`.
