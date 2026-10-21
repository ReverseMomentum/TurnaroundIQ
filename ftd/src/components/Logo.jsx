import { LOGO_PATH, LOGO_VIEWBOX } from "./logoPath.js";

// The FTD wordmark, traced from the supplied artwork.
// `outlined` adds a near-black keyline so the mark can sit over illustration.
export default function Logo({ className = "", title = "FTD", outlined = false, distressed = false }) {
  const cls = ["logo", outlined && "logo--outlined", distressed && "ink-worn", className].filter(Boolean).join(" ");
  return (
    <svg className={cls} viewBox={LOGO_VIEWBOX} role="img" aria-label={title} focusable="false">
      <path d={LOGO_PATH} fillRule="evenodd" />
    </svg>
  );
}
