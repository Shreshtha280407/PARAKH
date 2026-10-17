import {
  ApiError,
  type AssessmentOut,
  type AssessmentRevisionOut,
  type AuditLogEntryOut,
  type CompetencyProfileOut,
  type CriterionReviewItemOut,
  type CriterionScoreIn,
  type CriterionScoreOut,
  type MeOut,
  type PublicVerifyOut,
  type QueueItemOut,
  type ReassessmentRequestIn,
  type ReassessmentRequestOut,
  type ReportVerifyOut,
  type RubricItemOut,
  type SignOffIn,
  type SignedReportOut,
  type SyncStatusOut,
  type TokenOut,
  type WorkerTokenOut,
} from "./types";

// Build-time default (Vite inlines import.meta.env.* when the Docker image
// is built, see apps/dashboard/Dockerfile). This alone would tie one built
// image to one backend origin forever -- loadRuntimeConfig() below lets
// the SAME built image be redeployed against a different backend by only
// changing an environment variable and restarting the container, no
// rebuild required.
export let BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? "/api" : "http://localhost:8000");
export let PUBLIC_DASHBOARD = true;

/** P10: optional runtime override, read once at startup (see main.tsx) from
 * /config.json -- a plain static file nginx's docker-entrypoint regenerates
 * from $DASHBOARD_RUNTIME_API_BASE_URL at container start (see
 * apps/dashboard/docker/write-runtime-config.sh). Deliberately silent/best-
 * effort: a missing or empty config.json (local `npm run dev`, or a
 * deployment that intentionally only uses the build-time default) just
 * keeps the build-time BASE_URL -- this is progressive configuration, not
 * a required step. */
