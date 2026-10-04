# IAM Before/After Policy Comparison — Project 2: Smart Employee Onboarding & Identity Service (VEYRA)

## Executive Summary
This document provides a rigorous, evidence-based audit of IAM policies in the **Smart Employee Onboarding & Identity Service** (`onboarding-service-dev`). By evaluating historical baseline commit `64b0125` against hardened commit `1a3781d` in `template.yaml`, this audit proves the elimination of wildcard Amazon SES resources (`Resource: "*"`), the restriction of Amazon S3 document upload prefixes, the explicit authorization of AWS X-Ray tracing on both Lambda roles and the Step Functions state machine execution role, and the isolation of API Gateway observability configuration from IAM policies.

All 13 Lambda execution roles and the 1 Step Functions service role have been verified directly against repository history and CloudFormation definitions.

---

## Runtime Roles

The service defines **14 total execution roles**: exactly **13 Lambda execution roles** (one per Serverless Function) and **1 Step Functions state machine execution role**.

| Role | Service / Function | Historical State (Commit `64b0125`) | Hardened State (Commit `1a3781d`) |
|---|---|---|---|
| `PlaceholderFunctionRole` | Lambda (`PlaceholderFunction`) | S3 read/write wildcard on bucket root (`${DocumentsBucket.Arn}/*`) | Narrowed to `${DocumentsBucket.Arn}/documents/*` + AWS X-Ray tracing |
| `CreateEmployeeProfileFunctionRole` | Lambda (`CreateEmployeeProfileFunction`) | Scoped `dynamodb:PutItem` on `EmployeeProfileTable`; `states:StartExecution` on state machine | Functional policy unchanged; added `XRayTracingPolicy` |
| `ProvisionCognitoUserFunctionRole` | Lambda (`ProvisionCognitoUserFunction`) | Wildcard SES sending (`Resource: "*"`); scoped DynamoDB access | SES scoped to `arn:aws:ses:${Region}:${AccountId}:identity/*` + `XRayTracingPolicy` |
| `StageDocumentCollectionFunctionRole` | Lambda (`StageDocumentCollectionFunction`) | Scoped `dynamodb:UpdateItem`, `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `StageITProvisioningFunctionRole` | Lambda (`StageITProvisioningFunction`) | Scoped `dynamodb:UpdateItem`, `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `StagePolicySignOffFunctionRole` | Lambda (`StagePolicySignOffFunction`) | Scoped `dynamodb:UpdateItem`, `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `StageManagerIntroFunctionRole` | Lambda (`StageManagerIntroFunction`) | Scoped `dynamodb:UpdateItem`, `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `GetOnboardingStatusFunctionRole` | Lambda (`GetOnboardingStatusFunction`) | Scoped `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `ListOnboardingEmployeesFunctionRole` | Lambda (`ListOnboardingEmployeesFunction`) | Scoped `dynamodb:Scan` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `SendReminderEmailFunctionRole` | Lambda (`SendReminderEmailFunction`) | Wildcard SES sending (`Resource: "*"`); scoped DynamoDB access | SES narrowed to `...:identity/${SesSenderEmail}` + `XRayTracingPolicy` |
| `OnboardingStateMachineRole` | Step Functions (`OnboardingStateMachine`) | Scoped `lambda:InvokeFunction` across the 5 stage Lambdas | Added `XRayTracingPolicy` for Step Functions execution tracing |
| `CheckDocumentCollectionFunctionRole` | Lambda (`CheckDocumentCollectionFunction`) | Scoped `dynamodb:GetItem` on `EmployeeProfileTable` | Functional policy unchanged; added `XRayTracingPolicy` |
| `GetUploadUrlFunctionRole` | Lambda (`GetUploadUrlFunction`) | S3 presigned upload wildcard (`onboarding-documents-${Stage}-${AccountId}/*`) | Narrowed to `.../documents/*` + `XRayTracingPolicy` |
| `ValidateDocumentFunctionRole` | Lambda (`ValidateDocumentFunction`) | Already scoped to `/documents/*`, DynamoDB table, and SNS topic | Functional policies unchanged; added `XRayTracingPolicy` |

---

## Policy-by-Policy Comparison

### 1. SendReminderEmailFunctionRole — SES Sender Identity Scoping

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml` (Lines 688–697)
- **Exact policy scope**:
```yaml
- PolicyName: SESSendReminderPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - ses:SendEmail
          - ses:SendRawEmail
        Resource: "*"
```

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 812–822)
- **Exact policy scope**:
```yaml
# SES resource scoped to exact verified sender identity configured in SesSenderEmail parameter
- PolicyName: SESSendReminderPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - ses:SendEmail
          - ses:SendRawEmail
        Resource: !Sub "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/${SesSenderEmail}"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed from global wildcard (`*`) to the exact verified SES identity ARN.
- **Actions/resources affected**: `ses:SendEmail` and `ses:SendRawEmail` restricted from any sender domain or identity across AWS to `arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/${SesSenderEmail}` (default parameter value: `onboarding-noreply@example.com`).
- **Security justification**: Eliminates email spoofing risks and ensures automated cron reminders can only be dispatched from the authorized, authenticated domain identity.

---

### 2. ProvisionCognitoUserFunctionRole — SES Optional Welcome Email Scoping

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml` (Lines 418–427)
- **Exact policy scope**:
```yaml
- PolicyName: SESOptionalWelcomeEmailPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - ses:SendEmail
          - ses:SendRawEmail
        Resource: "*"
```

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 458–468)
- **Exact policy scope**:
```yaml
# SES resource scoped to verified sender identity; wildcard removed
- PolicyName: SESOptionalWelcomeEmailPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - ses:SendEmail
          - ses:SendRawEmail
        Resource: !Sub "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed from unrestricted wildcard (`*`) to account- and region-scoped SES identities (`arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/*`).
- **Actions/resources affected**: Restricts `ses:SendEmail` and `ses:SendRawEmail` to verified identities within the deploying AWS account and region only.
- **Security justification**: Prevents the Lambda function from attempting to dispatch notifications using external or unverified identities.

---

### 3. GetUploadUrlFunctionRole — S3 Presigned Upload Key Prefix Restriction

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml` (Lines 800–806)
- **Exact policy scope**:
```yaml
- PolicyName: S3PutObjectScopedPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - s3:PutObject
        Resource: !Sub "arn:aws:s3:::onboarding-documents-${Stage}-${AWS::AccountId}/*"
```

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 956–963)
- **Exact policy scope**:
```yaml
- PolicyName: S3PutObjectScopedPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - s3:PutObject
        Resource: !Sub "arn:aws:s3:::onboarding-documents-${Stage}-${AWS::AccountId}/documents/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed.
- **Actions/resources affected**: `s3:PutObject` presigned URL generation restricted from bucket root wildcard (`/*`) to the designated `/documents/*` key path.
- **Security justification**: New hire onboarding uploads are strictly partitioned under `/documents/{employee_id}/{doc_type}`. Scoping the policy prevents clients from obtaining presigned upload URLs targeting the bucket root, static assets, or unintended prefixes.

---

### 4. PlaceholderFunctionRole — S3 Mock Testing Access Scoping

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml` (Lines 312–317)
- **Exact policy scope**:
```yaml
- PolicyName: DocumentsS3AccessPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - s3:GetObject
          - s3:PutObject
        Resource: !Sub "${DocumentsBucket.Arn}/*"
```

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 327–333)
- **Exact policy scope**:
```yaml
- PolicyName: DocumentsS3AccessPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - s3:GetObject
          - s3:PutObject
        Resource: !Sub "${DocumentsBucket.Arn}/documents/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed.
- **Actions/resources affected**: `s3:GetObject` and `s3:PutObject` restricted from `${DocumentsBucket.Arn}/*` down to `${DocumentsBucket.Arn}/documents/*`.
- **Security justification**: Enforces directory isolation even on test/placeholder Lambda functions, eliminating privilege drift across deployment stages.

---

### 5. OnboardingStateMachineRole — Step Functions Distributed Tracing Permissions

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml` (Lines 715–736)
- **Exact policy scope**: No X-Ray tracing policy was attached to the state machine role. Role contained only `InvokeStageLambdaFunctions`.

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 864–877)
- **Exact policy scope**:
```yaml
# Justified wildcard: X-Ray daemon / Step Functions tracing requires these actions; resource cannot be scoped
- PolicyName: XRayTracingPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - xray:PutTraceSegments
          - xray:PutTelemetryRecords
          - xray:GetSamplingRules
          - xray:GetSamplingTargets
        Resource: "*"
```

**Analysis & Justification**
- **Nature of change**: Permissions added.
- **Actions/resources affected**: Allows AWS Step Functions service daemon to push trace segments and telemetry records to AWS X-Ray when executing `OnboardingStateMachine`.
- **Security justification**: Wildcard resource statement (`Resource: "*"`) is an AWS-mandated pattern because the X-Ray telemetry ingestion APIs do not support resource-level ARNs. Step Functions state machine configuration also had `Tracing: Enabled: true` activated (Line 1285).

---

### 6. Fleetwide Lambda AWS X-Ray Tracing Policies

**BEFORE — source**
- **Commit**: `64b0125`
- **File**: `template.yaml`
- **Exact policy scope**: Lambda execution roles lacked inline `XRayTracingPolicy` statements.

**AFTER — source**
- **Commit**: `1a3781d`
- **File**: `template.yaml` (Lines 29, 334–346, 398–410, 469–481, etc.)
- **Exact policy scope**:
```yaml
Globals:
  Function:
    Tracing: Active

# Inline policy added to all 13 Lambda execution roles:
- PolicyName: XRayTracingPolicy
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - xray:PutTraceSegments
          - xray:PutTelemetryRecords
          - xray:GetSamplingRules
          - xray:GetSamplingTargets
        Resource: "*"
```

**Analysis & Justification**
- **Nature of change**: Tracing permissions added to all 13 Lambda execution roles in tandem with `Tracing: Active` in `Globals.Function`.
- **Security justification**: Provides end-to-end distributed transaction tracing without adding extraneous broad AWS-managed policies.

---

## Observability & Governance Boundary (Separated from IAM)
- **API Gateway Tracing & Logging**: In commit `1a3781d` (Lines 48–56), `TracingEnabled: true` and `MethodSettings` with `DataTraceEnabled: false` and `LoggingLevel: 'OFF'` were configured on `onboarding-api-${Stage}`. This prevents sensitive employee PII and Cognito authentication tokens from leaking into CloudWatch Logs, while enabling AWS X-Ray transaction propagation.
- **S3 Bucket Encryption**: `onboarding-frontend-${Stage}-${AWS::AccountId}` had server-side encryption (`AES256`) codified in commit `1a3781d` (Lines 147–151).
- **Existing Scoped Roles Unchanged**: `ValidateDocumentFunctionRole` was verified to already possess strict `/documents/*` S3 scoping and exact `EmployeeProfileTable.Arn` in historical commit `64b0125`. No artificial narrowing was claimed.
