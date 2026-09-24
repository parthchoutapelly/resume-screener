"""T-072 / R-PRIV-01 / R-HON-08: static audit of the code base.

The runtime logger already strips forbidden keys (test_clock_ids_log), but this
catches the mistake at review time instead of relying on the safety net, and
keeps Textract/Comprehend out of the deployable code entirely.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FORBIDDEN_KWARGS = (
    "text",
    "extracted_text",
    "email",
    "name",
    "phone",
    "raw_text",
    "body",
    "skills",
    "titles_held",
    "employers",
)


def py_files():
    return [p for p in BACKEND.rglob("*.py") if ".aws-sam" not in p.parts]


def test_no_log_call_passes_a_forbidden_field():
    offenders = []
    for path in py_files():
        if path.name == "log.py":  # its docstring shows the forbidden pattern as an example
            continue
        src = path.read_text()
        for call in re.finditer(r"\blog\.(?:info|warning|error)\(", src):
            # take the call's argument text up to its matching close paren
            depth, i = 1, call.end()
            while i < len(src) and depth:
                depth += {"(": 1, ")": -1}.get(src[i], 0)
                i += 1
            args = src[call.end() : i - 1]
            for key in FORBIDDEN_KWARGS:
                if re.search(rf"(?<![\w.])\s*{key}\s*=", args):
                    offenders.append(f"{path.relative_to(REPO)}: log call passes {key}=")
    assert not offenders, offenders


def test_only_the_dlq_handler_prints_and_only_emf():
    printing = {
        str(p.relative_to(REPO)) for p in py_files() if re.search(r"^\s*print\(", p.read_text(), re.M)
    }
    # rs_common.log emits its JSON line with print(); dlqHandler emits the EMF metric.
    assert printing == {
        "backend/layers/common_layer/python/rs_common/log.py",
        "backend/reliability/dlq_handler/handler.py",
    }


def test_no_textract_or_comprehend_in_deployable_code():
    hits = []
    for path in [*py_files(), REPO / "template.yaml"]:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\b(textract|comprehend)\b", line, re.I):
                hits.append(f"{path.relative_to(REPO)}:{n}")
    assert not hits, hits


def test_table_and_queue_names_only_come_from_env_r_data_03():
    offenders = []
    for path in py_files():
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"""f?["'](jobs|candidates|failed_jobs|config)-\{?""", line):
                offenders.append(f"{path.relative_to(REPO)}:{n}")
    assert not offenders, offenders
