// src/components/job/RequirementsDrawer.jsx
// Drawer to view and edit job requirements and threshold.
// Triggers PATCH /jobs/{job_id} which automatically triggers rescoring while preserving decisions.
import { useState, useEffect } from 'react';
import ChipInput from '../form/ChipInput';
import { api } from '../../api/client';

function RequirementsDrawerContent({ job, onClose, onSaved }) {
  const [skills, setSkills] = useState(() => job.effective?.skills ?? job.required_skills ?? []);
  const [titles, setTitles] = useState(() => job.effective?.titles ?? job.required_titles ?? []);
  const [minYears, setMinYears] = useState(() => {
    const val = job.effective?.min_experience_years ?? job.min_experience_years;
    return val != null ? String(val) : '';
  });
  const [threshold, setThreshold] = useState(() => String(job.shortlist_threshold ?? 70));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Handle ESC key to close
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !saving) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [saving, onClose]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (saving) return;
    setError('');

    // Validation
    if (skills.length === 0) {
      setError('At least one required skill is required to score candidates.');
      return;
    }

    if (minYears !== '') {
      const parsedYears = Number(minYears);
      if (isNaN(parsedYears) || parsedYears < 0 || parsedYears > 50) {
        setError('Minimum experience must be between 0 and 50 years.');
        return;
      }
    }

    const parsedThreshold = Number(threshold);
    if (isNaN(parsedThreshold) || parsedThreshold < 50 || parsedThreshold > 95) {
      setError('Shortlist threshold must be between 50% and 95%.');
      return;
    }

    const patch = {
      required_skills: skills,
      required_titles: titles,
      shortlist_threshold: parsedThreshold,
    };
    if (minYears !== '') {
      patch.min_experience_years = Number(minYears);
    }

    setSaving(true);
    try {
      const updatedJob = await api.updateJob(job.job_id, patch);
      onSaved(updatedJob);
    } catch (err) {
      setError(err?.message ?? 'Failed to update requirements. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      id="requirements-drawer"
      className="drawer-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="requirements-drawer-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
    >
      <div className="drawer-panel">
        <div className="drawer-header">
          <div>
            <span className="page-header__kicker">CRITERIA CONFIGURATION</span>
            <h2 id="requirements-drawer-title" className="drawer-title">
              Edit Job Requirements
            </h2>
          </div>
          <button
            type="button"
            className="drawer-close"
            onClick={onClose}
            disabled={saving}
            aria-label="Close requirements drawer"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSave} style={{ display: 'contents' }}>
          <div className="drawer-body">
            {error && (
              <div className="error-message" role="alert" style={{ margin: 0 }}>
                {error}
              </div>
            )}

            <div className="banner banner--info" style={{ margin: 0, fontSize: '12px' }}>
              <span>
                Saving updated requirements will automatically trigger rescoring for existing candidates.
                Your shortlist and reject decisions will not be changed.
              </span>
            </div>

            <ChipInput
              id="drawer-required-skills"
              label={
                <>
                  Required skills <span style={{ color: 'var(--color-accent)' }}>*</span>
                </>
              }
              chips={skills}
              onAdd={(item) => setSkills((prev) => [...prev, item])}
              onRemove={(item) => setSkills((prev) => prev.filter((s) => s !== item))}
              placeholder="Add skill and press Enter (e.g. Python, AWS)…"
              helpText="Primary skills used to evaluate candidate resumes."
            />

            <ChipInput
              id="drawer-required-titles"
              label="Target job titles"
              chips={titles}
              onAdd={(item) => setTitles((prev) => [...prev, item])}
              onRemove={(item) => setTitles((prev) => prev.filter((t) => t !== item))}
              placeholder="e.g. Software Engineer, Tech Lead…"
              helpText="Titles evaluated against work history on resumes."
            />

            <div className="field">
              <label className="field__label" htmlFor="drawer-min-years">
                Minimum experience (years)
              </label>
              <input
                id="drawer-min-years"
                className="input mono"
                type="number"
                min="0"
                max="50"
                step="1"
                placeholder="e.g. 3 (leave blank for none)"
                value={minYears}
                onChange={(e) => setMinYears(e.target.value)}
              />
              <span className="field__help">Minimum years of relevant experience requested.</span>
            </div>

            <div className="field">
              <label className="field__label" htmlFor="drawer-threshold">
                Shortlist threshold:{' '}
                <span className="mono" style={{ color: 'var(--color-accent)', fontWeight: 700 }}>
                  {threshold}%
                </span>
              </label>
              <input
                id="drawer-threshold"
                type="range"
                min="50"
                max="95"
                step="5"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                style={{ width: '100%', marginTop: '6px' }}
              />
              <span className="field__help">Candidates scoring at or above this match score qualify as Recommended.</span>
            </div>
          </div>

          <div className="drawer-footer">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              id="save-requirements-btn"
              className="btn btn--primary"
              disabled={saving || skills.length === 0}
            >
              {saving ? 'Saving & Re-scoring…' : 'Save & Re-score Candidates'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function RequirementsDrawer({ open, job, onClose, onSaved }) {
  if (!open || !job) return null;

  return (
    <RequirementsDrawerContent
      key={`${job.job_id}-${job.updated_at || ''}`}
      job={job}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}
