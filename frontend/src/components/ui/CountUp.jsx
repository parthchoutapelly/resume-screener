// src/components/ui/CountUp.jsx
// Precision numerical transitions for ATS metrics and match scores.
// Respects prefers-reduced-motion and guards against spurious polling re-renders.

import { useState, useEffect, useRef } from 'react';

export default function CountUp({
  value,
  duration = 400,
  decimals = 0,
  prefix = '',
  suffix = '',
  className = '',
  formatter,
}) {
  const numericTarget = typeof value === 'number' ? value : parseFloat(value);
  const isValidNumber = !Number.isNaN(numericTarget) && numericTarget !== null && value !== undefined && value !== '';

  const [currentVal, setCurrentVal] = useState(isValidNumber ? numericTarget : 0);
  const prevValueRef = useRef(isValidNumber ? numericTarget : null);
  const animFrameRef = useRef(null);

  useEffect(() => {
    if (!isValidNumber) {
      prevValueRef.current = null;
      return;
    }

    const prev = prevValueRef.current;
    prevValueRef.current = numericTarget;

    if (prev === null || prev === numericTarget) {
      return;
    }

    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion || duration <= 0) {
      animFrameRef.current = requestAnimationFrame(() => {
        setCurrentVal(numericTarget);
      });
      return;
    }

    const startVal = prev;
    const diff = numericTarget - startVal;
    let startTime = null;

    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 2);
      const current = startVal + diff * eased;

      if (progress < 1) {
        setCurrentVal(current);
        animFrameRef.current = requestAnimationFrame(step);
      } else {
        setCurrentVal(numericTarget);
      }
    };

    animFrameRef.current = requestAnimationFrame(step);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [numericTarget, isValidNumber, duration]);

  if (!isValidNumber) {
    return <span className={className}>{value ?? '—'}</span>;
  }

  let formatted = '';
  if (formatter && typeof formatter === 'function') {
    formatted = formatter(currentVal);
  } else if (decimals > 0) {
    formatted = Number(currentVal).toFixed(decimals);
  } else {
    formatted = Math.round(currentVal).toString();
  }

  return (
    <span className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
