"""NLP Lambda (docs/02-ingestion-pipeline.md §8.2). Invoked only via a
synchronous lambda:Invoke from documentExtraction — no AWS event source of
its own (Architecture.md §2), which also makes it independently testable by
calling lambda_handler directly with a crafted payload.

Method-honesty split (docs/02-ingestion-pipeline.md §8.1): name/employers/date
mentions come from real spaCy NER; skills/titles are hybrid (spaCy tokenizer +
PhraseMatcher over a controlled dictionary); experience years, email, and JD
minimum years are deterministic, not NLP (R-HON-06).

D-20: this function never writes failed_jobs. An exception here surfaces to
documentExtraction as a Lambda FunctionError, which extraction classifies and
records exactly once.
"""

from __future__ import annotations

import os
import re

import boto3
import spacy
from spacy.matcher import PhraseMatcher

from rs_common import clock, fanout, log
from rs_common import normalization as norm
from rs_common.ddb import conditional_update, to_decimal
from rs_common.errors import EmptyDocumentError, OrphanRecordError
from rs_common.experience import compute_experience

_ddb = boto3.resource("dynamodb")
JOBS = _ddb.Table(os.environ["JOBS_TABLE"])
CANDIDATES = _ddb.Table(os.environ["CANDIDATES_TABLE"])

# ---- cold start only: config check, model, matchers (never per invocation) ----
_mode = (
    _ddb.Table(os.environ["CONFIG_TABLE"])
    .get_item(Key={"config_key": "nlp_engine_mode"})
    .get("Item", {})
    .get("config_value")
)
if _mode != "spacy_hybrid":  # D-13: fail loudly; no fallback engine exists
    raise RuntimeError(f"unsupported nlp_engine_mode: {_mode!r}")

nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
nlp.max_length = 200_000

SKILLS_CI = PhraseMatcher(nlp.vocab, attr="LOWER")
SKILLS_CI.add("SKILL", [nlp.make_doc(p) for p in norm.skill_patterns()])

SKILLS_CS = PhraseMatcher(nlp.vocab, attr="ORTH")
SKILLS_CS.add("SKILL", [nlp.make_doc(p) for p in norm.case_sensitive_skills()])

TITLES = PhraseMatcher(nlp.vocab, attr="LOWER")
TITLES.add("TITLE", [nlp.make_doc(p) for p in norm.title_patterns()])

_KNOWN_SKILLS = set(norm.skills())
_CORP_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|gmbh|plc)\b\.?", re.IGNORECASE)


def _strip_corp_suffix(name: str) -> str:
    return " ".join(_CORP_SUFFIX.sub("", name).split())


def lambda_handler(event, context):
    # No try/except-and-record here (D-20): exceptions surface as
    # FunctionError to documentExtraction, which classifies and records them.
    doc_type = event["doc_type"]
    job_id = event["job_id"]
    cand_id = event.get("candidate_id")
    text = event["extracted_text"]
    meta = event.get("extraction_metadata", {})

    doc = nlp(text)
    if not any(not t.is_space and not t.is_punct for t in doc):
        raise EmptyDocumentError("no tokens")

    skills = norm.normalize_list(norm.normalize_skill(doc[s:e].text) for _, s, e in SKILLS_CI(doc))
    skills = norm.normalize_list(
        skills + [norm.case_sensitive_skills()[doc[s:e].text] for _, s, e in SKILLS_CS(doc)]
    )
    titles = norm.normalize_list(norm.normalize_title(doc[s:e].text) for _, s, e in TITLES(doc))

    if doc_type == "resume":
        write_resume(job_id, cand_id, doc, text, meta, skills, titles)
        fanout.enqueue_one(job_id, cand_id, "candidate_parsed")
    else:
        write_jd(job_id, text, skills, titles)
        n = fanout.enqueue_rescore(job_id, "job_ready")  # D-18
        log.info("jd_fanout", stage="nlp", job_id=job_id, enqueued=n)

    return {"status": "parsed"}


