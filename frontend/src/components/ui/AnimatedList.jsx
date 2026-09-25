// src/components/ui/AnimatedList.jsx
// Semantic table row and list item entrance animations for dense candidate/job lists.
// Respects semantic table structure, preserves stable keys, and guards against repeated polling animations.

import { useState, useEffect } from 'react';

export function AnimatedRow({ children, className = '', index = 0, ...restProps }) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setEntered(true);
    }, Math.min(index * 15, 80));

    return () => clearTimeout(timer);
  }, [index]);

  return (
    <tr
      className={`animated-table-row ${entered ? 'animated-table-row--entered' : ''} ${className}`}
      {...restProps}
    >
      {children}
    </tr>
  );
}

export function AnimatedItem({
  children,
  className = '',
  index = 0,
  as: Component = 'div',
  ...restProps
}) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setEntered(true);
    }, Math.min(index * 20, 100));

    return () => clearTimeout(timer);
  }, [index]);

  return (
    <Component
      className={`animated-item ${entered ? 'animated-item--entered' : ''} ${className}`}
      {...restProps}
    >
      {children}
    </Component>
  );
}
