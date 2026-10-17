// Gate C: the REAL hosted assessor dashboard on Vercel, driven by a real
// browser, talking to the REAL Railway API and the REAL Neon staging
// database. No mocked API responses.
//
// The point of this file is the thing section 6.2 of the brief singles out:
// PARAKH authenticates assessors with an HttpOnly, SameSite=Lax session
// cookie plus a double-submit CSRF cookie. Vercel and Railway are different
// sites, so a cross-site XHR would never send that cookie. The deployment
// therefore routes the browser's API calls through a SAME-ORIGIN Vercel
// rewrite at /api/* -> Railway, which is what these checks verify end to
// end: real Set-Cookie, real HttpOnly, real CSRF enforcement, real
// authenticated media and Range requests, real signed-report download, and
// real logout -- with no cookie flag weakened and CSRF left fully enabled.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const base = process.env.HOSTED_DASHBOARD_URL;
const email = process.env.HOSTED_ASSESSOR_EMAIL;
const password = process.env.HOSTED_ASSESSOR_PASSWORD;
const chromePath = process.env.HOSTED_CHROME;

const pass = [];
const fail = [];
const check = (name, cond, detail = "") => {
  const line = `${name}${detail ? ` -- ${detail}` : ""}`;
  if (cond) { pass.push(line); console.log(`  PASS  ${line}`); }
  else { fail.push(line); console.log(`  FAIL  ${line}`); }
};

const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const context = await browser.newContext({ ignoreHTTPSErrors: false });
const page = await context.newPage();

const consoleErrors = [];
const failedRequests = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("requestfailed", (r) => failedRequests.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));

const apiCalls = [];
page.on("response", (r) => {
  const u = r.url();
  if (u.includes("/api/")) apiCalls.push({ url: u, status: r.status() });
});

console.log(`Gate C -- hosted browser checks against ${base}\n`);

// --- 1. the app itself loads from Vercel -----------------------------------
const resp = await page.goto(base, { waitUntil: "networkidle", timeout: 90000 });
check("dashboard loads over HTTPS from Vercel", resp.status() === 200, `HTTP ${resp.status()}`);
check("served over TLS", base.startsWith("https://"));

// --- 2. no stale localhost API baked into the production bundle ------------
const bundleUrls = [];
for (const s of await page.locator("script[src]").all()) {
  bundleUrls.push(new URL(await s.getAttribute("src"), base).toString());
}
let bundleText = "";
for (const u of bundleUrls) {
  const r = await page.request.get(u);
  bundleText += await r.text();
}
check("production bundle contains no localhost API URL",
  !/http:\/\/localhost:\d+/.test(bundleText) && !/127\.0\.0\.1:\d+/.test(bundleText));
check("production bundle targets the same-origin /api proxy", /["'`]\/api["'`]/.test(bundleText));

// --- 3. login through the same-origin proxy, and inspect the real cookies --
const loginResp = await page.evaluate(async ({ email, password }) => {
  const r = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    credentials: "include",
  });
  return { status: r.status, body: await r.text() };
}, { email, password });
check("login succeeds through the /api same-origin rewrite", loginResp.status === 200,
  `HTTP ${loginResp.status}`);

const cookies = await context.cookies();
const names = cookies.map((c) => c.name);
const session = cookies.find((c) => c.httpOnly);
const csrf = cookies.find((c) => /csrf/i.test(c.name));

check("a session cookie was set by Set-Cookie", cookies.length > 0, names.join(", "));
check("session cookie is HttpOnly (not readable by JS)", !!session, session?.name ?? "none found");
check("session cookie is Secure", !!session && session.secure === true,
  session ? `secure=${session.secure}` : "n/a");
check("session cookie is SameSite=Lax (not weakened to None)",
  !!session && String(session.sameSite).toLowerCase() === "lax",
  session ? `sameSite=${session.sameSite}` : "n/a");
check("cookie is host-only on the dashboard origin (no shared parent domain)",
  !!session && !session.domain.startsWith("."), session ? `domain=${session.domain}` : "n/a");
