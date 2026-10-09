import {performCaptureUnavailableMessage} from "../state/error_messages";
import {useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore} from "react";

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
  // The Perform surface renders the same global Pattern transport projection
  // every other mode consumes; it never drives it.
  readonly transport?: PatternTransportState;
  readonly recordingBusy?: boolean;
}

type PerformPage = "live" | "slots" | "takes" | "replay";

function RecordingPanel(props: {
  readonly page: PerformPage;
  readonly onReview: () => void;
  readonly navigationDisabled: boolean;
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
      {props.page === "live" || props.page === "takes" ? <>
        {phase === "idle" ? <button type="button" disabled={!props.canRecord}
          onClick={props.onRecord}>Record Performance</button> : null}
        {phase === "recording" || phase === "flushing" ? <button type="button"
          onClick={props.onStop}>Stop Performance</button> : null}
        {props.page === "live" && phase === "stopped" ? <button type="button"
          disabled={props.navigationDisabled} onClick={props.onReview}>Review recording</button> : null}
      </> : null}
      {props.page === "takes" ? <>
        {phase === "recording" ? <button type="button"
          onClick={props.onFlush}>Flush Performance</button> : null}
        {["stopped", "saving", "discarding"].includes(phase) ? <>
          <label>Performance name
            <input type="text" aria-label="Performance name" value={name}
              disabled={phase !== "stopped"}
              onChange={(event) => setName(event.currentTarget.value)} />
          </label>
          <button type="button" disabled={phase !== "stopped" || name.trim() === ""}
            onClick={() => props.onSave(name.trim())}>Save Performance</button>
          <button type="button" disabled={phase !== "stopped"}
            onClick={props.onDiscard}>Discard Performance</button>
        </> : null}
        {props.state.recording.wav !== null ? <button type="button"
          onClick={props.onExportWav}>Export Performance WAV</button> : null}
        {props.state.bindingStatus === "retry" ? <button type="button"
          onClick={props.onRetryBind}>Retry WAV bind</button> : null}
      </> : null}
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
  readonly onRecover: (sessionId: string) => void;
  readonly onDiscardRecovery: (sessionId: string) => void;
}) {
  return (
    <section className="perform-replay" aria-label="Performance replay">
      {props.state.performances.map((performance) => (
        <article key={performance.performanceId}>
          <span>{performance.name}</span>
          <button type="button"
            aria-label={`Replay ${performance.name}`}
            onClick={() => {
              props.onReplay(performance.performanceId);
            }}>Replay</button>
        </article>
      ))}
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
  const [page, setPage] = useState<PerformPage>("live");
  const surface = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    surface.current?.scrollIntoView?.({block: "start", inline: "nearest"});
  }, [page]);
  const [fxGestureActive, setFxGestureActive] = useState(false);
  useEffect(() => { controller.setBank(props.bank); }, [controller, props.bank]);
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
      ? performCaptureUnavailableMessage(state.captureStatus.error.code)
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
    <main ref={surface} className="perform-surface" aria-label="Perform" data-page={page}>
      <nav className="perform-page-nav" aria-label="Perform pages">
        {(["live", "slots", "takes", "replay"] as const).map((value) => (
          <button type="button" key={value} disabled={fxGestureActive}
            aria-current={page === value ? "page" : undefined}
            onClick={() => setPage(value)}>
            {{live: "Live", slots: "Slots", takes: "Takes", replay: "Replay"}[value]}
          </button>
        ))}
      </nav>
      <header className="perform-live-header">
        <p className="perform-live-title">{{live: "LIVE CONTROLS", slots: "PATTERN SLOTS", takes: "RECORDING", replay: "REPLAY"}[page]}</p>
        <output className="perform-live-cue"
          aria-label="Pattern launch cue">{cue}</output>
      </header>
      <PatternLaunchStrip slots={props.project.patternSlots}
        patterns={props.project.patterns}
        pending={state.pendingLaunch} lastAck={state.lastLaunchAck}
        view={page === "live" ? "launch" : page === "slots" ? "edit" : null}
        disabled={!performing}
        mutationDisabled={state.recording.phase !== "idle"}
        onAssign={(patternSlot, patternId) => {
          void controller.assignPattern(patternSlot, patternId);
        }}
        onClear={(patternSlot) => { void controller.clearPattern(patternSlot); }}
        onMove={(fromSlot, toSlot) => {
          void controller.movePattern(fromSlot, toSlot);
        }}
        onLaunch={(patternSlot) => { void controller.launchPattern(patternSlot); }} />
      {page === "slots" ? <dl className="project-summary perform-project-summary" aria-label="Perform Project status">
        <div>
          <dt>Revision</dt>
          <dd role="definition">{props.project.revision}</dd>
        </div>
      </dl> : null}
      <FxSliderBank action={<button className="perform-hold" type="button" aria-pressed={state.hold}
        onClick={() => controller.toggleHold()}>HOLD</button>} active={page === "live"} onGestureActiveChange={setFxGestureActive} order={PERFORMANCE_FX_ORDER} values={state.fx}
        onEngage={(fx, value) => controller.engageFx(fx, value)}
        onMove={(gestureId, fx, value) => controller.moveFx(gestureId, fx, value)}
        onRelease={(gestureId, fx) => controller.releaseFx(gestureId, fx)} />
      <RecordingPanel page={page} navigationDisabled={fxGestureActive} onReview={() => setPage("takes")} state={state} canRecord={!props.recordingBusy && controller.canRecord()}
        onRecord={() => { void controller.record(); }}
        onFlush={() => { void controller.flush(); }}
        onStop={() => { void controller.stop(); }}
        onSave={(name) => { void controller.save(name); }}
        onDiscard={() => { void controller.discard(); }}
        onRetryBind={() => { void controller.retryWavBind(); }}
        onExportWav={() => { void controller.exportWav(); }} />
      {page === "replay" ? <ReplayPanel state={state}
        onReplay={(performanceId) => { void controller.beginReplay(performanceId); }}
        onRecover={(sessionId) => { void controller.applyRecovery(sessionId); }}
        onDiscardRecovery={(sessionId) => {
          void controller.discardRecovery(sessionId);
        }} /> : null}
      {page !== "replay" && state.recovery.length > 0 ? <button type="button"
        onClick={() => setPage("replay")} disabled={fxGestureActive}>
        Review recovery ({state.recovery.length})
      </button> : null}
      {state.replay !== null || page === "replay" ? <section aria-label="Current Performance replay">
        {state.replay?.state === "playing" ? <button type="button"
          onClick={() => { void controller.stopReplay().catch(() => {}); }}>Stop Replay</button> : null}
        <output role="status" aria-label="Replay status">
          {state.replay === null ? "idle" : `${state.replay.state}${
            state.replayNeutral ? " · neutral" : ""} · resolved revision · ${
            state.replay.resolvedRevision}`}
        </output>
      </section> : null}
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
