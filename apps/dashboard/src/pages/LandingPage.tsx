import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { BrandEmblem } from '../components/DashboardShell';
import './landing.css';

const TASKS = [
  { title: 'Safety & protection', short: 'Safety', budget: 15, code: 'CON/N9001', detail: 'Good work begins before the first connection.', evidence: 'Protective equipment, supply isolation, a tester check, and a safe work area.', focus: 'safety' },
  { title: 'Tools & meter use', short: 'Tools', budget: 20, code: 'CON/N0602', detail: 'The right tool. The right reading.', evidence: 'Tool checks, correct handling, measurements, and close-ups of meter readings.', focus: 'tools' },
  { title: 'Low-voltage wiring', short: 'Wiring', budget: 30, code: 'CON/N0604', detail: 'Let every connection tell its story.', evidence: 'A training-board overview, clear terminal close-ups, earthing, and a continuity check.', focus: 'wiring' },
  { title: 'Temporary lighting', short: 'Lighting', budget: 25, code: 'CON/N0603', detail: 'Make the fix as visible as the fault.', evidence: 'The lighting arrangement, an isolated fault, and before-and-after evidence of the repair.', focus: 'lighting' },
  { title: 'Electrical panels', short: 'Panels', budget: 30, code: 'CON/N0605', detail: 'See how the whole system comes together.', evidence: 'Panel assembly, cable terminations, earthing, and clear labelling for supervisor inspection.', focus: 'panel' },
] as const;

const CHAPTERS = [
  { word: 'Capture.', eyebrow: '01 / THE WORKER', title: 'Good work happens everywhere.', text: 'A signal shouldn’t decide when someone can show their skills. Workers declare their experience, follow task guides, and capture photos and videos right on their phone.', note: 'English & Hindi · Capture works offline', label: 'Capture evidence' },
  { word: 'Preserve.', eyebrow: '02 / THE EVIDENCE', title: 'Every detail has a chain of trust.', text: 'Preview the final evidence, confirm it is your own work, then seal it. Files are encrypted on the phone and checked for integrity when they arrive. Interrupted uploads can resume.', note: 'Preview → seal → sync → verified receipt', label: 'Seal and sync' },
  { word: 'Recognise.', eyebrow: '03 / THE ASSESSOR', title: 'Technology assists. People decide.', text: 'Assessors see the work, score against clear behavioural anchors, and review the competency profile. They can request focused new evidence or sign a report with their recommendation.', note: 'Human scoring · Task-specific reassessment · Signed PDF', label: 'Human review' },
] as const;

