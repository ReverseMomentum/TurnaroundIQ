import { useState } from "react";

// Main image with a thumbnail strip. Thumbnails are a single-select button
// group; arrow keys move between them.
export default function ProductGallery({ images, name }) {
  const [active, setActive] = useState(0);
  const current = images[active];
  const many = images.length > 1;

  function onKeyDown(e) {
    if (!many) return;
    const delta = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (!delta) return;
    e.preventDefault();
    const next = (active + delta + images.length) % images.length;
    setActive(next);
    e.currentTarget.querySelectorAll("button")[next]?.focus();
  }

  return (
    <div className={`gallery ${many ? "" : "gallery--single"}`}>
      {many && (
        <div className="gallery__thumbs" role="group" aria-label={`${name} images`} onKeyDown={onKeyDown}>
          {images.map((img, i) => (
            <button
              key={img.src}
              type="button"
              className="gallery__thumb"
              aria-pressed={i === active}
              aria-label={`Show ${img.label.toLowerCase()} view`}
              tabIndex={i === active ? 0 : -1}
              onClick={() => setActive(i)}
            >
              <img src={img.thumb} alt="" width="400" height="440" loading="lazy" decoding="async" />
            </button>
          ))}
        </div>
      )}
      <figure className="gallery__main">
        <img key={current.src} className="gallery__image" src={current.src} alt={current.alt} width="1000" height="1100" decoding="async" />
        <figcaption className="gallery__caption">
          <span>{current.label}</span>
          {many && (
            <span>
              {String(active + 1).padStart(2, "0")} / {String(images.length).padStart(2, "0")}
            </span>
          )}
        </figcaption>
      </figure>
    </div>
  );
}
