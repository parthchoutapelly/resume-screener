// src/pages/JobDetailPage.jsx
// Main recruiter workbench: Job header + metrics strip + screening requirements + candidate pipeline table.
// Polls every 5s while any candidate is in progress.
import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useToast } from '../context/ToastContext';
import { usePolling } from '../hooks/usePolling';
import { DISPLAY, IN_PROGRESS, resolveLabel } from '../domain/status';
import { formatScore, formatYears, formatDate } from '../domain/format';
import ConfirmDialog from '../components/layout/ConfirmDialog';
import RequirementsDrawer from '../components/job/RequirementsDrawer';
import AddResumesModal from '../components/job/AddResumesModal';
import CountUp from '../components/ui/CountUp';
import StatusMark from '../components/ui/StatusMark';
import Tooltip from '../components/ui/Tooltip';
import SpotlightCard from '../components/ui/SpotlightCard';
import { AnimatedRow } from '../components/ui/AnimatedList';
import LatticeLoader from '../components/ui/LatticeLoader';
import { config } from '../config';

const api = config.useMocks
  ? (await import('../api/mock.js')).mockApi
  : (await import('../api/client.js')).api;

// --- Notification tag ---
function NotificationChip({ status }) {
  if (!status) return null;
  const map = {
    sent: { cls: 'success', label: 'Email sent' },
    skipped_no_email: { cls: 'neutral', label: 'No email found' },
    failed: { cls: 'danger', label: 'Email failed' },
    unknown: { cls: 'warning', label: 'Email unknown' },
  };
  const entry = map[status];
  if (!entry) return null;
  return (
    <span className={`badge badge--${entry.cls}`} style={{ fontSize: '9px', padding: '1px 5px' }}>
      {entry.label}
    </span>
  );
}

// --- Status cell ---
function StatusCell({ candidate }) {
  const { display_status, error_code } = candidate;
  const entry = DISPLAY[display_status] ?? { group: 'attention', label: 'Unknown status', tone: 'warning', spinner: false };
  const label = display_status === 'error' ? resolveLabel(display_status, error_code) : entry.label;

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <StatusMark status={display_status} tone={entry.tone} />
      <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
        {label}
      </span>
    </div>
  );
}

// --- Prominent Score display cell ---
function ScoreCell({ candidate }) {
  const { display_status, match_score, shortlist_candidate } = candidate;
  if (display_status !== 'scored') return <StatusCell candidate={candidate} />;
  const score = Number(match_score ?? 0);
  const recommended = shortlist_candidate;

  return (
    <Tooltip content={recommended ? 'Meets or exceeds shortlist threshold' : `Match score: ${formatScore(score)}`}>
      <div
        className={`score-display ${
          recommended
            ? 'score-display--recommended'
            : score >= 70
            ? 'score-display--high'
            : score >= 50
            ? 'score-display--mid'
            : 'score-display--low'
        }`}
      >
        <span className="score-display__number">
          <CountUp value={score} decimals={score % 1 !== 0 ? 1 : 0} suffix="%" />
        </span>
        <span className="score-display__label">{recommended ? 'RECOMMENDED' : 'MATCH'}</span>
      </div>
    </Tooltip>
  );
}

