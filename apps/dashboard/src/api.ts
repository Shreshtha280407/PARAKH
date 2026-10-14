import {
  ApiError,
  type AssessmentOut,
  type AuditLogEntryOut,
  type CompetencyProfileOut,
  type CriterionReviewItemOut,
  type CriterionScoreIn,
  type CriterionScoreOut,
  type MeOut,
  type QueueItemOut,
  type ReportVerifyOut,
  type RubricItemOut,
  type SignedReportOut,
  type SyncStatusOut,
  type TokenOut,
  type WorkerTokenOut,
} from "./types";

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Double-submit CSRF pattern (see server/app/auth.py): the server sets this
// as a readable (non-HttpOnly) cookie at login; every mutating request must
// echo it back as a header so the server can confirm the request wasn't
// forged by a cross-site page (which can send the cookie automatically, but
// can't read its value to put in a header).
function csrfToken(): string | null {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (MUTATING_METHODS.has(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, method, headers, credentials: "include" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // body wasn't JSON -- keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function login(email: string, password: string): Promise<TokenOut> {
  return request<TokenOut>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}

export function me(): Promise<MeOut> {
  return request<MeOut>("/auth/me");
}

export function getQueue(): Promise<QueueItemOut[]> {
  return request<QueueItemOut[]>("/queue");
}

export function getAssessment(id: number): Promise<AssessmentOut> {
  return request<AssessmentOut>(`/assessments/${id}`);
}

export function getAssessmentRubric(id: number): Promise<RubricItemOut[]> {
  return request<RubricItemOut[]>(`/assessments/${id}/rubric`);
}

export function startReview(id: number): Promise<AssessmentOut> {
  return request<AssessmentOut>(`/assessments/${id}/start-review`, { method: "POST" });
}

export function getReview(id: number): Promise<CriterionReviewItemOut[]> {
  return request<CriterionReviewItemOut[]>(`/assessments/${id}/review`);
}

export function putScore(id: number, body: CriterionScoreIn): Promise<CriterionScoreOut> {
  return request<CriterionScoreOut>(`/assessments/${id}/review`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function getCompetencyProfile(id: number): Promise<CompetencyProfileOut> {
  return request<CompetencyProfileOut>(`/assessments/${id}/competency-profile`);
}

export function decideAssessment(
  id: number,
  decision: "recommended" | "needs_reassessment",
  notes: string,
): Promise<AssessmentOut> {
  return request<AssessmentOut>(`/assessments/${id}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, notes: notes || null }),
  });
}

export function reassess(id: number): Promise<{ id: number; worker_token: string }> {
  return request(`/assessments/${id}/reassess`, { method: "POST" });
}

export function generateReport(id: number): Promise<SignedReportOut> {
  return request<SignedReportOut>(`/assessments/${id}/report`, { method: "POST" });
}

export function verifyReport(id: number): Promise<ReportVerifyOut> {
  return request<ReportVerifyOut>(`/reports/${id}/verify`);
}

export function rotateWorkerToken(id: number): Promise<WorkerTokenOut> {
  return request<WorkerTokenOut>(`/assessments/${id}/worker-token/rotate`, { method: "POST" });
}

export function revokeWorkerToken(id: number): Promise<WorkerTokenOut> {
  return request<WorkerTokenOut>(`/assessments/${id}/worker-token/revoke`, { method: "POST" });
}

export function healthCheck(): Promise<{ status: string; database: string; storage: string }> {
  return request("/health");
}

// ---- P6: sync status + audit log ----

export function getSyncStatus(id: number, revisionId?: string | null): Promise<SyncStatusOut> {
  const query = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  return request<SyncStatusOut>(`/assessments/${id}/sync-status${query}`);
}

export function getAuditLog(id: number): Promise<AuditLogEntryOut[]> {
  return request<AuditLogEntryOut[]>(`/assessments/${id}/audit-log`);
}

/** Protected evidence content/thumbnail URLs -- the browser's own cookie-based session
 * (credentials: "include" is the dashboard's default fetch behaviour, and <img>/<video> tags
 * send cookies for same-origin/CORS-with-credentials requests the same way) authorises these
 * directly; no separate token needs to be embedded in the URL. */
export function evidenceContentUrl(assessmentId: number, evidenceId: number): string {
  return `${BASE_URL}/assessments/${assessmentId}/evidence/${evidenceId}/content`;
}

export function evidenceThumbnailUrl(assessmentId: number, evidenceId: number): string {
  return `${BASE_URL}/assessments/${assessmentId}/evidence/${evidenceId}/thumbnail`;
}
