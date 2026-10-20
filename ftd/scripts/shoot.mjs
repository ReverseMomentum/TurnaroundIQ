// QA screenshots: node scripts/shoot.mjs <outdir> [path ...]
import { chromium } from "playwright";

const [, , out, ...paths] = process.argv;
const base = process.env.BASE || "http://127.0.0.1:5173";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const views = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
for (const [vname, viewport] of Object.entries(views)) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("requestfailed", (r) => errors.push("failed " + r.url()));
  for (const p of paths.length ? paths : ["/"]) {
    await page.goto(base + p, { waitUntil: "networkidle" });
    // walk the page so lazy images load, then return to the top
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 400) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 60));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(2600);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const name = `${vname}${p.replace(/[^a-z0-9]+/gi, "_")}`;
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
    const wide = await page.evaluate(() =>
      [...document.querySelectorAll("body *")]
        .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
        .slice(0, 5)
        .map((el) => el.className || el.tagName),
    );
    console.log(name, "overflowX:", overflow, overflow > 0 ? wide : "");
  }
  if (errors.length) console.log(vname, "ERRORS:", errors);
}
await browser.close();
