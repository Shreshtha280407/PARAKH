import { useEffect, useState } from "react";
import { getAssessment, getReview, getCompetencyProfile, getAuditLog, listReassessmentRequests,
  publicAssessment, reviewerAvailability, startReview, rejectAssessment, reviewerReassessment,
  reviewerSignOff, reportDownloadUrl, type PublicAssessment, type ReviewerAction } from "../api";
import type { AssessmentOut, CriterionReviewItemOut, CompetencyProfileOut, AuditLogEntryOut, ReassessmentRequestOut } from "../types";
import { EvidencePreview, ScoreRow } from "./AssessmentDetailPage";
import { ReviewerConfirmation } from "../components/ReviewerConfirmation";

export function OpenAssessmentPage({ id }: { id: number }) {
  const [summary, setSummary] = useState<PublicAssessment>();
  const [availability, setAvailability] = useState<{available: boolean; message: string}>();
  const [assessment, setAssessment] = useState<AssessmentOut>();
  const [privateExpiresAt, setPrivateExpiresAt] = useState(0);
  const [review, setReview] = useState<CriterionReviewItemOut[]>([]);
  const [profile, setProfile] = useState<CompetencyProfileOut>();
  const [audit, setAudit] = useState<AuditLogEntryOut[]>([]);
  const [history, setHistory] = useState<ReassessmentRequestOut[]>([]);
  const [action, setAction] = useState<ReviewerAction>();
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [instructions, setInstructions] = useState("");
  const [tasks, setTasks] = useState<string[]>([]);
  const [recommendation, setRecommendation] = useState("");
  const [override, setOverride] = useState("");
  useEffect(() => {
    if (!privateExpiresAt) return;
    const expire = () => {
      if (Date.now() >= privateExpiresAt) {
        setAssessment(undefined); setReview([]); setProfile(undefined); setAudit([]); setHistory([]);
        setError("Reviewer access expired. Verify your email again to continue.");
      }
    };
    const timer = window.setTimeout(expire, Math.max(0, privateExpiresAt - Date.now()));
    document.addEventListener("visibilitychange", expire);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", expire); };
  }, [privateExpiresAt]);
  useEffect(() => {
    let active = true;
    const load = () => publicAssessment(id).then(value => { if (active) setSummary(value); }).catch(e => { if (active) setError(String(e)); });
    void load();
    reviewerAvailability().then(value => { if (active) setAvailability(value); }).catch(() => undefined);
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [id]);

  async function loadPrivate() {
    const [detail, scores, competency, events, requests] = await Promise.all([
      getAssessment(id), getReview(id), getCompetencyProfile(id), getAuditLog(id), listReassessmentRequests(id)]);
    setAssessment(detail); setReview(scores); setProfile(competency); setAudit(events); setHistory(requests);
  }
  async function confirmed() {
    if (action === "review") { await loadPrivate(); setPrivateExpiresAt(Date.now() + 15 * 60 * 1000); }
    if (action === "reject") { await rejectAssessment(id, reason); setAssessment(undefined); }
    if (action === "reassessment") {
      await reviewerReassessment(id, {task_codes: tasks, reason, capture_instructions: instructions}); setAssessment(undefined);
    }
    if (action === "sign_off") {
      await reviewerSignOff(id, recommendation || profile?.computed_outcome || "", override); setAssessment(undefined);
    }
    setSummary(await publicAssessment(id)); setAction(undefined); setReason(""); setTasks([]); setInstructions("");
  }
  async function beginReview() {
    try { await startReview(id); await loadPrivate(); }
    catch (e) { setError(e instanceof Error ? e.message : "Review could not be started."); }
  }
  return <div className="page"><a href="#/queue">← Submitted assessments</a><h1>Assessment #{id}</h1>
    {error && <p className="error" role="alert">{error}</p>}
    {summary && <section className="card"><h2>{summary.candidate_display_name}</h2>
      <p>{summary.pack_code} · Submitted {new Date(summary.submitted_at).toLocaleString()} · {summary.status} · v{summary.revision_number}</p>
      <p>Tasks with evidence: {summary.tasks_completed}/{summary.tasks_total}. Review: {summary.review_status}.</p>
      {summary.report_available && summary.report_id ? <p>Report available · {summary.outcome} · <a href={`#/verify/${summary.report_id}`}>Verify report</a></p> : <p>Report not yet available.</p>}
    </section>}
    <section className="card"><h2>Assessor review</h2><p>{availability?.message ?? "Checking reviewer availability…"}</p>
      <button disabled={!availability?.available} onClick={() => setAction("review")}>Verify email to review</button>
      <p>Private evidence and committed scores require reviewer authorization. Reports are assessor recommendations, not official NCVET/MSDE certificates.</p>
    </section>
    {assessment && <>
      <section className="card"><h2>Private review · {assessment.worker_name}</h2><p>Email ownership verified. Name is self-declared. Access expires after 15 minutes.</p>
        <button onClick={() => { void loadPrivate().catch(e => setError(String(e))); }}>Refresh review</button>
        {assessment.status === "submitted" && <button onClick={() => void beginReview()}>Start review</button>}
        {assessment.tasks.map(task => <div key={task.task_code}><h3>{task.task_code}</h3><ul>{task.evidence.map(item => <EvidencePreview key={item.id} assessmentId={id} evidence={item} />)}</ul></div>)}
      </section>
      {assessment.status === "in_review" && <section className="card"><h2>Performance criteria</h2>
        <table><thead><tr><th>Criterion</th><th>Level 0–3</th><th>Evidence status</th><th>Remarks</th><th>Save</th></tr></thead><tbody>
          {review.map(item => <ScoreRow key={`${item.pc_full_id}-${item.score?.version ?? 0}`} assessmentId={id} item={item}
            onSaved={updated => { setReview(previous => previous.map(row => row.pc_full_id === updated.pc_full_id ? updated : row)); void getCompetencyProfile(id).then(setProfile); }}
            onConflict={() => { void loadPrivate().catch(e => setError(String(e))); }} />)}
        </tbody></table>
        <h2>Computed competency profile</h2><p>{profile?.computed_outcome} · {profile?.pcs_scored}/{profile?.pcs_total} criteria confirmed · {profile?.overall_percent}%</p>
        <p>{profile?.disclaimer}</p>
        <button onClick={() => setAction("reassessment")}>Request targeted reassessment</button>
        <button className="danger-button" onClick={() => setAction("reject")}>Reject / do not recommend</button>
        <button disabled={!profile || profile.pcs_scored !== profile.pcs_total} onClick={() => setAction("sign_off")}>Approve and sign report</button>
      </section>}
      {assessment.status === "recommended" && <a href={reportDownloadUrl(id, "pdf")}>Download private signed report</a>}
      <section className="card"><h2>Reassessment history</h2>{history.length ? history.map(item => <p key={item.id}>v{item.revision_number} · {item.task_codes.join(", ")} · {item.reason} · {item.status}</p>) : <p>No reassessment requests.</p>}
        <h2>Audit history</h2><ul>{audit.map(event => <li key={event.id}>{new Date(event.created_at).toLocaleString()} · {event.action} · {event.actor_role}<pre>{JSON.stringify(event.details, null, 2)}</pre></li>)}</ul>
      </section>
    </>}
    {action && <ReviewerConfirmation id={id} action={action} onConfirmed={confirmed} onCancel={() => setAction(undefined)}
      ready={action === "reject" ? reason.trim().length >= 3 : action === "reassessment" ? tasks.length > 0 && !!reason.trim() && !!instructions.trim() : action === "sign_off" ? !!(recommendation || profile?.computed_outcome) : true}>
      {(action === "reject" || action === "reassessment") && <label>Reason / remarks (required)<textarea required maxLength={4000} value={reason} onChange={e => setReason(e.target.value)} /></label>}
      {action === "reassessment" && <><fieldset><legend>Tasks requiring reassessment</legend>{assessment?.tasks.map(task => <label key={task.task_code}><input type="checkbox" checked={tasks.includes(task.task_code)} onChange={e => setTasks(previous => e.target.checked ? [...previous, task.task_code] : previous.filter(code => code !== task.task_code))} />{task.task_code}</label>)}</fieldset>
        <label>What to capture (required)<textarea required value={instructions} onChange={e => setInstructions(e.target.value)} /></label></>}
      {action === "sign_off" && <><label>Decision<select value={recommendation || profile?.computed_outcome || ""} onChange={e => setRecommendation(e.target.value)}>
        {["RECOMMEND_CERTIFICATION", "PARTIALLY_COMPETENT", "NOT_YET_COMPETENT", "INSUFFICIENT_EVIDENCE"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Override reason (required when changing computed outcome)<textarea value={override} onChange={e => setOverride(e.target.value)} /></label></>}
    </ReviewerConfirmation>}
  </div>;
}