function Arrow({ diagonal = false }: { diagonal?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d={diagonal ? 'M6 18 18 6M6 6h12v12' : 'M4 12h15m-6-6 6 6-6 6'} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Mark({ type, className = '' }: { type: 'check' | 'shield' | 'camera' | 'signal' | 'spark' | 'pause' | 'play'; className?: string }) {
  const paths = {
    check: <path d="m5 12 4 4L19 6" />,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
    camera: <><rect x="3" y="6" width="18" height="14" rx="3" /><circle cx="12" cy="13" r="4" /><path d="m7 6 2-3h6l2 3" /></>,
    signal: <><path d="M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0" /><circle cx="12" cy="20" r=".5" /></>,
    spark: <><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z" /></>,
    pause: <><path d="M8 5v14M16 5v14" /></>,
    play: <path d="m8 4 12 8-12 8V4Z" />,
  };
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[type]}</svg>;
}

function EnterLink({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <a className={`lp-enter ${className}`} href="#/queue" onClick={() => window.scrollTo(0, 0)}>{children}<Arrow /></a>;
}

function TaskSchematic({ focus }: { focus: string }) {
  if (focus === 'safety') return <g stroke="#c6a575" strokeWidth="2" strokeLinejoin="round">
    <path d="M82 165v-13a80 80 0 0 1 160 0v13" fill="#be975f" /><path d="M139 154V81q23-12 46 0v73" fill="#d8b981" /><path d="M117 121v33m89-33v33" stroke="#644d30" /><rect x="68" y="157" width="188" height="20" rx="8" fill="#e7d3ae" /><path d="M105 184h115" strokeOpacity=".3" />
    <path d="m306 179-16-37q-5-13 3-16t17 17l-4-55q-1-13 8-14t11 12l6 40-1-56q0-11 8-11t10 11l3 55 4-48q1-11 9-10t8 12l-1 55 8-32q3-10 10-8t5 13l-12 71q-5 25-28 29l-28 4Z" fill="#cfb48a" /><path d="m313 195 51-4 3 27-47 6Z" fill="#92734e" /><path d="m325 146 6 32m14-35 1 34m14-39-1 37" stroke="#92734e" strokeWidth="1" />
    <g fill="currentColor" stroke="none" fontSize="8" fontFamily="monospace" opacity=".7"><text x="109" y="213">HEAD PROTECTION</text><text x="302" y="249">HAND PROTECTION</text><text x="61" y="278">SAFETY FIRST / SUPPLY ISOLATED</text></g>
    <circle cx="79" cy="240" r="12" strokeOpacity=".5" /><path d="m73 240 4 4 8-9" stroke="#e7d3ae" />
  </g>;
  if (focus === 'tools') return <g stroke="#c6a575" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="260" y="46" width="116" height="180" rx="13" fill="#b98b50" /><rect x="272" y="59" width="92" height="47" rx="4" fill="#312b21" /><text x="318" y="91" textAnchor="middle" fill="#e7d3ae" stroke="none" fontSize="28" fontFamily="monospace">0.00</text><circle cx="318" cy="153" r="29" fill="#443222" /><path d="m318 153 15-15" stroke="#e7d3ae" strokeWidth="5" /><circle cx="288" cy="207" r="4" fill="#34271b" /><circle cx="348" cy="207" r="4" fill="#73412c" /><path d="M288 226v26q0 18-20 18h-35M348 226v26q0 18 20 18h27" strokeWidth="3" />
    <rect x="81" y="53" width="27" height="79" rx="10" fill="#d1af77" /><path d="M89 68v48m11-48v48" stroke="#7c5b34" /><path d="M95 133v80m-5 0h10v19H90Z" fill="#c6a575" />
    <path d="m170 53-12 27 10 18 13 9 14-9 10-18-12-27v24l-12 8-11-8V53Z" fill="#d6c7a7" /><path d="m175 106-14 109q-2 11-11 8t-6-14l26-106m17 3 16 109q2 11 11 8t6-14l-27-106" fill="#a17b49" /><circle cx="181" cy="105" r="5" fill="#5c442b" />
    <g fill="currentColor" stroke="none" fontSize="8" fontFamily="monospace" opacity=".7"><text x="67" y="255">CHECK. MEASURE. MAINTAIN.</text><text x="67" y="278">THE RIGHT TOOL / THE RIGHT READING</text></g>
  </g>;
  if (focus === 'lighting') return <g stroke="#c6a575" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M131 109h117q15 0 15-15V62h74v36" strokeWidth="4" /><path d="M131 134h96q15 0 15 15v87h95v-35" strokeWidth="4" /><rect x="70" y="72" width="74" height="101" rx="7" fill="#d7c09a" /><rect x="84" y="87" width="46" height="48" rx="4" fill="#453221" /><path d="m95 101 24 13" stroke="#c9a06b" strokeWidth="7" /><text x="107" y="157" textAnchor="middle" fill="#6b4e32" stroke="none" fontSize="9" fontFamily="monospace">ISOLATED</text>
    <path d="M310 169c0-23-25-27-25-58a52 52 0 0 1 104 0c0 31-25 35-25 58Z" fill="#c6a57522" /><path d="m319 137 18 27 17-27m-35 0 18 5 17-5" stroke="#e7d3ae" /><path d="M310 176h54m-52 9h50m-43 9h36" strokeWidth="5" /><path d="M325 203h24" strokeWidth="3" />
    <circle cx="231" cy="141" r="20" strokeDasharray="3 4" strokeOpacity=".55" /><path d="m218 156-25 33" strokeWidth="1" /><text x="151" y="208" stroke="none" fill="currentColor" fontSize="7" fontFamily="monospace">INSPECT THE CONNECTION</text>
    <g fill="currentColor" stroke="none" fontSize="8" fontFamily="monospace" opacity=".7"><text x="63" y="266">BEFORE → REPAIR → AFTER</text><text x="63" y="281">ISOLATED THROUGHOUT / SUPERVISOR INSPECTION</text></g>
  </g>;
  return <g stroke="#c6a575" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="87" y="41" width="307" height="229" rx="9" fill="#9f81501c" /><path d="M106 101h268" strokeWidth="7" strokeOpacity=".3" /><path d="M106 109h268" strokeWidth="2" strokeOpacity=".3" />
    {[121, 181, 241, 301].map((x, i) => <g key={x}><path d={`M${x + 21} 43v36`} strokeWidth="3" /><rect x={x} y="80" width="43" height="100" rx="4" fill="#d8c7a7" /><rect x={x + 7} y="103" width="29" height="35" rx="3" fill="#5c442b" /><path d={`M${x + 12} 115h19`} stroke="#c9a06b" strokeWidth="8" /><circle cx={x + 21} cy="91" r="3" fill="#5c442b" /><circle cx={x + 21} cy="166" r="3" fill="#5c442b" /><path d={`M${x + 21} 180v${20 + i * 9}h${i < 2 ? -25 : 25}`} strokeWidth="3" /><text x={x + 21} y="153" textAnchor="middle" fill="#6b4e32" stroke="none" fontSize="7" fontFamily="monospace">{i === 0 ? 'MAIN' : `0${i}`}</text></g>)}
    <path d="M116 240h248" strokeWidth="6" />{[130, 164, 198, 232, 266, 300, 334].map(x => <circle key={x} cx={x} cy="240" r="3" fill="#5c442b" strokeWidth="1" />)}
    <g fill="currentColor" stroke="none" fontSize="8" fontFamily="monospace" opacity=".7"><text x="113" y="258">EARTH / LABEL / INSPECT</text><text x="100" y="290">DISTRIBUTION PANEL / SUPPLY ISOLATED</text></g>
  </g>;
}

/** A schematic of the isolated training board, rather than simulated worker media. */
function TrainingBoard({ focus = 'wiring' }: { focus?: string }) {
  const id = useId().replaceAll(':', '');
  const grid = `${id}-grid`, copper = `${id}-copper`;
  return <svg className={`lp-board lp-board-${focus}`} viewBox="0 0 480 320" fill="none" aria-hidden="true">
    <defs>
      <pattern id={grid} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0v20" stroke="currentColor" strokeOpacity=".055" /></pattern>
      <linearGradient id={copper} x1="65" y1="70" x2="370" y2="270" gradientUnits="userSpaceOnUse"><stop stopColor="#C9A06B" /><stop offset=".5" stopColor="#f3d9ae" /><stop offset="1" stopColor="#997045" /></linearGradient>
    </defs>
    <rect x="16" y="16" width="448" height="288" rx="12" fill={`url(#${grid})`} stroke="currentColor" strokeOpacity=".17" />
    {[[30, 30], [450, 30], [30, 290], [450, 290]].map(([x, y]) => <g key={`${x}-${y}`} opacity=".35"><circle cx={x} cy={y} r="3" stroke="currentColor" /><path d={`M${x - 2} ${y + 2}l4-4`} stroke="currentColor" /></g>)}
    {focus === 'wiring' ? <>
    <g className="lp-wire-path" stroke={`url(#${copper})`} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"><path d="M112 91h103q16 0 16 16v125h107" /><path d="M112 108h78q16 0 16 16v134h132" /><path d="M112 125h51q16 0 16 16v141h159" /></g>
    <g className="lp-wire-flow" stroke="#FBF6EC" strokeWidth="2" strokeLinecap="round" strokeDasharray="2 180"><path d="M112 91h103q16 0 16 16v125h107" /><path d="M112 108h78q16 0 16 16v134h132" /></g>
    <g className="lp-board-switch"><rect x="61" y="57" width="70" height="102" rx="7" fill="#e8d9be" stroke="#92734e" /><rect x="72" y="69" width="48" height="58" rx="4" fill="#453221" /><rect x="80" y="77" width="32" height="20" rx="3" fill="#c9a06b" /><path d="M96 83v7" stroke="#453221" strokeWidth="2" /><text x="96" y="145" textAnchor="middle" fill="#6b4e32" fontSize="9" fontFamily="monospace">ISOLATED</text></g>
    <g className="lp-board-meter"><rect x="290" y="47" width="105" height="139" rx="13" fill="#b98b50" stroke="#e3c28e" /><rect x="300" y="58" width="85" height="40" rx="4" fill="#312b21" /><text x="342" y="84" textAnchor="middle" fill="#e7d3ae" fontSize="24" fontFamily="monospace">0.00</text><circle cx="342" cy="135" r="23" fill="#443222" stroke="#e2c18e" /><path d="m342 135 12-12" stroke="#e7d3ae" strokeWidth="4" strokeLinecap="round" /><circle cx="317" cy="171" r="4" fill="#34271b" /><circle cx="367" cy="171" r="4" fill="#73412c" /><path d="M317 176v24q0 15-16 15h-28M367 176v24q0 15 17 15h27" stroke="#a68258" strokeWidth="3" /></g>
    <g className="lp-board-terminal"><rect x="321" y="224" width="105" height="66" rx="7" fill="#d8c7a7" stroke="#876b48" />{[343, 373, 403].map((x, i) => <g key={x}><circle cx={x} cy="242" r="8" fill="#614a31" stroke="#efddbd" /><path d={`M${x - 3} 242h6`} stroke="#d8c7a7" /><text x={x} y="276" textAnchor="middle" fill="#614a31" fontFamily="monospace" fontSize="10">{['L', 'N', 'E'][i]}</text></g>)}</g>
    <g opacity=".65" fill="currentColor" fontSize="8" fontFamily="monospace"><text x="57" y="193">SUPPLY DISCONNECTED</text><text x="57" y="207">VERIFY BEFORE TOUCH</text><text x="57" y="278">TRAINING BOARD / SCHEMATIC</text></g>
    </> : <TaskSchematic focus={focus} />}
  </svg>;
}

function EvidenceSculpture() {
  return <div className="lp-sculpture" aria-label="Illustration of practical evidence becoming a reviewable record" role="img">
    <div className="lp-orbit lp-orbit-one" /><div className="lp-orbit lp-orbit-two" /><div className="lp-orbit lp-orbit-three" />
    <div className="lp-orbit-cross lp-cross-one" /><div className="lp-orbit-cross lp-cross-two" />
    <div className="lp-folio-shadow" />
    <div className="lp-folio">
      <div className="lp-folio-edge" /><div className="lp-folio-top"><span>PARAKH / EVIDENCE RECORD</span><Mark type="spark" /></div>
      <div className="lp-folio-drawing"><TrainingBoard /><span className="lp-focus-corner lp-focus-tl" /><span className="lp-focus-corner lp-focus-br" /></div>
      <div className="lp-folio-description"><div><span className="lp-micro">PRACTICE, IN FOCUS</span><h3>The skill is in<br />the details.</h3></div><span className="lp-folio-number">03<span>/ 05</span></span></div>
      <div className="lp-folio-footer"><span><span className="lp-status-dot" />Ready for human review</span><span>PHOTO + VIDEO</span></div>
    </div>
    <div className="lp-floating-label lp-label-capture"><span className="lp-label-icon"><Mark type="camera" /></span><span><small>MADE FOR REAL WORK</small>Captured offline</span></div>
    <div className="lp-floating-label lp-label-seal"><span className="lp-label-icon"><Mark type="shield" /></span><span><small>DETAILS THAT MATTER</small>Evidence, preserved</span></div>
    <div className="lp-seal"><BrandEmblem /><span>SKILL. EVIDENCE. TRUST.</span></div>
    <span className="lp-sculpture-coordinate">27° / PRACTICE → PROOF</span>
  </div>;
}

function JourneyScene({ chapter }: { chapter: number }) {
  return <div className="lp-scenes" data-chapter={chapter} data-ambient>
    <div className="lp-scene-grid" /><div className="lp-scene-glow" />
    <div className="lp-scene lp-scene-phone" aria-hidden={chapter !== 0}>
      <div className="lp-phone"><div className="lp-phone-speaker" /><div className="lp-phone-header"><BrandEmblem /><span>Parakh</span><span className="lp-offline-dot" /></div>
        <div className="lp-phone-copy"><small>YOUR WORK. YOUR EVIDENCE.</small><strong>Show what<br />you know.</strong></div>
        <div className="lp-phone-picture"><TrainingBoard /><span className="lp-viewfinder lp-viewfinder-a" /><span className="lp-viewfinder lp-viewfinder-b" /><span className="lp-phone-record"><i />EVIDENCE PREVIEW</span></div>
        <div className="lp-phone-task"><span>03</span><div>Low-voltage wiring<small>Photo & video evidence</small></div><Mark type="check" /></div>
        <div className="lp-phone-bottom"><span /><span className="lp-camera-button"><Mark type="camera" /></span><span /></div>
      </div><span className="lp-scene-tag lp-phone-tag"><Mark type="signal" />No signal? Keep going.</span>
    </div>
    <div className="lp-scene lp-scene-vault" aria-hidden={chapter !== 1}>
      <div className="lp-vault-ring lp-vault-ring-a" /><div className="lp-vault-ring lp-vault-ring-b" />
      <div className="lp-vault"><div className="lp-vault-header"><span>SEALED EVIDENCE</span><span>SHA-256</span></div><Mark type="shield" className="lp-vault-shield" /><strong>The work.<br />Kept intact.</strong><div className="lp-hash-strips">evidence → fingerprint<br /><span>size + hash → receipt</span></div><div className="lp-vault-bottom"><span className="lp-status-dot" />Integrity verified on arrival<Mark type="check" /></div></div>
      <div className="lp-packet lp-packet-one" /><div className="lp-packet lp-packet-two" /><div className="lp-packet lp-packet-three" />
    </div>
    <div className="lp-scene lp-scene-report" aria-hidden={chapter !== 2}>
      <div className="lp-report"><div className="lp-report-top"><BrandEmblem /><span>PARAKH<br /><small>ASSESSMENT RECORD</small></span><Mark type="shield" /></div><div className="lp-report-rule" /><span className="lp-micro">HUMAN-LED. EVIDENCE-BACKED.</span><h3>Practical skills.<br />A clearer picture.</h3><div className="lp-report-role">ASSISTANT ELECTRICIAN<span>NSQF LEVEL 3</span></div><div className="lp-report-lines">{TASKS.map((task, i) => <div key={task.code}><span>{task.short}</span><div><i style={{ width: `${[82, 91, 75, 85, 78][i]}%` }} /></div></div>)}</div><div className="lp-report-signature"><svg viewBox="0 0 160 50" fill="none"><path d="M8 39C26 23 44 4 37 5S12 47 33 39 67 8 61 9 48 41 68 33 90 14 85 19 77 39 98 30s28-13 23-9-10 14 6 10l24-9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg><span>ASSESSOR SIGN-OFF</span></div><span className="lp-report-footer">Signed recommendation · Verifiable PDF</span></div>
      <span className="lp-scene-tag lp-report-tag"><Mark type="check" />The judgement stays human.</span>
    </div>
    <span className="lp-scene-caption">ILLUSTRATED WORKFLOW · {String(chapter + 1).padStart(2, '0')} / 03</span>
  </div>;
}

function useLandingMotion(enabled: boolean) {
  const root = useRef<HTMLDivElement>(null);
  const [chapter, setChapter] = useState(0);
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    element.dataset.ready = 'true';
    const reveals = element.querySelectorAll('[data-reveal]');
    const revealObserver = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) { entry.target.setAttribute('data-visible', 'true'); revealObserver.unobserve(entry.target); }
    }, { threshold: 0.08 });
    reveals.forEach(target => revealObserver.observe(target));
    const chapterObserver = new IntersectionObserver(entries => {
      if (!window.matchMedia('(min-width: 901px)').matches) return;
      for (const entry of entries) if (entry.isIntersecting) setChapter(Number((entry.target as HTMLElement).dataset.chapter));
    }, { rootMargin: '-35% 0px -35% 0px' });
    element.querySelectorAll('[data-story-chapter]').forEach(target => chapterObserver.observe(target));
    const ambientObserver = new IntersectionObserver(entries => {
      for (const entry of entries) entry.target.setAttribute('data-in-view', String(entry.isIntersecting));
    }, { rootMargin: '100px' });
    element.querySelectorAll('[data-ambient]').forEach(target => ambientObserver.observe(target));
    const visibility = () => { element.dataset.pageVisible = String(!document.hidden); };
    visibility(); document.addEventListener('visibilitychange', visibility);
    return () => { revealObserver.disconnect(); chapterObserver.disconnect(); ambientObserver.disconnect(); document.removeEventListener('visibilitychange', visibility); };
  }, []);
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const height = document.documentElement.scrollHeight - window.innerHeight;
      element.style.setProperty('--read-progress', String(height > 0 ? Math.min(1, window.scrollY / height) : 0));
      if (enabled) element.style.setProperty('--hero-scroll', `${Math.min(window.scrollY * 0.13, 110)}px`);
    };
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll); window.cancelAnimationFrame(frame); };
  }, [enabled]);
  return { root, chapter, setChapter };
}

