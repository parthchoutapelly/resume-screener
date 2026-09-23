# Extraction function — phase 1 stub

`handler.py` here is a placeholder that returns HTTP 501. Real extraction logic
(pypdf / PyMuPDF / Tesseract OCR / python-docx) lands in phase 2 —
see `docs/02-ingestion-pipeline.md` §6.

The Dockerfile at `backend/ingestion/extraction/Dockerfile` already installs the
real OCR toolchain (decided by the phase 1 T-003 spike — see `infra/README.md`
for which base image and why), so the packaging strategy doesn't change between
phase 1 and phase 2; only `app/handler.py`'s contents do.
