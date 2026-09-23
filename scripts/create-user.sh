#!/usr/bin/env bash
# Creates a Cognito user and (optionally) adds them to a group.
# Usage: scripts/create-user.sh <env> <email> <Recruiter|Admin|none> [temp-password]
#
# The user is created with AllowAdminCreateUserOnly (self sign-up is disabled,
# R-AUTH-02), so this is the only way to provision an account. On first login
# the user is challenged to set a permanent password (NEW_PASSWORD_REQUIRED).
set -euo pipefail

ENV_NAME="${1:?Usage: create-user.sh <env> <email> <Recruiter|Admin|none> [temp-password]}"
EMAIL="${2:?Usage: create-user.sh <env> <email> <Recruiter|Admin|none> [temp-password]}"
GROUP="${3:?Usage: create-user.sh <env> <email> <Recruiter|Admin|none> [temp-password]}"
TEMP_PASSWORD="${4:-TempPass1234}"  # meets the pool's password policy; changed on first login
REGION="${AWS_REGION:-ap-south-1}"
STACK_NAME="resume-screener-${ENV_NAME}"

USER_POOL_ID=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)

if [[ -z "$USER_POOL_ID" || "$USER_POOL_ID" == "None" ]]; then
  echo "Could not resolve UserPoolId from stack ${STACK_NAME} outputs." >&2
  exit 1
fi

aws cognito-idp admin-create-user \
  --region "$REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --temporary-password "$TEMP_PASSWORD" \
  --message-action SUPPRESS

if [[ "$GROUP" == "Recruiter" || "$GROUP" == "Admin" ]]; then
  aws cognito-idp admin-add-user-to-group \
    --region "$REGION" \
    --user-pool-id "$USER_POOL_ID" \
    --username "$EMAIL" \
    --group-name "$GROUP"
  echo "Created ${EMAIL} in group ${GROUP} (temp password: ${TEMP_PASSWORD})"
else
  echo "Created ${EMAIL} with NO group — for 403 testing (temp password: ${TEMP_PASSWORD})"
fi
