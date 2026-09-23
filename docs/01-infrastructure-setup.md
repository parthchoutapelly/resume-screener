# PHASE 1 of 5 — Pre-flight Spikes & Infrastructure Scaffold
### Project: AI-Powered Resume Screener & Talent Acquisition Pipeline

| | |
|---|---|
| **Covers** | `Tasks.md` E0 (T-001–T-009) and E1 (T-010–T-019) |
| **Owner** | Parth |
| **Prerequisites** | AWS CLI v2, SAM CLI ≥ 1.120, Docker Desktop running, Python 3.12, Node 20, access to the AWS account (ap-south-1) |
| **Read first** | `Memory.md` §1–3 and §6 (pitfalls) · `Architecture.md` §1, §6, §8, §10 · `Rules.md` §3, §8 |
| **Produces** | Validated platform assumptions; a deployed `dev` stack with all storage, queues, auth, hosting, and alerting resources, and 14 stub functions |
| **Hands off to** | `02-ingestion-pipeline.md` |

> **Agent instructions.** You are building phase 1 of 5. Write **no business logic**: every handler is a 501 stub. Complete §2 (spikes) **before** §4 (template): spike results can change packaging decisions, and those changes must be recorded in `Memory.md` §3 before any code depends on them. If anything here conflicts with `Details.md`/`Implementation.md`, this file and the new spec set win (`Memory.md` §7).
>
> **Why the platform looks the way it does:** the account is on the AWS **Free plan**, so Amazon Textract and Amazon Comprehend can't be called (confirmed by AWS Support). Extraction therefore uses open-source libraries in a **container-image Lambda** (Tesseract is a native binary), and NLP uses spaCy in a zip Lambda with layers. Neither managed AI service appears anywhere in this project (R-HON-08).

---

## 1. Guardrails for this phase

- R-SEC-01: every bucket has Block Public Access ×4 + SSE + TLS-only policy; **no S3 static website hosting**.
- R-SEC-02: one role per function, scoped by ARN. The stubs get no data permissions yet.
- R-DATA-03: code gets resource names from env vars. Tables keep readable physical names (`jobs-dev`) for the console, but code must never construct them.
- D-33: `Architectures: [x86_64]` for every function and layer; build with `sam build --use-container`.
- No `textract:*` / `comprehend:*` anywhere.

---

## 2. Pre-flight spikes (E0) — do these first

Record every result in `infra/README.md` → "Platform validation". If a result contradicts an assumption (`PRD.md` §11), add a decision to `Memory.md` §3 before continuing.

| ID | Spike | How | Pass condition | If it fails |
|---|---|---|---|---|
| T-001 | Free-plan service availability | In the console, create then delete: a CloudFront distribution, an SES identity, an ECR repo, a Budget, and an SQS queue with a Lambda trigger | All creatable | Record the blocked service; CloudFront blocked → decide on an alternative HTTPS hosting (Amplify Hosting) before §4.4 |
| T-002 | Build toolchain | `sam init` hello-world (python3.12, **x86_64**), both zip and image; `sam build --use-container && sam deploy` | Both invoke OK | On Apple Silicon, enable Rosetta/QEMU emulation in Docker Desktop |
| T-003 | **Tesseract image** | Build candidate A; if Tesseract isn't installable, build candidate B (below). Deploy and run `pytesseract.image_to_string` on a PNG | Real OCR text returned from inside Lambda | Stop and escalate: extraction has no fallback that is honest (R-HON-03) |
| T-004 | SES | Verify the sender identity + 3 test recipients in ap-south-1 | All "Verified" | Start the production-access request now (can take ~24 h) |
| T-005 | Concurrency quota | Service Quotas → Lambda → Concurrent executions | ≥ 50 (or request an increase) | Keep `MaximumConcurrency` at 2/2 and record it |
| T-006 | spaCy layer size | Build the `NlpLayer` recipe from `02` §5 with `--use-container`; `du -sh` the unzipped layer; cold-start a test function | Function + layers < 250 MB unzipped | Package NLP as an image too; record a new decision |
| T-007 | Synthetic fixtures | Create per `Tasks.md` T-007 | Committed, no real PII | — |
| T-008 | Open questions | OQ8–OQ11 with the mentor | Answers recorded in `PRD.md` §13 | Proceed on the working assumptions |
| T-009 | Deploy IAM user | §6 below | E1 stack deploys with it | Add the missing actions; log each in the README |

