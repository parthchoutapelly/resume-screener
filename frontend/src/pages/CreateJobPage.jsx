// src/pages/CreateJobPage.jsx
// Professional two-column workflow for creating job requisitions and uploading candidate batches.
import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import ChipInput from '../components/form/ChipInput';
import FileDropZone from '../components/form/FileDropZone';
import StatusMark from '../components/ui/StatusMark';
import CountUp from '../components/ui/CountUp';
import Tooltip from '../components/ui/Tooltip';
import LatticeLoader from '../components/ui/LatticeLoader';
import { formatBytes } from '../domain/format';
import { useUploadQueue } from '../hooks/useUploadQueue';
import { config } from '../config';

const api = config.useMocks
  ? (await import('../api/mock.js')).mockApi
  : (await import('../api/client.js')).api;

const MAX_RESUMES = 50;

// Upload progress panel
function UploadProgressPanel({ items, statuses, total, uploaded, failed, done, onGoToJob }) {
  return (
    <div className="card">
      <div className="card__header">
        <span className="card__header-title">Ingestion Queue in Progress</span>
        <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
          <CountUp value={uploaded} />/{total} Uploaded{failed > 0 ? `, ${failed} Failed` : ''}
        </span>
      </div>
      <div className="card__body">
        {!done && (
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <LatticeLoader
              label="Uploading files to S3…"
              sublabel={`Direct presigned upload in progress (${uploaded} of ${total} files complete)`}
              showElapsed={true}
            />
          </div>
        )}

        <div className="file-list">
          {items.map((item, i) => {
            const s = statuses[i] || { status: 'queued', progress: 0 };
            return (
              <div key={item.originalFilename + i} className="file-item">
                <div className="file-item__info">
                  <span className="file-item__name">{item.originalFilename}</span>
                  <span className="file-item__size">{formatBytes(item.file?.size ?? 0)}</span>
                </div>
                <div className="file-item__actions">
                  <StatusMark
                    status={s.status}
                    label={
                      s.status === 'uploading'
                        ? `${Math.round((s.progress || 0) * 100)}%`
                        : undefined
                    }
                  />
                </div>
              </div>
            );
          })}
        </div>

        {done && (
          <div className="action-bar-bottom" style={{ borderTop: 'none', paddingBottom: 0 }}>
            <button id="go-to-job-btn" className="btn btn--primary" onClick={onGoToJob}>
              Go to job pipeline →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function CreateJobPage() {
  const navigate = useNavigate();

  // Form state
  const [jobTitle, setJobTitle] = useState('');
  const [jdSource, setJdSource] = useState('file'); // 'file' | 'text' | 'none'
  const [jdFile, setJdFile] = useState(null);
  const [jdFileError, setJdFileError] = useState('');
  const [jdText, setJdText] = useState('');
  const [skills, setSkills] = useState([]);
  const [titles, setTitles] = useState([]);
  const [minYears, setMinYears] = useState('');
  const [threshold, setThreshold] = useState('70');
  const [resumeFiles, setResumeFiles] = useState([]); // [{file, error}]

  // Upload queue state
  const [uploadItems, setUploadItems] = useState(null);
  const [createdJobId, setCreatedJobId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const { statuses, total, uploaded, failed, done } = useUploadQueue(uploadItems ?? []);

  useEffect(() => {
    if (uploadItems !== null && done && failed === 0 && createdJobId) {
      const timer = setTimeout(() => navigate(`/jobs/${createdJobId}`), 800);
      return () => clearTimeout(timer);
    }
  }, [uploadItems, done, failed, createdJobId, navigate]);

  // Validation
  const validResumes = resumeFiles.filter((f) => !f.error);
  const isValid = Boolean(
    jobTitle.trim() &&
    (jdSource === 'none' || (jdSource === 'file' && jdFile) || (jdSource === 'text' && jdText.trim())) &&
    (jdSource !== 'none' || skills.length > 0) &&
    validResumes.length + (jdSource === 'file' && jdFile ? 1 : 0) <= MAX_RESUMES
  );

  const handleJdFile = (results) => {
    const first = results[0];
    if (!first) return;
    if (first.error) {
      setJdFile(null);
      setJdFileError(first.error);
    } else {
      setJdFile(first.file);
      setJdFileError('');
    }
  };

  const handleResumeFiles = (results) => {
    setResumeFiles((prev) => {
      const existing = new Set(prev.map((f) => f.file.name));
      const newFiles = results.filter((r) => !existing.has(r.file.name));
      const combined = [...prev, ...newFiles];
      if (combined.length > MAX_RESUMES) {
        return combined.slice(0, MAX_RESUMES);
      }
      return combined;
    });
  };

  const removeResume = (filename) => {
    setResumeFiles((prev) => prev.filter((f) => f.file.name !== filename));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isValid || submitting) return;
    setFormError('');
    setSubmitting(true);

    try {
      const payload = {
        job_title: jobTitle.trim(),
        jd: {
          source: jdSource,
          ...(jdSource === 'file' ? { filename: jdFile.name } : {}),
          ...(jdSource === 'text' ? { text: jdText.trim() } : {}),
        },
        ...(skills.length > 0 ? { required_skills: skills } : {}),
        ...(titles.length > 0 ? { required_titles: titles } : {}),
        ...(minYears ? { min_experience_years: Number(minYears) } : {}),
        shortlist_threshold: Number(threshold) || 70,
        resume_filenames: validResumes.map((f) => f.file.name),
      };

      const { job_id, jd_upload, resumes = [] } = await api.createJob(payload);
      setCreatedJobId(job_id);

      const items = [];
      if (jdSource === 'file' && jdFile && jd_upload) {
        items.push({
          candidateId: null,
          originalFilename: jdFile.name,
          presigned: jd_upload,
          file: jdFile,
        });
      }
      for (const { file } of validResumes) {
        const up = resumes.find((r) => r.filename === file.name);
        if (up) {
          items.push({
            candidateId: up.candidate_id,
            originalFilename: file.name,
            presigned: up.upload,
            file,
          });
        }
      }

      if (items.length === 0) {
        navigate(`/jobs/${job_id}`);
        return;
      }

      setUploadItems(items);
    } catch (err) {
      setFormError(err?.message ?? 'Failed to create job posting. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (uploadItems !== null) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <div className="page-header">
          <div className="page-header__left">
            <span className="page-header__kicker">INGESTION BATCH</span>
            <h1 className="page-header__title">Uploading files</h1>
          </div>
        </div>
        <UploadProgressPanel
          items={uploadItems}
          statuses={statuses}
          total={total}
          uploaded={uploaded}
          failed={failed}
          done={done}
          onGoToJob={() => navigate(`/jobs/${createdJobId}`)}
        />
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header__left">
          <span className="page-header__kicker">REQUISITION WORKSPACE</span>
          <h1 className="page-header__title">Create Job Posting</h1>
          <p className="page-header__subtitle">
            Configure screening criteria, description source, and candidate resume batch.
          </p>
        </div>
      </div>

      {formError && (
        <div className="error-message" role="alert">
          {formError}
        </div>
      )}

      <form id="create-job-form" onSubmit={handleSubmit} noValidate>
        {/* Two-column layout on desktop */}
        <div className="workbench-two-col">
          {/* Left Column: JOB DETAILS */}
          <div className="card">
            <div className="card__header">
              <span className="card__header-title">Job Details</span>
            </div>
            <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <div className="field">
                <label className="field__label" htmlFor="job-title">
                  Job title <span style={{ color: 'var(--color-accent)' }}>*</span>
                </label>
                <input
                  id="job-title"
                  className="input"
                  type="text"
                  placeholder="e.g. Senior Backend Engineer"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  required
                />
              </div>

              <div className="field">
                <label className="field__label">Job description source</label>
                <div style={{ display: 'flex', gap: 'var(--space-3)', margin: 'var(--space-1) 0' }}>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      id="jd-source-file"
                      name="jd-source"
                      value="file"
                      checked={jdSource === 'file'}
                      onChange={() => setJdSource('file')}
                    />
                    Upload file (PDF/DOCX)
                  </label>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      id="jd-source-text"
                      name="jd-source"
                      value="text"
                      checked={jdSource === 'text'}
                      onChange={() => setJdSource('text')}
                    />
                    Paste text
                  </label>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      id="jd-source-none"
                      name="jd-source"
                      value="none"
                      checked={jdSource === 'none'}
                      onChange={() => setJdSource('none')}
                    />
                    No JD (criteria only)
                  </label>
                </div>
              </div>

              {jdSource === 'file' && (
                <div className="field">
                  <label className="field__label">Upload JD Document</label>
                  <FileDropZone
                    multiple={false}
                    onFiles={handleJdFile}
                    accept=".pdf,.docx"
                    label="Drop job description document here, or click to browse"
                  />
                  {jdFile && (
                    <div className="file-item" style={{ marginTop: 'var(--space-2)' }}>
                      <div className="file-item__info">
                        <span className="file-item__name">{jdFile.name}</span>
                        <span className="file-item__size">{formatBytes(jdFile.size)}</span>
                      </div>
                      <span className="badge badge--success">ATTACHED</span>
                    </div>
                  )}
                  {jdFileError && <span className="field__error">{jdFileError}</span>}
                  <span className="field__help">PDF or DOCX up to 10 MB.</span>
                </div>
              )}

              {jdSource === 'text' && (
                <div className="field">
                  <label className="field__label" htmlFor="jd-text">
                    Job description text
                  </label>
                  <textarea
                    id="jd-text"
                    className="textarea mono"
                    style={{ fontSize: '12px', minHeight: 140 }}
                    placeholder="Paste the complete job description text here…"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                  />
                  <span className="field__help">Raw text will be parsed by NLP pipeline.</span>
                </div>
              )}

              {jdSource === 'none' && (
                <div className="banner banner--info" style={{ marginTop: 'var(--space-1)' }}>
                  <span>
                    No document will be parsed. Candidates will be evaluated strictly against explicit screening criteria on the right.
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Right Column: SCREENING CRITERIA */}
          <div className="card">
            <div className="card__header">
              <span className="card__header-title">Screening Criteria</span>
            </div>
            <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              <ChipInput
                id="required-skills"
                label={
                  <>
                    Required skills {jdSource === 'none' && <span style={{ color: 'var(--color-accent)' }}>*</span>}
                  </>
                }
                chips={skills}
                onAdd={(item) => setSkills((prev) => [...prev, item])}
                onRemove={(item) => setSkills((prev) => prev.filter((s) => s !== item))}
                placeholder="Type a skill and press Enter (e.g. Python, AWS)…"
                helpText="Primary matching skills evaluated during candidate scoring."
              />

              <ChipInput
                id="required-titles"
                label="Target job titles"
                chips={titles}
                onAdd={(item) => setTitles((prev) => [...prev, item])}
                onRemove={(item) => setTitles((prev) => prev.filter((t) => t !== item))}
                placeholder="e.g. Software Engineer, Tech Lead…"
                helpText="Titles matched against candidate resume work history."
              />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div className="field">
                  <label className="field__label" htmlFor="min-years">
                    Min experience (years)
                  </label>
                  <input
                    id="min-years"
                    className="input mono"
                    type="number"
                    min="0"
                    max="50"
                    step="1"
                    placeholder="e.g. 3"
                    value={minYears}
                    onChange={(e) => setMinYears(e.target.value)}
                  />
                </div>

                <div className="field">
                  <label className="field__label" htmlFor="threshold">
                    Shortlist threshold: <span className="mono" style={{ color: 'var(--color-accent)' }}>{threshold}%</span>
                  </label>
                  <Tooltip content="Minimum overall match score required for candidate recommendation">
                    <input
                      id="threshold"
                      type="range"
                      min="50"
                      max="95"
                      step="5"
                      value={threshold}
                      onChange={(e) => setThreshold(e.target.value)}
                      style={{ width: '100%', marginTop: '6px' }}
                    />
                  </Tooltip>
                  <span className="field__help">Scores above this qualify as recommended.</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Below both: RESUMES BATCH INGESTION */}
        <div className="card">
          <div className="card__header">
            <span className="card__header-title">Candidate Resumes Batch</span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
              {validResumes.length} / {MAX_RESUMES} MAX
            </span>
          </div>
          <div className="card__body">
            <FileDropZone
              multiple
              onFiles={handleResumeFiles}
              accept=".pdf,.docx"
              label="Drop candidate resumes here (PDF or DOCX), or click to select multiple files"
            />

            {resumeFiles.length > 0 && (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-2)' }}>
                  <span className="mono" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text)' }}>
                    {validResumes.length} {validResumes.length === 1 ? 'resume' : 'resumes'} ready for ingestion
                  </span>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setResumeFiles([])}
                  >
                    Clear all
                  </button>
                </div>

                <div className="file-list">
                  {resumeFiles.map(({ file, error }) => (
                    <div key={file.name} className="file-item">
                      <div className="file-item__info">
                        <span className="file-item__name">{file.name}</span>
                        <span className="file-item__size">{formatBytes(file.size)}</span>
                      </div>
                      <div className="file-item__actions">
                        <StatusMark
                          status={error ? 'failed' : 'ready'}
                          label={error ? error : 'READY'}
                        />
                        <Tooltip content="Remove file from upload batch">
                          <button
                            type="button"
                            className="file-item__remove"
                            onClick={() => removeResume(file.name)}
                            title="Remove file"
                            aria-label={`Remove ${file.name}`}
                          >
                            ×
                          </button>
                        </Tooltip>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Bottom action bar */}
        <div className="action-bar-bottom">
          <Link to="/jobs" className="btn btn--secondary">
            Cancel
          </Link>
          <Tooltip content="Create requisition and begin automated candidate ingestion">
            <button
              type="submit"
              id="create-job-submit-btn"
              className="btn btn--primary btn--lg"
              disabled={!isValid || submitting}
            >
              {submitting ? 'Creating job…' : 'Create job & upload →'}
            </button>
          </Tooltip>
        </div>
      </form>
    </>
  );
}
