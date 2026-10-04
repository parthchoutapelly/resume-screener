# Artillery Load Test Report — Serverless Portfolio & API Gateway

> **Deliverable 5 — Load & Performance Testing**
> **Target Service**: REST API Gateway & Serverless Backend (`onboarding-service-dev` / VEYRA)
> **Execution Date**: October 2, 2026 (`2026-10-02T12:53:41Z` to `2026-10-02T12:54:44Z`)
> **AWS Region**: `ap-south-1` (Mumbai)
> **Tooling**: Artillery Core (`artillery/2.0.21`) via Node.js v20.17.0

> [!NOTE]
> Deliverable 5 records the measured Artillery load test executed against Project 2 (VEYRA / Smart Employee Onboarding & Identity Service). Project 4's resume-processing burst behavior is referenced separately as supporting scaling context and is not part of the measured 3,000-request Artillery run documented here.

---

## 1. Objective

The objective of this load test is to empirically evaluate the performance, throughput, concurrency limits, and failure behaviors of the portfolio's serverless REST architecture under high step-arrival traffic. The test evaluates:
1. **API Ingress Latency**: Measuring end-to-end client latency (p50, p95, p99) across heterogeneous GET and POST endpoints.
2. **Concurrency Saturation & Burst Dynamics**: Stressing the regional AWS Lambda concurrency ceiling to observe throttling behavior under un-ramped step-arrival load.
3. **Database & Storage Scaling**: Verifying that Amazon DynamoDB on-demand capacity smoothly absorbs read-heavy bursts without partition-level throttling.
4. **Resilience & Recovery**: Validating whether the system self-heals to a stable steady state following transient burst-phase throttling.

---

## 2. Environment

| Attribute | Specification / Value |
|---|---|
| **Target Service** | Smart Employee Onboarding & Identity Service (`onboarding-service-dev`) |
| **API Architecture** | Amazon API Gateway (REST API, Regional Endpoint) |
| **Target Base URL** | `https://5goe29bglh.execute-api.ap-south-1.amazonaws.com/dev` |
| **Deployment Stack** | `onboarding-service-dev` (AWS SAM / CloudFormation) |
| **AWS Region** | `ap-south-1` (Asia Pacific — Mumbai) |
| **Backend Compute** | AWS Lambda (Python 3.12, 128 MB – 256 MB memory allocations) |
| **Primary Datastore** | Amazon DynamoDB (`onboarding-employee-profile-dev`, On-Demand Billing) |
| **Account Concurrency Limit** | 10 Concurrent Executions (`aws lambda get-account-settings`) |

---

## 3. Tooling & Test Harness

- **Load Generation Engine**: **Artillery Core** (`v2.0.21`, darwin-arm64).
- **Execution Harness**: Custom Artillery test script (`load-test/onboarding.yml`) utilizing `processor.js` for dynamic path parameter interpolation and test data generation.
- **Telemetry & Validation**: Correlated with **Amazon CloudWatch Metrics** (`AWS/ApiGateway`, `AWS/Lambda`, and `AWS/DynamoDB`) queried via AWS CLI across the precise test timestamp window (`2026-10-02T12:50:00Z` to `2026-10-02T13:00:00Z`).

---

## 4. Test Scenario Design

To simulate realistic production employee portal and admin traffic while strictly isolating mutating state to prevent database pollution:
- **Scenario 1 — Pipeline Overview (`GET /onboarding/pipeline`) [Weight: 45%]**: Simulates HR administrators refreshing the master onboarding dashboard. Exercises DynamoDB `Scan` and Lambda serialization.
- **Scenario 2 — Employee Status Ingestion (`GET /onboarding/{employee_id}/status`) [Weight: 45%]**: Simulates employees polling their onboarding checklist status. Exercises single-item DynamoDB `GetItem` lookups across synthetic employee IDs.
- **Scenario 3 — Presigned Document Upload URL (`POST /documents/upload-url`) [Weight: 10%]**: Simulates employees requesting secure presigned S3 PUT URLs for identity documents. Exercises IAM presigned URL generation and parameter validation.
- **Scenario 4 — Create Profile (`POST /employees`) [Weight: 0%]**: Explicitly isolated with zero weight to prevent synthetic employee profile contamination during the burst test.

---

## 5. Load Profile

