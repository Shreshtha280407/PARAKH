import { useEffect, useState } from "react";
import {
  BASE_URL,
  decideAssessment,
  generateReport,
  getAssessment,
  getAssessmentRubric,
  getCompetencyProfile,
  getReview,
  putScore,
  reassess,
  revokeWorkerToken,
  rotateWorkerToken,
  startReview,
  verifyReport,
} from "../api";
import { navigate } from "../useHashRoute";
import {
  ApiError,
  type AssessmentOut,
  type CompetencyProfileOut,
  type CriterionReviewItemOut,
  type EvidenceReceiptOut,
  type EvidenceStatus,
  type ReportVerifyOut,
  type RubricItemOut,
  type SignedReportOut,
} from "../types";

type LoadState = "loading" | "error" | "ready";

function formatBytes(n: number): string {
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function EvidencePreview({ assessmentId, evidence }: { assessmentId: number; evidence: EvidenceReceiptOut }) {
  const contentUrl = `${BASE_URL}/assessments/${assessmentId}/evidence/${evidence.id}/content`;
  const thumbUrl = `${BASE_URL}/assessments/${assessmentId}/evidence/${evidence.id}/thumbnail`;
  return (
    <li>
      {evidence.kind} · {evidence.mime} · {formatBytes(evidence.declared_size_bytes)}
      <br />
      <code title="Server-verified SHA-256">{evidence.sha256.slice(0, 16)}…</code>{" "}
      <span className="badge-ok">verified</span>
      <br />
      <a href={contentUrl} target="_blank" rel="noreferrer">
        view full {evidence.kind}
      </a>
      {evidence.kind === "video" && (
        <>
          {" · "}
          <img className="thumb" src={thumbUrl} alt="thumbnail" onError={(e) => (e.currentTarget.style.display = "none")} />
        </>
      )}
      {evidence.kind === "photo" && <img className="thumb" src={thumbUrl} alt="thumbnail" />}
    </li>
  );
}

function ScoreRow({
  assessmentId,
  item,
  onSaved,
}: {
  assessmentId: number;
  item: CriterionReviewItemOut;
  onSaved: (updated: CriterionReviewItemOut) => void;
}) {
  const [scoreLevel, setScoreLevel] = useState(item.score?.score_level ?? 0);
  const [evidenceStatus, setEvidenceStatus] = useState<EvidenceStatus>(
    (item.score?.evidence_status as EvidenceStatus) ?? "DEMONSTRATED",
  );
  const [comment, setComment] = useState(item.score?.assessor_comment ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setErr(null);
    setSaving(true);
    try {
      const score = await putScore(assessmentId, {
        pc_full_id: item.pc_full_id,
        score_level: scoreLevel,
        evidence_status: evidenceStatus,
        assessor_comment: comment || null,
        expected_version: item.score?.version ?? 0,
      });
      onSaved({ ...item, score });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save this score.");
    } finally {
      setSaving(false);
    }
  }

  const commentRequired = evidenceStatus !== "DEMONSTRATED";

  return (
    <tr>
      <td>
        <strong>{item.pc_full_id}</strong> ({item.marks} marks{item.critical && <span className="badge-critical">critical</span>})
        <div className="hint">{item.evidence_hint}</div>
      </td>
      <td>
        <select value={scoreLevel} onChange={(e) => setScoreLevel(Number(e.target.value))}>
          {[0, 1, 2, 3].map((lvl) => (
            <option key={lvl} value={lvl}>
              {lvl} — {item.anchors[String(lvl)]?.slice(0, 40) ?? ""}
            </option>
          ))}
        </select>
      </td>
      <td>
        <select value={evidenceStatus} onChange={(e) => setEvidenceStatus(e.target.value as EvidenceStatus)}>
          <option value="DEMONSTRATED">DEMONSTRATED</option>
          <option value="NOT_OBSERVABLE">NOT_OBSERVABLE</option>
          <option value="NOT_APPLICABLE_IN_MVP">NOT_APPLICABLE_IN_MVP</option>
        </select>
      </td>
      <td>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={commentRequired ? "Required for this evidence status" : "Optional"}
          rows={2}
        />
      </td>
      <td>
        {item.score && <span className="hint">marks awarded: {item.score.marks_awarded}</span>}
        <button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {err && <p className="error">{err}</p>}
      </td>
    </tr>
  );
}

export function AssessmentDetailPage({ id }: { id: number }) {
  const [assessment, setAssessment] = useState<AssessmentOut | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [rubric, setRubric] = useState<RubricItemOut[] | null>(null);
  const [rubricError, setRubricError] = useState<string | null>(null);

  const [review, setReview] = useState<CriterionReviewItemOut[] | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [profile, setProfile] = useState<CompetencyProfileOut | null>(null);

  const [decisionNotes, setDecisionNotes] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [newWorkerToken, setNewWorkerToken] = useState<string | null>(null);
  const [newAssessmentId, setNewAssessmentId] = useState<number | null>(null);

  const [report, setReport] = useState<SignedReportOut | null>(null);
  const [reportVerify, setReportVerify] = useState<ReportVerifyOut | null>(null);

  function reload() {
    setState("loading");
    getAssessment(id)
      .then((result) => {
        setAssessment(result);
        setState("ready");
      })
      .catch((err) => {
        setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Could not reach the server.");
        setState("error");
      });
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function loadRubric() {
    setRubricError(null);
    try {
      setRubric(await getAssessmentRubric(id));
    } catch (err) {
      setRubricError(err instanceof ApiError ? err.message : "Could not load the rubric.");
    }
  }

  async function loadReview() {
    setReviewError(null);
    try {
      setReview(await getReview(id));
    } catch (err) {
      setReviewError(err instanceof ApiError ? err.message : "Could not load the review.");
    }
  }

  async function loadProfile() {
    try {
      setProfile(await getCompetencyProfile(id));
    } catch {
      // decision support only -- a failure here shouldn't block the rest of the page
    }
  }

  async function runAction(action: () => Promise<void>) {
    setActionError(null);
    setActionBusy(true);
    try {
      await action();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "That action failed.");
    } finally {
      setActionBusy(false);
    }
  }

  if (state === "loading") return <p>Loading…</p>;
  if (state === "error" || !assessment) return <p className="error">Failed to load this assessment: {error}</p>;

  return (
    <div className="page">
      <button className="link-button" onClick={() => navigate("#/queue")}>
        ← Back to queue
      </button>
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
            {assessment.reassessment_of_id && <span className="hint"> (reassessment of #{assessment.reassessment_of_id})</span>}
          </dd>
          <dt>Total evidence</dt>
          <dd>
            {formatBytes(assessment.total_bytes_used)} / {formatBytes(assessment.total_budget_bytes)}
          </dd>
          <dt>Created</dt>
          <dd>{new Date(assessment.created_at).toLocaleString()}</dd>
          {assessment.decision && (
            <>
              <dt>Decision</dt>
              <dd>
                {assessment.decision}
                {assessment.decision_notes && ` — ${assessment.decision_notes}`}
              </dd>
            </>
          )}
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
                        <EvidencePreview key={e.id} assessmentId={assessment.id} evidence={e} />
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
        {rubric === null && <button onClick={loadRubric}>Show rubric ({assessment.pack_code})</button>}
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

      {assessment.status === "submitted" && (
        <section className="card">
          <h2>Review</h2>
          <p className="hint">This assessment is submitted and awaiting an assessor to start reviewing it.</p>
          <button
            disabled={actionBusy}
            onClick={() =>
              runAction(async () => {
                setAssessment(await startReview(assessment.id));
              })
            }
          >
            Start review
          </button>
          {actionError && <p className="error">{actionError}</p>}
        </section>
      )}

      {assessment.status === "in_review" && (
        <>
          <section className="card">
            <h2>Score performance criteria</h2>
            {review === null && <button onClick={loadReview}>Load scoring sheet</button>}
            {reviewError && <p className="error">{reviewError}</p>}
            {review !== null && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th>Level (0-3)</th>
                      <th>Evidence status</th>
                      <th>Assessor comment</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {review.map((item) => (
                      <ScoreRow
                        key={item.pc_full_id}
                        assessmentId={assessment.id}
                        item={item}
                        onSaved={(updated) =>
                          setReview((prev) => prev!.map((r) => (r.pc_full_id === updated.pc_full_id ? updated : r)))
                        }
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h2>Competency profile (decision support only)</h2>
            {profile === null && <button onClick={loadProfile}>Load competency profile</button>}
            {profile !== null && (
              <>
                <p className="disclaimer">{profile.disclaimer}</p>
                <dl>
                  <dt>Scored</dt>
                  <dd>
                    {profile.pcs_scored} / {profile.pcs_total} criteria
                  </dd>
                  <dt>Overall</dt>
                  <dd>
                    {profile.overall_marks_awarded} / {profile.overall_marks_possible} ({profile.overall_percent}%,
                    minimum {profile.minimum_aggregate_passing_percent}%)
                  </dd>
                  <dt>Meets minimum threshold</dt>
                  <dd>{profile.meets_minimum_threshold ? "Yes" : "Not yet"}</dd>
                </dl>
                <table>
                  <thead>
                    <tr>
                      <th>NOS</th>
                      <th>Marks</th>
                      <th>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile.nos_breakdown.map((n) => (
                      <tr key={n.nos_code}>
                        <td>
                          {n.nos_code} — {n.nos_title}
                        </td>
                        <td>
                          {n.marks_awarded} / {n.marks_possible}
                        </td>
                        <td>{n.percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button onClick={loadProfile}>Refresh</button>
              </>
            )}
          </section>

          <section className="card">
            <h2>Recommendation</h2>
            <p className="hint">
              This is the human assessor's call -- never auto-derived from the competency profile above.
            </p>
            <label>
              Notes (optional, required reading on reassessment)
              <textarea value={decisionNotes} onChange={(e) => setDecisionNotes(e.target.value)} rows={2} />
            </label>
            <div className="panel-actions">
              <button
                disabled={actionBusy}
                onClick={() =>
                  runAction(async () => {
                    setAssessment(await decideAssessment(assessment.id, "recommended", decisionNotes));
                  })
                }
              >
                Recommend
              </button>
              <button
                className="danger-button"
                disabled={actionBusy}
                onClick={() =>
                  runAction(async () => {
                    setAssessment(await decideAssessment(assessment.id, "needs_reassessment", decisionNotes));
                  })
                }
              >
                Needs reassessment
              </button>
            </div>
            {actionError && <p className="error">{actionError}</p>}
          </section>
        </>
      )}

      {assessment.status === "needs_reassessment" && (
        <section className="card">
          <h2>Reassessment</h2>
          <p className="hint">
            Creates a brand-new assessment for the same worker and pack, with a fresh worker token. This
            assessment's data (tasks, evidence, scores, decision) is preserved untouched.
          </p>
          <button
            disabled={actionBusy}
            onClick={() =>
              runAction(async () => {
                const created = await reassess(assessment.id);
                setNewAssessmentId(created.id);
                setNewWorkerToken(created.worker_token);
              })
            }
          >
            Create reassessment
          </button>
          {newAssessmentId !== null && (
            <div className="token-reveal">
              <p>
                Created assessment #{newAssessmentId}. New worker token (shown once -- hand this to the worker, it
                will not be shown again):
              </p>
              <code>{newWorkerToken}</code>
              <br />
              <button onClick={() => navigate(`#/assessments/${newAssessmentId}`)}>Go to new assessment</button>
            </div>
          )}
          {actionError && <p className="error">{actionError}</p>}
        </section>
      )}

      {(assessment.status === "recommended" || assessment.status === "needs_reassessment") && (
        <section className="card">
          <h2>Signed report</h2>
          <p className="hint">
            A tamper-evident snapshot (Ed25519-signed) of the competency profile and decision -- decision support
            and an assessor recommendation only, never an official NCVET/MSDE certificate.
          </p>
          {report === null ? (
            <button
              disabled={actionBusy}
              onClick={() =>
                runAction(async () => {
                  setReport(await generateReport(assessment.id));
                })
              }
            >
              Generate / fetch report
            </button>
          ) : (
            <>
              <dl>
                <dt>SHA-256</dt>
                <dd>
                  <code>{report.sha256}</code>
                </dd>
                <dt>Signed</dt>
                <dd>{new Date(report.signed_at).toLocaleString()}</dd>
              </dl>
              <div className="panel-actions">
                <a href={`${BASE_URL}/assessments/${assessment.id}/report?format=json`} target="_blank" rel="noreferrer">
                  Download JSON
                </a>
                <a href={`${BASE_URL}/assessments/${assessment.id}/report?format=pdf`} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
                <button
                  onClick={() =>
                    runAction(async () => {
                      setReportVerify(await verifyReport(assessment.id));
                    })
                  }
                >
                  Verify
                </button>
              </div>
              {reportVerify && (
                <p className={reportVerify.valid ? "badge-ok" : "error"}>
                  {reportVerify.valid ? "Signature verified -- not tampered with." : "VERIFICATION FAILED -- do not trust this report."}
                </p>
              )}
            </>
          )}
          {actionError && <p className="error">{actionError}</p>}
        </section>
      )}

      <section className="card">
        <h2>Worker capability token</h2>
        <p className="hint">
          The worker's mobile app uses this opaque token (never a login) to upload evidence for this assessment.
        </p>
        <div className="panel-actions">
          <button
            disabled={actionBusy}
            onClick={() =>
              runAction(async () => {
                const result = await rotateWorkerToken(assessment.id);
                setNewWorkerToken(result.worker_token);
              })
            }
          >
            Rotate token
          </button>
          <button
            className="danger-button"
            disabled={actionBusy}
            onClick={() =>
              runAction(async () => {
                await revokeWorkerToken(assessment.id);
                setNewWorkerToken(null);
                reload();
              })
            }
          >
            Revoke token
          </button>
        </div>
        {newWorkerToken && assessment.status !== "needs_reassessment" && (
          <div className="token-reveal">
            <p>New token (shown once):</p>
            <code>{newWorkerToken}</code>
          </div>
        )}
        {actionError && <p className="error">{actionError}</p>}
      </section>
    </div>
  );
}
