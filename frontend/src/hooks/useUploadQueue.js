// src/hooks/useUploadQueue.js
// Manages a pool of 4 concurrent S3 presigned-POST uploads.
// Per 04-frontend-dashboard.md §4.2 and Design.md §5.1.
import { useState, useEffect, useRef, useCallback } from 'react';
import { uploadFile, UploadError } from '../api/upload';

// Each item: { candidateId, originalFilename, presigned: {url, fields}, file: File }
// File status: 'queued' | 'uploading' | 'uploaded' | 'failed'

const CONCURRENCY = 4;

/**
 * @param {Array<{ candidateId: string, originalFilename: string,
 *                  presigned: { url: string, fields: {} }, file: File }>} items
 */
export function useUploadQueue(items) {
  const [statuses, setStatuses] = useState(() =>
    items.map(() => ({ status: 'queued', progress: 0, error: null }))
  );
  const mountedRef = useRef(true);
  const startedItemsRef = useRef(null);

  const updateStatus = useCallback((idx, patch) => {
    if (!mountedRef.current) return;
    setStatuses((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (items.length === 0 || startedItemsRef.current === items) return;

    startedItemsRef.current = items;
    setStatuses(items.map(() => ({ status: 'queued', progress: 0, error: null })));

    let nextIdx = 0;

    const uploadOne = async (idx) => {
      if (idx >= items.length || !mountedRef.current) return;
      const item = items[idx];
      updateStatus(idx, { status: 'uploading', progress: 0 });
      try {
        await uploadFile(item.presigned, item.file, (p) =>
          updateStatus(idx, { progress: p })
        );
        updateStatus(idx, { status: 'uploaded', progress: 1 });
      } catch (err) {
        if (err instanceof UploadError && err.kind === 'network') {
          // One automatic retry on network errors
          try {
            await uploadFile(item.presigned, item.file, (p) =>
              updateStatus(idx, { progress: p })
            );
            updateStatus(idx, { status: 'uploaded', progress: 1 });
          } catch (retryErr) {
            updateStatus(idx, { status: 'failed', error: retryErr.kind || 'network' });
          }
        } else {
          updateStatus(idx, { status: 'failed', error: err.kind || 'rejected' });
        }
      } finally {
        if (nextIdx < items.length) {
          uploadOne(nextIdx++);
        }
      }
    };

    // Seed the initial pool
    const initial = Math.min(CONCURRENCY, items.length);
    nextIdx = initial;
    for (let i = 0; i < initial; i++) uploadOne(i);
  }, [items, updateStatus]);

  useEffect(() => {
    // beforeunload guard
    const guard = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', guard);

    return () => {
      mountedRef.current = false;
      window.removeEventListener('beforeunload', guard);
    };
  }, []);

  const total = items.length;
  const uploaded = statuses.filter((s) => s.status === 'uploaded').length;
  const failed = statuses.filter((s) => s.status === 'failed').length;
  const done = total > 0 && uploaded + failed === total;

  return { statuses, total, uploaded, failed, done };
}