export default function LandingPage() {
  const [motion, setMotion] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [taskIndex, setTaskIndex] = useState(2);
  const { root, chapter, setChapter } = useLandingMotion(motion);
  const hero = useRef<HTMLDivElement>(null);
  const task = TASKS[taskIndex];
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setMotion(!preference.matches);
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const target = hero.current;
    if (!target || !motion || !window.matchMedia('(pointer: fine)').matches) return;
    let frame = 0, x = 0, y = 0;
    const draw = () => { frame = 0; target.style.setProperty('--pointer-x', `${x}deg`); target.style.setProperty('--pointer-y', `${y}deg`); };
    const move = (event: PointerEvent) => {
      const rect = target.getBoundingClientRect();
      x = ((event.clientX - rect.left) / rect.width - 0.5) * 8;
      y = -((event.clientY - rect.top) / rect.height - 0.5) * 8;
      if (!frame) frame = window.requestAnimationFrame(draw);
    };
    const reset = () => { x = 0; y = 0; if (!frame) frame = window.requestAnimationFrame(draw); };
    target.addEventListener('pointermove', move); target.addEventListener('pointerleave', reset);
    return () => { target.removeEventListener('pointermove', move); target.removeEventListener('pointerleave', reset); window.cancelAnimationFrame(frame); target.style.removeProperty('--pointer-x'); target.style.removeProperty('--pointer-y'); };
  }, [motion]);

  const goTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: motion ? 'smooth' : 'instant', block: 'start' });
  const chooseChapter = (index: number) => {
    setChapter(index);
    if (window.matchMedia('(min-width: 901px)').matches) goTo(`lp-chapter-${index}`);
  };
  const taskKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % TASKS.length;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index + TASKS.length - 1) % TASKS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TASKS.length - 1;
    else return;
    event.preventDefault(); setTaskIndex(next); document.getElementById(`lp-task-${next}`)?.focus();
  };

  return <div className="parakh-landing" ref={root} data-motion={motion ? 'on' : 'off'}>
    <a className="lp-skip" href="#lp-content" onClick={event => { event.preventDefault(); document.getElementById('lp-content')?.focus(); goTo('lp-content'); }}>Skip to content</a>
    <div className="lp-read-progress" aria-hidden="true" />
    <header className="lp-header"><a className="lp-brand" href="#/" onClick={() => window.scrollTo({ top: 0, behavior: motion ? 'smooth' : 'instant' })} aria-label="Parakh home"><BrandEmblem /><span>Parakh<span className="lp-brand-period">.</span></span></a>
      <nav className="lp-nav" aria-label="Explore Parakh"><button onClick={() => goTo('lp-journey')}>The journey</button><button onClick={() => goTo('lp-craft')}>The craft</button><button onClick={() => goTo('lp-principles')}>The trust</button></nav>
      <a className="lp-header-enter" href="#/queue" onClick={() => window.scrollTo(0, 0)}>Assessor dashboard<Arrow diagonal /></a>
    </header>
    <main className="lp-main" id="lp-content" tabIndex={-1}>
      <section className="lp-hero" aria-labelledby="lp-hero-heading">
        <div className="lp-hero-grain" /><div className="lp-hero-copy"><div className="lp-eyebrow lp-hero-reveal"><span className="lp-status-dot" />PRIOR SKILLS. NEW POSSIBILITIES.</div>
          <h1 id="lp-hero-heading" className="lp-hero-reveal">Skill,<br />made <em>visible.</em></h1>
          <p className="lp-hero-description lp-hero-reveal">Behind every skilled pair of hands is a story.<br className="lp-desktop-break" /> Parakh helps turn that experience into evidence.<br className="lp-desktop-break" /> And evidence into recognition.</p>
          <div className="lp-hero-actions lp-hero-reveal"><EnterLink>Enter dashboard</EnterLink><button className="lp-text-button" onClick={() => goTo('lp-journey')}><span className="lp-play-circle"><Mark type="play" /></span>Explore the journey</button></div>
          <div className="lp-hero-footnote lp-hero-reveal"><span className="lp-mini-line" />OFFLINE-FIRST CAPTURE. HUMAN-LED ASSESSMENT.</div>
        </div>
        <div className="lp-hero-art" ref={hero} data-ambient><span className="lp-art-caption">A CLOSER LOOK AT WHAT YOU CAN DO</span><EvidenceSculpture /></div>
        <div className="lp-hero-bottom"><span><span className="lp-scroll-line" />SCROLL TO DISCOVER</span><span>BUILT AROUND THE WORK. DESIGNED FOR PEOPLE.</span><button className="lp-motion-control" aria-pressed={!motion} onClick={() => setMotion(value => !value)}><Mark type={motion ? 'pause' : 'play'} />{motion ? 'Pause motion' : 'Enable motion'}</button></div>
      </section>

      <section className="lp-manifesto lp-section" aria-labelledby="lp-manifesto-heading"><div className="lp-section-index" data-reveal><span>THE IDEA</span><span>01 — 04</span></div><div className="lp-manifesto-main"><h2 id="lp-manifesto-heading" data-reveal>Experience is earned.<br /><span>Let’s give it a voice.</span></h2><p data-reveal>Some skills are learned on a worksite, not in a classroom. Parakh brings practical work into focus, connecting a worker’s evidence with a structured, human-led assessment.</p></div><div className="lp-facts" data-reveal><div><strong>05</strong><span>Practical tasks.<br />One connected journey.</span></div><div><strong>120<span> MB</span></strong><span>A considered budget.<br />For final evidence.</span></div><div><strong>Human<span> first.</span></strong><span>AI flags evidence quality.<br />The assessor decides.</span></div></div></section>

      <section className="lp-journey lp-section" id="lp-journey" aria-labelledby="lp-journey-heading"><div className="lp-section-index" data-reveal><span>FROM PRACTICE TO PROOF</span><span>02 — 04</span></div><div className="lp-section-heading" data-reveal><h2 id="lp-journey-heading">A small screen.<br /><em>A bigger possibility.</em></h2><p>Built for the place where skills actually live.<br />From the worker’s hands to the assessor’s desk.</p></div>
        <div className="lp-journey-layout"><div className="lp-journey-stories">{CHAPTERS.map((item, index) => <article className={`lp-story ${chapter === index ? 'lp-story-active' : ''}`} id={`lp-chapter-${index}`} data-story-chapter data-chapter={index} key={item.word}><span className="lp-eyebrow">{item.eyebrow}</span><span className="lp-story-word">{item.word}</span><h3>{item.title}</h3><p>{item.text}</p><span className="lp-story-note"><span />{item.note}</span></article>)}</div>
          <div className="lp-journey-visual"><JourneyScene chapter={chapter} /><div className="lp-chapter-controls" role="group" aria-label="Explore workflow chapters">{CHAPTERS.map((item, index) => <button key={item.word} aria-pressed={chapter === index} onClick={() => chooseChapter(index)}><span>0{index + 1}</span>{item.label}<i /></button>)}</div></div>
        </div>
      </section>

      <section className="lp-craft lp-section" id="lp-craft" aria-labelledby="lp-craft-heading"><div className="lp-section-index" data-reveal><span>THE CRAFT, IN FOCUS</span><span>03 — 04</span></div><div className="lp-section-heading" data-reveal><h2 id="lp-craft-heading">Real tasks.<br /><em>Meaningful evidence.</em></h2><div><span className="lp-pilot-pill">CURRENT PILOT · ASSISTANT ELECTRICIAN</span><p>Five practical tasks, each with a clear guide and its own evidence budget. Explore what the work looks like.</p></div></div>
        <div className="lp-task-workspace" data-reveal><div className="lp-task-tabs" role="tablist" aria-label="Practical assessment tasks" aria-orientation="vertical">{TASKS.map((item, index) => <button id={`lp-task-${index}`} role="tab" key={item.code} aria-selected={taskIndex === index} aria-controls="lp-task-panel" tabIndex={taskIndex === index ? 0 : -1} onClick={() => setTaskIndex(index)} onKeyDown={event => taskKeyDown(event, index)}><span className="lp-task-index">0{index + 1}</span><span>{item.title}</span><Arrow diagonal /></button>)}<div className="lp-task-pack">ASSISTANT ELECTRICIAN<span>NSQF Level 3 <i /> CON/Q0602 v4.0</span></div></div>
          <div className="lp-task-panel" id="lp-task-panel" role="tabpanel" aria-labelledby={`lp-task-${taskIndex}`} tabIndex={0}><div className="lp-task-visual" data-ambient><div className="lp-task-visual-top"><span>FIELD NOTES / 0{taskIndex + 1}</span><span>ISOLATED TRAINING BOARD</span></div><div key={task.focus} className="lp-task-drawing"><TrainingBoard focus={task.focus} /></div><div className="lp-task-visual-bottom"><span>LOOK CLOSER. SEE THE SKILL.</span><Mark type="spark" /></div></div><div className="lp-task-detail" key={task.code}><div><span className="lp-micro">{task.title.toUpperCase()} <span className="lp-secondary-code">/ {task.code}</span></span><h3>{task.detail}</h3><p>{task.evidence}</p></div><div className="lp-task-budget"><strong>{task.budget}<span>MB</span></strong><span>Final evidence budget</span></div></div></div>
        </div><p className="lp-craft-footnote">Photos, videos, or a mix of both. Preview before sealing. Practical work uses an isolated training board with supervisor oversight.</p>
      </section>

      <section className="lp-trust lp-section" id="lp-principles" aria-labelledby="lp-trust-heading"><div className="lp-section-index" data-reveal><span>TRUST IS IN THE DETAILS</span><span>04 — 04</span></div><div className="lp-trust-layout"><div className="lp-trust-intro" data-reveal><div className="lp-trust-emblem" data-ambient><BrandEmblem /><div /></div><h2 id="lp-trust-heading">A fairer view.<br /><em>At every step.</em></h2><p>Thoughtful assistance. Clear standards. A record you can follow.</p></div><div className="lp-trust-principles">{[
          { n: '01', title: 'Guidance, without the guesswork.', text: 'On-device checks flag dark or blurry evidence and hand visibility. Workers get a chance to capture a clearer view; assessors keep control of every score.', type: 'spark' as const },
          { n: '02', title: 'The same standards. A clearer judgement.', text: 'Versioned rubrics describe what each score means. Critical safety criteria remain visible, and an override needs a written reason.', type: 'check' as const },
          { n: '03', title: 'A record that holds together.', text: 'Evidence fingerprints, revision history, and an audit trail connect the work to the outcome. Signed PDF reports can be checked through public verification.', type: 'shield' as const },
        ].map(item => <article key={item.n} data-reveal><div className="lp-principle-top"><span>{item.n}</span><Mark type={item.type} /></div><h3>{item.title}</h3><p>{item.text}</p></article>)}</div></div></section>

      <section className="lp-finale" data-ambient aria-labelledby="lp-finale-heading"><div className="lp-finale-orbit lp-finale-orbit-a" /><div className="lp-finale-orbit lp-finale-orbit-b" /><div className="lp-finale-content" data-reveal><span className="lp-eyebrow"><span className="lp-status-dot" />THE WORK IS REAL. LET IT BE SEEN.</span><h2 id="lp-finale-heading">Look at the work.<br /><em>See the potential.</em></h2><p>Open the assessor dashboard.<br />Give practical experience the attention it deserves.</p><EnterLink className="lp-enter-light">Begin a review</EnterLink></div><span className="lp-finale-word" aria-hidden="true">Parakh</span></section>
    </main>
    <footer className="lp-footer"><div className="lp-footer-top"><a className="lp-brand" href="#/" onClick={() => window.scrollTo({ top: 0, behavior: motion ? 'smooth' : 'instant' })} aria-label="Parakh home"><BrandEmblem /><span>Parakh<span className="lp-brand-period">.</span></span></a><p>Prior-skill Assessment & Recognition<br />through AI-driven Knowledge</p><a className="lp-footer-verify" href="#/verify" onClick={() => window.scrollTo(0, 0)}>Verify a signed report<Arrow diagonal /></a></div><div className="lp-footer-bottom"><span>MADE FOR SKILL. BUILT ON TRUST.</span><p>Pilot: Assistant Electrician · NSQF Level 3. Reports carry assessor recommendations; formal certification remains with the awarding body.</p><button onClick={() => window.scrollTo({ top: 0, behavior: motion ? 'smooth' : 'instant' })}>Back to top ↑</button></div></footer>
  </div>;
}
