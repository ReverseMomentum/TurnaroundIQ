// End-to-end checks of the interactive pieces against the dev server + API.
// node scripts/qa-flows.mjs <shot-dir>
import { chromium } from "playwright";

const out = process.argv[2];
const base = process.env.BASE || "http://127.0.0.1:5173";
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
const results = [];
const ok = (name, cond, extra = "") => results.push(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
const errors = [];

async function page(viewport = { width: 1440, height: 900 }) {
  const p = await browser.newPage({ viewport });
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => m.type() === "error" && !/503|ERR_FAILED/.test(m.text()) && errors.push(m.text()));
  return p;
}

const email = `qa+${Date.now()}@example.com`;
{
  const p = await page();
  await p.goto(base + "/", { waitUntil: "networkidle" });
  const form = p.locator("#waitlist form");
  await form.locator("button[type=submit]").click();
  ok("empty email shows inline error", (await form.locator(".waitlist-form__msg").textContent()).includes("Enter your email"));
  await form.locator("input[type=email]").fill("not-an-email");
  await form.locator("button[type=submit]").click();
  ok("malformed email rejected client-side", (await form.locator(".waitlist-form__msg").textContent()).includes("doesn't look right"));
  ok("invalid field is aria-invalid", (await form.locator("input[type=email]").getAttribute("aria-invalid")) === "true");
  await form.locator("input[type=email]").fill(email);
  await form.locator("button[type=submit]").click();
  await p.waitForSelector("#waitlist .waitlist-form--done");
  ok("valid email -> success state", (await p.locator("#waitlist .waitlist-form__done-title").textContent()).includes("on the list"));
  await p.locator("#waitlist").screenshot({ path: `${out}/flow-success.png` });

  await p.goto(base + "/", { waitUntil: "networkidle" });
  await p.fill("#waitlist input[type=email]", email.toUpperCase());
  await p.click("#waitlist button[type=submit]");
  await p.waitForSelector("#waitlist .waitlist-form--done");
  ok("duplicate (case-insensitive) -> 'already on the list'", (await p.locator("#waitlist .waitlist-form__done-title").textContent()).includes("Already"));

  // server failure must not show success
  await p.goto(base + "/", { waitUntil: "networkidle" });
  await p.route("**/api/waitlist", (r) => r.fulfill({ status: 503, contentType: "text/html", body: "<h1>down</h1>" }));
  await p.fill("#waitlist input[type=email]", "someone@example.com");
  await p.click("#waitlist button[type=submit]");
  await p.waitForSelector("#waitlist .waitlist-form__msg.is-error");
  ok("API 503 -> error, no success", (await p.locator("#waitlist .waitlist-form--done").count()) === 0,
    await p.locator("#waitlist .waitlist-form__msg").textContent());
  await p.locator("#waitlist").screenshot({ path: `${out}/flow-error.png` });

  // slow server -> visible pending state
  await p.unroute("**/api/waitlist");
  await p.route("**/api/waitlist", async (r) => { await new Promise((s) => setTimeout(s, 1500)); r.abort(); });
  await p.fill("#waitlist input[type=email]", "slow@example.com");
  await p.click("#waitlist button[type=submit]");
  await p.waitForTimeout(300);
  ok("pending: form aria-busy + disabled submit", (await p.locator("#waitlist form").getAttribute("aria-busy")) === "true" &&
    (await p.locator("#waitlist button[type=submit]").isDisabled()));
  await p.waitForSelector("#waitlist .waitlist-form__msg.is-error");
  ok("network failure -> connection error", (await p.locator("#waitlist .waitlist-form__msg").textContent()).includes("Couldn't reach"));
  await p.close();
}

