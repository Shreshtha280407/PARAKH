import { useEffect, useRef, useState } from "react";
import { publicAssessments, type PublicAssessment } from "../api";

export function PublicQueuePage() {
  const [items, setItems] = useState<PublicAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [before, setBefore] = useState<number>();
  const sequence = useRef(0);
  useEffect(() => {
    let active = true;
    async function load() {
      const current = ++sequence.current;
      try {
        const records = await publicAssessments(before);
        if (active && current === sequence.current) { setItems(records); setError(""); }
      } catch { if (active) setError("Could not load submitted assessments. Please try again."); }
      finally { if (active) setLoading(false); }
    }
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [before]);
  return <div className="page"><h1>Submitted assessments</h1>
    <p>Public summaries refresh every 15 seconds. Names appear only with candidate consent.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <p>Loading…</p> : items.length === 0 ? <p>No submitted assessments yet.</p> :
      <table><thead><tr><th>Assessment</th><th>Candidate</th><th>Qualification pack</th><th>Submitted</th><th>Status</th><th>Tasks</th><th>Review</th><th>Report</th></tr></thead>
        <tbody>{items.map(item => <tr key={item.id}>
          <td><a href={`#/assessments/${item.id}`}>#{item.id}</a></td><td>{item.candidate_display_name}</td>
          <td>{item.pack_code}</td><td>{new Date(item.submitted_at).toLocaleString()}</td><td>{item.status}</td>
          <td>{item.tasks_completed}/{item.tasks_total}</td><td>{item.review_status} · v{item.revision_number}</td>
          <td>{item.report_available && item.report_id ? <a href={`#/verify/${item.report_id}`}>Verify report</a> : "Not available"}</td>
        </tr>)}</tbody></table>}
    {before && <button onClick={() => setBefore(undefined)}>Newest submissions</button>}
    {items.length === 50 && <button onClick={() => setBefore(items[items.length - 1].id)}>Older submissions</button>}
  </div>;
}
