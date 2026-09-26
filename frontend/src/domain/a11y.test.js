/**
 * Accessibility (a11y) structural, contrast, and link-name regression test.
 *
 * Phase 5 T-107 / WCAG 2.1 AA: verifies contract requirements across
 * domain status presentations, badges, interactive elements, design tokens,
 * and accessible naming fallbacks.
 */

import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { DISPLAY, ERROR_COPY, resolveLabel } from './status';
import { getJobAccessibleTitle } from './format';

function getLuminance(hex) {
  const cleanHex = hex.trim().replace('#', '');
  const r = parseInt(cleanHex.slice(0, 2), 16) / 255;
  const g = parseInt(cleanHex.slice(2, 4), 16) / 255;
  const b = parseInt(cleanHex.slice(4, 6), 16) / 255;
  const a = [r, g, b].map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
  return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
}

function getContrastRatio(hex1, hex2) {
  const l1 = getLuminance(hex1);
  const l2 = getLuminance(hex2);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

describe('accessibility contract (WCAG 2.1 AA)', () => {
  it('all status indicators and error codes resolve to a readable label or score group', () => {
    for (const [status, cfg] of Object.entries(DISPLAY)) {
      if (status === 'scored') {
        expect(cfg.group).toBe('scored');
      } else if (status === 'error') {
        for (const code of Object.keys(ERROR_COPY)) {
          const label = resolveLabel('error', code);
          expect(label, `Error code "${code}" must have human-readable text`).toBeTruthy();
          expect(typeof label).toBe('string');
        }
      } else {
        expect(cfg.label, `Status "${status}" must have a readable text label`).toBeTruthy();
        expect(typeof cfg.label).toBe('string');
      }
    }
  });

  it('all status indicators have an accessible tone category for contrast mapping', () => {
    const ALLOWED_TONES = new Set(['neutral', 'info', 'warning', 'danger', 'success']);
    for (const [status, cfg] of Object.entries(DISPLAY)) {
      expect(
        ALLOWED_TONES.has(cfg.tone),
        `Status "${status}" tone "${cfg.tone}" must be one of allowed WCAG-compliant badge tones`,
      ).toBe(true);
    }
  });

  it('status indicators requiring active attention have explicit spinners/indicators', () => {
    expect(DISPLAY.processing.spinner).toBe(true);
    expect(DISPLAY.scoring.spinner).toBe(true);
    expect(DISPLAY.scored.spinner).toBe(false);
    expect(DISPLAY.error.spinner).toBe(false);
    expect(DISPLAY.upload_missing.spinner).toBe(false);
  });

  it('muted text token satisfies WCAG 2.1 AA minimum contrast requirement (>= 4.5:1)', () => {
    const tokensPath = path.resolve(__dirname, '../styles/tokens.css');
    const css = fs.readFileSync(tokensPath, 'utf-8');

    const mutedMatch = css.match(/--color-text-muted:\s*(#[0-9a-fA-F]{6});/);
    const surfaceMatch = css.match(/--color-surface:\s*(#[0-9a-fA-F]{6});/);
    const bgMatch = css.match(/--color-bg:\s*(#[0-9a-fA-F]{6});/);

    expect(mutedMatch, 'Must define --color-text-muted in tokens.css').toBeTruthy();
    expect(surfaceMatch, 'Must define --color-surface in tokens.css').toBeTruthy();
    expect(bgMatch, 'Must define --color-bg in tokens.css').toBeTruthy();

    const mutedHex = mutedMatch[1];
    const surfaceHex = surfaceMatch[1];
    const bgHex = bgMatch[1];

    const contrastSurface = getContrastRatio(mutedHex, surfaceHex);
    const contrastBg = getContrastRatio(mutedHex, bgHex);

    expect(contrastSurface).toBeGreaterThanOrEqual(4.5);
    expect(contrastBg).toBeGreaterThanOrEqual(4.5);
  });

  it('job links have non-empty accessible names for jobs with or without a title', () => {
    // Case 1: Job with a valid title
    const jobWithTitle = { job_id: 'job_12345', job_title: 'Senior Backend Engineer' };
    const title1 = getJobAccessibleTitle(jobWithTitle);
    expect(title1).toBe('Senior Backend Engineer');
    expect(title1.trim().length).toBeGreaterThan(0);

    // Case 2: Job with null/empty title produces deterministic fallback to job_id
    const jobWithoutTitle = { job_id: 'job_67890', job_title: null };
    const title2 = getJobAccessibleTitle(jobWithoutTitle);
    expect(title2).toBe('job_67890');
    expect(title2.trim().length).toBeGreaterThan(0);

    // Case 3: Job with whitespace title falls back to job_id
    const jobWithWhitespace = { job_id: 'job_abcde', job_title: '   ' };
    const title3 = getJobAccessibleTitle(jobWithWhitespace);
    expect(title3).toBe('job_abcde');
    expect(title3.trim().length).toBeGreaterThan(0);
  });
});
