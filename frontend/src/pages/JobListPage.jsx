// src/pages/JobListPage.jsx
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import CountUp from '../components/ui/CountUp';
import StatusMark from '../components/ui/StatusMark';
import Tooltip from '../components/ui/Tooltip';
import { AnimatedRow } from '../components/ui/AnimatedList';
import { config } from '../config';

const api = config.useMocks
  ? (await import('../api/mock.js')).mockApi
  : (await import('../api/client.js')).api;

// Restrained status badge
function JobStatusBadge({ job }) {
  const { parse_status, blocking_reason, jd_source, scorable } = job;

  if (parse_status === 'error') {
    return <StatusMark status="failed" label="FAILED" />;
  }
  if (blocking_reason === 'no_required_skills') {
    return <StatusMark status="awaiting_requirements" label="NEEDS REVIEW" />;
  }
  if (parse_status === 'parsing' || parse_status === 'pending') {
    return <StatusMark status="processing" label="PROCESSING" />;
  }
  if (scorable || parse_status === 'success') {
    return <StatusMark status="ready" label="READY" />;
  }
  if (jd_source === 'none') {
    return <StatusMark status="no jd" label="NO JD" />;
  }
  return <StatusMark status="ready" label="READY" />;
}

export default function JobListPage() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchJobs = useCallback(async (token = null, append = false) => {
    try {
      const data = await api.listJobs(token);
      const incomingJobs = data?.jobs || [];
      setJobs((prev) => (append ? [...prev, ...incomingJobs] : incomingJobs));
      setNextToken(data?.next_token || null);
    } catch {
      setError('Failed to load jobs. Please refresh.');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleLoadMore = () => {
    setLoadingMore(true);
    fetchJobs(nextToken, true);
  };

  // Real metrics calculated from live API data
  const metrics = useMemo(() => {
    const total = jobs.length;
    let ready = 0;
    let processing = 0;
    let attention = 0;

    for (const j of jobs) {
      if (j.parse_status === 'error' || j.blocking_reason === 'no_required_skills') {
        attention++;
      } else if (j.parse_status === 'parsing' || j.parse_status === 'pending') {
        processing++;
      } else if (j.scorable || j.parse_status === 'success' || j.jd_source === 'none') {
        ready++;
      }
    }
    return { total, ready, processing, attention };
  }, [jobs]);

  // Filtered jobs by search query
  const filteredJobs = useMemo(() => {
    if (!searchQuery.trim()) return jobs;
    const q = searchQuery.toLowerCase();
    return jobs.filter(
      (j) =>
        (j.job_title || '').toLowerCase().includes(q) ||
        (j.job_id || '').toLowerCase().includes(q)
    );
  }, [jobs, searchQuery]);

  if (loading) {
    return (
      <div className="loading-page">
        <div className="spinner spinner--lg" aria-label="Loading jobs" />
        <span>Loading talent pipeline…</span>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <span className="page-header__kicker">TALENT PIPELINE</span>
          <h1 className="page-header__title">Your active hiring workspace</h1>
          <p className="page-header__subtitle">
            Manage requisition postings, candidate ingest queues, and scoring criteria.
          </p>
        </div>
        <div className="page-header__actions">
          <Tooltip content="Create new job posting and configure screening criteria">
            <Link to="/jobs/new" className="btn btn--primary" id="create-job-btn">
              + Create Job
            </Link>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      {/* Real metrics strip */}
      <div className="metrics-strip">
        <div className="metric-card">
          <span className="metric-card__label">Active Jobs</span>
          <span className="metric-card__value"><CountUp value={metrics.total} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Ready for Screening</span>
          <span className="metric-card__value metric-card__value--success"><CountUp value={metrics.ready} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Processing JD</span>
          <span className="metric-card__value metric-card__value--accent"><CountUp value={metrics.processing} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Needs Attention</span>
          <span className="metric-card__value metric-card__value--warning"><CountUp value={metrics.attention} /></span>
        </div>
      </div>

      {/* Main section header with search */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
        <div className="section-kicker" style={{ margin: 0 }}>
          <span>JOB POSTINGS</span>
          <span className="section-kicker__count">{filteredJobs.length}</span>
        </div>
        {jobs.length > 0 && (
          <input
            id="jobs-search-input"
            type="search"
            className="input"
            style={{ width: 220, padding: '4px 8px', fontSize: '12px' }}
            placeholder="Search jobs by title or ID…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search jobs"
          />
        )}
      </div>

      {jobs.length === 0 && !error ? (
        <div className="empty-state">
          <div className="empty-state__icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <line x1="7" y1="8" x2="17" y2="8" />
              <line x1="7" y1="12" x2="17" y2="12" />
              <line x1="7" y1="16" x2="12" y2="16" />
            </svg>
          </div>
          <h2 className="empty-state__title">NO JOB POSTINGS</h2>
          <p className="empty-state__description">
            Create your first job to begin screening candidates.
          </p>
          <Link to="/jobs/new" className="btn btn--primary">
            + Create Job
          </Link>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table" aria-label="Job postings table">
            <thead>
              <tr>
                <th scope="col" style={{ width: '40%' }}>Job Title</th>
                <th scope="col">Status</th>
                <th scope="col">JD Source</th>
                <th scope="col">Created</th>
                {isAdmin && <th scope="col">Owner</th>}
                <th scope="col" style={{ textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job, idx) => (
                <AnimatedRow
                  key={job.job_id}
                  index={idx}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/jobs/${job.job_id}`)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') navigate(`/jobs/${job.job_id}`);
                  }}
                  aria-label={`View job: ${job.job_title}`}
                >
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <Link
                        to={`/jobs/${job.job_id}`}
                        onClick={(e) => e.stopPropagation()}
                        style={{ color: 'var(--color-text)', fontWeight: 600, fontSize: '13px' }}
                      >
                        {job.job_title}
                      </Link>
                      <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                        {job.job_id}
                      </span>
                    </div>
                  </td>
                  <td>
                    <JobStatusBadge job={job} />
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                      {job.jd_source || 'none'}
                    </span>
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                      {job.created_at
                        ? new Date(job.created_at).toLocaleDateString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                          })
                        : '—'}
                    </span>
                  </td>
                  {isAdmin && (
                    <td>
                      <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                        {job.recruiter_id ? job.recruiter_id.slice(0, 10) + '…' : '—'}
                      </span>
                    </td>
                  )}
                  <td style={{ textAlign: 'right' }}>
                    <Tooltip content="Open candidate screening pipeline">
                      <span className="table-action-link">
                        Open Pipeline →
                      </span>
                    </Tooltip>
                  </td>
                </AnimatedRow>
              ))}
            </tbody>
          </table>

          {nextToken && (
            <div className="load-more">
              <button
                id="load-more-jobs-btn"
                className="btn btn--secondary btn--sm"
                onClick={handleLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load more jobs'}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
