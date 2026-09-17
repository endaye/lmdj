import {useEffect, useState, useSyncExternalStore} from "react";

import type {ProjectView} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import {
  type PatternTransportState,
} from "../state/pattern_transport_state";
import {transportStatusLabel} from "./transport_status";
import {
  PERFORMANCE_FX_ORDER,
  type PerformController,
  type PerformState,
} from "../state/perform_state";
import {FxSliderBank} from "./fx_slider_bank";
import {PatternLaunchStrip} from "./pattern_launch_strip";

export interface PerformSurfaceProps {
  readonly controller: PerformController;
  readonly project: ProjectView;
  readonly bank: Bank;
  readonly onBankChange: (bank: Bank) => void;
  // The Perform surface renders the same global Pattern transport projection
  // every other mode consumes; it never drives it.
  readonly transport?: PatternTransportState;
}

function RecordingPanel(props: {
  readonly state: PerformState;
  readonly canRecord: boolean;
  readonly onRecord: () => void;
  readonly onFlush: () => void;
  readonly onStop: () => void;
  readonly onSave: (name: string) => void;
  readonly onDiscard: () => void;
  readonly onRetryBind: () => void;
  readonly onExportWav: () => void;
}) {
  const phase = props.state.recording.phase;
  const [name, setName] = useState("Performance");
  return (
    <section className="perform-recording" aria-label="Performance recording">
      <button type="button" disabled={!props.canRecord}
        onClick={props.onRecord}>Record Performance</button>
      <button type="button" disabled={phase !== "recording"}
        onClick={props.onFlush}>Flush Performance</button>
      <button type="button" disabled={phase !== "recording" && phase !== "flushing"}
        onClick={props.onStop}>Stop Performance</button>
      <label>Performance name
        <input type="text" aria-label="Performance name" value={name}
          onChange={(event) => setName(event.currentTarget.value)} />
      </label>
      <button type="button" disabled={phase !== "stopped" || name.trim() === ""}
        onClick={() => props.onSave(name.trim())}>Save Performance</button>
      <button type="button" disabled={phase !== "stopped"}
        onClick={props.onDiscard}>Discard Performance</button>
      <button type="button" disabled={props.state.recording.wav === null}
        onClick={props.onExportWav}>Export Performance WAV</button>
      {props.state.bindingStatus === "retry" ? (
        <button type="button" onClick={props.onRetryBind}>Retry WAV bind</button>
      ) : null}
      <output role="status" aria-label="Performance recording status">
        {phase}
        {props.state.recordingNote === null ? "" : ` · ${props.state.recordingNote}`}
        {props.state.authority === null ? "" : ` · open Pads: ${
          props.state.authority.openPadGestures} · open FX: ${
          props.state.authority.openFxGestures} · HOLD: ${
          props.state.authority.hold ? "on" : "off"}${
          props.state.authority.lastLaunchAck === null ? "" :
            ` · last launch: ${props.state.authority.lastLaunchAck.patternSlot + 1} acknowledged`
        }`}
      </output>
      <output role="status" aria-label="WAV recording status">
        {props.state.wavStatus}
      </output>
      <output role="status" aria-label="WAV binding status">
        {props.state.bindingStatus}
      </output>
    </section>
  );
}

function ReplayPanel(props: {
  readonly state: PerformState;
  readonly onReplay: (performanceId: string) => void;
  readonly onStop: () => void;
  readonly onResample: (performanceId: string, start: number,
    end: number, targetSlot: number) => void;
  readonly onRecover: (sessionId: string) => void;
  readonly onDiscardRecovery: (sessionId: string) => void;
}) {
  const [selectedPerformance, setSelectedPerformance] = useState<string | null>(null);
  const [startFrame, setStartFrame] = useState(0);
  const [endFrame, setEndFrame] = useState(4_800);
  const [targetSlot, setTargetSlot] = useState(0);
  const selected = selectedPerformance ?? props.state.performances[0]?.performanceId ?? null;
  return (
    <section className="perform-replay" aria-label="Performance replay">
      {props.state.performances.map((performance) => (
        <article key={performance.performanceId}>
          <span>{performance.name}</span>
          <button type="button"
            aria-label={`Replay ${performance.name}`}
            onClick={() => {
              setSelectedPerformance(performance.performanceId);
              props.onReplay(performance.performanceId);
            }}>Replay</button>
        </article>
      ))}
      <button type="button" disabled={props.state.replay === null}
        onClick={props.onStop}>Stop Replay</button>
      <output role="status" aria-label="Replay status">
        {props.state.replay === null ? "idle" : `${props.state.replay.state}${
          props.state.replayNeutral ? " · neutral" : ""} · resolved revision · ${
          props.state.replay.resolvedRevision}`}
      </output>
      <label>Resample start frame
        <input type="number" min={0} aria-label="Resample start frame"
          value={startFrame}
          onChange={(event) => setStartFrame(event.currentTarget.valueAsNumber)} />
      </label>
      <label>Resample end frame
        <input type="number" min={1} aria-label="Resample end frame"
          value={endFrame}
          onChange={(event) => setEndFrame(event.currentTarget.valueAsNumber)} />
      </label>
      <label>Resample target Pad
        <input type="number" min={0} max={63} aria-label="Resample target Pad"
          value={targetSlot}
          onChange={(event) => setTargetSlot(event.currentTarget.valueAsNumber)} />
      </label>
      <button type="button" disabled={selected === null ||
        !Number.isSafeInteger(startFrame) || !Number.isSafeInteger(endFrame) ||
        endFrame <= startFrame || !Number.isSafeInteger(targetSlot) ||
        targetSlot < 0 || targetSlot > 63}
        onClick={() => {
          if (selected !== null) props.onResample(
            selected, startFrame, endFrame, targetSlot,
          );
        }}>Resample selection</button>
      <output role="status" aria-label="Resample status">
        {props.state.resampleStatus}
      </output>
      {props.state.recovery.map((candidate) => (
        <article key={candidate.sessionId}>
          <span>{candidate.reason}</span>
          <button type="button"
            onClick={() => props.onRecover(candidate.sessionId)}>Apply recovery</button>
          <button type="button"
            onClick={() => props.onDiscardRecovery(candidate.sessionId)}>
            Discard recovery
          </button>
        </article>
      ))}
      <output role="status" aria-label="Performance recovery status">
        {props.state.recoveryStatus}
      </output>
    </section>
  );
}

