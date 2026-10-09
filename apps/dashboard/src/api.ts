import { ApiError, type AssessmentOut, type MeOut, type QueueItemOut, type RubricItemOut, type TokenOut } from "./types";
import { getToken } from "./auth";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
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

export function healthCheck(): Promise<{ status: string; database: string; storage: string }> {
  return request("/health");
}
