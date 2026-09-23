# Base image decision: D-34 (docs/Memory.md). The Lambda-official AL2023 base
# (public.ecr.aws/lambda/python:3.12) has no `tesseract` package in its repos
# (confirmed by direct test, not just a build failure) — Debian's does.
# This follows AWS's documented pattern for a Lambda image built from a non-AWS
# base: install `awslambdaric` and use it as the entrypoint.
#
# Phase 1: requirements.txt is empty (business deps land in phase 2, T-030) and
# app/handler.py is a 501 stub — but the OS/Tesseract layer is real from the
# start, so the packaging strategy never has to change mid-project.
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /var/task
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric
COPY app/ ./
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