// --- Score breakdown when expanded ---
function ScoreBreakdown({ candidate }) {
  const { addToast } = useToast();
  const {
    skills_score,
    title_score,
    experience_score,
    matched_skills = [],
    missing_skills = [],
    title_match_type,
    title_match_held,
    title_match_required,
    total_experience_years,
    experience_estimated,
    experience_basis,
    file_type,
    ocr_pages,
    page_count,
    employers = [],
  } = candidate;

  const subScores = [
    { label: 'Skills Match', score: skills_score, weight: 50 },
    { label: 'Title Relevance', score: title_score, weight: 30 },
    { label: 'Experience Depth', score: experience_score, weight: 20 },
  ];

  const extractionLabel = {
    pdf_native: 'Native PDF',
    pdf_scanned: `Scanned PDF — OCR (${page_count ?? '?'} pages)`,
    pdf_mixed: `Mixed PDF — OCR (${ocr_pages ?? '?'} pages)`,
    docx: 'DOCX',
    image: 'Image — OCR',
  }[file_type] ?? file_type;

  const expBasis =
    experience_basis ??
    (experience_estimated ? 'Estimated — ambiguous dates' : 'Calculated from date ranges');

  return (
    <SpotlightCard
      style={{
        padding: 'var(--space-4) var(--space-5)',
        background: 'var(--color-surface-raised)',
        borderBottom: '1px solid var(--color-border)',
        borderRadius: 0,
      }}
    >
      {/* Subscores bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
        {subScores.map(({ label, score, weight }) => (
          <div key={label} style={{ background: 'var(--color-surface)', padding: 'var(--space-2) var(--space-3)', border: '1px solid var(--color-border)', borderRadius: 'var(--border-radius-xs)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
              <span style={{ color: 'var(--color-text-secondary)', textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}>{label} ({weight}%)</span>
              <span className="mono" style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                {score != null ? <CountUp value={score} decimals={score % 1 !== 0 ? 1 : 0} suffix="%" /> : '—'}
              </span>
            </div>
            <div style={{ height: '3px', background: 'var(--color-border)', borderRadius: '1px', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.min(score ?? 0, 100)}%`, background: 'var(--color-accent)' }} />
            </div>
          </div>
        ))}
      </div>

      {/* Detailed skills & history */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-4)' }}>
        <div>
          <span className="section-kicker" style={{ marginBottom: '6px' }}>SKILLS EVALUATION</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {matched_skills.map((s) => (
              <span key={s} className="chip chip--matched">✓ {s}</span>
            ))}
            {missing_skills.map((s) => (
              <span key={s} className="chip chip--missing">✗ {s}</span>
            ))}
            {matched_skills.length === 0 && missing_skills.length === 0 && (
              <span style={{ color: 'var(--color-text-secondary)', fontSize: '12px' }}>No specific skills extracted</span>
            )}
          </div>
        </div>

        <div>
          <span className="section-kicker" style={{ marginBottom: '6px' }}>WORK HISTORY & TITLES</span>
          {title_match_type && (
            <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>
              Title match: <strong style={{ color: 'var(--color-text)' }}>{title_match_held || 'None'}</strong> matches requirement <em>{title_match_required || 'None'}</em> ({title_match_type})
            </p>
          )}
          {employers.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '11px', color: 'var(--color-text-secondary)' }}>
              {employers.slice(0, 3).map((emp, i) => (
                <div key={i} className="mono">• {emp.title} at {emp.employer} ({emp.dates || 'dates unavailable'})</div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Experience: {formatYears(total_experience_years, experience_estimated)} ({expBasis})</p>
          )}
        </div>

        <div>
          <span className="section-kicker" style={{ marginBottom: '6px' }}>DOCUMENT EXTRACTION</span>
          <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Format: <span className="mono">{extractionLabel}</span></p>
          {config.featureResumeView && candidate.s3_key && (
            <div style={{ marginTop: 'var(--space-2)' }}>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={async () => {
                  try {
                    const { url } = await api.resumeUrl(candidate.job_id, candidate.candidate_id);
                    window.open(url, '_blank', 'noopener,noreferrer');
                  } catch {
                    addToast('Could not generate view link.');
                  }
                }}
              >
                Open original resume ↗
              </button>
            </div>
          )}
        </div>
      </div>
    </SpotlightCard>
  );
}

