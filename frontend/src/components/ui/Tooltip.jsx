// src/components/ui/Tooltip.jsx
// Centralized accessible tooltip for workbench actions, status badges, and compact controls.
// Supports hover, keyboard focus, Escape dismissal, and respects prefers-reduced-motion.

import { useState, useRef, useEffect, useId, cloneElement, isValidElement } from 'react';

export default function Tooltip({
  content,
  children,
  position = 'top',
  delay = 120,
  disabled = false,
  className = '',
}) {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef(null);
  const tooltipId = useId();

  const showTooltip = () => {
    if (disabled || !content) return;
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  };

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsVisible(false);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!isVisible) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        hideTooltip();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isVisible]);

  if (!content || disabled) {
    return children;
  }

  // If children is a valid React element, attach props or wrap cleanly
  const childElement = isValidElement(children) ? (
    cloneElement(children, {
      'aria-describedby': isVisible ? tooltipId : undefined,
    })
  ) : (
    <span>{children}</span>
  );

  return (
    <span
      className={`tooltip-wrapper ${className}`}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
      style={{ display: 'inline-flex', position: 'relative', verticalAlign: 'middle' }}
    >
      {childElement}
      {isVisible && (
        <span
          id={tooltipId}
          role="tooltip"
          className={`tooltip-bubble tooltip-bubble--${position}`}
          aria-hidden={!isVisible}
        >
          {content}
        </span>
      )}
    </span>
  );
}
