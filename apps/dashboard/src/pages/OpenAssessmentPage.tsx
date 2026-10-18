import { humanize, qualificationName, readableTaskTitle } from "../presentation";
import { useCallback, useEffect, useRef, useState } from "react";
import { getReviewWorkspace, getCompetencyProfile,
  publicAssessment, publicAssessmentSnapshot, updatePublicAssessmentSnapshot, startReview, rejectAssessment, reviewerReassessment,
  reviewerSignOff, reportDownloadUrl, type PublicAssessment, type ReviewerAction } from "../api";
import type { AssessmentOut, CriterionReviewItemOut, CompetencyProfileOut, SyncStatusOut } from "../types";
import { EvidenceViewer as EvidencePreview } from "../components/EvidenceViewer";
import { ReviewerConfirmation } from "../components/ReviewerConfirmation";
import { StatusBadge } from "../components/DashboardShell";

import { AssessorAccess } from '../components/AssessorAccess';
import { useAssessorSession } from '../components/AssessorSession';
import { ApiError } from '../types';
import { TaskScoring } from '../components/TaskScoring';
import { AssessmentHistory } from '../components/AssessmentHistory';
import type { CompletedDecision } from '../components/DecisionComplete';

const tabs = ['Overview', 'Evidence', 'Scoring', 'Decision', 'Audit & history'];
const taskNames: Record<string, string> = {T1: 'Safety & PPE', T2: 'Tools & meter use', T3: 'LV wiring (switchboard)', T4: 'Temporary lighting / fault', T5: 'Temporary LV panel'};
const mb = (bytes: number) => `${(bytes / 1048576).toFixed(1)} MB`;