def pick_name(doc, text: str) -> str | None:
    """First high-confidence PERSON near the top of the document (resumes
    almost always lead with the candidate's name); falls back to the first
    PERSON found anywhere. Genuine spaCy NER — no filename/heuristic guess.

    `en_core_web_sm` sometimes merges a name with an immediately adjacent
    line (e.g. an email right below it, with no blank line to act as a
    boundary) into one PERSON span — so only the entity's own first line is
    used, and a span whose first line still looks like an email/contains
    digits is rejected rather than trusted verbatim."""
    non_empty = [line for line in text.splitlines() if line.strip()]
    cutoff = text.find(non_empty[4]) + len(non_empty[4]) if len(non_empty) >= 5 else len(text)

    candidates = []
    for e in doc.ents:
        if e.label_ != "PERSON":
            continue
        first_line = e.text.splitlines()[0].strip()
        words = first_line.split()
        if not (2 <= len(words) <= 4) or "@" in first_line or any(ch.isdigit() for ch in first_line):
            continue
        candidates.append((e.start_char < cutoff, first_line))

    top = [name for near_top, name in candidates if near_top]
    chosen = (top or [name for _, name in candidates] or [None])[0]
    return " ".join(chosen.split()) if chosen else None


def write_resume(job_id, cand_id, doc, text, meta, skills, titles) -> None:
    name = pick_name(doc, text)
    employers = norm.normalize_list(
        " ".join(e.text.split())
        for e in doc.ents
        if e.label_ == "ORG"
        # R-DATA-10: drop ORGs that are really a skill name — check both the
        # raw text and with a trailing corporate suffix stripped ("Docker
        # Inc" -> "Docker" -> normalizes to the skill "docker"), so a company
        # literally named after its own product isn't recorded as an employer.
        and norm.normalize_skill(e.text) not in _KNOWN_SKILLS
        and norm.normalize_skill(_strip_corp_suffix(e.text)) not in _KNOWN_SKILLS
    )
    date_spans = [(e.start_char, e.end_char) for e in doc.ents if e.label_ == "DATE"]
    exp = compute_experience(text, date_spans, today=clock.today())

    values = {
        ":sk": skills,
        ":ti": titles,
        ":em": employers,
        ":est": exp.basis == "estimated",
        ":ft": meta.get("file_type"),
        ":pc": meta.get("page_count", 1),
        ":op": meta.get("ocr_pages", 0),
        ":cc": meta.get("char_count", len(text)),
        ":p": "parsed",
        ":t": clock.now_iso(),
    }
    sets = [
        "skills=:sk",
        "titles_held=:ti",
        "employers=:em",
        "experience_estimated=:est",
        "file_type=:ft",
        "page_count=:pc",
        "ocr_pages=:op",
        "char_count=:cc",
        "parse_status=:p",
        "updated_at=:t",
    ]
    removes = ["error_code"]

    if name:
        sets.append("#n=:n")
        values[":n"] = name
    else:
        removes.append("#n")

    email = norm.extract_email(text)
    if email:
        sets.append("email=:email")
        values[":email"] = email
    else:
        removes.append("email")

    if exp.years is not None:
        sets.append("total_experience_years=:yrs")
        values[":yrs"] = to_decimal(float(exp.years))  # R-DATA-01
    else:
        removes.append("total_experience_years")  # unknown != 0 (R-HON-09)

    ok = conditional_update(
        CANDIDATES,
        Key={"job_id": job_id, "candidate_id": cand_id},
        UpdateExpression="SET " + ", ".join(sets) + " REMOVE " + ", ".join(removes),
        ConditionExpression="attribute_exists(candidate_id)",
        ExpressionAttributeNames={"#n": "name"},
        ExpressionAttributeValues=values,
    )
    if not ok:
        raise OrphanRecordError("candidate placeholder missing")


def write_jd(job_id, text, skills, titles) -> None:
    min_years = norm.extract_min_years(text)
    sets = ["derived_skills=:s", "derived_titles=:ti", "parse_status=:p", "updated_at=:t"]
    values = {":s": skills, ":ti": titles, ":p": "parsed", ":t": clock.now_iso()}
    if min_years is not None:
        sets.append("derived_min_experience_years=:m")
        values[":m"] = min_years

    # Writes derived_* ONLY — explicit required_* are never touched (R-BUS-03, D-29)
    ok = conditional_update(
        JOBS,
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(sets) + " REMOVE error_code",
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeValues=values,
    )
    if not ok:
        raise OrphanRecordError("job missing")
