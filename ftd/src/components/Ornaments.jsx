// Small engraved ornaments used as punctuation in the layout. Decorative only.

// Compass star with long, hairline cardinal rays.
export function Star({ className = "", size = 28, long = false }) {
  const r = long ? 50 : 24;
  return (
    <svg className={`ornament ${className}`} width={size} height={size} viewBox="-50 -50 100 100" aria-hidden="true">
      <path
        d={`M0,-${r} L3,-6 L6,-6 L5,-3 L${r},0 L5,3 L6,6 L3,6 L0,${r} L-3,6 L-6,6 L-5,3 L-${r},0 L-5,-3 L-6,-6 L-3,-6 Z`}
        fill="currentColor"
      />
      <path d="M0,-14 L2,-2 L14,0 L2,2 L0,14 L-2,2 L-14,0 L-2,-2 Z" fill="currentColor" transform="rotate(45)" />
      <circle r="2.4" fill="var(--ink)" />
    </svg>
  );
}

// A tall thorned cross with a star at the crossing, used to flank compositions.
export function CrossStar({ className = "", height = 160 }) {
  return (
    <svg className={`ornament ${className}`} width={height * 0.36} height={height} viewBox="-18 -10 36 100" aria-hidden="true">
      <path d="M-0.8,-10 L0.8,-10 L1.2,88 L0,90 L-1.2,88 Z" fill="currentColor" />
      <path d="M-14,16 L14,16 L14,17.4 L-14,17.4 Z" fill="currentColor" />
      <path d="M0,4 L1.6,14.6 L12,16.7 L1.6,18.8 L0,30 L-1.6,18.8 L-12,16.7 L-1.6,14.6 Z" fill="currentColor" />
      {[40, 52, 64, 76].map((y, i) => (
        <path key={y} d={i % 2 ? `M1,${y} L6,${y - 3} L1,${y + 2} Z` : `M-1,${y} L-6,${y - 3} L-1,${y + 2} Z`} fill="currentColor" />
      ))}
    </svg>
  );
}

// Hairline rule with a centred star, for section breaks.
export function Rule({ label, className = "" }) {
  return (
    <div className={`rule ${className}`} role={label ? undefined : "presentation"}>
      <span className="rule__line" />
      {label ? <span className="rule__label">{label}</span> : <Star size={22} />}
      <span className="rule__line" />
    </div>
  );
}
