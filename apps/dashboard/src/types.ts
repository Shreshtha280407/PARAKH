// Mirrors server/app/schemas.py. Kept hand-written and minimal rather than
// generated -- see contracts/openapi.json for the authoritative contract
// (tools/export_openapi.py / CI checks it stays fresh against the API).

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
}

export interface MeOut {
  id: number;
  role: string;
  display_name: string;
  email: string | null;
}

export interface QueueItemOut {
  id: number;
  worker_id: number;
  worker_name: string;
  pack_code: string;
  status: string;
  created_at: string;
}

export interface EvidenceReceiptOut {
  id: number;
  kind: string;
  mime: string;
  declared_size_bytes: number;
  sha256: string;
  created_at: string;
  thumbnail_status: string;
  metadata_status: string;
  duration_ms: number | null;
  width_px: number | null;
  height_px: number | null;
  // P7: which revision uploaded this item, and whether it's still part of the
  // assessment's CURRENT revision's evidence snapshot -- see
  // server/app/routers/assessments.py's _evidence_currency.
  revision_number: number;
  is_current_revision: boolean;
  // Device-reported, NOT independently verified -- never show this as if it
  // were a verified capture time (see models.EvidenceItem.device_captured_at).
  device_captured_at: string | null;
  quality_check_status: string;
  assistance: AssistanceSnapshot | null;
}

export type AssistanceStatus = "NOT_RUN" | "QUEUED" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED" | "UNAVAILABLE";
export type AssistanceFlagType = "DARK" | "OVEREXPOSED" | "BLURRY" | "CAMERA_MOTION" | "HANDS_NOT_DETECTED";
export interface AssistanceFlag {
  type: AssistanceFlagType;
  startMs: number;
  endMs: number | null;
  severity: "review";
  observed: number | null;
  threshold: number | null;
}
export interface AssistanceAnalysis {
  status: AssistanceStatus;
  provenance: { moduleVersion: string; profileVersion: string; profileSha256: string; modelSha256: string | null; sampleIntervalMs: 1000 } | null;
  coverage: { requestedSamples: number; analysedSamples: number; coveredDurationMs: number; motionRequestedPairs: number; motionAnalysedPairs: number };
  reviewRecommended: boolean | null;
  visibleRatio: number | null;
  visibleRatioGapFilled: number | null;
}
export interface AssistanceSnapshot {
  contractVersion: 1;
  source: "ON_DEVICE";
  assessmentId: string;
  taskId: string;
  evidenceId: string;
  revisionId: string;
  revisionNumber: number;
  mediaSha256: string;
  durationMs: number | null;
  status: AssistanceStatus;
  quality: AssistanceAnalysis | null;
  hands: AssistanceAnalysis | null;
  flags: AssistanceFlag[];
  completedAtMillis: number | null;
  errorCategory: string | null;
  intervalsTruncated: boolean;
}

export interface AssessmentTaskOut {
  task_code: string;
  budget_bytes: number;
  bytes_used: number;
  status: string;
  evidence: EvidenceReceiptOut[];
}

export interface AssessmentOut {
  id: number;
  worker_id: number;
  worker_name: string;
  pack_id: number;
  pack_code: string;
  pack_name: string;
  status: string;
  assessor_id: number | null;
  total_bytes_used: number;
  total_budget_bytes: number;
  created_at: string;
  submitted_at: string | null;
  decision: string | null;
  decision_notes: string | null;
  reassessment_of_id: number | null;
  // P6: honest, bounded declaration/match snapshot synced from the phone's durable
  // AssessmentDraftEntity (matchResult/overallCoverage/gapTaskIdsCsv) -- the full
  // declaration Q&A and on-device "because" reason text are NOT transmitted (see
  // docs/gates/P6.md's stated limitation; this is inherited from P3/P4's own scope,
  // not a P6 regression).
  declared_match_result: string | null;
  declared_coverage_fraction: string | null; // Decimal, serialised as a string
  declared_gap_task_codes: string[] | null;
  // P7: the matcher's overall "why" explanation -- a flat list of reason
  // strings, never a fabricated per-task breakdown (the matcher doesn't
  // produce one). Null means "not recorded" (synced before this field
  // existed on the Android side), distinct from an empty list.
  declared_match_reasons: string[] | null;
  current_revision_id: string | null;
  revision_number: number;
  tasks: AssessmentTaskOut[];
}

// ---- P6: resumable sync status ----

export type SyncItemState = "pending" | "uploading" | "verified" | "rejected";

export interface SyncItemStatusOut {
  client_evidence_id: string;
  task_code: string;
  kind: string;
  declared_bytes: number;
  state: SyncItemState;
  received_bytes: number | null;
  upload_session_id: number | null;
  evidence_id: number | null;
  rejection_reason: string | null;
}

export type ManifestSyncState = "none" | "received" | "complete" | "rejected";

