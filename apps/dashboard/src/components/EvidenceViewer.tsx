import { useEffect, useRef, useState } from 'react';
import { evidenceContentUrl, evidenceThumbnailUrl } from '../api';
import type { EvidenceReceiptOut } from '../types';
import { EvidenceAssistance } from './EvidenceAssistance';

export function EvidenceViewer({ assessmentId, evidence }: { assessmentId: number; evidence: EvidenceReceiptOut }) {
  const contentUrl = evidenceContentUrl(assessmentId, evidence.id);
  const [failure, setFailure] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const [checking, setChecking] = useState(false);
  const inlinePlayer = useRef<HTMLVideoElement>(null);
  const expandedPlayer = useRef<HTMLVideoElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const mounted = useRef(true);
  const requestId = useRef(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!expanded || !dialog.current) return;
    const previousOverflow = document.body.style.overflow;
    const restoreFocus = opener.current;
    document.body.style.overflow = 'hidden';
    inlinePlayer.current?.pause();
    dialog.current.showModal();
    return () => { document.body.style.overflow = previousOverflow; restoreFocus?.focus(); };
  }, [expanded]);

  async function diagnose() {
    const current = ++requestId.current;
    setChecking(true);
    let message = 'This recording could not be opened. Check your connection and retry.';
    try {
      const response = await fetch(contentUrl, {credentials: 'include', headers: {Range: 'bytes=0-0'}, cache: 'no-store'});
      await response.body?.cancel();
      if (response.status === 401 || response.status === 403) message = 'Reviewer access expired or is unavailable. Sign in again to open private evidence.';
      else if (response.status === 404) message = 'This recording is missing from server storage. Refresh the assessment or request the evidence again.';
      else if (response.ok) message = 'The recording is available, but this browser could not decode it. Retry or open the original file.';
      else message = `The media server could not serve this recording (${response.status}). Please retry.`;
    } catch { /* Keep the connection-specific recovery message. */ }
    if (mounted.current && current === requestId.current) { setFailure(message); setChecking(false); }
  }
  function retry() { ++requestId.current; setFailure(''); setChecking(false); setDuration(null); setAttempt(v => v + 1); }
  function media(large: boolean) {
    return evidence.kind === 'video' ? <video key={`${large}-${attempt}`} ref={large ? expandedPlayer : inlinePlayer} controls playsInline crossOrigin="use-credentials" preload="metadata" src={contentUrl} poster={evidence.thumbnail_status === 'completed' ? evidenceThumbnailUrl(assessmentId, evidence.id) : undefined} aria-label={`Evidence video v${evidence.revision_number}`} onError={() => { void diagnose(); }} onLoadedMetadata={e => { const seconds = e.currentTarget.duration; setDuration(Number.isFinite(seconds) ? seconds * 1000 : null); }} /> : <img key={`${large}-${attempt}`} crossOrigin="use-credentials" src={contentUrl} alt={`Photo evidence, revision ${evidence.revision_number}`} onError={() => { void diagnose(); }} onClick={large ? undefined : () => setExpanded(true)} />;
  }
  function fallback() {
    return <div className="media-fallback" role="status">{checking ? 'Checking media access…' : failure}<div className="panel-actions"><button disabled={checking} onClick={retry}>Retry media</button><a href={`#/assessments/${assessmentId}`} onClick={() => { setExpanded(false); window.location.reload(); }} style={{color: 'var(--paper)'}}>Refresh assessment</a></div>{failure.includes('decode') && <a style={{color: 'var(--paper)'}} href={contentUrl} target="_blank" rel="noreferrer">Open original file →</a>}</div>;
  }
  return <li className="evidence-gallery-item">
    <div className="evidence-media">{failure || checking ? fallback() : media(false)}</div>
    <div className="evidence-meta"><strong>{evidence.kind === 'video' ? 'Video' : 'Photo'} evidence</strong> · {(evidence.declared_size_bytes / 1048576).toFixed(1)} MB{evidence.duration_ms != null && ` · ${Math.floor(evidence.duration_ms / 60000)}:${String(Math.floor(evidence.duration_ms / 1000) % 60).padStart(2, '0')}`}<br />{evidence.width_px && evidence.height_px ? `${evidence.width_px} × ${evidence.height_px} px · ` : ''}<span className="badge-ok">SHA-256 verified</span><br /><code title={evidence.sha256}>{evidence.sha256.slice(0, 20)}…</code><p className="hint">v{evidence.revision_number} · {evidence.is_current_revision ? 'Current' : 'Historical'} · Captured {evidence.device_captured_at ? new Date(evidence.device_captured_at).toLocaleString() : 'time not recorded'} (device-reported)</p><button ref={opener} className="media-open" onClick={() => setExpanded(true)}>Open {evidence.kind === 'video' ? 'video' : 'photo'} ↗</button></div>
    <EvidenceAssistance snapshot={evidence.assistance ?? null} durationMs={duration} mediaAvailable={!failure && !checking} onSeek={ms => { const player = expanded ? expandedPlayer.current : inlinePlayer.current; if (player && duration !== null && ms >= 0 && ms < duration) player.currentTime = ms / 1000; }} />
    {expanded && <dialog ref={dialog} className="modal-card media-dialog" aria-label="Evidence viewer" onCancel={e => { e.preventDefault(); setExpanded(false); }} onClick={e => { if (e.target === e.currentTarget && e.clientX < e.currentTarget.getBoundingClientRect().left) setExpanded(false); }}><div className="media-dialog-head"><h2>{evidence.kind === 'video' ? 'Video' : 'Photo'} evidence · v{evidence.revision_number}</h2><button autoFocus className="secondary-button" onClick={() => setExpanded(false)}>Close</button></div><div className="evidence-media">{failure || checking ? fallback() : media(true)}</div></dialog>}
  </li>;
}
