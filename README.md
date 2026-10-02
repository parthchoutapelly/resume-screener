# AI-Powered Resume Screener & Talent Acquisition Pipeline

An AWS-based serverless recruitment platform that automates resume ingestion, document extraction, NLP-based candidate analysis, explainable candidate scoring, recruiter decisions, and candidate export.

The system allows a recruiter to create a job, define its requirements, upload a batch of resumes, and automatically receive processed candidates ranked against the job requirements.

---

## Live Application

**Live Website:**  
https://d1yg427uu45noj.cloudfront.net

**AWS Region:** `ap-south-1`

**Environment:** `dev`

**API Gateway:**  
`https://qdcgssdx9l.execute-api.ap-south-1.amazonaws.com/dev`

> The application is deployed on AWS. The frontend is delivered through Amazon CloudFront, while the backend uses API Gateway, Lambda, S3, SQS, DynamoDB, Cognito, SNS, SES, and CloudWatch.

---

# 1. Project Overview

Recruiters often need to manually review large numbers of resumes against a single job description. This process is time-consuming and makes it difficult to consistently compare candidates.

This project automates that workflow.

A recruiter can:

1. Create a job requisition.
2. Define required skills, preferred titles, minimum experience, and screening threshold.
3. Upload multiple resumes.
4. Automatically extract resume content.
5. Process the extracted text using NLP.
6. Identify candidate information such as name, email, skills, titles, and experience.
7. Score each candidate against the job requirements.
8. Review an explainable candidate breakdown.
9. Shortlist or reject candidates.
10. Export candidate results as CSV.
11. Monitor failed processing jobs through an administrative failures view.

The system is designed as a serverless AWS pipeline with asynchronous processing, retries, dead-letter queues, monitoring, authentication, authorization, and failure handling.

---

# 2. Key Features

## Recruiter Features

- Create and manage job requisitions
- Upload job descriptions
- Upload multiple resumes
- Support PDF, DOCX, and image-based documents
- Process native and scanned documents
- Automatic candidate extraction
- NLP-based skill and title matching
- Deterministic experience calculation
- Explainable candidate scoring
- Candidate ranking
- Matched and missing skills
- Shortlist candidates
- Reject candidates
- Edit job requirements and rescore candidates
- Export candidate results to CSV
- Processing status tracking
- Failure status visibility

## Administration

- Cognito-based authentication
- Recruiter/Admin roles
- Admin-only failure monitoring
- Processing failure visibility
- SQS dead-letter queues
- CloudWatch alarms
- SNS notifications

## Reliability

- SQS-based asynchronous processing
- Retry handling
- Ingestion DLQ
- Scoring DLQ
- Failure persistence
- Duplicate-event protection
- Terminal failure states
- Processing status tracking

## Security

- Amazon Cognito authentication
- Role/group-based authorization
- Recruiter job isolation
- Private S3 buckets
- API authorization
- CORS restrictions
- HTTPS/TLS
- Security headers
- Upload validation
- CSV injection protection
- XSS-safe rendering
- PII-conscious logging
- Least-privilege IAM policies

---

# 3. High-Level Architecture

