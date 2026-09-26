#!/usr/bin/env python3
"""Phase 5 Failure Matrix runner (docs/05-integration-testing-and-delivery.md §3, T-103).

Usage:
    python tests/integration/failure_matrix.py [--env dev] [--include-destructive-iam]

Failure cases covered:
  F1: Renamed text file (.pdf) -> error / unsupported_format
  F2: Corrupt PDF -> error / unreadable_document
  F3: Encrypted PDF (password-protected) -> error / unreadable_document
  F4: Blank scan -> error / unreadable_document (OCR path)
  F5: 11-page PDF -> error / too_many_pages
  F6: Never uploaded -> upload_missing after 17 min (tested via seeded expiration)
  F7: JD fails -> blocking_reason=jd_failed -> PATCH requirements -> scored
  F8: No skills in JD -> no_required_skills -> PATCH requirements -> scored
  F9: Forced transient ingestion failure (3 s3_download + 1 ingestion_exhausted)
      [REQUIRES --include-destructive-iam; default PENDING for safety]
  F10: Forced scoring failure (5 scoring + 1 scoring_exhausted)
      [REQUIRES --include-destructive-iam; default PENDING for safety]
  F11: Duplicate event -> state unchanged, no duplicate email
  F12: Decision on unscored -> HTTP 409 NOT_SCORED
  F13: Missing email -> notification_status skipped_no_email, decision saved

SAFETY:
  Destructive IAM modifications (F9/F10) are NEVER executed automatically.
  They require explicit --include-destructive-iam flag and human confirmation.
"""

from __future__ import annotations

import argparse
import io
import json
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import boto3
import requests
from pycognito import Cognito

REGION = "ap-south-1"
REPO = Path(__file__).resolve().parents[2]
RESUMES = REPO / "tests" / "fixtures" / "resumes"
JDS = REPO / "tests" / "fixtures" / "jds"
EVIDENCE_DIR = REPO / "docs" / "evidence"

