import { useState } from 'react';
import { putScore } from '../api';
import { ApiError, type CriterionReviewItemOut, type EvidenceStatus, type CompetencyProfileOut } from '../types';
import { humanize, readableTaskTitle } from '../presentation';
import { StatusBadge } from './DashboardShell';

interface Draft { level: number; evidence: EvidenceStatus; comment: string }
const draftFor = (item: CriterionReviewItemOut): Draft => ({level: item.score?.score_level ?? 0,
  evidence: item.score?.evidence_status as EvidenceStatus ?? 'DEMONSTRATED', comment: item.score?.assessor_comment ?? ''});
const levelNames = ['Not demonstrated', 'Needs significant help', 'Mostly independent', 'Fully competent'];
const evidenceNames: Record<EvidenceStatus, string> = {
  DEMONSTRATED: 'Visible in submitted evidence', NOT_OBSERVABLE: 'Cannot be seen in the evidence',
  NOT_APPLICABLE_IN_MVP: 'Outside this assessment’s scope',
};

export function TaskScoring({assessmentId, items, profile, editable, visible, onSaved, onConflict, onViewEvidence}: {
  assessmentId: number; items: CriterionReviewItemOut[]; profile?: CompetencyProfileOut; editable: boolean; visible: boolean;
  onSaved: (item: CriterionReviewItemOut) => void; onConflict: () => void; onViewEvidence: (task: string) => void;
}) {
  const [selected, setSelected] = useState<string>();
  // Keep only edits in memory, so switching tasks/tabs never loses an unsaved remark.
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  if (!visible) return null;
  const groups = Array.from(new Set(items.map(item => item.task_code ?? 'Other'))).sort().map(code => {
    const criteria = items.filter(item => (item.task_code ?? 'Other') === code)
      .sort((a, b) => a.pc_full_id.localeCompare(b.pc_full_id, undefined, {numeric: true}));
    return {code, title: readableTaskTitle(criteria[0].task_title || criteria[0].nos_title || 'Other skills'), criteria,
      scored: criteria.filter(item => item.score?.scored_at && !item.score.needs_review).length};
  });
  const group = groups.find(item => item.code === selected) ?? groups[0];
  function edit(item: CriterionReviewItemOut, patch: Partial<Draft>) {
    setDrafts(previous => ({...previous, [item.pc_full_id]: {...(previous[item.pc_full_id] ?? draftFor(item)), ...patch}}));
  }
  async function save(item: CriterionReviewItemOut) {
    const draft = drafts[item.pc_full_id] ?? draftFor(item);
    if (draft.evidence !== 'DEMONSTRATED' && !draft.comment.trim()) {
      setErrors(previous => ({...previous, [item.pc_full_id]: 'A comment is required when the skill cannot be seen or is outside scope.'}));
      return;
    }
    setSaving(previous => ({...previous, [item.pc_full_id]: true}));
    setErrors(previous => ({...previous, [item.pc_full_id]: ''}));
    try {
      const score = await putScore(assessmentId, {pc_full_id: item.pc_full_id, score_level: draft.level,
        evidence_status: draft.evidence, assessor_comment: draft.comment || null, expected_version: item.score?.version ?? 0});
      onSaved({...item, score});
      setDrafts(previous => { const next = {...previous}; delete next[item.pc_full_id]; return next; });
    } catch (error) {
      setErrors(previous => ({...previous, [item.pc_full_id]: error instanceof ApiError && error.status === 409
        ? 'This score changed in another review. The latest scores are being loaded; check your entry and save again.'
        : error instanceof Error ? error.message : 'Could not save this score. Please retry.'}));
      if (error instanceof ApiError && error.status === 409) onConflict();
    } finally { setSaving(previous => ({...previous, [item.pc_full_id]: false})); }
  }
  const scored = items.filter(item => item.score?.scored_at && !item.score.needs_review).length;
  return <>
    <section className="card scoring-intro"><div className="section-heading"><div><span className="eyebrow">Assessor workspace</span><h2>Performance criteria</h2></div><span className="score-progress">{scored} / {items.length} saved</span></div>
      <p>Review one task at a time. Each task contains several skills to check in the same photos or videos. Score every skill separately; the skill codes are reference numbers.</p>
      <progress aria-label="Skills scored" max={Math.max(items.length, 1)} value={scored} />
      <div className="score-scale" aria-label="Score level guide">{levelNames.map((name, level) => <div key={level}><span>{level}</span><strong>{name}</strong></div>)}</div>
      <p className="hint">Use the criterion’s full level descriptions below to make your judgement. Marks = level ÷ 3 × available marks. An unobservable or out-of-scope skill earns zero marks and requires a remark. Critical safety skills need at least level 2 with observable evidence.</p>
    </section>
    {!items.length ? <section className="card"><p>No scoring criteria are available for this assessment.</p></section> : <div className="scoring-workspace">
      <aside className="scoring-task-menu" aria-label="Scoring tasks">{groups.map(item => <button key={item.code} className={group?.code === item.code ? 'active' : ''} aria-pressed={group?.code === item.code} onClick={() => setSelected(item.code)}><span><strong>{item.title} <span className="task-index">{item.code}</span></strong><small>{item.scored} of {item.criteria.length} skills saved</small></span><span className="task-count">{item.scored === item.criteria.length ? '✓' : item.criteria.length - item.scored}</span></button>)}</aside>
      <section className="criteria-panel" aria-label={group?.title}>
        <div className="section-heading"><div><h2>{group?.title}</h2><p className="sub">{group?.criteria.length} skills to assess · {group?.scored} saved</p></div>{group?.code !== 'Other' && <button className="secondary-button" onClick={() => onViewEvidence(group.code)}>View task evidence ↗</button>}</div>
        {!editable && <div className="notice">Scoring is read-only. Start review to score a submitted assessment; completed decisions stay locked.</div>}
        {group?.criteria.map((item, index) => {
          const draft = drafts[item.pc_full_id] ?? draftFor(item);
          const inputId = `criterion-${item.pc_full_id.replaceAll(/[^a-zA-Z0-9]/g, '-')}`;
          const dirty = !!drafts[item.pc_full_id];
          const state = item.score?.needs_review ? 'Review again' : dirty ? 'Unsaved changes' : item.score?.scored_at ? 'Saved' : 'Not scored';
          return <article className={`criterion-card ${item.critical ? 'criterion-critical' : ''}`} key={item.pc_full_id} aria-labelledby={`${inputId}-title`}>
            <div className="criterion-heading"><span className="criterion-number">{index + 1}</span><h3 id={`${inputId}-title`}>{item.criterion_text || item.evidence_hint || 'Review this performance criterion'}</h3><span className={`criterion-state ${state === 'Saved' ? 'is-saved' : ''}`} role="status">{state}</span></div>
            <div className="criterion-meta"><span>{item.marks} marks available</span>{item.critical && <span className="badge-critical">Critical safety skill</span>}<span className="criterion-reference">Reference: {item.pc_full_id}</span></div>
            <p className="evidence-guidance"><strong>Look for:</strong> {item.evidence_hint}</p>
            <fieldset className="criterion-inputs" disabled={!editable || saving[item.pc_full_id]}>
              <legend className="sr-only">Score for {item.criterion_text || item.pc_full_id}</legend>
              <label htmlFor={`${inputId}-level`}>Performance level<select id={`${inputId}-level`} value={draft.level} onChange={e => edit(item, {level: Number(e.target.value)})}>{levelNames.map((name, level) => <option key={level} value={level}>{level} — {name}</option>)}</select></label>
              <label htmlFor={`${inputId}-evidence`}>Can you observe this skill?<select id={`${inputId}-evidence`} value={draft.evidence} onChange={e => edit(item, {evidence: e.target.value as EvidenceStatus})}>{Object.entries(evidenceNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
              <div className="selected-anchor"><strong>Level {draft.level}: {levelNames[draft.level]}</strong><p>{item.anchors[String(draft.level)]}</p></div>
              <label className="criterion-remark" htmlFor={`${inputId}-comment`}>Assessor remarks {draft.evidence === 'DEMONSTRATED' ? '(optional)' : '(required)'}<textarea id={`${inputId}-comment`} value={draft.comment} maxLength={4000} rows={2} placeholder="What did the evidence show?" onChange={e => edit(item, {comment: e.target.value})} /></label>
            </fieldset>
            <details className="rubric-guidance"><summary>See all scoring levels</summary>{levelNames.map((name, level) => <p key={level}><strong>{level} — {name}:</strong> {item.anchors[String(level)]}</p>)}</details>
            <div className="criterion-footer"><span className="hint">{item.score?.scored_at ? `${item.score.marks_awarded} / ${item.marks} marks awarded` : 'Save to confirm your judgement.'}</span>{editable && <button disabled={saving[item.pc_full_id]} onClick={() => void save(item)}>{saving[item.pc_full_id] ? 'Saving…' : 'Save score'}</button>}</div>
            {errors[item.pc_full_id] && <p className="error" role="alert">{errors[item.pc_full_id]}</p>}
          </article>;
        })}
      </section>
    </div>}
    <section className="card competency-summary"><div className="section-heading"><h2>Competency profile</h2>{profile && <StatusBadge value={profile.computed_outcome} />}</div>{profile && <><p>{profile.pcs_scored}/{profile.pcs_total} criteria confirmed · {profile.overall_percent}% overall</p><div className="competency-grid">{profile.nos_breakdown.map(nos => <div key={nos.nos_code} className={`competency-item ${nos.competent ? 'competency-met' : ''}`}><strong>{nos.nos_title} <small className="pack-reference">{nos.nos_code}</small></strong><span>{nos.percent}% · {nos.marks_awarded}/{nos.marks_possible} marks</span><small>{nos.competent ? 'Competency threshold met' : nos.has_insufficient_evidence ? 'More observable evidence needed' : 'Competency threshold not yet met'}</small></div>)}</div><p className="hint">{profile.disclaimer}</p></>}</section>
    <p className="hint">Your scores support the final recommendation: {profile ? humanize(profile.computed_outcome) : 'waiting for scoring data'}.</p>
  </>;
}
