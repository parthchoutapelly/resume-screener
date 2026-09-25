// src/api/client.js
// JSON API client. Auth header uses the raw ID token (no "Bearer " prefix — per 03 §5).
// On 401: one silent token refresh + retry, then redirect to /login.
import { config } from '../config';
import { getIdToken, logout } from '../auth/cognito';

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, { method = 'GET', body, retried = false } = {}) {
  const token = await getIdToken({ forceRefresh: retried });

  // On a second 401 (refresh already happened), sign out and redirect.
  if (!token && retried) {
    await logout();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}&reason=expired`);
    return;
  }

  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: token } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // One silent refresh on 401
  if (res.status === 401 && !retried) {
    return request(path, { method, body, retried: true });
  }

  // Second 401 → redirect
  if (res.status === 401 && retried) {
    await logout();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}&reason=expired`);
    return;
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null);

  if (!res.ok) {
    const e = data?.error ?? {};
    throw new ApiError(
      res.status,
      e.code ?? `HTTP_${res.status}`,
      e.message ?? 'Request failed',
      e.details
    );
  }

  return data;
}

export const api = {
  // Jobs
  createJob: (payload) =>
    request('/jobs', { method: 'POST', body: payload }),
  listJobs: (nextToken) =>
    request('/jobs' + (nextToken ? `?next_token=${encodeURIComponent(nextToken)}` : '')),
  getJob: (jobId) =>
    request(`/jobs/${jobId}`),
  updateJob: (jobId, patch) =>
    request(`/jobs/${jobId}`, { method: 'PATCH', body: patch }),

  // Resumes
  addResumes: (jobId, filenames) =>
    request(`/jobs/${jobId}/resumes`, { method: 'POST', body: { resume_filenames: filenames } }),

  // Candidates
  listCandidates: (jobId) =>
    request(`/jobs/${jobId}/candidates`),
  decide: (jobId, candidateId, decision) =>
    request(`/jobs/${jobId}/candidates/${candidateId}/decision`, {
      method: 'POST',
      body: { decision },
    }),
  resumeUrl: (jobId, candidateId) =>
    request(`/jobs/${jobId}/candidates/${candidateId}/resume-url`),

  // Export
  exportCsv: (jobId) =>
    request(`/jobs/${jobId}/export`),

  // Admin
  listFailures: ({ jobId, nextToken } = {}) =>
    request(
      '/failed-jobs?' +
        new URLSearchParams({
          ...(jobId ? { job_id: jobId } : {}),
          ...(nextToken ? { next_token: nextToken } : {}),
        })
    ),
};
