// src/components/job/AddResumesModal.jsx
// Modal for adding more resumes to an existing job.
// Calls POST /jobs/{job_id}/resumes to get presigned S3 URLs, then uploads via uploadFile.
import { useState, useEffect } from 'react';
import FileDropZone from '../form/FileDropZone';
import StatusMark from '../ui/StatusMark';
import CountUp from '../ui/CountUp';
import Tooltip from '../ui/Tooltip';
import LatticeLoader from '../ui/LatticeLoader';
import { uploadFile, UploadError } from '../../api/upload';
import { formatBytes } from '../../domain/format';
import { api } from '../../api/client';

const MAX_PER_REQUEST = 25;
const MAX_TOTAL_CANDIDATES = 100;
const CONCURRENCY = 4;

function AddResumesModalContent({
  jobId,
  currentCandidateCount = 0,
  onClose,
  onUploadComplete,
}) {
  const [selectedFiles, setSelectedFiles] = useState([]); // [{ file: File, error: string|null }]
  const [uploadStatuses, setUploadStatuses] = useState(null); // [{ status, progress, error }]
  const [submitting, setSubmitting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const [uploadSummary, setUploadSummary] = useState(null); // { total, uploaded, failed }

  const remainingCapacity = Math.max(0, MAX_TOTAL_CANDIDATES - currentCandidateCount);
  const maxAllowed = Math.min(MAX_PER_REQUEST, remainingCapacity);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isUploading && !submitting) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isUploading, submitting, onClose]);

  const validFiles = selectedFiles.filter((f) => !f.error);

  const handleFilesAdded = (newResults) => {
    setSelectedFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.file.name));
      const filtered = newResults.filter((r) => !existingNames.has(r.file.name));
      const combined = [...prev, ...filtered];
      if (combined.length > maxAllowed) {
        return combined.slice(0, maxAllowed);
      }
      return combined;
    });
  };

  const removeFile = (filename) => {
    if (isUploading) return;
    setSelectedFiles((prev) => prev.filter((f) => f.file.name !== filename));
  };

  const handleStartUpload = async () => {
    if (validFiles.length === 0 || submitting || isUploading) return;
    setError('');
    setSubmitting(true);

    let presignedList = [];
    try {
      // 1. Request presigned upload policies from API
      const filenames = validFiles.map((f) => f.file.name);
      const res = await api.addResumes(jobId, filenames);
      presignedList = res.resumes ?? [];
    } catch (err) {
      setError(err?.message ?? 'Failed to initiate resume uploads. Please try again.');
      setSubmitting(false);
      return;
    }

    setSubmitting(false);
    setIsUploading(true);

    // Map each valid file to its presigned item
    const uploadItems = validFiles.map((item, index) => {
      const match = presignedList.find((p) => p.filename === item.file.name) ?? presignedList[index];
      return {
        candidateId: match?.candidate_id,
        filename: item.file.name,
        presigned: match?.upload,
        file: item.file,
      };
    });

    const initialStatuses = uploadItems.map(() => ({ status: 'queued', progress: 0, error: null }));
    setUploadStatuses(initialStatuses);

    // 2. Upload worker pool
    let completedCount = 0;
    let failedCount = 0;
    const total = uploadItems.length;
    let nextIdx = 0;
    let running = 0;

    const updateStatus = (idx, update) => {
      setUploadStatuses((prev) => {
        if (!prev) return prev;
        const copy = [...prev];
        copy[idx] = { ...copy[idx], ...update };
        return copy;
      });
    };

    const uploadWorker = async (idx) => {
      if (idx >= total) return;
      running++;
      const item = uploadItems[idx];

      if (!item.presigned) {
        updateStatus(idx, { status: 'failed', error: 'No upload URL provided' });
        failedCount++;
        running--;
        if (nextIdx < total) uploadWorker(nextIdx++);
        return;
      }

      updateStatus(idx, { status: 'uploading', progress: 0 });

      try {
        await uploadFile(item.presigned, item.file, (progress) => {
          updateStatus(idx, { status: 'uploading', progress });
        });
        updateStatus(idx, { status: 'uploaded', progress: 1 });
        completedCount++;
      } catch (err) {
        // Retry once on transient network or 5xx error
        if (err instanceof UploadError && (err.status >= 500 || err.status === 0 || err.kind === 'network')) {
          try {
            await uploadFile(item.presigned, item.file, (progress) => {
              updateStatus(idx, { status: 'uploading', progress });
            });
            updateStatus(idx, { status: 'uploaded', progress: 1 });
            completedCount++;
          } catch (retryErr) {
            updateStatus(idx, { status: 'failed', error: retryErr.kind || 'network' });
            failedCount++;
          }
        } else {
          updateStatus(idx, { status: 'failed', error: err.kind || err.message || 'failed' });
          failedCount++;
        }
      } finally {
        running--;
        if (nextIdx < total) {
          const next = nextIdx++;
          uploadWorker(next);
        } else if (running === 0) {
          // Finished all items
          setIsUploading(false);
          setUploadSummary({ total, uploaded: completedCount, failed: failedCount });
          if (completedCount > 0) {
            onUploadComplete(completedCount);
          }
        }
      }
    };

    const initialPool = Math.min(CONCURRENCY, total);
    nextIdx = initialPool;
    for (let i = 0; i < initialPool; i++) {
      uploadWorker(i);
    }
  };

  return (
    <div
      id="add-resumes-modal"
      className="dialog-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-resumes-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isUploading && !submitting) onClose();
      }}
    >
      <div className="dialog-card" style={{ maxWidth: 640 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
          <div>
            <span className="page-header__kicker">RESUME INGESTION</span>
            <h2 id="add-resumes-title" className="dialog-card__title" style={{ margin: 0, fontSize: '18px' }}>
              Add Resumes to Job
            </h2>
          </div>
          {!isUploading && !submitting && (
            <button
              type="button"
              className="drawer-close"
              onClick={onClose}
              aria-label="Close add resumes modal"
            >
              ×
            </button>
          )}
        </div>

        {error && (
          <div className="error-message" role="alert" style={{ marginBottom: 'var(--space-3)' }}>
            {error}
          </div>
        )}

        {/* Capacity indicator */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-3)' }}>
          <span>Current candidates: <span className="mono">{currentCandidateCount}</span> / {MAX_TOTAL_CANDIDATES} max</span>
          <span>Batch limit: <span className="mono">{maxAllowed}</span> resumes</span>
        </div>

        {remainingCapacity <= 0 ? (
          <div className="banner banner--warning" style={{ margin: 0 }}>
            <span>This job has reached the maximum capacity of {MAX_TOTAL_CANDIDATES} candidates.</span>
          </div>
        ) : !isUploading && !uploadStatuses ? (
          <>
            <FileDropZone
              onFiles={handleFilesAdded}
              multiple={true}
              label="Drop candidate resumes here or click to browse"
            />

            {/* Selected files preview */}
            {selectedFiles.length > 0 && (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                  <span className="section-kicker" style={{ margin: 0 }}>
                    SELECTED FILES ({validFiles.length})
                  </span>
                  {selectedFiles.length > maxAllowed && (
                    <span style={{ fontSize: '11px', color: 'var(--color-warning)' }}>
                      Capped at {maxAllowed} files
                    </span>
                  )}
                </div>

                <div className="file-list" style={{ maxHeight: 220, overflowY: 'auto' }}>
                  {selectedFiles.map(({ file, error: fileErr }) => (
                    <div key={file.name} className="file-item">
                      <div className="file-item__info">
                        <span className="file-item__name" title={file.name}>{file.name}</span>
                        <span className="file-item__size">{formatBytes(file.size)}</span>
                      </div>
                      {fileErr ? (
                        <StatusMark status="failed" label={fileErr} />
                      ) : (
                        <Tooltip content="Remove file from list">
                          <button
                            type="button"
                            className="btn-icon"
                            onClick={() => removeFile(file.name)}
                            aria-label={`Remove ${file.name}`}
                            style={{ color: 'var(--color-text-muted)', background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px 6px' }}
                          >
                            ✕
                          </button>
                        </Tooltip>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          /* Active upload progress */
          <div style={{ marginTop: 'var(--space-2)' }}>
            {isUploading && (
              <div style={{ marginBottom: 'var(--space-3)' }}>
                <LatticeLoader
                  label="Uploading resumes to S3…"
                  sublabel="Direct multi-part presigned upload in progress"
                  showElapsed={true}
                />
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-3)' }}>
              <span className="section-kicker" style={{ margin: 0 }}>
                {isUploading ? 'UPLOADING TO S3…' : 'UPLOAD COMPLETE'}
              </span>
              {uploadSummary && (
                <span className="mono" style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                  <CountUp value={uploadSummary.uploaded} />/{uploadSummary.total} Uploaded
                  {uploadSummary.failed > 0 ? `, ${uploadSummary.failed} Failed` : ''}
                </span>
              )}
            </div>

            <div className="file-list" style={{ maxHeight: 280, overflowY: 'auto' }}>
              {validFiles.map(({ file }, idx) => {
                const s = uploadStatuses?.[idx] || { status: 'queued', progress: 0 };
                return (
                  <div key={file.name} className="file-item">
                    <div className="file-item__info">
                      <span className="file-item__name" title={file.name}>{file.name}</span>
                      <span className="file-item__size">{formatBytes(file.size)}</span>
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
          </div>
        )}

        <div className="dialog-card__actions" style={{ marginTop: 'var(--space-5)' }}>
          {!isUploading && !uploadSummary ? (
            <>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="button"
                id="upload-resumes-btn"
                className="btn btn--primary"
                onClick={handleStartUpload}
                disabled={validFiles.length === 0 || submitting || remainingCapacity <= 0}
              >
                {submitting ? 'Requesting Upload URLs…' : `Upload ${validFiles.length} Resume${validFiles.length !== 1 ? 's' : ''} →`}
              </button>
            </>
          ) : !isUploading && uploadSummary ? (
            <button
              type="button"
              id="finish-add-resumes-btn"
              className="btn btn--primary"
              onClick={onClose}
            >
              Done
            </button>
          ) : (
            <button type="button" className="btn btn--secondary" disabled>
              Uploading in progress…
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AddResumesModal({
  open,
  jobId,
  currentCandidateCount = 0,
  onClose,
  onUploadComplete,
}) {
  if (!open) return null;

  return (
    <AddResumesModalContent
      jobId={jobId}
      currentCandidateCount={currentCandidateCount}
      onClose={onClose}
      onUploadComplete={onUploadComplete}
    />
  );
}
