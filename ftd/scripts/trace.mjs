// Traces a black-on-white bitmap to a single-path SVG: node scripts/trace.mjs in.png out.svg [turdSize]
import potrace from "potrace";
import fs from "node:fs";

const [, , input, output, turd = "4"] = process.argv;
potrace.trace(input, { threshold: 128, turdSize: +turd, optTolerance: 0.2, alphaMax: 1 }, (err, svg) => {
  if (err) throw err;
  fs.writeFileSync(output, svg);
});
