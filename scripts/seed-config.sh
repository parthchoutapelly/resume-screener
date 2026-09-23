#!/usr/bin/env bash
# Seeds the config table's single required row (idempotent — safe to re-run).
# "spacy_hybrid" is the only nlp_engine_mode implemented in this codebase (D-13).
# Usage: scripts/seed-config.sh <env>
set -euo pipefail

ENV_NAME="${1:?Usage: seed-config.sh <env>}"
REGION="${AWS_REGION:-ap-south-1}"

aws dynamodb put-item \
  --region "$REGION" \
  --table-name "config-${ENV_NAME}" \
  --item '{"config_key":{"S":"nlp_engine_mode"},"config_value":{"S":"spacy_hybrid"}}'

echo "Seeded config-${ENV_NAME}.nlp_engine_mode = spacy_hybrid"
