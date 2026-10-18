import assert from "node:assert/strict";
import { randomBytes, randomUUID, createHash } from "node:crypto";
import { readFileSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.OPEN_DASHBOARD_URL ?? "http://127.0.0.1:18177";
const api = process.env.OPEN_API_URL ?? "http://127.0.0.1:18178";
const browser = await chromium.launch({headless: true, ...(process.env.P8_CHROME ? {executablePath: process.env.P8_CHROME} : {})});
const checks = [];
const pass = name => { checks.push(name); console.log(`PASS ${name}`); };

async function enroll(name, consent = false) {
  const response = await fetch(`${api}/workers/enroll`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
    device_worker_id: `KP-${randomUUID()}`, enrollment_secret: randomBytes(32).toString("hex"), client_assessment_id: randomUUID(),
    full_name: name, phone: "+919876543210", public_name_consent: consent})});
  assert.equal(response.status, 200);
  return response.json();
}
async function submit(a) {
  assert.equal((await fetch(`${api}/assessments/${a.id}/submit`, {method:"POST", headers:{"X-Worker-Token":a.worker_token}})).status,200);
}
const accountEmail = `assessor-${randomUUID()}@parakh.invalid`;
const accountPassword = randomBytes(24).toString('hex');
async function confirm(page, id, action, prepare, wrongPassword = false) {
  const dialog = page.getByRole('dialog', {name:/^Confirm/});
  if (prepare) await prepare(dialog);
  await dialog.getByRole('checkbox', {name:/explicitly confirm/}).check();
  if (wrongPassword) {
    await dialog.getByLabel('Confirm your password', {exact:true}).fill('deliberately-wrong-password');
    await dialog.getByRole('button', {name:'Confirm action',exact:true}).click();
    await dialog.getByRole('alert').filter({hasText:'incorrect password'}).waitFor();
    assert.equal(await dialog.getByLabel('Confirm your password',{exact:true}).inputValue(),'');
  }
  await dialog.getByLabel('Confirm your password', {exact:true}).fill(accountPassword);
  await dialog.getByRole('button', {name:'Confirm action',exact:true}).click();
  await dialog.waitFor({state:'detached',timeout:20000});
}

