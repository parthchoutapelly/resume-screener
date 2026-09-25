#!/usr/bin/env bash
# scripts/deploy-frontend.sh <env>
# Builds the React SPA and deploys it to the CloudFront-backed S3 web bucket.
# Prerequisites: AWS CLI, Node 18+, stack deployed with WebBucketName + DistributionId outputs.
set -euo pipefail

ENV="${1:?Usage: deploy-frontend.sh <env>}"
STACK="resume-screener-${ENV}"

out() {
  aws cloudformation describe-stacks \
    --stack-name "${STACK}" \
    --query "Stacks[0].Outputs[?OutputKey=='${1}'].OutputValue" \
    --output text
}

WEB="$(out WebBucketName)"
DIST="$(out DistributionId)"

echo "==> Generating .env.${ENV} from stack outputs..."
bash "$(dirname "$0")/gen-frontend-env.sh" "${ENV}"

echo "==> Building frontend (mode=${ENV})..."
(cd frontend && npm ci && npm run build -- --mode "${ENV}")

echo "==> Syncing assets to s3://${WEB}/ ..."
# Long-cache everything except index.html (hashed filenames)
aws s3 sync frontend/dist/ "s3://${WEB}/" \
  --delete \
  --exclude "index.html" \
  --cache-control "public,max-age=31536000,immutable"

# index.html must always be fresh
aws s3 cp frontend/dist/index.html "s3://${WEB}/index.html" \
  --cache-control "no-cache"

echo "==> Invalidating CloudFront /index.html ..."
aws cloudfront create-invalidation \
  --distribution-id "${DIST}" \
  --paths "/index.html" > /dev/null

DOMAIN="$(out DistributionDomain)"
echo ""
echo "Deployed: https://${DOMAIN}"
