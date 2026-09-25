// src/pages/FailedJobsPage.jsx
// Admin workbench view showing pipeline failures.
// raw_payload is strictly rendered as text inside <pre>, never as HTML (R-SEC-08).
import { useState, useEffect, useCallback } from 'react';
import StatusMark from '../components/ui/StatusMark';
import Tooltip from '../components/ui/Tooltip';
import { AnimatedRow } from '../components/ui/AnimatedList';
import { config } from '../config';
import { formatDate } from '../domain/format';

const api = config.useMocks
  ? (await import('../api/mock.js')).mockApi
  : (await import('../api/client.js')).api;

function FailureRow({ failure }) {
  const [expanded, setExpanded] = useState(false);
  const { failure_id, job_id, stage, terminal, error_code, original_filename, raw_payload, created_at } = failure;

  return (
    <>
      <AnimatedRow>
        <td>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text)' }}>
              {job_id}
            </span>
            {original_filename && (
              <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                {original_filename}
              </span>
            )}
          </div>
        </td>
        <td>
          <Tooltip content={`Processing failure occurred during ${stage} pipeline execution`}>
            <span className="badge badge--warning" style={{ textTransform: 'uppercase' }}>
              {stage}
            </span>
          </Tooltip>
        </td>
        <td>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Tooltip content={terminal ? 'Terminal failure — cannot be automatically recovered' : 'Transient failure — pipeline paused or retried'}>
              <StatusMark
                status={terminal ? 'failed' : 'stalled'}
                label={terminal ? 'TERMINAL' : 'TRANSIENT'}
              />
            </Tooltip>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text)' }}>
              {error_code ?? 'UNKNOWN_ERROR'}
            </span>
          </div>
        </td>
        <td>
          <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
            {formatDate(created_at)}
          </span>
        </td>
        <td style={{ textAlign: 'right' }}>
          <Tooltip content={expanded ? 'Hide JSON payload trace' : 'Inspect JSON trace and system error payload'}>
            <button
              id={`expand-failure-${failure_id}`}
              className="btn btn--ghost btn--sm"
              aria-expanded={expanded}
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? 'Hide Payload ▴' : 'View Payload ▾'}
            </button>
          </Tooltip>
        </td>
      </AnimatedRow>
      {expanded && (
        <tr>
          <td colSpan={5} style={{ padding: 'var(--space-3) var(--space-4)', background: 'var(--color-surface-raised)', borderBottom: '1px solid var(--color-border)' }}>
            <span className="section-kicker" style={{ marginBottom: '4px' }}>RAW PAYLOAD TRACE</span>
            {/* SECURITY: raw_payload rendered as plain text only — never innerHTML */}
            <pre className="mono" style={{ fontSize: '11px', padding: 'var(--space-3)', background: 'var(--color-bg)', border: '1px solid var(--color-border)', borderRadius: 'var(--border-radius-xs)', overflowX: 'auto', color: 'var(--color-text-secondary)', maxHeight: 240 }}>
              {String(raw_payload ?? '')}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

export default function FailedJobsPage() {
  const [failures, setFailures] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [jobFilter, setJobFilter] = useState('');
  const [terminalOnly, setTerminalOnly] = useState(false);

  const fetchFailures = useCallback(async (token = null, append = false) => {
    try {
      const data = await api.listFailures({ nextToken: token });
      const items = data?.failures ?? [];
      setFailures((prev) => (append ? [...prev, ...items] : items));
      setNextToken(data?.next_token ?? null);
    } catch {
      setError('Failed to load failures. Please refresh.');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    fetchFailures();
  }, [fetchFailures]);

  const displayed = failures
    .filter((f) => !jobFilter || (f.job_id || '').includes(jobFilter.trim()))
    .filter((f) => !terminalOnly || f.terminal);

  if (loading) {
    return (
      <div className="loading-page">
        <div className="spinner spinner--lg" aria-label="Loading failures" />
        <span>Loading system failures…</span>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <span className="page-header__kicker">SYSTEM AUDIT</span>
          <h1 className="page-header__title">FAILED JOBS</h1>
          <p className="page-header__subtitle">
            Jobs requiring attention across ingestion, extraction, and scoring stages.
          </p>
        </div>
      </div>

      {/* Filter row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
        <input
          id="failure-job-filter"
          type="text"
          className="input"
          style={{ maxWidth: 300, fontSize: '12px', padding: '6px 10px' }}
          placeholder="Filter by Job ID…"
          value={jobFilter}
          onChange={(e) => setJobFilter(e.target.value)}
          aria-label="Filter by job ID"
        />

        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
          <input
            id="terminal-only-toggle"
            type="checkbox"
            checked={terminalOnly}
            onChange={(e) => setTerminalOnly(e.target.checked)}
          />
          Terminal failures only
        </label>
      </div>

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      {displayed.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state__icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <h2 className="empty-state__title">NO FAILED JOBS</h2>
          <p className="empty-state__description">
            {jobFilter || terminalOnly
              ? 'No pipeline failures match your active filter.'
              : 'All ingestion, extraction, and scoring pipelines are operating without logged failures.'}
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table" aria-label="Ingestion and scoring failures">
            <thead>
              <tr>
                <th scope="col" style={{ width: '25%' }}>Job</th>
                <th scope="col">Failure Stage</th>
                <th scope="col">Reason & Severity</th>
                <th scope="col">Created</th>
                <th scope="col" style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((f) => (
                <FailureRow key={f.failure_id} failure={f} />
              ))}
            </tbody>
          </table>

          {nextToken && (
            <div className="load-more">
              <button
                id="load-more-failures-btn"
                className="btn btn--secondary btn--sm"
                onClick={() => {
                  setLoadingMore(true);
                  fetchFailures(nextToken, true);
                }}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load more failures'}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
