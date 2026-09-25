// src/config.js
// Reads all required VITE_ env vars and throws at startup if any are missing.
// This means the app never runs half-configured — per 04-frontend-dashboard.md §2.

const required = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
  userPoolId: import.meta.env.VITE_USER_POOL_ID,
  userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
  region: import.meta.env.VITE_REGION,
};

for (const [key, value] of Object.entries(required)) {
  if (!value) {
    throw new Error(
      `Missing required env var for config key "${key}". ` +
      `Run scripts/gen-frontend-env.sh dev to regenerate .env.dev from stack outputs.`
    );
  }
}

export const config = {
  ...required,
  featureResumeView: import.meta.env.VITE_FEATURE_RESUME_VIEW === 'true',
  useMocks: import.meta.env.VITE_USE_MOCKS === 'true',
};
