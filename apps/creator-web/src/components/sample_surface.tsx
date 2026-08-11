import {useEffect, useRef, useState} from "react";

import {BankSelector} from "./bank_selector";
import {ConfirmationDialog, SampleControls} from "./sample_controls";
import {WaveformEditor} from "./waveform_editor";
import type {createCreatorInputController} from "../runtime/input_controller";
import {
  cancelSamplePreviewJourney,
  importAssignSampleJourney,
  inspectSampleJourney,
  previewSampleDraftJourney,
  queryWaveformJourney,
  resetSampleJourney,
  updateSampleJourney,
  type SampleMutationResolution,
} from "../runtime/sample_actions";
import {refreshProjectProjectionJourney} from "../runtime/project_actions";
import type {
  CreatorSampleRuntimeSession,
  PadPlayback,
  TypedRuntimeError,
} from "../runtime/runtime_types";
import {
  beginSampleDraft,
  fitSampleViewport,
  updateSampleDraft,
  waveformWindowForViewport,
  type SamplePendingAction,
} from "../state/sample_state";
import {
  selectVisiblePads,
  type CreatorAction,
  type CreatorState,
} from "../state/creator_state";
import {padAddress} from "../state/view_model";

interface SampleSurfaceProps {
  state: CreatorState;
  session?: CreatorSampleRuntimeSession;
  controller?: ReturnType<typeof createCreatorInputController>;
  filePickIntent: {current: (slot: number) => void};
  dispatch: (action: CreatorAction) => void;
}

interface PendingFile {
  readonly slot: number;
  readonly file: File;
}

const SAMPLE_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED",
  "PERMISSION_DENIED",
  "IO_ERROR",
  "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME",
  "PROJECT_BUSY",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID",
  "HOST_TIMEOUT",
  "HOST_RESTART_REQUIRED",
  "HOST_PROTOCOL_MISMATCH",
]);
const PAD_KEY_CODES = Object.freeze([
  "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
  "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
]);

function publicOperationError(error: unknown): Readonly<{code: string; message: string}> {
  const candidate = (error as TypedRuntimeError | null)?.code;
  const code = candidate !== undefined && SAMPLE_ERROR_CODES.has(candidate)
    ? candidate
    : "INTERNAL_ERROR";
  return Object.freeze({code, message: "Sample operation failed"});
}

function metadataCopy(state: CreatorState): string {
  const metadata = state.sample.inspect?.metadata;
  if (metadata === null || metadata === undefined) return "No Sample assigned";
  const rate = metadata.sampleRate === 44_100 ? "44.1 kHz" : "48 kHz";
  const channels = metadata.channels === 1 ? "Mono" : "Stereo";
  return `${rate} · ${channels} · ${metadata.sourceFrames.toLocaleString()} frames`;
}

function displayFileName(name: string): string {
  const characters = Array.from(name);
  return characters.length <= 96 ? name : `${characters.slice(0, 95).join("")}…`;
}

