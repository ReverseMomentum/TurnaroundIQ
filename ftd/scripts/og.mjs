// Renders public/og.jpg (1200x630 share card): node scripts/og.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(".");
const font = (f) => `file://${root}/node_modules/@fontsource/${f}`;
const html = `<html><head><style>
@font-face{font-family:S;src:url("${font("grenze/files/grenze-latin-600-normal.woff2")}")}
body{margin:0;width:1200px;height:630px;background:#0A0807;overflow:hidden;font-family:S;color:#9C3A22;text-transform:uppercase}
.art{position:absolute;right:60px;top:0;height:630px}
.s{position:absolute;left:80px;top:150px;font-size:46px;line-height:1.12;letter-spacing:.06em}
.d{position:absolute;left:84px;top:430px;letter-spacing:.2em;font-size:20px;color:#E6DCC9}
.g{position:absolute;inset:0;background:url("file://${root}/public/art/grain.png");opacity:.05}
</style></head><body>
<img class="art" src="file://${root}/public/art/hero.webp">
<div class="s">Something<br>beautiful<br>dies<br>in you.</div><div class="d">Drop 01 — join the waitlist</div><div class="g"></div>
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
