// Real device-generated analysis and Android Keystore signatures, persisted by P6.
// The phone inputs are synthetic; this is integration evidence, not field accuracy.
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

assert(process.env.P8_NATIVE_FIXTURE, "Set P8_NATIVE_FIXTURE to the p8NativeResult JSON emitted by Android instrumentation");
const fixture = JSON.parse(await readFile(process.env.P8_NATIVE_FIXTURE, "utf8"));
const base = process.env.P8_DASHBOARD_URL ?? "http://127.0.0.1:15178";
const api = process.env.P8_API_URL ?? "http://127.0.0.1:18008";
const out = process.env.P8_BROWSER_OUTPUT ?? "/tmp/parakh-p8-native-browser";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true,
  ...(process.env.P8_CHROME ? { executablePath: process.env.P8_CHROME } : { channel: "chrome" }) });
const checks = [];
const pass = name => { checks.push({ name, verdict: "PASS" }); console.log(`PASS ${name}`); };
try {
  const context = await browser.newContext();
  const credentials = { email: process.env.P8_ASSESSOR_EMAIL ?? "p8-assessor@parakh.test",
    password: process.env.P8_ASSESSOR_PASSWORD ?? "p8-isolated-test-only" };
  const login = await context.request.post(`${api}/auth/login`, { data: credentials });
  assert.equal(login.status(), 200);
  const token = (await login.json()).access_token;
  const response = await context.request.get(`${api}/assessments/${fixture.assessmentId}`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(response.status(), 200);
  const detail = await response.json();
  assert.equal(detail.revision_number, 2);
  const page = await context.newPage();
  let mutations = 0;
  page.on("request", r => { if (["POST", "PUT"].includes(r.method()) && /\/(review|decision|sign-off|reassessment-requests)$/.test(r.url())) mutations++; });
  await page.goto(base);
  // The real login response installed the existing HttpOnly session cookie in
  // this context. The product should therefore open its authenticated queue.
  await page.getByRole("heading", { name: /queue/i }).waitFor();
  await page.goto(`${base}/#/assessments/${fixture.assessmentId}`);
  await page.getByRole("button", { name: /^T2 \(/ }).click();
  pass("authenticated review of the native uploaded assessment");
  for (const [id, label] of [[fixture.historicalVideoEvidenceId, "v1 · historical"], [fixture.currentVideoEvidenceId, "v2 · current"]]) {
    const evidence = detail.tasks.flatMap(t => t.evidence).find(e => e.id === id);
    assert(evidence.assistance.hands.provenance.modelSha256);
    const card = page.locator(".evidence-gallery-item").filter({ has: page.locator(`video[src$='/${id}/content']`) });
    await card.locator("video").evaluate(v => new Promise((resolve, reject) => {
      if (v.readyState >= 1) return resolve();
      v.addEventListener("loadedmetadata", resolve, { once: true });
      v.addEventListener("error", () => reject(new Error("native uploaded video unavailable")), { once: true });
    }));
    assert((await card.textContent()).includes(label));
    const duration = await card.locator("video").evaluate(v => v.duration * 1000);
    const groups = ["DARK", "OVEREXPOSED", "BLURRY", "CAMERA_MOTION", "HANDS_NOT_DETECTED"];
    const flags = groups.flatMap(type => evidence.assistance.flags.filter(f => f.type === type && f.endMs !== null));
    assert(flags.length > 0, "native video should expose actual analyzer intervals for this fixture");
    const markers = card.locator("button.assistance-marker");
    assert.equal(await markers.count(), flags.length);
    for (const [index, flag] of flags.entries()) {
      assert(flag.endMs <= duration);
      await markers.nth(index).click();
      assert(Math.abs(await card.locator("video").evaluate(v => v.currentTime * 1000) - flag.startMs) < 2);
    }
    pass(`${label}: actual Q2/Q3 intervals render and seek (${flags.length} markers)`);
  }
  await page.getByRole("button", { name: /^T1 \(/ }).click();
  assert((await page.locator(".assistance-summary").textContent()).includes("Dark capture"));
  pass("native dark-photo advice remains visible after targeted video reassessment");
  assert.equal(mutations, 0);
  pass("reviewing native advice makes no scoring or outcome mutations");
  await page.screenshot({ path: `${out}/native-photo.png`, fullPage: true });
  await page.getByRole("button", { name: /^T2 \(/ }).click();
  await page.screenshot({ path: `${out}/native-history.png`, fullPage: true });
  await writeFile(`${out}/results.json`, JSON.stringify({ runId: fixture.runId, source: fixture.source,
    checks, verdict: "PASS", physicalDeviceInference: true, syntheticMedia: true, cameraXCaptureVerified: false }, null, 2) + "\n");
} finally { await browser.close(); }