```text
                         ┌───────────────────────┐
                         │       Recruiter       │
                         │     / Administrator   │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   React + Vite Web    │
                         │      Application       │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │     Amazon Cognito     │
                         │ Authentication / Roles │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │     API Gateway       │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   API Lambda Functions │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │      DynamoDB         │
                         │ Jobs / Candidates /   │
                         │ Config / Failed Jobs  │
                         └───────────────────────┘


Resume Upload Pipeline
────────────────────────────────────────────────────────────

     Resume
       │
       ▼
┌───────────────┐
│   Amazon S3   │
│ Upload Bucket │
└───────┬───────┘
        │
        ▼
┌───────────────────┐
│  SQS Ingestion    │
│      Queue        │
└─────────┬─────────┘
          │
          ▼
┌────────────────────────┐
│ Document Extraction    │
│       Lambda           │
│                        │
│ PDF / DOCX / Image     │
│ OCR / Text Extraction  │
└──────────┬─────────────┘
           │
           │ Synchronous Lambda Invoke
           ▼
┌────────────────────────┐
│      NLP Lambda        │
│                        │
│ spaCy NER              │
│ Skill Matching         │
│ Title Matching         │
│ Experience Detection   │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│       DynamoDB         │
│ Candidate Information  │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│    SQS Scoring Queue   │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│   ScoreMatch Lambda    │
│                        │
│ Skills      50%        │
│ Title       30%        │
│ Experience  20%        │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────┐
│       DynamoDB         │
│ Scores / Decisions     │
└────────────────────────┘


Failure / Operations
────────────────────────────────────────────────────────────

SQS Ingestion Queue ───────► Ingestion DLQ
                                      │
                                      ▼
                              DLQ Handler Lambda

SQS Scoring Queue ─────────► Scoring DLQ
                                      │
                                      ▼
                              DLQ Handler Lambda

Lambda / SQS / DLQ
        │
        ▼
   CloudWatch
        │
        ▼
       SNS
        │
        ▼
     Alerts

4. AWS Services Used
Service	Purpose
Amazon S3	Resume and job-description storage
Amazon CloudFront	Frontend delivery
Amazon Cognito	Authentication and role/group management
Amazon API Gateway	REST API
AWS Lambda	Extraction, NLP, scoring, API and operational functions
Amazon SQS	Asynchronous ingestion and scoring queues
Amazon SQS DLQ	Failed message isolation
Amazon DynamoDB	Jobs, candidates, configuration and failure records
Amazon SNS	Operational notifications
Amazon SES	Candidate/recruiter email notifications
Amazon CloudWatch	Logs, metrics and alarms
Amazon ECR	Lambda container images
AWS SAM	Infrastructure-as-code and deployment
AWS IAM	Least-privilege permissions


5. Document Processing
The project uses genuine document processing rather than treating resume text as pre-extracted fixture data.
Supported Inputs
- Native PDF
- Scanned PDF
- Mixed PDF
- DOCX
- PNG/image documents
Extraction Technologies
The extraction pipeline uses open-source document-processing components:
- pypdf
- python-docx
- PyMuPDF
- Tesseract OCR
The extraction Lambda is deployed as a container image because the required native/document-processing dependencies are too large for a conventional Lambda ZIP/layer deployment.
The extraction stage produces structured output containing the extracted text and extraction metadata.
6. NLP Processing
The NLP stage uses spaCy and deterministic matching logic.
The pipeline extracts and identifies:
- Candidate name
- Email address
- Skills
- Previous job titles
- Experience
- Relevant entities
NLP Techniques
Named Entity Recognition
spaCy NER is used where appropriate for entity extraction.
Skill Matching
A hybrid approach is used for skills:
- Dictionary-based matching
- Phrase matching
- Normalized skill names
- Matching against required job skills
Title Matching
Candidate job titles are compared with job-required titles.
The system also supports related title families so that semantically related titles can contribute to the title score.
Experience
Experience is calculated using deterministic rules based on detected employment/date information.
The experience calculation is intentionally explainable rather than relying on an opaque model.
7. Candidate Scoring
The project uses scoring version v1.
The overall candidate score is calculated from three components:
Overall Score =
    Skills Score      × 50%
  + Title Score       × 30%
  + Experience Score  × 20%

Skills — 50%
Measures how many of the required job skills are present in the candidate profile.
Title — 30%
Measures relevance between the candidate's previous titles and the titles specified by the recruiter.
Related title families are also considered.
Experience — 20%
Compares the candidate's calculated experience with the minimum experience requirement.
8. Explainability
The system does not only provide a final percentage.
For every scored candidate, the recruiter can inspect:
- Overall score
- Skills score
- Title score
- Experience score
- Matched skills
- Missing skills
- Extracted experience
- Titles held
- Processing status
- Recruiter decision
This allows the recruiter to understand why a candidate received a particular score.
The score is intended to support recruiter decision-making rather than replace the recruiter.
9. Backend Data Model
The application uses DynamoDB for its core application data.
Jobs
Stores:
- Job ID
- Recruiter information
- Job title
- Job description
- Required skills
- Required titles
- Minimum experience
- Shortlist threshold
- Job status
- Processing state
Candidates
Stores:
- Candidate ID
- Job ID
- Resume information
- Candidate name
- Email
- Extracted skills
- Titles
- Experience
- Processing status
- Scoring status
- Overall score
- Skill score
- Title score
- Experience score
- Matched skills
- Missing skills
- Recruiter decision
- Notification status
- Scoring version
Failed Jobs
Stores operational failure information, including:
- Failure type
- Processing stage
- Error state
- Retry/exhaustion information
- Failure metadata
Config
Stores configurable application/NLP settings.
10. API
The recruiter application communicates with the backend through Amazon API Gateway.
Important API operations include:
POST   /jobs
GET    /jobs
GET    /jobs/{job_id}
PATCH  /jobs/{job_id}
GET    /jobs/{job_id}/candidates
POST   /jobs/{job_id}/candidates/{candidate_id}/decision
GET    /jobs/{job_id}/export
GET    /failed-jobs

Additional upload and resume-related endpoints support presigned S3 uploads and candidate document access.
Authentication is handled using Amazon Cognito tokens.
11. Frontend
The frontend is built using:
- React
- Vite
- JavaScript/TypeScript components
- Amazon Cognito authentication
- REST API integration
The UI is designed as a recruiter operations console rather than a generic dashboard.
Major screens include:
- Login
- Jobs pipeline
- Create job
- Job details
- Candidate list
- Candidate details
- Requirements editing
- Resume upload
- Decisions
- CSV export
- Admin failures view
The frontend is deployed to a private S3 web bucket and delivered through CloudFront.
12. Authentication & Authorization
Amazon Cognito provides authentication.
The application supports role-based access through Cognito groups:
Recruiter
Admin

Recruiters can access their permitted recruitment workflows.
Administrative operations such as the failed-jobs view are restricted to the Admin role.
Cross-recruiter access to another recruiter's job resources is rejected.
13. Reliability & Failure Handling
The system was designed to handle processing failures without losing messages silently.
The ingestion and scoring pipelines use:
SQS
  │
  ├── Retry
  │
  ├── Retry
  │
  ├── Retry
  │
  └── DLQ

The DLQ handler processes exhausted failures and makes operational failures visible to administrators.
CloudWatch alarms are configured for important failure conditions.
Tested failure scenarios include:
- Unsupported document format
- Corrupt PDF
- Encrypted PDF
- Blank scanned document
- Too many pages
- Missing upload
- Failed job description
- Job description without required skills
- Transient ingestion failure
- Scoring failure
- Duplicate events
- Decision on an unscored candidate
- Candidate without an email address
14. Security
Security validation covered authentication, authorization, storage, API, browser, logging and IAM behavior.
The security test suite covered:
- Unauthenticated API access
- Groupless authenticated users
- Cross-recruiter isolation
- Admin-only routes
- CORS behavior
- Private S3 buckets
- TLS-only access
- Upload size restrictions
- CSV injection
- XSS payload handling
- PII exposure in logs
- IAM policy validation
- Removal of managed-AI service references
- Cognito self-signup restrictions
- Security headers
S3 buckets are configured as private resources and the frontend is delivered through CloudFront rather than public S3 website hosting.
15. Testing
The project includes unit, component, integration, security, failure-path, NLP evaluation and frontend testing.
Automated Test Results
Final verification included:
Test Area	Result
Python Unit Tests	246 / 246
rs_common Coverage	94%
Component Tests	143 / 143
Frontend Tests	14 / 14
Integration Tests	31 / 31
Security Checks	S1–S15 verified
Failure Matrix	F1–F13 verified
Accessibility	0 Critical / 0 Serious
Skill Precision	0.910
Skill Recall	1.000
Name Accuracy	10 / 10
Experience Accuracy	9 / 9
Title Hit Rate	10 / 10


The integration suite validates the complete workflow from authenticated job creation and resume upload through processing, scoring, recruiter decisions, notification behavior and CSV export.
16. NLP Evaluation
The NLP evaluation uses a separate truth dataset rather than evaluating the system only against its own output.
The evaluation measures:
- Skill precision
- Skill recall
- Name accuracy
- Experience accuracy
- Title hit rate
Final evaluation:
Skill Precision:      0.910
Skill Recall:         1.000
Name Accuracy:        10/10
Experience Accuracy:  9/9
Title Hit Rate:       10/10

The evaluation process also records causes for extraction misses, such as:
- Dictionary gaps
- OCR noise
- NER misses
- Section detection issues
17. Accessibility
The frontend was tested using automated accessibility checks and keyboard navigation.
The final accessibility verification reported:
Critical issues: 0
Serious issues:  0
Moderate issues: 5
Minor issues:    0

Keyboard navigation was also verified across the primary recruiter workflows.
18. Integration Test
The full integration test uses a mixed document set containing:
- Native PDFs
- Scanned PDF
- Mixed PDF
- DOCX
- PNG
- Unsupported renamed document
The test verifies that:
6 candidates → successfully scored
1 candidate  → correctly rejected as unsupported

It also validates:
- Candidate sub-scores
- Matched skills
- scoring_version = v1
- Worked scoring example
- Recruiter decisions
- Email notification behavior
- CSV export
- Failure records
19. Demo Workflow
The recommended live demonstration is:
1. Login
      ↓
2. Create a job
      ↓
3. Add job requirements
      ↓
4. Upload resumes
      ↓
5. Show processing
      ↓
6. Show candidate scores
      ↓
7. Open candidate details
      ↓
8. Explain matched/missing skills
      ↓
9. Shortlist / Reject
      ↓
10. Export CSV
      ↓
11. Show Admin / Failures

A cybersecurity recruitment dataset is available for the primary demonstration.
A second Cloud/DevOps dataset is available as an alternate mentor/demo dataset.
20. Example Demo Job
Cybersecurity Engineer
Minimum Experience
3 years
Screening Threshold
50%
Required Skills
SIEM
SOC
Splunk
AWS
IAM
Python
Incident Response
Threat Detection
Vulnerability Management
Linux
EDR
Firewall

Relevant Titles
Cybersecurity Engineer
Security Engineer
SOC Analyst
Information Security Engineer
Cybersecurity Analyst

The demo dataset contains four synthetic resumes designed to produce different levels of skill, title and experience matching.
21. Project Structure
resume-screener/
│
├── backend/
│   ├── functions/
│   │   ├── extraction/
│   │   ├── nlp/
│   │   ├── scoring/
│   │   ├── api/
│   │   └── dlq/
│   │
│   ├── layers/
│   └── common/
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.*
│
├── tests/
│   ├── unit/
│   ├── component/
│   ├── integration/
│   └── fixtures/
│
├── scripts/
│   ├── evaluate.py
│   ├── validate_data.py
│   └── capture_sample_output.py
│
├── docs/
│   ├── Memory.md
│   ├── PRD.md
│   ├── Rules.md
│   ├── Architecture.md
│   ├── 01-infrastructure-setup.md
│   ├── 02-ingestion-pipeline.md
│   ├── 03-scoring-and-api.md
│   ├── 04-frontend-dashboard.md
│   ├── 05-integration-testing-and-delivery.md
│   ├── deliverables.md
│   ├── evaluation.md
│   ├── demo.md
│   ├── evidence/
│   └── sample-nlp-output/
│
├── infra/
│   └── README.md
│
├── template.yaml
├── Makefile
├── requirements.txt
└── README.md

22. Development Environment
Requirements
Recommended prerequisites:
- Python 3.12
- Node.js / npm
- AWS CLI
- AWS SAM CLI
- Docker
- Git
- AWS credentials with the required deployment permissions
Verify:
python3 --version
node --version
npm --version
aws --version
sam --version
docker --version

23. Local Setup
Clone the repository:
git clone https://github.com/parthchoutapelly/Resume-Screener.git
cd Resume-Screener

Create the Python environment:
make venv

Run linting:
make lint

Run tests:
make test

24. AWS Build
The project uses AWS SAM for infrastructure and deployment.
Build the application:
make build ENV=dev

Equivalent SAM command:
sam build --use-container

The --use-container option is important because the project contains Lambda dependencies that require a compatible Linux build environment.
25. AWS Deployment
Deploy the development environment:
make deploy ENV=dev

or:
sam deploy --config-env dev

The primary deployment stack is:
resume-screener-dev

AWS Region:
ap-south-1

26. Configuration
The project uses AWS SAM parameters and environment configuration for deployment-specific settings.
The development environment contains resources such as:
S3 buckets
DynamoDB tables
SQS queues
SQS DLQs
Lambda functions
Cognito
API Gateway
SNS
SES
CloudWatch alarms
CloudFront
ECR

Do not commit:
- AWS access keys
- Cognito passwords
- Secrets
- Environment-specific credentials
- Personal credentials
27. NLP Configuration
The project includes a configuration/seed mechanism for NLP settings.
Seed the development configuration:
make seed ENV=dev

This initializes the required NLP engine configuration in DynamoDB.
28. Useful Development Commands
Lint
make lint

Tests
make test

Build
make build ENV=dev

Deploy
make deploy ENV=dev

Seed configuration
make seed ENV=dev

Validate data
python scripts/validate_data.py

NLP evaluation
python scripts/evaluate.py --env dev

Integration test
python tests/integration/run.py --env dev

29. Deployment Information
Current development deployment:
Stack:
resume-screener-dev

Region:
ap-south-1

CloudFront Distribution:
E19GPCBPKSYGJG

CloudFront Domain:
d1yg427uu45noj.cloudfront.net

API Gateway:
rs-api-dev

API ID:
qdcgssdx9l

API Stage:
dev

Frontend web bucket:
resume-screener-web-dev-331262815638

The frontend bucket is private and is accessed through CloudFront.
30. AWS Account / Free-Tier Design Considerations
The project was developed with AWS account/resource constraints in mind.
During development, managed AI services such as Amazon Textract and Amazon Comprehend were not relied upon because of account/service availability constraints.
Instead, the project uses open-source document extraction and NLP components:
Document Processing:
pypdf
python-docx
PyMuPDF
Tesseract OCR

NLP:
spaCy

This allows the system to demonstrate genuine document extraction and NLP while remaining deployable under the project's AWS constraints.
The architecture maintains a provider boundary so that managed AWS AI services can be introduced later if the AWS account is upgraded or those services become available.
31. Known Limitation
The Phase 5 load-test harness supports a 50-resume workload consisting of:
35 native PDFs
10 scanned PDFs
5 DOCX files

The 50-resume live burst was not executed because of AWS regional unreserved-concurrency constraints.
The load harness itself was validated, but the project does not claim a successful live 50-resume burst.
This limitation was documented rather than changing the production architecture solely to satisfy the test.
All other Phase 5 integration, failure, security, NLP and accessibility gates were completed.
32. Future Enhancements
The project identifies three primary future enhancements.
F1 — Custom NER
Train or fine-tune a domain-specific NER model for:
- Skills
- Organizations
- Job titles
- Certifications
- Employment dates
This would improve extraction accuracy for resumes with unusual formatting.
F2 — Cover Letter Sentiment
Add optional cover-letter analysis as a soft signal.
This should not replace objective candidate requirements and should remain separate from the primary screening score.
F3 — Blind Screening & Parity Dashboard
Introduce optional blind screening features that hide selected identifying information during initial review.
A parity dashboard could provide aggregate monitoring of screening outcomes and help identify potential disparities in the screening pipeline.
33. Project Limitations
The current implementation has several intentional limitations:
- NLP is based on open-source models and deterministic matching rather than a large proprietary language model.
- Skill extraction depends partly on the configured skill dictionary.
- OCR quality depends on document quality and scan quality.
- Resume formatting can affect extraction.
- Experience calculation uses deterministic date/rule logic and can have limitations with ambiguous employment histories.
- Title matching uses configured title families rather than semantic LLM reasoning.
- The current scoring model is intentionally explainable rather than a learned ranking model.
- The live 50-resume burst test was not executed because of AWS regional concurrency constraints.
- The current solution is a technical screening aid and does not replace recruiter judgment.
34. Licenses & Third-Party Components
The project uses open-source libraries for document processing and NLP.
Important third-party components include:
- spaCy
- PyMuPDF
- pypdf
- python-docx
- Tesseract OCR
Licensing requirements and limitations of third-party dependencies should be reviewed before commercial redistribution.
In particular, PyMuPDF's AGPL licensing implications must be considered for deployment and distribution scenarios.
35. Team
Parth Choutapelly
Project lead / architecture / AWS infrastructure / integration / frontend / final sign-off
Allen Scott
Testing and validation
Tejesh Geda
Testing and validation
Gaurav Yewale
Documentation and deliverables
36. Project Phases
Phase 1 — Infrastructure
Implemented:
- AWS SAM infrastructure
- S3
- DynamoDB
- SQS
- DLQs
- Cognito
- SNS
- Lambda foundations
- IAM
Status:
Completed and deployed
Phase 2 — Ingestion Pipeline
Implemented:
- Real document extraction
- PDF processing
- DOCX processing
- OCR
- spaCy NLP
- Skill extraction
- Title extraction
- Experience extraction
- Failure handling
Status:
Completed and deployed
Phase 3 — Scoring, API & Reliability
Implemented:
- Candidate scoring
- Scoring version v1
- Recruiter REST API
- Cognito authorization
- CORS
- DLQ handler
- CloudWatch alarms
- Recruiter decisions
- CSV export
Status:
Completed and deployed
Phase 4 — Frontend Dashboard
Implemented:
- React recruiter dashboard
- Authentication
- Job pipeline
- Job creation
- Resume upload
- Candidate ranking
- Candidate details
- Requirements editing
- Recruiter decisions
- CSV export
- Admin failure view
- CloudFront deployment
Status:
Completed and deployed
Phase 5 — Integration Testing & Delivery
Implemented and verified:
- Automated test gates
- End-to-end integration
- Failure matrix
- Security verification
- NLP evaluation
- Accessibility testing
- Load-test harness
- Sample NLP outputs
- Final documentation
- Demo workflow
Status:
Completed
The live 50-resume burst remains documented as a test limitation due to AWS regional concurrency constraints.
37. Final Project Status
╔══════════════════════════════════════════════════════╗
║              PROJECT STATUS: COMPLETE               ║
╠══════════════════════════════════════════════════════╣
║ Infrastructure                  ✓                   ║
║ Document Extraction             ✓                   ║
║ OCR                             ✓                   ║
║ NLP Processing                  ✓                   ║
║ Candidate Scoring               ✓                   ║
║ Recruiter API                   ✓                   ║
║ Authentication                  ✓                   ║
║ Frontend Dashboard              ✓                   ║
║ CloudFront Deployment           ✓                   ║
║ Failure Handling                ✓                   ║
║ Security Verification           ✓                   ║
║ NLP Evaluation                  ✓                   ║
║ Accessibility                   ✓                   ║
║ Integration Testing             ✓                   ║
║ Documentation                   ✓                   ║
║ Live 50-Resume Burst            Documented Limit.   ║
╚══════════════════════════════════════════════════════╝

38. Documentation
The complete project specification and implementation documentation is available under:
docs/

Important documents:
docs/Memory.md
docs/PRD.md
docs/Rules.md
docs/Architecture.md

docs/01-infrastructure-setup.md
docs/02-ingestion-pipeline.md
docs/03-scoring-and-api.md
docs/04-frontend-dashboard.md
docs/05-integration-testing-and-delivery.md

docs/deliverables.md
docs/evaluation.md
docs/demo.md

Evidence generated during validation is stored under:
docs/evidence/

Sample NLP outputs are stored under:
docs/sample-nlp-output/

39. Demo Credentials
For development/demo use only.
Recruiter
Username:
recruiter.a@example.com

Password:
TestPass123!

Administrator
Username:
admin@example.com

Password:
AdminPass123!

These credentials are intended only for the deployed development/demo environment. They should never be reused as production credentials.

40. Quick Demo
Open:
https://d1yg427uu45noj.cloudfront.net
Login using the recruiter demo account.
Recommended flow:
Login
  ↓
Jobs Pipeline
  ↓
Create New Requisition
  ↓
Cybersecurity Engineer
  ↓
Upload Demo Resumes
  ↓
Wait for Processing
  ↓
Open Candidates
  ↓
Review Scores
  ↓
Open Candidate Details
  ↓
Shortlist / Reject
  ↓
Export CSV

41. Summary
The AI-Powered Resume Screener & Talent Acquisition Pipeline demonstrates a complete serverless recruitment workflow on AWS.
The system combines:
React
   +
AWS CloudFront
   +
Amazon Cognito
   +
API Gateway
   +
Lambda
   +
S3
   +
SQS
   +
DynamoDB
   +
spaCy
   +
Tesseract OCR
   +
CloudWatch
   +
SNS / SES

to transform uploaded resumes into structured candidate profiles and explainable screening results.
The project focuses on:
- Real document processing
- Genuine OCR
- Practical NLP
- Explainable scoring
- Serverless AWS architecture
- Secure recruiter workflows
- Reliable asynchronous processing
- Failure isolation
- Operational monitoring
- Human-in-the-loop decisions
The result is an end-to-end recruitment screening platform that can be demonstrated through a live AWS deployment and extended with more advanced NLP, screening, and analytics capabilities in future iterations.
