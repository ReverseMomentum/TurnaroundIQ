// Renders an HTML file to PDF with Chromium (A4, per the page's @page rule),
// and a PNG preview of each page: node scripts/html-to-pdf.mjs in.html out.pdf
import { chromium } from "playwright";
import path from "node:path";

const [, , input, output] = process.argv;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const page = await browser.newPage();
await page.goto("file://" + path.resolve(input), { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await page.pdf({ path: output, preferCSSPageSize: true, printBackground: true });
// previews for checking: one PNG per page
await page.setViewportSize({ width: 1123, height: 794 });
const n = await page.locator("section.page").count();
for (let i = 0; i < n; i++) {
  await page.locator("section.page").nth(i).screenshot({ path: input.replace(/\.html$/, `-p${i + 1}.png`) });
}
await browser.close();
