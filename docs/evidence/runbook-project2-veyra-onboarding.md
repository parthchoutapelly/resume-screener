# Operations Runbook — Project 2: Smart Employee Onboarding & Identity Service (VEYRA)

## 1. Purpose
VEYRA (`onboarding-service-dev`) is an automated serverless workflow orchestration engine that streamlines end-to-end employee onboarding. It coordinates identity provisioning, secure document collection, IT equipment assignment, and compliance sign-off through an AWS Step Functions state machine with event-driven notifications.

## 2. Architecture / Components
- **API Ingress**: Amazon API Gateway (REST API `onboarding-api-dev`, Stage `dev`).
- **Workflow Orchestration**: AWS Step Functions (`OnboardingStateMachine` Standard Workflow).
- **Compute**: 13 AWS Lambda functions across workflow stages and REST handlers with AWS X-Ray tracing.
- **Identity & Access**: Amazon Cognito User Pool (`ap-south-1_LDOpZYY1U`, Essentials Tier), IAM service execution roles.
- **Datastore & Storage**: Amazon DynamoDB (`onboarding-employee-profile-dev`, On-Demand), Amazon S3 (`onboarding-documents-dev-*`, SSE-S3).
- **Messaging & Notifications**: Amazon SES (Verified sender identity), Amazon SNS (`onboarding-notifications-dev`).

## 3. Normal Operation
- CloudFormation stack `onboarding-service-dev` in `UPDATE_COMPLETE` or `CREATE_COMPLETE`.
- Step Functions state machine execution success rate > 98% with 0 timed-out executions.
- API Gateway latency p95 < 200 ms (measured steady-state ~73 ms at 50 req/s).
- Active Cognito User Pool accepting authentication requests.
- DynamoDB `onboarding-employee-profile-dev` operating with zero read/write throttles.

## 4. Key Health Checks

```bash
# 1. Verify CloudFormation Stack Status
aws cloudformation describe-stacks --stack-name onboarding-service-dev --region ap-south-1 \
  --query "Stacks[0].[StackName,StackStatus]" --output table

# 2. Check Step Functions Execution Failure Counts (Last 1 Hour)
aws stepfunctions list-executions --state-machine-arn $(aws stepfunctions list-state-machines --region ap-south-1 \
  --query "stateMachines[?contains(name,'OnboardingStateMachine')].stateMachineArn" --output text) \
  --status-filter FAILED --max-items 10 --region ap-south-1

# 3. Check Account Lambda Regional Concurrency Headroom
aws lambda get-account-settings --region ap-south-1 --query "AccountLimit" --output json

# 4. Check API Gateway Request Count and 5XX Errors
aws cloudwatch get-metric-data --region ap-south-1 --start-time $(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ) --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --metric-data-queries '[
    {"Id":"cnt","MetricStat":{"Metric":{"Namespace":"AWS/ApiGateway","MetricName":"Count","Dimensions":[{"Name":"ApiName","Value":"onboarding-api-dev"},{"Name":"Stage","Value":"dev"}]},"Period":300,"Stat":"Sum"}},
    {"Id":"err","MetricStat":{"Metric":{"Namespace":"AWS/ApiGateway","MetricName":"5XXError","Dimensions":[{"Name":"ApiName","Value":"onboarding-api-dev"},{"Name":"Stage","Value":"dev"}]},"Period":300,"Stat":"Sum"}}
  ]'

# 5. Check Active CloudWatch Alarms
aws cloudwatch describe-alarms --alarm-name-prefix "onboarding-" --state-value ALARM --region ap-south-1
```

## 5. Common Failure Scenarios

| Symptom | Likely Cause | First Diagnostic Step | Safe Recovery Action |
|---|---|---|---|
| **Step Functions execution stalled or failed** | Document validation timeout or unhandled task rejection in `ValidateDocumentFunction`. | Open Step Functions console; click the failed execution ARN to inspect the execution history and error payload. | If document was corrupted, trigger `SendReminderEmailFunction` to request re-upload, or retry workflow from failed state. |
| **Transient HTTP 500 errors during sudden traffic bursts** | AWS Account regional Lambda concurrency ceiling reached (account limit = 10 concurrent executions). | Inspect CloudWatch metric `Throttles` across Lambda functions (`list-employees`, `get-status`). | Confirmed normal burst dynamic; system self-heals in ~8s. For sustained high load, request regional concurrency increase. |
| **Cognito User Provisioning Failure (HTTP 409)** | Duplicate employee email or user profile already exists in Cognito User Pool. | Check CloudWatch logs for `ProvisionCognitoUserFunction` for `UsernameExistsException`. | Verify employee database record. If user exists from previous attempt, update status to `ACTIVE` without re-creating. |
| **Email notification not delivered** | In SES sandbox mode, recipient email address is not verified, or sending quota reached. | Check CloudWatch metric `Reputation.BounceRate` and SES sending statistics. | Verify recipient email in Amazon SES console (`aws ses verify-email-identity`) or request SES production access. |

## 6. Security Checks
- **SES Sender Identity Scoping**: Confirm IAM policies for `SendReminderEmailFunctionRole` restrict `ses:SendEmail` strictly to the verified identity ARN.
- **S3 Presigned Upload Boundary**: Assert presigned upload generation enforces prefix `documents/{employee_id}/*`.
- **Step Functions Execution Role**: Confirm `OnboardingStateMachineRole` permits `lambda:InvokeFunction` strictly for the 5 stage Lambda function ARNs.
- **Cognito Security Configuration**: Confirm password policy requires 8+ characters, symbols, numbers, and uppercase characters.

## 7. Deployment / Rollback
- **Deployment**: Deployed via AWS SAM CLI with template `template.yaml`.
  ```bash
  sam build && sam deploy --config-file samconfig.toml
  ```
- **Rollback**: On failure during deployment, CloudFormation automatically executes rollback. To revert an application regression, redeploy previous validated git commit.

## 8. Escalation & Evidence
- **CloudWatch Dashboard**: Inspect `internship-portfolio-overview-dev` (Widgets 6 & 7 for Step Functions workflow executions and API Gateway latency).
- **Log Groups**: `/aws/lambda/onboarding-create-profile-dev`, `/aws/lambda/onboarding-validate-doc-dev`, `/aws/vendedlogs/states/OnboardingStateMachine-dev`.
- **Execution History**: Use `aws stepfunctions describe-execution --execution-arn <Arn>` to export full JSON state transition history.
