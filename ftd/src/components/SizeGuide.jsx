import { useEffect, useRef } from "react";
import { SIZE_GUIDE } from "../data/products.js";

// Modal size chart built on <dialog>, which handles focus trapping and Escape.
export default function SizeGuide({ open, onClose, fit }) {
  const ref = useRef(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="size-guide"
      aria-labelledby="size-guide-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className="size-guide__inner">
        <header className="size-guide__head">
          <h2 id="size-guide-title" className="label">Size guide</h2>
          <button type="button" className="size-guide__close" onClick={onClose}>
            Close <span aria-hidden="true">×</span>
          </button>
        </header>
        <table className="size-guide__table">
          <caption className="visually-hidden">Garment measurements in centimetres, measured flat</caption>
          <thead>
            <tr>
              {SIZE_GUIDE.columns.map((c) => (
                <th key={c} scope="col">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SIZE_GUIDE.rows.map(([size, ...cells]) => (
              <tr key={size}>
                <th scope="row">{size}</th>
                {cells.map((v, i) => (
                  <td key={i}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="size-guide__note">Centimetres, measured flat. Chest is pit to pit; length is shoulder to hem.</p>
        {fit && <p className="size-guide__note">{fit}</p>}
        <p className="size-guide__note size-guide__note--flag">Indicative measurements. Final grading is published at release.</p>
      </div>
    </dialog>
  );
}
