// Renders public/og.jpg (1200x630 share card): node scripts/og.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { LOGO_PATH, LOGO_VIEWBOX } from "../src/components/logoPath.js";

const root = path.resolve(".");
const font = (f) => `file://${root}/node_modules/@fontsource/${f}`;
const html = `<html><head><style>
@font-face{font-family:B;src:url("${font("barlow-condensed/files/barlow-condensed-latin-600-normal.woff2")}")}
body{margin:0;width:1200px;height:630px;background:#0A0807;overflow:hidden;font-family:B;color:#D8782B}
.art{position:absolute;right:40px;top:-40px;width:560px}
.l{position:absolute;left:80px;top:150px;width:520px}
.t{position:absolute;left:84px;top:430px;letter-spacing:.32em;font-size:30px;text-transform:uppercase}
.d{position:absolute;left:86px;top:490px;letter-spacing:.32em;font-size:18px;color:#E6DCC9;text-transform:uppercase}
.g{position:absolute;inset:0;background:url("file://${root}/public/art/grain.png");opacity:.05}
</style></head><body>
<img class="art" src="file://${root}/public/art/hero-skull.webp">
<svg class="l" viewBox="${LOGO_VIEWBOX}"><path d="${LOGO_PATH}" fill="#D8782B" fill-rule="evenodd" stroke="#0A0807" stroke-width="40" paint-order="stroke"/></svg>
<div class="t">“Forsaken to decay”</div><div class="d">Drop 01 — join the waitlist</div><div class="g"></div>
</body></html>`;
fs.mkdirSync("art/_build", { recursive: true });
fs.writeFileSync("art/_build/og.html", html);
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
await p.goto("file://" + root + "/art/_build/og.html");
await p.evaluate(() => document.fonts.ready);
await p.screenshot({ path: "public/og.jpg", type: "jpeg", quality: 86 });
await b.close();
console.log("wrote public/og.jpg");
