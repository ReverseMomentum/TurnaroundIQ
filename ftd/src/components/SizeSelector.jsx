import { useId } from "react";

// Native radio inputs styled as a size grid: arrow-key navigation and form
// semantics come for free.
export default function SizeSelector({ sizes, value, onChange, error }) {
  const id = useId();
  return (
    <fieldset className={`sizes ${error ? "is-invalid" : ""}`} aria-describedby={error ? `${id}-err` : undefined}>
      <legend className="label">
        Size{value ? <span className="sizes__chosen"> — {value}</span> : null}
      </legend>
      <div className="sizes__grid">
        {sizes.map((s) => (
          <label key={s} className="sizes__option">
            <input type="radio" name={`${id}-size`} value={s} checked={value === s} onChange={() => onChange(s)} />
            <span>{s}</span>
          </label>
        ))}
      </div>
      {error && (
        <p id={`${id}-err`} className="sizes__error" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
