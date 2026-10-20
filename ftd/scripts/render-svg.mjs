// Rasterises an SVG with Chromium: node scripts/render-svg.mjs in.svg out.png width height
// The brand fonts are loaded from node_modules so SVG <text> renders in Pirata One / IBM Plex Mono.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const [, , input, output, w, h] = process.argv;
const fonts = path.resolve("node_modules/@fontsource");
const css = `
@font-face{font-family:"Pirata One";src:url("file://${fonts}/pirata-one/files/pirata-one-latin-400-normal.woff2")}
@font-face{font-family:"IBM Plex Mono";src:url("file://${fonts}/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2")}
@font-face{font-family:"Barlow Condensed";src:url("file://${fonts}/barlow-condensed/files/barlow-condensed-latin-600-normal.woff2")}`;
const html = input.replace(/\.svg$/, ".html");
fs.writeFileSync(html, `<html><head><style>${css}</style></head><body style="margin:0;background:#000">${fs.readFileSync(input, "utf8")}</body></html>`);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
await page.goto("file://" + path.resolve(html));
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: output, clip: { x: 0, y: 0, width: +w, height: +h } });
await browser.close();