**Candidate A — AWS base image** (the Python 3.12 base is Amazon Linux 2023: it has `dnf` or `microdnf`, **not `yum`**):
```dockerfile
FROM public.ecr.aws/lambda/python:3.12
# Package availability on AL2023 is UNVERIFIED — this is what the spike tests.
RUN (dnf install -y tesseract tesseract-langpack-eng || microdnf install -y tesseract tesseract-langpack-eng) \
    && (dnf clean all || microdnf clean all)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"
COPY app/ ${LAMBDA_TASK_ROOT}/
CMD ["handler.lambda_handler"]
```

**Candidate B — Debian slim + runtime interface client** (well-trodden, `tesseract-ocr` is in the Debian repos):
```dockerfile
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /var/task
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric
COPY app/ ./
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
```
For B, confirm that `sam local invoke` works (SAM mounts the runtime interface emulator). If it doesn't, add `aws-lambda-rie` for local testing only. Whichever candidate wins becomes `backend/ingestion/extraction/Dockerfile`; record the choice as the D-34 outcome in `Memory.md`.

Verify the image platform before deploying: `docker inspect <image> --format '{{.Architecture}}'` must print `amd64`.

---

## 3. Repository scaffold (T-010)

```
resume-screener/
├── template.yaml
├── samconfig.toml                 # [dev] and [prod] config envs
├── Makefile                       # build | deploy ENV=dev | test | lint | seed ENV=dev | frontend ENV=dev
├── pyproject.toml                 # ruff, black, pytest config
├── infra/README.md                # prerequisites, platform validation, manual steps, runbook
├── scripts/
│   ├── seed-config.sh             # idempotent config row
│   ├── create-user.sh             # admin-create-user + add to group
│   ├── gen-frontend-env.sh        # stack outputs → frontend/.env.<env>   (phase 4)
│   └── deploy-frontend.sh         # build, sync, invalidate               (phase 4)
├── backend/
│   ├── ingestion/extraction/{Dockerfile, requirements.txt, app/handler.py}
│   ├── ingestion/nlp/handler.py
│   ├── scoring/score_match/handler.py
│   ├── api/{create_job_posting, add_resumes, get_jobs, get_job, update_job,
│   │        get_candidates_by_job, update_candidate_decision, get_resume_url,
│   │        export_shortlist_csv, get_failed_jobs}/handler.py
│   ├── reliability/dlq_handler/handler.py
│   ├── layers/common_layer/{python/rs_common/, data/}      # phase 2
│   ├── layers/nlp_layer/requirements.txt                   # phase 2
│   └── data/                                               # dictionary sources (phase 2)
├── frontend/                                               # phase 4
├── tests/{unit, component, integration, fixtures}/
└── docs/                                                   # this spec set + deliverables
```

Stub handler (all zip functions, and `app/handler.py` in the image):
```python
def lambda_handler(event, context):
    return {"statusCode": 501, "body": '{"error":{"code":"NOT_IMPLEMENTED","message":"Stub — see phase files 2/3"}}'}
```

---

## 4. `template.yaml` (T-011 – T-019)

Fragments below are normative for properties shown; fill in the obvious boilerplate. Run `sam validate --lint` after each block.

### 4.1 Parameters, conditions, globals
```yaml
Parameters:
  EnvName:        {Type: String, Default: dev, AllowedValues: [dev, prod]}
  SesSenderAddress: {Type: String, Description: "SES-verified sender (T-004)"}
  AlertEmail:     {Type: String, Default: ""}
  CreateBudget:   {Type: String, Default: "false", AllowedValues: ["true", "false"]}   # true in ONE stack only — budgets are account-wide
  BudgetAmountUsd: {Type: Number, Default: 10}

Conditions:
  IsDev:          !Equals [!Ref EnvName, dev]
  HasAlertEmail:  !Not [!Equals [!Ref AlertEmail, ""]]
  MakeBudget:     !Equals [!Ref CreateBudget, "true"]

Globals:
  Function:
    Runtime: python3.12          # ignored by the image function; if `sam validate` objects, move Runtime to each zip function
    Architectures: [x86_64]
    Timeout: 10
    MemorySize: 256
    LoggingConfig: {LogFormat: JSON}
    Environment:
      Variables:
        ENV: !Ref EnvName
        LOG_LEVEL: INFO
```