check("a readable CSRF cookie exists for the double-submit pattern",
  !!csrf && csrf.httpOnly === false, csrf ? `${csrf.name} httpOnly=${csrf.httpOnly}` : "none");

// the HttpOnly session cookie must NOT be visible to document.cookie
const docCookie = await page.evaluate(() => document.cookie);
check("HttpOnly session cookie is absent from document.cookie",
  !!session && !docCookie.includes(session.name), `document.cookie=[${docCookie}]`);

// --- 4. authenticated requests work, and CSRF is really enforced ----------
const meResp = await page.evaluate(async () => {
  const r = await fetch("/api/auth/me", { credentials: "include" });
  return { status: r.status, body: await r.text() };
});
check("authenticated GET /auth/me succeeds with the cookie alone", meResp.status === 200,
  `HTTP ${meResp.status}`);

const queueResp = await page.evaluate(async () => {
  const r = await fetch("/api/queue", { credentials: "include" });
  return { status: r.status, body: await r.text() };
});
check("authenticated GET /queue succeeds", queueResp.status === 200, `HTTP ${queueResp.status}`);
const queue = JSON.parse(queueResp.body || "[]");
console.log(`        queue contains ${queue.length} assessment(s)`);

// Discover assessments directly rather than via /queue: a signed-off
// assessment has already LEFT the queue, and a draft has not entered it, so
// the queue alone cannot reach the evidence this file needs to exercise.
const assessments = [];
for (let id = 1; id <= 12; id += 1) {
  const r = await page.evaluate(async (i) => {
    const res = await fetch(`/api/assessments/${i}`, { credentials: "include" });
    return { status: res.status, body: res.status === 200 ? await res.text() : "" };
  }, id);
  if (r.status === 200) assessments.push(JSON.parse(r.body));
}
console.log(`        reachable assessments: ${assessments.map((a) => `${a.id}:${a.status}`).join(", ")}`);

// A mutating request WITHOUT the CSRF header must be rejected even though the
// cookie IS sent -- proving CSRF was not globally disabled to make the
// deployment work.
//
// Deliberately NOT /auth/logout: that endpoint takes no get_current_user
// dependency (it only clears cookies, see routers/auth.py), so it is
// CSRF-free by design and would both pass trivially and destroy the session
// mid-run. start-review is a genuine state-changing endpoint behind
// get_current_user, which is where auth.py actually enforces double-submit.
const csrfTarget = assessments[0]?.id;
if (csrfTarget) {
  const noCsrf = await page.evaluate(async (id) => {
    const r = await fetch(`/api/assessments/${id}/start-review`, {
      method: "POST", credentials: "include",
    });
    return r.status;
  }, csrfTarget);
  check("state-changing request WITHOUT the CSRF header is rejected (403)", noCsrf === 403,
    `HTTP ${noCsrf}`);

  const withCsrf = await page.evaluate(async (id) => {
    const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
    const r = await fetch(`/api/assessments/${id}/start-review`, {
      method: "POST", credentials: "include",
      headers: m ? { "X-CSRF-Token": decodeURIComponent(m[1]) } : {},
    });
    return r.status;
  }, csrfTarget);
  check("the same request WITH the CSRF header is accepted by the server",
    withCsrf < 500 && withCsrf !== 403, `HTTP ${withCsrf}`);
} else {
  check("an assessment existed to probe CSRF against", false, "none reachable");
}

// still authenticated -- the rejected call must not have ended the session
const stillMe = await page.evaluate(async () => (await fetch("/api/auth/me", { credentials: "include" })).status);
check("session survives the rejected CSRF attempt", stillMe === 200, `HTTP ${stillMe}`);

// --- 5. private media + Range through the proxy ---------------------------
// Prefer an assessment that actually has a worker-processed video: that is
// the only one that can exercise thumbnail serving, Range requests and
// <video> playback. Taking merely the first assessment with any photo would
// silently skip the interesting half of this section.
const mediaOrder = [...assessments].sort((x, y) => {
  const score = (a) => {
    const ev = (a.tasks ?? []).flatMap((t) => t.evidence ?? []);
    if (ev.some((e) => e.kind === "video" && e.thumbnail_status === "completed")) return 0;
    if (ev.some((e) => e.kind === "video")) return 1;
    if (ev.length) return 2;
    return 3;
  };
  return score(x) - score(y);
});

