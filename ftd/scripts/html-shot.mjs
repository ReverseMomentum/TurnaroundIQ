// Screenshots an HTML file at an exact pixel size: node scripts/html-shot.mjs in.html out.png width height
import { chromium } from "playwright";
import path from "node:path";

const [, , input, output, w, h] = process.argv;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
await page.goto("file://" + path.resolve(input), { waitUntil: "load" });
await page.screenshot({ path: output, clip: { x: 0, y: 0, width: +w, height: +h } });
await browser.close();