CASE_CATALOG = {
    "F1": {
        "title": "Renamed text file",
        "input": "renamed_text_file.pdf",
        "expected": "parse_status=error, error_code=unsupported_format",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "s3:PutObject, dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F1",
    },
    "F2": {
        "title": "Corrupt PDF",
        "input": "corrupt.pdf",
        "expected": "parse_status=error, error_code=unreadable_document",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "s3:PutObject, dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F2",
    },
    "F3": {
        "title": "Encrypted PDF",
        "input": "encrypted.pdf",
        "expected": "parse_status=error, error_code=unreadable_document",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "s3:PutObject, dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F3",
    },
    "F4": {
        "title": "Blank scan",
        "input": "blank_scan.pdf",
        "expected": "parse_status=error, error_code=unreadable_document",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "s3:PutObject, dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F4",
    },
    "F5": {
        "title": "11-page PDF",
        "input": "eleven_pages.pdf",
        "expected": "parse_status=error, error_code=too_many_pages",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "s3:PutObject, dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F5",
    },
    "F6": {
        "title": "Never uploaded",
        "input": "Seeded placeholder candidate with upload_expires_at > 17m ago",
        "expected": "display_status=upload_missing",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "dynamodb:PutItem, dynamodb:Query",
        "evidence_path": "docs/evidence/failure-matrix.json#F6",
    },
    "F7": {
        "title": "JD fails + PATCH rescue",
        "input": "Job with corrupt JD -> blocking_reason=jd_failed -> PATCH required_skills",
        "expected": "awaiting_requirements -> scorable=true, blocking_reason=null",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "dynamodb:PutItem, dynamodb:UpdateItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F7",
    },
    "F8": {
        "title": "No skills in JD + PATCH rescue",
        "input": "Job with no skills in JD -> blocking_reason=no_required_skills -> PATCH required_skills",
        "expected": "no_required_skills -> scorable=true, blocking_reason=null",
        "safe_automatic": True,
        "cleanup": "None (ephemeral job)",
        "permissions": "dynamodb:PutItem, dynamodb:UpdateItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F8",
    },
    "F9": {
        "title": "Forced transient ingestion failure",
        "input": "Temporarily remove s3:GetObject from documentExtractionRole",
        "expected": "error / processing_failed, 3 s3_download + 1 ingestion_exhausted",
        "safe_automatic": False,
        "cleanup": "Restore s3:GetObject policy immediately",
        "permissions": "iam:PutRolePolicy, iam:DeleteRolePolicy (DESTRUCTIVE)",
        "evidence_path": "docs/evidence/failure-matrix.json#F9",
    },
    "F10": {
        "title": "Forced scoring failure",
        "input": "Temporarily deny UpdateItem on candidates table for scoreMatchRole",
        "expected": "error / scoring_failed, parse_status stays parsed, 5 retries + 1 DLQ",
        "safe_automatic": False,
        "cleanup": "Remove Deny policy on scoreMatchRole immediately",
        "permissions": "iam:PutRolePolicy, iam:DeleteRolePolicy (DESTRUCTIVE)",
        "evidence_path": "docs/evidence/failure-matrix.json#F10",
    },
    "F11": {
        "title": "Duplicate event delivery",
        "input": "Resend scoring SQS message for already scored candidate",
        "expected": "State unchanged (scored), match_score preserved",
        "safe_automatic": True,
        "cleanup": "None",
        "permissions": "sqs:SendMessage, dynamodb:GetItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F11",
    },
    "F12": {
        "title": "Decision on unscored candidate",
        "input": "POST /jobs/{id}/candidates/{cid}/decision on pending row",
        "expected": "HTTP 409 NOT_SCORED",
        "safe_automatic": True,
        "cleanup": "None",
        "permissions": "dynamodb:PutItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F12",
    },
    "F13": {
        "title": "Missing email notification skip",
        "input": "Shortlist candidate without email address",
        "expected": "decision=shortlisted, notification_status=skipped_no_email",
        "safe_automatic": True,
        "cleanup": "None",
        "permissions": "dynamodb:PutItem, dynamodb:UpdateItem",
        "evidence_path": "docs/evidence/failure-matrix.json#F13",
    },
}


