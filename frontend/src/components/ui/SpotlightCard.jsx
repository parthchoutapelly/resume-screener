// src/components/ui/SpotlightCard.jsx
// Subtle localized pointer highlight for high-value ATS summary surfaces.
// Adapts React Bits Spotlight Card with strict performance throttling, no neon, and touch/reduced-motion guards.

import { useRef, useCallback } from 'react';

export default function SpotlightCard({
  children,
  className = '',
  spotlightColor = 'var(--color-spotlight)',
  radius = 260,
  style = {},
  ...restProps
}) {
  const cardRef = useRef(null);
  const rafRef = useRef(null);

  const handleMouseMove = useCallback((e) => {
    if (!cardRef.current) return;

    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }

    const target = cardRef.current;
    const clientX = e.clientX;
    const clientY = e.clientY;

    rafRef.current = requestAnimationFrame(() => {
      if (!target) return;
      const rect = target.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      target.style.setProperty('--spotlight-x', `${x}px`);
      target.style.setProperty('--spotlight-y', `${y}px`);
      target.style.setProperty('--spotlight-opacity', '1');
    });
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }
    if (cardRef.current) {
      cardRef.current.style.setProperty('--spotlight-opacity', '0');
    }
  }, []);

  return (
    <div
      ref={cardRef}
      className={`spotlight-card ${className}`}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        '--spotlight-color': spotlightColor,
        '--spotlight-radius': `${radius}px`,
        ...style,
      }}
      {...restProps}
    >
      <div className="spotlight-card__highlight" aria-hidden="true" />
      <div className="spotlight-card__content">
        {children}
      </div>
    </div>
  );
}
