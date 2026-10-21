// Thorned bramble corners framing the page, after the corner work on printed gig
// posters: a tapered stem along each edge and one into the corner, with thorns and
// tendrils. Drawn once for the top-left corner; the other three are CSS mirrors.
const STEMS = [
  "M1,1 C34,3 70,0 124,8 C70,3 34,5 1,4.5 Z", // along the top edge
  "M1,1 C3,34 0,70 8,124 C3,70 5,34 4.5,1 Z", // down the side edge
  "M1,1 C13,11 24,20 42,38 C23,23 12,14 2.5,4.5 Z", // into the corner, kept short to clear the nav
  "M27,3 C33,9 35,15 34,25 C32,17 29,11 25,5 Z", // short offshoots
  "M3,27 C9,33 15,35 25,34 C17,32 11,29 5,25 Z",
];
const THORNS = [
  "M16,3.5 L21,11 L20,3.5 Z", "M40,3 L43,-2 L45,3 Z", "M58,3 L64,9 L62,3.5 Z", "M80,4 L83,-1 L85,4.5 Z",
  "M97,5 L102,11 L101,5.5 Z", "M113,7 L116,2 L118,7.5 Z",
  "M3.5,16 L11,21 L3.5,20 Z", "M3,40 L-2,43 L3,45 Z", "M3,58 L9,64 L3.5,62 Z", "M4,80 L-1,83 L4.5,85 Z",
  "M5,97 L11,102 L5.5,101 Z", "M7,113 L2,116 L7.5,118 Z",
  "M15,13 L16,6 L19,15 Z", "M13,15 L6,16 L15,19 Z", "M29,26 L31,19 L33,28 Z", "M26,29 L19,31 L28,33 Z",
];
const TENDRILS = [
  "M50,3.5 c5,6 2,13 -4,11 c-3,-1 -2,-5 1,-5",
  "M3.5,50 c6,5 13,2 11,-4 c-1,-3 -5,-2 -5,1",
  "M88,5 c3,4 1,8 -3,7",
  "M5,88 c4,3 8,1 7,-3",
];

function Corner({ className }) {
  return (
    <svg className={`corner ${className}`} viewBox="-4 -4 132 132" aria-hidden="true" focusable="false">
      <g className="corner__ink">
        {STEMS.map((d) => <path key={d} d={d} />)}
        {THORNS.map((d) => <path key={d} d={d} />)}
      </g>
      <g className="corner__line">
        {TENDRILS.map((d) => <path key={d} d={d} />)}
      </g>
    </svg>
  );
}

export default function PageCorners() {
  return (
    <div className="page-corners" aria-hidden="true">
      <Corner className="corner--tl" />
      <Corner className="corner--tr" />
      <Corner className="corner--bl" />
      <Corner className="corner--br" />
    </div>
  );
}
