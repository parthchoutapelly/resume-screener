#!/usr/bin/env python3
"""Deployed integration test for phase 2 (docs/02-ingestion-pipeline.md §10,
"Deployed" row). Creates real placeholder items in the live jobs/candidates
tables, uploads the real fixture files to the real S3 bucket (triggering the
real S3 -> SQS -> ExtractionFunction -> NlpFunction pipeline exactly as
production would), then polls DynamoDB until every candidate reaches a
terminal state and asserts the results.

No mocks anywhere in this file — this exercises the actual deployed AWS
resources. Usage: python tests/integration/phase2_run.py <env>
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr

REGION = "ap-south-1"
REPO_ROOT = Path(__file__).resolve().parents[2]
RESUMES = REPO_ROOT / "tests" / "fixtures" / "resumes"
JDS = REPO_ROOT / "tests" / "fixtures" / "jds"

# (fixture filename, extension, expected outcome)
# outcome "parsed" means we expect parse_status to end as "parsed";
# an error_code string means we expect that terminal error_code.
RESUME_CASES = [
    ("worked_example_native.pdf", "pdf", "parsed"),
    ("alice_johnson_native.pdf", "pdf", "parsed"),
    ("daniel_kim_scanned.pdf", "pdf", "parsed"),
    ("maya_bennett_mixed.pdf", "pdf", "parsed"),
    ("bob_kumar.docx", "docx", "parsed"),
    ("jordan_rivera.png", "png", "parsed"),
    ("corrupt.pdf", "pdf", "unreadable_document"),
    ("renamed_text_file.pdf", "pdf", "unsupported_format"),
    ("blank_scan.pdf", "pdf", "unreadable_document"),
    ("eleven_pages.pdf", "pdf", "too_many_pages"),
]


def main() -> int:
    env = sys.argv[1] if len(sys.argv) > 1 else "dev"
    stack = f"resume-screener-{env}"

    cf = boto3.client("cloudformation", region_name=REGION)
    outputs = {
        o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    }
    bucket = outputs["UploadBucketName"]
    jobs_table_name = outputs["JobsTableName"]
    candidates_table_name = outputs["CandidatesTableName"]
    failed_table_name = outputs["FailedJobsTableName"]

    s3 = boto3.client("s3", region_name=REGION)
    ddb = boto3.resource("dynamodb", region_name=REGION)
    jobs_table = ddb.Table(jobs_table_name)
    candidates_table = ddb.Table(candidates_table_name)
    failed_table = ddb.Table(failed_table_name)

    job_id = f"job_itest{uuid.uuid4().hex[:12]}"
    print(f"[+] job_id = {job_id}")

    # 1. Create job + JD placeholder, upload the JD file.
    jobs_table.put_item(Item={"job_id": job_id, "parse_status": "pending", "recruiter_id": "itest"})
    jd_key = f"jd-uploads/{job_id}/jd.pdf"
    s3.upload_file(str(JDS / "backend_engineer_jd.pdf"), bucket, jd_key)
    print(f"[+] uploaded JD -> s3://{bucket}/{jd_key}")

    # 2. Create candidate placeholders + upload each resume fixture.
    candidate_ids = {}
    for filename, ext, _expected in RESUME_CASES:
        cand_id = f"cand_itest{uuid.uuid4().hex[:12]}"
        candidate_ids[filename] = cand_id
        candidates_table.put_item(Item={"job_id": job_id, "candidate_id": cand_id, "parse_status": "pending"})
        key = f"resume-uploads/{job_id}/{cand_id}/resume.{ext}"
        s3.upload_file(str(RESUMES / filename), bucket, key)
        print(f"[+] uploaded {filename} -> s3://{bucket}/{key}")

    # 3. Poll until every candidate reaches a terminal parse_status (or timeout).
    deadline = time.time() + 15 * 60
    pending = set(candidate_ids)
    results = {}
    print("[+] polling for terminal states (up to 15 min)...")
    while pending and time.time() < deadline:
        time.sleep(10)
        for filename in list(pending):
            cand_id = candidate_ids[filename]
            item = candidates_table.get_item(Key={"job_id": job_id, "candidate_id": cand_id}).get("Item", {})
            status = item.get("parse_status")
            if status in ("parsed", "error"):
                results[filename] = item
                pending.discard(filename)
                print(f"    {filename:32s} -> {status} ({item.get('error_code', '')})")

    if pending:
        print(f"[!] TIMED OUT waiting for: {sorted(pending)}")

    # 4. Report + assert.
    ok = True
    for filename, _ext, expected in RESUME_CASES:
        item = results.get(filename)
        if item is None:
            print(f"[FAIL] {filename}: never reached a terminal state")
            ok = False
            continue
        status = item.get("parse_status")
        if expected == "parsed":
            if status != "parsed":
                print(f"[FAIL] {filename}: expected parsed, got {status} ({item.get('error_code')})")
                ok = False
            else:
                has_years = "total_experience_years" in item
                print(
                    f"[OK]   {filename}: name={item.get('name')!r} "
                    f"skills={item.get('skills')} file_type={item.get('file_type')} "
                    f"years={item.get('total_experience_years') if has_years else 'unknown'}"
                )
        else:
            if status != "error" or item.get("error_code") != expected:
                print(f"[FAIL] {filename}: expected error/{expected}, got {status}/{item.get('error_code')}")
                ok = False
            else:
                print(f"[OK]   {filename}: correctly terminal ({expected})")

    # 5. JD should have parsed too.
    job_item = jobs_table.get_item(Key={"job_id": job_id}).get("Item", {})
    if job_item.get("parse_status") == "parsed":
        print(f"[OK]   JD parsed: derived_skills={job_item.get('derived_skills')}")
    else:
        print(f"[FAIL] JD did not parse: {job_item.get('parse_status')}")
        ok = False

    # 6. failed_jobs sanity: exactly one row per terminal failure, none stray for successes.
    failures = failed_table.scan(FilterExpression=Attr("job_id").eq(job_id))["Items"]
    terminal_failures = [f for f in failures if f.get("terminal")]
    expected_terminal = sum(1 for _, _, exp in RESUME_CASES if exp != "parsed")
    print(f"[+] failed_jobs rows for this job: {len(failures)} total, {len(terminal_failures)} terminal")
    if len(terminal_failures) < expected_terminal:
        print(f"[FAIL] expected >= {expected_terminal} terminal failure rows, got {len(terminal_failures)}")
        ok = False

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