export function PerformSurface(props: PerformSurfaceProps) {
  const {controller} = props;
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getState,
    controller.getState,
  );
  useEffect(() => {
    const disconnect = controller.connect();
    const stopWhenHidden = () => {
      if (document.visibilityState === "hidden") {
        void controller.leave().catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", stopWhenHidden);
    return () => {
      document.removeEventListener("visibilitychange", stopWhenHidden);
      disconnect();
      void controller.leave().catch(() => {});
    };
  }, [controller]);
  useEffect(() => {
    if (state.replay?.state !== "playing") return;
    const timer = window.setInterval(() => { void controller.refreshReplay(); }, 250);
    return () => window.clearInterval(timer);
  }, [controller, state.replay?.state]);
  const captureMessage = state.captureStatus.state === "configured"
    ? "Preparing recording…"
    : state.captureStatus.state === "unavailable"
      ? state.captureStatus.error.message
      : null;
  const performing = ["recording", "flushing"].includes(state.recording.phase);
  // D04 heads the touch workspace with the switch cue. NEXT BAR is pictured
  // text; the Host only knows whether a launch is queued or acknowledged.
  const cue = state.pendingLaunch !== null
    ? `Slot ${state.pendingLaunch.patternSlot + 1} queued`
    : state.lastLaunchAck !== null
      ? `Slot ${state.lastLaunchAck.patternSlot + 1} live`
      : "No Pattern queued";
  return (
    <main className="perform-surface" aria-label="Perform">
      <header className="perform-live-header">
        <p className="perform-live-title">LIVE CONTROLS</p>
        <output className="perform-live-cue"
          aria-label="Pattern launch cue">{cue}</output>
      </header>
      <PatternLaunchStrip slots={props.project.patternSlots}
        patterns={props.project.patterns}
        pending={state.pendingLaunch} lastAck={state.lastLaunchAck} bank={props.bank}
        disabled={!performing}
        mutationDisabled={state.recording.phase !== "idle"}
        onBankChange={(bank) => {
          controller.setBank(bank);
          props.onBankChange(bank);
        }}
        onAssign={(patternSlot, patternId) => {
          void controller.assignPattern(patternSlot, patternId);
        }}
        onClear={(patternSlot) => { void controller.clearPattern(patternSlot); }}
        onMove={(fromSlot, toSlot) => {
          void controller.movePattern(fromSlot, toSlot);
        }}
        onLaunch={(patternSlot) => { void controller.launchPattern(patternSlot); }} />
      <dl className="project-summary perform-project-summary" aria-label="Perform Project status">
        <div>
          <dt>Revision</dt>
          <dd role="definition">{props.project.revision}</dd>
        </div>
      </dl>
      <FxSliderBank order={PERFORMANCE_FX_ORDER} values={state.fx}
        disabled={!performing}
        onEngage={(fx, value) => controller.engageFx(fx, value)}
        onMove={(gestureId, fx, value) => controller.moveFx(gestureId, fx, value)}
        onRelease={(gestureId, fx) => controller.releaseFx(gestureId, fx)} />
      <button className="perform-hold" type="button" aria-pressed={state.hold}
        disabled={!performing}
        onClick={() => controller.toggleHold()}>HOLD</button>
      <RecordingPanel state={state} canRecord={controller.canRecord()}
        onRecord={() => { void controller.record(); }}
        onFlush={() => { void controller.flush(); }}
        onStop={() => { void controller.stop(); }}
        onSave={(name) => { void controller.save(name); }}
        onDiscard={() => { void controller.discard(); }}
        onRetryBind={() => { void controller.retryWavBind(); }}
        onExportWav={() => { void controller.exportWav(); }} />
      <ReplayPanel state={state}
        onReplay={(performanceId) => { void controller.beginReplay(performanceId); }}
        onStop={() => { void controller.stopReplay().catch(() => {}); }}
        onResample={(performanceId, start, end, targetSlot) => {
          void controller.resample(performanceId, start, end, targetSlot);
        }}
        onRecover={(sessionId) => { void controller.applyRecovery(sessionId); }}
        onDiscardRecovery={(sessionId) => {
          void controller.discardRecovery(sessionId);
        }} />
      {captureMessage !== null ? <p role="status">{captureMessage}</p> : null}
      {props.transport !== undefined ? (
        <output role="status" aria-label="Pattern transport status">
          Pattern transport: {transportStatusLabel(props.transport)}
          {props.transport.status?.publicationPending === true
            ? " · committed, publication pending"
            : ""}
        </output>
      ) : null}
      {state.error !== null ? <p role="alert">{state.error}</p> : null}
    </main>
  );
}
