import { useEffect, useRef, useState } from "react";
import {
  createReassessmentRequest,
  decideAssessment,
  evidenceContentUrl,
  evidenceThumbnailUrl,
  getAssessment,
  getAssessmentRubric,
  getAuditLog,
  getCompetencyProfile,
  getReportReceipt,
  getReportSnapshot,
  getReview,
  getSyncStatus,
  listReassessmentRequests,
  listRevisions,
  putScore,
  reassess,
  reportDownloadUrl,
  revokeWorkerToken,
  rotateWorkerToken,
  signOff,
  startReview,
  verifyReport,
} from "../api";
import { navigate } from "../useHashRoute";
import {
  ApiError,
  type AssessmentOut,
  type AssessmentRevisionOut,
  type AuditLogEntryOut,
  type CompetencyProfileOut,
  type ComputedOutcomeValue,
  type CriterionReviewItemOut,
  type EvidenceReceiptOut,
  type EvidenceStatus,
  type ReassessmentRequestOut,
  type ReportVerifyOut,
  type RubricItemOut,
  type SignedReportOut,
  type SyncStatusOut,
} from "../types";

type LoadState = "loading" | "error" | "ready";

function formatBytes(n: number): string {
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  const totalSeconds = Math.round(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** The protected evidence gallery/player item: plays video inline and shows the photo at
 * preview size directly in the page (both authorised by the browser's own cookie-based
 * dashboard session -- the same credentialed request the thumbnail/content endpoints already
 * require, see server/app/routers/evidence.py's dual auth). A failed/queued thumbnail job
 * (section B.4 of the P6 spec) shows a clear, safe fallback rather than a broken image or a
 * claim that the media itself is missing -- the ORIGINAL content is always still playable
 * regardless of thumbnail/metadata job outcome. */
function EvidencePreview({ assessmentId, evidence }: { assessmentId: number; evidence: EvidenceReceiptOut }) {
  const contentUrl = evidenceContentUrl(assessmentId, evidence.id);
  const [mediaFailed, setMediaFailed] = useState(false);

  return (
    <li className="evidence-gallery-item">
      <div className="evidence-media">
        {mediaFailed ? (
          <div className="thumb evidence-media-fallback">media unavailable</div>
        ) : evidence.kind === "video" ? (
          <video
            className="thumb"
            controls
            preload="metadata"
            src={contentUrl}
            poster={evidence.thumbnail_status === "completed" ? evidenceThumbnailUrl(assessmentId, evidence.id) : undefined}
            onError={() => setMediaFailed(true)}
          />
        ) : (
          <img className="thumb" src={contentUrl} alt="evidence" onError={() => setMediaFailed(true)} />
        )}
      </div>
      <div className="evidence-meta">
        {evidence.kind} · {evidence.mime} · {formatBytes(evidence.declared_size_bytes)}
        {evidence.width_px && evidence.height_px && (
          <>
            {" "}
            · {evidence.width_px}×{evidence.height_px}
          </>
        )}
        {evidence.kind === "video" && evidence.duration_ms && <> · {formatDuration(evidence.duration_ms)}</>}
        <br />
        <code title="Server-verified SHA-256">{evidence.sha256.slice(0, 16)}…</code>{" "}
        <span className="badge-ok">hash verified</span>
        {evidence.metadata_status === "unavailable" && (
          <span className="hint"> · metadata unavailable (media itself is unaffected)</span>
        )}
        <br />
        {evidence.is_current_revision ? (
          <span className="status status-submitted">v{evidence.revision_number} · current</span>
        ) : (
          <span className="status status-needs_reassessment">v{evidence.revision_number} · historical</span>
        )}{" "}
        <span className="hint" title="Device-reported, not independently verified">
          captured {evidence.device_captured_at ? new Date(evidence.device_captured_at).toLocaleString() : "not recorded"}
        </span>
        <br />
        <a href={contentUrl} target="_blank" rel="noreferrer">
          open in a new tab
        </a>
      </div>
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
        {item.score?.needs_review && (
          <span className="badge-critical" title="This task was reopened for reassessment -- re-score before signing off">
            needs re-review
          </span>
        )}
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

  const [syncStatus, setSyncStatus] = useState<SyncStatusOut | null>(null);
  const [syncStatusError, setSyncStatusError] = useState<string | null>(null);
  const [activeTaskTab, setActiveTaskTab] = useState<string | null>(null);
  const [auditLog, setAuditLog] = useState<AuditLogEntryOut[] | null>(null);
  const [auditLogError, setAuditLogError] = useState<string | null>(null);

  // P7: revision history + task-specific reassessment requests.
  const [revisions, setRevisions] = useState<AssessmentRevisionOut[] | null>(null);
  const [reassessmentRequests, setReassessmentRequests] = useState<ReassessmentRequestOut[] | null>(null);
  const [showReassessDialog, setShowReassessDialog] = useState(false);
  const [reassessTaskCodes, setReassessTaskCodes] = useState<string[]>([]);
  const [reassessReason, setReassessReason] = useState("");
  const [reassessInstructions, setReassessInstructions] = useState("");
  const [reassessError, setReassessError] = useState<string | null>(null);

  // P7: password-confirmed sign-off.
  const [signOffPassword, setSignOffPassword] = useState("");
  const [signOffRecommendation, setSignOffRecommendation] = useState<ComputedOutcomeValue | "">("");
  const [signOffOverrideReason, setSignOffOverrideReason] = useState("");
  const [signOffError, setSignOffError] = useState<string | null>(null);
  const [signOffBusy, setSignOffBusy] = useState(false);

  // Bug found during live P7 verification, two parts:
  //  1. This page's many lazily-loaded panels (rubric, review, profile,
  //     report, audit log, revision history/reassessment requests) are
  //     plain useState with no reset -- navigating straight from one
  //     assessment to another left the PREVIOUS assessment's data on
  //     screen. Fixed below by resetting everything derived from `id`
  //     whenever `id` changes.
  //  2. That reset alone isn't enough: an async call already in flight for
  //     the OLD id (e.g. loadRevisionHistory() kicked off just before
  //     navigating away) can resolve AFTER the reset and clobber the NEW
  //     id's freshly-cleared state with the old assessment's data. Fixed
  //     by stamping every async loader's response against this ref before
  //     applying it -- a response is only applied while it's still for the
  //     assessment currently on screen.
  const currentIdRef = useRef(id);
  useEffect(() => {
    currentIdRef.current = id;
  }, [id]);

  useEffect(() => {
    setRubric(null);
    setRubricError(null);
    setReview(null);
    setReviewError(null);
    setProfile(null);
    setDecisionNotes("");
    setActionError(null);
    setNewWorkerToken(null);
    setNewAssessmentId(null);
    setReport(null);
    setReportVerify(null);
    setSyncStatus(null);
    setSyncStatusError(null);
    setActiveTaskTab(null);
    setAuditLog(null);
    setAuditLogError(null);
    setRevisions(null);
    setReassessmentRequests(null);
    setShowReassessDialog(false);
    setReassessTaskCodes([]);
    setReassessReason("");
    setReassessInstructions("");
    setReassessError(null);
    setSignOffPassword("");
    setSignOffRecommendation("");
    setSignOffOverrideReason("");
    setSignOffError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function reload() {
    setState("loading");
    getAssessment(id)
      .then((result) => {
        if (currentIdRef.current !== id) return;
        setAssessment(result);
        setState("ready");
        setActiveTaskTab((prev) => prev ?? result.tasks[0]?.task_code ?? null);
        if (result.current_revision_id) {
          getSyncStatus(id, result.current_revision_id)
            .then((status) => {
              if (currentIdRef.current === id) setSyncStatus(status);
            })
            .catch((err) => {
              if (currentIdRef.current === id) setSyncStatusError(err instanceof ApiError ? err.message : "Could not load sync status.");
            });
        }
      })
      .catch((err) => {
        if (currentIdRef.current !== id) return;
        setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Could not reach the server.");
        setState("error");
      });
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // P7: a signed report may already exist from an earlier session (e.g. a page
  // reload) -- fetch its receipt passively (no password needed) so the panel
  // shows the right state without the assessor re-entering their password just
  // to SEE it again.
  useEffect(() => {
    if (assessment?.status !== "recommended") return;
    Promise.all([getReportReceipt(id), getReportSnapshot(id)])
      .then(([receipt, snapshot]) => {
        if (currentIdRef.current !== id) return;
        setReport({
          assessment_id: receipt.assessment_id,
          report_uid: receipt.report_id,
          revision_number: receipt.revision_number,
          pdf_sha256: receipt.pdf_sha256,
          signature: receipt.signature,
          key_id: receipt.key_id,
          computed_recommendation: snapshot.computed_recommendation as ComputedOutcomeValue,
          final_recommendation: snapshot.final_recommendation as ComputedOutcomeValue,
          override_reason: snapshot.override_reason,
          signed_at: receipt.signed_at,
        });
      })
      .catch(() => {
        // Not signed yet -- the sign-off panel below handles that state.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, assessment?.status]);

  function loadRevisionHistory() {
    const forId = id;
    listRevisions(forId)
      .then((result) => {
        if (currentIdRef.current === forId) setRevisions(result);
      })
      .catch(() => undefined);
    listReassessmentRequests(forId)
      .then((result) => {
        if (currentIdRef.current === forId) setReassessmentRequests(result);
      })
      .catch(() => undefined);
  }

  async function loadRubric() {
    const forId = id;
    setRubricError(null);
    try {
      const result = await getAssessmentRubric(forId);
      if (currentIdRef.current === forId) setRubric(result);
    } catch (err) {
      if (currentIdRef.current === forId) setRubricError(err instanceof ApiError ? err.message : "Could not load the rubric.");
    }
  }

  async function loadReview() {
    const forId = id;
    setReviewError(null);
    try {
      const result = await getReview(forId);
      if (currentIdRef.current === forId) setReview(result);
    } catch (err) {
      if (currentIdRef.current === forId) setReviewError(err instanceof ApiError ? err.message : "Could not load the review.");
    }
  }

  async function loadAuditLog() {
    const forId = id;
    setAuditLogError(null);
    try {
      const result = await getAuditLog(forId);
      if (currentIdRef.current === forId) setAuditLog(result);
    } catch (err) {
      if (currentIdRef.current === forId) setAuditLogError(err instanceof ApiError ? err.message : "Could not load the audit log.");
    }
  }

  async function loadProfile() {
    const forId = id;
    try {
      const result = await getCompetencyProfile(forId);
      if (currentIdRef.current === forId) setProfile(result);
    } catch {
      // decision support only -- a failure here shouldn't block the rest of the page
    }
  }

  // Guards every "apply this freshly-returned AssessmentOut" call the same
  // way the loaders above are guarded -- see the stale-navigation bug note
  // near currentIdRef's declaration.
  function applyAssessmentIfCurrent(forId: number, updated: AssessmentOut) {
    if (currentIdRef.current === forId) setAssessment(updated);
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
        <h2>Declaration &amp; QP match</h2>
        {assessment.declared_match_result ? (
          <dl>
            <dt>Match result</dt>
            <dd>
              <span className={`status status-${assessment.declared_match_result.toLowerCase()}`}>
                {assessment.declared_match_result}
              </span>
              {assessment.declared_coverage_fraction && (
                <> — {(Number(assessment.declared_coverage_fraction) * 100).toFixed(0)}% NOS coverage</>
              )}
            </dd>
            {assessment.declared_gap_task_codes && assessment.declared_gap_task_codes.length > 0 && (
              <>
                <dt>Gap tasks (extra evidence needed)</dt>
                <dd>{assessment.declared_gap_task_codes.join(", ")}</dd>
              </>
            )}
            <dt>Match reasoning</dt>
            <dd>
              {assessment.declared_match_reasons && assessment.declared_match_reasons.length > 0 ? (
                <ul>
                  {assessment.declared_match_reasons.map((reason, i) => (
                    <li key={i}>{reason}</li>
                  ))}
                </ul>
              ) : (
                <span className="hint">
                  Not recorded (synced before this field existed on the device, or no reasons returned by the
                  matcher).
                </span>
              )}
            </dd>
          </dl>
        ) : (
          <p className="hint">No match summary has synced from the phone yet.</p>
        )}
        <p className="disclaimer">
          This is a summary snapshot synced from the device at seal time (match result, coverage, gap tasks, and
          the matcher's own overall reasoning) -- not the worker's full declaration question-by-question answers,
          which this server never receives. The match itself was computed entirely on-device by the deterministic
          Kotlin/Python matcher, never by this server.
        </p>
      </section>

      <section className="card">
        <h2>Sync &amp; package integrity</h2>
        {!assessment.current_revision_id && <p className="hint">This device has not started syncing yet.</p>}
        {syncStatusError && <p className="error">{syncStatusError}</p>}
        {syncStatus && (
          <dl>
            <dt>Revision</dt>
            <dd>
              <code>{syncStatus.revision_id}</code>
            </dd>
            <dt>Manifest</dt>
            <dd>
              <span className={`status status-${syncStatus.manifest_state}`}>{syncStatus.manifest_state}</span>
              {syncStatus.manifest_rejection_reason && <span className="error"> — {syncStatus.manifest_rejection_reason}</span>}
            </dd>
            <dt>Items verified</dt>
            <dd>
              {syncStatus.items.filter((i) => i.state === "verified").length} / {syncStatus.items.length}
              {syncStatus.all_items_verified && <span className="badge-ok"> package complete</span>}
            </dd>
          </dl>
        )}
      </section>

      <section className="card">
        <h2>Evidence by task</h2>
        <div className="tab-bar">
          {assessment.tasks.map((task) => (
            <button
              key={task.task_code}
              className={`tab-button${activeTaskTab === task.task_code ? " tab-button-active" : ""}`}
              onClick={() => setActiveTaskTab(task.task_code)}
            >
              {task.task_code}
              {task.evidence.length > 0 && ` (${task.evidence.length})`}
            </button>
          ))}
        </div>
        {assessment.tasks
          .filter((task) => task.task_code === activeTaskTab)
          .map((task) => (
            <div key={task.task_code}>
              <p className="hint">
                <span className={`status status-${task.status}`}>{task.status}</span> ·{" "}
                {formatBytes(task.bytes_used)} / {formatBytes(task.budget_bytes)} used
              </p>
              {task.evidence.length === 0 ? (
                <em>No evidence uploaded yet</em>
              ) : (
                <ul className="evidence-list evidence-gallery">
                  {task.evidence.map((e) => (
                    <EvidencePreview key={e.id} assessmentId={assessment.id} evidence={e} />
                  ))}
                </ul>
              )}
            </div>
          ))}
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
                applyAssessmentIfCurrent(assessment.id, await startReview(assessment.id));
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
                  <dt>Computed outcome (§4.4)</dt>
                  <dd>
                    <span className={`status status-${profile.computed_outcome.toLowerCase()}`}>{profile.computed_outcome}</span>
                  </dd>
                </dl>
                <table>
                  <thead>
                    <tr>
                      <th>NOS</th>
                      <th>Marks</th>
                      <th>%</th>
                      <th>Competent</th>
                      <th>Flags</th>
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
                        <td>{n.competent ? <span className="badge-ok">yes</span> : "no"}</td>
                        <td>
                          {n.critical_violation && <span className="badge-critical">critical PC below level 2</span>}
                          {n.has_insufficient_evidence && <span className="badge-critical">insufficient evidence</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button onClick={loadProfile}>Refresh</button>
              </>
            )}
          </section>

          <section className="card">
            <h2>Targeted reassessment</h2>
            <p className="hint">
              Reopen specific task(s) for the worker to recapture -- the worker's app unlocks ONLY those tasks;
              every other task's evidence and scores stay exactly as they are. Preferred over "Needs reassessment"
              below when only part of the evidence is insufficient.
            </p>
            <button disabled={actionBusy} onClick={() => setShowReassessDialog(true)}>
              Request targeted reassessment…
            </button>
            <h3>Broad reassessment (whole-assessment restart)</h3>
            <p className="hint">
              This is the human assessor's call -- never auto-derived from the competency profile above. Starts an
              entirely new assessment for the same worker; this one's data stays untouched.
            </p>
            <label>
              Notes
              <textarea value={decisionNotes} onChange={(e) => setDecisionNotes(e.target.value)} rows={2} />
            </label>
            <div className="panel-actions">
              <button
                className="danger-button"
                disabled={actionBusy}
                onClick={() =>
                  runAction(async () => {
                    applyAssessmentIfCurrent(assessment.id, await decideAssessment(assessment.id, "needs_reassessment", decisionNotes));
                  })
                }
              >
                Needs reassessment
              </button>
            </div>
            {actionError && <p className="error">{actionError}</p>}
          </section>

          <section className="card">
            <h2>Sign off</h2>
            <p className="hint">
              Password-confirmed: validated on the backend against your own authenticated account, never a
              frontend-only check. Produces the one, immutable, Ed25519-signed PDF for this assessment.
            </p>
            <label>
              Final recommendation
              <select
                value={signOffRecommendation || profile?.computed_outcome || ""}
                onChange={(e) => setSignOffRecommendation(e.target.value as ComputedOutcomeValue)}
              >
                <option value="" disabled>
                  Load the competency profile above first
                </option>
                <option value="RECOMMEND_CERTIFICATION">RECOMMEND_CERTIFICATION</option>
                <option value="PARTIALLY_COMPETENT">PARTIALLY_COMPETENT</option>
                <option value="NOT_YET_COMPETENT">NOT_YET_COMPETENT</option>
                <option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE</option>
              </select>
            </label>
            {profile && (signOffRecommendation || profile.computed_outcome) !== profile.computed_outcome && (
              <label>
                Override reason (required -- differs from the computed outcome: {profile.computed_outcome})
                <textarea
                  value={signOffOverrideReason}
                  onChange={(e) => setSignOffOverrideReason(e.target.value)}
                  rows={2}
                  placeholder="Why does your final recommendation differ from the computed outcome?"
                />
              </label>
            )}
            <label>
              Confirm your password
              <input
                type="password"
                value={signOffPassword}
                onChange={(e) => setSignOffPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <div className="panel-actions">
              <button
                disabled={signOffBusy || !signOffPassword}
                onClick={async () => {
                  setSignOffError(null);
                  setSignOffBusy(true);
                  try {
                    const finalRecommendation = (signOffRecommendation || profile?.computed_outcome) as ComputedOutcomeValue;
                    const signOffForId = assessment.id;
                    const signed = await signOff(signOffForId, {
                      password: signOffPassword,
                      final_recommendation: finalRecommendation,
                      override_reason: signOffOverrideReason || null,
                    });
                    if (currentIdRef.current === signOffForId) {
                      setReport(signed);
                      setSignOffPassword("");
                      reload();
                    }
                  } catch (err) {
                    setSignOffError(err instanceof ApiError ? err.message : "Sign-off failed.");
                  } finally {
                    setSignOffBusy(false);
                  }
                }}
              >
                {signOffBusy ? "Signing…" : "Sign off and produce signed report"}
              </button>
            </div>
            {signOffError && <p className="error">{signOffError}</p>}
          </section>
        </>
      )}

      {showReassessDialog && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card">
            <h2>Request targeted reassessment</h2>
            <p className="hint">The worker's app will unlock ONLY the task(s) you select here.</p>
            <fieldset>
              <legend>Tasks to reopen</legend>
              {assessment.tasks.map((task) => (
                <label key={task.task_code} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={reassessTaskCodes.includes(task.task_code)}
                    onChange={(e) =>
                      setReassessTaskCodes((prev) =>
                        e.target.checked ? [...prev, task.task_code] : prev.filter((c) => c !== task.task_code),
                      )
                    }
                  />
                  {task.task_code}
                </label>
              ))}
            </fieldset>
            <label>
              Reason (required)
              <textarea value={reassessReason} onChange={(e) => setReassessReason(e.target.value)} rows={2} />
            </label>
            <label>
              What to capture (required)
              <textarea value={reassessInstructions} onChange={(e) => setReassessInstructions(e.target.value)} rows={2} />
            </label>
            {reassessError && <p className="error">{reassessError}</p>}
            <div className="panel-actions">
              <button
                disabled={actionBusy || reassessTaskCodes.length === 0 || !reassessReason.trim() || !reassessInstructions.trim()}
                onClick={() =>
                  runAction(async () => {
                    setReassessError(null);
                    try {
                      await createReassessmentRequest(assessment.id, {
                        task_codes: reassessTaskCodes,
                        reason: reassessReason,
                        capture_instructions: reassessInstructions,
                      });
                      setShowReassessDialog(false);
                      setReassessTaskCodes([]);
                      setReassessReason("");
                      setReassessInstructions("");
                      loadRevisionHistory();
                      reload();
                    } catch (err) {
                      setReassessError(err instanceof ApiError ? err.message : "Could not create the reassessment request.");
                    }
                  })
                }
              >
                Send request
              </button>
              <button onClick={() => setShowReassessDialog(false)}>Cancel</button>
            </div>
          </div>
        </div>
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

      {assessment.status === "recommended" && (
        <section className="card">
          <h2>Signed report</h2>
          <p className="hint">
            A tamper-evident, immutable PDF (Ed25519-signed over its own rendered bytes) -- an assessor
            recommendation, not an official certificate. Produced once via Sign off above; never regenerated or
            re-signed by this panel.
          </p>
          {report === null ? (
            <p className="hint">Not signed yet -- use the Sign off panel above.</p>
          ) : (
            <>
              <dl>
                <dt>Report ID</dt>
                <dd>
                  <code>{report.report_uid}</code>
                </dd>
                <dt>Revision</dt>
                <dd>v{report.revision_number}</dd>
                <dt>PDF SHA-256</dt>
                <dd>
                  <code>{report.pdf_sha256}</code>
                </dd>
                <dt>Computed vs final recommendation</dt>
                <dd>
                  {report.computed_recommendation} → {report.final_recommendation}
                  {report.override_reason && <span className="hint"> ({report.override_reason})</span>}
                </dd>
                <dt>Signed</dt>
                <dd>{new Date(report.signed_at).toLocaleString()}</dd>
              </dl>
              <div className="panel-actions">
                <a href={reportDownloadUrl(assessment.id, "json")} target="_blank" rel="noreferrer">
                  Download JSON
                </a>
                <a href={reportDownloadUrl(assessment.id, "pdf")} target="_blank" rel="noreferrer">
                  Download PDF
                </a>
                <a href={reportDownloadUrl(assessment.id, "receipt")} target="_blank" rel="noreferrer">
                  Download receipt (for offline verify_report.py)
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
                <button onClick={() => navigate(`#/verify/${report.report_uid}`)}>Open public verify page</button>
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

      {assessment.status === "needs_reassessment" && (
        <section className="card">
          <h2>Signed report</h2>
          <p className="hint">Signing is blocked while a reassessment is pending or in progress for this assessment.</p>
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

      <section className="card">
        <h2>Revision history (v1/v2/…)</h2>
        <p className="hint">
          v1 is always the original submission (immutable, still viewable above). A later revision exists only for
          the task(s) a targeted reassessment reopened -- every other task's evidence and scores stay exactly as
          they were.
        </p>
        {revisions === null && <button onClick={loadRevisionHistory}>Load revision history</button>}
        {revisions !== null && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Revision</th>
                  <th>Reopened tasks</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {revisions.map((r) => (
                  <tr key={r.revision_number}>
                    <td>v{r.revision_number}</td>
                    <td>{r.reopened_task_codes ? r.reopened_task_codes.join(", ") : "all (original)"}</td>
                    <td>
                      <span className={`status status-${r.status}`}>{r.status}</span>
                    </td>
                    <td>{new Date(r.created_at).toLocaleString()}</td>
                    <td>{r.submitted_at ? new Date(r.submitted_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {reassessmentRequests !== null && reassessmentRequests.length > 0 && (
          <>
            <h3>Reassessment requests</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Revision</th>
                    <th>Tasks</th>
                    <th>Reason</th>
                    <th>Capture instructions</th>
                    <th>Status</th>
                    <th>Requested</th>
                  </tr>
                </thead>
                <tbody>
                  {reassessmentRequests.map((r) => (
                    <tr key={r.id}>
                      <td>v{r.revision_number}</td>
                      <td>{r.task_codes.join(", ")}</td>
                      <td>{r.reason}</td>
                      <td>{r.capture_instructions}</td>
                      <td>
                        <span className={`status status-${r.status}`}>{r.status}</span>
                      </td>
                      <td>{new Date(r.requested_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>Audit log</h2>
        <p className="hint">Append-only accountability trail -- who did what, and when. Nothing here is ever edited or removed.</p>
        {auditLog === null && <button onClick={loadAuditLog}>Load audit log</button>}
        {auditLogError && <p className="error">{auditLogError}</p>}
        {auditLog !== null && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((entry) => (
                  <tr key={entry.id}>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
                    <td>
                      {entry.actor_name ?? entry.actor_role} ({entry.actor_role})
                    </td>
                    <td>{entry.action}</td>
                    <td>
                      <code className="audit-details">{JSON.stringify(entry.details)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
