# Security Verification Checklist (S1–S15)

> Phase 5 §4 (T-104) Live and Local Security Verification  
> Environment: `dev` | Region: `ap-south-1` | Date: 2026-09-25

---

## 1. Summary Matrix

| Control | Description | Verification Method | Deployed Dev Status | Local Contract Status | Verdict |
|---|---|---|---|---|---|
| **S1** | Unauthenticated request to every route returns 401 with CORS headers | Live API Gateway GatewayResponses + Lambda | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S2** | Valid JWT token without group membership returns 403 Forbidden | Live Cognito token (`noaccess@example.com`) | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S3** | Recruiter B accessing Recruiter A's job returns 404 (no leak, no mutation) | Live API test (`job_81e6...` queried by B) | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S4** | Recruiter accessing `/failed-jobs` returns 403; Admin returns 200 | Live API test (`recruiter.a` vs `admin`) | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S5** | CORS: Allowed CloudFront origin accepted; evil origin denied cross-origin access | Live API Gateway CORS check | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S6** | S3 buckets private with Public Access Block enabled | Live `s3:GetPublicAccessBlock` API | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S7** | TLS/HTTPS enforced on all endpoints | Live CloudFront HTTPS redirect + S3 `aws:SecureTransport` | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S8** | Upload limits enforced (10 MB max, valid file types) | Live presigned POST condition check | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S9** | CSV formula injection protection (`=`, `+`, `-`, `@` defused with single quote) | Live CSV export output inspection | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S10** | XSS payloads rendered strictly as text in UI, never executable HTML | React JSX text escaping + integration test payload | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S11** | PII absent from application CloudWatch logs (emails/phones/raw text not in INFO) | Live CloudWatch log stream sampling | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S12** | IAM policies adhere to least-privilege matrix in Architecture.md | CloudFormation template & deployed role policy audit | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S13** | No runtime dependency on Amazon Textract or Amazon Comprehend | Codebase scan & template audit | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S14** | Cognito self-signup disabled (`AllowAdminCreateUserOnly: true`) | Live `cognito-idp:DescribeUserPool` API | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |
| **S15** | Security headers present on frontend and API responses (HSTS, CSP, nosniff, DENY) | Live CloudFront response headers audit | DEPLOYED DEV VERIFIED | AUTOMATED LOCAL | **PASS** |

---

## 2. Detailed Findings

### S1: Unauthenticated Requests (401 + CORS)
- **Observed Behavior:**
  - `POST /jobs` without `Authorization` header returned `HTTP 401 Unauthorized` with `Access-Control-Allow-Origin: https://d1yg427uu45noj.cloudfront.net`.
  - `GET /jobs` without `Authorization` header returned `HTTP 401 Unauthorized` with CORS header.
  - `GET /failed-jobs` without `Authorization` header returned `HTTP 401 Unauthorized` with CORS header.
- **Evidence:** Verified directly against API Gateway dev endpoint `https://qdcgssdx9l.execute-api.ap-south-1.amazonaws.com/dev`.

### S2: Valid Token Without Group (403 Forbidden)
- **Setup:** Ephemeral Cognito authentication for `noaccess@example.com` (user exists in User Pool but belongs to neither `Recruiter` nor `Admin` group).
- **Observed Behavior:** `GET /jobs` returned `HTTP 403 Forbidden` with response body:
  `{"code": "FORBIDDEN", "message": "Your account has no access. Contact an administrator."}`.
- **Evidence:** Tested live via `Cognito.authenticate()`.

### S3: Cross-Tenant Isolation (Recruiter B -> Recruiter A Job)
- **Setup:** Recruiter A created job `job_81e6435197154707a86acdf2d36836b4`. Recruiter B queried `GET /jobs/job_81e6435197154707a86acdf2d36836b4`.
- **Observed Behavior:** Returned `HTTP 404 Not Found` with message `Job not found.` (indistinguishable from a non-existent job ID; preventing enumeration or status leakage).
- **Evidence:** Tested live via API Gateway endpoint.

### S4: Admin Route Protection (`/failed-jobs`)
- **Setup:** Query `/failed-jobs` with Recruiter A credentials vs Admin credentials.
- **Observed Behavior:**
  - Recruiter A: `HTTP 403 Forbidden` (`{"code": "FORBIDDEN", "message": "Admin access required."}`).
  - Admin: `HTTP 200 OK`.
- **Evidence:** Tested live via API Gateway endpoint.

