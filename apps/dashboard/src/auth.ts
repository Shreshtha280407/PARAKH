// Token storage for this demo: sessionStorage, not localStorage -- it
// clears automatically when the tab/browser closes and isn't shared across
// tabs. This is NOT httpOnly-cookie-grade security (still readable by any
// script on the page, i.e. vulnerable to XSS exfiltration); fine for a
// basic internal demo dashboard, not for a pilot-grade deployment.
const STORAGE_KEY = "parakh_access_token";

export function getToken(): string | null {
  return sessionStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(STORAGE_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}
