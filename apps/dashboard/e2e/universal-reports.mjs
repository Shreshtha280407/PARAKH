// Real local API/PDF tests. No production endpoints, synthetic signing bypasses,
// mocked verification responses or public media endpoints are used.
import assert from 'node:assert/strict';
import {randomBytes,randomUUID,createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {chromium} from 'playwright';

const base=process.env.REPORT_DASHBOARD_URL ?? 'http://127.0.0.1:18187';
const api=process.env.REPORT_API_URL ?? 'http://127.0.0.1:18188';
assert.equal(new URL(api).origin,'http://127.0.0.1:18188','Use only the isolated report-test API');
assert.equal(new URL(base).origin,'http://127.0.0.1:18187','Use only the isolated report-test dashboard');
const artifacts='/tmp/parakh-universal-reports-review';
mkdirSync(artifacts,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.P8_CHROME?{executablePath:process.env.P8_CHROME}:{})});
const checks=[],errors=[];
const pass=message=>{checks.push(message);console.log('PASS '+message)};
const password=randomBytes(24).toString('hex');
try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const registration=await context.request.post(api+'/reviewer/accounts',{data:{name:'Report Regression Assessor',email:`reports-${randomUUID()}@example.invalid`,phone:'9876543210',password,password_acknowledged:true}});
  assert.equal(registration.status(),201,await registration.text());
  const csrf=(await context.cookies(api)).find(cookie=>cookie.name==='parakh_reviewer_csrf').value;
  const headers={'X-Reviewer-CSRF':csrf};
  async function enroll(name,consent=false) {
    const response=await context.request.post(api+'/workers/enroll',{data:{device_worker_id:'KP-'+randomUUID(),enrollment_secret:randomBytes(32).toString('hex'),client_assessment_id:randomUUID(),full_name:name,phone:'+919876543210',public_name_consent:consent}});
    assert.equal(response.status(),200,await response.text());const a=await response.json();
    assert.equal((await context.request.post(`${api}/assessments/${a.id}/submit`,{headers:{'X-Worker-Token':a.worker_token}})).status(),200);
    assert.equal((await context.request.post(`${api}/reviewer/assessments/${a.id}/start-review`,{headers})).status(),200);
    return a;
  }
  async function confirm(wrong=false) {
    const dialog=page.getByRole('dialog',{name:/^Confirm/});
    await dialog.getByRole('checkbox',{name:/explicitly confirm/}).check();
    if(wrong){
      await dialog.getByLabel('Confirm your password',{exact:true}).fill('incorrect-password');
      await dialog.getByRole('button',{name:'Confirm action',exact:true}).click();
      await dialog.getByRole('alert').filter({hasText:'incorrect password'}).waitFor();
      assert.equal(await dialog.getByLabel('Confirm your password',{exact:true}).inputValue(),'');
    }
    await dialog.getByLabel('Confirm your password',{exact:true}).fill(password);
    await dialog.getByRole('button',{name:'Confirm action',exact:true}).click();
    await dialog.waitFor({state:'detached'});
    await page.getByRole('heading',{name:'Assessment queue',exact:true}).waitFor();
  }
  async function publication(a,consent=true){
    const response=await context.request.put(`${api}/assessments/${a.id}/public-outcome-consent`,{headers:{'X-Worker-Token':a.worker_token},data:{consent,consent_version:'public-outcome-v1'}});
    assert.equal(response.status(),200,await response.text());
  }
  async function reportPanel(a) {
    await page.goto(`${base}/#/assessments/${a.id}`);
    const panel=page.getByRole('region',{name:'Signed assessment report'});
    await panel.waitFor();
    const detail=await (await context.request.get(`${api}/reviewer/assessments/${a.id}`)).json();
    const report=detail.signed_report;
    await panel.getByText(report.report_uid,{exact:true}).waitFor();
    const download=await panel.getByRole('link',{name:'Download Signed PDF',exact:true}).getAttribute('href');
    const pdf=await context.request.get(download);
    assert.equal(pdf.status(),200);const bytes=await pdf.body();
    assert.equal(createHash('sha256').update(bytes).digest('hex'),report.pdf_sha256);
    assert.ok(bytes.includes(Buffer.from(report.final_recommendation)));
    assert.equal(pdf.headers()['cache-control'],'private, no-store');
    assert.equal(await panel.getByRole('link',{name:'Verify Report',exact:false}).getAttribute('href'),'#/verify/'+report.report_uid);
    return report;
  }

  const positive=await enroll('Private Positive Candidate');
  await page.goto(`${base}/#/assessments/${positive.id}`);
  await page.getByText(/Reviewing as Report Regression Assessor/).waitFor();
  assert.equal(await page.getByRole('region',{name:'Signed assessment report'}).count(),0);
  pass('In-review assessment has no signed Report ID or download link');
  const review=await (await context.request.get(`${api}/reviewer/assessments/${positive.id}/review`)).json();
  for(const item of review){
    const response=await context.request.put(`${api}/reviewer/assessments/${positive.id}/review`,{headers,data:{pc_full_id:item.pc_full_id,score_level:3,evidence_status:'DEMONSTRATED',expected_version:0}});
    assert.equal(response.status(),200,await response.text());
  }
  await page.reload();await page.getByText(/Reviewing as Report Regression Assessor/).waitFor();
  await page.getByRole('tab',{name:'Decision',exact:true}).click();
  await page.getByRole('checkbox',{name:/I have reviewed all evidence/}).check();
  await page.getByRole('button',{name:'Finalize and sign report',exact:true}).click();
  await confirm(true);
  const positiveReport=await reportPanel(positive);
  assert.equal(positiveReport.final_recommendation,'RECOMMEND_CERTIFICATION');
  pass('Positive finalization uses actual human scores, rejects a wrong password, displays Report ID and downloads bytes matching SHA-256');

  const negative=await enroll('Consented Negative Candidate',true);
  await page.goto(`${base}/#/assessments/${negative.id}`);await page.getByText(/Reviewing as Report Regression Assessor/).waitFor();
  await page.getByRole('tab',{name:'Decision',exact:true}).click();
  await page.getByRole('button',{name:'Reject / do not recommend',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Reason / remarks (required)').fill('The isolated safety check has not been demonstrated.');
  await confirm(true);
  const negativeReport=await reportPanel(negative);
  assert.equal(negativeReport.final_recommendation,'NOT_YET_COMPETENT');
  const negativePanel=page.getByRole('region',{name:'Signed assessment report'});
  await negativePanel.getByText('Not Recommended',{exact:true}).waitFor();
  await page.screenshot({path:artifacts+'/negative-detail-desktop.png',fullPage:true});
  pass('Reject finalizes Not Recommended, issues a signed PDF, and shows the correct outcome and Report ID after reopening');
  let listing=await (await context.request.get(api+'/public/reports')).json();
  assert.ok(!listing.some(row=>[positive.id,negative.id].includes(row.id)));
  await negativePanel.getByText(/Not listed publicly/).waitFor();
  pass('Name consent alone never publishes a positive or negative outcome in the searchable directory');
  await publication(positive);await publication(negative);
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Public queue',exact:true}).click();
  for(const [report,outcome] of [[positiveReport,/Recommended/],[negativeReport,/Not Recommended/i]]){
    const row=page.locator('.public-report').filter({hasText:report.report_uid});
    await row.waitFor();await row.locator('.status').filter({hasText:outcome}).waitFor();
    assert.match(await row.innerText(),/Issued/);
    assert.equal(await row.getByRole('link',{name:'Verify Report',exact:false}).getAttribute('href'),'#/verify/'+report.report_uid);
  }
  await page.screenshot({path:artifacts+'/public-signed-outcomes.png',fullPage:true});
  pass('Consented positive and negative reports both appear with outcome, Report ID, issuance date and verification link');

  const anonymous=await browser.newContext({viewport:{width:390,height:844}});
  const verifyPage=await anonymous.newPage();verifyPage.on('pageerror',e=>errors.push(e.message));
  for(const [report,label] of [[positiveReport,'Recommended'],[negativeReport,'Not Recommended']]){
    const proof=await anonymous.request.get(`${api}/verify/${report.report_uid}`);
    assert.equal(proof.status(),200);assert.equal(proof.headers()['cache-control'],'no-store');
    assert.equal((await proof.json()).valid,true);
    await verifyPage.goto(`${base}/#/verify/${report.report_uid}`);
    await verifyPage.getByText('Signature verified',{exact:true}).waitFor();
    await verifyPage.getByText(label,{exact:true}).waitFor();
    const body=await verifyPage.locator('main').innerText();
    for(const forbidden of ['Consented Negative Candidate','Private Positive Candidate','9876543210','@example.invalid','Safety criteria','scoring evidence'])assert.ok(!body.includes(forbidden));
    assert.ok(body.includes(report.pdf_sha256));
    assert.ok(body.includes('A downloaded or uploaded copy has not been checked here.'));
    assert.ok(await verifyPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await verifyPage.screenshot({path:artifacts+'/negative-verification-phone.png',fullPage:true});
  pass('Anonymous phone verification separates valid signatures from positive/negative outcomes, retains SHA-256, and reveals no identity/contact/evidence');

  // Deliberately corrupt only the test fixture's local stored file. No product
  // tampering endpoint exists. The original bytes are restored in finally.
  const fixture=`/tmp/parakh-universal-reports-storage/reports/${negativeReport.report_uid}.pdf`;
  const original=readFileSync(fixture);
  try {
    const altered=Buffer.from(original);altered[altered.length-10]^=1;writeFileSync(fixture,altered);
    await verifyPage.reload();await verifyPage.getByText('Verification failed',{exact:true}).waitFor();
    await verifyPage.getByText('Unverified recorded outcome',{exact:true}).waitFor();
    assert.equal(await verifyPage.getByText('Verification failed',{exact:true}).evaluate(el=>getComputedStyle(el).color),
      await verifyPage.locator('.verify-icon').evaluate(el=>getComputedStyle(el).color));
    assert.ok(await verifyPage.getByText('Unverified recorded outcome',{exact:true}).evaluate(el=>el.classList.contains('status-unverified')));
    assert.equal(await verifyPage.getByText('Signature verified',{exact:true}).count(),0);
    assert.equal((await context.request.get(`${api}/reviewer/assessments/${negative.id}/report?format=pdf`)).status(),409);
    await verifyPage.screenshot({path:artifacts+'/tamper-failure-phone.png',fullPage:true});
  } finally {writeFileSync(fixture,original)}
  pass('Actual stored-PDF tampering produces verification failure and blocks signed-PDF download');
  await verifyPage.goto(`${base}/#/verify/no-such-report-${randomUUID()}`);
  await verifyPage.getByRole('alert').filter({hasText:'Report not found'}).waitFor();
  await verifyPage.getByRole('link',{name:'Try another report',exact:true}).click();
  await verifyPage.getByRole('heading',{name:'Find a signed report',exact:true}).waitFor();
  pass('Invalid-ID and missing-ID states provide a useful report search path');
  await publication(negative,false);
  await page.reload();await page.locator('.public-report').filter({hasText:positiveReport.report_uid}).waitFor();
  await page.locator('.public-report').filter({hasText:negativeReport.report_uid}).waitFor({state:'detached'});
  assert.equal((await anonymous.request.get(`${api}/reviewer/assessments/${negative.id}/report?format=pdf`)).status(),401);
  assert.equal((await anonymous.request.get(`${api}/reviewer/assessments/${negative.id}/evidence/1/content`)).status(),401);
  pass('Consent revocation removes the directory entry, while anonymous report/evidence downloads remain protected');
  await page.setViewportSize({width:390,height:844});await reportPanel(negative);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:artifacts+'/negative-detail-phone.png',fullPage:true});
  pass('Negative signed report controls and Report ID fit on a phone without horizontal overflow');
  const privateMode=await browser.newContext();
  await privateMode.route('**/config.json',route=>route.fulfill({json:{apiBaseUrl:api,accessMode:'private'}}));
  const privateVerify=await privateMode.newPage();privateVerify.on('pageerror',e=>errors.push(e.message));
  await privateVerify.goto(`${base}/#/verify`);
  await privateVerify.getByRole('heading',{name:'Find a signed report',exact:true}).waitFor();
  await privateVerify.getByLabel('Report ID',{exact:true}).fill(negativeReport.report_uid);
  await privateVerify.getByRole('button',{name:'Verify report',exact:true}).click();
  await privateVerify.getByText('Signature verified',{exact:true}).waitFor();
  await privateVerify.getByText('Not Recommended',{exact:true}).waitFor();
  await privateVerify.getByRole('link',{name:'Verify another report',exact:false}).click();
  await privateVerify.getByRole('heading',{name:'Find a signed report',exact:true}).waitFor();
  pass('Private dashboard mode also permits anonymous report search, negative verification and verify-another navigation');
  assert.deepEqual(errors,[]);
  pass('No JavaScript errors across the report workflow');
  writeFileSync(artifacts+'/verification.json',JSON.stringify({checkedAt:new Date().toISOString(),checks,errors},null,2)+'\n');
  console.log(JSON.stringify({passed:checks.length,errors}));
} finally {await browser.close()}
