// src/components/layout/ConfirmDialog.jsx
// Focus-trapping confirmation dialog per Design.md §5.3 and §8.
// Closes on Esc, returns focus to trigger on close.
import { useEffect, useRef } from 'react';

/**
 * @param {{ title: string, body: React.ReactNode,
 *            confirmLabel?: string, cancelLabel?: string, danger?: boolean,
 *            onConfirm: () => void, onCancel: () => void }} props
 */
export default function ConfirmDialog({
  title,
  body,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null);
  const confirmRef = useRef(null);

  useEffect(() => {
    // Focus the confirm button on open
    confirmRef.current?.focus();

    // Esc to cancel
    const onKey = (e) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', onKey);

    // Focus trap
    const trap = (e) => {
      if (!dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])')
      ).filter((el) => !el.disabled);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.key === 'Tab') {
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    };
    document.addEventListener('keydown', trap);

    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('keydown', trap);
    };
  }, [onCancel]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-body"
      >
        <div className="modal__header">
          <h2 className="modal__title" id="confirm-dialog-title">{title}</h2>
          <button
            className="modal__close"
            onClick={onCancel}
            aria-label="Close dialog"
          >
            ×
          </button>
        </div>
        <div className="modal__body" id="confirm-dialog-body">
          {body}
        </div>
        <div className="modal__footer">
          <button
            id="confirm-dialog-cancel-btn"
            className="btn btn--secondary"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            id="confirm-dialog-confirm-btn"
            ref={confirmRef}
            className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