### 4.2 Upload bucket (T-012)
```yaml
UploadBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub resume-screener-${EnvName}-${AWS::AccountId}
    PublicAccessBlockConfiguration: {BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true}
    OwnershipControls: {Rules: [{ObjectOwnership: BucketOwnerEnforced}]}
    BucketEncryption: {ServerSideEncryptionConfiguration: [{ServerSideEncryptionByDefault: {SSEAlgorithm: AES256}}]}
    CorsConfiguration:
      CorsRules:
        - AllowedMethods: [POST, GET]
          AllowedOrigins: !If
            - IsDev
            - [!Sub "https://${WebDistribution.DomainName}", "http://localhost:5173"]
            - [!Sub "https://${WebDistribution.DomainName}"]
          AllowedHeaders: ["*"]
          MaxAge: 3000
    LifecycleConfiguration:
      Rules:
        - {Id: expire-exports, Status: Enabled, Prefix: exports/,        ExpirationInDays: 7}
        - {Id: expire-jds,     Status: Enabled, Prefix: jd-uploads/,     ExpirationInDays: 180}   # OQ9
        - {Id: expire-resumes, Status: Enabled, Prefix: resume-uploads/, ExpirationInDays: 180}   # OQ9
    # NotificationConfiguration is added in phase 2 (T-038), once the extraction consumer exists.

UploadBucketPolicy:
  Type: AWS::S3::BucketPolicy
  Properties:
    Bucket: !Ref UploadBucket
    PolicyDocument:
      Statement:
        - Sid: DenyInsecureTransport
          Effect: Deny
          Principal: "*"
          Action: "s3:*"
          Resource: [!GetAtt UploadBucket.Arn, !Sub "${UploadBucket.Arn}/*"]
          Condition: {Bool: {"aws:SecureTransport": "false"}}
```
The allowed origin is **derived from the CloudFront distribution in the same stack**, so there's no manual origin parameter to keep in sync. In development the SPA runs on `localhost:5173`; its API calls go through the Vite proxy (phase 4), so only the S3 upload needs the extra dev origin.

