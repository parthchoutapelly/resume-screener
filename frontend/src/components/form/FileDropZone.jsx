// src/components/form/FileDropZone.jsx
// Drag-and-drop + click file picker. Client-side validation per R-VAL-04.
import { useState, useRef, useCallback } from 'react';
import { formatBytes } from '../../domain/format';

const ALLOWED_EXTENSIONS = new Set(['pdf', 'docx', 'png', 'jpg', 'jpeg', 'tiff']);
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MiB

export function validateFile(file) {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    return `File type not supported. Use PDF, DOCX, PNG, JPG, or TIFF.`;
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File is larger than 10\u00a0MB (${formatBytes(file.size)}).`;
  }
  return null;
}

/**
 * @param {{ onFiles: (files: Array<{file: File, error: string|null}>) => void,
 *            multiple?: boolean, label?: string, accept?: string }} props
 */
export default function FileDropZone({ onFiles, multiple = true, label = 'Drop files here or click to browse', accept }) {
  const [active, setActive] = useState(false);
  const inputRef = useRef(null);

  const processFiles = useCallback((rawFiles) => {
    const results = Array.from(rawFiles).map((file) => ({
      file,
      error: validateFile(file),
    }));
    onFiles(results);
  }, [onFiles]);

  const handleDrop = (e) => {
    e.preventDefault();
    setActive(false);
    if (e.dataTransfer.files.length) processFiles(e.dataTransfer.files);
  };

  return (
    <div
      className={'drop-zone' + (active ? ' drop-zone--active' : '')}
      onDragOver={(e) => { e.preventDefault(); setActive(true); }}
      onDragLeave={() => setActive(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
      role="button"
      tabIndex={0}
      aria-label={label}
    >
      <div className="drop-zone__title">{label}</div>
      <p style={{ fontSize: 'var(--font-size-sm)', marginTop: 'var(--space-1)' }}>
        PDF, DOCX, PNG, JPG, TIFF · Max 10 MB each
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept || '.pdf,.docx,.png,.jpg,.jpeg,.tiff'}
        className="sr-only"
        onChange={(e) => { if (e.target.files?.length) processFiles(e.target.files); }}
        tabIndex={-1}
        aria-hidden="true"
      />
    </div>
  );
}