// --- Decision control ---
function DecisionControl({ candidate, jobId, onDecisionChange }) {
  const { addToast } = useToast();
  const [confirm, setConfirm] = useState(null);
  const [pending, setPending] = useState(false);
  const prevDecision = useRef(candidate.decision);
  prevDecision.current = candidate.decision;

  const { candidate_id, decision, display_status, name, email, notification_status } = candidate;
  const isScored = display_status === 'scored';

  const doDecide = useCallback(
    async (newDecision) => {
      onDecisionChange(candidate_id, { decision: newDecision });
      setPending(true);
      try {
        await api.decide(jobId, candidate_id, newDecision);
        if (newDecision === 'shortlisted' && notification_status !== 'sent') {
          addToast(`Shortlisted ${name || candidate_id}`);
        }
      } catch (err) {
        onDecisionChange(candidate_id, { decision: prevDecision.current });
        if (err?.status === 409) {
          addToast('This candidate is not scored yet.');
        } else {
          addToast(err?.message ?? 'Could not save decision. Please try again.');
        }
      } finally {
        setPending(false);
      }
    },
    [jobId, candidate_id, name, notification_status, onDecisionChange, addToast]
  );

  const handleShortlist = () => {
    if (notification_status === 'sent') {
      doDecide('shortlisted');
      return;
    }
    setConfirm({ decision: 'shortlisted' });
  };

  const handleConfirmShortlist = () => {
    setConfirm(null);
    doDecide('shortlisted');
  };

  return (
    <>
      <div
        role="radiogroup"
        aria-label="Recruitment decision"
        className="decision-control"
      >
        <Tooltip content="Shortlist candidate and send notification when applicable">
          <button
            type="button"
            id={`shortlist-${candidate_id}`}
            role="radio"
            aria-checked={decision === 'shortlisted'}
            className={`decision-control__option${
              decision === 'shortlisted' ? ' decision-control__option--shortlisted' : ''
            }`}
            onClick={handleShortlist}
            disabled={!isScored || pending}
            aria-label="Shortlist candidate"
          >
            Shortlist
          </button>
        </Tooltip>
        <Tooltip content="Mark candidate as rejected">
          <button
            type="button"
            id={`reject-${candidate_id}`}
            role="radio"
            aria-checked={decision === 'rejected'}
            className={`decision-control__option${
              decision === 'rejected' ? ' decision-control__option--rejected' : ''
            }`}
            onClick={() => doDecide('rejected')}
            disabled={!isScored || pending}
            aria-label="Reject candidate"
          >
            Reject
          </button>
        </Tooltip>
      </div>

      {confirm && (
        <ConfirmDialog
          title="Shortlist Candidate"
          body={
            <div>
              {email ? (
                <p>
                  An email notification will be sent to <strong>{email}</strong>.
                </p>
              ) : (
                <p>No email address was extracted from this resume. No email will be sent.</p>
              )}
              {name && (
                <p style={{ marginTop: 'var(--space-2)', color: 'var(--color-text-secondary)', fontSize: '12px' }}>
                  {name}
                </p>
              )}
            </div>
          }
          confirmLabel="Confirm shortlist"
          onConfirm={handleConfirmShortlist}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  );
}

// --- Candidate row ---
function CandidateRow({ candidate, rank, jobId, onDecisionChange }) {
  const [expanded, setExpanded] = useState(false);
  const expandId = `expand-${candidate.candidate_id}`;
  const breakdownId = `breakdown-${candidate.candidate_id}`;
  const {
    name,
    email,
    original_filename,
    skills = [],
    total_experience_years,
    experience_estimated,
    display_status,
    notification_status,
  } = candidate;

  const visibleSkills = skills.slice(0, 5);
  const extraSkills = skills.length - 5;

  return (
    <>
      <AnimatedRow index={rank ? rank - 1 : 0}>
        <td className="mono" style={{ color: 'var(--color-text-secondary)', fontSize: '11px', textAlign: 'center' }}>
          {display_status === 'scored' && rank != null ? `#${rank}` : '—'}
        </td>
        <td>
          <div style={{ fontWeight: 600, color: 'var(--color-text)', fontSize: '13px' }}>
            {name ?? <span style={{ color: 'var(--color-text-muted)' }}>Name not found</span>}
          </div>
          <div className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
            {original_filename}
          </div>
          {email && (
            <div className="mono" style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
              {email}
            </div>
          )}
        </td>
        <td style={{ minWidth: 90, textAlign: 'center' }}>
          <ScoreCell candidate={candidate} />
        </td>
        <td>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px', maxWidth: 260 }}>
            {visibleSkills.map((s) => (
              <span key={s} className="chip chip--neutral">
                {s}
              </span>
            ))}
            {extraSkills > 0 && (
              <span className="mono" style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>
                +{extraSkills}
              </span>
            )}
          </div>
        </td>
        <td className="mono" style={{ fontSize: '12px' }}>
          {total_experience_years != null ? (
            formatYears(total_experience_years, experience_estimated)
          ) : (
            <span style={{ color: 'var(--color-text-secondary)' }}>—</span>
          )}
        </td>
        <td>
          <StatusCell candidate={candidate} />
        </td>
        <td>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <DecisionControl candidate={candidate} jobId={jobId} onDecisionChange={onDecisionChange} />
            <NotificationChip status={notification_status} />
          </div>
        </td>
        <td style={{ textAlign: 'right' }}>
          <Tooltip content={expanded ? 'Collapse breakdown' : 'Inspect score breakdown and extracted skills'}>
            <button
              id={expandId}
              className="btn btn--ghost btn--sm"
              aria-expanded={expanded}
              aria-controls={breakdownId}
              onClick={() => setExpanded((e) => !e)}
              aria-label={expanded ? 'Collapse breakdown' : 'Expand breakdown'}
            >
              {expanded ? 'Hide ▴' : 'Inspect ▾'}
            </button>
          </Tooltip>
        </td>
      </AnimatedRow>
      {expanded && (
        <tr id={breakdownId}>
          <td colSpan={8} style={{ padding: 0 }}>
            <ScoreBreakdown candidate={candidate} />
          </td>
        </tr>
      )}
    </>
  );
}

// === Main JobDetailPage component ===
export default function JobDetailPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [job, setJob] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortKey, setSortKey] = useState('match_score');
  const [sortDir, setSortDir] = useState('desc');
  const [search, setSearch] = useState('');
  const [filterGroup, setFilterGroup] = useState(null);
  const [pollPaused, setPollPaused] = useState(false);
  const [pollError, setPollError] = useState(false);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [addResumesModalOpen, setAddResumesModalOpen] = useState(false);

  const handleRequirementsSaved = (updatedJob) => {
    setJob(updatedJob);
    setEditDrawerOpen(false);
    const count = updatedJob?.rescore_enqueued ?? 0;
    addToast(
      count > 0
        ? `Requirements saved. Re-scoring ${count} candidate${count !== 1 ? 's' : ''}…`
        : 'Requirements saved.'
    );
    setPollPaused(false);
    api.listCandidates(jobId).then((data) => setCandidates(data?.candidates ?? []));
  };

  const handleResumesUploaded = (count) => {
    setAddResumesModalOpen(false);
    addToast(`Uploaded ${count} resume${count !== 1 ? 's' : ''}. Candidates are being processed.`);
    setPollPaused(false);
    api.listCandidates(jobId).then((data) => setCandidates(data?.candidates ?? []));
  };

  const tableRef = useRef(null);
  const pointerOverTable = useRef(false);

  // Initial load
  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getJob(jobId), api.listCandidates(jobId)])
      .then(([jobData, candData]) => {
        if (cancelled) return;
        setJob(jobData);
        setCandidates(candData?.candidates ?? []);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err?.status === 404) {
          navigate('/jobs', { replace: true });
          return;
        }
        setError('Failed to load job details. Please refresh.');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, navigate]);

  // Polling
  const liveRef = useRef({ job, candidates });
  liveRef.current = { job, candidates };

  const shouldPoll = useCallback((data) => {
    if (!data) return false;
    const { job: j, candidates: cands } = data || {};
    if (j?.blocking_reason === 'awaiting_jd') return true;
    return (cands ?? []).some((c) => IN_PROGRESS.has(c.display_status));
  }, []);

  usePolling(
    async () => {
      const [jobData, candData] = await Promise.all([
        api.getJob(jobId),
        api.listCandidates(jobId),
      ]);
      return { job: jobData, candidates: candData?.candidates ?? [] };
    },
    {
      shouldPoll: (data) => {
        if (!data) return shouldPoll({ job: liveRef.current.job, candidates: liveRef.current.candidates });
        return shouldPoll(data);
      },
      onData: ({ job: newJob, candidates: newCands }) => {
        setPollError(false);
        setJob(newJob);
        setCandidates((prev) => {
          if (pointerOverTable.current) return prev;
          const merged = new Map(prev.map((c) => [c.candidate_id, c]));
          newCands.forEach((c) => merged.set(c.candidate_id, c));
          return Array.from(merged.values());
        });
      },
      onError: () => {
        setPollError(true);
      },
      onMaxDuration: () => setPollPaused(true),
    }
  );

  // Table hover detection
  useEffect(() => {
    const el = tableRef.current;
    if (!el) return;
    const over = () => { pointerOverTable.current = true; };
    const out = () => { pointerOverTable.current = false; };
    el.addEventListener('pointerenter', over);
    el.addEventListener('pointerleave', out);
    return () => {
      el.removeEventListener('pointerenter', over);
      el.removeEventListener('pointerleave', out);
    };
  }, []);

  const handleDecisionChange = useCallback((candidateId, patch) => {
    setCandidates((prev) =>
      prev.map((c) => (c.candidate_id === candidateId ? { ...c, ...patch } : c))
    );
  }, []);

  const handleExport = async () => {
    try {
      const { download_url, count } = await api.exportCsv(jobId);
      window.location.assign(download_url);
      addToast(`Exported ${count} candidate${count !== 1 ? 's' : ''}.`);
    } catch (err) {
      addToast(err?.message ?? 'Export failed.');
    }
  };

  // Metrics derived from real candidate data
  const counts = candidates.reduce((acc, c) => {
    const group = DISPLAY[c.display_status]?.group ?? 'attention';
    acc[group] = (acc[group] || 0) + 1;
    if (c.shortlist_candidate) acc.recommended = (acc.recommended || 0) + 1;
    if (c.decision === 'shortlisted') acc.shortlisted = (acc.shortlisted || 0) + 1;
    if (c.decision === 'rejected') acc.rejected = (acc.rejected || 0) + 1;
    return acc;
  }, {});

  const totalCandidates = candidates.length;
  const recommendedCount = counts.recommended ?? 0;
  const reviewedCount = (counts.shortlisted ?? 0) + (counts.rejected ?? 0);
  const processingCount = counts.progress ?? 0;
  const shortlistedCount = counts.shortlisted ?? 0;

  // Filter & sort
  let displayed = candidates;
  if (search) {
    const q = search.toLowerCase();
    displayed = displayed.filter(
      (c) =>
        (c.name ?? '').toLowerCase().includes(q) ||
        (c.skills ?? []).some((s) => s.toLowerCase().includes(q))
    );
  }
  if (filterGroup) {
    displayed = displayed.filter((c) => {
      const g = DISPLAY[c.display_status]?.group;
      if (filterGroup === 'recommended') return c.shortlist_candidate;
      if (filterGroup === 'shortlisted') return c.decision === 'shortlisted';
      return g === filterGroup;
    });
  }

  displayed = [...displayed].sort((a, b) => {
    const aVal = a[sortKey];
    const bVal = b[sortKey];
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const rankMap = new Map();
  [...candidates]
    .filter((c) => c.display_status === 'scored')
    .sort((a, b) => (Number(b.match_score ?? 0)) - (Number(a.match_score ?? 0)))
    .forEach((c, idx) => rankMap.set(c.candidate_id, idx + 1));

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  if (loading) {
    return (
      <div className="loading-page">
        <div className="spinner spinner--lg" role="status" aria-label="Loading job details" />
        <span>Loading requisition pipeline…</span>
      </div>
    );
  }

  if (error) {
    return <div className="error-message" role="alert">{error}</div>;
  }

  const {
    job_title,
    blocking_reason,
    parse_status,
    scorable,
  } = job ?? {};

  const required_skills = job?.effective?.skills ?? job?.required_skills ?? [];
  const required_titles = job?.effective?.titles ?? job?.required_titles ?? [];
  const min_experience_years = job?.effective?.min_experience_years ?? job?.min_experience_years;
  const shortlist_threshold = job?.shortlist_threshold ?? 70;

  const isReady = scorable || parse_status === 'success';

  return (
    <>
      {/* Compact Job Header */}
      <div className="page-header">
        <div className="page-header__left">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="page-header__kicker">JOB PIPELINE</span>
            <StatusMark
              status={parse_status === 'error' ? 'failed' : isReady ? 'ready' : 'processing'}
              label={parse_status === 'error' ? 'FAILED' : isReady ? 'READY' : 'PROCESSING'}
            />
          </div>
          <h1 className="page-header__title" style={{ fontSize: '24px' }}>
            {job_title}
          </h1>
          <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
            Created {job?.created_at ? formatDate(job.created_at) : '—'} • ID: {jobId}
          </span>
        </div>

        <div className="page-header__actions">
          <Tooltip content="Upload additional candidate resumes to this requisition">
            <button
              id="add-resumes-btn"
              className="btn btn--secondary"
              onClick={() => setAddResumesModalOpen(true)}
            >
              + Add Resumes
            </button>
          </Tooltip>
          <Tooltip content="Modify required skills, titles, experience, and shortlist threshold">
            <button
              id="edit-requirements-btn"
              className="btn btn--secondary"
              onClick={() => setEditDrawerOpen(true)}
            >
              Edit Requirements
            </button>
          </Tooltip>
          <Tooltip content={shortlistedCount === 0 ? 'Shortlist at least one candidate to export' : `Export ${shortlistedCount} shortlisted candidate${shortlistedCount !== 1 ? 's' : ''} to CSV`}>
            <button
              id="export-btn"
              className="btn btn--primary"
              onClick={handleExport}
              disabled={shortlistedCount === 0}
            >
              Export Shortlist ({shortlistedCount})
            </button>
          </Tooltip>
        </div>
      </div>

      {/* Metrics Strip */}
      <div className="metrics-strip">
        <div className="metric-card">
          <span className="metric-card__label">Candidates</span>
          <span className="metric-card__value"><CountUp value={totalCandidates} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Recommended</span>
          <span className="metric-card__value metric-card__value--success"><CountUp value={recommendedCount} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Reviewed</span>
          <span className="metric-card__value metric-card__value--accent"><CountUp value={reviewedCount} /></span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Processing</span>
          <span className="metric-card__value metric-card__value--warning"><CountUp value={processingCount} /></span>
        </div>
      </div>

      {/* Poll / Blocking Banners */}
      {pollError && (
        <div className="banner banner--warning" style={{ marginBottom: 'var(--space-3)' }}>
          <span>Having trouble polling live candidate updates. Retrying in background…</span>
        </div>
      )}
      {pollPaused && (
        <div className="banner banner--warning" style={{ marginBottom: 'var(--space-3)' }}>
          <span>Live polling paused after maximum interval.</span>
          <button className="banner__action" onClick={() => setPollPaused(false)}>
            Resume Polling
          </button>
        </div>
      )}
      {blocking_reason === 'awaiting_jd' && (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <LatticeLoader
            label="Processing Job Description…"
            sublabel="Candidates will be scored automatically once criteria extraction completes."
            showElapsed={true}
          />
        </div>
      )}
      {blocking_reason === 'jd_failed' && (
        <div className="banner banner--warning" style={{ marginBottom: 'var(--space-3)' }}>
          <span>Could not extract job description document. Review criteria to enable scoring.</span>
          <button
            className="banner__action"
            id="review-requirements-btn"
            onClick={() => setEditDrawerOpen(true)}
          >
            Review Requirements
          </button>
        </div>
      )}

      {/* Compact Criteria Strip */}
      <SpotlightCard className="card" style={{ marginBottom: 'var(--space-5)' }}>
        <div className="card__header">
          <span className="card__header-title">Screening Criteria</span>
          <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
            Threshold: {shortlist_threshold ?? 70}%
          </span>
        </div>
        <div className="card__body" style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)', fontSize: '12px' }}>
          <div>
            <span style={{ color: 'var(--color-text-secondary)', marginRight: '6px' }}>Required Skills:</span>
            {required_skills.length === 0 ? (
              <span style={{ color: 'var(--color-text-muted)' }}>None</span>
            ) : (
              required_skills.map((s) => <span key={s} className="chip chip--neutral" style={{ marginRight: '4px' }}>{s}</span>)
            )}
          </div>
          <div>
            <span style={{ color: 'var(--color-text-secondary)', marginRight: '6px' }}>Target Titles:</span>
            {required_titles.length === 0 ? (
              <span style={{ color: 'var(--color-text-muted)' }}>None</span>
            ) : (
              required_titles.map((t) => <span key={t} className="chip chip--neutral" style={{ marginRight: '4px' }}>{t}</span>)
            )}
          </div>
          <div>
            <span style={{ color: 'var(--color-text-secondary)', marginRight: '6px' }}>Min Experience:</span>
            <span className="mono">{min_experience_years != null ? `${min_experience_years} yrs` : 'Not set'}</span>
          </div>
        </div>
      </SpotlightCard>

      {/* Candidate Pipeline Section */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
        <div className="section-kicker" style={{ margin: 0 }}>
          <span>CANDIDATE PIPELINE</span>
          <span className="section-kicker__count">{displayed.length}</span>
        </div>

        {/* Search & Filter Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <input
            id="candidate-search"
            type="search"
            className="input"
            style={{ width: 220, padding: '5px 8px', fontSize: '12px' }}
            placeholder="Search candidate or skill…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search candidates"
          />

          <div className="segmented-control">
            <button
              id="filter-all-btn"
              type="button"
              className={`segmented-control__option ${!filterGroup ? 'active' : ''}`}
              onClick={() => setFilterGroup(null)}
            >
              All ({totalCandidates})
            </button>
            <button
              id="filter-recommended-btn"
              type="button"
              className={`segmented-control__option ${filterGroup === 'recommended' ? 'active' : ''}`}
              onClick={() => setFilterGroup('recommended')}
            >
              Recommended ({recommendedCount})
            </button>
            <button
              id="filter-shortlisted-btn"
              type="button"
              className={`segmented-control__option ${filterGroup === 'shortlisted' ? 'active' : ''}`}
              onClick={() => setFilterGroup('shortlisted')}
            >
              Shortlisted ({shortlistedCount})
            </button>
          </div>
        </div>
      </div>

      {/* Candidate Table */}
      {displayed.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state__icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <h2 className="empty-state__title">NO CANDIDATES IN PIPELINE</h2>
          <p className="empty-state__description">
            {filterGroup || search
              ? 'No candidates match the selected filters.'
              : 'Upload candidate resumes to start automated extraction and scoring.'}
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table ref={tableRef} className="data-table" aria-label="Candidates pipeline table">
            <thead>
              <tr>
                <th scope="col" style={{ width: 45, textAlign: 'center' }}>#</th>
                <th scope="col" style={{ width: '25%' }}>Candidate</th>
                <th
                  scope="col"
                  style={{ textAlign: 'center', cursor: 'pointer' }}
                  onClick={() => handleSort('match_score')}
                >
                  Match Score {sortKey === 'match_score' ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                </th>
                <th scope="col">Skills</th>
                <th
                  scope="col"
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleSort('total_experience_years')}
                >
                  Experience {sortKey === 'total_experience_years' ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                </th>
                <th scope="col">Status</th>
                <th scope="col">Decision</th>
                <th scope="col" style={{ width: 60, textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((c) => (
                <CandidateRow
                  key={c.candidate_id}
                  candidate={c}
                  rank={rankMap.get(c.candidate_id)}
                  jobId={jobId}
                  onDecisionChange={handleDecisionChange}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Requirements Editor Drawer */}
      <RequirementsDrawer
        open={editDrawerOpen}
        job={job}
        onClose={() => setEditDrawerOpen(false)}
        onSaved={handleRequirementsSaved}
      />

      {/* Add Resumes Modal */}
      <AddResumesModal
        open={addResumesModalOpen}
        jobId={jobId}
        currentCandidateCount={candidates.length}
        onClose={() => setAddResumesModalOpen(false)}
        onUploadComplete={handleResumesUploaded}
      />
    </>
  );
}
