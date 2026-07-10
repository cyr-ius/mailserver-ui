#!/usr/bin/env node
/**
 * Drive the Mailserver UI SPA: sign in, navigate, click, screenshot, report.
 *
 * The app is behind a login wall, so every run authenticates as the admin
 * account launch.sh seeded. Reads its base URL and password from $MSUI_RUN_DIR.
 *
 *   node driver.mjs --route /dashboard --screenshot /tmp/d.png --dump
 *   node driver.mjs --route /mailboxes --click 'button:has-text("Refresh")' --theme dark
 *   node driver.mjs --route /dashboard --assert-loaded   # exit 1 if a tile is stuck
 *
 * Exit codes: 0 ok, 1 an assertion failed, 2 bad usage / could not launch.
 */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const RUN_DIR = process.env.MSUI_RUN_DIR || "/tmp/mailserver-ui-run";

// Playwright is not a project dependency — it is installed into the run dir
// (see SKILL.md). ESM ignores NODE_PATH, so resolve the entry point by hand.
const playwrightPaths = [
  join(RUN_DIR, "node_modules/playwright/index.js"),
  resolve(process.cwd(), "node_modules/playwright/index.js"),
];
const playwrightPath = playwrightPaths.find(existsSync);
if (!playwrightPath) {
  console.error(`playwright not found. Install it:\n  (cd ${RUN_DIR} && npm install playwright)`);
  process.exit(2);
}
// playwright ships CommonJS: importing it by path puts its exports on `default`.
const playwright = await import(pathToFileURL(playwrightPath).href);
const chromium = playwright.chromium ?? playwright.default?.chromium;
if (!chromium) {
  console.error(`playwright at ${playwrightPath} exposes no chromium export`);
  process.exit(2);
}

// ── Arguments ────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const clicks = [];
const flag = (name, fallback = null) => {
  const i = argv.indexOf(name);
  return i === -1 ? fallback : argv[i + 1];
};
const has = (name) => argv.includes(name);
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--click") clicks.push(argv[i + 1]);
}

const route = flag("--route", "/dashboard");
const screenshot = flag("--screenshot");
const theme = flag("--theme");
const settleMs = Number(flag("--settle", "2000"));

const readState = (file, envVar) => {
  if (process.env[envVar]) return process.env[envVar];
  const path = join(RUN_DIR, file);
  if (!existsSync(path)) {
    console.error(`missing ${path} — run launch.sh start first`);
    process.exit(2);
  }
  return readFileSync(path, "utf8").trim();
};

const password = readState("password", "MSUI_PASSWORD");
const base =
  process.env.MSUI_BASE || (readState("env", "__none").match(/MSUI_BASE=(\S+)/) || [])[1] || "http://127.0.0.1:4210";

// ── Drive ────────────────────────────────────────────────────────────────────
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });

const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(`PAGEERROR: ${e.message}`));

await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill('input#username, input[name="username"]', "admin");
await page.fill('input[type="password"]', password);
await page.click('button[type="submit"]');
await page.waitForURL("**/dashboard", { timeout: 20000 });

if (route !== "/dashboard") {
  // Let the dashboard settle first. Navigating while its tiles are still
  // fetching aborts those requests, and each aborted tile logs an error that
  // looks exactly like a real failure.
  await page.waitForLoadState("networkidle");
  await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
  consoleErrors.length = 0;
}

// Tiles fan out to many endpoints, several shelling into the container.
await page.waitForLoadState("networkidle");
await page.waitForTimeout(settleMs);

for (const selector of clicks) {
  await page.click(selector);
  await page.waitForTimeout(settleMs);
  console.log(`clicked: ${selector}`);
}

if (theme === "dark" || theme === "light") {
  await page.evaluate((t) => document.documentElement.setAttribute("data-bs-theme", t), theme);
  await page.waitForTimeout(400);
}

// The shell wraps the routed page in `main.app-main`, and every page opens with
// its own <main> (`.container-fluid` on the dashboard, `.container` elsewhere).
// Target the inner one so shell chrome never counts as page content.
const content = page.locator("main.app-main main");

if (has("--dump")) {
  console.log("───── PAGE TEXT ─────");
  console.log(await content.innerText());
}

const cards = await content.locator(".card").count();
const placeholders = await content.locator(".placeholder").count();
const errorText = (await content.locator(".text-danger").allInnerTexts())
  .map((t) => t.replace(/\s+/g, " ").trim())
  .filter(Boolean);

console.log("───── STATE ─────");
console.log(`route: ${route}`);
console.log(`cards: ${cards}`);
console.log(`loading placeholders: ${placeholders}`);
console.log(`red text: ${JSON.stringify(errorText)}`);
console.log(`console errors: ${consoleErrors.length ? JSON.stringify(consoleErrors) : "none"}`);

if (screenshot) {
  await page.screenshot({ path: screenshot, fullPage: true });
  console.log(`screenshot: ${screenshot}`);
}

await browser.close();

// --assert-loaded: a tile still showing its skeleton means a request never
// resolved. Red text is legitimate (a tile reporting its own failure).
if (has("--assert-loaded") && placeholders > 0) {
  console.error(`FAIL: ${placeholders} placeholder(s) still loading`);
  process.exit(1);
}
if (has("--assert-no-console-errors") && consoleErrors.length) {
  console.error("FAIL: console errors present");
  process.exit(1);
}
