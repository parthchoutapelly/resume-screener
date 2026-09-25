// src/components/ui/LatticeLoader.jsx
// Operation-level 3x3 lattice progress indicator for batch processing and rescoring.
// Adapts React Bits LatticeLoader with restrained palette, no neon glow, and reduced-motion safety.

import { useState, useEffect } from 'react';

export default function LatticeLoader({
  label,
  sublabel,
  size = 28,
  showElapsed = false,
  className = '',
}) {
  const [elapsedSecs, setElapsedSecs] = useState(0);

  useEffect(() => {
    if (!showElapsed) return;
    const interval = setInterval(() => {
      setElapsedSecs((s) => s + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [showElapsed]);

  // 3x3 grid cells with staggered animation delays
  const cells = [
    { id: 0, delay: '0ms' },
    { id: 1, delay: '120ms' },
    { id: 2, delay: '240ms' },
    { id: 3, delay: '360ms' },
    { id: 4, delay: '480ms' },
    { id: 5, delay: '600ms' },
    { id: 6, delay: '720ms' },
    { id: 7, delay: '840ms' },
    { id: 8, delay: '960ms' },
  ];

  const dotSize = Math.max(3, Math.round(size / 5));

  return (
    <div
      className={`lattice-loader ${className}`}
      role="status"
      aria-live="polite"
      aria-label={label || 'Processing operation'}
    >
      <div
        className="lattice-loader__grid"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gridTemplateRows: 'repeat(3, 1fr)',
          gap: '3px',
          alignItems: 'center',
          justifyItems: 'center',
        }}
        aria-hidden="true"
      >
        {cells.map((c) => (
          <span
            key={c.id}
            className="lattice-loader__dot"
            style={{
              width: `${dotSize}px`,
              height: `${dotSize}px`,
              animationDelay: c.delay,
            }}
          />
        ))}
      </div>

      {(label || showElapsed) && (
        <div className="lattice-loader__meta">
          {label && <span className="lattice-loader__label">{label}</span>}
          {sublabel && <span className="lattice-loader__sublabel">{sublabel}</span>}
          {showElapsed && (
            <span className="lattice-loader__timer mono">
              {Math.floor(elapsedSecs / 60)}:{String(elapsedSecs % 60).padStart(2, '0')}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