export function SampleSurface({
  state,
  session,
  controller,
  filePickIntent,
  dispatch,
}: SampleSurfaceProps) {
  const input = useRef<HTMLInputElement | null>(null);
  const fileSlot = useRef<number | null>(null);
  const replaceReturnFocus = useRef<HTMLElement | null>(null);
  const importController = useRef<AbortController | null>(null);
  const operationPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const importPending = useRef<Readonly<SamplePendingAction> | null>(null);
  const previousSession = useRef(session);
  const previewEpoch = useRef(0);
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const sample = state.sample;
  const inspect = sample.inspect;
  const selectedSlot = sample.selectedSlot;

  useEffect(() => {
    filePickIntent.current = (slot) => {
      replaceReturnFocus.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      fileSlot.current = slot;
      input.current?.click();
    };
    return () => { filePickIntent.current = () => {}; };
  }, [filePickIntent]);

  useEffect(() => () => {
    const pending = importPending.current;
    importPending.current = null;
    if (pending !== null) {
      if (operationPending.current === pending) operationPending.current = null;
      dispatch({
        type: "sample-action",
        action: {type: "operation-cancelled", pending},
      });
    }
    importController.current?.abort();
    importController.current = null;
  }, [dispatch]);

  useEffect(() => {
    if (previousSession.current === session) return;
    previousSession.current = session;
    const pending = operationPending.current;
    operationPending.current = null;
    importPending.current = null;
    importController.current?.abort();
    importController.current = null;
    if (pending !== null) {
      dispatch({
        type: "sample-action",
        action: {type: "operation-cancelled", pending},
      });
    }
  }, [dispatch, session]);

  useEffect(() => {
    if (selectedSlot !== null || state.project.current === null) return;
    dispatch({
      type: "sample-action",
      action: {type: "slot-selected", slot: state.activeBank * 16},
    });
  }, [dispatch, selectedSlot, state.activeBank, state.project.current]);

  useEffect(() => {
    if (session === undefined || selectedSlot === null ||
      state.project.current === null) return;
    let current = true;
    void inspectSampleJourney(session, selectedSlot).then(
      (value) => {
        if (current) {
          dispatch({
            type: "sample-action",
            action: {type: "inspect-stored", inspect: value},
          });
        }
      },
      () => {
        // Input-controller and mutation paths own typed public failures.
      },
    );
    return () => { current = false; };
  }, [
    dispatch,
    sample.savedRevision,
    selectedSlot,
    session,
    state.project.current,
  ]);

  useEffect(() => {
    if (session === undefined || inspect === null || inspect.metadata === null ||
      inspect.waveformCacheIdentity === null) return;
    let current = true;
    const viewport = fitSampleViewport(inspect.metadata.sourceFrames);
    const window = waveformWindowForViewport(
      viewport,
      Math.min(256, inspect.metadata.sourceFrames),
    );
    const request = Object.freeze({
      slot: inspect.slot,
      window,
      waveformCacheIdentity: inspect.waveformCacheIdentity,
    });
    void queryWaveformJourney(session, {slot: inspect.slot, window}).then(
      (envelope) => {
        if (current) {
          dispatch({
            type: "sample-action",
            action: {type: "waveform-stored", envelope, request},
          });
        }
      },
      () => {
        // Inspect remains usable when the derived waveform query is unavailable.
      },
    );
    return () => { current = false; };
  }, [dispatch, inspect, session]);

  useEffect(() => {
    const refresh = state.sampleProjectionRefresh;
    const currentProject = state.project.current;
    if (refresh === null || session === undefined || currentProject === null) return;
    let active = true;
    let retryTimer: number | null = null;
    const waitForRetry = (milliseconds: number) => new Promise<void>((resolve) => {
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        resolve();
      }, milliseconds);
    });
    const failRefresh = (errorCode: string) => {
      if (active) dispatch({type: "sample-projection-refresh-failed", errorCode});
    };
    void (async () => {
      let currentInspect = refresh.inspect;
      for (let attempt = 0; attempt < 4; ++attempt) {
        if (attempt > 0) await waitForRetry(attempt * 25);
        if (!active) return;
        let project;
        try {
          project = await refreshProjectProjectionJourney(session, currentProject);
        } catch (error) {
          const code = publicOperationError(error).code;
          if (code === "PROJECT_BUSY") continue;
          failRefresh(code);
          return;
        }
        if (!active) return;
        if (project === null) continue;
        if (project.revision !== currentInspect.projectRevision) {
          try {
            currentInspect = await inspectSampleJourney(session, refresh.pending.slot);
          } catch (error) {
            const code = publicOperationError(error).code;
            if (code === "PROJECT_BUSY") continue;
            failRefresh(code);
            return;
          }
          if (project.revision !== currentInspect.projectRevision) continue;
        }
        if (!active) return;
        dispatch({
          type: "sample-project-refreshed",
          project,
          action: {...refresh, inspect: currentInspect},
        });
        return;
      }
      failRefresh("HOST_TIMEOUT");
    })();
    return () => {
      active = false;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [dispatch, session, state.project.current, state.sampleProjectionRefresh]);

  const dispatchResolution = (
    pending: Readonly<SamplePendingAction>,
    resolution: SampleMutationResolution,
  ): void => {
    if (operationPending.current !== pending) return;
    operationPending.current = null;
    if (importPending.current === pending) importPending.current = null;
    dispatch({
      type: "sample-projection-refresh-started",
      action: resolution.kind === "committed"
        ? {
            type: "mutation-committed",
            pending,
            inspect: resolution.inspect,
            commit: resolution.commit,
          }
        : {
            type: "mutation-conflicted",
            pending,
            inspect: resolution.inspect,
          },
    });
  };

  const isAssigned = (slot: number): boolean =>
    (state.project.current?.pads[slot]?.assetId !== null &&
      state.project.current?.pads[slot]?.assetId !== undefined) ||
    (inspect?.slot === slot && inspect.assetId !== null);

  const stopIfActive = async (slot: number) => {
    if (session === undefined || !sample.voices.some((voice) => voice.slot === slot)) return;
    if (await session.stopPad(slot) !== true) {
      throw Object.assign(new Error("Sample stop failed"), {code: "HOST_STATE_INVALID"});
    }
  };

  const performUpdate = async (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    previewEpoch.current += 1;
    const pending = Object.freeze({
      kind: "update" as const,
      slot: inspect.slot,
      expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    try {
      if (playback.muted !== inspect.playback.muted) await stopIfActive(inspect.slot);
      const resolution = await updateSampleJourney(session, {
        slot: inspect.slot,
        expectedRevision: inspect.projectRevision,
        playback,
      });
      if (operationPending.current !== pending) return;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
      dispatch({type: "sample-action", action: {type: "preview-cleared"}});
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: publicOperationError(error)},
      });
    }
  };

  const preview = (playback: Readonly<PadPlayback>) => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const epoch = ++previewEpoch.current;
    const draft = updateSampleDraft(
      beginSampleDraft(inspect.playback, inspect.projectRevision),
      playback,
    );
    if (sample.draft === null) {
      dispatch({type: "sample-action", action: {type: "draft-began"}});
    }
    dispatch({
      type: "sample-action",
      action: {type: "draft-updated", changes: playback},
    });
    void previewSampleDraftJourney(session, inspect.slot, draft).then(
      () => {
        if (previewEpoch.current === epoch) {
          dispatch({
            type: "sample-action",
            action: {type: "preview-applied", playback},
          });
        }
      },
      () => {
        if (previewEpoch.current === epoch) {
          dispatch({type: "sample-action", action: {type: "preview-failed"}});
        }
      },
    );
  };

  const cancelPreview = () => {
    previewEpoch.current += 1;
    dispatch({type: "sample-action", action: {type: "draft-cancelled"}});
    if (session !== undefined && selectedSlot !== null) {
      void cancelSamplePreviewJourney(session, selectedSlot).then(
        () => dispatch({type: "sample-action", action: {type: "preview-cleared"}}),
        () => {},
      );
    }
  };

  const reset = async () => {
    if (session === undefined || inspect === null || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const pending = Object.freeze({
      kind: "reset" as const,
      slot: inspect.slot,
      expectedRevision: inspect.projectRevision,
    });
    operationPending.current = pending;
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    try {
      await stopIfActive(inspect.slot);
      const resolution = await resetSampleJourney(session, {
        slot: inspect.slot,
        expectedRevision: inspect.projectRevision,
      });
      if (operationPending.current !== pending) return;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      dispatch({
        type: "sample-action",
        action: {type: "operation-failed", pending, error: publicOperationError(error)},
      });
    }
  };

  const performImport = async ({slot, file}: PendingFile) => {
    if (session === undefined || sample.pendingAction !== null ||
      operationPending.current !== null) return;
    const expectedRevision = sample.savedRevision ?? state.project.current?.revision;
    if (expectedRevision === null || expectedRevision === undefined) return;
    const assigned = isAssigned(slot);
    const pending = Object.freeze({
      kind: assigned ? "replace" as const : "import" as const,
      slot,
      expectedRevision,
    });
    dispatch({type: "sample-action", action: {type: "pending-began", pending}});
    const controller = new AbortController();
    importController.current = controller;
    operationPending.current = pending;
    importPending.current = pending;
    try {
      if (assigned) await stopIfActive(slot);
      const resolution = await importAssignSampleJourney(session, file, {
        slot,
        expectedRevision,
        signal: controller.signal,
      });
      if (operationPending.current !== pending) return;
      dispatchResolution(pending, resolution);
    } catch (error) {
      if (operationPending.current !== pending) return;
      operationPending.current = null;
      importPending.current = null;
      if (error instanceof DOMException && error.name === "AbortError") {
        dispatch({
          type: "sample-action",
          action: {type: "operation-cancelled", pending},
        });
      } else {
        dispatch({
          type: "sample-action",
          action: {type: "operation-failed", pending, error: publicOperationError(error)},
        });
      }
    } finally {
      if (importController.current === controller) importController.current = null;
    }
  };

  const chooseFile = (slot: number) => {
    replaceReturnFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    fileSlot.current = slot;
    input.current?.click();
  };
  const selectedAddress = selectedSlot === null
    ? "No Pad selected"
    : `Pad ${padAddress({slot: selectedSlot, assetId: inspect?.assetId ?? null})}`;
  const editablePlayback = sample.auditionPlayback ?? sample.draft?.proposed ?? inspect?.playback;
  const selectedAssigned = inspect?.assetId !== null && inspect?.assetId !== undefined;
  const projectUnavailable = state.project.phase !== "ready" ||
    state.project.current === null;
  const actionsDisabled = session === undefined || projectUnavailable || inspect === null ||
    !selectedAssigned || sample.pendingAction !== null;
  const inspectedMetadata = inspect?.metadata;
  const queryViewportWaveform = session === undefined || inspect === null ||
      inspectedMetadata === null || inspectedMetadata === undefined ||
      inspect.waveformCacheIdentity === null
    ? undefined
    : async (viewport: Readonly<ReturnType<typeof fitSampleViewport>>) => {
        const span = viewport.endFrame - viewport.startFrame;
        const window = waveformWindowForViewport(viewport, Math.min(256, span));
        const envelope = await queryWaveformJourney(session, {slot: inspect.slot, window});
        if (envelope.projectRevision !== inspect.projectRevision ||
          envelope.metadata.sourceFrames !== inspectedMetadata.sourceFrames ||
          envelope.metadata.sampleRate !== inspectedMetadata.sampleRate ||
          envelope.metadata.channels !== inspectedMetadata.channels) {
          return null;
        }
        return envelope;
      };

  return (
    <main className="sample-surface">
      <header className="sample-heading">
        <div>
          <p className="eyebrow">Sample surface</p>
          <h1>Sample editor</h1>
        </div>
        <div className="selected-sample" aria-live="polite">
          <strong>{selectedAddress}</strong>
          <span>{inspect?.assetId === null || inspect?.assetId === undefined
            ? "Empty"
            : `Asset ${inspect.assetId.slice(0, 8)}`}</span>
          <span>{metadataCopy(state)}</span>
          {selectedAssigned && selectedSlot !== null ? (
            <button
              type="button"
              disabled={session === undefined || projectUnavailable ||
                sample.pendingAction !== null}
              onClick={() => chooseFile(selectedSlot)}
            >
              Replace Sample
            </button>
          ) : null}
        </div>
      </header>

      {inspect !== null && inspect.metadata !== null && editablePlayback !== undefined ? (
        <>
          <WaveformEditor
            key={`${inspect.slot}:${inspect.waveformCacheIdentity ?? "none"}`}
            padLabel={selectedAddress}
            envelope={sample.waveform}
            metadata={inspect.metadata}
            projectRevision={inspect.projectRevision}
            playback={editablePlayback}
            playheadFrame={sample.playhead?.sourceFrame ?? null}
            disabled={actionsDisabled}
            onPreview={preview}
            onCommit={(playback) => { void performUpdate(playback); }}
            onCancel={cancelPreview}
            {...(queryViewportWaveform === undefined
              ? {}
              : {onQueryWaveform: queryViewportWaveform})}
          />
          <SampleControls
            padLabel={selectedAddress}
            playback={editablePlayback}
            audioSuspended={state.audio.phase !== "running" && state.audio.phase !== "recovering"}
            disabled={actionsDisabled}
            onPreview={preview}
            onCommit={(playback) => { void performUpdate(playback); }}
            onCancel={cancelPreview}
            onReset={() => { void reset(); }}
          />
        </>
      ) : (
        <section className="empty-sample" aria-label="Selected Pad Sample">
          <p>Select an assigned Pad to edit its waveform and playback.</p>
          {selectedSlot === null ? null : (
            <button
              type="button"
              disabled={session === undefined || projectUnavailable ||
                sample.pendingAction !== null}
              onClick={() => chooseFile(selectedSlot)}
            >
              Add Sample to {selectedAddress}
            </button>
          )}
        </section>
      )}

      {sample.lastError === null ? null : (
        <p className="sample-error" role="alert">{sample.lastError.message}</p>
      )}

      <section className="sample-pads" aria-label="Sample Pads">
        <BankSelector
          activeBank={state.activeBank}
          onSelect={(bank) => {
            controller?.clearPressed();
            dispatch({type: "bank-selected", bank});
          }}
        />
        <div className="pad-grid" aria-label="Playable Pads">
          {selectVisiblePads(state).map((pad) => {
            const address = padAddress(pad);
            const selected = sample.selectedSlot === pad.slot;
            const assigned = pad.assetId !== null ||
              (selected && inspect?.assetId !== null && inspect?.assetId !== undefined);
            const outcome = state.pressed.get(pad.slot);
            return (
              <button
                type="button"
                className={`pad${selected ? " is-selected" : ""}`}
                data-outcome={outcome ?? "idle"}
                aria-pressed={selected}
                aria-label={`Pad ${address} — ${assigned ? "assigned" : "empty"}`}
                key={pad.slot}
                disabled={projectUnavailable}
                onPointerDown={(event) => controller?.pointerDown(event, pad.slot)}
                onMouseDown={(event) => controller?.pointerDown(event, pad.slot)}
                onPointerUp={(event) => controller?.pointerUp(event, pad.slot)}
                onMouseUp={(event) => controller?.pointerUp(event, pad.slot)}
                onPointerCancel={(event) => controller?.pointerCancel(event, pad.slot)}
                onKeyDown={(event) => {
                  if (!assigned || controller === undefined ||
                    (event.key !== "Enter" && event.key !== " ")) return;
                  event.preventDefault();
                  if (event.repeat) return;
                  const code = PAD_KEY_CODES[pad.slot - state.activeBank * 16];
                  if (code !== undefined) {
                    controller.keyDown({code, repeat: false, target: document.body});
                  }
                }}
                onKeyUp={(event) => {
                  if (!assigned || controller === undefined ||
                    (event.key !== "Enter" && event.key !== " ")) return;
                  event.preventDefault();
                  const code = PAD_KEY_CODES[pad.slot - state.activeBank * 16];
                  if (code !== undefined) {
                    controller.keyUp({code, repeat: false, target: document.body});
                  }
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  const file = event.dataTransfer.files[0];
                  if (file === undefined) return;
                  if (!selected) {
                    dispatch({
                      type: "sample-action",
                      action: {type: "slot-selected", slot: pad.slot},
                    });
                  }
                  if (assigned) {
                    replaceReturnFocus.current = event.currentTarget;
                    setPendingFile({slot: pad.slot, file});
                  }
                  else void performImport({slot: pad.slot, file});
                }}
                onClick={(event) => {
                  if (!selected) {
                    dispatch({
                      type: "sample-action",
                      action: {type: "slot-selected", slot: pad.slot},
                    });
                  }
                  if (!assigned && (controller === undefined || event.detail === 0)) {
                    chooseFile(pad.slot);
                  }
                }}
              >
                <strong>{address}</strong>
                <span>{assigned ? "Assigned" : "Empty"}</span>
              </button>
            );
          })}
        </div>
      </section>

      <input
        ref={input}
        className="sample-file-input"
        type="file"
        accept=".wav,audio/wav,audio/wave"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          const slot = fileSlot.current;
          event.currentTarget.value = "";
          if (file === undefined || slot === null) return;
          const assigned = isAssigned(slot);
          if (assigned) setPendingFile({slot, file});
          else void performImport({slot, file});
        }}
      />
      {pendingFile === null ? null : (
        <ConfirmationDialog
          labelledBy="replace-heading"
          returnFocus={replaceReturnFocus.current}
          onCancel={() => setPendingFile(null)}
        >
          <h2 id="replace-heading">
            Replace Pad {padAddress({slot: pendingFile.slot, assetId: null})}?
          </h2>
          <p>{displayFileName(pendingFile.file.name)}</p>
          <p>Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.</p>
          <div className="confirmation-actions">
            <button type="button" onClick={() => setPendingFile(null)}>Cancel replace</button>
            <button
              type="button"
              onClick={() => {
                const replacement = pendingFile;
                setPendingFile(null);
                void performImport(replacement);
              }}
            >
              Confirm replace
            </button>
          </div>
        </ConfirmationDialog>
      )}
    </main>
  );
}
