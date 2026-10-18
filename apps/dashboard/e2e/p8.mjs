// Actual product pages + persisted signed snapshots. No API response mocking.
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const fixturePath = process.env.P8_FIXTURE;
assert(fixturePath, "P8_FIXTURE must point to tools/p8_e2e.py output");
const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const base = process.env.P8_DASHBOARD_URL ?? "http://127.0.0.1:15178";
const api = process.env.P8_API_URL ?? "http://127.0.0.1:18008";
const output = process.env.P8_BROWSER_OUTPUT ?? "/tmp/parakh-p8-browser";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true,
  ...(process.env.P8_CHROME ? { executablePath: process.env.P8_CHROME } : { channel: "chrome" }) });
const checks = [];
const check = name => { checks.push({ name, verdict: "PASS" }); console.log(`PASS ${name}`); };
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, hasTouch: true });
  const page = await context.newPage();
  let scoringMutations = 0;
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("request", r => { if (["POST", "PUT"].includes(r.method()) && /\/(review|decision|sign-off|reassessment-requests)$/.test(r.url())) scoringMutations++; });
  await page.goto(base);
  await page.getByLabel("Email").fill(process.env.P8_ASSESSOR_EMAIL ?? "p8-assessor@parakh.test");
  await page.getByLabel("Password").fill(process.env.P8_ASSESSOR_PASSWORD ?? "p8-isolated-test-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: /queue/i }).waitFor();
  check("authenticated dashboard login and queue");
  await page.goto(`${base}/#/assessments/${fixture.assessmentId}`);
  await page.getByRole("button", { name: /^T2 \(/ }).click();
  const old = page.locator(".evidence-gallery-item").filter({ has: page.locator(`video[src$='/${fixture.videoEvidenceId}/content']`) });
  const current = page.locator(".evidence-gallery-item").filter({ has: page.locator(`video[src$='/${fixture.currentVideoEvidenceId}/content']`) });
  await old.locator("video").waitFor();
  await old.locator("video").evaluate(v => new Promise((resolve, reject) => {
    if (v.readyState >= 1) return resolve();
    v.addEventListener("loadedmetadata", resolve, { once: true });
    v.addEventListener("error", () => reject(new Error("persisted evidence video could not load")), { once: true });
  }));
  const durationMs = await old.locator("video").evaluate(v => v.duration * 1000);
  assert.equal(durationMs, 5000);
  check("actual protected persisted video metadata/duration");
  assert.match(await old.textContent(), /v1 · historical/i);
  assert.match(await current.textContent(), /v2 · current/i);
  check("historical and current evidence separated");
  const buttons = old.locator("button.assistance-marker");
  assert.equal(await buttons.count(), fixture.expectedMarkers.length);
  const actual = await old.locator(".assistance-range").evaluateAll(elements => elements.map(el => ({ left: parseFloat(el.style.left), width: parseFloat(el.style.width) })));
  for (const [i, flag] of fixture.expectedMarkers.entries()) {
    assert.equal(actual[i].left, flag.startMs / durationMs * 100);
    assert.equal(actual[i].width, (flag.endMs - flag.startMs) / durationMs * 100);
    await buttons.nth(i).click();
    const time = await old.locator("video").evaluate(v => v.currentTime);
    assert(Math.abs(time * 1000 - flag.startMs) < 2, `seek ${time} vs ${flag.startMs}`);
    check(`marker ${flag.type} positions and seeks at ${flag.startMs} ms`);
  }
  check("start/end, overlapping intervals and simultaneous flags");
  await buttons.first().focus();
  await page.keyboard.press("Enter");
  assert.equal(await old.locator("video").evaluate(v => v.currentTime), 0);
  check("keyboard marker seeking");
  await buttons.last().tap();
  assert.equal(await old.locator("video").evaluate(v => v.currentTime), 4);
  check("touch marker seeking");
  assert.equal(await current.locator("button.assistance-marker").count(), 1);
  assert.match(await current.locator(".assistance-summary").textContent(), /v2/);
  check("new revision does not inherit old markers");
  for (const [task, expected] of [["T3", /unavailable at sealing/], ["T4", /queued at sealing/], ["T5", /no signed assistance recorded/]]) {
    await page.getByRole("button", { name: new RegExp(`^${task} \\(`) }).click();
    assert.match(await page.locator(".assistance-summary").allTextContents().then(v => v.join("\n")), expected);
  }
  await page.getByRole("button", { name: /^T2 \(/ }).click();
  check("unavailable, pending and legacy states rendered honestly");
  await page.setViewportSize({ width: 360, height: 780 });
  await page.screenshot({ path: `${output}/mobile-before-check.png`, fullPage: true });
  const overflow = await page.evaluate(() => Array.from(document.querySelectorAll("body *")).filter(el => {
    const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1);
  }).map(el => ({ tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width, text: el.textContent?.slice(0, 80) })).slice(0, 15));
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) console.log(JSON.stringify(overflow));
  assert(await old.locator("button.assistance-marker").first().evaluate(el => el.getBoundingClientRect().height >= 44));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "mobile horizontal overflow");
  await page.screenshot({ path: `${output}/mobile.png`, fullPage: true });
  check("mobile resize, touch targets and no horizontal overflow");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: `${output}/desktop.png`, fullPage: true });
  assert.equal(scoringMutations, 0);
  check("assistance never triggers score/outcome/reassessment actions");
  assert.deepEqual(errors, []);
  check("no browser runtime errors");
  const unauth = await browser.newContext();
  const response = await unauth.request.get(`${api}/assessments/${fixture.assessmentId}/evidence/${fixture.videoEvidenceId}/content`);
  assert.equal(response.status(), 401);
  check("unauthenticated evidence access denied");
  await unauth.close();
  let blockedEvidenceRequests = 0;
  await context.route(`**/evidence/${fixture.videoEvidenceId}/content`, route => {
    blockedEvidenceRequests++;
    return route.abort();
  });
  await page.reload();
  await page.getByRole("button", { name: /^T2 \(/ }).click();
  const failed = page.locator(".evidence-gallery-item").filter({ hasText: /v1 · historical/i });
  // Wait for the player's real error state rather than a phrase the UI
  // no longer displays; the interrupted media request must be observed.
  await failed.locator(".media-fallback[role='status']")
    .filter({ hasText: /This recording could not be opened/i }).waitFor();
  assert(blockedEvidenceRequests > 0, "the media route must be interrupted for this negative test");
  assert.equal(await failed.locator("button.assistance-marker:disabled").count(), fixture.expectedMarkers.length);
  assert.equal(await failed.locator(".assistance-range").count(), 0);
  check("unavailable media / missing playable duration disables seek without fake positions");
  await page.goto(`${base}/#/assessments/${fixture.mismatchedDurationAssessmentId}`);
  await page.getByRole("button", { name: /^T1 \(/ }).click();
  const mismatch = page.locator(".evidence-gallery-item").filter({ has: page.locator(`video[src$='/${fixture.mismatchedDurationEvidenceId}/content']`) });
  await mismatch.getByText(/Some signed intervals exceed the playable media duration/).waitFor();
  assert.equal(await mismatch.locator("button.assistance-marker:disabled").count(), 1);
  assert.equal(await mismatch.locator(".assistance-range").count(), 0);
  check("signed timestamps beyond actual playable duration are suppressed and explained");
  await writeFile(`${output}/results.json`, JSON.stringify({ runId: fixture.runId, source: "real API and persisted synthetic signed snapshots", checks, physicalDevice: false, verdict: "PASS" }, null, 2) + "\n");
} finally { await browser.close(); }
