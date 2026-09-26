#!/usr/bin/env python3
"""NLP quality evaluation against ground-truth fixtures.

docs/05-integration-testing-and-delivery.md §5 (T-105)

Usage:
    python scripts/evaluate.py --env dev [--job-id JOB_ID]

Loads tests/fixtures/truth.json, queries DynamoDB for the most recent
successfully scored candidate matching each fixture filename, and computes:

  - Skill precision   >= 0.80  (SC3)
  - Skill recall      >= 0.70  (SC3)
  - Name accuracy     >= 8/10
  - Experience accuracy >= 7/10  (|computed - truth| <= 1.0 year)
  - Title hit rate    (report only)

Writes docs/evaluation.md with full results, individual misses and causes.

Miss classification (R-HON-02 — no fixture-specific production code):
  dictionary_gap     — skill/title exists in truth but not in the skills/titles dict
  ocr_noise          — OCR fixture (scanned/image); plausible rendering artefact
  ner_miss           — spaCy NER did not detect the span
  section_detection  — experience section header not recognised, years missed
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import boto3

REPO = Path(__file__).resolve().parent.parent
TRUTH_PATH = REPO / "tests" / "fixtures" / "truth.json"
EVAL_PATH = REPO / "docs" / "evaluation.md"
DATA_DIR = REPO / "backend" / "data"
REGION = "ap-south-1"

ERROR_FIXTURES = {
    "corrupt.pdf",
    "renamed_text_file.pdf",
    "blank_scan.pdf",
    "eleven_pages.pdf",
    "encrypted.pdf",
}

# OCR fixtures: misses here are more likely OCR noise
OCR_FIXTURES = {"daniel_kim_scanned.pdf", "maya_bennett_mixed.pdf", "jordan_rivera.png"}


def load_data_dict(name: str) -> list | dict:
    p = DATA_DIR / f"{name}.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _skills_set() -> set[str]:
    s = set(load_data_dict("skills_dictionary"))
    syn_skills = load_data_dict("synonyms").get("skills", {})
    s |= set(syn_skills.keys()) | set(syn_skills.values())
    return s


def _titles_set() -> set[str]:
    t = set(load_data_dict("job_titles_dictionary"))
    syn_titles = load_data_dict("synonyms").get("titles", {})
    t |= set(syn_titles.keys()) | set(syn_titles.values())
    return t


def setup_aws(env: str):
    cf = boto3.client("cloudformation", region_name=REGION)
    out = {
        o["OutputKey"]: o["OutputValue"]
        for o in cf.describe_stacks(StackName=f"resume-screener-{env}")["Stacks"][0]["Outputs"]
    }
    ddb = boto3.resource("dynamodb", region_name=REGION)
    return ddb.Table(out["CandidatesTableName"])


def scan_all_candidates(table) -> list[dict]:
    """Full table scan — evaluation is done offline, not in hot path."""
    items, last = [], None
    while True:
        kw = {"FilterExpression": "score_status = :s", "ExpressionAttributeValues": {":s": "scored"}}
        if last:
            kw["ExclusiveStartKey"] = last
        resp = table.scan(**kw)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
    return items


def best_match(items: list[dict], filename: str) -> dict | None:
    """Return the most recently updated scored candidate matching the filename."""
    matches = [i for i in items if i.get("original_filename") == filename]
    if not matches:
        return None
    return max(matches, key=lambda i: i.get("updated_at", ""))


def classify_skill_miss(skill: str, fixture: str, skills_set: set[str]) -> str:
    """Best-effort classification of why a skill was missed."""
    if skill not in skills_set:
        return "dictionary_gap"
    if fixture in OCR_FIXTURES:
        return "ocr_noise"
    return "ner_miss"


def classify_title_miss(title: str, fixture: str, titles_set: set[str]) -> str:
    if title not in titles_set:
        return "dictionary_gap"
    if fixture in OCR_FIXTURES:
        return "ocr_noise"
    return "ner_miss"


def classify_exp_miss(fixture: str) -> str:
    if fixture in OCR_FIXTURES:
        return "section_detection"
    return "section_detection"


def as_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate(truth: dict, items: list[dict]) -> dict:
    skills_set = _skills_set()
    titles_set = _titles_set()

    scorable = {k: v for k, v in truth.items() if k not in ERROR_FIXTURES}

    skill_tp = skill_fp = skill_fn = 0
    name_correct = name_total = 0
    exp_correct = exp_total = 0
    title_hit = title_total = 0

    miss_log: list[dict] = []
    per_fixture: list[dict] = []
    not_found: list[str] = []

    for fname, expected in scorable.items():
        item = best_match(items, fname)
        if item is None:
            not_found.append(fname)
            print(f"  [WARN] no scored DynamoDB record for {fname} — skipping", file=sys.stderr)
            continue

        actual_skills = set(item.get("skills", []))
        truth_skills = set(expected.get("skills", []))

        tp = len(actual_skills & truth_skills)
        fp = len(actual_skills - truth_skills)
        fn = len(truth_skills - actual_skills)
        skill_tp += tp
        skill_fp += fp
        skill_fn += fn

        for s in sorted(actual_skills - truth_skills):
            miss_log.append(
                {"fixture": fname, "type": "skill_fp", "value": s, "cause": "ner_miss_or_dict_gap"}
            )
        for s in sorted(truth_skills - actual_skills):
            miss_log.append(
                {
                    "fixture": fname,
                    "type": "skill_fn",
                    "value": s,
                    "cause": classify_skill_miss(s, fname, skills_set),
                }
            )

        # Name accuracy
        actual_name = (item.get("name") or "").strip().lower()
        truth_name = (expected.get("name") or "").strip().lower()
        name_match = actual_name == truth_name
        name_correct += int(name_match)
        name_total += 1
        if not name_match:
            miss_log.append(
                {
                    "fixture": fname,
                    "type": "name",
                    "expected": truth_name,
                    "got": actual_name,
                    "cause": "ner_miss" if fname not in OCR_FIXTURES else "ocr_noise",
                }
            )

        # Experience accuracy
        truth_exp = expected.get("total_experience_years_approx")
        if truth_exp is not None:
            actual_exp = as_float(item.get("total_experience_years"))
            exp_total += 1
            if actual_exp is not None and abs(actual_exp - float(truth_exp)) <= 1.0:
                exp_correct += 1
            else:
                miss_log.append(
                    {
                        "fixture": fname,
                        "type": "experience",
                        "expected": truth_exp,
                        "got": actual_exp,
                        "cause": classify_exp_miss(fname),
                    }
                )

        # Title hit rate
        truth_titles = set(expected.get("titles_held", []))
        actual_titles = set(item.get("titles_held", []))
        title_total += 1
        if truth_titles and truth_titles & actual_titles:
            title_hit += 1
        elif truth_titles:
            for t in sorted(truth_titles - actual_titles):
                miss_log.append(
                    {
                        "fixture": fname,
                        "type": "title",
                        "value": t,
                        "cause": classify_title_miss(t, fname, titles_set),
                    }
                )

        per_fixture.append(
            {
                "filename": fname,
                "skill_tp": tp,
                "skill_fp": fp,
                "skill_fn": fn,
                "name_match": name_match,
                "exp_truth": truth_exp,
                "exp_actual": as_float(item.get("total_experience_years")),
                "title_hit": bool(truth_titles & actual_titles) if truth_titles else None,
            }
        )

    precision = skill_tp / (skill_tp + skill_fp) if (skill_tp + skill_fp) > 0 else 0.0
    recall = skill_tp / (skill_tp + skill_fn) if (skill_tp + skill_fn) > 0 else 0.0
    name_acc = name_correct / name_total if name_total else 0.0
    exp_acc = exp_correct / exp_total if exp_total else 0.0
    title_rate = title_hit / title_total if title_total else 0.0

    return {
        "evaluated_fixtures": len(per_fixture),
        "not_found": not_found,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "name_accuracy": {"correct": name_correct, "total": name_total, "rate": round(name_acc, 3)},
        "experience_accuracy": {"correct": exp_correct, "total": exp_total, "rate": round(exp_acc, 3)},
        "title_hit_rate": {"hits": title_hit, "total": title_total, "rate": round(title_rate, 3)},
        "targets": {
            "precision_target": 0.80,
            "recall_target": 0.70,
            "name_target": 8,
            "name_total": name_total,
            "exp_target": 7,
            "exp_total": exp_total,
        },
        "passes": {
            "precision": precision >= 0.80,
            "recall": recall >= 0.70,
            "name": name_correct >= 8,
            "experience": exp_correct >= 7,
        },
        "miss_log": miss_log,
        "per_fixture": per_fixture,
    }


def write_md(results: dict, env: str) -> None:
    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    p = results["passes"]
    na = results["name_accuracy"]
    ea = results["experience_accuracy"]
    tr = results["title_hit_rate"]

    lines = [
        "# NLP Quality Evaluation",
        "",
        f"> Generated {now} — env `{env}` — **do not edit by hand** (re-run `make evaluate`)",
        "",
        "## Summary",
        "",
        "| Metric | Result | Target (SC3) | Pass |",
        "|--------|--------|-------------|------|",
        f"| Skill precision | {results['precision']:.3f} | ≥ 0.80 | {'✅' if p['precision'] else '❌'} |",
        f"| Skill recall | {results['recall']:.3f} | ≥ 0.70 | {'✅' if p['recall'] else '❌'} |",
        f"| Name accuracy | {na['correct']}/{na['total']} ({na['rate']:.0%}) | ≥ 8/{na['total']} | {'✅' if p['name'] else '❌'} |",
        f"| Experience accuracy (±1 yr) | {ea['correct']}/{ea['total']} ({ea['rate']:.0%}) | ≥ 7/{ea['total']} | {'✅' if p['experience'] else '❌'} |",
        f"| Title hit rate | {tr['hits']}/{tr['total']} ({tr['rate']:.0%}) | report only | — |",
        "",
        f"Evaluated against {results['evaluated_fixtures']} scorable fixture(s).",
    ]

    if results["not_found"]:
        lines += [
            "",
            "> [!WARNING]",
            f"> The following fixtures had no matching DynamoDB record and were skipped: {', '.join(results['not_found'])}",
            "> Run the integration suite first to populate candidate records.",
        ]

    lines += [
        "",
        "## Per-fixture results",
        "",
        "| Fixture | TP | FP | FN | Name | Exp | Title |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in results["per_fixture"]:
        exp_ok = (
            "✅"
            if f["exp_truth"] is None
            else (
                "✅"
                if f["exp_actual"] is not None and abs(f["exp_actual"] - float(f["exp_truth"])) <= 1.0
                else "❌"
            )
        )
        lines.append(
            f"| {f['filename']} | {f['skill_tp']} | {f['skill_fp']} | {f['skill_fn']} "
            f"| {'✅' if f['name_match'] else '❌'} | {exp_ok} | {'✅' if f['title_hit'] else ('—' if f['title_hit'] is None else '❌')} |"
        )

    if results["miss_log"]:
        lines += [
            "",
            "## Misses and causes",
            "",
            "| Fixture | Type | Value | Expected | Got | Cause |",
            "|---|---|---|---|---|---|",
        ]
        for m in results["miss_log"]:
            mtype = m["type"]
            val = m.get("value", "")
            exp = m.get("expected", "")
            got = m.get("got", "")
            cause = m.get("cause", "")
            lines.append(f"| {m['fixture']} | {mtype} | {val} | {exp} | {got} | {cause} |")

    lines += [
        "",
        "## Miss classification legend",
        "",
        "| Code | Meaning |",
        "|------|---------|",
        "| `dictionary_gap` | Term is in the truth but absent from `backend/data/skills_dictionary.json` or `job_titles_dictionary.json` |",
        "| `ocr_noise` | Fixture is a scanned/image file; likely OCR rendering artefact |",
        "| `ner_miss` | Term is in the dictionary but spaCy NER/PhraseMatcher did not detect the span |",
        "| `section_detection` | Experience section header not recognised; date ranges ignored |",
        "",
        "## Overall",
        "",
        "**PASS**" if all(p.values()) else "**FAIL** — see misses above",
    ]

    EVAL_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written: {EVAL_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate NLP quality against ground truth")
    parser.add_argument("--env", default="dev")
    parser.add_argument(
        "--job-id", default=None, help="Restrict to candidates from a specific job (optional)"
    )
    args = parser.parse_args()

    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    scorable = {k: v for k, v in truth.items() if k not in ERROR_FIXTURES}
    print(f"Truth: {len(scorable)} scorable fixtures")
    print("Querying DynamoDB for scored candidates…")
    table = setup_aws(args.env)
    items = scan_all_candidates(table)
    if args.job_id:
        items = [i for i in items if i.get("job_id") == args.job_id]
    print(f"Found {len(items)} scored candidates")

    if not items:
        print("No scored candidates found in DynamoDB.")
        print("Report: not executed — live records unavailable.")
        return 0

    results = evaluate(truth, items)

    print(
        f"\nSkill precision : {results['precision']:.3f}  (target ≥ 0.80 → {'PASS' if results['passes']['precision'] else 'FAIL'})"
    )
    print(
        f"Skill recall    : {results['recall']:.3f}  (target ≥ 0.70 → {'PASS' if results['passes']['recall'] else 'FAIL'})"
    )
    na = results["name_accuracy"]
    print(
        f"Name accuracy   : {na['correct']}/{na['total']}  (target ≥ 8 → {'PASS' if results['passes']['name'] else 'FAIL'})"
    )
    ea = results["experience_accuracy"]
    print(
        f"Exp accuracy    : {ea['correct']}/{ea['total']}  (target ≥ 7 → {'PASS' if results['passes']['experience'] else 'FAIL'})"
    )

    write_md(results, args.env)

    all_pass = all(results["passes"].values())
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