{
  const p = await page();
  await p.goto(base + "/shop/crossbone-zip-hoodie", { waitUntil: "networkidle" });
  ok("product title", (await p.title()).startsWith("Crossbone Zip Hoodie"));
  const thumbs = p.locator(".gallery__thumb");
  await thumbs.nth(1).click();
  ok("thumbnail switches main image", (await p.locator(".gallery__image").getAttribute("src")).includes("hoodie-back"));
  await thumbs.nth(1).focus();
  await p.keyboard.press("ArrowRight");
  ok("arrow keys move through thumbnails", (await p.locator(".gallery__image").getAttribute("src")).includes("detail-back"));

  await p.click("text=Notify me at drop");
  ok("notify without size asks for a size", (await p.locator(".sizes__error").count()) === 1);
  await p.click(".sizes__option:has-text('XL') >> nth=0");
  await p.locator(".sizes__option", { hasText: /^L$/ }).click();
  ok("size selection reflected in legend", (await p.locator(".sizes__chosen").textContent()).includes("L"));
  await p.click("text=Size guide");
  ok("size guide dialog opens", await p.locator("dialog.size-guide").evaluate((d) => d.open));
  await p.screenshot({ path: `${out}/flow-sizeguide.png` });
  await p.keyboard.press("Escape");
  ok("Escape closes size guide", !(await p.locator("dialog.size-guide").evaluate((d) => d.open)));

  await p.click("text=Notify me at drop");
  const nf = p.locator(".pdp__notify");
  ok("notify opens inline form with size", (await nf.locator(".label").textContent()).includes("size L"));
  ok("notify form email focused", await nf.locator("input[type=email]").evaluate((el) => el === document.activeElement));
  await nf.locator("input[type=email]").fill(`qa-notify+${Date.now()}@example.com`);
  const req = p.waitForRequest("**/api/waitlist");
  await nf.locator("button[type=submit]").click();
  const body = JSON.parse((await req).postData());
  ok("notify posts product + size", body.product === "crossbone-zip-hoodie" && body.size === "L" && body.source === "product");
  await p.waitForSelector(".pdp__notify .waitlist-form--done");
  ok("notify success copy mentions size", (await nf.textContent()).includes("size L noted"));
  await p.locator(".pdp__info").screenshot({ path: `${out}/flow-notify.png` });

  await p.click(".others .card__link >> nth=0");
  await p.waitForURL("**/shop/crossbone-baggy-pants");
  await p.locator("h1", { hasText: "Baggy Pants" }).waitFor({ timeout: 3000 }).catch(() => {});
  ok("other-piece card navigates", (await p.locator("h1").textContent()).includes("Baggy Pants"),
    await p.locator("h1").textContent());
  ok("single-image product hides thumbnails", (await p.locator(".gallery__thumb").count()) === 0);
  await p.goto(base + "/shop/nope", { waitUntil: "networkidle" });
  ok("unknown product -> 404 page", (await p.locator("h1").textContent()).includes("Nothing here"));
  await p.close();
}

{
  const p = await page({ width: 390, height: 844 });
  await p.goto(base + "/shop/crossbone-zip-hoodie", { waitUntil: "networkidle" });
  await p.click(".menu-toggle");
  ok("mobile menu opens", await p.locator("#mobile-menu").isVisible());
  await p.screenshot({ path: `${out}/flow-menu.png` });
  await p.click("#mobile-menu >> text=Join waitlist");
  await p.waitForURL("**/#waitlist");
  await p.waitForTimeout(900);
  ok("menu link -> landing #waitlist, menu closed, email focused",
    !(await p.locator("#mobile-menu").isVisible()) &&
      (await p.locator("#waitlist input[type=email]").evaluate((el) => el === document.activeElement)));
  const small = await p.evaluate(() =>
    [...document.querySelectorAll("a, button, input, .sizes__option")]
      .filter((el) => el.offsetParent && !el.closest(".hp") && !el.classList.contains("skip-link"))
      .map((el) => [el.textContent.trim().slice(0, 20) || el.className, Math.round(el.getBoundingClientRect().height)])
      .filter(([, h]) => h < 32));
  ok("mobile tap targets >= 32px tall on landing", small.length === 0, JSON.stringify(small));
  await p.close();
}

{
  const p = await page();
  await p.goto(base + "/", { waitUntil: "networkidle" });
  await p.keyboard.press("Tab");
  ok("first Tab reaches skip link", (await p.evaluate(() => document.activeElement.className)) === "skip-link");
  await p.close();
}

console.log(results.join("\n"));
console.log(errors.length ? "PAGE ERRORS: " + JSON.stringify(errors) : "no page errors");
await browser.close();