### 4.3 Web bucket + CloudFront (T-013) — replaces S3 website hosting (D-22)
```yaml
WebBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub resume-screener-web-${EnvName}-${AWS::AccountId}
    PublicAccessBlockConfiguration: {BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true}
    OwnershipControls: {Rules: [{ObjectOwnership: BucketOwnerEnforced}]}
    BucketEncryption: {ServerSideEncryptionConfiguration: [{ServerSideEncryptionByDefault: {SSEAlgorithm: AES256}}]}

WebOAC:
  Type: AWS::CloudFront::OriginAccessControl
  Properties:
    OriginAccessControlConfig:
      Name: !Sub rs-web-oac-${EnvName}
      OriginAccessControlOriginType: s3
      SigningBehavior: always
      SigningProtocol: sigv4

WebHeadersPolicy:
  Type: AWS::CloudFront::ResponseHeadersPolicy
  Properties:
    ResponseHeadersPolicyConfig:
      Name: !Sub rs-web-headers-${EnvName}
      SecurityHeadersConfig:
        StrictTransportSecurity: {AccessControlMaxAgeSec: 31536000, IncludeSubdomains: true, Override: true}
        ContentTypeOptions: {Override: true}
        FrameOptions: {FrameOption: DENY, Override: true}
        ReferrerPolicy: {ReferrerPolicy: same-origin, Override: true}
        ContentSecurityPolicy:
          Override: true
          ContentSecurityPolicy: !Sub >-
            default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';
            connect-src 'self' https://*.execute-api.${AWS::Region}.amazonaws.com
            https://cognito-idp.${AWS::Region}.amazonaws.com
            https://*.s3.${AWS::Region}.amazonaws.com https://*.s3.amazonaws.com;
            frame-ancestors 'none'

WebDistribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    DistributionConfig:
      Enabled: true
      DefaultRootObject: index.html
      HttpVersion: http2
      PriceClass: PriceClass_200            # includes edge locations in India
      Origins:
        - Id: web
          DomainName: !GetAtt WebBucket.RegionalDomainName
          S3OriginConfig: {OriginAccessIdentity: ""}
          OriginAccessControlId: !GetAtt WebOAC.Id
      DefaultCacheBehavior:
        TargetOriginId: web
        ViewerProtocolPolicy: redirect-to-https
        CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6    # Managed-CachingOptimized
        ResponseHeadersPolicyId: !Ref WebHeadersPolicy
      CustomErrorResponses:                  # SPA deep links
        - {ErrorCode: 403, ResponseCode: 200, ResponsePagePath: /index.html}
        - {ErrorCode: 404, ResponseCode: 200, ResponsePagePath: /index.html}

WebBucketPolicy:
  Type: AWS::S3::BucketPolicy
  Properties:
    Bucket: !Ref WebBucket
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal: {Service: cloudfront.amazonaws.com}
          Action: s3:GetObject
          Resource: !Sub "${WebBucket.Arn}/*"
          Condition: {StringEquals: {"AWS:SourceArn": !Sub "arn:aws:cloudfront::${AWS::AccountId}:distribution/${WebDistribution}"}}
        - Sid: DenyInsecureTransport
          Effect: Deny
          Principal: "*"
          Action: "s3:*"
          Resource: [!GetAtt WebBucket.Arn, !Sub "${WebBucket.Arn}/*"]
          Condition: {Bool: {"aws:SecureTransport": "false"}}
```
Upload a placeholder `index.html` after deploy to check it (`aws s3 cp`).

### 4.4 DynamoDB (T-014)
All tables: `BillingMode: PAY_PER_REQUEST`, `SSESpecification: {SSEEnabled: true}`.

| Logical ID | TableName | Keys | Extras |
|---|---|---|---|
| `JobsTable` | `jobs-${EnvName}` | PK `job_id` (S) | GSI **`RecruiterJobsIndex`**: PK `recruiter_id` (S), SK `created_at` (S), projection `ALL` |
| `CandidatesTable` | `candidates-${EnvName}` | PK `job_id` (S), SK `candidate_id` (S) | **No GSI** — `JobScoreIndex` was removed (D-16: sparse index hid unscored rows) |
| `FailedJobsTable` | `failed_jobs-${EnvName}` | PK `job_id` (S), SK `failure_id` (S) | `TimeToLiveSpecification: {AttributeName: expires_at, Enabled: true}` (90-day audit TTL) |
| `ConfigTable` | `config-${EnvName}` | PK `config_key` (S) | Seeded by T-015 |

The attribute-level schema is in `Architecture.md` §6 (DynamoDB only declares key attributes). **Reminder for later phases:** numbers are written as `Decimal`, and `match_score` / `total_experience_years` are **omitted** until known — never written as null (R-DATA-01/02).

### 4.5 Config seed (T-015)
`scripts/seed-config.sh <env>` (idempotent; run from `make seed`):
```bash
aws dynamodb put-item --region ap-south-1 --table-name "config-$1" \
  --item '{"config_key":{"S":"nlp_engine_mode"},"config_value":{"S":"spacy_hybrid"}}'
```
`spacy_hybrid` is the only mode. Do not add other values, branches, or fallbacks (D-13).

