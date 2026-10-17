import { useState, type ReactNode } from "react";
import { requestReviewerCode, verifyReviewerCode, type ReviewerAction } from "../api";

export function ReviewerConfirmation({ id, action, ready = true, children, onConfirmed, onCancel }: {
  id: number; action: ReviewerAction; ready?: boolean; children?: ReactNode;
  onConfirmed: () => Promise<void>; onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true); setError("");
    try {
      if (!challenge) {
        const result = await requestReviewerCode(id, name, email, action);
        setChallenge(result.challenge_id);
      } else {
        await verifyReviewerCode(challenge, code);
        await onConfirmed();
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Verification failed."); }
    finally { setBusy(false); }
  }
  return <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="reviewer-dialog-title">
    <form className="modal-card" onSubmit={e => { e.preventDefault(); void submit(); }}>
      <h2 id="reviewer-dialog-title">Confirm {action.replaceAll("_", " ")}</h2>
      <p>Assessment #{id}. Your name is self-declared. The email code verifies email ownership; operator permission is also required.</p>
      <label>Assessor full name<input required minLength={2} maxLength={120} value={name} disabled={!!challenge} onChange={e => setName(e.target.value)} /></label>
      <label>Assessor email<input required type="email" value={email} disabled={!!challenge} onChange={e => setEmail(e.target.value)} /></label>
      {children}
      <p>{challenge ? "A short-lived code was sent. Identity remains unverified until the code is accepted." : "Identity: unverified"}</p>
      {challenge && <label>Email code<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} /></label>}
      <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I explicitly confirm this action and take responsibility for the recorded review.</label>
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy || !confirmed || !ready || (!!challenge && code.length !== 6)} type="submit">{busy ? "Please wait…" : challenge ? "Verify and confirm action" : "Send verification code"}</button>
      <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
    </form>
  </div>;
}
