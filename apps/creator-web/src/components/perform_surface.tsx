import "./perform_surface.css";
import {performCaptureUnavailableMessage} from "../state/error_messages";
import {useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore} from "react";
import type {PerformanceFx} from "@lmdj/web-runtime-platform/runtime_types";
import type {ContextualEncoders, ContextualNavigation} from "./physical_controls";

import type {ProjectView} from "../runtime/runtime_types";
import type {Bank} from "../state/creator_state";
import {
  selectTransportBusy,
  selectTransportPlaying,
  type PatternTransportState,
} from "../state/pattern_transport_state";
import {transportStatusLabel} from "./transport_status";
import {
  PERFORMANCE_FX_ORDER,
  selectLivePadGate,
  type PerformController,
  type PerformState,
} from "../state/perform_state";
import {
  formatCutoffHz,
  FxSliderBank,
  type FxGroup,
  type MonitorVolumeControl,
} from "./fx_slider_bank";
import {slotAddress} from "../state/view_model";
import {PatternLaunchStrip} from "./pattern_launch_strip";
import {RecordingAudioReadout} from "./recording_audio_readout";

export interface PerformSurfaceProps {
  readonly controller: PerformController;
  readonly project: ProjectView;
  readonly bank: Bank;
  readonly currentPad?: number;
  // The Perform surface renders the same global Pattern transport projection
  // every other mode consumes; it never drives it.
  readonly transport?: PatternTransportState;
  readonly recordingBusy?: boolean;
  readonly reviewRequested?: boolean;
  readonly onReviewShown?: () => void;
  readonly onEncodersReady?: (encoders: ContextualEncoders | null) => void;
  readonly onNavigationReady?: (navigation: ContextualNavigation | null) => void;
  readonly monitorVolume?: MonitorVolumeControl | undefined;
  // #1958: without a Performance recording, a Launch slot selects its Pattern
  // through the app's Sequence selection path, which queues a transport switch
  // while playing and reloads the snapshot while stopped.
  readonly onSelectPattern?: (patternId: string) => void;
  readonly patternSelectionLocked?: boolean;
  readonly slotEditingLocked?: boolean;
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
      {props.page === "live" || props.page === "takes"
        ? <RecordingAudioReadout progress={props.state.recordingAudio} /> : null}
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
      <p aria-hidden="true">{phase === "stopped" ? "Ready to save or discard" : phase}
        {props.state.recordingNote === null ? "" : ` · ${props.state.recordingNote}`}</p>
      <output className="visually-hidden" role="status" aria-label="Performance recording status">
        {phase}
        {props.state.recordingNote === null ? "" : ` · ${props.state.recordingNote}`}
        {props.state.authority === null ? "" : ` · open Pads: ${
          props.state.authority.openPadGestures} · open FX: ${
          props.state.authority.openFxGestures} · HOLD: ${
          props.state.authority.hold ? "on" : "off"}`}
      </output>
      <output className="visually-hidden" role="status" aria-label="WAV recording status">
        {props.state.wavStatus}
      </output>
      <output className="visually-hidden" role="status" aria-label="WAV binding status">
        {props.state.bindingStatus}
      </output>
      <details className="perform-details">
        <summary>Recording details</summary>
        <dl>
          <div><dt>WAV recording</dt><dd>{props.state.wavStatus}</dd></div>
          <div><dt>WAV binding</dt><dd>{props.state.bindingStatus}</dd></div>
          {props.state.authority !== null && <>
            <div><dt>Open Pad gestures</dt><dd>{props.state.authority.openPadGestures}</dd></div>
            <div><dt>Open FX gestures</dt><dd>{props.state.authority.openFxGestures}</dd></div>
            <div><dt>HOLD</dt><dd>{props.state.authority.hold ? "on" : "off"}</dd></div>
          </>}
        </dl>
      </details>
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
  useEffect(() => {
    if (!props.reviewRequested) return;
    setPage("takes");
    props.onReviewShown?.();
  }, [props.reviewRequested, props.onReviewShown]);
  useLayoutEffect(() => {
    surface.current?.scrollIntoView?.({block: "start", inline: "nearest"});
  }, [page]);
  const [fxGestureActive, setFxGestureActive] = useState(false);
  useEffect(() => { controller.setBank(props.bank); }, [controller, props.bank]);
  const [encoderGroup, setEncoderGroup] = useState<FxGroup>("main");
  const [padGatesOpen, setPadGatesOpen] = useState(false);
  const navigation = useMemo<ContextualNavigation>(() => {
    const groups: readonly FxGroup[] = ["main", "filter", "more"];
    const index = groups.indexOf(encoderGroup);
    const step = (direction: -1 | 1) => {
      setPadGatesOpen(false);
      setEncoderGroup(groups[Math.max(0, Math.min(2, index + direction))]!);
    };
    return {directionStep: {
      backLabel: "Previous FX group — ←", forwardLabel: "Next FX group — →",
      backAvailable: index > 0, forwardAvailable: index < 2,
      onBack: () => step(-1), onForward: () => step(1),
    }};
  }, [encoderGroup]);
  useLayoutEffect(() => {
    props.onNavigationReady?.(navigation);
    return () => props.onNavigationReady?.(null);
  }, [navigation, props.onNavigationReady]);
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getState,
    controller.getState,
  );
  const encoders = useMemo<ContextualEncoders>(() => {
    if (encoderGroup === "filter") {
      // The FILTER group is pure UI state: entering it calls no producer and
      // engages nothing (D04); the first actual turn engages.
      return {bindings: {
        1: {label: "Type", value: state.filter.provenance === "unavailable" ? "—" : state.filter.type.toUpperCase(),
          onTurn: (detents: number) => controller.turnFilterType(detents)},
        2: {label: "Cutoff", value: state.filter.provenance === "unavailable" ? "—" : formatCutoffHz(state.filter.cutoffHz),
          onTurn: (detents: number, fine?: boolean) =>
            controller.turnFilterCutoff(detents, fine)},
        3: {label: "Resonance",
          value: state.filter.provenance === "unavailable" ? "—" : `${(state.filter.resonanceMilli / 10).toFixed(1)}%`,
          onTurn: (detents: number, fine?: boolean) =>
            controller.turnFilterResonance(detents, fine)},
      }};
    }
    if (encoderGroup === "more") {
      const group = ["crush", "stutter", "gate"] as const;
      return {bindings: Object.fromEntries(group.map((fx, index) => [index + 1, {
        label: fx[0]!.toUpperCase() + fx.slice(1),
        value: `${(state.fx[fx] / 10).toFixed(1)}%`,
        onTurn: (detents: number, fine?: boolean) => controller.turnFx(fx, detents, fine),
      }]))};
    }
    // Main group: ENC1 is the independent Filter cutoff when the typed
    // producer answered; an unavailable producer — or a legacy Filter
    // gesture still open from before the first answer — keeps the legacy
    // scalar Filter turn.
    const typed = state.liveControl.available && !state.legacyFilterGesture;
    return {bindings: {
      1: typed
        ? {label: "Cutoff", value: formatCutoffHz(state.filter.cutoffHz),
            onTurn: (detents: number, fine?: boolean) =>
              controller.turnFilterCutoff(detents, fine)}
        : {label: "Filter", value: `${(state.fx.filter / 10).toFixed(1)}%`,
            onTurn: (detents: number, fine?: boolean) =>
              controller.turnFx("filter", detents, fine)},
      2: {label: "Delay", value: `${(state.fx.delay / 10).toFixed(1)}%`,
        onTurn: (detents: number, fine?: boolean) =>
          controller.turnFx("delay", detents, fine)},
      3: {label: "Reverb", value: `${(state.fx.reverb / 10).toFixed(1)}%`,
        onTurn: (detents: number, fine?: boolean) =>
          controller.turnFx("reverb", detents, fine)},
    }};
  }, [controller, encoderGroup, state.fx, state.filter,
    state.liveControl.available, state.legacyFilterGesture]);
  useLayoutEffect(() => {
    props.onEncodersReady?.(encoders);
    return () => props.onEncodersReady?.(null);
  }, [props.onEncodersReady, encoders]);
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
  const currentPad = props.currentPad;
  const currentGate = currentPad === undefined ? null : selectLivePadGate(state.padGates, currentPad);
  const gatesDisabled = currentGate === null || state.padGates.provenance !== "core" ||
    state.replay?.state === "playing" ||
    !["idle", "recording", "flushing", "stopped"].includes(state.recording.phase);
  const performing = ["recording", "flushing"].includes(state.recording.phase);
  // #1958: without a Performance recording, Launch drives the global transport
  // through selection. Unsettled Performance operations still own their
  // recording/capture transition. Global Pattern recording uses this ordinary
  // selection path after opening; it never joins the Performance event clock.
  const transportLaunchOpen = ["idle", "stopped"].includes(state.recording.phase) &&
    props.patternSelectionLocked !== true &&
    props.transport !== undefined &&
    props.transport.status !== null &&
    !selectTransportBusy(props.transport);
  const launchDisabled = !performing && !transportLaunchOpen;
  // The transport's slot facts exist only while it plays; stopped, no slot is
  // Playing and a queued switch cannot outlive Stop.
  const transportPlaying = props.transport !== undefined &&
    selectTransportPlaying(props.transport);
  return (
    <main ref={surface} className="perform-surface" aria-label="Perform" data-page={page} data-pad-gates={padGatesOpen}>
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
      </header>
      <FxSliderBank action={<button className="perform-hold" type="button" aria-pressed={state.hold}
        onClick={() => controller.toggleHold()}>HOLD</button>} gestureOwner={controller} active={page === "live" && !padGatesOpen} onGestureActiveChange={setFxGestureActive} order={PERFORMANCE_FX_ORDER} values={state.fx}
        filter={state.filter}
        legacyFilterGesture={state.legacyFilterGesture}
        onFilterType={(type) => controller.setFilterType(type)}
        onFilterTouchEngage={(parameter) => controller.touchFilterEngage(parameter)}
        onFilterTouchMove={(token, parameter, value) =>
          controller.touchFilterMove(token, parameter, value)}
        onFilterTouchRelease={(token, parameter) =>
          controller.touchFilterRelease(token, parameter)}
        monitorVolume={props.monitorVolume}
        group={encoderGroup}
        onGroupChange={setEncoderGroup}
        onEngage={(fx, value) => controller.engageFx(fx, value)}
        onMove={(gestureId, fx, value) => controller.moveFx(gestureId, fx, value)}
        onRelease={(gestureId, fx) => controller.releaseFx(gestureId, fx)} />
      <PatternLaunchStrip slots={props.project.patternSlots}
        patterns={props.project.patterns}
        pending={state.pendingLaunch} lastAck={state.lastLaunchAck}
        view={page === "live" ? "launch" : page === "slots" ? "edit" : null}
        disabled={launchDisabled}
        mutationDisabled={props.slotEditingLocked === true || state.recording.phase !== "idle"}
        transportPendingPatternId={props.transport?.status?.pendingSwitch?.patternId ?? null}
        transportCurrentPatternId={transportPlaying
          ? props.transport?.status?.currentPatternId ?? null
          : null}
        onAssign={(patternSlot, patternId) => {
          void controller.assignPattern(patternSlot, patternId);
        }}
        onClear={(patternSlot) => { void controller.clearPattern(patternSlot); }}
        onMove={(fromSlot, toSlot) => {
          void controller.movePattern(fromSlot, toSlot);
        }}
        onLaunch={(patternSlot) => {
          if (performing) {
            void controller.launchPattern(patternSlot);
            return;
          }
          // #1958: outside a Performance recording an empty slot has nothing
          // to launch — no switch, no selection.
          const patternId = props.project.patternSlots[patternSlot] ?? null;
          if (patternId === null) return;
          props.onSelectPattern?.(patternId);
        }} />
      {page === "slots" ? <details className="perform-details"><summary>Project details</summary>
      <dl className="project-summary perform-project-summary" aria-label="Perform Project status">
        <div>
          <dt>Revision</dt>
          <dd role="definition">{props.project.revision}</dd>
        </div>
      </dl></details> : null}
      {page === "live" && !padGatesOpen ? <button type="button" className="perform-pad-gates-entry"
        onClick={() => { setPadGatesOpen(true); }}>
        Live Mute / Solo
      </button> : null}
      {page === "live" && padGatesOpen && currentPad !== undefined && currentGate !== null ? (
        <section className="perform-pad-gates" aria-label="Current Pad live controls">
          <header><p>LIVE MUTE / SOLO · Bank {slotAddress(currentPad)[0]}</p>
            <strong>Current Pad {slotAddress(currentPad)}</strong></header>
          <button type="button" aria-label={`Mute ${slotAddress(currentPad)}`}
            aria-pressed={currentGate.muted} disabled={gatesDisabled}
            onClick={() => controller.togglePadGate("mute", currentPad)}>Mute</button>
          <button type="button" aria-label={`Solo ${slotAddress(currentPad)}`}
            aria-pressed={currentGate.solo} disabled={gatesDisabled}
            onClick={() => controller.togglePadGate("solo", currentPad)}>Solo</button>
          <output role="status" aria-label="Live Pad status">
            {state.padGates.provenance === "unavailable" ? "Unavailable" :
              state.padGates.provenance === "pending" ? "Pending" :
              currentGate.muted ? "Silenced · Mute" :
              currentGate.silenced ? "Silenced · other Pads soloed" :
              currentGate.solo ? "Active · Solo" : "Active"}
          </output>
          <dl className="perform-pad-gate-summary" data-provenance={state.padGates.provenance}>
            {(["mutedSlots", "soloSlots"] as const).map((kind) => <div key={kind}>
              <dt>{kind === "mutedSlots" ? "Muted Pads" : "Soloed Pads"}</dt>
              <dd>{state.padGates.provenance !== "core" ?
                (state.padGates.provenance === "pending" ? "Pending" : "Unavailable") :
                [...state.padGates[kind]].sort((a, b) => a - b).map(slotAddress).join(" · ") || "None"}</dd>
            </div>)}
          </dl>
          <p>Mute silences a Pad even when it is soloed. Multiple Pads can be soloed together.</p>
          <button type="button" onClick={() => {setEncoderGroup("filter"); setPadGatesOpen(false);}}>
            Back to Filter
          </button>
        </section>
      ) : null}
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
        <p aria-hidden="true">{state.replay?.state ?? "No replay selected"}</p>
        <output className="visually-hidden" role="status" aria-label="Replay status">
          {state.replay === null ? "idle" : `${state.replay.state}${
            state.replayNeutral ? " · neutral" : ""} · resolved revision · ${
            state.replay.resolvedRevision}`}
        </output>
        {state.replay !== null && <details className="perform-details">
          <summary>Replay details</summary>
          <dl><div><dt>Resolved revision</dt><dd>{state.replay.resolvedRevision}</dd></div>
            <div><dt>Neutral FX</dt><dd>{state.replayNeutral ? "yes" : "no"}</dd></div></dl>
        </details>}
      </section> : null}
      {captureMessage !== null ? <p role="status">{captureMessage}</p> : null}
      {props.transport !== undefined ? (
        <output role="status" aria-label="Pattern transport status">
          Pattern transport: {transportStatusLabel(props.transport)}
          {props.transport.status?.publicationPending === true
            ? " · publication pending"
            : ""}
        </output>
      ) : null}
      {state.error !== null ? <p role="alert">{state.error}</p> : null}
    </main>
  );
}
