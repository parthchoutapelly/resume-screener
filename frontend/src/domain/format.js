// src/domain/format.js
// Pure formatting utilities. No side effects.

/** Format a match score to 1 decimal place. */
export function formatScore(score) {
  if (score == null) return '\u2014';
  return Number(score).toFixed(1);
}

/** Format years of experience. */
export function formatYears(years, estimated = false) {
  if (years == null) return 'Unknown';
  const n = Number(years).toFixed(1);
  return estimated ? `\u2248\u00a0${n}\u00a0yrs` : `${n}\u00a0yrs`;
}

/** Format a file size in bytes to a human-readable string. */
export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes}\u00a0B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}\u00a0KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}\u00a0MB`;
}

/** Format an ISO timestamp to a locale date string with optional relative time for recent dates. */
export function formatDate(iso) {
  if (!iso) return '\u2014';
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff >= 0 && diff < 24 * 60 * 60 * 1000) {
    // Less than 24 h ago — show relative time
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}\u00a0min ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}\u00a0hr ago`;
  }
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/** Sanitise a string for use as a CSV cell (formula injection protection). */
export function csvEscape(value) {
  const s = String(value ?? '');
  // Prefix cells starting with =, +, -, @ with a single quote
  if (/^[=+\-@]/.test(s)) return "'" + s;
  // Wrap in double quotes if contains comma, newline, or double-quote
  if (/[,"\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

/** Return an accessible, non-empty title for a job posting. */
export function getJobAccessibleTitle(job) {
  if (job?.job_title && typeof job.job_title === 'string' && job.job_title.trim().length > 0) {
    return job.job_title.trim();
  }
  return job?.job_id || 'Untitled Job';
}