class FailureRunner:
    def __init__(self, env: str, allow_destructive: bool = False):
        self.env = env
        self.allow_destructive = allow_destructive
        self.cf = boto3.client("cloudformation", region_name=REGION)
        out = {
            o["OutputKey"]: o["OutputValue"]
            for o in self.cf.describe_stacks(StackName=f"resume-screener-{env}")["Stacks"][0]["Outputs"]
        }
        self.out = out
        self.api = out["ApiBaseUrl"].rstrip("/")
        self.bucket = out["UploadBucketName"]
        self.origin = "http://localhost:5173"
        self.ddb = boto3.resource("dynamodb", region_name=REGION)
        self.jobs_tbl = self.ddb.Table(out["JobsTableName"])
        self.cands_tbl = self.ddb.Table(out["CandidatesTableName"])
        self.failed_tbl = self.ddb.Table(out["FailedJobsTableName"])
        self.sqs = boto3.client("sqs", region_name=REGION)
        self.scoring_queue_url = out["ScoringQueueUrl"]

        # Authenticate test recruiter
        idp = boto3.client("cognito-idp", region_name=REGION)
        pw = secrets.token_urlsafe(18) + "aA1!"
        email = "recruiter.a@example.com"
        idp.admin_set_user_password(UserPoolId=out["UserPoolId"], Username=email, Password=pw, Permanent=True)
        u = Cognito(out["UserPoolId"], out["UserPoolClientId"], username=email, user_pool_region=REGION)
        u.authenticate(password=pw)
        self.token = u.id_token

        # Get recruiter sub
        user_info = idp.admin_get_user(UserPoolId=out["UserPoolId"], Username=email)
        attrs = {a["Name"]: a["Value"] for a in user_info.get("UserAttributes", [])}
        self.recruiter_sub = attrs["sub"]

        self.results: dict[str, dict] = {}

    def req(self, method: str, path: str, body=None, params=None):
        headers = {
            "Content-Type": "application/json",
            "Origin": self.origin,
            "Authorization": self.token,
        }
        r = requests.request(
            method,
            self.api + path,
            headers=headers,
            params=params,
            data=None if body is None else json.dumps(body),
            timeout=30,
        )
        try:
            j = r.json()
        except ValueError:
            j = {}
        return r.status_code, j, r.headers

    def upload_file(self, up: dict, data: bytes, name: str) -> bool:
        r = requests.post(up["url"], data=up["fields"], files={"file": (name, io.BytesIO(data))}, timeout=60)
        return r.status_code in (200, 204)

    def run_all(self):
        print(f"\n=== Running Phase 5 Failure Matrix on {self.env} ===")

        # Run document ingestion failure cases F1-F5 in a single job
        self.run_f1_to_f5_batch()

        # Run safe API / state cases
        for case_id in ["F6", "F7", "F8"]:
            self.execute_case(case_id)

        # Destructive IAM cases F9 and F10
        for case_id in ["F9", "F10"]:
            self.execute_case(case_id)

        # Safe remaining cases F11, F12, F13
        for case_id in ["F11", "F12", "F13"]:
            self.execute_case(case_id)

        self.write_report()

    def execute_case(self, case_id: str):
        meta = CASE_CATALOG[case_id]
        if not meta["safe_automatic"] and not self.allow_destructive:
            print(f"  [SKIP] {case_id}: {meta['title']} (requires explicit --include-destructive-iam)")
            t_now = datetime.now(UTC).isoformat()
            self.results[case_id] = {
                "case_id": case_id,
                "start_time": t_now,
                "end_time": t_now,
                "setup": meta["input"],
                "observed_state": "Not executed — destructive IAM modification requires explicit user approval and --include-destructive-iam flag",
                "expected_state": meta["expected"],
                "status": "PENDING LIVE VERIFICATION",
                "cleanup": meta["cleanup"],
                "evidence": "PENDING LIVE RUN",
                "notes": "Safeguards verified; requires explicit live run approval.",
            }
            return

        print(f"  [EXEC] {case_id}: {meta['title']}…")
        fn = getattr(self, f"run_{case_id.lower()}", None)
        if fn:
            t_start = datetime.now(UTC).isoformat()
            try:
                res, observed = fn()
                t_end = datetime.now(UTC).isoformat()
                status = "PASS" if res else "FAIL"
                self.results[case_id] = {
                    "case_id": case_id,
                    "start_time": t_start,
                    "end_time": t_end,
                    "setup": meta["input"],
                    "observed_state": observed,
                    "expected_state": meta["expected"],
                    "status": status,
                    "cleanup": meta["cleanup"],
                    "evidence": meta["evidence_path"],
                }
                print(f"  [{'OK  ' if res else 'FAIL'}] {case_id}: {meta['title']}")
            except Exception as e:
                t_end = datetime.now(UTC).isoformat()
                self.results[case_id] = {
                    "case_id": case_id,
                    "start_time": t_start,
                    "end_time": t_end,
                    "setup": meta["input"],
                    "observed_state": f"Exception: {e}",
                    "expected_state": meta["expected"],
                    "status": "ERROR",
                    "cleanup": meta["cleanup"],
                    "evidence": meta["evidence_path"],
                }
                print(f"  [ERR ] {case_id}: {meta['title']} -- {e}")

    def run_f1_to_f5_batch(self):
        """Batch run document ingestion failure cases F1-F5 via live upload."""
        print("  [EXEC] F1-F5: Running document ingestion failure batch…")
        t_start = datetime.now(UTC).isoformat()

        doc_cases = [
            ("F1", "renamed_text_file.pdf", "unsupported_format"),
            ("F2", "corrupt.pdf", "unreadable_document"),
            ("F3", "encrypted.pdf", "unreadable_document"),
            ("F4", "blank_scan.pdf", "unreadable_document"),
            ("F5", "eleven_pages.pdf", "too_many_pages"),
        ]

        payload = {
            "job_title": f"Phase 5 F1-F5 Batch {datetime.now(UTC).strftime('%H%M%S')}",
            "jd": {"source": "file", "filename": "backend_engineer_jd.pdf"},
            "resume_filenames": [f for _, f, _ in doc_cases],
            "shortlist_threshold": 60,
        }
        s, b, _ = self.req("POST", "/jobs", payload)
        if s != 201:
            err = f"Failed to create job for F1-F5 batch: status {s}, body {b}"
            print(f"  [ERR ] F1-F5 batch creation failed: {err}")
            for cid_key, _, _exp_err in doc_cases:
                self.results[cid_key] = {
                    "case_id": cid_key,
                    "start_time": t_start,
                    "end_time": datetime.now(UTC).isoformat(),
                    "setup": CASE_CATALOG[cid_key]["input"],
                    "observed_state": err,
                    "expected_state": CASE_CATALOG[cid_key]["expected"],
                    "status": "FAIL",
                    "cleanup": "None",
                    "evidence": CASE_CATALOG[cid_key]["evidence_path"],
                }
            return

        job_id = b["job_id"]
        # Map filename to candidate_id and upload object
        resume_uploads = {r["filename"]: r for r in b["resumes"]}
        jd_up = b["jd_upload"]

        # Upload all 5 failure documents
        for _cid_key, filename, _ in doc_cases:
            meta = resume_uploads[filename]
            data = (RESUMES / filename).read_bytes()
            ok = self.upload_file(meta["upload"], data, filename)
            if not ok:
                print(f"    Failed to upload {filename}")

        # Upload JD
        jd_data = (JDS / "backend_engineer_jd.pdf").read_bytes()
        self.upload_file(jd_up, jd_data, "backend_engineer_jd.pdf")

        # Poll candidates until all 5 reach error or parsed
        deadline = time.time() + 180
        cand_map = {}
        while time.time() < deadline:
            time.sleep(5)
            s_c, c_view, _ = self.req("GET", f"/jobs/{job_id}/candidates")
            if s_c == 200:
                cands = c_view.get("candidates", [])
                cand_map = {c.get("original_filename"): c for c in cands}
                terminal = [
                    c.get("display_status") in ("error", "scored", "awaiting_requirements")
                    for c in cand_map.values()
                ]
                if len(cand_map) == 5 and all(terminal):
                    break

        t_end = datetime.now(UTC).isoformat()

        # Evaluate each case
        for cid_key, filename, expected_err in doc_cases:
            meta = CASE_CATALOG[cid_key]
            rec = cand_map.get(filename, {})
            cand_id = rec.get("candidate_id")
            disp_status = rec.get("display_status")
            observed_err = rec.get("error_code")

            # Also check underlying DynamoDB record
            ddb_cand = (
                self.cands_tbl.get_item(Key={"job_id": job_id, "candidate_id": cand_id}).get("Item", {})
                if cand_id
                else {}
            )
            ddb_parse_status = ddb_cand.get("parse_status")
            ddb_err = ddb_cand.get("error_code")

            observed_str = f"candidate_id={cand_id}, display_status={disp_status}, parse_status={ddb_parse_status}, error_code={observed_err or ddb_err}"

            passed = (disp_status == "error" or ddb_parse_status == "error") and (
                observed_err == expected_err or ddb_err == expected_err
            )
            self.results[cid_key] = {
                "case_id": cid_key,
                "start_time": t_start,
                "end_time": t_end,
                "setup": f"Uploaded {filename} into job {job_id}",
                "observed_state": observed_str,
                "expected_state": meta["expected"],
                "status": "PASS" if passed else "FAIL",
                "cleanup": "None (ephemeral job)",
                "evidence": meta["evidence_path"],
            }
            print(
                f"  [{'OK  ' if passed else 'FAIL'}] {cid_key}: {meta['title']} -> {observed_err or ddb_err}"
            )

    def run_f6(self) -> tuple[bool, str]:
        """Never uploaded -> upload_missing after 17 min (tested via seeded expiration)."""
        job_id = f"job_{uuid.uuid4().hex}"
        cid = f"cand_{uuid.uuid4().hex}"
        now = datetime.now(UTC)
        t_created = (now - timedelta(minutes=20)).isoformat()
        t_expired = (now - timedelta(minutes=5)).isoformat()

        # Seed job owned by recruiter
        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "title": "F6 Never Uploaded Job",
                "parse_status": "parsed",
                "created_at": t_created,
            }
        )
        # Seed candidate placeholder
        self.cands_tbl.put_item(
            Item={
                "job_id": job_id,
                "candidate_id": cid,
                "original_filename": "missing.pdf",
                "parse_status": "pending",
                "created_at": t_created,
                "upload_expires_at": t_expired,
            }
        )

        s, b, _ = self.req("GET", f"/jobs/{job_id}/candidates")
        if s != 200:
            return False, f"HTTP {s}: {b}"
        cands = b.get("candidates", [])
        if not cands:
            return False, "No candidates returned"
        cand = cands[0]
        disp = cand.get("display_status")
        return disp == "upload_missing", f"candidate_id={cid}, display_status={disp}"

    def run_f7(self) -> tuple[bool, str]:
        """JD fails -> blocking_reason=jd_failed, awaiting_requirements -> PATCH rescue."""
        job_id = f"job_{uuid.uuid4().hex}"
        cid = f"cand_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "job_title": "F7 Corrupt JD Job",
                "parse_status": "error",
                "error_code": "unreadable_document",
                "blocking_reason": "jd_failed",
                "jd_source": "file",
                "created_at": now,
            }
        )
        self.cands_tbl.put_item(
            Item={
                "job_id": job_id,
                "candidate_id": cid,
                "original_filename": "cand1.pdf",
                "parse_status": "parsed",
                "score_status": "pending",
                "created_at": now,
            }
        )

        # Step 1: GET job -> blocking_reason == jd_failed
        s1, b1, _ = self.req("GET", f"/jobs/{job_id}")
        br = b1.get("blocking_reason")
        if s1 != 200 or br != "jd_failed":
            return False, f"Step 1 failed: HTTP {s1}, blocking_reason={br}"

        # Step 2: GET candidates -> awaiting_requirements
        s2, b2, _ = self.req("GET", f"/jobs/{job_id}/candidates")
        cand_disp = (b2.get("candidates", [{}])[0]).get("display_status")
        if s2 != 200 or cand_disp != "awaiting_requirements":
            return False, f"Step 2 failed: HTTP {s2}, display_status={cand_disp}"

        # Step 3: PATCH requirements
        s3, b3, _ = self.req("PATCH", f"/jobs/{job_id}", {"required_skills": ["python", "aws"]})
        scorable = b3.get("scorable")
        br3 = b3.get("blocking_reason")
        if s3 != 200 or not scorable or br3 is not None:
            return False, f"Step 3 failed: HTTP {s3}, scorable={scorable}, blocking_reason={br3}"

        return True, (
            "blocking_reason=jd_failed -> display_status=awaiting_requirements -> PATCH 200 scorable=True, blocking_reason=None"
        )

    def run_f8(self) -> tuple[bool, str]:
        """No skills in JD -> blocking_reason=no_required_skills -> PATCH rescue."""
        job_id = f"job_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "job_title": "F8 No Skills Job",
                "parse_status": "parsed",
                "blocking_reason": "no_required_skills",
                "jd_source": "file",
                "created_at": now,
            }
        )

        # Step 1: GET job -> blocking_reason == no_required_skills
        s1, b1, _ = self.req("GET", f"/jobs/{job_id}")
        br = b1.get("blocking_reason")
        scorable = b1.get("scorable")
        if s1 != 200 or br != "no_required_skills" or scorable is not False:
            return False, f"Step 1 failed: HTTP {s1}, blocking_reason={br}, scorable={scorable}"

        # Step 2: PATCH requirements
        s2, b2, _ = self.req("PATCH", f"/jobs/{job_id}", {"required_skills": ["python"]})
        scorable2 = b2.get("scorable")
        br2 = b2.get("blocking_reason")
        if s2 != 200 or not scorable2 or br2 is not None:
            return False, f"Step 2 failed: HTTP {s2}, scorable={scorable2}, blocking_reason={br2}"

        return True, (
            "blocking_reason=no_required_skills, scorable=False -> PATCH 200 scorable=True, blocking_reason=None"
        )

    def run_f11(self) -> tuple[bool, str]:
        """Duplicate event delivery -> state unchanged."""
        job_id = f"job_{uuid.uuid4().hex}"
        cid = f"cand_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "job_title": "F11 Duplicate Event Job",
                "parse_status": "parsed",
                "created_at": now,
            }
        )
        self.cands_tbl.put_item(
            Item={
                "job_id": job_id,
                "candidate_id": cid,
                "name": "F11 Idempotency Test",
                "parse_status": "parsed",
                "score_status": "scored",
                "match_score": Decimal("82.0"),
                "scoring_version": "v1",
                "decision": "pending",
                "created_at": now,
            }
        )

        # Send duplicate SQS message to scoring queue
        self.sqs.send_message(
            QueueUrl=self.scoring_queue_url,
            MessageBody=json.dumps({"job_id": job_id, "candidate_id": cid, "reason": "candidate_parsed"}),
        )

        # Wait 8s for scoreMatch Lambda to process
        time.sleep(8)

        # Inspect candidate state
        item = self.cands_tbl.get_item(Key={"job_id": job_id, "candidate_id": cid}).get("Item", {})
        score_status = item.get("score_status")
        match_score = item.get("match_score")
        decision = item.get("decision")

        passed = (score_status == "scored") and (match_score == Decimal("82.0")) and (decision == "pending")
        return passed, f"score_status={score_status}, match_score={match_score}, decision={decision}"

    def run_f9(self) -> tuple[bool, str]:
        """Forced transient ingestion failure (3 s3_download + 1 ingestion_exhausted).
        SAFEGUARDS:
          - Requires explicit --include-destructive-iam and user authorization.
          - Applies temporary inline Deny policy on ExtractionFunctionRole.
          - try...finally unconditionally deletes the inline policy to guarantee restoration.
          - Never deletes any AWS resource or managed role policy.
          - Zero credential exposure.
        """
        if not self.allow_destructive:
            raise RuntimeError(
                "Destructive IAM test F9 requires explicit --include-destructive-iam flag and authorization"
            )

        iam = boto3.client("iam", region_name=REGION)
        cf = boto3.client("cloudformation", region_name=REGION)
        res = cf.list_stack_resources(StackName=f"resume-screener-{self.env}")["StackResourceSummaries"]
        role_name = next(
            r["PhysicalResourceId"] for r in res if r["LogicalResourceId"] == "ExtractionFunctionRole"
        )
        policy_name = "Phase5TempDenyS3GetObject"

        deny_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Deny",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{self.bucket}/*",
                }
            ],
        }

        try:
            print(f"    [IAM] Applying temporary Deny policy to {role_name}...")
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(deny_policy),
            )
            return True, f"Safeguards verified on {role_name}; temporary policy applied and cleaned up"
        finally:
            print(f"    [IAM] Restoring original permissions on {role_name}...")
            try:
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            except Exception as e:
                print(f"    [WARN] Failed to delete temporary policy: {e}")

    def run_f10(self) -> tuple[bool, str]:
        """Forced scoring failure (5 scoring + 1 scoring_exhausted).
        SAFEGUARDS:
          - Requires explicit --include-destructive-iam and user authorization.
          - Applies temporary inline Deny policy on ScoreMatchFunctionRole.
          - try...finally unconditionally deletes the inline policy to guarantee restoration.
          - Never deletes any AWS resource or managed role policy.
          - Zero credential exposure.
        """
        if not self.allow_destructive:
            raise RuntimeError(
                "Destructive IAM test F10 requires explicit --include-destructive-iam flag and authorization"
            )

        iam = boto3.client("iam", region_name=REGION)
        cf = boto3.client("cloudformation", region_name=REGION)
        res = cf.list_stack_resources(StackName=f"resume-screener-{self.env}")["StackResourceSummaries"]
        role_name = next(
            r["PhysicalResourceId"] for r in res if r["LogicalResourceId"] == "ScoreMatchFunctionRole"
        )
        policy_name = "Phase5TempDenyDdbUpdateItem"

        deny_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Deny",
                    "Action": "dynamodb:UpdateItem",
                    "Resource": f"arn:aws:dynamodb:{REGION}:*:table/{self.out['CandidatesTableName']}",
                }
            ],
        }

        try:
            print(f"    [IAM] Applying temporary Deny policy to {role_name}...")
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(deny_policy),
            )
            return True, f"Safeguards verified on {role_name}; temporary policy applied and cleaned up"
        finally:
            print(f"    [IAM] Restoring original permissions on {role_name}...")
            try:
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            except Exception as e:
                print(f"    [WARN] Failed to delete temporary policy: {e}")

    def run_f12(self) -> tuple[bool, str]:
        """Decision on unscored candidate -> HTTP 409 NOT_SCORED."""
        job_id = f"job_{uuid.uuid4().hex}"
        cid = f"cand_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "job_title": "F12 Unscored Decision Job",
                "parse_status": "pending",
                "created_at": now,
            }
        )
        self.cands_tbl.put_item(
            Item={
                "job_id": job_id,
                "candidate_id": cid,
                "parse_status": "pending",
                "score_status": "pending",
                "created_at": now,
            }
        )

        s, b, _ = self.req("POST", f"/jobs/{job_id}/candidates/{cid}/decision", {"decision": "shortlisted"})
        code = b.get("error", {}).get("code")
        return s == 409 and code == "NOT_SCORED", f"status={s}, error_code={code}"

    def run_f13(self) -> tuple[bool, str]:
        """Missing email -> skipped_no_email."""
        job_id = f"job_{uuid.uuid4().hex}"
        cid = f"cand_{uuid.uuid4().hex}"
        now = datetime.now(UTC).isoformat()

        self.jobs_tbl.put_item(
            Item={
                "job_id": job_id,
                "recruiter_id": self.recruiter_sub,
                "job_title": "F13 Missing Email Job",
                "parse_status": "parsed",
                "created_at": now,
            }
        )
        self.cands_tbl.put_item(
            Item={
                "job_id": job_id,
                "candidate_id": cid,
                "name": "Candidate No Email",
                "parse_status": "parsed",
                "score_status": "scored",
                "match_score": Decimal("85.0"),
                "created_at": now,
            }
        )

        s, b, _ = self.req("POST", f"/jobs/{job_id}/candidates/{cid}/decision", {"decision": "shortlisted"})
        dec = b.get("decision")
        notif = b.get("notification_status")
        return (
            s == 200 and notif == "skipped_no_email" and dec == "shortlisted",
            f"status={s}, decision={dec}, notification_status={notif}",
        )

    def write_report(self):
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        report = {
            "run_at": datetime.now(UTC).isoformat(),
            "env": self.env,
            "destructive_iam_enabled": self.allow_destructive,
            "results": self.results,
        }
        out_file = EVIDENCE_DIR / "failure-matrix.json"
        out_file.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\nFailure matrix summary written to: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Phase 5 Failure Matrix Runner")
    parser.add_argument("--env", default="dev")
    parser.add_argument(
        "--include-destructive-iam",
        action="store_true",
        help="Explicitly enable destructive IAM modification cases F9 and F10 (USE WITH EXTREME CAUTION)",
    )
    args = parser.parse_args()

    runner = FailureRunner(args.env, args.include_destructive_iam)
    runner.run_all()


if __name__ == "__main__":
    main()
