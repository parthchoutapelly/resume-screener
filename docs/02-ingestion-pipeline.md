# PHASE 2 of 5 — Shared Library, Document Extraction & NLP Pipeline
### Project: AI-Powered Resume Screener & Talent Acquisition Pipeline

| | |
|---|---|
| **Covers** | `Tasks.md` E2 (T-020–T-029), E3 (T-030–T-038), E4 (T-040–T-046) |
| **Owner** | Parth |
| **Prerequisites** | Phase 1 DoD fully checked; D-34 (extraction base image) and T-006 (layer size) outcomes recorded |
| **Read first** | `Architecture.md` §3.2, §4, §6, §7 · `Rules.md` §1, §5, §7, §8 · `Memory.md` §6 (pitfalls) · `Details.md` §2–3 (why open-source extraction/NLP) |
| **Produces** | `rs_common` layer; working extraction (native/scanned/mixed PDF, DOCX, image, JD text) and NLP functions; S3 → SQS wiring; JD fan-out to scoring |
| **Hands off to** | `03-scoring-and-api.md` |

> **Agent instructions.** At the end of this phase, uploading a JD and resumes to S3 (with the aws CLI, using keys that match placeholders you created by hand or with a test script) produces populated `jobs`/`candidates` items and scoring messages, with no manual step. `match_score` stays absent until phase 3; that's expected. Code blocks here are **reference implementations**: complete them, but keep their behaviour. Where `Implementation.md` differs from this file, this file wins (`Memory.md` §7).

---

## 1. Absolute prohibitions (checked in the DoD, §11)

- Branching on filename, S3 key contents beyond the prefix/ids/extension, or sample-specific conditions (R-HON-01/02).
- Canned or hardcoded resume text anywhere in `backend/` (R-HON-01).
- "Fake OCR" or "fake NLP": any path returning text or entities without running Tesseract or spaCy on the actual content (R-HON-03).
- Invented confidence values (R-HON-05).
- Resume text, names, or emails in logs or `failed_jobs.error_message` (R-PRIV-01/02).
- Writing `float` to DynamoDB; writing NULL for `total_experience_years`; building table names in code (R-DATA-01..03).
- Any `textract`/`comprehend` reference (R-HON-08).

## 2. Design recap (why the pipeline looks like this)

- **One IngestionQueue for JD and resumes** (D-05). `doc_type` comes from the key prefix: `jd-uploads/{job_id}/jd.{ext}` or `resume-uploads/{job_id}/{candidate_id}/resume.{ext}`. Keys are server-chosen (D-21), so a user filename never reaches S3 or `/tmp`.
- **Extraction → NLP is a synchronous invoke** (D-04): two deployable units, with two packaging strategies and two IAM scopes, but no third queue. An NLP failure surfaces as `FunctionError`, which extraction classifies.
- **Terminal vs transient** (D-19). A deterministic problem (bad format, corrupt, encrypted, too many pages, no readable text) is recorded once, marked `error`, and **acknowledged**. Retrying it could never succeed and would hold the error state back for ~36 min. Everything else re-raises, SQS retries (3 attempts), and `dlqHandler` (phase 3) makes it terminal.
- **Extraction is the only writer of ingestion audit rows** (D-20). NLP never writes `failed_jobs`; before this rule, every NLP failure was recorded twice.
- **JD fan-out** (D-18). When a JD is parsed, NLP enqueues scoring for every candidate of that job already parsed. That is what lets `scoreMatch` simply acknowledge "JD not ready" instead of retrying until it gives up.

## 3. Permissions to add this phase

- **Deploy user:** `s3:PutBucketNotification` on the upload bucket; layer publish actions (already listed in `01` §6).
- **Execution roles:** §9 (per function, by ARN).

## 4. Data files (`backend/data/`, T-023)

Single source of truth. They are copied into the layer at build time (§5.3) and land at `/opt/data/`.

| File | Shape | Seed size | Notes |
|---|---|---|---|
| `skills_dictionary.json` | `["python", "aws", "node.js", "ci/cd", ...]` | ≥250 | Lowercase canonical names |
| `case_sensitive_skills.json` | `{"Go": "go", "R": "r", "C": "c"}` | small | Ambiguous short skills, matched **case-sensitively only** so "go to market" doesn't count as Go. Their canonical values are excluded from the case-insensitive matcher |
| `job_titles_dictionary.json` | `["software engineer", "backend engineer", ...]` | ≥120 | Lowercase |
| `synonyms.json` | `{"skills": {"js": "javascript", "k8s": "kubernetes", ...}, "titles": {"sde": "software engineer", ...}}` | — | **Keys are also added as matcher patterns** (otherwise "k8s" is never matched and normalization never runs) |
| `title_families.json` | `[["backend engineer", "backend developer", "software engineer", "api developer"], ["data scientist", "ml engineer", "machine learning engineer"], ...]` | ≥15 families | Drives the 60-point related-title score (D-26). A title may appear in several families |

`scripts/validate_data.py` (run in CI) checks: all entries lowercase and trimmed; no duplicates; every synonym value exists in its dictionary; every family member exists in the titles dictionary; no case-sensitive canonical also appears in the case-insensitive skills list.

## 5. `rs_common` shared layer (T-020–T-029)

