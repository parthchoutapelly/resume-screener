# Operations Runbook — Project 1: AWS Cloud Security Analyzer & Document Vault (CloudGuard ULTRA / DocVault)

## 1. Purpose
The Employee Document Vault (`employee-document-vault-dev`) provides an enterprise-grade, cryptographically secure document repository for sensitive employee records. It enforces zero-trust presigned upload/download authorization, customer-managed AWS KMS encryption, immutable audit logging, and continuous security compliance analysis.

## 2. Architecture / Components
- **API Ingress**: Amazon API Gateway (REST API `employee-document-vault-dev`, Stage `dev`).
- **Compute**: 7 AWS Lambda microservices (`Upload`, `Download`, `Delete`, `ListFiles`, `UpdateTags`, `Versions`, `Activity`) with active AWS X-Ray tracing.
- **Data & Object Storage**: Amazon S3 (`DocumentsBucket`, SSE-KMS, Versioning Enabled, prefix-isolated `/documents/*`), Amazon DynamoDB (`DocumentsTable`, `AuditLogTable`, On-Demand).
- **Security & Encryption**: AWS KMS (Dedicated Customer Managed Key `docvault-cmk-dev`), IAM least-privilege functional execution roles.
- **Observability**: Amazon CloudWatch (Metric Alarms, Log Groups), AWS X-Ray service map.

## 3. Normal Operation
- CloudFormation stack `employee-document-vault-dev` in `UPDATE_COMPLETE` or `CREATE_COMPLETE`.
- API Gateway latency p95 < 200 ms with zero 5xx server errors.
- Lambda error rate 0.0% across all 7 functions.
- KMS CMK status is `Enabled` with automatic key rotation active.
- Document uploads follow mandatory prefix convention: `documents/{employee_id}/{document_type}/{filename}`.

## 4. Key Health Checks

```bash
# 1. Verify CloudFormation Stack State
aws cloudformation describe-stacks --stack-name employee-document-vault-dev --region ap-south-1 \
  --query "Stacks[0].[StackName,StackStatus]" --output table

# 2. Check KMS Customer Managed Key Status
aws kms describe-key --key-id alias/docvault-cmk-dev --region ap-south-1 \
  --query "KeyMetadata.[KeyId,KeyState,KeyManager,Origin]" --output table

# 3. Check S3 Bucket Public Access Block & TLS Policy
aws s3api get-public-access-block --bucket employee-document-vault-dev-331262815638 --region ap-south-1

# 4. Check Lambda 5-Minute Error Counts
aws cloudwatch get-metric-data --region ap-south-1 --start-time $(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --metric-data-queries '[{"Id":"err","MetricStat":{"Metric":{"Namespace":"AWS/Lambda","MetricName":"Errors"},"Period":300,"Stat":"Sum"}}]'

# 5. Check Active CloudWatch Alarms
aws cloudwatch describe-alarms --alarm-name-prefix "docvault-" --state-value ALARM --region ap-south-1
```

## 5. Common Failure Scenarios

| Symptom | Likely Cause | First Diagnostic Step | Safe Recovery Action |
|---|---|---|---|
| **Presigned URL generation rejected (HTTP 403)** | Requested document key attempts to write outside `/documents/*` or invalid employee token. | Inspect API Gateway access logs for rejected path parameter and `sub` claim. | Ensure client submits key matching `documents/{employee_id}/...`; verify token expiration. |
| **Download fails with S3 AccessDenied / Decryption error** | KMS Customer Managed Key disabled, pending deletion, or Lambda role denied `kms:Decrypt`. | Inspect CloudWatch log group `/aws/lambda/docvault-download-dev` for `KMS.DisabledException`. | If key was inadvertently disabled, run `aws kms enable-key --key-id <KeyId>`. Re-verify IAM key policy. |
| **Audit log entry missing on document deletion** | DynamoDB write throttling or transient network timeout on `AuditLogTable`. | Check CloudWatch metric `UserErrors` and `ThrottledRequests` on `AuditLogTable`. | DynamoDB is on-demand; verify partition key distribution. Retry failed operation; audit logs self-recover. |
| **Spike in API Gateway 5xx errors** | Downstream Lambda timeout or unhandled exception during document metadata validation. | Open AWS X-Ray console or query CloudWatch Logs Insights for `ERROR` / `Traceback`. | Identify failing function version; deploy bug fix via CloudFormation or rollback to previous template commit. |

## 6. Security Checks
- **KMS Key Rotation**: Assert `aws kms get-key-rotation-status --key-id alias/docvault-cmk-dev` returns `KeyRotationEnabled: true`.
- **S3 Bucket Public Access Block**: Confirm all 4 settings (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, `RestrictPublicBuckets`) remain `true`.
- **Transport Security**: S3 bucket policy contains explicit `DenyInsecureTransport` denying `aws:SecureTransport == false`.
- **IAM Scoping**: Verify Lambda roles contain zero `Resource: "*"` statements for S3 or DynamoDB actions.

## 7. Deployment / Rollback
- **Deployment**: Deployed via AWS SAM CLI with template `infra/template.yaml`.
  ```bash
  sam build && sam deploy --config-file samconfig.toml
  ```
- **Rollback**: CloudFormation automatically rolls back on resource provisioning failure (`UPDATE_ROLLBACK_COMPLETE`). For application regression, re-deploy previous stable git commit SHA.

## 8. Escalation & Evidence
- **CloudWatch Dashboard**: Inspect `internship-portfolio-overview-dev` (Widgets 4 & 5 for Project 1 API traffic, Lambda errors, and DynamoDB operations).
- **Log Groups**: `/aws/lambda/docvault-upload-dev`, `/aws/lambda/docvault-download-dev`, `/aws/api-gateway/docvault-dev`.
- **X-Ray Traces**: Query traces with `service("docvault-upload-dev") AND error = true` to capture fault payloads and request IDs.