### 4.6 SQS (T-016)
```yaml
IngestionDLQ: {Type: AWS::SQS::Queue, Properties: {QueueName: !Sub rs-ingestion-dlq-${EnvName}, MessageRetentionPeriod: 1209600, SqsManagedSseEnabled: true}}
ScoringDLQ:   {Type: AWS::SQS::Queue, Properties: {QueueName: !Sub rs-scoring-dlq-${EnvName},   MessageRetentionPeriod: 1209600, SqsManagedSseEnabled: true}}

IngestionQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: !Sub rs-ingestion-${EnvName}
    VisibilityTimeout: 720               # 6 × extraction timeout (120 s)
    SqsManagedSseEnabled: true
    RedrivePolicy: {deadLetterTargetArn: !GetAtt IngestionDLQ.Arn, maxReceiveCount: 3}

ScoringQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: !Sub rs-scoring-${EnvName}
    VisibilityTimeout: 60                # 6 × scoreMatch timeout (10 s)
    SqsManagedSseEnabled: true
    RedrivePolicy: {deadLetterTargetArn: !GetAtt ScoringDLQ.Arn, maxReceiveCount: 5}

IngestionQueuePolicy:                    # lets S3 deliver events (used from phase 2)
  Type: AWS::SQS::QueuePolicy
  Properties:
    Queues: [!Ref IngestionQueue]
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal: {Service: s3.amazonaws.com}
          Action: sqs:SendMessage
          Resource: !GetAtt IngestionQueue.Arn
          Condition:
            ArnEquals: {"aws:SourceArn": !Sub "arn:aws:s3:::resume-screener-${EnvName}-${AWS::AccountId}"}
            StringEquals: {"aws:SourceAccount": !Ref AWS::AccountId}
```
Both queues carry messages for **JD and resume** documents (D-05). The scoring queue's 5 attempts are now only for genuine errors: "JD not ready" is acknowledged, not retried (D-18).

### 4.7 Cognito (T-017)
```yaml
UserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: !Sub resume-screener-users-${EnvName}
    UsernameAttributes: [email]
    AutoVerifiedAttributes: [email]
    AdminCreateUserConfig: {AllowAdminCreateUserOnly: true}     # no self sign-up (R-AUTH-02)
    AccountRecoverySetting: {RecoveryMechanisms: [{Name: admin_only, Priority: 1}]}
    Policies:
      PasswordPolicy: {MinimumLength: 12, RequireLowercase: true, RequireUppercase: true, RequireNumbers: true, RequireSymbols: false, TemporaryPasswordValidityDays: 7}

UserPoolClient:
  Type: AWS::Cognito::UserPoolClient
  Properties:
    UserPoolId: !Ref UserPool
    GenerateSecret: false                                       # public SPA
    ExplicitAuthFlows: [ALLOW_USER_SRP_AUTH, ALLOW_REFRESH_TOKEN_AUTH]
    PreventUserExistenceErrors: ENABLED
    IdTokenValidity: 60
    AccessTokenValidity: 60
    RefreshTokenValidity: 7
    TokenValidityUnits: {IdToken: minutes, AccessToken: minutes, RefreshToken: days}

RecruiterGroup: {Type: AWS::Cognito::UserPoolGroup, Properties: {UserPoolId: !Ref UserPool, GroupName: Recruiter}}
AdminGroup:     {Type: AWS::Cognito::UserPoolGroup, Properties: {UserPoolId: !Ref UserPool, GroupName: Admin}}
```
`scripts/create-user.sh <env> <email> <Recruiter|Admin|none>` wraps `admin-create-user` + `admin-add-user-to-group`. Create at least: two Recruiters (isolation tests), one Admin, and **one user with no group** (403 tests).

### 4.8 Alerting & budget (T-018)
```yaml
AlertsTopic:
  Type: AWS::SNS::Topic
  Properties:
    TopicName: !Sub rs-alerts-${EnvName}
    Subscription: !If [HasAlertEmail, [{Protocol: email, Endpoint: !Ref AlertEmail}], !Ref AWS::NoValue]

AlertsTopicPolicy:
  Type: AWS::SNS::TopicPolicy
  Properties:
    Topics: [!Ref AlertsTopic]
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal: {Service: [budgets.amazonaws.com, cloudwatch.amazonaws.com]}
          Action: sns:Publish
          Resource: !Ref AlertsTopic

MonthlyBudget:
  Type: AWS::Budgets::Budget
  Condition: MakeBudget
  Properties:
    Budget: {BudgetName: resume-screener-monthly, BudgetType: COST, TimeUnit: MONTHLY, BudgetLimit: {Amount: !Ref BudgetAmountUsd, Unit: USD}}
    NotificationsWithSubscribers:
      - Notification: {NotificationType: ACTUAL, ComparisonOperator: GREATER_THAN, Threshold: 80, ThresholdType: PERCENTAGE}
        Subscribers: [{SubscriptionType: SNS, Address: !Ref AlertsTopic}]
      - Notification: {NotificationType: FORECASTED, ComparisonOperator: GREATER_THAN, Threshold: 100, ThresholdType: PERCENTAGE}
        Subscribers: [{SubscriptionType: SNS, Address: !Ref AlertsTopic}]
```
The alarms themselves are added in phase 3 (T-071), once there are real functions to watch. Pass the `AlertEmail` parameter rather than hardcoding a personal address.

