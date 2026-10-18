import { useEffect, useRef } from 'react';
import { navigate } from '../useHashRoute';

export interface CompletedDecision { assessmentId: number; title: string; description: string }

export function DecisionComplete({decision, onDone}: {decision: CompletedDecision; onDone: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    const timer = window.setTimeout(() => { navigate('#/queue'); onDone(); }, 2400);
    return () => window.clearTimeout(timer);
  }, [onDone]);
  function finish() { navigate('#/queue'); onDone(); }
  return <dialog ref={dialog} className="modal-card reviewer-dialog decision-complete" aria-labelledby="decision-complete-title" onCancel={e => { e.preventDefault(); finish(); }}>
    <span className="decision-success-icon" aria-hidden="true">✓</span><p className="eyebrow">Assessment #{decision.assessmentId} · Saved successfully</p><h2 id="decision-complete-title">{decision.title}</h2><p>{decision.description}</p><p className="hint">Returning to the assessment queue…</p><button autoFocus onClick={finish}>Back to queue</button>
  </dialog>;
}
