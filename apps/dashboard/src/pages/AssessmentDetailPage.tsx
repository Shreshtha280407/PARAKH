import { useEffect, useState } from "react";
import { getAssessment, getAssessmentRubric } from "../api";
import { navigate } from "../useHashRoute";
import { ApiError, type AssessmentOut, type RubricItemOut } from "../types";

type LoadState = "loading" | "error" | "ready";

function formatBytes(n: number): string {
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export function AssessmentDetailPage({ id }: { id: number }) {
  const [assessment, setAssessment] = useState<AssessmentOut | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [rubric, setRubric] = useState<RubricItemOut[] | null>(null);
  const [rubricError, setRubricError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    getAssessment(id)
      .then((result) => {
        if (cancelled) return;
        setAssessment(result);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Could not reach the server.");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function loadRubric() {
    setRubricError(null);
    try {
      setRubric(await getAssessmentRubric(id));
    } catch (err) {
      setRubricError(err instanceof ApiError ? err.message : "Could not load the rubric.");
    }
  }

  return (
    <div className="page">
      <button className="link-button" onClick={() => navigate("#/queue")}>
        ← Back to queue
      </button>
      {state === "loading" && <p>Loading…</p>}
      {state === "error" && <p className="error">Failed to load this assessment: {error}</p>}
      {state === "ready" && assessment && (
        <>
          <h1>Assessment #{assessment.id}</h1>

          <section className="card">
            <h2>Worker summary</h2>
            <dl>
              <dt>Worker</dt>
              <dd>{assessment.worker_name} (id {assessment.worker_id})</dd>
              <dt>Qualification Pack</dt>
              <dd>
                {assessment.pack_name} ({assessment.pack_code})
              </dd>
              <dt>Assessment status</dt>
              <dd>
                <span className={`status status-${assessment.status}`}>{assessment.status}</span>
              </dd>
              <dt>Total evidence</dt>
              <dd>
                {formatBytes(assessment.total_bytes_used)} / {formatBytes(assessment.total_budget_bytes)}
              </dd>
              <dt>Created</dt>
              <dd>{new Date(assessment.created_at).toLocaleString()}</dd>
            </dl>
          </section>

          <section className="card">
            <h2>Fixed five tasks</h2>
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Status</th>
                  <th>Evidence used</th>
                  <th>Evidence items (integrity)</th>
                </tr>
              </thead>
              <tbody>
                {assessment.tasks.map((task) => (
                  <tr key={task.task_code}>
                    <td>{task.task_code}</td>
                    <td>
                      <span className={`status status-${task.status}`}>{task.status}</span>
                    </td>
                    <td>
                      {formatBytes(task.bytes_used)} / {formatBytes(task.budget_bytes)}
                    </td>
                    <td>
                      {task.evidence.length === 0 ? (
                        <em>No evidence uploaded yet</em>
                      ) : (
                        <ul className="evidence-list">
                          {task.evidence.map((e) => (
                            <li key={e.id}>
                              {e.kind} · {e.mime} · {formatBytes(e.declared_size_bytes)}
                              <br />
                              <code title="Server-verified SHA-256">{e.sha256.slice(0, 16)}…</code>{" "}
                              <span className="badge-ok">verified</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card">
            <h2>Rubric</h2>
            {rubric === null && (
              <button onClick={loadRubric}>Show rubric ({assessment.pack_code})</button>
            )}
            {rubricError && <p className="error">{rubricError}</p>}
            {rubric !== null && (
              <>
                <p className="hint">
                  MVP assessor-support rubric; not an official SSC scoring replacement. {rubric.length} criteria.
                </p>
                <ul className="rubric-list">
                  {rubric.map((item) => (
                    <li key={item.pc_full_id}>
                      <strong>{item.pc_full_id}</strong> — {item.marks} marks
                      {item.critical && <span className="badge-critical">critical</span>}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
