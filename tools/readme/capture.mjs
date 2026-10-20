/** Real browser capture. Live site is read-only; decisions use localhost only. */
import {chromium} from '../../apps/dashboard/node_modules/playwright/index.mjs';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {randomBytes,randomUUID,createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'../..');
const out=path.join(root,'docs/assets/readme');
const raw='/tmp/parakh-readme-capture/browser';
mkdirSync(out,{recursive:true});mkdirSync(raw,{recursive:true});
const base='http://127.0.0.1:18197',api='http://127.0.0.1:18198';
const browser=await chromium.launch({headless:true,executablePath:process.env.P8_CHROME||'/opt/google/chrome/chrome',args:['--no-sandbox']});
const errors=[],checks=[];
const hold=page=>page.waitForTimeout(1700);
async function shot(page,name){await page.evaluate(()=>document.fonts.ready);await hold(page);await page.screenshot({path:`${out}/${name}.png`});console.log('CAPTURE '+name)}
async function json(context,url,options={}){const r=await context.request.fetch(url,options);assert.ok(r.ok(),`${r.status()} ${await r.text()}`);return r.json()}
try{
  if(!process.env.SKIP_LIVE){
  const live=await browser.newContext({viewport:{width:1440,height:960},deviceScaleFactor:1,recordVideo:{dir:raw,size:{width:1440,height:960}}});
  const landing=await live.newPage();landing.on('pageerror',e=>errors.push('live: '+e.message));
  await landing.goto('https://parakh-dashboard-five.vercel.app',{waitUntil:'networkidle'});
  await shot(landing,'live-landing');
  const sections=await landing.locator('section').count();
  for(let i=1;i<Math.min(sections,7);i++){
    await landing.locator('section').nth(i).scrollIntoViewIfNeeded();await hold(landing);
    if(i===3)await shot(landing,'live-workflow');
  }
  await landing.evaluate(()=>window.scrollTo({top:0,behavior:'smooth'}));await hold(landing);
  const liveVideo=landing.video();await live.close();await liveVideo.saveAs(`${out}/live-product-tour.webm`);
  checks.push('Live landing captured read-only from the supplied Vercel URL');
  }

  const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,recordVideo:{dir:raw,size:{width:1440,height:1000}}});
  const password=randomBytes(24).toString('hex');
  await json(context,api+'/reviewer/accounts',{method:'POST',data:{name:'PARAKH Demo Assessor',email:`readme-${randomUUID()}@example.invalid`,phone:'9876543210',password,password_acknowledged:true}});
  const csrf=(await context.cookies(api)).find(c=>c.name==='parakh_reviewer_csrf').value;
  const headers={'X-Reviewer-CSRF':csrf};
  async function enroll(name){return json(context,api+'/workers/enroll',{method:'POST',data:{device_worker_id:'KP-'+randomUUID(),enrollment_secret:randomBytes(32).toString('hex'),client_assessment_id:randomUUID(),full_name:name,phone:'+919876543210',public_name_consent:true}})}
  async function upload(a,filename,kind){
    const data=readFileSync(path.join(root,'apps/dashboard/e2e/fixtures',filename));
    const hash=createHash('sha256').update(data).digest('hex');
    const wh={'X-Worker-Token':a.worker_token};
    const u=await json(context,api+'/uploads',{method:'POST',headers:wh,data:{assessment_id:a.id,task_code:'T1',kind,mime:kind==='photo'?'image/jpeg':'video/mp4',claimed_size_bytes:data.length,claimed_sha256:hash}});
    const chunk=await context.request.put(`${api}/uploads/${u.id}/chunks/0`,{headers:{...wh,'Content-Type':'application/octet-stream'},data});assert.ok(chunk.ok());
    await json(context,`${api}/uploads/${u.id}/complete`,{method:'POST',headers:wh,data:{client_sha256:hash}});
  }
  const a=await enroll('Sample Candidate · Product Walkthrough');
  await upload(a,'evidence.jpg','photo');await upload(a,'evidence.mp4','video');
  await json(context,`${api}/assessments/${a.id}/submit`,{method:'POST',headers:{'X-Worker-Token':a.worker_token}});
  const extra=await enroll('Sample Candidate · Awaiting Review');
  await json(context,`${api}/assessments/${extra.id}/submit`,{method:'POST',headers:{'X-Worker-Token':extra.worker_token}});
  const page=await context.newPage();page.on('pageerror',e=>errors.push('local: '+e.message));
  await page.goto(base+'/#/queue');await page.getByRole('heading',{name:'Assessment queue',exact:true}).waitFor();
  await shot(page,'dashboard-queue');
  await page.getByRole('link',{name:`Open assessment ${a.id}`,exact:true}).click();
  await page.getByText(/Reviewing as PARAKH Demo Assessor/).waitFor();
  await shot(page,'dashboard-overview');
  await page.getByRole('button',{name:'Start review',exact:true}).click();
  await page.getByRole('tab',{name:'Evidence',exact:true}).click();await shot(page,'dashboard-evidence');
  await page.getByRole('tab',{name:'Scoring',exact:true}).click();await shot(page,'dashboard-scoring');
  await page.locator('.criterion-card').first().getByRole('combobox',{name:/Performance level/}).selectOption('3');
  await page.locator('.criterion-card').first().getByRole('button',{name:'Save score',exact:true}).click();await hold(page);
  await page.getByRole('tab',{name:'Decision',exact:true}).click();await shot(page,'dashboard-decision');
  await page.getByRole('button',{name:'Request targeted reassessment',exact:true}).click();
  const reassess=page.getByRole('dialog');
  await reassess.getByLabel('Reason / remarks (required)').fill('Please show the isolated continuity test more clearly.');
  await reassess.getByLabel('What to capture (required)').fill('Record a close view of the meter display and both test points on the isolated training board.');
  await reassess.getByRole('checkbox',{name:/Tools and meter use/}).check();
  await shot(page,'dashboard-reassessment');
  await reassess.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.getByRole('tab',{name:'Audit & history',exact:true}).click();await shot(page,'dashboard-history');
  checks.push('Authenticated sample queue, protected media, score save, reassessment dialog and audit history captured against real local API');
  const reviewVideo=page.video();await page.close();await reviewVideo.saveAs(`${out}/assessor-review.webm`);

  // Scripted sample scores demonstrate report mechanics, not occupational validation.
  const reviews=await json(context,`${api}/reviewer/assessments/${a.id}/review`);
  for(const row of reviews){await json(context,`${api}/reviewer/assessments/${a.id}/review`,{method:'PUT',headers,data:{pc_full_id:row.pc_full_id,score_level:3,evidence_status:'DEMONSTRATED',expected_version:row.score?.version??0,comment:'Scripted README demonstration using sample records.'}})}
  const signing=await context.newPage();signing.on('pageerror',e=>errors.push('signing: '+e.message));
  await signing.goto(`${base}/#/assessments/${a.id}`);await signing.getByText(/Reviewing as PARAKH Demo Assessor/).waitFor();
  await signing.getByRole('tab',{name:'Decision',exact:true}).click();
  await signing.getByRole('checkbox',{name:/I have reviewed all evidence/}).check();
  await signing.getByRole('button',{name:'Finalize and sign report',exact:true}).click();
  const confirm=signing.getByRole('dialog');await confirm.getByRole('checkbox',{name:/explicitly confirm/}).check();
  await confirm.getByLabel('Confirm your password',{exact:true}).fill(password);await shot(signing,'dashboard-signoff');
  await confirm.getByRole('button',{name:'Confirm action',exact:true}).click();
  await signing.getByRole('heading',{name:'Assessment queue',exact:true}).waitFor();
  await signing.goto(`${base}/#/assessments/${a.id}`);await signing.getByRole('region',{name:'Signed assessment report'}).waitFor();await shot(signing,'dashboard-report');
  const detail=await json(context,`${api}/reviewer/assessments/${a.id}`),report=detail.signed_report;
  const pdf=await context.request.get(`${api}/reviewer/assessments/${a.id}/report?format=pdf`);assert.ok(pdf.ok());
  assert.equal(createHash('sha256').update(await pdf.body()).digest('hex'),report.pdf_sha256);
  await signing.close();await context.close();
  const anonymous=await browser.newContext({viewport:{width:1440,height:960}});
  const proof=await anonymous.newPage();await proof.goto(`${base}/#/verify/${report.report_uid}`);
  await proof.getByText('Signature verified',{exact:true}).waitFor();await shot(proof,'report-verification');
  const proofText=await proof.locator('main').innerText();assert.ok(!proofText.includes('Sample Candidate'));
  await proof.setViewportSize({width:390,height:844});await shot(proof,'report-verification-mobile');
  assert.ok(await proof.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  checks.push('Signed PDF SHA-256 matches downloaded bytes; anonymous verification succeeds without exposing sample candidate identity; phone layout fits');
  await anonymous.close();
  assert.deepEqual(errors,[]);
  writeFileSync(`${out}/capture-manifest.json`,JSON.stringify({capturedAt:new Date().toISOString(),liveUrl:'https://parakh-dashboard-five.vercel.app',localApi:api,localDatabase:'disposable SQLite',sampleData:true,checks,errors},null,2)+'\n');
  console.log(JSON.stringify({checks,errors}));
}finally{await browser.close()}
