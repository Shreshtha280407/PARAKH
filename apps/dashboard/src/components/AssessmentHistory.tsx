import { useEffect, useRef, useState } from 'react';
import { getReviewHistory, type ReviewHistory } from '../api';
import { humanize } from '../presentation';
import { StatusBadge } from './DashboardShell';

const date = (value: string) => new Date(value).toLocaleString('en-IN', {dateStyle: 'medium', timeStyle: 'short'});

export function AssessmentHistory({assessmentId, visible, refreshKey, taskNames}: {
  assessmentId: number; visible: boolean; refreshKey: number; taskNames: Record<string, string>;
}) {
  const [history, setHistory] = useState<ReviewHistory>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const loadedVersion = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!visible || loadedVersion.current === refreshKey) return;
    let active = true;
    setLoading(true); setError('');
    getReviewHistory(assessmentId).then(value => {
      if (active) { setHistory(value); loadedVersion.current = refreshKey; }
    }).catch(() => { if (active) setError('Could not load the assessment history. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [assessmentId, visible, refreshKey, retry]);
  if (!visible) return null;
  return <div hidden={!visible}>
    {loading && <p className="notice" role="status">Loading assessment history…</p>}
    {error && <p className="notice error" role="alert">{error} <button onClick={() => setRetry(v => v + 1)}>Retry history</button></p>}
    {history && <>
      <section className="card history-section"><div className="section-heading"><div><span className="eyebrow">Evidence journey</span><h2>Revision history</h2></div><span className="history-total">{history.revisions.length} version{history.revisions.length === 1 ? '' : 's'}</span></div>
        {history.revisions.length ? <ol className="revision-timeline">{history.revisions.map((item, index) => <li key={item.revision_number} className={index === history.revisions.length - 1 ? 'revision-current' : ''}><span className="revision-marker">{item.revision_number}</span><div className="revision-entry"><div className="section-heading"><h3>Version {item.revision_number}{index === history.revisions.length - 1 && <span className="current-version">Current</span>}</h3><StatusBadge value={item.status} /></div><p className="history-date">Created {date(item.created_at)}</p>{item.submitted_at && <p className="history-date">Submitted {date(item.submitted_at)}</p>}{item.reopened_task_codes?.length ? <><p className="history-label">Tasks reopened for new evidence</p><div className="history-task-chips">{item.reopened_task_codes.map(code => <span key={code}>{taskNames[code] ?? code}</span>)}</div></> : <p className="hint">Original evidence submission</p>}</div></li>)}</ol> : <p className="history-empty">No revision history recorded yet.</p>}
      </section>
      <section className="card history-section"><div className="section-heading"><div><span className="eyebrow">Follow-up evidence</span><h2>Reassessment requests</h2></div><span className="history-total">{history.requests.filter(item => item.status === 'pending').length} pending</span></div>
        {history.requests.length ? <div className="reassessment-list">{[...history.requests].reverse().map(item => <article key={item.id} className={`reassessment-entry request-${item.status}`}><div className="section-heading"><h3>Request #{item.id}<span className="request-version">Version {item.revision_number}</span></h3><StatusBadge value={item.status} /></div><p className="history-date">Requested {date(item.requested_at)}{item.fulfilled_at && ` · Completed ${date(item.fulfilled_at)}`}</p><div className="history-task-chips">{item.task_codes.map(code => <span key={code}>{taskNames[code] ?? code}</span>)}</div><div className="request-details"><div><span className="history-label">Why new evidence is needed</span><p>{item.reason}</p></div><div className="capture-instructions"><span className="history-label">What the worker should capture</span><p>{item.capture_instructions}</p></div></div></article>)}</div> : <p className="history-empty">No reassessment requested. Any future evidence requests will appear here.</p>}
      </section>
      <section className="card"><h2>Audit log</h2><div className="table-scroll"><table><thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Detail</th></tr></thead><tbody>{history.audit.map(event => <tr key={event.id}><td>{date(event.created_at)}</td><td>{event.actor_name ?? event.actor_role}</td><td>{humanize(event.action)}</td><td><pre className="audit-details">{JSON.stringify(event.details, null, 2)}</pre></td></tr>)}</tbody></table></div>{!history.audit.length && <p className="hint">No audit events yet.</p>}<p className="hint">Append-only — entries cannot be edited or deleted.</p></section>
    </>}
  </div>;
}
