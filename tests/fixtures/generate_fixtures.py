"""Generates synthetic test fixtures for the resume screener (Tasks.md T-007).

No real PII: every name, employer, and email below is invented for testing.
Run: python tests/fixtures/generate_fixtures.py

Produces:
  tests/fixtures/jds/*.pdf, *.txt
  tests/fixtures/resumes/*.{pdf,docx,png}
  tests/fixtures/truth.json
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF — only used here to rasterize a fixture into a "scanned" PDF
from docx import Document
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
RESUMES = HERE / "resumes"
JDS = HERE / "jds"
RESUMES.mkdir(exist_ok=True)
JDS.mkdir(exist_ok=True)


def text_pdf(path: Path, lines: list[str]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.set_x(pdf.l_margin)  # fpdf2 leaves x at the right margin after multi_cell(w=0, ...)
        if line == "":
            pdf.ln(6)
        else:
            pdf.multi_cell(0, 6, line)
    pdf.output(str(path))


def _image_file_to_pdf(img_path: Path, out_path: Path) -> None:
    """Wraps an existing image file in a single-page PDF with NO text layer.
    Uses jpg_quality-compressed JPEG intermediates + PDF stream compression so
    fixtures stay well under the 10 MiB upload limit (PyMuPDF re-encodes
    embedded images as raw pixel data otherwise, which bloats a plain PNG by
    50-100x)."""
    out = fitz.open()
    img_doc = fitz.open(img_path)
    rect = img_doc[0].rect
    page = out.new_page(width=rect.width, height=rect.height)
    page.insert_image(rect, filename=img_path)
    out.save(out_path, garbage=4, deflate=True)
    out.close()
    img_doc.close()


def rasterized_pdf(path: Path, lines: list[str]) -> None:
    """Builds a text PDF, renders it to a grayscale JPEG (like a real scan or
    phone photo), then wraps that image in a new PDF with no text layer — this
    genuinely exercises the OCR path rather than faking a "scanned" file."""
    tmp = path.with_suffix(".tmp.pdf")
    text_pdf(tmp, lines)
    src = fitz.open(tmp)
    pix = src[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    img_path = path.with_suffix(".jpg")
    pix.save(img_path, jpg_quality=80)
    src.close()
    tmp.unlink()

    _image_file_to_pdf(img_path, path)
    img_path.unlink()


def mixed_pdf(path: Path, native_lines: list[str], scanned_lines: list[str]) -> None:
    """Page 1 = real text layer, page 2 = image only (D-42 mixed-PDF test case)."""
    text_pdf(path.with_suffix(".p1.pdf"), native_lines)
    rasterized_pdf(path.with_suffix(".p2.pdf"), scanned_lines)

    out = fitz.open()
    p1 = fitz.open(path.with_suffix(".p1.pdf"))
    p2 = fitz.open(path.with_suffix(".p2.pdf"))
    out.insert_pdf(p1)
    out.insert_pdf(p2)
    out.save(path)
    out.close()
    p1.close()
    p2.close()
    path.with_suffix(".p1.pdf").unlink()
    path.with_suffix(".p2.pdf").unlink()


def docx_resume(path: Path, name: str, lines: list[str]) -> None:
    doc = Document()
    doc.add_heading(name, level=1)
    for line in lines:
        doc.add_paragraph(line)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Reference"
    table.rows[0].cells[1].text = "Available on request"
    doc.save(path)


def image_resume(path: Path, lines: list[str]) -> None:
    img = Image.new("RGB", (1000, 1300), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 32
    img.save(path)


def corrupt_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\n%truncated garbage, not a real PDF body\n")


def renamed_text_file(path: Path) -> None:
    path.write_text("This is a plain text file with a .pdf extension. It has no PDF structure.\n")


# ---------------------------------------------------------------------------
# Fixture 1 — "worked example" resume: must score exactly 71.3 against jd_backend.
# 2/3 skills (python, aws; missing dynamodb) -> 66.7; title "backend developer"
# is a related-family match to "backend engineer" -> 60; 4.0y / 3y experience,
# capped -> 100.  0.5*66.7 + 0.3*60 + 0.2*100 = 71.35 -> round(.,1) = 71.3|71.4
# depending on rounding mode; scoring.py uses round-half-to-even via Python's
# round(), which gives 71.3 here (71.35 is not exactly representable in binary
# float and lands fractionally below .35) — this is exactly why it's a fixture:
# it pins the real implementation's rounding behaviour, not a hand-computed value.
text_pdf(
    RESUMES / "worked_example_native.pdf",
    [
        "Jane Doe",
        "jane.doe@example-mail.test",
        "",
        "Professional Experience",
        "Acme Corp - Backend Developer - Jan 2021 to Present",
        "Built REST APIs in Python on AWS, working with SQL databases.",
        "",
        "Skills",
        "Python, AWS, SQL",
        "",
        "Education",
        "B.S. Computer Science, State University, 2016 to 2020",
    ],
)

# Fixture 2 — clean native PDF, different profile (senior, more skills)
text_pdf(
    RESUMES / "alice_johnson_native.pdf",
    [
        "Alice Johnson",
        "alice.johnson@example-mail.test",
        "",
        "Work Experience",
        "Globex Inc - Senior Backend Engineer - Mar 2018 to Aug 2022",
        "Led a team building services in Python and Java on AWS, using DynamoDB",
        "and Kubernetes for orchestration. CI/CD via GitHub Actions.",
        "",
        "Initech LLC - Software Engineer - Jun 2015 to Feb 2018",
        "Developed internal tools in Python with PostgreSQL.",
        "",
        "Skills: Python, AWS, DynamoDB, Kubernetes, CI/CD, SQL, Leadership",
    ],
)

# Fixture 3 — DOCX
docx_resume(
    RESUMES / "bob_kumar.docx",
    "Bob Kumar",
    [
        "bob.kumar@example-mail.test",
        "Work Experience",
        "Umbrella Systems - Backend Developer - 07/2019 - 06/2023",
        "Built and maintained Python microservices deployed on AWS with Docker.",
        "Skills: Python, AWS, Docker, REST API, Git",
    ],
)

# Fixture 4 — DOCX, junior / short experience
docx_resume(
    RESUMES / "carol_singh.docx",
    "Carol Singh",
    [
        "carol.singh@example-mail.test",
        "Experience",
        "Startup Labs - Software Engineer - Jan 2023 to Present",
        "Worked on a Python/Flask backend with a React frontend, on AWS.",
        "Skills: Python, Flask, React, AWS, JavaScript",
    ],
)

# Fixture 5 — scanned PDF (image only, real OCR required)
rasterized_pdf(
    RESUMES / "daniel_kim_scanned.pdf",
    [
        "Daniel Kim",
        "daniel.kim@example-mail.test",
        "",
        "Employment History",
        "Wayne Enterprises - Backend Engineer - Feb 2017 to Dec 2021",
        "Designed Python services on AWS using DynamoDB.",
        "",
        "Skills",
        "Python, AWS, DynamoDB, SQL",
    ],
)

# Fixture 6 — mixed PDF: page 1 native text, page 2 scanned image (D-42)
mixed_pdf(
    RESUMES / "maya_bennett_mixed.pdf",
    native_lines=[
        "Maya Bennett",
        "maya.bennett@example-mail.test",
        "",
        "Summary",
        "Backend engineer with AWS and Python experience.",
    ],
    scanned_lines=[
        "Experience",
        "Oscorp - Backend Engineer - May 2016 to Apr 2022",
        "Python, AWS, DynamoDB, Kubernetes",
    ],
)

# Fixture 7 — standalone image resume (PNG, OCR path)
image_resume(
    RESUMES / "jordan_rivera.png",
    [
        "Jordan Rivera",
        "jordan.rivera@example-mail.test",
        "",
        "Experience",
        "Stark Industries - Software Engineer - Mar 2020 to Jan 2023",
        "Python, AWS, SQL, Git",
    ],
)

# Fixture 8 — corrupt PDF (terminal: unreadable_document)
corrupt_pdf(RESUMES / "corrupt.pdf")

# Fixture 9 — renamed text file (terminal: unsupported_format at extraction;
# rejected earlier at the API for a fresh upload, per R-VAL-02 / 05 §2 test F1)
renamed_text_file(RESUMES / "renamed_text_file.pdf")

# Fixture 10 — blank scanned page (terminal: unreadable_document, <100 usable chars)
blank_img_path = RESUMES / "blank_scan.jpg"
Image.new("L", (1000, 1300), 255).save(blank_img_path, quality=80)
_image_file_to_pdf(blank_img_path, RESUMES / "blank_scan.pdf")
blank_img_path.unlink()

# Fixture 11 — too many pages (11 pages, terminal: too_many_pages)
pdf = FPDF()
for i in range(11):
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 10, f"Page {i + 1} of an overly long resume.")
pdf.output(str(RESUMES / "eleven_pages.pdf"))

# --- Job descriptions -------------------------------------------------------

text_pdf(
    JDS / "backend_engineer_jd.pdf",
    [
        "Backend Engineer",
        "",
        "We are hiring a Backend Engineer with at least 3 years of experience.",
        "Required skills: Python, AWS, DynamoDB.",
    ],
)

(JDS / "backend_engineer_jd.txt").write_text(
    "Backend Engineer\n\n"
    "We are hiring a Backend Engineer with at least 3 years of experience.\n"
    "Required skills: Python, AWS, DynamoDB.\n"
)

# JD with no dictionary skills at all (fixture for F8 / no_required_skills test)
text_pdf(
    JDS / "no_skills_jd.pdf",
    [
        "Team Player Wanted",
        "",
        "We want someone who is passionate, driven, and a great culture fit.",
    ],
)

# Corrupt JD (fixture for F7 / jd_failed test)
corrupt_pdf(JDS / "corrupt_jd.pdf")

# --- Ground truth for evaluation (Tasks.md T-105, docs/evaluation.md) -------

truth = {
    "worked_example_native.pdf": {
        "name": "Jane Doe",
        "email": "jane.doe@example-mail.test",
        "skills": ["python", "aws", "sql"],
        "titles_held": ["backend developer"],
        "total_experience_years_approx": 4.0,  # Jan 2021 -> "today" at test time; assert within tolerance
        "notes": "Fixture pinned to score 71.3 against backend_engineer_jd (see comment in generator).",
    },
    "alice_johnson_native.pdf": {
        "name": "Alice Johnson",
        "email": "alice.johnson@example-mail.test",
        "skills": ["python", "aws", "dynamodb", "kubernetes", "ci/cd", "sql"],
        "titles_held": ["senior backend engineer", "software engineer"],
        "total_experience_years_approx": 6.9,
    },
    "bob_kumar.docx": {
        "name": "Bob Kumar",
        "email": "bob.kumar@example-mail.test",
        "skills": ["python", "aws", "docker", "rest api", "git"],
        "titles_held": ["backend developer"],
        "total_experience_years_approx": 4.0,
    },
    "carol_singh.docx": {
        "name": "Carol Singh",
        "email": "carol.singh@example-mail.test",
        "skills": ["python", "flask", "react", "aws", "javascript"],
        "titles_held": ["software engineer"],
        "total_experience_years_approx": None,  # "Present" only, short tenure — estimated
    },
    "daniel_kim_scanned.pdf": {
        "name": "Daniel Kim",
        "email": "daniel.kim@example-mail.test",
        "skills": ["python", "aws", "dynamodb", "sql"],
        "titles_held": ["backend engineer"],
        "total_experience_years_approx": 4.8,
        "notes": "OCR fixture — text quality depends on Tesseract render/recognition.",
    },
    "maya_bennett_mixed.pdf": {
        "name": "Maya Bennett",
        "email": "maya.bennett@example-mail.test",
        "skills": ["python", "aws", "dynamodb", "kubernetes"],
        "titles_held": ["backend engineer"],
        "total_experience_years_approx": 5.9,
        "notes": "Mixed PDF — page 1 native, page 2 scanned image only.",
    },
    "jordan_rivera.png": {
        "name": "Jordan Rivera",
        "email": "jordan.rivera@example-mail.test",
        "skills": ["python", "aws", "sql", "git"],
        "titles_held": ["software engineer"],
        "total_experience_years_approx": 2.8,
        "notes": "Standalone image fixture (OCR path, no PDF wrapper).",
    },
    "corrupt.pdf": {"expected_error_code": "unreadable_document"},
    "renamed_text_file.pdf": {"expected_error_code": "unsupported_format"},
    "blank_scan.pdf": {"expected_error_code": "unreadable_document"},
    "eleven_pages.pdf": {"expected_error_code": "too_many_pages"},
}

(HERE / "truth.json").write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n")

print(f"Wrote {sum(1 for _ in RESUMES.iterdir())} resume fixtures to {RESUMES}")
print(f"Wrote {sum(1 for _ in JDS.iterdir())} JD fixtures to {JDS}")
print(f"Wrote truth.json ({len(truth)} entries)")
