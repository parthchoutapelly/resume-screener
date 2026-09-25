// src/context/ToastContext.jsx
// Production SwipeToast provider with touch swipe dismissal, pause-on-hover,
// and accessible role alerts. Preserves existing addToast(message, options) API.

import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';

const ToastContext = createContext(null);

function inferTone(message = '') {
  const m = message.toLowerCase();
  if (m.includes('fail') || m.includes('error') || m.includes('could not') || m.includes('cannot')) {
    return 'danger';
  }
  if (m.includes('shortlist') || m.includes('uploaded') || m.includes('saved') || m.includes('exported') || m.includes('success')) {
    return 'success';
  }
  if (m.includes('warning') || m.includes('attention') || m.includes('not scored') || m.includes('missing')) {
    return 'warning';
  }
  return 'info';
}

function ToastItem({ toast, onDismiss }) {
  const [dragX, setDragX] = useState(0);
  const [isSwiping, setIsSwiping] = useState(false);
  const startXRef = useRef(0);
  const timerRef = useRef(null);
  const startTimeRef = useRef(0);
  const remainingRef = useRef(toast.duration || 4200);

  const tone = toast.tone || inferTone(toast.message);

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    timerRef.current = setTimeout(() => {
      onDismiss(toast.id);
    }, remainingRef.current);
  }, [toast.id, onDismiss]);

  const pauseTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const elapsed = Date.now() - startTimeRef.current;
    remainingRef.current = Math.max(800, remainingRef.current - elapsed);
  }, []);

  useEffect(() => {
    startTimer();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [startTimer]);

  const handleTouchStart = (e) => {
    startXRef.current = e.touches[0].clientX;
    setIsSwiping(true);
    pauseTimer();
  };

  const handleTouchMove = (e) => {
    if (!isSwiping) return;
    const diff = e.touches[0].clientX - startXRef.current;
    if (diff > 0) {
      setDragX(diff);
    }
  };

  const handleTouchEnd = () => {
    setIsSwiping(false);
    if (dragX > 75) {
      onDismiss(toast.id);
    } else {
      setDragX(0);
      startTimer();
    }
  };

  const toneIcons = {
    success: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" stroke="var(--color-success)" strokeWidth="1.5" />
        <path d="M5.5 8.2L7.2 10L10.5 6.5" stroke="var(--color-success)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    danger: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" stroke="var(--color-danger)" strokeWidth="1.5" />
        <path d="M6 6l4 4M10 6l-4 4" stroke="var(--color-danger)" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    warning: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" stroke="var(--color-warning)" strokeWidth="1.5" />
        <line x1="8" y1="5" x2="8" y2="8.5" stroke="var(--color-warning)" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.75" fill="var(--color-warning)" />
      </svg>
    ),
    info: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" stroke="var(--color-accent)" strokeWidth="1.5" />
        <line x1="8" y1="7.5" x2="8" y2="11" stroke="var(--color-accent)" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="5" r="0.75" fill="var(--color-accent)" />
      </svg>
    ),
  };

  return (
    <div
      className={`toast toast--${tone}`}
      role={tone === 'danger' ? 'alert' : 'status'}
      onMouseEnter={pauseTimer}
      onMouseLeave={startTimer}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{
        transform: dragX > 0 ? `translateX(${dragX}px)` : undefined,
        opacity: dragX > 0 ? Math.max(0.2, 1 - dragX / 150) : undefined,
        transition: isSwiping ? 'none' : 'transform 180ms ease, opacity 180ms ease',
      }}
    >
      <span className="toast__icon" aria-hidden="true">
        {toneIcons[tone] || toneIcons.info}
      </span>
      <span className="toast__content">{toast.message}</span>
      <button
        type="button"
        className="toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, options = {}) => {
    const duration = options.duration ?? 4000;
    const tone = options.tone ?? null;
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, duration, tone }]);
  }, []);

  const handleDismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div
        className="toast-container"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={handleDismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside ToastProvider');
  return ctx;
}
