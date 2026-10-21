// Traces the supplied FTD wordmark (art/ftd-logo-source.jpg) into a single-path SVG.
// Run once: node scripts/trace-logo.mjs  -> src/components/logoPath.js
import potrace from "potrace";
import fs from "node:fs";

potrace.trace("art/_logo_bw.png", { threshold: 128, turdSize: 40, optTolerance: 0.4 }, (err, svg) => {
  if (err) throw err;
  const d = svg.match(/ d="([^"]+)"/)[1];
  const [w, h] = svg.match(/viewBox="0 0 (\d+) (\d+)"/).slice(1).map(Number);
  fs.writeFileSync("art/_logo_traced.svg", svg);
  fs.writeFileSync("src/_logo_raw.json", JSON.stringify({ d, w, h }));
  console.log(w, h, d.length);
});
