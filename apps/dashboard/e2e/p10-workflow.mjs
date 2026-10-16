// P10: browser coverage for the single rubric-assisted assessor workflow
// (Authentication -> Queue -> Evidence Review -> PC Scoring -> Competency
// Profile -> Human Decision -> Reassessment or Signed Report -> Verification).
// Before this file, apps/dashboard/e2e/ only covered the Q2/Q3 evidence
// assistance overlay (p8*.mjs) -- login, queue states, PC scoring
// validation/concurrency, competency profile, reassessment and sign-off/
// verify had zero automated browser coverage. Real services only: a real
// FastAPI + PostgreSQL stack (see infra/docker-compose.yml), a real
// browser, no mocked API responses except where a test deliberately
// simulates a network failure to prove the UI's own recovery path.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const base = process.env.P10_DASHBOARD_URL ?? "http://127.0.0.1:18173";
const api = process.env.P10_API_URL ?? "http://127.0.0.1:18100";
const email = process.env.P10_ASSESSOR_EMAIL ?? "p10-e2e-assessor@parakh.test";
const password = process.env.P10_ASSESSOR_PASSWORD ?? "p10-e2e-isolated-test-only";

const browser = await chromium.launch({
  headless: true,
  ...(process.env.P8_CHROME ? { executablePath: process.env.P8_CHROME } : { channel: "chrome" }),
});

const checks = [];
const check = (name) => {
  checks.push(name);
  console.log(`PASS ${name}`);
};

