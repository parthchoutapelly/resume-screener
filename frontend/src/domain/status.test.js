/**
 * Status-mapping completeness test.
 *
 * Phase 5 T-101 gate: every backend display_status value emitted by
 * rs_common/status.py must have a corresponding entry in the frontend
 * DISPLAY map (src/domain/status.js). If a new status is added to the
 * backend without updating the frontend, this test fails — preventing
 * silent "Unknown status" fallbacks from reaching recruiters.
 *
 * The canonical list of statuses is taken from Architecture.md §7.2 and
 * mirrored in the backend's rs_common/status.py ORDER constant.
 */

import { describe, it, expect } from 'vitest';
import { DISPLAY, ERROR_COPY, IN_PROGRESS, resolveLabel, resolveStatus } from '../domain/status';

// ---------------------------------------------------------------------------
// These must stay in sync with rs_common/status.py ORDER (§7.2).
// ---------------------------------------------------------------------------
const BACKEND_STATUSES = [
  'scored',
  'scoring',
  'awaiting_jd',
  'awaiting_requirements',
  'processing',
  'stalled',
  'upload_missing',
  'error',
];

// Error codes from rs_common/status.py and the API contract (§7.3).
const BACKEND_ERROR_CODES = [
  'unsupported_format',
  'file_too_large',
  'too_many_pages',
  'unreadable_document',
  'processing_failed',
  'scoring_failed',
];

describe('status-mapping completeness', () => {
  it('DISPLAY has an entry for every backend display_status', () => {
    const mapped = Object.keys(DISPLAY);
    const missing = BACKEND_STATUSES.filter((s) => !mapped.includes(s));
    expect(missing, `Missing from DISPLAY: ${missing.join(', ')}`).toEqual([]);
  });

  it('ERROR_COPY has an entry for every backend error_code', () => {
    const mapped = Object.keys(ERROR_COPY);
    const missing = BACKEND_ERROR_CODES.filter((c) => !mapped.includes(c));
    expect(missing, `Missing from ERROR_COPY: ${missing.join(', ')}`).toEqual([]);
  });

  it('no extra statuses in DISPLAY that the backend does not emit', () => {
    const extra = Object.keys(DISPLAY).filter((s) => !BACKEND_STATUSES.includes(s));
    expect(extra, `Extra in DISPLAY (backend never emits): ${extra.join(', ')}`).toEqual([]);
  });

  it('IN_PROGRESS only contains statuses that are in DISPLAY', () => {
    for (const s of IN_PROGRESS) {
      expect(DISPLAY[s], `IN_PROGRESS contains "${s}" which is not in DISPLAY`).toBeDefined();
    }
  });

  it('every DISPLAY entry has required shape keys', () => {
    const REQUIRED_KEYS = ['group', 'label', 'tone', 'spinner'];
    for (const [status, entry] of Object.entries(DISPLAY)) {
      for (const key of REQUIRED_KEYS) {
        expect(key in entry, `DISPLAY["${status}"] missing key "${key}"`).toBe(true);
      }
    }
  });

  it('tone values are one of the allowed set', () => {
    const VALID_TONES = new Set(['neutral', 'info', 'warning', 'danger', 'success']);
    for (const [status, entry] of Object.entries(DISPLAY)) {
      expect(
        VALID_TONES.has(entry.tone),
        `DISPLAY["${status}"].tone is "${entry.tone}" — not in allowed set`,
      ).toBe(true);
    }
  });

  it('resolveStatus returns a valid entry for every known status', () => {
    for (const s of BACKEND_STATUSES) {
      const entry = resolveStatus(s);
      expect(entry).toBeDefined();
      expect(entry.tone).toBeTruthy();
    }
  });

  it('resolveStatus returns fallback (not throws) for unknown status', () => {
    const entry = resolveStatus('__unknown_status__');
    expect(entry).toBeDefined();
    expect(entry.tone).toBe('warning');
  });

  it('resolveLabel returns a non-empty string for every status × error_code combination', () => {
    // For non-error statuses the label comes from DISPLAY
    for (const s of BACKEND_STATUSES.filter((s) => s !== 'error')) {
      const label = resolveLabel(s, null);
      // 'scored' label is intentionally null (score number shown instead)
      if (s === 'scored') {
        expect(label).toBeNull();
      } else {
        expect(typeof label).toBe('string');
        expect(label.length).toBeGreaterThan(0);
      }
    }

    // For error status every known error_code must resolve
    for (const code of BACKEND_ERROR_CODES) {
      const label = resolveLabel('error', code);
      expect(typeof label).toBe('string');
      expect(label.length).toBeGreaterThan(0);
    }

    // Unknown error_code falls back to a generic message (not throws)
    const fallback = resolveLabel('error', '__unknown_code__');
    expect(typeof fallback).toBe('string');
    expect(fallback.length).toBeGreaterThan(0);
  });
});
