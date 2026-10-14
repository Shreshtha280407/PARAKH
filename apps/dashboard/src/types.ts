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
  current_revision_id: string | null;
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
}

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
}

// ---- signed reports ----

export interface SignedReportOut {
  assessment_id: number;
  sha256: string;
  signature: string;
  key_id: string;
  signed_at: string;
}

export interface ReportVerifyOut {
  assessment_id: number;
  valid: boolean;
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
