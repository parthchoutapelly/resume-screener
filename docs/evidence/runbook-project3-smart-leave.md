# Operations Runbook — Project 3: Smart Leave & Absence Management Engine

## 1. Purpose
The Smart Leave & Absence Management Engine (`smart-leave-management-dev`) automates corporate leave requests, quota ledger accounting, cryptographically signed manager approval workflows, team availability conflict detection, and automated HR SLA escalations via serverless event-driven architecture.

## 2. Architecture / Components
- **API Ingress**: Amazon API Gateway (HTTP API v2 `smart-leave-management-dev`, Stage `dev`).
- **Orchestration**: AWS Step Functions (`LeaveApprovalStateMachine`).
- **Compute**: 12 AWS Lambda microservices handling request submission, cryptographic token signing, balance accounting, and email notifications.
- **Cryptographic Security**: AWS Secrets Manager (Stores `ApprovalSecret` used to sign one-time approval tokens).
- **Database & State**: Amazon DynamoDB (`LeaveRequestsTable`, `LeaveBalancesTable`, `LeaveConfigTable`, On-Demand).
- **Messaging & Notifications**: Amazon SES (Verified sender identity), Amazon SNS (`smart-leave-manager-notifications-dev`).

## 3. Normal Operation
- CloudFormation stack `smart-leave-management-dev` in `UPDATE_COMPLETE` or `CREATE_COMPLETE`.
- HTTP API latency p95 < 150 ms (lightweight HTTP API delivers ~30 ms response times).
- Step Functions state machines running without unhandled task failures.
- Leave requests transition smoothly: `PENDING_MANAGER` $\to$ `APPROVED` or `ESCALATED_HR` within configured SLA.
- Balance deductions in `LeaveBalancesTable` are strictly atomic with zero overdrafts.

## 4. Key Health Checks

```bash
# 1. Verify CloudFormation Stack State
aws cloudformation describe-stacks --stack-name smart-leave-management-dev --region ap-south-1 \
  --query "Stacks[0].[StackName,StackStatus]" --output table

# 2. Check Secrets Manager Secret Availability
aws secretsmanager describe-secret --secret-id smart-leave/approval-secret-dev --region ap-south-1 \
  --query "[Name,RotationEnabled,LastAccessedDate]" --output table

# 3. Check Pending Approvals in LeaveRequestsTable (via ManagerStatusIndex GSI)
aws dynamodb query --table-name smart-leave-requests-dev --index-name ManagerStatusIndex \
  --key-condition-expression "#s = :pending" --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":pending":{"S":"PENDING_MANAGER"}}' --select COUNT --region ap-south-1

# 4. Check Lambda 5-Minute Error Counts
aws cloudwatch get-metric-data --region ap-south-1 --start-time $(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --metric-data-queries '[{"Id":"err","MetricStat":{"Metric":{"Namespace":"AWS/Lambda","MetricName":"Errors"},"Period":300,"Stat":"Sum"}}]'

# 5. Check Active CloudWatch Alarms
aws cloudwatch describe-alarms --alarm-name-prefix "smart-leave-" --state-value ALARM --region ap-south-1
```

## 5. Common Failure Scenarios

| Symptom | Likely Cause | First Diagnostic Step | Safe Recovery Action |
|---|---|---|---|
| **Manager approval link rejected (HTTP 401/403)** | Token expired (> 48h SLA), invalid HMAC signature, or `ApprovalSecret` was rotated. | Inspect CloudWatch log `/aws/lambda/smart-leave-process-approval-dev` for `TokenValidationError`. | If request is valid, manager can re-trigger approval from dashboard or HR can approve via admin console. |
| **Leave request submission fails (HTTP 409)** | Insufficient leave balance in `LeaveBalancesTable` or conflicting concurrent request. | Check `LeaveBalancesTable` for employee's balance record and available days. | Advise employee of balance exhaustion; if conflict occurred, employee can re-submit with adjusted dates. |
| **Request transitions to ESCALATED_HR unexpectedly** | Manager did not respond within configured 48-hour Step Functions wait timer. | Check Step Functions execution history for task state `WaitForManagerDecision` timing out. | Normal automated SLA behavior. HR receives automated escalation email and resolves request directly. |
| **Balance recredit cron fails** | CloudWatch Event rule execution failed or Lambda timeout scanning `LeaveBalancesTable`. | Check `/aws/lambda/smart-leave-weekly-recredit-dev` logs for timeout or DynamoDB scan error. | Re-run recredit job manually using test payload; DynamoDB conditional updates ensure idempotency. |

## 6. Security Checks
- **Secrets Access Scoping**: Confirm only `ProcessApprovalDecisionFunctionRole`, `NotifyManagerWithTokenFunctionRole`, and `NotifyHRWithTokenFunctionRole` possess `secretsmanager:GetSecretValue`.
- **Atomic Balance Updates**: Confirm balance deductions in DynamoDB use conditional expressions (`attribute_exists` and `remaining_days >= :requested`) to prevent negative balances.
- **SES Sender Scoping**: Verify `ses:SendEmail` is strictly confined to `identity/${SesSenderEmail}`.
- **No Wildcard Permissions**: Ensure Lambda roles possess no `Resource: "*"` except where mandated by AWS APIs (`states:SendTaskSuccess`).

## 7. Deployment / Rollback
- **Deployment**: Deployed via AWS SAM CLI with template `infra/template.yaml`.
  ```bash
  sam build && sam deploy --config-file samconfig.toml
  ```
- **Rollback**: Standard CloudFormation rollback. If an issue occurs post-deployment, re-deploy previous git commit. DynamoDB PITR provides point-in-time state recovery if data inconsistency arises.

## 8. Escalation & Evidence
- **CloudWatch Dashboard**: Inspect `internship-portfolio-overview-dev` (Widgets 8 & 9 for HTTP API volume and approval workflow metrics).
- **Log Groups**: `/aws/lambda/smart-leave-submit-request-dev`, `/aws/lambda/smart-leave-process-approval-dev`, `/aws/vendedlogs/states/LeaveApprovalStateMachine-dev`.
- **Audit Records**: All request status transitions (`PENDING_MANAGER` $\to$ `APPROVED` / `REJECTED` / `CANCELLED`) are permanently recorded in `LeaveRequestsTable`.