### 4.9 Functions: stubs + log groups (T-019)
Declare all 14 functions now so their ARNs exist, each with an explicit `FunctionName` (`rs-<name>-${EnvName}`) and a matching log group:
```yaml
ExtractionFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: !Sub rs-extraction-${EnvName}
    PackageType: Image
    Architectures: [x86_64]
    Timeout: 120
    MemorySize: 1536
    EphemeralStorage: {Size: 1024}
  Metadata:
    Dockerfile: Dockerfile
    DockerContext: ./backend/ingestion/extraction
    DockerTag: python3.12-v1

ExtractionLogGroup:
  Type: AWS::Logs::LogGroup
  Properties: {LogGroupName: !Sub /aws/lambda/rs-extraction-${EnvName}, RetentionInDays: 30}
```

| Logical ID | Code | Final timeout / memory (set now) |
|---|---|---|
| `ExtractionFunction` | image | 120 s / 1536 MB / 1024 MB `/tmp` |
| `NlpFunction` | `backend/ingestion/nlp/` | 30 s / 1024 MB |
| `ScoreMatchFunction` | `backend/scoring/score_match/` | 10 s / 256 MB |
| `CreateJobPostingFunction`, `AddResumesFunction`, `GetJobsFunction`, `GetJobFunction`, `UpdateJobFunction`, `GetCandidatesByJobFunction`, `UpdateCandidateDecisionFunction`, `GetResumeUrlFunction`, `ExportShortlistCsvFunction`, `GetFailedJobsFunction` | `backend/api/<snake_name>/` | 10 s / 256 MB |
| `DlqHandlerFunction` | `backend/reliability/dlq_handler/` | 10 s / 128 MB |

No `Events`, no `Policies`, and no layers yet: phases 2–3 add them. Deploy with `sam deploy --resolve-image-repos` (SAM creates and manages the ECR repo).

### 4.10 Outputs
```yaml
Outputs:
  UploadBucketName:    {Value: !Ref UploadBucket}
  WebBucketName:       {Value: !Ref WebBucket}
  DistributionId:      {Value: !Ref WebDistribution}
  DistributionDomain:  {Value: !GetAtt WebDistribution.DomainName}
  JobsTableName:       {Value: !Ref JobsTable}
  CandidatesTableName: {Value: !Ref CandidatesTable}
  FailedJobsTableName: {Value: !Ref FailedJobsTable}
  ConfigTableName:     {Value: !Ref ConfigTable}
  IngestionQueueUrl:   {Value: !Ref IngestionQueue}
  ScoringQueueUrl:     {Value: !Ref ScoringQueue}
  UserPoolId:          {Value: !Ref UserPool}
  UserPoolClientId:    {Value: !Ref UserPoolClient}
  AlertsTopicArn:      {Value: !Ref AlertsTopic}
  # ApiBaseUrl is added in phase 3
```

---

## 5. `samconfig.toml`

```toml
version = 0.1
[dev.deploy.parameters]
stack_name = "resume-screener-dev"
region = "ap-south-1"
capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"
resolve_s3 = true
resolve_image_repos = true
parameter_overrides = "EnvName=dev SesSenderAddress=<verified> CreateBudget=true"
confirm_changeset = true

[prod.deploy.parameters]
stack_name = "resume-screener-prod"
region = "ap-south-1"
capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"
resolve_s3 = true
resolve_image_repos = true
parameter_overrides = "EnvName=prod SesSenderAddress=<verified> CreateBudget=false"
confirm_changeset = true
```
Build: `sam build --use-container` · Deploy: `sam deploy --config-env dev`.

