#!/usr/bin/env python3
"""Validates backend/data/*.json (docs/02-ingestion-pipeline.md §4).

Checks:
  - all entries lowercase and trimmed (except case_sensitive_skills.json keys)
  - no duplicates within any list
  - every synonym VALUE exists in its dictionary
  - every title_family member exists in job_titles_dictionary
  - no case-sensitive canonical also appears in the case-insensitive skills list
  - minimum sizes: >=250 skills, >=120 titles, >=15 title families

Exit 0 and prints a summary on success; exit 1 with the first failure otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"


def load(name: str):
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_lowercase_trimmed(name: str, values) -> None:
    for v in values:
        if v != v.strip():
            fail(f"{name}: entry {v!r} has leading/trailing whitespace")
        if v != v.lower():
            fail(f"{name}: entry {v!r} is not lowercase")


def check_no_duplicates(name: str, values) -> None:
    seen = set()
    for v in values:
        if v in seen:
            fail(f"{name}: duplicate entry {v!r}")
        seen.add(v)


def main() -> None:
    skills = load("skills_dictionary")
    titles = load("job_titles_dictionary")
    synonyms = load("synonyms")
    title_families = load("title_families")
    case_sensitive = load("case_sensitive_skills")

    if not isinstance(skills, list) or not isinstance(titles, list):
        fail("skills_dictionary.json and job_titles_dictionary.json must be JSON arrays")

    check_lowercase_trimmed("skills_dictionary", skills)
    check_lowercase_trimmed("job_titles_dictionary", titles)
    check_no_duplicates("skills_dictionary", skills)
    check_no_duplicates("job_titles_dictionary", titles)

    if len(skills) < 250:
        fail(f"skills_dictionary has only {len(skills)} entries, need >=250")
    if len(titles) < 120:
        fail(f"job_titles_dictionary has only {len(titles)} entries, need >=120")

    # synonyms: every value must exist in the corresponding dictionary — for
    # skills, a synonym MAY also target a case-sensitive canonical (e.g.
    # "golang" -> "go"), since that's still a legitimate skill value, just one
    # excluded from the case-insensitive dictionary/matcher.
    skills_set, titles_set = set(skills), set(titles)
    cs_canonical = set((case_sensitive or {}).values())
    for k, v in synonyms.get("skills", {}).items():
        if k != k.strip().lower():
            fail(f"synonyms.skills key {k!r} not lowercase/trimmed")
        if v not in skills_set and v not in cs_canonical:
            fail(f"synonyms.skills[{k!r}] -> {v!r} not in skills_dictionary or case_sensitive_skills")
    for k, v in synonyms.get("titles", {}).items():
        if k != k.strip().lower():
            fail(f"synonyms.titles key {k!r} not lowercase/trimmed")
        if v not in titles_set:
            fail(f"synonyms.titles[{k!r}] -> {v!r} not in job_titles_dictionary")

    # title_families: every member must exist in job_titles_dictionary; >=15 families
    if len(title_families) < 15:
        fail(f"title_families has only {len(title_families)} families, need >=15")
    for fam in title_families:
        if not isinstance(fam, list) or len(fam) < 2:
            fail(f"title_families entry is not a list of >=2 members: {fam!r}")
        check_no_duplicates("title_families (within one family)", fam)
        for member in fam:
            if member not in titles_set:
                fail(f"title_families member {member!r} not in job_titles_dictionary")

    # case_sensitive_skills: keys are the exact-case forms to match; values are
    # canonical lowercase forms that must NOT also appear in skills_dictionary
    # (the case-insensitive matcher would otherwise double-match them).
    if not isinstance(case_sensitive, dict):
        fail("case_sensitive_skills.json must be a JSON object")
    for k, v in case_sensitive.items():
        if v != v.strip().lower():
            fail(f"case_sensitive_skills[{k!r}] value {v!r} not lowercase/trimmed")
        if v in skills_set:
            fail(
                f"case_sensitive_skills[{k!r}] -> {v!r} also appears in skills_dictionary "
                "(would be double-matched by both matchers)"
            )

    print("OK")
    print(f"  skills_dictionary:      {len(skills)} entries")
    print(f"  job_titles_dictionary:  {len(titles)} entries")
    print(f"  title_families:         {len(title_families)} families")
    print(f"  case_sensitive_skills:  {len(case_sensitive)} entries")
    print(f"  synonyms.skills:        {len(synonyms.get('skills', {}))} entries")
    print(f"  synonyms.titles:        {len(synonyms.get('titles', {}))} entries")


if __name__ == "__main__":
    main()
