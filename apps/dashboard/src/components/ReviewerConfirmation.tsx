import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { ReviewerAction } from '../api';

export function ReviewerConfirmation({id, action, ready = true, children, onConfirmed, onCancel}: {
  id: number; action: ReviewerAction; ready?: boolean; children?: ReactNode;
  onConfirmed: (password: string) => Promise<void>; onCancel: () => void;
}) {
  const [password, setPassword] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const restore = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.showModal();
    return () => { document.body.style.overflow = overflow; restore?.focus(); };
  }, []);
  async function submit() {
    if (busy || !confirmed || !ready) return;
    setBusy(true); setError('');
    try { await onConfirmed(password); setPassword(''); }
    catch (e) { setPassword(''); setError(e instanceof Error ? e.message : 'This action could not be confirmed. Please try again.'); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="modal-card reviewer-dialog" aria-labelledby="reviewer-dialog-title" onCancel={e => { e.preventDefault(); if (!busy) onCancel(); }}>
    <form onSubmit={e => { e.preventDefault(); void submit(); }}>
      <h2 id="reviewer-dialog-title">{action === 'sign_off' ? 'Confirm and sign assessment' : action === 'reject' ? 'Confirm rejection' : 'Confirm reassessment suggestion'}</h2>
      <p>Assessment #{id}. Enter your password again to confirm this action.</p>
      {children}
      <label>Confirm your password<input autoFocus required type="password" maxLength={128} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label className="checkbox-label"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I explicitly confirm this action and take responsibility for the recorded review.</label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="panel-actions"><button disabled={busy || !confirmed || !ready || !password} type="submit">{busy ? 'Confirming…' : 'Confirm action'}</button><button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button></div>
    </form>
  </dialog>;
}
