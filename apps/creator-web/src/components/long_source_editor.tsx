import {useEffect, useMemo, useState} from "react";

import type {DecodedLongSource} from "../ingest/long_source_ingest";
import type {SampleQuota} from "../runtime/runtime_types";
import {padAddress} from "../state/view_model";
import {ModalDialog} from "./modal_dialog";

export type LongSourceCommitOutcome =
  | {readonly kind: "committed"}
  | {readonly kind: "conflict"; readonly message: string}
  | {readonly kind: "failed"; readonly message: string};

interface LongSourceEditorProps {
  readonly source: DecodedLongSource;
  readonly quota: Readonly<SampleQuota>;
  readonly returnFocus?: HTMLElement | null;
  onCommit(selection: {startFrame: number; frameCount: number}): Promise<LongSourceCommitOutcome>;
  onCancel(): void;
}

const WAVEFORM_BINS = 192;

function seconds(frames: number): string {
  return `${(frames / 48_000).toFixed(2)} s`;
}

function sourceLabel(name: string): string {
  const characters = Array.from(name);
  return characters.length <= 96 ? name : `${characters.slice(0, 95).join("")}…`;
}

export function LongSourceEditor({
  source,
  quota,
  returnFocus = null,
  onCommit,
  onCancel,
}: LongSourceEditorProps) {
  const maximumFrames = Math.min(source.frameCount, quota.effectiveRemainingFrames);
  const [selectionStart, setSelectionStart] = useState(0);
  const [selectionFrames, setSelectionFrames] = useState(maximumFrames);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const waveform = useMemo(
    () => source.envelope(WAVEFORM_BINS, 0, source.frameCount),
    [source],
  );

  useEffect(() => () => source.stopPreview(), [source]);

  const selectStart = (next: number) => {
    const start = Math.max(0, Math.min(Math.round(next), source.frameCount - 1));
    const available = Math.min(maximumFrames, source.frameCount - start);
    setSelectionStart(start);
    setSelectionFrames((current) => Math.min(current, available));
    setError(null);
  };
  const selectFrames = (next: number) => {
    const available = Math.min(maximumFrames, source.frameCount - selectionStart);
    setSelectionFrames(Math.max(1, Math.min(Math.round(next), available)));
    setError(null);
  };

  const togglePreview = async () => {
    if (previewing) {
      source.stopPreview();
      setPreviewing(false);
      return;
    }
    try {
      await source.preview({startFrame: selectionStart, frameCount: selectionFrames});
      setPreviewing(true);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Preview failed");
    }
  };

  const commit = async () => {
    if (committing || selectionFrames < 1) return;
    source.stopPreview();
    setPreviewing(false);
    setCommitting(true);
    setError(null);
    const result = await onCommit({startFrame: selectionStart, frameCount: selectionFrames});
    if (result.kind !== "committed") {
      setError(result.message);
      setCommitting(false);
    }
  };

  const bank = Math.floor(quota.slot / 16);
  const padUsage = quota.consumed.map((entry) =>
    `${padAddress({slot: entry.slot, assetId: null})}: ${seconds(entry.preparedFrames)}`);

  return (
    <ModalDialog
      label={`Pad ${padAddress({slot: quota.slot, assetId: null})} Long Source`}
      returnFocus={returnFocus}
      onCancel={onCancel}
      dialogClassName="long-source-dialog"
    >
      <div className="capture-panel-header">
        <div>
          <p className="eyebrow">Long-source ingest</p>
          <h2>{sourceLabel(source.sourceName)}</h2>
        </div>
        <button type="button" disabled={committing} onClick={onCancel}>Cancel</button>
      </div>
      <div className="long-source-content">
        <p>
          {source.container.toUpperCase()} · {source.channelCount === 1 ? "Mono" : "Stereo"}
          {" · "}{seconds(source.frameCount)} · 48 kHz
        </p>
        <svg
          className="long-source-waveform"
          viewBox={`0 0 ${WAVEFORM_BINS} 100`}
          role="img"
          aria-label={`${sourceLabel(source.sourceName)} decoded waveform`}
        >
          {Array.from(waveform, (magnitude, index) => {
            const height = Math.max(1, Math.min(100, magnitude * 100));
            return <rect key={index} x={index} y={(100 - height) / 2} width={1} height={height} />;
          })}
        </svg>
        <p className="quota-summary">
          Bank {String.fromCharCode(65 + bank)}: {seconds(quota.bankRemainingBytes / 4)} remaining;
          Project: {seconds(quota.projectRemainingBytes / 4)} remaining.
        </p>
        <p className="quota-usage">
          Pad usage: {padUsage.length === 0 ? "none" : padUsage.join(" · ")}
        </p>
        {maximumFrames < 1 ? (
          <p role="alert">
            why: no prepared-PCM quota remains; remedy: free a Pad or choose another Bank.
          </p>
        ) : (
          <>
            <label>
              <span>Selection start ({seconds(selectionStart)})</span>
              <input
                type="range"
                min={0}
                max={Math.max(0, source.frameCount - selectionFrames)}
                step={1}
                value={selectionStart}
                aria-label="Long source selection start"
                disabled={committing}
                onChange={(event) => selectStart(event.currentTarget.valueAsNumber)}
              />
            </label>
            <label>
              <span>Selection length ({seconds(selectionFrames)})</span>
              <input
                type="range"
                min={1}
                max={Math.max(1, Math.min(maximumFrames, source.frameCount - selectionStart))}
                step={1}
                value={selectionFrames}
                aria-label="Long source selection length"
                disabled={committing}
                onChange={(event) => selectFrames(event.currentTarget.valueAsNumber)}
              />
            </label>
          </>
        )}
        {error === null ? null : <p role="alert">{error}</p>}
      </div>
      <div className="capture-panel-actions">
        <button
          type="button"
          disabled={committing || selectionFrames < 1}
          onClick={() => { void togglePreview(); }}
        >
          {previewing ? "Stop preview" : "Preview selection"}
        </button>
        <button
          type="button"
          disabled={committing || maximumFrames < 1 || selectionFrames < 1}
          onClick={() => { void commit(); }}
        >
          {committing ? "Committing…" : "Commit selection"}
        </button>
      </div>
    </ModalDialog>
  );
}
