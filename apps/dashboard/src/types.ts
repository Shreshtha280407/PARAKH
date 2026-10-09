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
  total_bytes_used: number;
  total_budget_bytes: number;
  created_at: string;
  tasks: AssessmentTaskOut[];
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

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
