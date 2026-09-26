#!/usr/bin/env python3
"""Generate 3 additional scorable NLP test fixtures (Phase 5 T-106 / truth.json >=10 gate).

New fixtures:
  - priya_sharma_native.pdf   native PDF, senior DevOps/SRE profile
  - lena_kowalski.docx        DOCX, data engineer profile
  - omar_hassan_scanned.pdf   scanned PDF (OCR path), frontend engineer

These deliberately cover NLP variations:
  - priya: CI/CD, infrastructure-as-code keywords (cross-domain skill variety)
  - lena:  DOCX with data-specific skills (pandas, spark, sql, postgresql)
  - omar:  OCR path; tests scanned DOCX-style layout

Run from repo root:
    python tests/fixtures/generate_extra_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import fitz
from docx import Document
from fpdf import FPDF
from pypdf import PdfWriter

HERE = Path(__file__).parent
RESUMES = HERE / "resumes"

# ---------------------------------------------------------------------------
# Helpers (copied API from generate_fixtures.py so this is self-contained)
# ---------------------------------------------------------------------------


def text_pdf(path: Path, lines: list[str]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.set_x(pdf.l_margin)
        if line == "":
            pdf.ln(6)
        else:
            pdf.multi_cell(0, 6, line)
    pdf.output(str(path))


def rasterized_pdf(path: Path, lines: list[str]) -> None:
    """Build a text PDF, render to grayscale image, re-wrap as image-only PDF."""
    tmp = path.with_suffix(".tmp.pdf")
    text_pdf(tmp, lines)
    src = fitz.open(tmp)
    pix = src[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    img_path = path.with_suffix(".jpg")
    pix.save(img_path, jpg_quality=80)
    src.close()
    tmp.unlink()

    out = fitz.open()
    img_doc = fitz.open(img_path)
    rect = img_doc[0].rect
    page = out.new_page(width=rect.width, height=rect.height)
    page.insert_image(rect, filename=img_path)
    out.save(path, garbage=4, deflate=True)
    out.close()
    img_doc.close()
    img_path.unlink()


def docx_resume(path: Path, name: str, lines: list[str]) -> None:
    doc = Document()
    doc.add_heading(name, level=1)
    for line in lines:
        doc.add_paragraph(line)
    doc.save(path)


# ---------------------------------------------------------------------------
# Fixture A — native PDF, DevOps/SRE engineer
# ---------------------------------------------------------------------------
text_pdf(
    RESUMES / "priya_sharma_native.pdf",
    [
        "Priya Sharma",
        "priya.sharma@example-mail.test",
        "",
        "Professional Experience",
        "Infosys Ltd - Site Reliability Engineer - Jun 2019 to Present",
        "Managed Kubernetes clusters on AWS. Implemented CI/CD pipelines with Jenkins",
        "and GitHub Actions. Authored Terraform modules for IaC. Monitored services",
        "with Prometheus and Grafana.",
        "",
        "Tata Consultancy Services - DevOps Engineer - Jan 2016 to May 2019",
        "Built Docker-based deployment workflows. Automated infrastructure on AWS.",
        "",
        "Skills",
        "Python, AWS, Kubernetes, Docker, Terraform, CI/CD, Prometheus, Linux",
        "",
        "Education",
        "B.Tech Computer Science, IIT Bombay, Aug 2012 to May 2016",
    ],
)

# Fixture B — DOCX, data engineer profile
docx_resume(
    RESUMES / "lena_kowalski.docx",
    "Lena Kowalski",
    [
        "lena.kowalski@example-mail.test",
        "Work Experience",
        "DataStream GmbH - Data Engineer - Mar 2020 to Present",
        "Built ETL pipelines in Python using Apache Spark and Pandas. Designed",
        "PostgreSQL schemas and migrated workloads to AWS Redshift. Used Airflow",
        "for workflow orchestration.",
        "Freelance - Data Analyst - Sep 2018 to Feb 2020",
        "SQL queries, Excel dashboards, and Python scripts for a fintech startup.",
        "Skills: Python, SQL, PostgreSQL, Spark, Pandas, AWS, Airflow, Git",
    ],
)

# Fixture C — scanned PDF, frontend engineer (OCR path)
rasterized_pdf(
    RESUMES / "omar_hassan_scanned.pdf",
    [
        "Omar Hassan",
        "omar.hassan@example-mail.test",
        "",
        "Experience",
        "Nexus Digital - Frontend Engineer - Apr 2021 to Present",
        "Developed React and TypeScript single-page apps with Redux state management.",
        "Integrated REST APIs and GraphQL endpoints. Deployed on AWS S3 / CloudFront.",
        "",
        "Pixel Agency - Junior Developer - Jul 2019 to Mar 2021",
        "HTML, CSS, JavaScript, and Node.js projects for e-commerce clients.",
        "",
        "Skills",
        "JavaScript, TypeScript, React, Redux, Node.js, GraphQL, AWS, Git",
    ],
)

# Fixture D — encrypted PDF (F3 failure case: password protected -> unreadable_document)
enc_writer = PdfWriter()
enc_writer.add_blank_page(width=612, height=792)
enc_writer.encrypt(user_password="user_secret_password_123", owner_password="owner_secret_password_123")
with open(RESUMES / "encrypted.pdf", "wb") as f:
    enc_writer.write(f)

print("Generated extra fixture files:")
for f in ["priya_sharma_native.pdf", "lena_kowalski.docx", "omar_hassan_scanned.pdf", "encrypted.pdf"]:
    size = (RESUMES / f).stat().st_size
    print(f"  {RESUMES / f}  ({size:,} bytes)")