let mediaChecked = false;
for (const a of mediaOrder) {
  const evidence = (a.tasks ?? []).flatMap((t) => t.evidence ?? []);
  const video = evidence.find((e) => e.kind === "video" && e.thumbnail_status === "completed");
  const photo = evidence.find((e) => e.kind === "photo");
  if (!video && !photo) continue;

  if (photo) {
    const r = await page.evaluate(async ({ aid, eid }) => {
      const res = await fetch(`/api/assessments/${aid}/evidence/${eid}/content`, { credentials: "include" });
      const buf = await res.arrayBuffer();
      return { status: res.status, bytes: buf.byteLength, cc: res.headers.get("cache-control") };
    }, { aid: a.id, eid: photo.id });
    check("private photo evidence loads through the proxy", r.status === 200 && r.bytes > 0,
      `HTTP ${r.status} ${r.bytes}B`);
    check("private evidence is not shared-cacheable", /no-store/.test(r.cc ?? ""), r.cc ?? "(none)");
  }
  if (video) {
    const t = await page.evaluate(async ({ aid, eid }) => {
      const res = await fetch(`/api/assessments/${aid}/evidence/${eid}/thumbnail`, { credentials: "include" });
      const buf = await res.arrayBuffer();
      return { status: res.status, bytes: buf.byteLength };
    }, { aid: a.id, eid: video.id });
    check("worker-generated video thumbnail renders through the proxy", t.status === 200 && t.bytes > 0,
      `HTTP ${t.status} ${t.bytes}B`);

    const rng = await page.evaluate(async ({ aid, eid }) => {
      const res = await fetch(`/api/assessments/${aid}/evidence/${eid}/content`, {
        credentials: "include", headers: { Range: "bytes=0-1023" },
      });
      const buf = await res.arrayBuffer();
      return { status: res.status, bytes: buf.byteLength, cr: res.headers.get("content-range") };
    }, { aid: a.id, eid: video.id });
    check("video Range request survives the Vercel rewrite (206)", rng.status === 206,
      `HTTP ${rng.status}`);
    check("Range returns exactly 1024 bytes with a Content-Range", rng.bytes === 1024 && !!rng.cr,
      `${rng.bytes}B ${rng.cr ?? "(no header)"}`);

    // real <video> element must actually be able to load metadata
    const playable = await page.evaluate(async ({ aid, eid }) => {
      const v = document.createElement("video");
      v.src = `/api/assessments/${aid}/evidence/${eid}/content`;
      v.preload = "metadata";
      document.body.appendChild(v);
      return await new Promise((res) => {
        const done = (ok) => res(ok ? { ok: true, dur: v.duration, w: v.videoWidth, h: v.videoHeight } : { ok: false });
        v.onloadedmetadata = () => done(true);
        v.onerror = () => done(false);
        setTimeout(() => done(false), 45000);
      });
    }, { aid: a.id, eid: video.id });
    check("a real <video> element loads metadata (playback/seeking viable)",
      playable.ok === true, playable.ok ? `${playable.w}x${playable.h} dur=${playable.dur}s` : "did not load");
  }
  mediaChecked = true;
  break;
}
if (!mediaChecked) check("private media checks had an assessment with evidence", false, "no suitable assessment in queue");

