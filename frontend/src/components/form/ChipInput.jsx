// src/components/form/ChipInput.jsx
// Accessible chip/tag input. Enter or comma adds a chip, Backspace removes the last one.
// Per Design.md §4.3 and 04-frontend-dashboard.md §8.
import { useState, useRef } from 'react';

export default function ChipInput({
  id,
  label,
  chips = [],
  onAdd,
  onRemove,
  placeholder = 'Type and press Enter',
  helpText,
  onNormalize,  // optional: (value) => normalized string
  'aria-required': ariaRequired,
}) {
  const [input, setInput] = useState('');
  const inputRef = useRef(null);

  const addChip = (raw) => {
    const normalized = onNormalize ? onNormalize(raw.trim()) : raw.trim().toLowerCase();
    if (!normalized) return;
    if (!chips.includes(normalized)) {
      onAdd(normalized);
    }
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addChip(input);
    } else if (e.key === 'Backspace' && !input && chips.length > 0) {
      onRemove(chips[chips.length - 1]);
    }
  };

  const handleBlur = () => {
    if (input.trim()) addChip(input);
  };

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>{label}</label>
      {helpText && <span className="field__help" id={`${id}-help`}>{helpText}</span>}
      <div
        className="chip-input"
        onClick={() => inputRef.current?.focus()}
        role="group"
        aria-labelledby={`${id}-label`}
      >
        {chips.map((chip) => (
          <span key={chip} className="chip chip--input">
            {chip}
            <button
              type="button"
              className="chip__remove"
              onClick={() => onRemove(chip)}
              aria-label={`Remove ${chip}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={id}
          ref={inputRef}
          type="text"
          className="chip-input__text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          placeholder={chips.length === 0 ? placeholder : ''}
          aria-describedby={helpText ? `${id}-help` : undefined}
          aria-required={ariaRequired}
          autoComplete="off"
        />
      </div>
    </div>
  );
}
