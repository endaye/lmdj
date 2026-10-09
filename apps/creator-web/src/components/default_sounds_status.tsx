import {useState} from "react";
import type {DefaultSeed} from "../state/default_seed";

interface DefaultSoundsStatusProps {
  seed: DefaultSeed | null;
  error: string | null;
  onRetry(): void;
  onPrepare(): Promise<void>;
  onDetails(): void;
}

export function DefaultSoundsStatus({seed, error, onRetry, onPrepare, onDetails}: DefaultSoundsStatusProps) {
  const [preparing, setPreparing] = useState(false);
  const [prepareFailed, setPrepareFailed] = useState(false);
  const slots = seed?.slots ?? [];
  const ready = slots.filter(slot => slot.phase === "ready").length;
  const failed = slots.filter(slot => slot.phase === "failed").length;
  const pendingAudio = slots.filter(slot => slot.phase === "saved-unavailable").length;
  const loading = slots.filter(slot => ["pending", "loading", "processing"].includes(slot.phase)).length;
  const needsAttention = error !== null || failed > 0 || pendingAudio > 0;
  if (seed === null && error === null) return null;
  const summary = error !== null ? error : [
    "Default sounds",
    ready > 0 || (!needsAttention && loading === 0) ? `${ready} ready` : null,
    loading > 0 ? `${loading} loading` : null,
    failed > 0 ? `${failed} unavailable` : null,
    pendingAudio > 0 ? `${pendingAudio} saved · playback pending` : null,
  ].filter(Boolean).join(" · ");
  // Completed loading remains announced without keeping a routine banner in
  // the editing area. Per-Pad colours/readiness retain the local result.
  if (!needsAttention && loading === 0) return <output className="visually-hidden" role="status">{summary}</output>;
  return <section className="workspace-status" aria-label="Default sounds">
    <output role="status">{summary}</output>
    {failed > 0 && <button type="button" onClick={onRetry}>Retry default sounds</button>}
    {pendingAudio > 0 && <button type="button" disabled={preparing} onClick={() => {
      setPreparing(true); setPrepareFailed(false);
      void onPrepare().catch(() => setPrepareFailed(true)).finally(() => setPreparing(false));
    }}>{preparing ? "Preparing playback…" : "Prepare default sounds"}</button>}
    {prepareFailed && pendingAudio > 0 && <output role="status">
      Playback is still unavailable. Try again or open System details.
    </output>}
    {needsAttention && <button type="button" onClick={onDetails}>System details</button>}
  </section>;
}
