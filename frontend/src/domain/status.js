// src/domain/status.js
// The ONLY place statuses become UI copy, icons, and tones.
// Mirrors Architecture.md §7.2/§7.4 and Design.md §6.
// A unit test asserts that every enum value is mapped, so no unknown value can reach the UI.

export const DISPLAY = {
  scored: {
    group: 'scored',
    label: null,        // show the score instead
    tone: 'neutral',
    icon: null,
    spinner: false,
  },
  scoring: {
    group: 'progress',
    label: 'Scoring\u2026',
    tone: 'info',
    icon: null,
    spinner: true,
  },
  awaiting_jd: {
    group: 'progress',
    label: 'Waiting for job description',
    tone: 'info',
    icon: 'clock',
    spinner: false,
  },
  awaiting_requirements: {
    group: 'attention',
    label: 'Needs job requirements',
    tone: 'warning',
    icon: 'warning',
    spinner: false,
  },
  processing: {
    group: 'progress',
    label: 'Processing\u2026',
    tone: 'info',
    icon: null,
    spinner: true,
  },
  upload_missing: {
    group: 'attention',
    label: 'Upload not received',
    tone: 'warning',
    icon: 'cloud-off',
    spinner: false,
  },
  stalled: {
    group: 'attention',
    label: 'Taking longer than expected',
    tone: 'warning',
    icon: 'warning',
    spinner: false,
  },
  error: {
    group: 'attention',
    label: null,  // resolved from ERROR_COPY using error_code
    tone: 'danger',
    icon: 'error',
    spinner: false,
  },
};

export const ERROR_COPY = {
  unsupported_format:
    'File type isn\u2019t supported. Use PDF, DOCX, PNG, JPG or TIFF.',
  file_too_large: 'File is larger than 10\u00a0MB.',
  too_many_pages: 'Resume is longer than 10\u00a0pages.',
  unreadable_document:
    'We couldn\u2019t read any text from this file. It may be blank, password-protected, or too low quality.',
  processing_failed:
    'Something went wrong while processing this file. Try re-uploading.',
  scoring_failed:
    'Scoring failed. An administrator has been alerted.',
};

/** States that keep the polling loop alive. */
export const IN_PROGRESS = new Set(['processing', 'scoring', 'awaiting_jd']);

/**
 * Resolve a candidate's display_status to its DISPLAY entry.
 * Unknown statuses log a console warning and return a fallback.
 */
export function resolveStatus(status) {
  if (DISPLAY[status]) return DISPLAY[status];
  console.warn(`[status] Unknown display_status: "${status}"`);
  return {
    group: 'attention',
    label: 'Unknown status',
    tone: 'warning',
    icon: 'warning',
    spinner: false,
  };
}

/** Resolve the user-facing label for a given display_status + error_code pair. */
export function resolveLabel(status, error_code) {
  const entry = resolveStatus(status);
  if (status === 'error') {
    return ERROR_COPY[error_code] ?? 'An error occurred. Try re-uploading.';
  }
  return entry.label;
}
