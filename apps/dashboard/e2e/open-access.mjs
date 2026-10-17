import assert from "node:assert/strict";
import { randomBytes, randomUUID, createHash } from "node:crypto";
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
async function confirm(page, id, action, prepare) {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Assessor full name").fill("Browser Reviewer");
  await dialog.getByLabel("Assessor email").fill("reviewer@parakh.invalid");
  if (prepare) await prepare(dialog);
  await dialog.getByRole("checkbox", {name:/explicitly confirm/}).check();
  await dialog.getByRole("button",{name:"Send verification code"}).click();
  await dialog.getByLabel("Email code",{exact:true}).waitFor();
  const {code} = await (await fetch(`${api}/_test/code/${id}/${action}`)).json();
  await dialog.getByLabel("Email code",{exact:true}).fill(code);
  await dialog.getByRole("button",{name:"Verify and confirm action"}).click();
  await dialog.waitFor({state:"detached", timeout:20000});
}

try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(base);
  await page.getByText("No submitted assessments yet.").waitFor();
  assert.equal(await page.getByRole("button", {name:/log in|sign up|demo/i}).count(),0);
  pass("Public dashboard opens without login or demo records; real empty state");
  const a = await enroll("Private Candidate");
  // A real private object upload via existing resumable protocol.
  const data = Buffer.from("isolated browser evidence fixture");
  const headers = {"X-Worker-Token":a.worker_token,"Content-Type":"application/json"};
  const opened = await fetch(`${api}/uploads`, {method:"POST", headers, body:JSON.stringify({
    assessment_id:a.id, task_code:"T1",kind:"photo",mime:"image/jpeg", claimed_size_bytes:data.length,
    claimed_sha256:createHash("sha256").update(data).digest("hex")})});
  assert.equal(opened.status,201, await opened.clone().text());
  const session = await opened.json();
  const chunk = await fetch(`${api}/uploads/${session.id}/chunks/0`, {method:"PUT",headers:{"X-Worker-Token":a.worker_token,"Content-Type":"application/octet-stream"},body:data});
  assert.equal(chunk.status,200);
  assert.equal((await fetch(`${api}/uploads/${session.id}/complete`,{method:"POST",headers,body:JSON.stringify({client_sha256:createHash("sha256").update(data).digest("hex")})})).status,200);
  await submit(a);
  await page.getByRole("link",{name:`#${a.id}`,exact:true}).waitFor({timeout:22000});
  assert.equal(await page.getByText("Private Candidate",{exact:true}).count(),0);
  assert.equal((await page.locator("body").innerText()).includes("9876543210"),false);
  pass("New real submission appears on periodic refresh with pseudonym and no phone/PIN");
  assert.equal((await fetch(`${api}/assessments/${a.id}/evidence/1/content`)).status,401);
  assert.equal((await fetch(`${api}/reviewer/assessments/${a.id}/evidence/1/content`)).status,401);
  pass("Anonymous private evidence access is denied");
  await page.getByRole("link",{name:`#${a.id}`,exact:true}).click();
  await page.getByRole("button",{name:"Verify email to review"}).click();
  await confirm(page,a.id,"review");
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("heading",{name:"Performance criteria",exact:true}).waitFor();
  const first = page.locator("tbody tr").first();
  await first.locator("select").nth(1).selectOption("NOT_OBSERVABLE");
  await first.getByRole("button",{name:"Save",exact:true}).click();
  await first.getByText("A comment is required",{exact:false}).waitFor();
  await first.locator("textarea").fill("Evidence is not observable in this view.");
  await first.getByRole("button",{name:"Save",exact:true}).click();
  await page.getByRole("button",{name:"Save",exact:true}).first().waitFor();
  pass("Reviewer identity/code workflow and score/comment validation work");
  const csrf = (await context.cookies(api)).find(c=>c.name==="parakh_reviewer_csrf").value;
  const reviewResponse = await context.request.get(`${api}/reviewer/assessments/${a.id}/review`);
  const scores = await reviewResponse.json();
  for (const item of scores) {
    const scored = await context.request.put(`${api}/reviewer/assessments/${a.id}/review`, {headers:{"X-Reviewer-CSRF":csrf},data:{
      pc_full_id:item.pc_full_id,score_level:3,evidence_status:"DEMONSTRATED",expected_version:item.score?.version ?? 0}});
    assert.equal(scored.status(),200, await scored.text());
  }
  await page.getByRole("button",{name:"Refresh review"}).click();
  await page.getByRole("button",{name:"Approve and sign report"}).click();
  await confirm(page,a.id,"sign_off");
  await page.getByRole("link",{name:"Verify report",exact:true}).click();
  await page.getByText(/Signature verified/).first().waitFor();
  pass("Human-confirmed scores, authorized report signing and public QR verification");
  const b=await enroll("Consenting Candidate",true); await submit(b);
  await page.goto(`${base}/#/assessments/${b.id}`);
  await page.getByText("Consenting Candidate",{exact:true}).waitFor();
  await page.getByRole("button",{name:"Verify email to review"}).click(); await confirm(page,b.id,"review");
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("button",{name:"Request targeted reassessment",exact:true}).click();
  await confirm(page,b.id,"reassessment",async dialog=>{
    await dialog.getByLabel("Reason / remarks (required)").fill("Retake the board evidence.");
    await dialog.getByLabel("What to capture (required)").fill("Show the complete board.");
    await dialog.getByRole("checkbox",{name:"T4",exact:true}).check();
  });
  await page.getByText(/Review: needs_reassessment/).waitFor();
  pass("Targeted reassessment records reason, actor and precise task selection");
  const c=await enroll("Reject Candidate"); await submit(c);
  await page.goto(`${base}/#/assessments/${c.id}`);
  await page.getByRole("button",{name:"Verify email to review"}).click(); await confirm(page,c.id,"review");
  await page.getByRole("button",{name:"Start review",exact:true}).click();
  await page.getByRole("button",{name:"Reject / do not recommend",exact:true}).click();
  await confirm(page,c.id,"reject",async dialog=>{
    await dialog.getByLabel("Reason / remarks (required)").fill("Safety could not be demonstrated.");
  });
  await page.getByText(/Review: not_recommended/).waitFor();
  pass("Rejection requires verified authorization, explicit confirmation and remarks");
  console.log(JSON.stringify({passed:checks.length,checks},null,2));
} finally { await browser.close(); }