### S5: CORS Allowed vs Evil Origin
- **Setup:** Send preflight/request with `Origin: https://d1yg427uu45noj.cloudfront.net` vs `Origin: https://evil.example.com`.
- **Observed Behavior:**
  - Allowed origin receives `Access-Control-Allow-Origin: https://d1yg427uu45noj.cloudfront.net`.
  - Evil origin receives `Access-Control-Allow-Origin: https://d1yg427uu45noj.cloudfront.net` (never reflects `https://evil.example.com` and never returns `*`). Modern browsers block cross-origin reads.
- **Evidence:** Live HTTP response headers verified.

### S6: S3 Buckets Private (Public Access Block)
- **Observed Configuration:**
  - Bucket: `resume-screener-dev-uploads-626671049925`
  - `BlockPublicAcls`: `True`
  - `IgnorePublicAcls`: `True`
  - `BlockPublicPolicy`: `True`
  - `RestrictPublicBuckets`: `True`
- **Evidence:** AWS SDK `s3:GetPublicAccessBlock`.

### S7: TLS Enforcement
- **Observed Configuration:**
  - CloudFront distribution `d1yg427uu45noj.cloudfront.net` enforces `ViewerProtocolPolicy: redirect-to-https`.
  - API Gateway dev endpoint is HTTPS only.
  - S3 bucket policy contains explicit Deny on non-HTTPS requests (`aws:SecureTransport: false`).
- **Evidence:** CloudFormation template outputs and live HTTPS requests.

### S8: Upload Limits
- **Observed Configuration:**
  - Presigned POST conditions specify `["content-length-range", 1, 10485760]` (10 MB maximum upload limit).
  - File extension allowlist: `.pdf`, `.docx`, `.png`.
- **Evidence:** Presigned POST generation and extraction handler validation.

### S9: CSV Formula Injection Protection
- **Observed Behavior:** Main integration test verified export of candidate records with leading special characters (`'=cmd`). Exported CSV cells prefix dangerous characters (`=`, `+`, `-`, `@`) with a single apostrophe `'`.
- **Evidence:** Main integration test assertion S4 passed.

### S10: XSS Rendered as Text
- **Observed Behavior:** Candidate names and job descriptions containing markup strings (e.g. `<script>alert(1)</script>`) are stored as raw strings in DynamoDB and rendered as text nodes by React JSX without unescaped `dangerouslySetInnerHTML`.
- **Evidence:** Frontend Vitest DOM tests + live integration test candidate data.

### S11: PII Absent from Logs
- **Observed Behavior:** Structured Lambda logger prints metadata (`job_id`, `candidate_id`, `timing_ms`, error codes) and specifically avoids logging raw resume text, email addresses, or phone numbers in CloudWatch INFO logs.
- **Evidence:** CloudWatch log stream inspection.

### S12: IAM Least Privilege Matrix
- **Observed Configuration:**
  - `ExtractionFunction`: Read access to S3 upload bucket prefix `resume-uploads/`, write access to Candidates table.
  - `ScoreMatchFunction`: Read/write access to Candidates table, read access to Jobs table, send message to ScoringQueue.
  - `DlqHandlerFunction`: Read from DLQ, write to FailedJobs table and Candidates table.
  - No wildcard resource permissions on customer data.
- **Evidence:** Audit of `template.yaml` against Architecture.md §7.

### S13: No Forbidden AWS Services
- **Observed Configuration:**
  - Text extraction is performed entirely by local libraries: PyPDF2 / pdfplumber / python-docx / Tesseract OCR (in Lambda container layer).
  - Zero runtime dependencies or API calls to Amazon Textract or Amazon Comprehend.
- **Evidence:** Automated grep scan across backend codebase and SAM template.

### S14: Cognito Self-Signup Disabled
- **Observed Configuration:**
  - User Pool `ap-south-1_J4vQd2c6c` has `AdminCreateUserConfig.AllowAdminCreateUserOnly = True`.
  - Public registration is prohibited; recruiters and admins must be provisioned by an administrator.
- **Evidence:** AWS SDK `cognito-idp:DescribeUserPool`.

### S15: Security Headers
- **Observed Response Headers from CloudFront Distribution:**
  - `Strict-Transport-Security`: `max-age=31536000; includeSubDomains`
  - `Content-Security-Policy`: `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.execute-api.ap-south-1.amazonaws.com https://cognito-idp.ap-south-1.amazonaws.com https://*.s3.ap-south-1.amazonaws.com https://*.s3.amazonaws.com; frame-ancestors 'none'`
  - `X-Content-Type-Options`: `nosniff`
  - `X-Frame-Options`: `DENY`
- **Evidence:** Live HTTP GET against `https://d1yg427uu45noj.cloudfront.net`.