### 5.1 Package layout
```
backend/layers/common_layer/python/rs_common/
  __init__.py      # empty — NO I/O at import time anywhere in this package
  clock.py         # now_iso(), today(), epoch_in_days(n); injectable for tests
  ids.py           # job_id(), candidate_id(), failure_id()  → prefix + uuid4().hex
  log.py           # json logger; drops forbidden keys (text, extracted_text, email, name, phone)
  errors.py        # TerminalError, TransientError, EmptyDocumentError, OrphanRecordError, ErrorCode, Stage, safe_message()
  ddb.py           # to_decimal(), from_decimal(), conditional_update() → bool
  normalization.py # lazy-loaded dictionaries; normalize_*; skill/title patterns; extract_email; extract_min_years
  experience.py    # pure date-range experience computation (§8.3)
  requirements.py  # effective(), sources(), scorable(), blocking_reason()        (used from phase 3)
  status.py        # display_status(), sort_key()                                (phase 3)
  scoring.py       # pure score()                                                (phase 3)
  fanout.py        # enqueue_one(), enqueue_rescore()
  authz.py, http.py                                                              (phase 3)
```

### 5.2 Key modules (reference)

```python
# errors.py
from enum import StrEnum

class ErrorCode(StrEnum):            # recruiter-visible (Architecture §7.4)
    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    UNREADABLE_DOCUMENT = "unreadable_document"
    PROCESSING_FAILED = "processing_failed"
    SCORING_FAILED = "scoring_failed"

class Stage(StrEnum):                # internal (Admin-only)
    ORPHAN_OBJECT = "orphan_object"; UNSUPPORTED_FORMAT = "unsupported_format"
    S3_DOWNLOAD = "s3_download"; PDF_EXTRACT = "pdf_extract"; DOCX_EXTRACT = "docx_extract"
    OCR = "ocr"; NLP = "nlp"; SCORING = "scoring"; API = "api"
    INGESTION_EXHAUSTED = "ingestion_exhausted"; SCORING_EXHAUSTED = "scoring_exhausted"

class TerminalError(Exception):
    """Deterministic failure: record once, mark item error, ACK the message."""
    def __init__(self, code: ErrorCode | None, stage: Stage, detail: str):
        super().__init__(detail); self.code, self.stage = code, stage

class TransientError(Exception):
    """Possibly recoverable: record attempt, re-raise so SQS retries."""
    def __init__(self, stage: Stage, detail: str):
        super().__init__(detail); self.stage = stage

class EmptyDocumentError(Exception): ...   # raised by NLP → terminal unreadable_document
class OrphanRecordError(Exception): ...    # raised by NLP → terminal orphan_object

def safe_message(exc: BaseException, limit: int = 500) -> str:
    """Exception type + our own detail string only. Callers must never put document content in `detail`."""
    return f"{type(exc).__name__}: {exc}"[:limit]
```

```python
# ddb.py
from decimal import Decimal
def to_decimal(x):
    if isinstance(x, float): return Decimal(str(round(x, 1)))
    if isinstance(x, list):  return [to_decimal(v) for v in x]
    if isinstance(x, dict):  return {k: to_decimal(v) for k, v in x.items()}
    return x
def from_decimal(x):
    if isinstance(x, Decimal): return float(x)
    if isinstance(x, list):    return [from_decimal(v) for v in x]
    if isinstance(x, dict):    return {k: from_decimal(v) for k, v in x.items()}
    return x
def conditional_update(table, **kwargs) -> bool:
    """Returns False (not raising) when the ConditionExpression fails — that is the expected no-regression path."""
    try:
        table.update_item(**kwargs); return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
```

```python
# normalization.py
import json, os, re
from functools import lru_cache
DATA_DIR = os.environ.get("RS_DATA_DIR", "/opt/data")

@lru_cache(maxsize=None)
def _load(name):
    with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)

def skills():             return _load("skills_dictionary")
def titles():             return _load("job_titles_dictionary")
def synonyms():           return _load("synonyms")
def title_families():     return _load("title_families")
def case_sensitive_skills(): return _load("case_sensitive_skills")

def normalize_skill(s: str) -> str:
    s = " ".join(s.lower().split()); return synonyms()["skills"].get(s, s)
def normalize_title(t: str) -> str:
    t = " ".join(t.lower().split()); return synonyms()["titles"].get(t, t)
def normalize_list(values) -> list[str]:
    return sorted({v for v in values if v})

def skill_patterns() -> list[str]:   # dictionary ∪ synonym keys, minus case-sensitive canonicals
    cs = set(case_sensitive_skills().values())
    return sorted((set(skills()) | set(synonyms()["skills"])) - cs)
def title_patterns() -> list[str]:
    return sorted(set(titles()) | set(synonyms()["titles"]))

_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")
def extract_email(text: str) -> str | None:        # deterministic — NOT NLP (R-HON-06)
    m = _EMAIL.search(text); return m.group(0).lower() if m else None

_MIN_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b", re.I)
def extract_min_years(text: str) -> int | None:     # deterministic — NOT NLP
    vals = [int(m.group(1)) for m in _MIN_YEARS.finditer(text) if 0 < int(m.group(1)) <= 30]
    return min(vals) if vals else None
```