- **Arrival Rate Model**: Fixed step-arrival rate of **50 virtual users per second** ($t=0$ to $t=60\text{ s}$).
- **Ramp-Up Period**: None (instantaneous step arrival to intentionally test cold-start absorption and unreserved concurrency boundaries).
- **Total Test Duration**: 60 seconds of load generation (63 seconds total test lifecycle).
- **Virtual Users Completed**: **3,000 VUs** completed (0 failed/timed-out VUs).

---

## 6. Requests & Scenarios Executed

| Endpoint | HTTP Method | Target Proportion | Planned Requests | Actual Requests Executed | Actual Proportion |
|---|---|---:|---:|---:|---:|
| `/onboarding/pipeline` | `GET` | 45% | ~1,350 | **1,330** | 44.33% |
| `/onboarding/{employee_id}/status` | `GET` | 45% | ~1,350 | **1,360** | 45.33% |
| `/documents/upload-url` | `POST` | 10% | ~300 | **310** | 10.33% |
| `/employees` | `POST` | 0% | 0 | **0** | 0.00% |
| **Total Requests** | — | **100%** | **3,000** | **3,000** | **100.00%** |

- **Mean Throughput**: **50.0 requests/second** sustained across the test window.

---

## 7. Response Metrics & Latency Statistics

### Client-Observed Response Latency (Artillery Measured)

| Metric | Target SLA | Measured Value | SLA Status |
|---|---:|---:|---|
| **Minimum Latency** | — | **36.2 ms** | Informational |
| **Median Latency (p50)** | < 100 ms | **47.0 ms** | **PASS** |
| **p90 Latency** | < 250 ms | **62.8 ms** | **PASS** |
| **p95 Latency** | < 500 ms | **73.0 ms** | **PASS** |
| **p99 Latency** | < 1,000 ms | **111.1 ms** | **PASS** |
| **p99.9 Latency** | < 2,000 ms | **1,484.0 ms** | **PASS** |
| **Maximum Latency** | — | **1,514.0 ms** | Occurred during opening burst |

### API Gateway & Backend Latency (CloudWatch Telemetry)

| CloudWatch Metric | Metric Target | Measured Average | Measured p95 |
|---|---:|---:|---:|
| **API Gateway Latency** | < 200 ms | **34.8 ms** | **47.6 ms** |
| **IntegrationLatency (Lambda Compute + DDB)** | < 150 ms | **30.7 ms** | **39.8 ms** |

---

## 8. Error & Failure Rate

| Response Code Category | HTTP Status Code | Count | Percentage | Operational Meaning |
|---|---|---:|---:|---|
| **Success** | `HTTP 200 OK` | **2,947** | **98.23%** | Requests successfully processed by Lambda and DynamoDB |
| **Client Error** | `HTTP 4xx` | **0** | **0.00%** | Zero client validation or authentication rejections |
| **Server Error** | `HTTP 500 Internal Server Error` | **53** | **1.77%** | Dropped invocations due to Lambda account concurrency throttling |
| **Total** | — | **3,000** | **100.00%** | **Overall Success Rate: 98.23%** |

---

## 9. Bottlenecks & Operational Observations

### Temporal Breakdown of Degradation
- **Burst Phase ($t = 0\text{ s}$ to $t = 8.8\text{ s}$)**:
  - 379 HTTP 200 responses.
  - **53 HTTP 500 responses**.
  - All 53 errors occurred strictly within the first 8.8 seconds of traffic injection.
- **Steady-State Phase ($t = 8.9\text{ s}$ to $t = 60.0\text{ s}$)**:
  - **2,568 consecutive HTTP 200 responses** with **0 failures**.
  - 100% success rate across the remaining 51.2 seconds of the test.
  - Zero additional throttles or dropped requests.

### CloudWatch Metric Reconciliation

Querying AWS CloudWatch for the test window (`18:23:41` to `18:24:44 IST`) proved exact 1-to-1 correlation between Lambda throttles and API Gateway 5xx errors:

| Component | Invocations | Application Errors | Throttles | CloudWatch Observation |
|---|---:|---:|---:|---|
| `onboarding-list-employees-dev` | 1,298 | 0 | **32** | 32 invocations throttled during opening burst |
| `onboarding-get-status-dev` | 1,343 | 0 | **17** | 17 invocations throttled during opening burst |
| `onboarding-get-upload-url-dev` | 306 | 0 | **4** | 4 invocations throttled during opening burst |
| **Total Across Lambdas** | **2,947** | **0** | **53** | **Exact match: 53 Lambda Throttles = 53 HTTP 500 Responses** |