export async function loadRuntimeConfig(): Promise<void> {
  try {
    const res = await fetch("/config.json", { cache: "no-store" });
    if (!res.ok) return;
    const config = await res.json();
    PUBLIC_DASHBOARD = config.accessMode !== "private";
    if (typeof config.apiBaseUrl === "string" && config.apiBaseUrl.length > 0) {
      BASE_URL = config.apiBaseUrl;
    }
  } catch {
    // No runtime config available -- keep the build-time default.
  }
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Fired on any 401 from an authenticated call other than the login attempt
// itself (a wrong password on /auth/login is a normal, expected failure
// the login form already shows inline -- not a session expiry). App.tsx
// registers a handler that drops back to the login screen with a clear
// "your session expired" message instead of letting a mid-action 401 show
// up as a confusing generic "That action failed" on whatever panel the
// assessor happened to be using (queue, scoring, sign-off, ...).
let sessionExpiredHandler: (() => void) | null = null;

export function onSessionExpired(handler: (() => void) | null): void {
  sessionExpiredHandler = handler;
}

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
  if (PUBLIC_DASHBOARD && path.startsWith("/assessments/")) path = `/reviewer${path}`;
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (MUTATING_METHODS.has(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
    const reviewerCsrf = document.cookie.match(/(?:^|; )parakh_reviewer_csrf=([^;]*)/);
    if (reviewerCsrf) headers.set("X-Reviewer-CSRF", decodeURIComponent(reviewerCsrf[1]));
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
    if (res.status === 401 && path !== "/auth/login") {
      sessionExpiredHandler?.();
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

/** P7: password-confirmed sign-off -- the ONLY way to produce the one,
 * immutable, Ed25519-signed PDF for an assessment (see
 * routers/reports.py::sign_off). Idempotent: a retry after the first
 * success returns the exact same signed artifact. */
export function signOff(id: number, body: SignOffIn): Promise<SignedReportOut> {
  return request<SignedReportOut>(`/assessments/${id}/sign-off`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function verifyReport(id: number): Promise<ReportVerifyOut> {
  return request<ReportVerifyOut>(`/reports/${id}/verify`);
}

/** Public, unauthenticated -- the exact URL the signed PDF's own QR code
 * points at (see routers/verify.py). No credentials sent on purpose: this
 * must work for an arbitrary third party, not just a logged-in assessor. */
export function publicVerify(reportId: string): Promise<PublicVerifyOut> {
  return fetch(`${BASE_URL}/verify/${encodeURIComponent(reportId)}`).then(async (res) => {
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        // not JSON -- keep statusText
      }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<PublicVerifyOut>;
  });
}

export function reportDownloadUrl(id: number, format: "json" | "pdf" | "receipt"): string {
  return `${BASE_URL}${PUBLIC_DASHBOARD ? "/reviewer" : ""}/assessments/${id}/report?format=${format}`;
}

interface ReportReceipt {
  report_id: string;
  assessment_id: number;
  revision_number: number;
  pdf_sha256: string;
  signature: string;
  key_id: string;
  signed_at: string;
}

/** Lightweight "has this already been signed, and what's its id" check for a page
 * load/reload -- no password needed (same dual auth as any other protected
 * download), so this is safe to call passively, unlike signOff itself. */
export function getReportReceipt(id: number): Promise<ReportReceipt> {
  return request<ReportReceipt>(`/assessments/${id}/report?format=receipt`);
}

interface ReportSnapshotJson {
  report_uid: string;
  revision_number: number;
  computed_recommendation: string;
  final_recommendation: string;
  override_reason: string | null;
}

/** The informational (unsigned) JSON snapshot -- carries the recommendation
 * fields the receipt doesn't (format=receipt is crypto-only by design). Also
 * no password needed. */
export function getReportSnapshot(id: number): Promise<ReportSnapshotJson> {
  return request<ReportSnapshotJson>(`/assessments/${id}/report?format=json`);
}

// ---- P7: task-specific reassessment requests + revision history ----

export function createReassessmentRequest(id: number, body: ReassessmentRequestIn): Promise<ReassessmentRequestOut> {
  return request<ReassessmentRequestOut>(`/assessments/${id}/reassessment-requests`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listReassessmentRequests(id: number): Promise<ReassessmentRequestOut[]> {
  return request<ReassessmentRequestOut[]>(`/assessments/${id}/reassessment-requests`);
}

export function listRevisions(id: number): Promise<AssessmentRevisionOut[]> {
  return request<AssessmentRevisionOut[]>(`/assessments/${id}/revisions`);
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
  return `${BASE_URL}${PUBLIC_DASHBOARD ? "/reviewer" : ""}/assessments/${assessmentId}/evidence/${evidenceId}/content`;
}

export function evidenceThumbnailUrl(assessmentId: number, evidenceId: number): string {
  return `${BASE_URL}${PUBLIC_DASHBOARD ? "/reviewer" : ""}/assessments/${assessmentId}/evidence/${evidenceId}/thumbnail`;
}

export interface PublicAssessment {
  id: number; candidate_display_name: string; pack_code: string; submitted_at: string;
  status: string; tasks_completed: number; tasks_total: number; review_status: string;
  revision_number: number; report_available: boolean; report_id: string | null; outcome: string | null;
}
export type ReviewerAction = "review" | "reject" | "reassessment" | "sign_off";
export function publicAssessments(beforeId?: number): Promise<PublicAssessment[]> {
  return request(`/public/assessments${beforeId ? `?before_id=${beforeId}` : ""}`);
}
export function publicAssessment(id: number): Promise<PublicAssessment> { return request(`/public/assessments/${id}`); }
export function reviewerAvailability(): Promise<{available: boolean; message: string}> { return request("/reviewer/availability"); }
export function requestReviewerCode(assessmentId: number, name: string, email: string, action: ReviewerAction): Promise<{challenge_id: string}> {
  return request("/reviewer/challenges", {method: "POST", body: JSON.stringify({assessment_id: assessmentId, name, email, action})});
}
export function verifyReviewerCode(challengeId: string, code: string): Promise<{name: string; email: string}> {
  return request("/reviewer/verify", {method: "POST", body: JSON.stringify({challenge_id: challengeId, code})});
}
export function rejectAssessment(id: number, reason: string): Promise<AssessmentOut> {
  return request(`/reviewer/assessments/${id}/reject`, {method: "POST", body: JSON.stringify({reason, confirmed: true})});
}
export function reviewerSignOff(id: number, finalRecommendation: string, overrideReason: string): Promise<SignedReportOut> {
  return request(`/reviewer/assessments/${id}/sign-off`, {method: "POST", body: JSON.stringify({final_recommendation: finalRecommendation, override_reason: overrideReason || null, confirmed: true})});
}
export function reviewerReassessment(id: number, body: ReassessmentRequestIn): Promise<ReassessmentRequestOut> {
  return request(`/reviewer/assessments/${id}/reassessment-requests`, {method: "POST", body: JSON.stringify({...body, confirmed: true})});
}
