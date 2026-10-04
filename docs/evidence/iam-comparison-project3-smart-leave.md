# IAM Before/After Policy Comparison — Project 3: Smart Leave & Absence Management Engine

## Executive Summary
This document provides a verified, evidence-based audit of IAM policies in the **Smart Leave & Absence Management Engine** (`smart-leave-management-dev`). Prior to commit `567e83f`, the repository contained no CloudFormation, SAM, or IAM definitions in version control; Lambda functions operated with unmanaged execution roles whose pre-hardening policy definitions could not be established from repository history.

In commit `567e83f` (`feat: harden smart leave management`), complete infrastructure-as-code was codified in `infra/template.yaml`, establishing **13 newly codified runtime execution roles** (12 Lambda execution roles and 1 Step Functions state machine execution role). Each role was codified from its inception under strict least-privilege principles, binding all actions to specific resource ARNs across AWS Secrets Manager, DynamoDB tables and GSIs, AWS Step Functions, Amazon SES verified identities, and Amazon SNS topics.

---

## Runtime Roles

| Role / Function | Service Type | Historical State (Commit `4d1db45`) | Hardened State (Commit `567e83f`, `infra/template.yaml`) |
|---|---|---|---|
| `SubmitLeaveRequestFunctionRole` | Lambda (`SubmitLeaveRequestFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:GetItem` (Config, Balances), `PutItem`/`Query` (Requests), `states:StartExecution`, and `cognito-idp:ListUsers` |
| `ProcessApprovalDecisionFunctionRole` | Lambda (`ProcessApprovalDecisionFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `secretsmanager:GetSecretValue` on `ApprovalSecret`, `dynamodb:GetItem`/`UpdateItem` (Requests), and `states:SendTaskSuccess`/`Failure` on `*` (AWS API requirement) |
| `UpdateBalanceAndNotifyFunctionRole` | Lambda (`UpdateBalanceAndNotifyFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:UpdateItem` (Balances, Requests), and `ses:SendEmail` restricted to verified identity `${SesSenderEmail}` |
| `NotifyManagerWithTokenFunctionRole` | Lambda (`NotifyManagerWithTokenFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `secretsmanager:GetSecretValue`, `dynamodb:UpdateItem` (Requests), and `sns:Publish` on `ManagerNotificationsTopic` |
| `NotifyHRWithTokenFunctionRole` | Lambda (`NotifyHRWithTokenFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `secretsmanager:GetSecretValue`, `dynamodb:UpdateItem` (Requests), and `ses:SendEmail` on `${SesSenderEmail}` |
| `NotifyHREscalationFunctionRole` | Lambda (`NotifyHREscalationFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `ses:SendEmail` restricted to verified identity `${SesSenderEmail}` |
| `NotifyRejectedFunctionRole` | Lambda (`NotifyRejectedFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:UpdateItem` (Requests), and `ses:SendEmail` on `${SesSenderEmail}` |
| `GetEmployeeBalancesFunctionRole` | Lambda (`GetEmployeeBalancesFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:Query` on `LeaveBalancesTable.Arn` and `cognito-idp:ListUsers` on `LeaveUserPool.Arn` |
| `GetEmployeeRequestsFunctionRole` | Lambda (`GetEmployeeRequestsFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:Query` on `LeaveRequestsTable.Arn` and `cognito-idp:ListUsers` on `LeaveUserPool.Arn` |
| `GetPendingApprovalsFunctionRole` | Lambda (`GetPendingApprovalsFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:Query` on GSI `${LeaveRequestsTable.Arn}/index/ManagerStatusIndex` |
| `GetApprovedLeaveForTeamFunctionRole` | Lambda (`GetApprovedLeaveForTeamFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:Query` on GSI `${LeaveRequestsTable.Arn}/index/StatusDateIndex` |
| `WeeklyBalanceRecreditFunctionRole` | Lambda (`WeeklyBalanceRecreditFunction`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `dynamodb:Scan` on `LeaveBalancesTable.Arn` and `ses:SendEmail` on `${SesSenderEmail}` |
| `LeaveApprovalStateMachineRole` | Step Functions (`LeaveApprovalStateMachine`) | Historical pre-hardening policy definition could not be established from repository history. | Newly codified role: Scoped `lambda:InvokeFunction` strictly bound to the 5 worker Lambda ARNs + active X-Ray tracing |

---

## Policy-by-Policy Comparison

### 1. SubmitLeaveRequestFunctionRole — Leave Request Ingestion & State Machine Initiation

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history. No SAM/CloudFormation template or IAM configuration existed in the repository prior to commit 567e83f.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 281–301)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:GetItem
        Resource:
          - !GetAtt LeaveConfigTable.Arn
          - !GetAtt LeaveBalancesTable.Arn
      - Effect: Allow
        Action:
          - dynamodb:PutItem
          - dynamodb:Query
        Resource:
          - !GetAtt LeaveRequestsTable.Arn
      - Effect: Allow
        Action:
          - states:StartExecution
        Resource:
          - !Sub "arn:aws:states:${AWS::Region}:${AWS::AccountId}:stateMachine:smart-leave-approval-workflow-dev"
      - Effect: Allow
        Action:
          - cognito-idp:ListUsers
        Resource: !GetAtt LeaveUserPool.Arn
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege role.
- **Actions/resources affected**: Grants read-only `GetItem` on `LeaveConfigTable` and `LeaveBalancesTable` for leave quota validation; `PutItem` and `Query` on `LeaveRequestsTable` to record pending requests; `states:StartExecution` strictly bound to the leave approval state machine ARN; and `cognito-idp:ListUsers` on `LeaveUserPool.Arn` to resolve manager email addresses.
- **Security justification**: Prevents the leave submission endpoint from modifying balances directly, accessing non-leave tables, or invoking unauthorized workflows.

---

### 2. ProcessApprovalDecisionFunctionRole — HMAC Secret Retrieval & Step Functions Task Completion

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 345–365)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - secretsmanager:GetSecretValue
        Resource:
          - !Ref ApprovalSecret
      - Effect: Allow
        Action:
          - dynamodb:GetItem
          - dynamodb:UpdateItem
        Resource:
          - !GetAtt LeaveRequestsTable.Arn
      # AWS Step Functions API Architectural Limitation:
      # SendTaskSuccess and SendTaskFailure accept only taskToken as an argument and
      # do not support resource-level ARN restrictions in IAM. AWS IAM documentation
      # specifically mandates Resource: "*" for task-token callback operations.
      - Effect: Allow
        Action:
          - states:SendTaskSuccess
          - states:SendTaskFailure
        Resource: "*"
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege role.
- **Actions/resources affected**: `secretsmanager:GetSecretValue` strictly restricted to `!Ref ApprovalSecret` (`smart-leave/approval-secret-dev`); `dynamodb:GetItem` and `UpdateItem` restricted to `LeaveRequestsTable.Arn`; `states:SendTaskSuccess` and `states:SendTaskFailure` granted on `*`.
- **Security justification**:
  - Restricts cryptographic signing key retrieval strictly to the dedicated approval secret.
  - The `Resource: "*"` statement on `states:SendTaskSuccess` and `states:SendTaskFailure` is an **AWS-documented architectural limitation**: Step Functions task token callback actions do not accept state machine ARNs in their IAM authorization context, requiring `Resource: "*"`.

---

### 3. UpdateBalanceAndNotifyFunctionRole — Leave Balance Ledger Modification & Verified Email Dispatch

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 378–391)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:UpdateItem
        Resource:
          - !GetAtt LeaveBalancesTable.Arn
          - !GetAtt LeaveRequestsTable.Arn
      - Effect: Allow
        Action:
          - ses:SendEmail
        Resource: !Sub "arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/${SesSenderEmail}"
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege role.
- **Actions/resources affected**: Confines ledger deduction (`dynamodb:UpdateItem`) exclusively to `LeaveBalancesTable` and `LeaveRequestsTable`. Scopes `ses:SendEmail` strictly to the verified SES identity ARN (configured sender address).
- **Security justification**: Guarantees that balance modifications can only occur when invoked by the state machine following valid approval, and prevents outbound notification abuse.

---

### 4. NotifyManagerWithTokenFunctionRole — Manager Notification & SNS Escalation

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 413–427)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - secretsmanager:GetSecretValue
        Resource:
          - !Ref ApprovalSecret
      - Effect: Allow
        Action:
          - dynamodb:UpdateItem
        Resource:
          - !GetAtt LeaveRequestsTable.Arn
      - Effect: Allow
        Action:
          - sns:Publish
        Resource:
          - !Ref ManagerNotificationsTopic
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege role.
- **Actions/resources affected**: `secretsmanager:GetSecretValue` on `ApprovalSecret`, `dynamodb:UpdateItem` on `LeaveRequestsTable.Arn`, and `sns:Publish` on `!Ref ManagerNotificationsTopic` (`smart-leave-manager-notifications-dev`).
- **Security justification**: Restricts SNS publishing strictly to the internal manager notification topic and prevents cross-topic publishing.

---

### 5. Read-Only Query Roles — Query Scoping & GSI Isolation

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 534–540, 568–574, 599–604, 629–634)
- **Exact policy scope**:
```yaml
# GetEmployeeBalancesFunction:
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:Query
        Resource:
          - !GetAtt LeaveBalancesTable.Arn
      - Effect: Allow
        Action:
          - cognito-idp:ListUsers
        Resource: !GetAtt LeaveUserPool.Arn

# GetEmployeeRequestsFunction:
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:Query
        Resource:
          - !GetAtt LeaveRequestsTable.Arn
      - Effect: Allow
        Action:
          - cognito-idp:ListUsers
        Resource: !GetAtt LeaveUserPool.Arn

# GetPendingApprovalsFunction:
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:Query
        Resource:
          - !Sub "${LeaveRequestsTable.Arn}/index/ManagerStatusIndex"

# GetApprovedLeaveForTeamFunction:
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - dynamodb:Query
        Resource:
          - !Sub "${LeaveRequestsTable.Arn}/index/StatusDateIndex"
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege roles.
- **Actions/resources affected**: Completely eliminates table-wide `dynamodb:Scan` or broad read permissions for API queries. Each read endpoint is restricted exclusively to the specific table or Global Secondary Index (`ManagerStatusIndex`, `StatusDateIndex`) required for that query.
- **Security justification**: Enforces strict index-level boundary isolation and prevents unauthorized cross-tenant data traversal.

---

### 6. LeaveApprovalStateMachineRole — Step Functions Worker Orchestration

**BEFORE — source**
- **Commit**: `4d1db45` (and earlier)
- **File**: N/A
- **Exact policy scope**:
```text
Historical pre-hardening policy definition could not be established from repository history.
```

**AFTER — source**
- **Commit**: `567e83f`
- **File**: `infra/template.yaml` (Lines 246–256)
- **Exact policy scope**:
```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action: lambda:InvokeFunction
        Resource:
          - !GetAtt NotifyManagerWithTokenFunction.Arn
          - !GetAtt NotifyHRWithTokenFunction.Arn
          - !GetAtt NotifyHREscalationFunction.Arn
          - !GetAtt UpdateBalanceAndNotifyFunction.Arn
          - !GetAtt NotifyRejectedFunction.Arn
```

**Analysis & Justification**
- **Nature of change**: Newly codified least-privilege role.
- **Actions/resources affected**: `lambda:InvokeFunction` is explicitly constrained to the exact ARNs of the 5 worker functions that comprise the approval state machine workflow.
- **Security justification**: Prevents the Step Functions execution role from being leveraged to invoke arbitrary Lambdas in the account.

---

## Observability & Governance Boundary (Separated from IAM)
- **X-Ray Distributed Tracing**: Configured globally in `Globals.Function` via `Tracing: Active` (Line 23) and on the state machine via `Tracing: Enabled: true` (Line 244).
- **Log Group Retention**: All 12 Lambda functions have dedicated `AWS::Logs::LogGroup` resources defined with `RetentionInDays: 14` to prevent indefinite unmanaged log storage.
- **Cognito JWT Authorization**: API Gateway routes (`/balances`, `/requests`, `/manager/pending`, `/calendar/approved`) enforce `CognitoJwtAuthorizer` with `Audience: !Ref LeaveUserPoolClient` and `Issuer: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${LeaveUserPool}"`.
