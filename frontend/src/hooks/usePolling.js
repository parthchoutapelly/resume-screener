// src/hooks/usePolling.js
// Generic polling hook. Exactly ONE timer per mount. Pauses on hidden tabs.
// Per 04-frontend-dashboard.md §6 and Design.md §5.2.

import { useEffect, useRef, useCallback } from 'react';

const BASE_INTERVAL_MS = 5000;
const BACKOFF_INTERVAL_MS = 15000;
const MAX_FAILURES = 3;
const MAX_DURATION_MS = 30 * 60 * 1000; // 30 min

/**
 * @param {() => Promise<any>} fetchFn  Called each poll cycle.
 * @param {{
 *   shouldPoll: (data: any) => boolean,
 *   onData: (data: any) => void,
 *   onError: (err: Error, backingOff: boolean) => void,
 *   onMaxDuration: () => void,
 * }} opts
 */
export function usePolling(fetchFn, { shouldPoll, onData, onError, onMaxDuration }) {
  const timerRef = useRef(null);
  const failCountRef = useRef(0);
  const startTimeRef = useRef(Date.now());
  const latestDataRef = useRef(null);
  const mountedRef = useRef(true);

  // Stable references
  const fetchFnRef = useRef(fetchFn);
  const shouldPollRef = useRef(shouldPoll);
  const onDataRef = useRef(onData);
  const onErrorRef = useRef(onError);
  const onMaxDurationRef = useRef(onMaxDuration);

  fetchFnRef.current = fetchFn;
  shouldPollRef.current = shouldPoll;
  onDataRef.current = onData;
  onErrorRef.current = onError;
  onMaxDurationRef.current = onMaxDuration;

  const schedule = useCallback((intervalMs) => {
    if (!mountedRef.current) return;
    timerRef.current = setTimeout(async () => {
      if (!mountedRef.current) return;

      // Stop if tab is hidden
      if (document.visibilityState === 'hidden') return;

      // Stop if max duration reached
      if (Date.now() - startTimeRef.current >= MAX_DURATION_MS) {
        onMaxDurationRef.current();
        return;
      }

      try {
        const data = await fetchFnRef.current();
        if (!mountedRef.current) return;
        failCountRef.current = 0;
        latestDataRef.current = data;
        onDataRef.current(data);

        if (shouldPollRef.current(data)) {
          schedule(BASE_INTERVAL_MS);
        }
      } catch (err) {
        if (!mountedRef.current) return;
        failCountRef.current += 1;
        const backingOff = failCountRef.current >= MAX_FAILURES;
        onErrorRef.current(err, backingOff);
        if (shouldPollRef.current(latestDataRef.current)) {
          schedule(backingOff ? BACKOFF_INTERVAL_MS : BASE_INTERVAL_MS);
        }
      }
    }, intervalMs);
  }, []);

  // Visibility change: resume immediately
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        clearTimeout(timerRef.current);
        schedule(0);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [schedule]);

  // Start polling immediately on mount
  useEffect(() => {
    mountedRef.current = true;
    startTimeRef.current = Date.now();
    schedule(0);
    return () => {
      mountedRef.current = false;
      clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
