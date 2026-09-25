// src/auth/cognito.js
// Amplify v6 Auth-only configuration. Raw ID token in Authorization header (no Bearer prefix).
import { Amplify } from 'aws-amplify';
import {
  signIn,
  confirmSignIn,
  signOut,
  fetchAuthSession,
} from 'aws-amplify/auth';
import { config } from '../config';

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
    },
  },
});

/**
 * Sign in with email + password.
 * Returns { done: true } on success, or { done: false, needsNewPassword: true }
 * when the user was admin-created and must set a new password.
 */
export async function login(email, password) {
  const { isSignedIn, nextStep } = await signIn({ username: email, password });
  if (isSignedIn) return { done: true };
  if (nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
    return { done: false, needsNewPassword: true };
  }
  throw new Error(`Unsupported sign-in step: ${nextStep.signInStep}`);
}

/** Complete the NEW_PASSWORD_REQUIRED challenge. */
export const completeNewPassword = (newPassword) =>
  confirmSignIn({ challengeResponse: newPassword });

/** Sign out the current user. */
export const logout = () => signOut();

/** Returns the raw ID token string, or null if not signed in. */
export async function getIdToken({ forceRefresh = false } = {}) {
  const s = await fetchAuthSession({ forceRefresh });
  return s.tokens?.idToken?.toString() ?? null;
}

/** Returns the cognito:groups array from the ID token payload. */
export async function getGroups() {
  const s = await fetchAuthSession();
  const raw = s.tokens?.idToken?.payload['cognito:groups'] ?? [];
  // The claim can arrive as a JSON-stringified array (a known Cognito quirk);
  // handle both forms.
  if (typeof raw === 'string') {
    try { return JSON.parse(raw); } catch { return [raw]; }
  }
  return Array.isArray(raw) ? raw : [raw];
}
