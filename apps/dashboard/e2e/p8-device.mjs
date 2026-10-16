// Persisted CameraX -> native assistance -> P5/P6 -> authenticated product player.
// Input is redacted QA observer state; no server mocking or imported media.
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

assert(process.env.P8_DEVICE_SEALED && process.env.P8_DEVICE_SYNCED,
  "Set P8_DEVICE_SEALED and P8_DEVICE_SYNCED to the physical UI phase JSON files");
const sealed = JSON.parse(await readFile(process.env.P8_DEVICE_SEALED, "utf8")).state;
const synced = JSON.parse(await readFile(process.env.P8_DEVICE_SYNCED, "utf8")).state;
assert.equal(sealed.assessmentId, synced.assessmentId);
assert.equal(sealed.package, "in.kaushalpramaan.app.p8validation");
assert.equal(sealed.internetNetworkCount, 0);
assert.equal(sealed.synced, false);
assert.equal(synced.synced, true);
assert(synced.serverAssessmentId);
const api = process.env.P8_API_URL ?? "http://127.0.0.1:18008";
const base = process.env.P8_DASHBOARD_URL ?? "http://127.0.0.1:15178";
const out = process.env.P8_BROWSER_OUTPUT ?? "/tmp/parakh-p8-device-browser";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true,
  ...(process.env.P8_CHROME ? { executablePath: process.env.P8_CHROME } : { channel: "chrome" }) });
const checks = [];
const pass = name => { checks.push({ name, verdict: "PASS" }); console.log(`PASS ${name}`); };
try {
  const context = await browser.newContext();
  const login = await context.request.post(`${api}/auth/login`, { data: {
    email: process.env.P8_ASSESSOR_EMAIL ?? "p8-assessor@parakh.test",
    password: process.env.P8_ASSESSOR_PASSWORD ?? "p8-isolated-test-only",
  } });
  assert.equal(login.status(), 200);
  const token = (await login.json()).access_token;
  const response = await context.request.get(`${api}/assessments/${synced.serverAssessmentId}`,
    { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(response.status(), 200);
  const detail = await response.json();
  assert.equal(detail.revision_number, sealed.revisionNumber);
  const review = await context.request.get(`${api}/assessments/${synced.serverAssessmentId}/review`,
    { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(review.status(), 200);
  const beforeReview = await review.json();
  assert(beforeReview.every(row => row.score == null), "This QA capture assessment must have no inferred scores");
  const evidence = detail.tasks.flatMap(t => t.evidence);
  for (const item of sealed.evidence) {
    assert(item.sealedSnapshot, "Every CameraX item needs its signed snapshot");
    const uploaded = evidence.find(e => e.assistance?.evidenceId === item.id);
    assert(uploaded, "CameraX evidence missing from the real backend");
    assert.deepEqual(uploaded.assistance, item.sealedSnapshot);
    assert.deepEqual(synced.evidence.find(e => e.id === item.id).sealedSnapshot, item.sealedSnapshot);
  }
  pass("offline sealed snapshots match the uploaded API and post-sync phone state exactly");
  const page = await context.newPage();
  let mutations = 0;
  page.on("request", r => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(r.method()) &&
        /\/(review|decision|sign-off|reassessment-requests|scores)(?:[/?]|$)/.test(r.url())) mutations++;
  });
  await page.goto(base);
  await page.getByRole("heading", { name: /queue/i }).waitFor();
  await page.goto(`${base}/#/assessments/${synced.serverAssessmentId}`);
  let markerCount = 0;
  for (const task of detail.tasks) {
    const videos = task.evidence.filter(e => e.content_type?.startsWith("video/") || e.kind === "VIDEO" || e.media_type === "video");
    // Existing API uses media_type; select via actual signed video duration too.
    const selected = task.evidence.filter(e => e.assistance?.durationMs != null || videos.includes(e));
    if (!selected.length) continue;
    await page.getByRole("button", { name: new RegExp(`^${task.task_code} \\(`) }).click();
    for (const item of selected) {
      const card = page.locator(".evidence-gallery-item").filter({ has: page.locator(`video[src$='/${item.id}/content']`) });
      assert((await card.textContent()).includes(`v${item.revision_number} · ${item.is_current_revision ? "current" : "historical"}`));
      const video = card.locator("video");
      await video.evaluate(v => new Promise((resolve, reject) => {
        if (v.readyState >= 1) return resolve();
        v.addEventListener("loadedmetadata", resolve, { once: true });
        v.addEventListener("error", () => reject(new Error("Uploaded CameraX video unavailable")), { once: true });
      }));
      const duration = await video.evaluate(v => v.duration * 1000);
      console.log(`CameraX video ${item.id}: signed duration=${item.assistance.durationMs} ms, browser duration=${duration} ms`);
      const types = ["DARK", "OVEREXPOSED", "BLURRY", "CAMERA_MOTION", "HANDS_NOT_DETECTED"];
      const flags = types.flatMap(type => item.assistance.flags.filter(f => f.type === type && f.endMs != null));
      const markers = card.locator("button.assistance-marker");
      assert.equal(await markers.count(), flags.length);
      for (const [i, flag] of flags.entries()) {
        if (flag.startMs >= duration) {
          assert(await markers.nth(i).isDisabled());
          continue;
        }
        await markers.nth(i).click();
        assert(Math.abs(await video.evaluate(v => v.currentTime * 1000) - flag.startMs) < 2);
        markerCount++;
      }
      const firstPlayable = flags.findIndex(f => f.startMs < duration);
      if (firstPlayable >= 0) {
        await markers.nth(firstPlayable).focus();
        await page.keyboard.press("Enter");
        assert(Math.abs(await video.evaluate(v => v.currentTime * 1000) - flags[firstPlayable].startMs) < 2);
      }
      if (flags.some(f => f.endMs > duration)) {
        await card.getByText(/Some signed intervals exceed the playable media duration/).waitFor();
        const ranges = await card.locator(".assistance-range").evaluateAll(elements => elements.map(e => ({left: parseFloat(e.style.left), width: parseFloat(e.style.width)})));
        assert(ranges.every(r => r.left >= 0 && r.width > 0 && r.left + r.width <= 100.000001));
      }
      pass(`CameraX video ${item.id}: ${flags.length} persisted intervals seek at source milliseconds`);
    }
  }
  assert(markerCount > 0, "No real marker available: timeline exit is NOT VERIFIED for this recording");
  await page.setViewportSize({ width: 360, height: 800 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  pass("physical capture review fits a 360px viewport");
  assert.equal(mutations, 0);
  const afterReview = await context.request.get(`${api}/assessments/${synced.serverAssessmentId}/review`,
    { headers: { Authorization: `Bearer ${token}` } });
  assert.deepEqual(await afterReview.json(), beforeReview);
  pass("viewing assistance makes no assessment decision mutations");
  const unauth = await browser.newContext();
  const protectedVideo = evidence.find(e => e.assistance?.durationMs != null);
  assert.equal((await unauth.request.get(`${api}/assessments/${synced.serverAssessmentId}/evidence/${protectedVideo.id}/content`)).status(), 401);
  await unauth.close();
  pass("actual CameraX evidence requires reviewer authentication");
  await writeFile(`${out}/results.json`, JSON.stringify({ assessmentId: synced.serverAssessmentId,
    revisionNumber: sealed.revisionNumber, checks, markerCount, verdict: "PASS",
    physicalDevice: true, cameraXCapture: true, independentAccuracyEvidence: false }, null, 2) + "\n");
} finally { await browser.close(); }
