import { useId } from "react";

// Colourway picker: native radios rendered as swatches, like SizeSelector.
export default function ColourSelector({ colours, value, onChange }) {
  const id = useId();
  const current = colours.find((c) => c.id === value);
  return (
    <fieldset className="colours">
      <legend className="label">
        Colour<span className="sizes__chosen"> — {current?.name}</span>
      </legend>
      <div className="colours__row">
        {colours.map((c) => (
          <label key={c.id} className="colours__option">
            <input type="radio" name={`${id}-colour`} value={c.id} checked={value === c.id} onChange={() => onChange(c.id)} />
            <span className="colours__swatch" style={{ "--swatch": c.swatch }} aria-hidden="true" />
            <span className="colours__name">{c.name}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