```python
# fanout.py
import json, os, boto3
from boto3.dynamodb.conditions import Key
_sqs = boto3.client("sqs"); _ddb = boto3.resource("dynamodb")

def enqueue_one(job_id, candidate_id, reason):
    _sqs.send_message(QueueUrl=os.environ["SCORING_QUEUE_URL"],
                      MessageBody=json.dumps({"job_id": job_id, "candidate_id": candidate_id, "reason": reason}))

def enqueue_rescore(job_id, reason) -> int:
    """Enqueue every PARSED candidate of the job. ConsistentRead makes the D-18 race argument hold."""
    table = _ddb.Table(os.environ["CANDIDATES_TABLE"])
    ids, kwargs = [], {"KeyConditionExpression": Key("job_id").eq(job_id), "ConsistentRead": True,
                       "ProjectionExpression": "candidate_id, parse_status"}
    while True:
        page = table.query(**kwargs)
        ids += [i["candidate_id"] for i in page["Items"] if i.get("parse_status") == "parsed"]
        if "LastEvaluatedKey" not in page: break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    for i in range(0, len(ids), 10):
        batch = [{"Id": str(n), "MessageBody": json.dumps({"job_id": job_id, "candidate_id": c, "reason": reason})}
                 for n, c in enumerate(ids[i:i + 10])]
        resp = _sqs.send_message_batch(QueueUrl=os.environ["SCORING_QUEUE_URL"], Entries=batch)
        if resp.get("Failed"):
            raise RuntimeError(f"fan-out partial failure: {len(resp['Failed'])} entries")
    return len(ids)
```

### 5.3 Layer builds (makefile build method — deterministic layout)

`template.yaml`:
```yaml
CommonLayer:
  Type: AWS::Serverless::LayerVersion
  Properties: {LayerName: !Sub rs-common-${EnvName}, ContentUri: backend/, CompatibleRuntimes: [python3.12], CompatibleArchitectures: [x86_64]}
  Metadata: {BuildMethod: makefile}
NlpLayer:
  Type: AWS::Serverless::LayerVersion
  Properties: {LayerName: !Sub rs-nlp-${EnvName}, ContentUri: backend/layers/nlp_layer/, CompatibleRuntimes: [python3.12], CompatibleArchitectures: [x86_64]}
  Metadata: {BuildMethod: makefile}
```
`backend/Makefile`:
```make
build-CommonLayer:
	mkdir -p "$(ARTIFACTS_DIR)/python" "$(ARTIFACTS_DIR)/data"
	cp -R layers/common_layer/python/rs_common "$(ARTIFACTS_DIR)/python/"
	cp data/*.json "$(ARTIFACTS_DIR)/data/"
```
`backend/layers/nlp_layer/Makefile`:
```make
build-NlpLayer:
	pip install -r requirements.txt -t "$(ARTIFACTS_DIR)/python" \
	    --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 --no-cache-dir
```
`backend/layers/nlp_layer/requirements.txt`: pin spaCy and the model to **matching minor versions** (for example `spacy==3.8.*` with `en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl`), plus `python-dateutil` (missing from the original plan). Verify the unzipped size (< 250 MB with the function; T-006). If it's over, switch NLP to an image and record a decision.

Result at runtime: `/opt/python/rs_common/…`, `/opt/data/*.json`, `/opt/python/spacy/…`.

## 6. Document Extraction (`backend/ingestion/extraction/`, T-030–T-038)