- **DynamoDB Table Performance (`onboarding-employee-profile-dev`)**:
  - Consumed Read Capacity Units: **~3,269.5 RCUs** absorbed automatically.
  - Consumed Write Capacity Units: **0.0 WCUs** (read-heavy profile).
  - ThrottledRequests / ReadThrottleEvents: **0**. Zero database-level throttling.

---

## 10. Root Cause Analysis & Interpretation

The failure of 53 requests was **not** caused by software bugs, memory exhaustion, timeout errors, or database contention. CloudWatch confirmed `Errors: 0` across all functions.

The root cause was strictly **AWS Account-Level Regional Lambda Concurrency Throttling**:
1. **Account Concurrency Limit**: Inspecting `aws lambda get-account-settings` revealed that this shared sandbox development account is configured with a strict ceiling of **10 concurrent Lambda executions** (`AccountLimit.ConcurrentExecutions = 10`).
2. **Instantaneous Arrival Mismatch**: Injecting a step-arrival rate of 50 requests/second at $t=0$ required 50 container allocations instantly. With an account ceiling of 10, the Lambda service immediately throttled 53 invocations while initializing micro-VM containers.
3. **Execution Duration & Self-Healing**: Because Lambda execution durations were exceptionally fast (**20.2 ms** for `list-employees`, **20.7 ms** for `get-status`, and **3.7 ms** for `get-upload-url`), containers recycled in ~20 ms. Once the initial container pool was warm, a single warm container could process $\sim 50$ sequential requests per second. As a result, the 10 available containers easily handled the 50 req/sec load for the remainder of the test with zero further throttling.

---

## 11. Cross-Project Load Testing Context & 10x Scaling Implications

### Cross-Project Load Constraints (Project 4 / Resume Screener)
In Project 4 (`resume-screener-dev`), load test readiness assessments ([load-readiness.md](file:///Users/parthchoutapelly/Downloads/resume-screener/docs/evidence/load-readiness.md)) identified similar concurrency governance principles. Because Project 4 runs heavy containerized OCR and NLP Lambdas (1536 MB RAM, 8–15s CPU duration for Tesseract OCR), a burst of 50 resumes (10 scanned PDFs) without dedicated concurrency quotas would starve account-level concurrency slots. As documented in Project 4, production scale testing requires isolating heavy OCR workers behind dedicated SQS queues and reserved concurrency allocations ($\ge 25$) to protect user-facing REST endpoints.

### Recommendations for 10x Scale (500 requests/sec)
To scale this architecture by an order of magnitude (500 requests/second), four specific optimizations are required:
1. **Increase Regional Concurrency Quotas**: Submit an AWS Service Quotas request to elevate account concurrency from the dev limit of 10 to standard enterprise tiers (1,000 – 5,000).
2. **Attach Provisioned Concurrency**: Configure 20–50 provisioned concurrency instances on read-heavy Lambdas (`onboarding-list-employees-dev`, `onboarding-get-status-dev`) to eliminate cold starts and absorb initial step-arrival spikes.
3. **Enable API Gateway Response Caching**: Enable API Gateway caching on `GET /onboarding/pipeline` with a 10-second TTL. At 500 req/sec, caching offloads over 95% of requests before reaching Lambda or DynamoDB, reducing monthly compute costs while delivering single-digit millisecond latency.
4. **Implement Client-Side Retry with Exponential Backoff**: Implement jittered exponential backoff for transient 500/503 responses, allowing clients to cleanly ride through burst intervals.

---

## 12. Limitations

1. **Development Environment Quota**: Testing was conducted in a development AWS account subject to a 10 concurrent execution limit.
2. **Synthetic Data**: Virtual users queried synthetic employee identifiers rather than live enterprise personnel records.
3. **Duration**: 60-second test window measured burst and early steady-state performance; extended soak tests (e.g., 24-hour endurance testing) were not performed in dev.

---

## 13. Conclusion

The Artillery load test demonstrated outstanding steady-state performance for the serverless architecture:
- **Throughput**: Sustained **50 requests/sec** for 3,000 requests.
- **Latency**: **p50 of 47 ms**, **p95 of 73 ms**, and **p99 of 111.1 ms**, easily outperforming the 500 ms SLA.
- **Reliability**: Following the initial 8.8-second burst adjustment, the system achieved a **100% success rate across 2,568 consecutive requests**.
- **Root Cause Verified**: All 53 dropped requests were proven via CloudWatch telemetry to stem from account-level concurrency limits (10 concurrent executions), not architectural failure or database contention.
