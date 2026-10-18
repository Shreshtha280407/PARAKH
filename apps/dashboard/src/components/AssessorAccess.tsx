import { useEffect, useRef, useState } from 'react';
import { loginAssessor, registerAssessor } from '../api';
import { useAssessorSession } from './AssessorSession';

export function AssessorAccess({onClose}: {onClose: () => void}) {
  const {setAccount} = useAssessorSession();
  const [register, setRegister] = useState(true);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
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
    if (busy || (register && !acknowledged)) return;
    setBusy(true); setError('');
    try {
      const account = register
        ? await registerAssessor({name:name.trim(), email:email.trim(), phone:phone.trim(), password, password_acknowledged:true})
        : await loginAssessor(email.trim(), password);
      setPassword(''); setAccount(account); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not enter the dashboard. Please try again.'); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="modal-card reviewer-dialog" aria-labelledby="assessor-access-title" onCancel={e => { e.preventDefault(); if (!busy) onClose(); }}>
    <form onSubmit={e => { e.preventDefault(); void submit(); }}>
      <h2 id="assessor-access-title">{register ? 'Assessor details' : 'Assessor sign in'}</h2>
      <p>{register ? 'Enter your details and create a password to review assessments.' : 'Enter the email and password you used when creating your assessor account.'}</p>
      <div className="notice password-reminder"><strong>Remember your password.</strong><p>There is no forgot-password or password reset option. You will need this password to sign in again and to confirm signing, rejection or reassessment suggestions.</p></div>
      {register && <label>Full name<input autoFocus required minLength={2} maxLength={120} autoComplete="name" value={name} onChange={e => setName(e.target.value)} /></label>}
      <label>Email<input autoFocus={!register} required type="email" maxLength={254} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
      {register && <label>Phone number<input required type="tel" inputMode="tel" pattern="\+?[1-9][0-9]{9,14}" maxLength={16} autoComplete="tel" placeholder="9876543210 or +919876543210" value={phone} onChange={e => setPhone(e.target.value)} /></label>}
      <label>Password<input required type="password" minLength={8} maxLength={128} autoComplete={register ? 'new-password' : 'current-password'} aria-describedby="assessor-password-hint" value={password} onChange={e => setPassword(e.target.value)} /></label>
      <p id="assessor-password-hint" className="hint">Use at least 8 characters. Your password is required again for final assessment actions.</p>
      {register && <label className="checkbox-label"><input required type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />I understand that I must remember my password and cannot reset it.</label>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="panel-actions"><button type="submit" disabled={busy || (register && !acknowledged)}>{busy ? 'Please wait…' : register ? 'Create account and enter' : 'Sign in and enter'}</button><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancel</button></div>
      <button type="button" className="link-button" disabled={busy} onClick={() => { setRegister(value => !value); setPassword(''); setError(''); }}>{register ? 'Already registered? Sign in' : 'New assessor? Create an account'}</button>
    </form>
  </dialog>;
}