export interface SyncStatusOut {
  assessment_id: number;
  assessment_status: string;
  revision_id: string | null;
  manifest_state: ManifestSyncState;
  manifest_rejection_reason: string | null;
  items: SyncItemStatusOut[];
  all_items_verified: boolean;
}

// ---- P6: audit log ----

export interface AuditLogEntryOut {
  id: number;
  actor_user_id: number | null;
  actor_name: string | null;
  actor_role: string;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface RubricItemOut {
  pc_full_id: string;
  rubric_version: string;
  marks: string; // Decimal, serialised as a string -- never parse as float and re-round
  critical: boolean;
  anchors: Record<string, string>;
  disclaimer: string;
  evidence_hint: string;
}

// ---- scoring ----

export type EvidenceStatus = "DEMONSTRATED" | "NOT_OBSERVABLE" | "NOT_APPLICABLE_IN_MVP";

export interface CriterionScoreIn {
  pc_full_id: string;
  score_level: number;
  evidence_status: EvidenceStatus;
  assessor_comment: string | null;
  expected_version: number;
}

export interface CriterionScoreOut {
  pc_full_id: string;
  score_level: number;
  evidence_status: string;
  assessor_comment: string | null;
  marks_awarded: string;
  rubric_version: string;
  assessor_id: number | null;
  scored_at: string | null;
  version: number;
  revision_number: number;
  // P7: true while this PC's task has been reopened for targeted
  // reassessment and has NOT been re-scored since -- see
  // models.AssessmentCriterionScore.needs_review. Final sign-off is
  // blocked while any score still has this set.
  needs_review: boolean;
}

export interface CriterionReviewItemOut {
  pc_full_id: string;
  rubric_version: string;
  marks: string;
  critical: boolean;
  anchors: Record<string, string>;
  disclaimer: string;
  evidence_hint: string;
  score: CriterionScoreOut | null;
}

export interface NosProfileOut {
  nos_code: string;
  nos_title: string;
  marks_awarded: string;
  marks_possible: string;
  percent: number;
  meets_threshold: boolean;
  critical_violation: boolean;
  has_insufficient_evidence: boolean;
  competent: boolean;
}

export type ComputedOutcomeValue =
  | "RECOMMEND_CERTIFICATION"
  | "PARTIALLY_COMPETENT"
  | "NOT_YET_COMPETENT"
  | "INSUFFICIENT_EVIDENCE";

export interface CompetencyProfileOut {
  assessment_id: number;
  overall_marks_awarded: string;
  overall_marks_possible: string;
  overall_percent: number;
  minimum_aggregate_passing_percent: number;
  meets_minimum_threshold: boolean;
  pcs_scored: number;
  pcs_total: number;
  nos_breakdown: NosProfileOut[];
  disclaimer: string;
  // P7: the full §4.4 computed outcome -- decision support only, see
  // disclaimer above; the human assessor's sign-off call (optionally
  // overriding this, with a mandatory reason) is what actually gets signed.
  computed_outcome: ComputedOutcomeValue;
  achieved_nos_codes: string[];
  gap_nos_codes: string[];
  insufficient_evidence_nos_codes: string[];
  critical_violation_pc_ids: string[];
}

// ---- P7: task-specific reassessment requests + revision history ----

export interface ReassessmentRequestOut {
  id: number;
  assessment_id: number;
  revision_number: number;
  task_codes: string[];
  reason: string;
  capture_instructions: string;
  requested_by_id: number;
  requested_at: string;
  status: string; // "pending" | "fulfilled" | "cancelled"
  fulfilled_at: string | null;
}

export interface ReassessmentRequestIn {
  task_codes: string[];
  reason: string;
  capture_instructions: string;
}

export interface AssessmentRevisionOut {
  revision_number: number;
  revision_id: string | null;
  reopened_task_codes: string[] | null;
  status: string;
  created_at: string;
  submitted_at: string | null;
}

// ---- signed reports (P7: PDF-bytes-first Ed25519 signing) ----

export interface SignOffIn {
  password: string;
  final_recommendation: ComputedOutcomeValue;
  override_reason: string | null;
}

export interface SignedReportOut {
  assessment_id: number;
  report_uid: string;
  revision_number: number;
  pdf_sha256: string;
  signature: string;
  key_id: string;
  computed_recommendation: ComputedOutcomeValue;
  final_recommendation: ComputedOutcomeValue;
  override_reason: string | null;
  signed_at: string;
}

export interface ReportVerifyOut {
  assessment_id: number;
  valid: boolean;
  key_id: string;
  signed_at: string;
}

export interface PublicVerifyOut {
  report_id: string;
  status: "SIGNED";
  valid: boolean;
  qp: string;
  recommendation: ComputedOutcomeValue;
  revision_number: number;
  sha256: string;
  key_id: string;
  signed_at: string;
}

// ---- worker tokens ----

export interface WorkerTokenOut {
  assessment_id: number;
  worker_token: string | null;
  status: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
