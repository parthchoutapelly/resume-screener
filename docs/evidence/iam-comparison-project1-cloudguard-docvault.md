# IAM Before/After Policy Comparison — Project 1: AWS Cloud Security Analyzer / Employee Document Vault (docvault)

## Executive Summary
This document provides an evidence-based audit of IAM policies in the **Employee Document Vault** (`docvault`) project. By comparing historical commit `5f2affe` against hardened commit `a9e2984` in `infra/template.yaml`, this audit verifies the elimination of S3 wildcard object paths, the introduction of active AWS X-Ray tracing permissions, and the exact scope of runtime database and object access.

---

## Runtime Roles

| Role | Service / Function | Historical State (Commit `5f2affe`) | Hardened State (Commit `a9e2984`) |
|---|---|---|---|
| `UploadFunctionRole` | Lambda (`UploadFunction`) | Broad S3 object write access (`${DocumentsBucket}/*`) | Narrowed to `${DocumentsBucket}/documents/*` + AWSXrayWriteOnlyAccess |
| `DownloadFunctionRole` | Lambda (`DownloadFunction`) | Broad S3 object read access (`${DocumentsBucket}/*`) | Narrowed to `${DocumentsBucket}/documents/*` + AWSXrayWriteOnlyAccess |
| `DeleteFunctionRole` | Lambda (`DeleteFunction`) | Broad S3 object delete access (`${DocumentsBucket}/*`) | Narrowed to `${DocumentsBucket}/documents/*` + AWSXrayWriteOnlyAccess |
| `ListFilesFunctionRole` | Lambda (`ListFilesFunction`) | Scoped DynamoDB queries on `DocumentsTable` / GSIs | DynamoDB policy unchanged; added AWSXrayWriteOnlyAccess |
| `UpdateTagsFunctionRole` | Lambda (`UpdateTagsFunction`) | Scoped `dynamodb:UpdateItem` on `DocumentsTable` | DynamoDB policy unchanged; added AWSXrayWriteOnlyAccess |
| `VersionsFunctionRole` | Lambda (`VersionsFunction`) | Scoped DynamoDB queries on `DocumentsTable` | DynamoDB policy unchanged; added AWSXrayWriteOnlyAccess |
| `ActivityFunctionRole` | Lambda (`ActivityFunction`) | Scoped `dynamodb:Scan`/`Query` on `AuditLogTable` | DynamoDB policy unchanged; added AWSXrayWriteOnlyAccess |

---

## Policy-by-Policy Comparison

### 1. UploadFunctionRole — S3 Document Upload Permission

**BEFORE — source**
- **Commit**: `5f2affe`
- **File**: `infra/template.yaml` (Lines 571–576)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Upload
  Effect: Allow
  Action:
    - s3:PutObject
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/*"
```

**AFTER — source**
- **Commit**: `a9e2984`
- **File**: `infra/template.yaml` (Lines 582–587)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Upload
  Effect: Allow
  Action:
    - s3:PutObject
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/documents/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed.
- **Actions/resources affected**: `s3:PutObject` restricted from bucket root wildcard (`/*`) to designated subfolder (`/documents/*`).
- **Security justification**: Employee documents follow the mandatory key convention `documents/{employee_id}/{document_type}/{filename}`. Restricting presigned upload signatures to `/documents/*` prevents clients from overwriting root-level bucket configurations or writing into unauthorized prefixes.

---

### 2. DownloadFunctionRole — S3 Document Download Permission

**BEFORE — source**
- **Commit**: `5f2affe`
- **File**: `infra/template.yaml` (Lines 675–681)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Download
  Effect: Allow
  Action:
    - s3:GetObject
    - s3:GetObjectVersion
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/*"
```

**AFTER — source**
- **Commit**: `a9e2984`
- **File**: `infra/template.yaml` (Lines 686–692)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Download
  Effect: Allow
  Action:
    - s3:GetObject
    - s3:GetObjectVersion
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/documents/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed.
- **Actions/resources affected**: `s3:GetObject` and `s3:GetObjectVersion` restricted from `/*` down to `/documents/*`.
- **Security justification**: Prevents presigned GET URL generation from accessing non-document bucket objects, enforcing strict data boundary isolation.

---

### 3. DeleteFunctionRole — S3 Document Deletion Permission

**BEFORE — source**
- **Commit**: `5f2affe`
- **File**: `infra/template.yaml` (Lines 732–737)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Delete
  Effect: Allow
  Action:
    - s3:DeleteObject
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/*"
```

**AFTER — source**
- **Commit**: `a9e2984`
- **File**: `infra/template.yaml` (Lines 743–748)
- **Exact policy scope**:
```yaml
- Sid: DocumentsS3Delete
  Effect: Allow
  Action:
    - s3:DeleteObject
  Resource: !Sub "arn:aws:s3:::${DocumentsBucket}/documents/*"
```

**Analysis & Justification**
- **Nature of change**: Resource narrowed.
- **Actions/resources affected**: `s3:DeleteObject` restricted to `/documents/*`.
- **Security justification**: Confines soft deletion (creation of delete markers in versioned bucket) strictly to employee documents, preventing deletion markers on other prefixes.

---

### 4. Fleetwide AWS X-Ray Tracing Permissions

**BEFORE — source**
- **Commit**: `5f2affe`
- **File**: `infra/template.yaml`
- **Exact policy scope**: No X-Ray tracing configuration existed under `Globals.Function`.

**AFTER — source**
- **Commit**: `a9e2984`
- **File**: `infra/template.yaml` (Lines 18–22)
- **Exact policy scope**:
```yaml
Globals:
  Function:
    Runtime: python3.12
    Timeout: 10
    Tracing: Active
```

**Analysis & Justification**
- **Nature of change**: Permissions added globally.
- **Actions/resources affected**: Enabling `Tracing: Active` causes AWS SAM to automatically attach the AWS-managed policy `arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess` (`xray:PutTraceSegments`, `xray:PutTelemetryRecords`, `xray:GetSamplingRules`, `xray:GetSamplingTargets` on `Resource: "*"`) to all 7 Lambda execution roles.
- **Security justification**: Resource wildcard `*` is an AWS-documented justified exception because the AWS X-Ray ingestion API does not support resource-level permissions.

---

## Least-Privilege Verification & Evidence
- **Repository**: `~/Desktop/employee-document-vault`
- **Git Commit Diff**: Verified via `git diff 5f2affe..a9e2984 -- infra/template.yaml`.
- **DynamoDB Access**: Roles `ListFilesFunctionRole`, `UpdateTagsFunctionRole`, `VersionsFunctionRole`, and `ActivityFunctionRole` already had granular table and GSI ARNs (`DocumentsTable`, `EmployeesTable`, `AuditLogTable`) in commit `5f2affe`. These were verified and left unchanged.
- **KMS Scoping**: `kms:GenerateDataKey*` and `kms:Encrypt` for `UploadFunctionRole`, and `kms:Decrypt` for `DownloadFunctionRole`, remain explicitly bound to `!GetAtt DocVaultKmsKey.Arn`.
- **Observability Configuration (Separated from IAM)**: API Gateway `DataTraceEnabled: false` was set on stage `MethodSettings` to prevent PII and STS tokens from being logged to CloudWatch.