async function findSeededAssessments() {
  const loginRes = await fetch(`${api}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(loginRes.status, 200, "setup: seeded assessor login failed -- run `python -m app.seed` first");
  const { access_token } = await loginRes.json();
  const queueRes = await fetch(`${api}/queue`, { headers: { Authorization: `Bearer ${access_token}` } });
  const queue = await queueRes.json();
  const submitted = queue.find((a) => a.status === "submitted");
  const inReview = queue.find((a) => a.status === "in_review");
  assert(submitted && inReview, "setup: need one 'submitted' and one 'in_review' seeded assessment");
  return { submittedId: submitted.id, inReviewId: inReview.id };
}

const { submittedId, inReviewId } = await findSeededAssessments();

try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  // ---- 1. Unauthenticated access is redirected to login, not the page ----
  await page.goto(`${base}/#/assessments/${inReviewId}`);
  await page.getByRole("heading", { name: /Assessor Login/i }).waitFor();
  check("unauthenticated deep link redirects to login, not the assessment");

  // ---- 2. Wrong password: inline error, stays on login ----
  // Clear the hash left over from step 1 -- the app deliberately preserves
  // whatever route was requested across a login (so a deep link still
  // lands where it was aimed once authenticated); this test wants to land
  // on the queue next, so it must ask for the queue explicitly.
  await page.goto(`${base}/#/queue`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("definitely-the-wrong-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator(".error").filter({ hasText: /incorrect/i }).waitFor();
  await page.getByRole("heading", { name: /Assessor Login/i }).waitFor();
  check("wrong password shows inline error and does not navigate");

  // ---- 3. Correct credentials reach the queue ----
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();
  await page.locator("tbody tr").first().waitFor();
  check("correct login reaches the assessor queue");

  // ---- 4. Session persists across a reload ----
  await page.reload();
  await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();
  check("session persists across a page reload (cookie-based, no client storage)");

  // ---- 5. Queue network failure shows an error + Retry, which recovers ----
  await page.route("**/queue", (route) => route.fulfill({ status: 500, body: "{}" }));
  await page.reload();
  await page.locator(".error").filter({ hasText: /Failed to load the queue/i }).waitFor();
  const retryButton = page.getByRole("button", { name: "Retry" });
  await retryButton.waitFor();
  check("queue network failure renders an explicit error with a Retry control");
  await page.unroute("**/queue");
  await retryButton.click();
  await page.getByRole("heading", { name: /Assessor Queue/i }).waitFor();
  await page.locator("tbody tr").first().waitFor();
  check("Retry recovers the queue once the network call succeeds");

  // ---- 6. Human decision: start review on the submitted assessment ----
  await page.goto(`${base}/#/assessments/${submittedId}`);
  await page.getByRole("button", { name: "Start review" }).click();
  await page.getByRole("button", { name: "Load scoring sheet" }).waitFor();
  check("assessor can start review, transitioning submitted -> in_review");

  // ---- 7/8. PC scoring: client-side comment validation, then a real save ----
  await page.goto(`${base}/#/assessments/${inReviewId}`);
  await page.getByRole("button", { name: "Load scoring sheet" }).click();
  const rows = page.locator("table tbody tr");
  await rows.first().waitFor();
  const firstRow = rows.nth(0);
  let putRequests = 0;
  page.on("request", (r) => {
    if (r.method() === "PUT" && /\/review$/.test(r.url())) putRequests++;
  });
  await firstRow.locator("select").nth(1).selectOption("NOT_OBSERVABLE"); // evidence status
  await firstRow.locator("button", { hasText: "Save" }).click();
  await firstRow.locator(".error").filter({ hasText: /comment is required/i }).waitFor();
  assert.equal(putRequests, 0, "a client-side validation failure must not reach the network");
  check("PC scoring blocks a NOT_OBSERVABLE save with no comment, client-side, before any request");

  await firstRow.locator("textarea").fill("Not observable in the submitted evidence for this PC.");
  await firstRow.locator("button", { hasText: "Save" }).click();
  await firstRow.locator("text=/marks awarded/").waitFor();
  assert.equal(putRequests, 1);
  check("PC scoring saves successfully once the required comment is present");

  // ---- 9. Optimistic concurrency: a concurrent PUT makes this save 409 ----
  const secondRow = rows.nth(1);
  const secondPcId = await secondRow.locator("td").first().locator("strong").textContent();
  const csrfToken = await page.evaluate(() => document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1]);
  const concurrentPut = await page.evaluate(
    async ({ apiBase, assessmentId, pcFullId, csrf }) => {
      const res = await fetch(`${apiBase}/assessments/${assessmentId}/review`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          pc_full_id: pcFullId,
          score_level: 2,
          evidence_status: "DEMONSTRATED",
          assessor_comment: null,
          expected_version: 0,
        }),
      });
      return res.status;
    },
    { apiBase: api, assessmentId: inReviewId, pcFullId: secondPcId, csrf: csrfToken },
  );
  assert.equal(concurrentPut, 200, "setup: the simulated concurrent update itself must succeed");
  await secondRow.locator("select").nth(0).selectOption("3"); // stale UI still thinks expected_version is 0
  await secondRow.locator("button", { hasText: "Save" }).click();
  await secondRow.locator(".error").filter({ hasText: /someone else updated/i }).waitFor();
  check("a stale save (lost the race to a concurrent update) surfaces a clear conflict message, not a dead-end error");
  await page.locator(`tr:has-text("${secondPcId}") >> text=/marks awarded/`).first().waitFor();
  check("after a conflict, the row is refreshed with the server's current (winning) value");

  // ---- 10. Competency profile ----
  await page.getByRole("button", { name: "Load competency profile" }).click();
  await page.locator(".disclaimer").filter({ hasText: /decision support only/i }).waitFor();
  await page.locator("dt", { hasText: "Computed outcome" }).waitFor();
  check("competency profile renders the computed outcome with its advisory disclaimer");

  // ---- 11. Targeted reassessment request ----
  await page.getByRole("button", { name: "Request targeted reassessment…" }).click();
  await page.locator(".modal-card").getByRole("checkbox").first().check();
  await page.locator(".modal-card textarea").nth(0).fill("P10 workflow test -- targeted reassessment reason.");
  await page.locator(".modal-card textarea").nth(1).fill("Recapture this task only.");
  await page.getByRole("button", { name: "Send request" }).click();
  await page.locator(".modal-overlay").waitFor({ state: "detached" });
  await page.locator("h3", { hasText: "Reassessment requests" }).waitFor();
  await page.locator("td", { hasText: "P10 workflow test -- targeted reassessment reason." }).waitFor();
  check("targeted reassessment request is created and appears in the assessment's own history");

  // ---- 12. Sign-off + signed report + authenticated verify ----
  await page.goto(`${base}/#/assessments/${submittedId}`);
  await page.getByRole("button", { name: "Load competency profile" }).click();
  await page.locator("dt", { hasText: "Computed outcome" }).waitFor();
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign off and produce signed report" }).click();
  await page.locator("dt", { hasText: "Report ID" }).waitFor();
  const reportId = await page.locator("dl dd code").first().textContent();
  check("password-confirmed sign-off produces a signed report with a report ID");
  await page.getByRole("button", { name: "Verify", exact: true }).click();
  await page.locator("text=/Signature verified/i").waitFor();
  check("authenticated in-page verify confirms the signature");
  // Once signed, the assessment moves to "recommended" and the dashboard
  // correctly stops offering the Sign-off form at all (it only renders
  // while status === "in_review") -- idempotent-retry-returns-the-same-
  // report is a backend contract already covered by server/tests/
  // test_reports.py, not something the UI exposes a repeat action for.
  await page.locator('input[type="password"]').count().then((n) => assert.equal(n, 0));
  check("once signed, the sign-off form is correctly no longer offered");

  // ---- 13. Public verification page, reachable with NO login at all ----
  const publicContext = await browser.newContext();
  const publicPage = await publicContext.newPage();
  await publicPage.goto(`${base}/#/verify/${encodeURIComponent(reportId)}`);
  await publicPage.locator("text=/Signature verified/i").waitFor();
  await publicPage.getByRole("button", { name: "Log out" }).count().then((n) => assert.equal(n, 0));
  check("public QR-target verify page confirms the same signature with no session/cookie at all");

  await publicPage.goto(`${base}/#/verify/report-id-that-does-not-exist`);
  await publicPage.locator(".error").filter({ hasText: /no signed report exists/i }).waitFor();
  check("public verify page handles an unknown report id with a clear, non-crashing error");
  await publicContext.close();

  // ---- 14. Logout ends the session ----
  await page.goto(`${base}/#/queue`);
  await page.getByRole("button", { name: "Log out" }).click();
  await page.getByRole("heading", { name: /Assessor Login/i }).waitFor();
  check("logout returns to the login screen");
  await page.reload();
  await page.getByRole("heading", { name: /Assessor Login/i }).waitFor();
  check("logout actually ended the server-side session (reload does not silently resume it)");

  assert.deepEqual(pageErrors, [], `uncaught browser errors: ${pageErrors.join("; ")}`);
  check("no uncaught browser errors across the whole workflow");

  console.log(`\n${checks.length} checks passed.`);
} finally {
  await browser.close();
}