try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(base);
  await page.getByRole("link", {name: "Enter", exact: false}).click();
  if ((await (await fetch(`${api}/public/assessments`)).json()).length === 0) await page.getByText("No submitted assessments yet.").waitFor();
  else await page.getByRole("heading", {name:"Assessment queue", exact:true}).waitFor();
  assert.equal(await page.getByRole("button", {name:/log in|sign up|demo/i}).count(),0);
  pass("Public dashboard opens without login or demo records; real empty state");
  const nav = page.getByRole('navigation', {name:'Main navigation'});
  for (const name of ['Public queue', 'Verify report', 'Queue']) {
    await nav.getByRole('link', {name,exact:true}).click();
    assert.equal(await nav.getByRole('link').count(), 3);
    await page.waitForFunction(name => document.querySelector('.nav [aria-current="page"]')?.textContent === name, name);
    assert.equal(await page.locator('.topbar .header-enter').count(), 0);
  }
  await nav.getByRole('link', {name:'Verify report',exact:true}).click();
  await page.getByLabel('Report ID', {exact:true}).fill('unknown-navigation-check');
  await page.getByRole('button', {name:'Verify report',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'No signed report exists for this report ID.'}).waitFor();
  assert.equal(await nav.locator('[aria-current="page"]').innerText(), 'Verify report');
  await page.setViewportSize({width:390,height:844});
  for (const name of ['Public queue', 'Verify report', 'Queue']) {
    await nav.getByRole('link', {name,exact:true}).click();
    await page.waitForFunction(name => document.querySelector('.nav [aria-current="page"]')?.textContent === name, name);
    assert.equal(await nav.getByRole('link').count(), 3);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  }
  await page.setViewportSize({width:1280,height:900});
  pass('All top navigation links remain visible with one active page, including nested verification and mobile views');
  const a = await enroll("Private Candidate");
  // A real private object upload via existing resumable protocol.
  const data = readFileSync(new URL("./fixtures/evidence.jpg", import.meta.url));
  const headers = {"X-Worker-Token":a.worker_token,"Content-Type":"application/json"};
  const opened = await fetch(`${api}/uploads`, {method:"POST", headers, body:JSON.stringify({
    assessment_id:a.id, task_code:"T1",kind:"photo",mime:"image/jpeg", claimed_size_bytes:data.length,
    claimed_sha256:createHash("sha256").update(data).digest("hex")})});
  assert.equal(opened.status,201, await opened.clone().text());
  const session = await opened.json();
  const chunk = await fetch(`${api}/uploads/${session.id}/chunks/0`, {method:"PUT",headers:{"X-Worker-Token":a.worker_token,"Content-Type":"application/octet-stream"},body:data});
  assert.equal(chunk.status,200);
  assert.equal((await fetch(`${api}/uploads/${session.id}/complete`,{method:"POST",headers,body:JSON.stringify({client_sha256:createHash("sha256").update(data).digest("hex")})})).status,200);
  const clip = readFileSync(new URL("./fixtures/evidence.mp4", import.meta.url));
  const clipHash = createHash("sha256").update(clip).digest("hex");
  const videoOpened = await fetch(`${api}/uploads`, {method:"POST", headers, body:JSON.stringify({assessment_id:a.id, task_code:"T1",kind:"video",mime:"video/mp4", claimed_size_bytes:clip.length, claimed_sha256:clipHash})});
  assert.equal(videoOpened.status,201);
  const videoSession = await videoOpened.json();
  assert.equal((await fetch(`${api}/uploads/${videoSession.id}/chunks/0`, {method:"PUT",headers:{"X-Worker-Token":a.worker_token,"Content-Type":"application/octet-stream"},body:clip})).status,200);
  assert.equal((await fetch(`${api}/uploads/${videoSession.id}/complete`, {method:"POST",headers,body:JSON.stringify({client_sha256:clipHash})})).status,200);
  await submit(a);
  await page.getByRole("link",{name:`#${a.id}`,exact:true}).waitFor({timeout:22000});
  assert.equal(await page.getByText("Private Candidate",{exact:true}).count(),0);
  assert.equal((await page.locator("body").innerText()).includes("9876543210"),false);
  pass("New real submission appears on periodic refresh with pseudonym and no phone/PIN");
  assert.equal((await fetch(`${api}/assessments/${a.id}/evidence/1/content`)).status,401);
  assert.equal((await fetch(`${api}/reviewer/assessments/${a.id}/evidence/1/content`)).status,401);
  pass("Anonymous private evidence access is denied");
  await page.getByRole("link",{name:`#${a.id}`,exact:true}).click();
  const access = page.getByRole('dialog',{name:'Assessor details'});
  await access.waitFor();
  await access.getByText('Remember your password.',{exact:true}).waitFor();
  await access.getByText(/There is no forgot-password or password reset option/).waitFor();
  await access.getByLabel('Full name',{exact:true}).fill('Browser Assessor');
  await access.getByLabel('Email',{exact:true}).fill(accountEmail);
  await access.getByLabel('Phone number',{exact:true}).fill('9876543210');
  await access.getByLabel('Password',{exact:true}).fill(accountPassword);
  assert.equal(await access.getByRole('button',{name:'Create account and enter',exact:true}).isDisabled(),true);
  await access.getByRole('checkbox',{name:/must remember my password/}).check();
  await access.getByRole('button',{name:'Create account and enter',exact:true}).click();
  await access.waitFor({state:'detached'});
  await page.getByText(/Reviewing as Browser Assessor/).waitFor();
  pass('Opening an assessment prompts for name, email, phone and password, with required no-reset acknowledgement');
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("tab", {name:"Evidence",exact:true}).click();
  const photo = page.locator(".evidence-gallery img").first();
  await photo.waitFor();
  await page.waitForFunction(() => { const image=document.querySelector('.evidence-gallery img'); return image?.complete && image.naturalWidth > 0; });
  await page.getByRole("button",{name:"Open photo",exact:false}).click();
  await page.getByRole("dialog",{name:"Evidence viewer"}).waitFor();
  assert.equal(await page.getByRole("dialog").locator("img").evaluate(image=>image.complete && image.naturalWidth>0), true);
  await page.keyboard.press("Escape");
  const video = page.locator(".evidence-gallery video").first();
  await video.waitFor();
  await page.waitForFunction(() => document.querySelector('.evidence-gallery video')?.readyState >= 2);
  await video.evaluate(async v => { await v.play(); });
  await page.waitForFunction(() => document.querySelector('.evidence-gallery video')?.currentTime > .2);
  await video.evaluate(v => { v.pause(); v.currentTime = 1.5; });
  await page.waitForFunction(() => document.querySelector('.evidence-gallery video')?.currentTime >= 1.4);
  await page.getByRole("button",{name:"Open video",exact:false}).click();
  const expandedVideo = page.getByRole("dialog").locator("video");
  await expandedVideo.waitFor();
  await expandedVideo.evaluate(async v => { await v.play(); });
  await page.getByRole("button",{name:"Close",exact:true}).click();
  const detail = await (await context.request.get(`${api}/reviewer/assessments/${a.id}`)).json();
  const evidenceId = detail.tasks.find(task=>task.task_code==='T1').evidence.find(item=>item.kind==='video').id;
  const partial = await context.request.get(`${api}/reviewer/assessments/${a.id}/evidence/${evidenceId}/content`, {headers:{Range:"bytes=0-31"}});
  assert.equal(partial.status(),206);
  assert.equal((await partial.body()).length,32);
  mkdirSync('/tmp/parakh-ui-review', {recursive:true});
  await page.screenshot({path:'/tmp/parakh-ui-review/dashboard-evidence.png',fullPage:true});
  await page.route(`**/reviewer/assessments/${a.id}/evidence/**/content`, route=>route.fulfill({status:401,body:'{"detail":"expired"}',contentType:'application/json'}));
  await page.reload();
  // The HttpOnly assessor session restores private review after reload.
  await page.getByText(/Reviewing as Browser Assessor/).waitFor();
  await page.getByRole("tab",{name:"Evidence",exact:true}).click();
  await page.getByText(/Reviewer access expired or is unavailable/).first().waitFor();
  await page.unroute(`**/reviewer/assessments/${a.id}/evidence/**/content`);
  await page.getByRole("button",{name:"Retry media",exact:true}).first().click();
  await page.waitForFunction(() => { const image=document.querySelector('.evidence-gallery img'); return image?.complete && image.naturalWidth > 0; });
  pass("Real private photo opens; video plays, seeks and opens expanded; byte ranges, access expiry and retry work");
  await page.getByRole("tab", {name:"Scoring",exact:true}).click();
  await page.getByRole("heading",{name:"Performance criteria",exact:true}).waitFor();
  const first = page.locator(".criterion-card").first();
  await first.locator("select").nth(1).selectOption("NOT_OBSERVABLE");
  await first.getByRole("button",{name:"Save score",exact:true}).click();
  await first.getByText("A comment is required",{exact:false}).waitFor();
  await first.locator("textarea").fill("Evidence is not observable in this view.");
  await page.getByRole("tab",{name:"Evidence",exact:true}).click();
  await page.getByRole("tab",{name:"Scoring",exact:true}).click();
  assert.equal(await first.locator("textarea").inputValue(),"Evidence is not observable in this view.");
  const initialCriterion = await first.getByRole('heading').innerText();
  assert.ok(initialCriterion.length > 15 && !initialCriterion.startsWith('CON/'));
  assert.ok(await page.locator('.criterion-card').count() < 25);
  await first.getByText('See all scoring levels', {exact:true}).click();
  assert.equal(await first.locator('.rubric-guidance strong').count(), 4);
  await page.getByRole('complementary', {name:'Scoring tasks'}).getByRole('button', {name:/Tools and meter use/}).click();
  await page.getByRole('complementary', {name:'Scoring tasks'}).getByRole('button', {name:/Safety and PPE/}).click();
  assert.equal(await first.locator('textarea').inputValue(), 'Evidence is not observable in this view.');
  await page.screenshot({path:'/tmp/parakh-ui-review/dashboard-scoring.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:'/tmp/parakh-ui-review/dashboard-scoring-mobile.png',fullPage:true});
  await page.setViewportSize({width:1280,height:900});
  pass("Readable task scoring, complete anchors, mobile layout and drafts survive task and evidence navigation");
  await first.getByRole("button",{name:"Save score",exact:true}).click();
  await page.getByRole("button",{name:"Save score",exact:true}).first().waitFor();
  pass("Assessor session restoration and score/comment validation work");
  const csrf = (await context.cookies(api)).find(c=>c.name==="parakh_reviewer_csrf").value;
  const reviewResponse = await context.request.get(`${api}/reviewer/assessments/${a.id}/review`);
  const scores = await reviewResponse.json();
  for (const item of scores) {
    const scored = await context.request.put(`${api}/reviewer/assessments/${a.id}/review`, {headers:{"X-Reviewer-CSRF":csrf},data:{
      pc_full_id:item.pc_full_id,score_level:3,evidence_status:"DEMONSTRATED",expected_version:item.score?.version ?? 0}});
    assert.equal(scored.status(),200, await scored.text());
  }
  await page.getByRole("button",{name:"Refresh review"}).click();
  await page.getByRole("tab",{name:"Decision",exact:true}).click();
  await page.getByRole("checkbox",{name:/I have reviewed all evidence/}).check();
  await page.getByRole("button",{name:"Approve and sign report"}).click();
  await confirm(page,a.id,"sign_off",undefined,true);
  await page.getByRole('dialog', {name:'Report signed successfully',exact:true}).waitFor();
  await page.getByRole('heading', {name:'Assessment queue',exact:true}).waitFor();
  await page.goto(`${base}/#/assessments/${a.id}`);
  await page.getByRole("tabpanel").getByRole("link",{name:"Verify report",exact:true}).click();
  await page.getByText(/Signature verified/).first().waitFor();
  pass("Human-confirmed scores, wrong-password rejection, password signing and public QR verification");
  const b=await enroll("Consenting Candidate",true); await submit(b);
  await page.goto(`${base}/#/assessments/${b.id}`);
  await page.getByRole("heading",{name:"Consenting Candidate",exact:true}).waitFor();
  await page.getByText(/Reviewing as Browser Assessor/).waitFor();
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("tab",{name:"Decision",exact:true}).click();
  await page.getByRole("button",{name:"Request targeted reassessment",exact:true}).click();
  await confirm(page,b.id,"reassessment",async dialog=>{
    await dialog.getByLabel("Reason / remarks (required)").fill("Retake the board evidence.");
    await dialog.getByLabel("What to capture (required)").fill("Show the complete board.");
    await dialog.getByRole("checkbox",{name:/Temporary lighting and fault finding/}).check();
  },true);
  await page.getByRole('dialog', {name:'Reassessment requested',exact:true}).waitFor();
  await page.getByRole('heading', {name:'Assessment queue',exact:true}).waitFor();
  await page.goto(`${base}/#/assessments/${b.id}`);
  await page.getByText(/Review: needs_reassessment/).waitFor();
  await page.getByRole('tab', {name:'Audit & history',exact:true}).click();
  await page.locator('.reassessment-entry.request-pending').waitFor();
  await page.locator('.revision-current').waitFor();
  assert.match(await page.locator('.reassessment-entry').innerText(), /Temporary lighting and fault finding/);
  await page.screenshot({path:'/tmp/parakh-ui-review/dashboard-history.png',fullPage:true});
  pass("Targeted reassessment records reason, actor and precise task selection");
  const c=await enroll("Reject Candidate"); await submit(c);
  await page.goto(`${base}/#/assessments/${c.id}`);
  await page.getByText(/Reviewing as Browser Assessor/).waitFor();
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("tab",{name:"Decision",exact:true}).click();
  await page.getByRole("button",{name:"Reject / do not recommend",exact:true}).click();
  await confirm(page,c.id,"reject",async dialog=>{
    await dialog.getByLabel("Reason / remarks (required)").fill("Safety could not be demonstrated.");
  },true);
  await page.getByRole('dialog', {name:'Assessment marked not qualified',exact:true}).waitFor();
  await page.getByRole('heading', {name:'Assessment queue',exact:true}).waitFor();
  await page.goto(`${base}/#/assessments/${c.id}`);
  await page.getByText(/Review: not_recommended/).waitFor();
  pass("Rejection requires verified authorization, explicit confirmation and remarks");
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await page.getByRole('dialog',{name:'Assessor details'}).waitFor();
  await page.getByRole('button',{name:'Already registered? Sign in',exact:true}).click();
  const login = page.getByRole('dialog',{name:'Assessor sign in'});
  await login.getByLabel('Email',{exact:true}).fill(accountEmail);
  await login.getByLabel('Password',{exact:true}).fill(accountPassword);
  await login.getByRole('button',{name:'Sign in and enter',exact:true}).click();
  await login.waitFor({state:'detached'});
  await page.getByText(/Reviewing as Browser Assessor/).waitFor();
  pass('Logout removes private review and the same assessor can sign in again with the saved password');
  console.log(JSON.stringify({passed:checks.length,checks},null,2));
} finally { await browser.close(); }
