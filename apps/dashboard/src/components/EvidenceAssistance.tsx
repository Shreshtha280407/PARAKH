import { useState } from "react";
import type { AssistanceFlag, AssistanceFlagType, AssistanceSnapshot } from "../types";

const FLAG_LABELS: Record<AssistanceFlagType, string> = {
  DARK: "Dark capture", OVEREXPOSED: "Overexposed capture", BLURRY: "Unclear detail / blur",
  CAMERA_MOTION: "Camera movement", HANDS_NOT_DETECTED: "Hands not detected",
};
const EXPLANATIONS: Record<AssistanceFlagType, string> = {
  DARK: "Sampled footage may be too dark to see detail.",
  OVEREXPOSED: "Bright sampled areas may have lost detail.",
  BLURRY: "Detail may be unclear. Low texture can also trigger this observation.",
  CAMERA_MOTION: "Coherent image movement was detected. Intentional panning can trigger this observation.",
  HANDS_NOT_DETECTED: "Hands were not detected in sampled frames. The model can miss visible hands; this does not establish physical absence or task performance.",
};

function sourceTime(ms: number): string {
  const value = Math.max(0, Math.round(ms));
  return `${Math.floor(value / 60000)}:${Math.floor(value / 1000 % 60).toString().padStart(2, "0")}.${(value % 1000).toString().padStart(3, "0")}`;
}

/** Intersect a signed source interval with actual playable footage. Container
 * and browser time bases can differ even for unchanged CameraX bytes. Preserve
 * the signed interval and seek offset; never invent footage beyond playback. */
function markerPosition(flag: AssistanceFlag, durationMs: number | null): { left: number; width: number } | null {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs <= 0 || flag.endMs === null ||
    !Number.isFinite(flag.startMs) || !Number.isFinite(flag.endMs) || flag.startMs < 0 || flag.endMs <= flag.startMs || flag.startMs >= durationMs) return null;
  return { left: flag.startMs / durationMs * 100, width: (Math.min(flag.endMs, durationMs) - flag.startMs) / durationMs * 100 };
}

export function EvidenceAssistance({ snapshot, durationMs, mediaAvailable, onSeek }: {
  snapshot: AssistanceSnapshot | null; durationMs: number | null; mediaAvailable: boolean; onSeek: (ms: number) => void;
}) {
  const [selected, setSelected] = useState<AssistanceFlag | null>(null);
  if (!snapshot) return <p className="hint assistance-summary">Quality review: not run (no signed assistance recorded).</p>;
  const groups = Object.keys(FLAG_LABELS) as AssistanceFlagType[];
  const temporal = snapshot.flags.filter(f => f.endMs !== null);
  const durationMismatch = durationMs !== null && temporal.some(f => f.endMs! > durationMs);
  return <section className="assistance-summary" aria-label="Advisory evidence quality review">
    <strong>Quality review: {snapshot.status.toLowerCase().replaceAll("_", " ")} at sealing · v{snapshot.revisionNumber}</strong>
    <p className="hint">Signed device advice. The assessor decides all scores and outcomes. These observations do not verify task execution, PPE, tools, identity or competence.</p>
    {["QUEUED", "RUNNING", "NOT_RUN"].includes(snapshot.status) && <p>Analysis was unfinished at sealing. This submission will retain that snapshot.</p>}
    {["FAILED", "UNAVAILABLE"].includes(snapshot.status) && <p>Analysis could not provide a complete result. This does not indicate poor evidence quality.</p>}
    {snapshot.status === "PARTIAL" && <p>Only part of the requested analysis is available. Unanalysed footage has no inferred result.</p>}
    {snapshot.intervalsTruncated && <p>Some intervals were omitted to keep the signed metadata bounded.</p>}
    {durationMismatch && <p className="hint" role="status">Some signed intervals exceed the playable media duration. Overlapping intervals are displayed only within playable footage; markers starting beyond it are unavailable. The original signed times remain below.</p>}
    {temporal.length > 0 && durationMs === null && <p className="hint">Timeline positions will appear when the player reports its duration.</p>}
    {snapshot.flags.length === 0 && ["COMPLETED", "PARTIAL"].includes(snapshot.status) && <p>No advisory issues detected in the analysed samples.</p>}
    {groups.map(type => {
      const flags = snapshot.flags.filter(f => f.type === type);
      if (flags.length === 0) return null;
      return <div className="assistance-condition" key={type}>
        <strong>{FLAG_LABELS[type]}</strong>
        <p className="hint">{EXPLANATIONS[type]}</p>
        {durationMs !== null && temporal.length > 0 && <div className="assistance-track" aria-hidden="true">
          {flags.map((flag, i) => {
            const position = markerPosition(flag, durationMs);
            return position && <span className={`assistance-range assistance-${type.toLowerCase()}`} key={i}
              style={{ left: `${position.left}%`, width: `${position.width}%` }} />;
          })}
        </div>}
        <div className="assistance-markers">
          {flags.filter(f => f.endMs !== null).map((flag, i) => <button type="button" key={i}
            className={`assistance-marker assistance-${type.toLowerCase()}`}
            disabled={!mediaAvailable || markerPosition(flag, durationMs) === null}
            aria-label={`Seek to ${FLAG_LABELS[type]} at ${sourceTime(flag.startMs)}`}
            onClick={() => { onSeek(flag.startMs); setSelected(flag); }}>
            {sourceTime(flag.startMs)}–{sourceTime(flag.endMs!)}
          </button>)}
        </div>
      </div>;
    })}
    <p className="hint" aria-live="polite">{selected ? `At ${sourceTime(selected.startMs)}: ${EXPLANATIONS[selected.type]}` : "Video intervals describe 1 fps samples, not continuously observed event boundaries."}</p>
    <details><summary>Coverage and analysis versions</summary>
      {(["quality", "hands"] as const).map(name => {
        const value = snapshot[name];
        if (!value) return <p key={name}>{name}: no result recorded</p>;
        const c = value.coverage;
        return <div key={name} className="hint"><strong>{name}: {value.status.toLowerCase()}</strong>
          <p>{c.analysedSamples}/{c.requestedSamples} requested samples analysed{snapshot.durationMs !== null && ` · ${(c.coveredDurationMs / 1000).toFixed(3)} s covered`}.
            {name === "quality" && c.motionRequestedPairs > 0 && ` Motion: ${c.motionAnalysedPairs}/${c.motionRequestedPairs} pairs usable.`}</p>
          {value.provenance && <p>{value.provenance.moduleVersion} · {value.provenance.profileVersion}<br />
            Profile SHA-256: <code>{value.provenance.profileSha256}</code>
            {value.provenance.modelSha256 && <><br />Model SHA-256: <code>{value.provenance.modelSha256}</code></>}</p>}
          {name === "hands" && value.visibleRatioGapFilled !== null && <p>Hands detected in {(value.visibleRatioGapFilled * 100).toFixed(1)}% of analysed samples after the versioned gap-fill policy. Missed visible hands remain possible.</p>}
        </div>;
      })}
    </details>
  </section>;
}
