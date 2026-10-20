#!/usr/bin/env python3
"""Generate accessible, code-native diagrams for the README."""
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'docs/assets/readme'
OUT.mkdir(parents=True, exist_ok=True)
INK='#482b1b'; MUTED='#8c6c51'; GOLD='#b9844e'; PAPER='#fbf6ec'; LINE='#dfc9a9'; GREEN='#517765'

def text(x,y,value,size=18,fill=INK,weight='normal',family='Arial, sans-serif'):
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" font-family="{family}">{escape(value)}</text>'

def rect(x,y,w,h,fill='#fffdfa',stroke=LINE,r=16):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}"/>'

def line(x1,y1,x2,y2,color=GOLD,dash=''):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="2" fill="none" marker-end="url(#arrow)" {f"stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>'

def card(x,y,w,title,lines,tag=None,height=115):
    s=rect(x,y,w,height)
    if tag:
        s+=text(x+22,y+25,tag,11,GOLD,'bold')
    s+=text(x+22,y+(51 if tag else 34),title,21,INK,'bold')
    for i,v in enumerate(lines):s+=text(x+22,y+(77 if tag else 62)+i*24,v,15,MUTED)
    return s

def save(name,title,desc,body,height=900):
    head=f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" viewBox="0 0 1400 {height}" role="img" aria-labelledby="title desc"><title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{GOLD}"/></marker></defs>{rect(0,0,1400,height,PAPER,PAPER,0)}'
    (OUT/name).write_text(head+body+'</svg>')

def heading(kicker,title,subtitle):
    return text(55,53,kicker,12,GOLD,'bold')+text(55,107,title,43,INK,'normal','Georgia, serif')+text(55,143,subtitle,17,MUTED)

s=heading('SYSTEM ARCHITECTURE / IMPLEMENTED MVP','One evidence record. Three connected experiences.','Capture stays on the phone until connectivity is available. The assessor owns the final recommendation.')
s+=rect(50,180,1300,80,'#f0e2cb')+text(75,212,'PINNED QUALIFICATION PACK',11,GOLD,'bold')+text(75,241,'CON/Q0602 v4.0  ·  tasks, criteria, support rubrics and versioned mapping rules',20)
for x,label in [(50,'01 / ANDROID · OFFLINE'),(510,'02 / FASTAPI · CONNECTED'),(970,'03 / DASHBOARD · HUMAN REVIEW')]:
    s+=rect(x,305,380,473,'#f6ecdc',LINE)+text(x+22,338,label,12,GOLD,'bold')
s+=card(68,360,344,'Guided worker journey',['Local PIN · English / Hindi','Structured declaration and explained match'])
s+=card(68,492,344,'Capture and assistance',['CameraX photos / videos · Media3','Quality hints · sampled hand presence'])
s+=card(68,624,344,'Protected local package',['SQLCipher Room · durable outbox','SHA-256 · ECDSA · Tink encrypted vault'])
s+=card(528,360,344,'Upload and integrity',['Resumable chunks · hashes · quotas','Signed manifests · revision binding'])
s+=card(528,492,344,'Assessment services',['Lifecycle · human scores · profiles','Targeted revisions · immutable reports'])
s+=card(528,624,344,'Durable background worker',['Database-backed jobs and retry leases','FFmpeg / ffprobe · media metadata'])
s+=card(988,360,344,'Inspect the evidence',['Protected gallery and video playback','Task groups · shared 0–3 rubric anchors'])
s+=card(988,492,344,'Make the judgement',['Score · annotate · request recapture','Computed profile supports the assessor'])
s+=card(988,624,344,'Confirm and sign',['Fresh password and explicit confirmation','Ed25519 receipt over immutable PDF'])
s+=line(432,460,506,460)+text(440,443,'HTTPS',11,GOLD,'bold')
s+=line(894,460,965,460)+text(904,443,'API',11,GOLD,'bold')
s+=card(50,822,380,'Versioned assessment data',['PostgreSQL in deployed environments','SQLite used only in the README capture'],height=116)
s+=card(510,822,380,'Private media and reports',['Local volume for LAN / offline hosting','S3-compatible storage for hosted services'],height=116)
s+=card(970,822,380,'Public verification',['Report ID / QR → authenticity + outcome','Local PDF + receipt → offline verifier'],height=116)
s+=text(55,980,'DEPLOYMENT OPTIONS',11,GOLD,'bold')+text(55,1010,'Local / LAN: Docker Compose   ·   Hosted topology: Vercel dashboard + Railway API / worker + Neon data / storage',16,MUTED)
save('architecture.svg','PARAKH system architecture','The offline Android app seals evidence and later syncs to FastAPI. A durable worker processes private media. The dashboard supports human scoring and signed reports. PostgreSQL, private storage and a public verifier complete the system.',s,1040)

s=heading('THE END-TO-END WORKFLOW','From prior experience to a verifiable recommendation.','A worker-friendly capture flow, followed by a structured human assessment.')
steps=[('01','Declare experience',['Choose a language, consent,','set a local PIN and answer','task and tool cards.']),('02','Understand the match',['See the pilot QP fit,','declared coverage, reasons','and experience gaps.']),('03','Capture evidence',['Follow five task guides.','Record photos and videos','on the isolated training board.']),('04','Review and seal',['Optimize within the quota.','Hash, sign and encrypt','the evidence package.']),('05','Sync and assess',['Resume uploads when online.','An assessor reviews evidence','and scores each criterion.']),('06','Sign and verify',['Confirm the recommendation.','Issue an immutable signed PDF','and verify using its Report ID.'])]
for i,(num,title,lines_) in enumerate(steps):
    col=i%3;row=i//3;x=50+col*460;y=210+row*245
    s+=card(x,y,380,title,lines_,num,height=175)
    if col<2:s+=line(x+387,y+88,x+449,y+88)
s+=f'<path d="M1160 390V422H240V448" fill="none" stroke="{GOLD}" stroke-width="2" stroke-dasharray="5 7" marker-end="url(#arrow)"/>'
s+=rect(50,686,1300,62,'#e9eddf',LINE)+text(76,725,'01–04: WORKS OFFLINE',14,GREEN,'bold')+text(550,725,'05–06: SERVER REACHABILITY REQUIRED',14,GREEN,'bold')
save('workflow.svg','PARAKH worker to assessor workflow','Declare experience, explain the qualification match, capture task evidence, review and seal offline, then synchronize for human assessment and a verifiable signed report.',s,790)

s=heading('THE EVIDENCE PIPELINE','A capture becomes a protected, reviewable record.','Integrity travels with the evidence, from local storage to the assessor workspace.')
xs=[50,510,970]
for x,title,items,tag in [(50,'Capture and prepare',['CameraX photo / video','Preview · retake · replace · delete','Media3 optimization to task budget'],'ON THE PHONE'),(510,'Bind and protect',['Canonical manifest + SHA-256 hashes','Android Keystore ECDSA signature','Tink vault + durable Room outbox'],'STILL OFFLINE'),(970,'Resume and verify',['WorkManager streams 1 MiB chunks','Server checks manifest, hashes, quota','Finalize idempotently by revision'],'WHEN CONNECTED')]:
    s+=card(x,220,380,title,items,tag,height=190)
s+=line(435,315,502,315)+line(895,315,963,315)
s+=rect(50,460,1300,140,'#f0e2cb')+text(78,499,'TWO DISTINCT SIGNATURES',12,GOLD,'bold')
s+=text(78,538,'Evidence package: ECDSA',23,INK,'bold')+text(78,570,'Binds a device-signed manifest to evidence hashes.',16,MUTED)
s+=text(740,538,'Final report: Ed25519',23,INK,'bold')+text(740,570,'Binds the server signature to the exact PDF digest.',16,MUTED)
s+=text(55,654,'Encryption protects stored files. Signatures and hashes detect changes. Neither proves that a recorded skill was performed correctly.',16,MUTED)
save('evidence-pipeline.svg','PARAKH evidence integrity pipeline','The phone captures, optimizes, hashes, signs and encrypts evidence offline. Resumable upload verifies the package. Evidence ECDSA signatures and final PDF Ed25519 signatures have separate roles.',s,700)

s=heading('TARGETED REASSESSMENT','Ask for the missing proof. Keep the rest.','A new revision preserves the relationship between original evidence and the requested recapture.')
for x,title,lines_,tag in [(50,'Assessor requests T2',['A reason is required.','Capture instructions explain','which detail must be visible.'],'01 / REVIEW'),(510,'Worker recaptures T2',['The phone unlocks the requested task.','Other tasks keep their prior evidence.','A new package records the revision.'],'02 / RECAPTURE'),(970,'Review the new revision',['Upload only the replacement evidence.','Inherit unchanged tasks by reference.','Keep requests and history auditable.'],'03 / RESUBMIT')]:s+=card(x,215,380,title,lines_,tag,height=195)
s+=line(435,308,502,308)+line(895,308,963,308)
for i in range(5):
 x=74+i*250; color='#dbe7da' if i==1 else '#f0e3cd'
 s+=rect(x,478,220,90,color)+text(x+22,513,'T'+str(i+1),17,GREEN if i==1 else INK,'bold')+text(x+22,545,'New evidence' if i==1 else 'Inherited by reference',14,MUTED)
save('reassessment.svg','Task-specific reassessment','Only the requested task is reopened and recaptured. The new revision inherits unchanged tasks by reference and preserves the request reason and evidence history.',s,620)

s=heading('PILOT TASK PACK / CON/Q0602 v4.0','Five practical tasks. A bounded evidence package.','The 120 MiB limit applies to final optimized media; each task has its own allowance.')
tasks=[('T1','Safety and PPE',15,'#b78b58'),('T2','Tools and meter use',20,'#9c7650'),('T3','LV switchboard wiring',30,'#755238'),('T4','Temporary lighting / fault',25,'#b49b71'),('T5','Temporary LV panel',30,'#6c8062')]
x=55
for code,title,mb,color in tasks:
 w=1290*mb/120;s+=rect(x,210,w-3,56,color,color,0)+text(x+14,245,f'{code} / {mb} MiB',16,'#fff9ee','bold');x+=w
for i,(code,title,mb,color) in enumerate(tasks):
 y=319+i*58;s+=rect(55,y-23,42,32,color,color,7)+text(63,y,code,14,'#fff9ee','bold')+text(120,y,title,19)+text(1130,y,str(mb)+' MiB',19,MUTED)
s+=text(55,653,'TOTAL',12,GOLD,'bold')+text(55,696,'120 MiB = 125,829,120 bytes',32,INK,'normal','Georgia, serif')+text(55,735,'Capture on a supervised, isolated training board. A qualified supervisor handles any powered verification.',16,MUTED)
save('task-budgets.svg','Five PARAKH evidence tasks and their budgets','Safety 15 MiB, tools and meter use 20 MiB, switchboard wiring 30 MiB, temporary lighting and fault 25 MiB, temporary LV panel 30 MiB. Total 120 MiB.',s,780)
print('Generated five accessible SVG diagrams')