// --- 6. signed report download + public verify ----------------------------
// The signed-report receipt lives at /assessments/{id}/report?format=receipt
// (see apps/dashboard/src/api.ts), not at a /report/signed path.
let reportUid = null;
let reportAssessmentId = null;
for (const a of assessments) {
  const d = await page.evaluate(async (id) => {
    const r = await fetch(`/api/assessments/${id}/report?format=receipt`, { credentials: "include" });
    return { status: r.status, body: await r.text() };
  }, a.id);
  if (d.status === 200) {
    try {
      const receipt = JSON.parse(d.body);
      reportUid = receipt.report_uid ?? receipt.report_id ?? null;
      if (reportUid) { reportAssessmentId = a.id; break; }
    } catch { /* not a receipt */ }
  }
}
if (reportUid && reportAssessmentId) {
  // the actual signed PDF bytes must come back through the proxy
  const pdfResp = await page.evaluate(async (id) => {
    const r = await fetch(`/api/assessments/${id}/report?format=pdf`, { credentials: "include" });
    const b = await r.arrayBuffer();
    const head = new Uint8Array(b.slice(0, 5));
    return { status: r.status, bytes: b.byteLength, magic: String.fromCharCode(...head) };
  }, reportAssessmentId);
  check("signed report PDF downloads through the proxy", pdfResp.status === 200 && pdfResp.bytes > 0,
    `HTTP ${pdfResp.status} ${pdfResp.bytes}B`);
  check("downloaded bytes are a real PDF", pdfResp.magic.startsWith("%PDF"),
    JSON.stringify(pdfResp.magic));
}
if (reportUid) {
  const pdf = await page.evaluate(async (uid) => {
    const r = await fetch(`/api/verify/${encodeURIComponent(uid)}`, { credentials: "omit" });
    return { status: r.status, body: await r.text() };
  }, reportUid);
  check("public /verify/{report_id} works unauthenticated through the proxy", pdf.status === 200,
    `HTTP ${pdf.status}`);

  // The public hash route must still render -- the /api rewrite must not
  // swallow client-side routing or static assets. Note page.goto() to a
  // URL differing only by its #fragment is a same-document navigation and
  // returns null, so this asserts on rendered content instead of a response.
  const freshCtx = await browser.newContext();          // unauthenticated, as a verifier would be
  const verifyPage = await freshCtx.newPage();
  await verifyPage.goto(`${base}/#/verify/${reportUid}`, { waitUntil: "networkidle", timeout: 90000 });
  await verifyPage.waitForTimeout(3000);
  const bodyText = await verifyPage.locator("body").innerText();
  check("public hash-route verification page renders for an ANONYMOUS visitor",
    bodyText.trim().length > 0, `${bodyText.trim().length} chars rendered`);
  check("verification page shows this report's id",
    bodyText.includes(reportUid.slice(0, 10)), `looked for ${reportUid.slice(0, 10)}`);
  const leaks = ["password", "secret", "S3_", "postgres://", "postgresql://"]
    .filter((s) => bodyText.toLowerCase().includes(s.toLowerCase()));
  check("public page leaks no credential-shaped text", leaks.length === 0, leaks.join(",") || "none");
  await freshCtx.close();
} else {
  check("a signed report existed to verify", false, "none found in queue");
}

// --- 7. logout with the CSRF header, then session is gone -----------------
await page.goto(base, { waitUntil: "networkidle", timeout: 90000 });
const out = await page.evaluate(async () => {
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  const r = await fetch("/api/auth/logout", {
    method: "POST", credentials: "include",
    headers: m ? { "X-CSRF-Token": decodeURIComponent(m[1]) } : {},
  });
  return r.status;
});
check("logout succeeds when the CSRF header IS supplied", out === 200 || out === 204, `HTTP ${out}`);
const afterLogout = await page.evaluate(async () => (await fetch("/api/auth/me", { credentials: "include" })).status);
check("session is rejected after logout", afterLogout === 401, `HTTP ${afterLogout}`);

console.log(`\nconsole errors: ${consoleErrors.length}`);
consoleErrors.slice(0, 5).forEach((e) => console.log(`   ! ${e.slice(0, 160)}`));
console.log(`failed requests: ${failedRequests.length}`);
failedRequests.slice(0, 5).forEach((e) => console.log(`   ! ${e.slice(0, 160)}`));
const nonOk = apiCalls.filter((c) => c.status >= 500);
console.log(`5xx API responses: ${nonOk.length}`);

await browser.close();
console.log(`\n${pass.length} passed, ${fail.length} failed`);
fail.forEach((f) => console.log(`  FAILED: ${f}`));
process.exit(fail.length ? 1 : 0);
