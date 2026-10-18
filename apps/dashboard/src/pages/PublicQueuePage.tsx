import { humanize, qualificationName } from "../presentation";
import { useEffect, useRef, useState } from "react";
import { publicAssessments, publicQueueSnapshot, type PublicAssessment } from "../api";
import { StatusBadge } from "../components/DashboardShell";

const filters = ['all', 'submitted', 'in_review', 'recommended', 'needs_reassessment', 'not_recommended'];

export function PublicQueuePage({ publicView = false }: { publicView?: boolean }) {
  const [items, setItems] = useState<PublicAssessment[]>(() => publicQueueSnapshot() ?? []);
  const [loading, setLoading] = useState(!publicQueueSnapshot());
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState("");
  const [before, setBefore] = useState<number>();
  const [filter, setFilter] = useState('all');
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  useEffect(() => {
    let active = true;
    const cached = publicQueueSnapshot(before);
    setItems(cached ?? []);
    setLoading(!cached);
    async function load() {
      const current = ++sequence.current;
      setUpdating(true);
      try {
        const records = await publicAssessments(before);
        if (active && current === sequence.current) { setItems(records); setError(""); }
      } catch { if (active) setError("Could not load submitted assessments. Please try again."); }
      finally { if (active && current === sequence.current) { setLoading(false); setUpdating(false); } }
    }
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [before, refresh]);
  const filtered = items.filter(item => filter === 'all' || item.status === filter);
  const visible = publicView ? items.filter(item => item.report_available && item.report_id) : filtered;
  return <div className="page queue-page">
    <div className="pagehead"><div><h1>{publicView ? 'Public assessment queue' : 'Assessment queue'}</h1>
      <p className="sub">{publicView ? 'Signed PARAKH assessments open for public verification. No sign-in required.' : `${items.length} assessments across ${new Set(items.map(i => i.pack_code)).size} qualification packs — ${items.filter(i => ['submitted', 'in_review', 'needs_reassessment'].includes(i.status)).length} awaiting action`}</p>
    </div></div>
    {!publicView && <div className="chiprow" aria-label="Filter by status">{filters.map(value => <button key={value} aria-pressed={filter === value} className={`chip ${filter === value ? 'sel' : ''}`} onClick={() => setFilter(value)}>{value === 'recommended' ? 'Signed reports' : value === 'not_recommended' ? 'Not qualified' : humanize(value)} ({value === 'all' ? items.length : items.filter(i => i.status === value).length})</button>)}</div>}
    {error && <div className="notice error" role="alert">{error} <button className="secondary-button" onClick={() => setRefresh(v => v + 1)}>Retry</button></div>}
    {loading ? <div className="empty-state" role="status">Loading assessments…</div> : visible.length === 0 ? <div className="empty-state"><span className="empty-icon" aria-hidden="true">▤</span><h2>{items.length === 0 ? 'No submitted assessments yet.' : publicView ? 'No signed reports yet.' : 'No assessments in this view.'}</h2><p>{items.length === 0 ? 'Submitted assessments will appear here automatically.' : 'Choose another filter or check again after a review is completed.'}</p></div> : publicView ?
      <div className="public-reports">{visible.map(item => <article className="card public-report" key={item.id}><div><h2>{item.candidate_display_name}</h2><p className="sub">{qualificationName(item.pack_code, item.pack_name)} <small className="pack-reference">{item.pack_code}</small> · {item.report_id}</p></div><StatusBadge value={item.report_available ? item.outcome ?? item.status : item.status} /><a className="openlink" href={`#/verify/${encodeURIComponent(item.report_id!)}`}>Verify this report →</a></article>)}</div> :
      <div className="tablewrap"><table><thead><tr><th>Worker</th><th>Qualification pack</th><th>Submitted</th><th>Status</th><th><span className="sr-only">Open assessment</span></th></tr></thead>
        <tbody>{visible.map(item => <tr key={item.id}><td><div className="worker">{item.candidate_display_name}</div><a className="wid" href={`#/assessments/${item.id}`}>#{item.id}</a></td><td>{qualificationName(item.pack_code, item.pack_name)}<small className="pack-reference">{item.pack_code}</small></td><td>{new Date(item.submitted_at).toLocaleString('en-IN', {dateStyle: 'medium', timeStyle: 'short'})}</td><td><StatusBadge value={item.report_available ? item.outcome ?? item.status : item.status} /><div className="hint">{item.tasks_completed}/{item.tasks_total} tasks · v{item.revision_number}</div></td><td><a className="openlink" href={`#/assessments/${item.id}`} aria-label={`Open assessment ${item.id}`}>Open →</a></td></tr>)}</tbody>
      </table></div>}
    <div className="queue-footer"><span className="hint" role="status">{updating ? 'Updating assessments…' : 'Updates every 15 seconds. Names appear only with candidate consent.'}</span><div className="panel-actions">{before && <button className="secondary-button" onClick={() => setBefore(undefined)}>Newest submissions</button>}{items.length === 50 && <button className="secondary-button" onClick={() => setBefore(items[items.length - 1].id)}>Older submissions →</button>}</div></div>
  </div>;
}