### 6.1 Packaging
- Base image from the D-34 spike (`01` §2). **Change the Docker context to `./backend`** so the image can `COPY layers/common_layer/python/rs_common` (container functions can't use layers):
```yaml
ExtractionFunction:
  Metadata: {Dockerfile: ingestion/extraction/Dockerfile, DockerContext: ./backend, DockerTag: python3.12-v2}
```
- `requirements.txt` (pinned): `pypdf`, `PyMuPDF`, `python-docx`, `pytesseract`, `Pillow`.
- Config (already set in phase 1): 1536 MB, 120 s, 1024 MB `/tmp`, x86_64.
- **Licence note:** PyMuPDF is AGPL. That's acceptable for this academic deliverable; mention it in `docs/deliverables.md` (T-111).

### 6.2 Reference implementation
```python
# backend/ingestion/extraction/app/handler.py
import json, os, shutil, uuid, zipfile
from dataclasses import dataclass
from urllib.parse import unquote_plus

import boto3, docx, fitz, pytesseract
from botocore.config import Config
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from rs_common import clock, ids, log
from rs_common.ddb import conditional_update
from rs_common.errors import ErrorCode as C, Stage as S, TerminalError, TransientError, safe_message

MAX_FILE_BYTES, MAX_PDF_PAGES, OCR_DPI = 10_485_760, 10, 200
NATIVE_PAGE_MIN_CHARS, MIN_USABLE_CHARS, MAX_TEXT_CHARS = 40, 100, 100_000
RESUME_EXT = {"pdf", "docx", "png", "jpg", "jpeg", "tiff"}
JD_EXT = RESUME_EXT | {"txt"}                          # txt only exists when the API wrote a pasted JD (D-45)
Image.MAX_IMAGE_PIXELS = 50_000_000                    # decompression-bomb guard (R-SEC-05)

s3 = boto3.client("s3")
lambda_client = boto3.client("lambda", config=Config(read_timeout=40, connect_timeout=5, retries={"max_attempts": 0}))  # D-43
_ddb = boto3.resource("dynamodb")
JOBS = _ddb.Table(os.environ["JOBS_TABLE"])
CANDIDATES = _ddb.Table(os.environ["CANDIDATES_TABLE"])
FAILED = _ddb.Table(os.environ["FAILED_JOBS_TABLE"])
NLP_FUNCTION_NAME = os.environ["NLP_FUNCTION_NAME"]

@dataclass(frozen=True)
class Ref:
    doc_type: str; job_id: str; candidate_id: str | None; key: str; ext: str

def lambda_handler(event, context):
    for record in event["Records"]:                                    # BatchSize = 1
        receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
        body = json.loads(record["body"])
        if body.get("Event") == "s3:TestEvent":                         # sent once when notifications are configured
            continue
        for s3rec in body.get("Records", []):
            process_object(s3rec["s3"]["bucket"]["name"], unquote_plus(s3rec["s3"]["object"]["key"]), receive_count)

def parse_key(key: str) -> Ref | None:
    parts = key.split("/")
    if len(parts) == 3 and parts[0] == "jd-uploads":
        doc_type, job_id, cand, fname = "jd", parts[1], None, parts[2]
    elif len(parts) == 4 and parts[0] == "resume-uploads":
        doc_type, job_id, cand, fname = "resume", parts[1], parts[2], parts[3]
    else:
        return None
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    return Ref(doc_type, job_id, cand, key, ext)

def process_object(bucket, key, receive_count):
    ref = parse_key(key)
    if ref is None:                                                    # not ours — audit, never retry
        record_failure(None, S.ORPHAN_OBJECT, TerminalError(None, S.ORPHAN_OBJECT, "key matches no upload prefix"), receive_count, True)
        return
    workdir = f"/tmp/{uuid.uuid4().hex}"                               # R-SEC-05: never /tmp/{basename}
    os.makedirs(workdir)
    try:
        if not mark_ingest_started(ref):
            raise TerminalError(None, S.ORPHAN_OBJECT, "no placeholder item for this key")
        allowed = JD_EXT if ref.doc_type == "jd" else RESUME_EXT
        if ref.ext not in allowed:
            raise TerminalError(C.UNSUPPORTED_FORMAT, S.UNSUPPORTED_FORMAT, f"extension .{ref.ext} not allowed")
        path = download(bucket, ref, workdir)
        text, meta = extract(path, ref.ext)
        if len("".join(text.split())) < MIN_USABLE_CHARS:
            raise TerminalError(C.UNREADABLE_DOCUMENT, S.OCR if meta.get("ocr_pages") else S.PDF_EXTRACT,
                                f"only {len(text.strip())} usable chars")
        invoke_nlp(ref, text, meta)
        log.info("ingested", stage="extraction", job_id=ref.job_id, candidate_id=ref.candidate_id,
                 doc_type=ref.doc_type, file_type=meta["file_type"], ocr_pages=meta.get("ocr_pages", 0))
    except TerminalError as e:                                          # R-ERR-02: record, mark, ACK
        record_failure(ref, e.stage, e, receive_count, terminal=True)
        if e.code is not None:
            mark_error(ref, e.code)
    except TransientError as e:                                         # R-ERR-03: record, re-raise
        record_failure(ref, e.stage, e, receive_count, terminal=False)
        raise
    except Exception as e:                                              # unknown → treat as transient
        record_failure(ref, S.S3_DOWNLOAD if "botocore" in type(e).__module__ else S.PDF_EXTRACT, e, receive_count, terminal=False)
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

def download(bucket, ref, workdir):
    try:
        size = s3.head_object(Bucket=bucket, Key=ref.key)["ContentLength"]
    except Exception as e:
        raise TransientError(S.S3_DOWNLOAD, f"head_object failed: {type(e).__name__}") from e
    if size > MAX_FILE_BYTES:                                           # defence in depth; the POST policy already caps size
        raise TerminalError(C.FILE_TOO_LARGE, S.UNSUPPORTED_FORMAT, f"{size} bytes")
    path = os.path.join(workdir, f"source.{ref.ext}")
    try:
        s3.download_file(bucket, ref.key, path)
    except Exception as e:
        raise TransientError(S.S3_DOWNLOAD, f"download failed: {type(e).__name__}") from e
    return path

def extract(path, ext):
    if ext == "pdf":  return extract_pdf(path)
    if ext == "docx": return extract_docx(path), {"file_type": "docx"}
    if ext == "txt":  return open(path, encoding="utf-8", errors="replace").read(), {"file_type": "text"}
    return extract_image(path)

def extract_pdf(path):
    with open(path, "rb") as f:
        if b"%PDF-" not in f.read(1024):                               # R-VAL-05 magic bytes
            raise TerminalError(C.UNSUPPORTED_FORMAT, S.UNSUPPORTED_FORMAT, "not a PDF")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):             # owner-only passwords decrypt with ""
            raise TerminalError(C.UNREADABLE_DOCUMENT, S.PDF_EXTRACT, "password-protected PDF")
        n = len(reader.pages)
    except TerminalError:
        raise
    except Exception as e:
        raise TerminalError(C.UNREADABLE_DOCUMENT, S.PDF_EXTRACT, f"cannot open PDF: {type(e).__name__}") from e
    if n == 0:
        raise TerminalError(C.UNREADABLE_DOCUMENT, S.PDF_EXTRACT, "PDF has no pages")
    if n > MAX_PDF_PAGES:
        raise TerminalError(C.TOO_MANY_PAGES, S.PDF_EXTRACT, f"{n} pages")
    pages = []
    for p in reader.pages:
        try:    pages.append(p.extract_text() or "")
        except Exception: pages.append("")
    ocr_idx = [i for i, t in enumerate(pages) if len(t.strip()) < NATIVE_PAGE_MIN_CHARS]    # per page (D-42, R-HON-04)
    if ocr_idx:
        try:
            with fitz.open(path) as doc:
                for i in ocr_idx:
                    pix = doc[i].get_pixmap(dpi=OCR_DPI, alpha=False)
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    pages[i] = pytesseract.image_to_string(img, lang="eng")                # real OCR (R-HON-03)
        except Exception as e:
            raise TransientError(S.OCR, f"OCR failed: {type(e).__name__}") from e
    file_type = "pdf_native" if not ocr_idx else ("pdf_scanned" if len(ocr_idx) == n else "pdf_mixed")
    return "\n".join(pages), {"file_type": file_type, "page_count": n, "ocr_pages": len(ocr_idx)}

def extract_docx(path):
    if not zipfile.is_zipfile(path):
        raise TerminalError(C.UNSUPPORTED_FORMAT, S.UNSUPPORTED_FORMAT, "not a DOCX (not a zip)")
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            raise TerminalError(C.UNSUPPORTED_FORMAT, S.UNSUPPORTED_FORMAT, "zip is not a Word document")
        if sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024:                 # zip-bomb guard
            raise TerminalError(C.UNREADABLE_DOCUMENT, S.DOCX_EXTRACT, "uncompressed size too large")
    try:
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)
    except Exception as e:
        raise TerminalError(C.UNREADABLE_DOCUMENT, S.DOCX_EXTRACT, f"python-docx failed: {type(e).__name__}") from e

def extract_image(path):
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if im.format not in {"PNG", "JPEG", "TIFF"}:
                raise TerminalError(C.UNSUPPORTED_FORMAT, S.UNSUPPORTED_FORMAT, f"image format {im.format}")
            frames = getattr(im, "n_frames", 1)                         # multi-page TIFF
            if frames > MAX_PDF_PAGES:
                raise TerminalError(C.TOO_MANY_PAGES, S.OCR, f"{frames} frames")
            texts = []
            for i in range(frames):
                im.seek(i)
                texts.append(pytesseract.image_to_string(im.convert("RGB"), lang="eng"))
        return "\n".join(texts), {"file_type": "image", "page_count": frames, "ocr_pages": frames}
    except TerminalError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, SyntaxError, OSError) as e:
        raise TerminalError(C.UNREADABLE_DOCUMENT if not isinstance(e, UnidentifiedImageError) else C.UNSUPPORTED_FORMAT,
                            S.OCR, f"image rejected: {type(e).__name__}") from e
    except Exception as e:
        raise TransientError(S.OCR, f"OCR failed: {type(e).__name__}") from e

def invoke_nlp(ref, text, meta):
    payload = {"doc_type": ref.doc_type, "job_id": ref.job_id, "candidate_id": ref.candidate_id,
               "extracted_text": text[:MAX_TEXT_CHARS],
               "extraction_metadata": {"source_key": ref.key, "char_count": len(text),
                                       "text_truncated": len(text) > MAX_TEXT_CHARS, **meta}}
    try:
        resp = lambda_client.invoke(FunctionName=NLP_FUNCTION_NAME, InvocationType="RequestResponse",
                                    Payload=json.dumps(payload).encode("utf-8"))
    except Exception as e:
        raise TransientError(S.NLP, f"invoke failed: {type(e).__name__}") from e
    if resp.get("FunctionError"):
        err_type = json.loads(resp["Payload"].read() or b"{}").get("errorType", "Unknown")
        if err_type == "EmptyDocumentError":
            raise TerminalError(C.UNREADABLE_DOCUMENT, S.NLP, "no tokens after NLP")
        if err_type == "OrphanRecordError":
            raise TerminalError(None, S.ORPHAN_OBJECT, "item vanished before NLP write")
        raise TransientError(S.NLP, f"nlpProcessing raised {err_type}")   # type only — message may contain text

def _item_key(ref):
    if ref.doc_type == "resume":
        return CANDIDATES, {"job_id": ref.job_id, "candidate_id": ref.candidate_id}
    return JOBS, {"job_id": ref.job_id}

def mark_ingest_started(ref) -> bool:
    table, key = _item_key(ref)
    now = clock.now_iso()
    return conditional_update(table, Key=key,
        UpdateExpression="SET ingest_started_at = if_not_exists(ingest_started_at, :t), updated_at = :t",
        ConditionExpression="attribute_exists(job_id)", ExpressionAttributeValues={":t": now})

def mark_error(ref, code):
    table, key = _item_key(ref)
    ok = conditional_update(table, Key=key,
        UpdateExpression="SET parse_status = :e, error_code = :c, updated_at = :t",
        ConditionExpression="attribute_exists(job_id) AND parse_status <> :p",       # R-DATA / Rules §5: never regress parsed
        ExpressionAttributeValues={":e": "error", ":c": str(code), ":p": "parsed", ":t": clock.now_iso()})
    if not ok:
        log.info("status_not_regressed", stage="extraction", job_id=ref.job_id, candidate_id=ref.candidate_id)

def record_failure(ref, stage, exc, receive_count, terminal):
    item = {"job_id": ref.job_id if ref else "unknown", "failure_id": ids.failure_id(), "stage": str(stage),
            "error_type": type(exc).__name__, "error_message": safe_message(exc), "terminal": terminal,
            "retry_count": receive_count, "created_at": clock.now_iso(), "expires_at": clock.epoch_in_days(90)}
    if ref and ref.candidate_id:
        item["candidate_id"] = ref.candidate_id
    FAILED.put_item(Item=item)
    log.warning("failure_recorded", stage=str(stage), terminal=terminal, job_id=item["job_id"],
                candidate_id=item.get("candidate_id"), error_type=item["error_type"])
```

### 6.3 Function wiring
```yaml
ExtractionFunction:
  Properties:
    Environment:
      Variables:
        NLP_FUNCTION_NAME: !Ref NlpFunction
        JOBS_TABLE: !Ref JobsTable
        CANDIDATES_TABLE: !Ref CandidatesTable
        FAILED_JOBS_TABLE: !Ref FailedJobsTable
    Events:
      Ingestion:
        Type: SQS
        Properties:
          Queue: !GetAtt IngestionQueue.Arn
          BatchSize: 1
          ScalingConfig: {MaximumConcurrency: 3}      # D-25 — throttling would otherwise push healthy messages to the DLQ
```

## 7. S3 → IngestionQueue wiring (T-038)

Add to `UploadBucket` (plus `DependsOn: IngestionQueuePolicy`). There's no cycle: the queue policy references the bucket by its name string, not `!Ref`.
```yaml
NotificationConfiguration:
  QueueConfigurations:
    - Event: s3:ObjectCreated:*
      Queue: !GetAtt IngestionQueue.Arn
      Filter: {S3Key: {Rules: [{Name: prefix, Value: jd-uploads/}]}}
    - Event: s3:ObjectCreated:*
      Queue: !GetAtt IngestionQueue.Arn
      Filter: {S3Key: {Rules: [{Name: prefix, Value: resume-uploads/}]}}
```
`exports/` is intentionally not wired.

## 8. NLP (`backend/ingestion/nlp/`, T-040–T-046)

### 8.1 Method honesty (unchanged contract — `Details.md` §3)
| Field | Method | NLP? |
|---|---|---|
| name | spaCy `PERSON` (2–4 tokens) in the first 5 non-empty lines, else the first `PERSON` anywhere | Yes |
| employers | spaCy `ORG`, deduped, minus anything that normalizes to a known skill (R-DATA-10) | Yes |
| date mentions | spaCy `DATE` spans — used to corroborate experience ranges | Yes |
| skills / titles | spaCy tokenizer + `PhraseMatcher` over dictionary ∪ synonym keys, then normalization | Hybrid |
| experience years | Deterministic range parsing + interval merge (§8.3) | No |
| email, JD min years | Regex | No |

### 8.2 Reference implementation
```python
# backend/ingestion/nlp/handler.py
import os
import boto3, spacy
from spacy.matcher import PhraseMatcher

from rs_common import clock, fanout, log, normalization as norm
from rs_common.ddb import conditional_update, to_decimal
from rs_common.errors import EmptyDocumentError, OrphanRecordError
from rs_common.experience import compute_experience

_ddb = boto3.resource("dynamodb")
JOBS = _ddb.Table(os.environ["JOBS_TABLE"])
CANDIDATES = _ddb.Table(os.environ["CANDIDATES_TABLE"])

# ---- cold start: config check, model, matchers (never per invocation) ----
_mode = _ddb.Table(os.environ["CONFIG_TABLE"]).get_item(Key={"config_key": "nlp_engine_mode"}).get("Item", {}).get("config_value")
if _mode != "spacy_hybrid":                                  # D-13: fail loudly; no fallback engine exists
    raise RuntimeError(f"unsupported nlp_engine_mode: {_mode!r}")
nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
nlp.max_length = 200_000
SKILLS_CI = PhraseMatcher(nlp.vocab, attr="LOWER"); SKILLS_CI.add("SKILL", [nlp.make_doc(p) for p in norm.skill_patterns()])
SKILLS_CS = PhraseMatcher(nlp.vocab, attr="ORTH");  SKILLS_CS.add("SKILL", [nlp.make_doc(p) for p in norm.case_sensitive_skills()])
TITLES = PhraseMatcher(nlp.vocab, attr="LOWER");    TITLES.add("TITLE", [nlp.make_doc(p) for p in norm.title_patterns()])
_KNOWN_SKILLS = set(norm.skills())

def lambda_handler(event, context):
    # No try/except-and-record here (D-20): exceptions surface as FunctionError to documentExtraction.
    doc_type, job_id, cand_id = event["doc_type"], event["job_id"], event.get("candidate_id")
    text, meta = event["extracted_text"], event.get("extraction_metadata", {})
    doc = nlp(text)
    if not any(not t.is_space and not t.is_punct for t in doc):
        raise EmptyDocumentError("no tokens")

    skills = norm.normalize_list(norm.normalize_skill(doc[s:e].text) for _, s, e in SKILLS_CI(doc))
    skills = norm.normalize_list(skills + [norm.case_sensitive_skills()[doc[s:e].text] for _, s, e in SKILLS_CS(doc)])
    titles = norm.normalize_list(norm.normalize_title(doc[s:e].text) for _, s, e in TITLES(doc))

    if doc_type == "resume":
        write_resume(job_id, cand_id, doc, text, meta, skills, titles)
        fanout.enqueue_one(job_id, cand_id, "candidate_parsed")
    else:
        write_jd(job_id, text, skills, titles)
        n = fanout.enqueue_rescore(job_id, "job_ready")                  # D-18
        log.info("jd_fanout", stage="nlp", job_id=job_id, enqueued=n)
    return {"status": "parsed"}

def pick_name(doc, text):
    non_empty = [l for l in text.splitlines() if l.strip()]
    cutoff = text.find(non_empty[4]) + len(non_empty[4]) if len(non_empty) >= 5 else len(text)
    persons = [e for e in doc.ents if e.label_ == "PERSON" and 2 <= len(e.text.split()) <= 4]
    top = [e for e in persons if e.start_char < cutoff]
    chosen = (top or persons or [None])[0]
    return " ".join(chosen.text.split()) if chosen else None

def write_resume(job_id, cand_id, doc, text, meta, skills, titles):
    name = pick_name(doc, text)
    employers = norm.normalize_list(" ".join(e.text.split()) for e in doc.ents
                                    if e.label_ == "ORG" and norm.normalize_skill(e.text) not in _KNOWN_SKILLS)
    date_spans = [(e.start_char, e.end_char) for e in doc.ents if e.label_ == "DATE"]
    exp = compute_experience(text, date_spans, today=clock.today())
    values = {":sk": skills, ":ti": titles, ":em": employers, ":est": exp.basis == "estimated",
              ":ft": meta.get("file_type"), ":pc": meta.get("page_count", 1), ":op": meta.get("ocr_pages", 0),
              ":cc": meta.get("char_count", len(text)), ":p": "parsed", ":t": clock.now_iso()}
    sets = ["skills=:sk", "titles_held=:ti", "employers=:em", "experience_estimated=:est", "file_type=:ft",
            "page_count=:pc", "ocr_pages=:op", "char_count=:cc", "parse_status=:p", "updated_at=:t"]
    removes = ["error_code"]
    for attr, val in (("#n", name), ("email", norm.extract_email(text))):
        if val: sets.append(f"{attr}=:{attr.strip('#')}"); values[f":{attr.strip('#')}"] = val
        else:   removes.append(attr)
    if exp.years is not None:
        sets.append("total_experience_years=:yrs"); values[":yrs"] = to_decimal(float(exp.years))   # R-DATA-01
    else:
        removes.append("total_experience_years")                                                    # unknown ≠ 0 (R-HON-09)
    ok = conditional_update(CANDIDATES, Key={"job_id": job_id, "candidate_id": cand_id},
        UpdateExpression="SET " + ", ".join(sets) + " REMOVE " + ", ".join(removes),
        ConditionExpression="attribute_exists(candidate_id)",
        ExpressionAttributeNames={"#n": "name"}, ExpressionAttributeValues=values)
    if not ok:
        raise OrphanRecordError("candidate placeholder missing")

def write_jd(job_id, text, skills, titles):
    min_years = norm.extract_min_years(text)
    sets = ["derived_skills=:s", "derived_titles=:ti", "parse_status=:p", "updated_at=:t"]
    values = {":s": skills, ":ti": titles, ":p": "parsed", ":t": clock.now_iso()}
    if min_years is not None:
        sets.append("derived_min_experience_years=:m"); values[":m"] = min_years
    # Writes derived_* ONLY — explicit required_* are never touched (R-BUS-03, D-29)
    ok = conditional_update(JOBS, Key={"job_id": job_id}, UpdateExpression="SET " + ", ".join(sets) + " REMOVE error_code",
                            ConditionExpression="attribute_exists(job_id)", ExpressionAttributeValues=values)
    if not ok:
        raise OrphanRecordError("job missing")
```
(The `REMOVE` clause must be omitted when `removes` is empty; `error_code` is always in the list, so it never is. Keep that invariant, or guard it.)

### 8.3 Experience computation — `rs_common/experience.py` (pure, spaCy-free, unit-tested)

Contract: `compute_experience(text: str, date_spans: list[tuple[int, int]], today: date) -> Experience(years: float | None, basis: "computed" | "estimated" | "unknown")`

Algorithm (D-27; replaces the consecutive-DATE pairing, which broke on "2019 – 2021" single entities, a missing "Present", overlaps, and education dates):
1. **Sections.** Scan lines for headers (a line that is ≤ 4 words and matches, case-insensitively): experience set = `experience | work experience | professional experience | employment | employment history | work history | career history`; stop set = `education | academic | qualifications | projects | skills | certifications | achievements | awards | publications | interests | summary | profile | references`. The experience section runs from an experience header to the next header of either set.
2. **Ranges.** Regex over candidate text:
   - `MONTH = (jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?`
   - `DATE = (MONTH\s*'?\d{2,4} | \d{1,2}[/.-]\d{4} | \d{4})`
   - `PRESENT = (present|current|now|till date|to date|ongoing)`
   - `RANGE = DATE \s*(-|–|—|to|until|till)\s* (DATE|PRESENT)`
3. **Scope.** If an experience section exists, use only ranges inside it. Otherwise use ranges anywhere **outside** stop-set sections, and a range counts only if it overlaps a spaCy `DATE` span (this is the NLP corroboration). With no headers at all, use the whole text with DATE corroboration.
4. **Parse.** Month-year → first of the month; `MM/YYYY` → first of the month; year only → Jan 1 for a start, Dec 31 for an end (and mark precision "year"); PRESENT → `today`; two-digit years → 20xx if ≤ the current two-digit year, else 19xx.
5. **Sanity.** Drop ranges with start > today, end < start, start year < 1960, or span > 50 years. Clamp end to today.
6. **Merge** overlapping or adjacent intervals and sum days / 365.25, rounded to 1 dp.
7. **Basis.** No intervals → `(None, "unknown")`. `computed` iff an experience section was found **and** every endpoint used has month precision; otherwise `estimated`.

Required unit cases (≥15): "Jan 2020 – Present"; "2019 – 2021" (year precision → estimated); two overlapping jobs (merged); education range excluded; "03/2018 - 06/2020"; "Sept 2017 to Aug 2019"; a future start dropped; a reversed range dropped; no dates → unknown; a DATE-uncorroborated range outside sections ignored; "'19 – '21"; multiple sections; "till date"; a 60-year span dropped; a resume with only a summary.

### 8.4 Function wiring
```yaml
NlpFunction:
  Properties:
    CodeUri: backend/ingestion/nlp/
    Handler: handler.lambda_handler
    Timeout: 30
    MemorySize: 1024
    Layers: [!Ref CommonLayer, !Ref NlpLayer]
    Environment:
      Variables: {JOBS_TABLE: !Ref JobsTable, CANDIDATES_TABLE: !Ref CandidatesTable, CONFIG_TABLE: !Ref ConfigTable, SCORING_QUEUE_URL: !Ref ScoringQueue}
    # No Events — invoked only by ExtractionFunction.
```

## 9. Execution-role IAM (this phase)

| Function | Statements |
|---|---|
| `ExtractionFunction` | `s3:GetObject` on `${UploadBucket.Arn}/jd-uploads/*` and `/resume-uploads/*` · `dynamodb:UpdateItem` on Jobs, Candidates · `dynamodb:PutItem` on FailedJobs · `lambda:InvokeFunction` on `NlpFunction.Arn` |
| `NlpFunction` | `dynamodb:UpdateItem` on Jobs, Candidates · `dynamodb:Query` on Candidates · `dynamodb:GetItem` on Config · `sqs:SendMessage` on ScoringQueue — **no** `failed_jobs` access (D-20) |

The SQS event source mapping adds its own `sqs:ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes` to the extraction role (SAM does this automatically for `Events: SQS`).

## 10. Testing

| Level | What | How |
|---|---|---|
| Unit | `rs_common` normalization, ddb, errors, experience (≥15 cases), `parse_key` (incl. `unquote_plus` of `resume-uploads/job_x/cand_y/resume.pdf` and a `+`-encoded key) | `pytest` with `RS_DATA_DIR=backend/data` |
| Component | Extraction handler against fixtures with S3/DynamoDB mocked (moto) and the NLP invoke stubbed: native PDF, scanned PDF, **mixed PDF** (only the scanned page OCR'd), DOCX with tables, PNG, multi-page TIFF, `.pdf` that's really text (terminal `unsupported_format`), corrupt PDF (terminal), encrypted PDF (terminal), blank scan (terminal `unreadable_document`), 11-page PDF (terminal), an `EmptyDocumentError` FunctionError (terminal), a `RuntimeError` FunctionError (transient re-raise) | `sam local invoke` inside the image, or `docker run` with pytest |
| Component | NLP handler with a real spaCy model on fixture texts: name, employers without skills, "k8s" → kubernetes, "go to market" ≠ go, JD writes only `derived_*`, orphan → `OrphanRecordError` | pytest in the build container |
| Deployed | Upload each fixture with the aws CLI after creating placeholders with `tests/integration/make_placeholders.py`; assert the items; one `failed_jobs` row per failure; no DLQ traffic for terminal cases; a duplicate event (re-copy the same object) causes no status regression | `tests/integration/phase2.py dev` |

Sample-output deliverable (T-110, completed in phase 5): the native PDF, scanned PDF, and DOCX runs are captured by `scripts/capture_sample_output.py`. It runs the **same extraction image** locally on the fixture to get the text, reads the deployed run's candidate item for the entities, and writes `docs/sample-nlp-output/<type>.json` with a per-field `method` key. The output is generated, never hand-edited.

## 11. Definition of Done

- [ ] `rs_common` unit tests green; coverage ≥ 90% for `normalization`, `experience`, `ddb`, `errors`
- [ ] `scripts/validate_data.py` passes; ≥250 skills, ≥120 titles, ≥15 title families
- [ ] Layers build with `sam build --use-container`; NLP function + layers < 250 MB unzipped; `/opt/data/*.json` present at runtime
- [ ] JD upload (file **and** API-written `jd.txt`) → job has `derived_*`, `parse_status=parsed`; explicit `required_*` untouched
- [ ] Native PDF, scanned PDF, mixed PDF, DOCX, and image resumes → `candidates` item populated from **their own text**; `file_type`, `page_count`, `ocr_pages` correct
- [ ] `total_experience_years` is a DynamoDB **Number** (console "Number" type) when known and **absent** when unknown
- [ ] Each terminal case produces exactly **one** `failed_jobs` row (`terminal=true`), `parse_status=error` with the right `error_code`, and **no** redelivery (IngestionQueue `NumberOfMessagesReceived` for that object = 1)
- [ ] A forced transient failure (e.g. temporarily remove `s3:GetObject`) retries 3× and leaves 3 rows with `terminal=false`
- [ ] Resumes parsed before their JD are enqueued again by the JD fan-out (inspect ScoringQueue or the NLP logs `jd_fanout enqueued=n`)
- [ ] `grep -rn "failed_jobs\|FAILED_JOBS" backend/ingestion/nlp/` → no matches
- [ ] Log review of a full run: no resume text, emails, or names in any log line
- [ ] Code review against §1: no filename branching, canned text, fabricated confidences, or `textract`/`comprehend` references

Once every box is checked, hand off to **`03-scoring-and-api.md`**.
