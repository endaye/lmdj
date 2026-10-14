import "./long_source_editor.css";

import {NO_ROOM_MESSAGE} from "../state/error_messages";
import {useEffect, useMemo, useState, type CSSProperties} from "react";

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
  onDelete?(): void;
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
  onDelete,
}: LongSourceEditorProps) {
  const maximumFrames = Math.min(source.frameCount, quota.effectiveRemainingFrames);
  const [selectionStart, setSelectionStart] = useState(0);
  const [selectionFrames, setSelectionFrames] = useState(maximumFrames);
  const [committing, setCommitting] = useState(false);
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

  const preview = async () => {
    try {
      await source.preview({startFrame: selectionStart, frameCount: selectionFrames});
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Preview failed");
    }
  };

  const commit = async () => {
    if (committing || selectionFrames < 1) return;
    source.stopPreview();
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

  const target = padAddress({slot: quota.slot, assetId: null});
  const selectionEnd = selectionStart + selectionFrames;

  return (
    <ModalDialog
      label={`Pad ${target} Long Source`}
      returnFocus={returnFocus}
      onCancel={onCancel}
      dialogClassName="long-source-dialog long-source-import-dialog"
      placement="touch-workspace"
    >
      <header className="long-source-heading">
        <h2>IMPORT AUDIO</h2>
        <span>TARGET {target}</span>
      </header>
      <div className="long-source-content">
        <svg
          className="long-source-waveform"
          viewBox={`0 0 ${WAVEFORM_BINS} 100`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${sourceLabel(source.sourceName)} decoded waveform`}
        >
          {Array.from(waveform, (magnitude, index) => {
            const height = Math.max(1, Math.min(100, magnitude * 100));
            // A bin is selected when any of its frames is: both edges of the
            // selection then round the same way, outward to the whole bin.
            const binStart = index * source.frameCount / WAVEFORM_BINS;
            const binEnd = (index + 1) * source.frameCount / WAVEFORM_BINS;
            return <rect key={index} x={index} y={(100 - height) / 2} width={1} height={height}
              data-selected={binStart < selectionEnd && binEnd > selectionStart} />;
          })}
          <line x1={selectionStart / source.frameCount * WAVEFORM_BINS} y1={0}
            x2={selectionStart / source.frameCount * WAVEFORM_BINS} y2={100} />
          <line x1={selectionEnd / source.frameCount * WAVEFORM_BINS} y1={0}
            x2={selectionEnd / source.frameCount * WAVEFORM_BINS} y2={100} />
        </svg>
        {maximumFrames < 1 ? (
          <p role="alert">{NO_ROOM_MESSAGE}</p>
        ) : (
          <>
            <label className="long-source-selection">
              <span><span>Selection start</span><span>{(selectionStart / 48_000).toFixed(3)} s</span></span>
              <input
                type="range"
                min={0}
                max={Math.max(0, source.frameCount - selectionFrames)}
                step={1}
                value={selectionStart}
                aria-label="Long source selection start"
                style={{"--selection-fill": `${selectionStart / Math.max(1, source.frameCount - selectionFrames) * 100}%`} as CSSProperties}
                disabled={committing}
                onChange={(event) => selectStart(event.currentTarget.valueAsNumber)}
              />
            </label>
            <label className="long-source-selection">
              <span><span>Selection length</span><span>{(selectionFrames / 48_000).toFixed(3)} s</span></span>
              <input
                type="range"
                min={1}
                max={Math.max(1, Math.min(maximumFrames, source.frameCount - selectionStart))}
                step={1}
                value={selectionFrames}
                aria-label="Long source selection length"
                style={{"--selection-fill": `${(selectionFrames - 1) / Math.max(1, Math.min(maximumFrames, source.frameCount - selectionStart) - 1) * 100}%`,
                  "--selection-colour": "var(--creator-sky)"} as CSSProperties}
                disabled={committing}
                onChange={(event) => selectFrames(event.currentTarget.valueAsNumber)}
              />
            </label>
          </>
        )}
        <div className="long-source-details">
          <p className="long-source-name">{sourceLabel(source.sourceName)}</p>
          <p>{source.container.toUpperCase()} · {source.channelCount === 1 ? "Mono" : "Stereo"}
            {" · "}{seconds(source.frameCount)} · 48 kHz</p>
          <p className="quota-summary">
            Bank {String.fromCharCode(65 + bank)}: {seconds(quota.bankRemainingBytes / 4)} remaining;
            Project: {seconds(quota.projectRemainingBytes / 4)} remaining.
          </p>
          <p className="quota-usage">Pad usage: {padUsage.length === 0 ? "none" : padUsage.join(" · ")}</p>
        </div>
        {error === null ? null : <p role="alert">{error}</p>}
      </div>
      <div className="long-source-actions">
        <button className="touch-control" type="button"
          disabled={committing || selectionFrames < 1}
          onClick={() => { void preview(); }}>
          Preview selection
        </button>
        <button className="touch-control" type="button" disabled={committing}
          onClick={() => source.stopPreview()}>
          Stop preview
        </button>
        <button className="touch-control is-primary" type="button"
          disabled={committing || maximumFrames < 1 || selectionFrames < 1}
          onClick={() => { void commit(); }}>
          {committing ? "Committing…" : "Commit selection"}
        </button>
        <button className="touch-control" type="button" disabled={committing} onClick={onCancel}>Cancel</button>
        {onDelete === undefined ? null : (
          <button className="touch-control is-danger long-source-delete" type="button"
            aria-label={`Delete Pad ${target}`} onClick={onDelete}>Delete Pad</button>
        )}
      </div>
    </ModalDialog>
  );
}
