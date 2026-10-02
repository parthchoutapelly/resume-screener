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