export function OpenAssessmentPage({ id, onCompleted }: { id: number; onCompleted: (decision: CompletedDecision) => void }) {
  const [summary, setSummary] = useState<PublicAssessment | undefined>(() => publicAssessmentSnapshot(id));
  const {account, loaded, setAccount} = useAssessorSession();
  const [accessOpen, setAccessOpen] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentOut>();
  const [review, setReview] = useState<CriterionReviewItemOut[]>([]);
  const [profile, setProfile] = useState<CompetencyProfileOut>();
  const [sync, setSync] = useState<SyncStatusOut>();
  const [action, setAction] = useState<ReviewerAction>();
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [instructions, setInstructions] = useState("");
  const [tasks, setTasks] = useState<string[]>([]);
  const [recommendation, setRecommendation] = useState("");
  const [override, setOverride] = useState("");
  const [tab, setTab] = useState('Overview');
  const [taskCode, setTaskCode] = useState('T1');
  const [busy, setBusy] = useState(false);
  const [attested, setAttested] = useState(false);
  const [retry, setRetry] = useState(0);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const privateSequence = useRef(0);
  const profileSequence = useRef(0);

  const clearPrivate = useCallback(() => { setAssessment(undefined); setReview([]); setProfile(undefined); setSync(undefined); setAction(undefined); }, []);
  useEffect(() => {
    let active = true;
    const load = () => publicAssessment(id).then(value => { if (active) setSummary(value); }).catch(() => { if (active) setError('Could not load this assessment. Please try again.'); });
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [id, retry]);

  const loadPrivate = useCallback(async () => {
    const sequence = ++privateSequence.current;
    const value = await getReviewWorkspace(id);
    if (sequence !== privateSequence.current) return;
    setAssessment(value.assessment); setReview(value.review); setProfile(value.profile); setSync(value.sync); setError('');
    setHistoryVersion(version => version + 1);
  }, [id]);
  useEffect(() => {
    let active = true;
    if (!account) {
      clearPrivate();
    } else {
      setAccessOpen(false); setLoading(true);
      void loadPrivate().catch(error => {
        if (!active) return;
        clearPrivate();
        if (error instanceof ApiError && error.status === 401) setAccount(null);
        else setError('Could not load the assessment. Please retry.');
      }).finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; privateSequence.current++; profileSequence.current++; };
  }, [account, loadPrivate, clearPrivate, setAccount, retry]);
  useEffect(() => { if (!account && loaded && summary?.id) setAccessOpen(true); }, [account, loaded, summary?.id]);
  async function confirmed(password: string) {
    const completedAction = action;
    const finalRecommendation = recommendation || profile?.computed_outcome || '';
    if (action === "reject") {
      await rejectAssessment(id, reason, password);
      if (summary) updatePublicAssessmentSnapshot({...summary, status: 'not_recommended', review_status: 'not_recommended'});
    }
    if (action === "reassessment") {
      await reviewerReassessment(id, {task_codes: tasks, reason, capture_instructions: instructions}, password);
      if (summary) updatePublicAssessmentSnapshot({...summary, status: 'needs_reassessment', review_status: 'needs_reassessment'});
    }
    if (action === "sign_off") {
      const signed = await reviewerSignOff(id, finalRecommendation, override, password);
      if (summary) updatePublicAssessmentSnapshot({...summary, status: 'recommended', review_status: 'signed_off', report_available: true, report_id: signed.report_uid, outcome: signed.final_recommendation});
    }
    setAction(undefined); setReason(""); setTasks([]); setInstructions(""); setAttested(false);
    const title = completedAction === 'reject' ? 'Assessment marked not qualified' : completedAction === 'reassessment' ? 'Reassessment requested'
      : finalRecommendation === 'RECOMMEND_CERTIFICATION' ? 'Report signed successfully'
      : finalRecommendation === 'NOT_YET_COMPETENT' ? 'Report signed — not yet qualified'
      : finalRecommendation === 'PARTIALLY_COMPETENT' ? 'Report signed — partially competent' : 'Report signed — more evidence needed';
    onCompleted({assessmentId: id, title, description: completedAction === 'reassessment'
      ? 'Your reassessment request and capture instructions have been saved for the worker.'
      : completedAction === 'reject' ? 'Your decision and reason have been recorded.' : 'Your signed report and final recommendation have been saved.'});
  }
  async function refreshReview(begin = false) {
    setBusy(true); setError('');
    try { if (begin) { const updated = await startReview(id); setAssessment(updated); setSummary(previous => previous ? {...previous, status: updated.status, review_status: updated.status} : previous); } await loadPrivate(); }
    catch (e) { setError(e instanceof Error ? e.message : "Review could not be loaded."); }
    finally { setBusy(false); }
  }
  const task = assessment?.tasks.find(t => t.task_code === taskCode) ?? assessment?.tasks[0];
  const canReview = assessment?.status === 'in_review';
  const allScored = !!profile && profile.pcs_scored === profile.pcs_total && profile.pcs_total > 0 && !review.some(i => i.score?.needs_review);
  const overrideNeeded = !!recommendation && recommendation !== profile?.computed_outcome;
  const displayTaskNames = Object.fromEntries(Object.entries({...taskNames, ...Object.fromEntries(review.filter(item => item.task_code).map(item => [item.task_code!, item.task_title]))}).map(([code, title]) => [code, readableTaskTitle(title)]));
  function scoreSaved(updated: CriterionReviewItemOut) {
    setReview(previous => previous.map(row => row.pc_full_id === updated.pc_full_id ? updated : row));
    setHistoryVersion(version => version + 1);
    const sequence = ++profileSequence.current;
    void getCompetencyProfile(id).then(value => { if (sequence === profileSequence.current) setProfile(value); })
      .catch(() => { if (sequence === profileSequence.current) setError('Score saved. Refresh the review to reload the competency profile.'); });
  }
  return <div className="page assessment-page">
    <div className="breadcrumb"><a href="#/queue">Queue</a> / {summary?.candidate_display_name ?? `Assessment #${id}`}</div>
    <div className="pagehead"><div><h1>{summary?.candidate_display_name ?? `Assessment #${id}`}</h1><p className="sub">Assessment #{id} · {summary ? qualificationName(summary.pack_code, assessment?.pack_name || summary.pack_name) : 'Loading qualification…'}{summary && <small className="pack-reference">{summary.pack_code}</small>} · v{summary?.revision_number ?? '—'}</p></div>{summary && <StatusBadge value={summary.status} />}</div>
    <div className="subnav" role="tablist" aria-label="Assessment sections">{tabs.map(value => <button key={value} id={`tab-${value.split(' ')[0]}`} role="tab" aria-selected={tab === value} aria-controls="assessment-panel" className={`subtab ${tab === value ? 'active' : ''}`} onClick={() => setTab(value)} onKeyDown={e => { const index = tabs.indexOf(value); if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); const next = tabs[(index + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; setTab(next); document.getElementById(`tab-${next.split(' ')[0]}`)?.focus(); } }}>{value}</button>)}</div>
    {error && <div className="notice error" role="alert">{error}<button className="secondary-button" onClick={() => setRetry(v => v + 1)}>Retry</button></div>}
    <div id="assessment-panel" role="tabpanel" aria-labelledby={`tab-${tab.split(' ')[0]}`}>
    {tab === 'Overview' && summary && <>
      <section className="card"><h2>Worker summary</h2><div className="grid3">
        <div className="kv"><span className="k">Full name / public identity</span><span className="v">{summary.candidate_display_name}</span></div><div className="kv"><span className="k">Assessment</span><span className="v mono">#{id}</span></div><div className="kv"><span className="k">Qualification pack</span><span className="v">{qualificationName(summary.pack_code, assessment?.pack_name || summary.pack_name)} <small className="pack-reference">{summary.pack_code}</small></span></div>
        <div className="kv"><span className="k">Submitted</span><span className="v">{new Date(summary.submitted_at).toLocaleString()}</span></div><div className="kv"><span className="k">Evidence coverage</span><span className="v">{summary.tasks_completed}/{summary.tasks_total} tasks</span></div><div className="kv"><span className="k">Review</span><span className="v">Review: {summary.review_status}</span></div>
      </div></section>
      {assessment && account && <><section className="card"><h2>Experience and qualification match</h2><div className="matchrow"><StatusBadge value={assessment.declared_match_result ?? 'not_recorded'} /><span className="coverage">{assessment.declared_coverage_fraction != null ? `${Math.round(Number(assessment.declared_coverage_fraction) * 100)}% declared-experience coverage` : 'Coverage not recorded'}</span></div><ul className="reasons">{assessment.declared_match_reasons?.map((line, i) => <li key={i}>{line}</li>)}</ul>{!assessment.declared_match_reasons && <p className="hint">Match reasons were not recorded for this submission.</p>}{!!assessment.declared_gap_task_codes?.length && <div className="gapbox">Extra evidence needed: {assessment.declared_gap_task_codes.map(code => displayTaskNames[code] ?? code).join(', ')}. Assessor attention is recommended on these tasks.</div>}</section>
      <section className="card"><h2>Sync &amp; package integrity</h2><div className="grid3"><div className="kv"><span className="k">Package uploaded</span><span className={`v ${sync?.all_items_verified ? 'good' : ''}`}>{sync?.all_items_verified ? '✓ All evidence verified' : 'Awaiting complete verification'}</span></div><div className="kv"><span className="k">Signed manifest</span><span className="v">{humanize(sync?.manifest_state ?? 'none')}</span></div><div className="kv"><span className="k">Total evidence size</span><span className="v">{mb(assessment.total_bytes_used)} of {mb(assessment.total_budget_bytes)}</span></div></div></section></>}
      {summary.report_available && summary.report_id && <section className="card"><h2>Signed report</h2><p>{humanize(summary.outcome ?? summary.status)}</p><a className="openlink" href={`#/verify/${encodeURIComponent(summary.report_id)}`}>Verify report</a></section>}
    </>}
    {(!assessment || !account) && <section className="card access-card" aria-busy={loading}><h2>{tab === 'Overview' ? 'Assessor review' : `Open ${tab.toLowerCase()}`}</h2><p role={loading ? 'status' : undefined}>{loading ? 'Loading evidence and scoring workspace…' : 'Enter your assessor details to review evidence and score this assessment.'}</p><button disabled={!loaded || busy || loading} onClick={() => { if (account) void refreshReview(); else setAccessOpen(true); }}>{loading ? 'Loading assessment…' : account ? 'Load assessment' : 'Enter assessor details'}</button><p className="hint">Signing, rejection and reassessment suggestions require your password again. Reports are assessor recommendations, not official NCVET/MSDE certificates.</p></section>}
    {assessment && account && <>
      <div className="panel-actions review-actions"><span className="hint">Reviewing as {account.name} · {account.email}</span><button className="secondary-button" disabled={busy} onClick={() => void refreshReview()}>Refresh review</button>{assessment.status === 'submitted' && <button disabled={busy} onClick={() => void refreshReview(true)}>Start review</button>}</div>
      {tab === 'Evidence' && <div className="evidence-workspace"><aside className="task-menu" aria-label="Evidence tasks">{assessment.tasks.map(t => <button key={t.task_code} className={task?.task_code === t.task_code ? 'active' : ''} aria-pressed={task?.task_code === t.task_code} onClick={() => setTaskCode(t.task_code)}>{displayTaskNames[t.task_code] ?? t.task_code} <small className="task-index">{t.task_code}</small></button>)}</aside><section>{task && <><h2>{displayTaskNames[task.task_code]} <small className="task-index">{task.task_code}</small></h2><p className="sub">{task.evidence.length} evidence item(s) · {mb(task.bytes_used)} of {mb(task.budget_bytes)}</p><ul className="evidence-gallery">{task.evidence.map(item => <EvidencePreview key={item.id} assessmentId={id} evidence={item} />)}</ul>{!task.evidence.length && <div className="empty-state"><h2>No evidence submitted for this task.</h2></div>}<section className="card" style={{marginTop: 20}}><h2>Evidence quality assistance</h2><p className="hint">On-device advisory signals appear with each recording. Decision support only — the assessor decides every score and outcome.</p></section></>}</section></div>}
      <TaskScoring assessmentId={id} items={review} profile={profile} editable={canReview} visible={tab === 'Scoring'} onSaved={scoreSaved} onConflict={() => void refreshReview()} onViewEvidence={code => { setTaskCode(code); setTab('Evidence'); }} />
      {tab === 'Decision' && <><section className="card"><h2>Reassessment</h2><p>Reopen specific tasks and send the worker clear instructions for new evidence.</p><button disabled={!canReview} onClick={() => setAction('reassessment')}>Request targeted reassessment</button></section><section className="card"><h2>Sign off</h2><p>{profile ? humanize(profile.computed_outcome) : 'Load the competency profile to continue.'}</p>{!allScored && <div className="gapbox">Confirm every performance criterion, including any reopened scores, before signing a report.</div>}<label className="checkbox-label"><input type="checkbox" checked={attested} onChange={e => setAttested(e.target.checked)} />I have reviewed all evidence and scores and confirm this outcome.</label><div className="panel-actions"><button disabled={!canReview || !allScored || !attested} onClick={() => setAction('sign_off')}>Approve and sign report</button><button className="danger-button" disabled={!canReview} onClick={() => setAction('reject')}>Reject / do not recommend</button></div></section><section className="card"><h2>Signed report</h2>{summary?.report_available && summary.report_id ? <><p className="mono">{summary.report_id}</p><div className="panel-actions"><a className="button" href={reportDownloadUrl(id, 'pdf')} target="_blank" rel="noreferrer">Download private signed report</a><a className="openlink" href={`#/verify/${encodeURIComponent(summary.report_id)}`}>View public verification →</a></div></> : <p className="hint">A signed report will appear after the assessor completes sign-off.</p>}</section></>}
      <AssessmentHistory assessmentId={id} visible={tab === 'Audit & history'} refreshKey={historyVersion} taskNames={displayTaskNames} />
    </>}
    </div>
    {accessOpen && !account && <AssessorAccess onClose={() => setAccessOpen(false)} />}
    {action && account && <ReviewerConfirmation id={id} action={action} onConfirmed={confirmed} onCancel={() => setAction(undefined)} ready={action === 'reject' ? reason.trim().length >= 3 : action === 'reassessment' ? tasks.length > 0 && !!reason.trim() && !!instructions.trim() : action === 'sign_off' ? allScored && attested && (!overrideNeeded || !!override.trim()) : true}>
      {(action === 'reject' || action === 'reassessment') && <label>Reason / remarks (required)<textarea required maxLength={4000} value={reason} onChange={e => setReason(e.target.value)} /></label>}
      {action === 'reassessment' && <><fieldset><legend>Tasks requiring reassessment</legend>{assessment?.tasks.map(t => <label key={t.task_code}><input type="checkbox" checked={tasks.includes(t.task_code)} onChange={e => setTasks(previous => e.target.checked ? [...previous, t.task_code] : previous.filter(code => code !== t.task_code))} />{displayTaskNames[t.task_code] ?? t.task_code} <small className="task-index">{t.task_code}</small></label>)}</fieldset><label>What to capture (required)<textarea required maxLength={4000} value={instructions} onChange={e => setInstructions(e.target.value)} /></label></>}
      {action === 'sign_off' && <><label>Decision<select value={recommendation || profile?.computed_outcome || ''} onChange={e => setRecommendation(e.target.value)}>{['RECOMMEND_CERTIFICATION', 'PARTIALLY_COMPETENT', 'NOT_YET_COMPETENT', 'INSUFFICIENT_EVIDENCE'].map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Override reason (required when changing computed outcome)<textarea required={overrideNeeded} value={override} onChange={e => setOverride(e.target.value)} /></label></>}
    </ReviewerConfirmation>}
  </div>;
}
