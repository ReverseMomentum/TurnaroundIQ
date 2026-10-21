// Renders an HTML file to a vector PDF at its own @page size: node scripts/label-pdf.mjs in.html out.pdf
import { chromium } from "playwright";
import path from "node:path";

const [, , input, output] = process.argv;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const page = await browser.newPage();
await page.goto("file://" + path.resolve(input), { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await page.pdf({ path: output, preferCSSPageSize: true, printBackground: true });
await browser.close();
