// P10.3: real dashboard-load timing against a live FastAPI+PostgreSQL+
// dashboard stack, driven by an actual Chrome browser (Playwright) -- not
// synthetic, not a Lighthouse estimate. Each stage is timed end-to-end as
// a user would experience it: navigation/click to the moment the target
// content is actually visible on screen (includes network round trip,
// server processing and React render, not just "the HTML arrived").
//
// Complements tools/perf_report.py (raw backend HTTP latency, no browser)
// -- this file is the dashboard-browser gap that file's docstring
// explicitly excludes. See docs/perf.md for how these two are combined
// and labelled.
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.PERF_DASHBOARD_URL ?? "http://127.0.0.1:18473";
const api = process.env.PERF_API_URL ?? "http://127.0.0.1:18400";
const email = process.env.PERF_ASSESSOR_EMAIL ?? "p10-perf-fix@parakh.test";
const password = process.env.PERF_ASSESSOR_PASSWORD ?? "p10-perf-fix-test-only";
const repeat = Number(process.env.PERF_REPEAT ?? "10");
const outPath = process.env.PERF_OUT ?? "/tmp/perf-dashboard.json";

function percentile(sorted, p) {
  const idx = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, idx)];
}

function summarize(name, samplesMs) {
  if (samplesMs.length === 0) {
    return { scenario: name, status: "failed", observations: 0, median_ms: null, p95_ms: null, min_ms: null, max_ms: null };
  }
  const sorted = [...samplesMs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  return {
    scenario: name,
    status: "ok",
    observations: samplesMs.length,
    median_ms: Math.round(median * 100) / 100,
    p95_ms: Math.round(percentile(sorted, 95) * 100) / 100,
    min_ms: Math.round(sorted[0] * 100) / 100,
    max_ms: Math.round(sorted[sorted.length - 1] * 100) / 100,
    provenance: "real Playwright/Chrome timing against a live dashboard + backend",
  };
}

async function findAnAssessmentId() {
  const loginRes = await fetch(`${api}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(loginRes.status, 200, "setup: perf assessor login failed");
  const { access_token } = await loginRes.json();
  const queueRes = await fetch(`${api}/queue`, { headers: { Authorization: `Bearer ${access_token}` } });
  const queue = await queueRes.json();
  assert(queue.length > 0, "setup: queue is empty -- seed demo data first (python -m app.seed)");
  return queue[0].id;
}

const assessmentId = await findAnAssessmentId();
const browser = await chromium.launch({
  headless: true,
  ...(process.env.P8_CHROME ? { executablePath: process.env.P8_CHROME } : { channel: "chrome" }),
});

const results = [];
try {
  // ---- login_page_load: fresh navigation to the login form being visible ----
  const loginPageLoadMs = [];
  for (let i = 0; i < repeat; i++) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const start = Date.now();
    await page.goto(`${base}/#/queue`);
    await page.getByRole("heading", { name: /Assessor Login/i }).waitFor();
    loginPageLoadMs.push(Date.now() - start);
    await context.close();
  }
  results.push(summarize("login_page_load", loginPageLoadMs));

  // ---- login_submit_to_queue_visible: click Sign in -> queue content rendered ----
  const loginToQueueMs = [];
  for (let i = 0; i < repeat; i++) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${base}/#/queue`);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    const start = Date.now();
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();
    await page.locator("tbody tr").first().waitFor();
    loginToQueueMs.push(Date.now() - start);
    await context.close();
  }
  results.push(summarize("login_submit_to_queue_visible", loginToQueueMs));

  // ---- queue_reload: already-authenticated reload -> queue content rendered ----
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${base}/#/queue`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();

  const queueReloadMs = [];
  for (let i = 0; i < repeat; i++) {
    const start = Date.now();
    await page.reload();
    await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();
    await page.locator("tbody tr").first().waitFor();
    queueReloadMs.push(Date.now() - start);
  }
  results.push(summarize("queue_reload_authenticated", queueReloadMs));

  // ---- assessment_detail_load: navigate to a real assessment's detail page ----
  const detailLoadMs = [];
  for (let i = 0; i < repeat; i++) {
    const start = Date.now();
    await page.goto(`${base}/#/assessments/${assessmentId}`);
    await page.locator("h1, h2").first().waitFor();
    await page.locator(".card").first().waitFor();
    detailLoadMs.push(Date.now() - start);
  }
  results.push(summarize("assessment_detail_load", detailLoadMs));

  await context.close();
} finally {
  await browser.close();
}

const report = {
  provenance: {
    base_url: base,
    api_url: api,
    measurement_kind: "real browser (Playwright/Chrome) wall-clock timing; not synthetic, not a Lighthouse score",
  },
  results,
};
writeFileSync(outPath, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