---

## 6. Deploy IAM user (T-009, manual — document in `infra/README.md`)

A dedicated IAM user (or, better, an IAM Identity Center permission set) for the humans and agents running SAM. Scope it to the project's resource name patterns (`resume-screener-*`, `rs-*`, `*-dev`/`*-prod` tables, `aws-sam-cli-managed-default*`):

| Service | Actions |
|---|---|
| CloudFormation | `*` on `resume-screener-*` and `aws-sam-cli-managed-default` stacks; `ValidateTemplate`, `CreateChangeSet` on `aws:transform/Serverless-2016-10-31` |
| S3 | `*` on project buckets and the SAM managed artifact bucket |
| DynamoDB, SQS, SNS, Cognito IdP, Logs | `*` on project resource ARNs (Cognito `CreateUserPool` needs `*`) |
| Lambda | `CreateFunction`, `GetFunction*`, `UpdateFunction*`, `DeleteFunction`, `AddPermission`, `RemovePermission`, `*EventSourceMapping*`, `PublishLayerVersion`, `GetLayerVersion`, `DeleteLayerVersion`, `TagResource`, `ListTags` |
| ECR | Repository lifecycle + push actions on `resume-screener*` repos; `GetAuthorizationToken` (`*`) |
| IAM | `CreateRole`, `DeleteRole`, `GetRole`, `PassRole`, `PutRolePolicy`, `DeleteRolePolicy`, `AttachRolePolicy`, `DetachRolePolicy`, `TagRole`, `UntagRole` on `resume-screener-*` roles |
| CloudFront | Distribution, OAC, and response-headers-policy CRUD; `CreateInvalidation` |
| Budgets / CloudWatch | `budgets:*` (account), `cloudwatch:PutMetricAlarm`, `DeleteAlarms`, `DescribeAlarms` |
| API Gateway, SES | Added in phase 3 |

**Never granted to the deploy user:** `lambda:InvokeFunction` (a runtime permission that belongs only in execution roles), `textract:*`, `comprehend:*`. Expect `AccessDenied` on the first deploys. Add the single missing action and log it in the README, rather than widening to `*`.

---

## 7. Definition of Done

Run each check; paste the outputs into the PR description.

- [ ] Spikes T-001–T-006 recorded in `infra/README.md`; D-34 outcome recorded in `Memory.md`
- [ ] `sam validate --lint` clean; `sam build --use-container && sam deploy --config-env dev` succeeds with the deploy user
- [ ] `aws s3api get-public-access-block` → all four `true` on **both** buckets; website hosting **not** configured (`get-bucket-website` → `NoSuchWebsiteConfiguration`)
- [ ] `https://<DistributionDomain>/` serves the placeholder; `http://` redirects; the direct S3 object URL returns 403
- [ ] `curl -I` on the distribution shows `strict-transport-security` and `content-security-policy`
- [ ] `aws s3api get-bucket-cors` on the upload bucket lists the CloudFront origin (and localhost in dev only)
- [ ] 4 tables exist; `jobs` has `RecruiterJobsIndex`; `candidates` has **no** GSI; `failed_jobs` TTL enabled on `expires_at`
- [ ] Config row `nlp_engine_mode = spacy_hybrid` present
- [ ] 4 queues; redrive policies linked (3 / 5); DLQ retention 14 days; queue policy present
- [ ] Cognito: self sign-up disabled (a `sign-up` CLI call fails); Recruiter×2, Admin×1, groupless×1 users can sign in
- [ ] `ExtractionFunction` shows Package type **Image**, architecture **x86_64**; all 14 functions return 501; every log group has 30-day retention
- [ ] SNS topic exists; budget exists in exactly one stack
- [ ] `grep -ri "textract\|comprehend" template.yaml backend/` → no matches
- [ ] `infra/README.md` documents prerequisites, spike results, the deploy user, and the user-creation script

Once every box is checked, hand off to **`02-ingestion-pipeline.md`**.
