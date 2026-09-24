# Base image decision: D-34 (docs/Memory.md, docs/infra/README.md "D-34 outcome").
# The Lambda-official AL2023 base has no `tesseract` package in its repos at
# all (confirmed by direct test, not just a build failure) — Debian's does.
# This follows AWS's documented pattern for a Lambda image built from a
# non-AWS base: install `awslambdaric` and use it as the entrypoint.
#
# Docker context is `./backend` (not this directory) so the image can COPY
# rs_common directly — container-image functions can't use Lambda layers
# (docs/02-ingestion-pipeline.md §6.1). Paths below are relative to that
# context.
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /var/task
COPY ingestion/extraction/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric
COPY layers/common_layer/python/rs_common ./rs_common
COPY ingestion/extraction/app/ ./
# No data/ copy here: extraction never imports rs_common.normalization (it has
# no entity-level responsibility — Architecture.md §2); only nlpProcessing
# reads the dictionaries.
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
