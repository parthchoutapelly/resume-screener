// src/components/ui/StatusMark.jsx
// Visual process and state indicator mapping domain states to restrained UI marks.
// Adapts React Bits StatusMark for dense ATS information hierarchy.

import { useMemo } from 'react';

const TONE_COLORS = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  info: 'var(--color-accent)',
  neutral: 'var(--color-text-secondary)',
};

export default function StatusMark({
  status,
  tone: toneOverride,
  size = 16,
  pulse: pulseOverride,
  strike = false,
  label,
  title,
  className = '',
}) {
  const normStatus = (status || '').toLowerCase().trim();

  const { resolvedTone, iconType, isPulsing, defaultLabel } = useMemo(() => {
    let t = 'neutral';
    let icon = 'dot';
    let p = false;
    let lbl = status || '';

    // Candidate domain statuses
    if (normStatus === 'scored') {
      t = 'success';
      icon = 'check';
      lbl = 'Scored';
    } else if (normStatus === 'scoring') {
      t = 'info';
      icon = 'spin';
      p = true;
      lbl = 'Scoring…';
    } else if (normStatus === 'processing') {
      t = 'info';
      icon = 'spin';
      p = true;
      lbl = 'Processing…';
    } else if (normStatus === 'awaiting_jd') {
      t = 'info';
      icon = 'clock';
      lbl = 'Awaiting JD';
    } else if (normStatus === 'awaiting_requirements' || normStatus === 'needs review') {
      t = 'warning';
      icon = 'warning';
      lbl = 'Needs Review';
    } else if (normStatus === 'upload_missing' || normStatus === 'stalled') {
      t = 'warning';
      icon = 'warning';
      lbl = 'Attention';
    } else if (normStatus === 'error' || normStatus === 'failed') {
      t = 'danger';
      icon = 'cross';
      lbl = 'Failed';
    } else if (normStatus === 'ready') {
      t = 'success';
      icon = 'check';
      lbl = 'Ready';
    } else if (normStatus === 'no jd') {
      t = 'neutral';
      icon = 'clock';
      lbl = 'No JD';
    } else if (normStatus === 'uploading') {
      t = 'info';
      icon = 'spin';
      p = true;
      lbl = 'Uploading';
    } else if (normStatus === 'uploaded') {
      t = 'success';
      icon = 'check';
      lbl = 'Uploaded';
    } else if (normStatus === 'queued') {
      t = 'neutral';
      icon = 'clock';
      lbl = 'Queued';
    } else if (normStatus === 'shortlisted') {
      t = 'success';
      icon = 'check';
      lbl = 'Shortlisted';
    } else if (normStatus === 'rejected') {
      t = 'danger';
      icon = 'cross';
      lbl = 'Rejected';
    }

    return {
      resolvedTone: toneOverride || t,
      iconType: icon,
      isPulsing: pulseOverride !== undefined ? pulseOverride : p,
      defaultLabel: label || lbl,
    };
  }, [normStatus, status, toneOverride, pulseOverride, label]);

  const color = TONE_COLORS[resolvedTone] || TONE_COLORS.neutral;
  const displayTitle = title || defaultLabel;

  return (
    <span
      className={`status-mark status-mark--${resolvedTone} ${isPulsing ? 'status-mark--pulsing' : ''} ${className}`}
      role="img"
      title={displayTitle}
      aria-label={displayTitle}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: label ? '6px' : '0',
        verticalAlign: 'middle',
      }}
    >
      <span
        className="status-mark__glyph"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        {iconType === 'check' && (
          <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.25" fill={`${color}18`} />
            <path d="M5.5 8.2L7.2 10L10.5 6.5" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        {iconType === 'spin' && (
          <svg
            className="status-mark__spinner"
            width={size}
            height={size}
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
            style={{ animation: 'statusMarkSpin 1s linear infinite' }}
          >
            <circle cx="8" cy="8" r="6" stroke="var(--color-border-strong)" strokeWidth="1.5" />
            <path d="M14 8a6 6 0 0 0-6-6" stroke={color} strokeWidth="1.75" strokeLinecap="round" />
          </svg>
        )}
        {iconType === 'warning' && (
          <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.25" fill={`${color}18`} />
            <line x1="8" y1="4.5" x2="8" y2="8.5" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="8" cy="11.2" r="0.75" fill={color} />
          </svg>
        )}
        {iconType === 'cross' && (
          <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.25" fill={`${color}18`} />
            <path d="M6 6l4 4M10 6l-4 4" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        )}
        {iconType === 'clock' && (
          <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" stroke={color} strokeWidth="1.25" fill={`${color}14`} />
            <path d="M8 5v3.5l2.5 1.5" stroke={color} strokeWidth="1.25" strokeLinecap="round" />
          </svg>
        )}
        {iconType === 'dot' && (
          <span
            style={{
              width: `${Math.max(6, size * 0.45)}px`,
              height: `${Math.max(6, size * 0.45)}px`,
              borderRadius: '50%',
              backgroundColor: color,
              display: 'inline-block',
            }}
          />
        )}
      </span>
      {label && (
        <span
          className="status-mark__label"
          style={{
            textDecoration: strike ? 'line-through' : 'none',
            color: 'inherit',
          }}
        >
          {label}
        </span>
      )}
    </span>
  );
}
