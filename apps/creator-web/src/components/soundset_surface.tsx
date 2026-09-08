import {useCallback, useEffect, useReducer} from "react";

import {BankSelector} from "./bank_selector";
import type {Bank} from "../state/creator_state";
import {bankName} from "../state/view_model";
import {
  initialSoundSetState,
  reduceSoundSet,
  selectBusy,
  selectCanInstall,
  selectPadPlan,
  selectWriteCount,
  type SoundSetError,
  type SoundSetState,
} from "../state/soundset_state";
import type {
  CreatorRuntimeSession,
  CreatorSoundSetRuntimeSession,
  OccupiedPadPolicy,
  SoundSetIdentity,
  SoundSetSlot,
  SoundSetSummary,
  TypedRuntimeError,
} from "../runtime/runtime_types";

interface SoundSetSurfaceProps {
  session?: CreatorSoundSetRuntimeSession;
  projectRevision: number | null;
  activeBank: Bank;
  onBankChange?: (bank: Bank) => void;
  onInstalled?: (revision: number) => void;
  initialState?: SoundSetState;
}

export function isSoundSetSession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorSoundSetRuntimeSession {
  return session !== undefined &&
    typeof (session as CreatorSoundSetRuntimeSession).listSoundSets ===
      "function";
}

function failure(error: unknown): SoundSetError {
  const typed = error as TypedRuntimeError | null;
  const details = typed?.details;
  const candidate = details !== null && typeof details === "object"
    ? (details as Record<string, unknown>).reason
    : null;
  const reason = typeof candidate === "string" ? candidate : null;
  return {
    code: typed?.code ?? "INTERNAL_ERROR",
    reason,
    message: typed?.message ?? "Sound Set request failed",
  };
}

export function formatSetBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function soundSetReasonCopy(error: SoundSetError): string | null {
  switch (error.reason) {
    case "soundset_license_ineligible":
      return "This Set's licence is outside the allowed list, or its required attribution is missing.";
    case "soundset_audio_unsupported":
      return "Accepted Set audio: PCM16 WAV, mono or stereo, 44.1 or 48 kHz";
    case "soundset_content_mismatch":
      return "The Catalog answered with bytes that are not the ones this Set declares.";
    case "catalog_unavailable":
      return "The Catalog could not be reached. Sets already in this Workspace are still listed.";
    case "soundset_occupied_conflict":
      return "Choose Keep or Replace for the occupied Pads before installing.";
    case "soundset_manifest_invalid":
    case "soundset_slot_invalid":
      return "This Set's manifest is not a valid Sound Set package.";
    default:
      return null;
  }
}

function identityOf(summary: Readonly<SoundSetSummary>): SoundSetIdentity {
  return {
    setId: summary.setId,
    version: summary.version,
    manifestSha256: summary.manifestSha256,
  };
}

// S11-D12: a slot is empty exactly when it declares no Artifact. Emptiness is
// never rendered as something the user can act on, because installing an empty
// Set slot is not a "clear this Pad" instruction.
function slotIsEmpty(slot: Readonly<SoundSetSlot>): boolean {
  return slot.artifact === null;
}

// AUDITION ATTACHMENT POINT (S11-D5, issue #773 phase 2, byte path #799).
//
// This surface plays nothing. Auditioning a Sound Set needs a Facade path that
// carries Set Store bytes to the audio engine, and there is none: the four
// operations this surface uses carry no audio, `soundset.audition` resolves and
// gates a playable Artifact but hands back an envelope with no samples, and
// `sample.preview.set` addresses a Project Pad, which an uninstalled Set slot
// is not. Reaching into Set Store bytes from the Host would put playback
// outside the Application Facade, so this surface deliberately stops at
// metadata.
//
// When that path exists, an audition control attaches at exactly two places and
// needs no restructuring:
//
//   1. the set-level demo, at the `soundset-demo` paragraph in the inspect
//      panel below — `selected.demo` already carries the Artifact reference,
//      and `selected.hasDemo` is on every listing summary;
//   2. one occupied slot, at the `soundset-slot-sound` span in the slots list —
//      `slot.artifact` and `slot.audio` are already there, and `slotIsEmpty`
//      already decides which rows may carry a control at all.
//
// Both sites render a bare `<span>` today precisely so that adding a `<button>`
// is the whole change. Add the control to those two spans; do not add a third
// surface, and do not reach past the Facade for bytes.

export function SoundSetSurface({
  session,
  projectRevision,
  activeBank,
  onBankChange,
  onInstalled,
  initialState = initialSoundSetState,
}: SoundSetSurfaceProps) {
  const [state, dispatch] = useReducer(reduceSoundSet, {
    ...initialState,
    targetBank: activeBank,
  });
  const busy = selectBusy(state);

  const refresh = useCallback(async () => {
    if (session === undefined) return;
    dispatch({type: "listing"});
    try {
      dispatch({type: "listed", catalog: await session.listSoundSets()});
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  }, [session]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const inspect = async (summary: Readonly<SoundSetSummary>) => {
    if (session === undefined) return;
    dispatch({type: "inspecting"});
    try {
      dispatch({
        type: "inspected",
        inspect: await session.inspectSoundSet(identityOf(summary)),
      });
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  };

  // #799. Audition is fire-and-forget with respect to this surface: the Host
  // publishes the decoded PCM into its reserved audition bank and starts a
  // voice, and what comes back is only the geometry of what it played. There
  // is no "now playing" state to hold, because the engine owns that and a
  // second audition replaces the first without this surface arbitrating.
  const audition = async (slotIndex?: number) => {
    if (session === undefined || state.selected === null) return;
    try {
      await session.auditionSoundSet(
        slotIndex === undefined
          ? identityOf(state.selected)
          : {...identityOf(state.selected), slotIndex},
      );
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  };

  // Idempotent by contract, so this needs no guard on whether anything is
  // playing -- asking for that guard here would be this surface duplicating a
  // decision the engine already owns, and getting it wrong whenever a voice
  // ended between the render and the click.
  const stopAudition = async () => {
    if (session === undefined) return;
    try {
      await session.stopSoundSetAudition();
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  };

  const preview = async () => {
    if (session === undefined || state.selected === null) return;
    dispatch({type: "previewing"});
    try {
      dispatch({
        type: "previewed",
        preview: await session.previewSoundSetMap({
          ...identityOf(state.selected),
          bankId: state.targetBank,
        }),
      });
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  };

  const install = async () => {
    if (
      session === undefined || state.selected === null ||
      state.preview === null || projectRevision === null
    ) {
      return;
    }
    dispatch({type: "installing"});
    const commandId = crypto.randomUUID();
    try {
      const receipt = await session.installSoundSet({
        ...identityOf(state.selected),
        bankId: state.preview.bankId,
        commandId,
        // The revision the mapping was computed against, not whatever the
        // Project is now: `expected_revision` exists so a Project that moved
        // between the preview and the confirmation refuses the install
        // instead of writing a mapping the user never saw.
        expectedRevision: state.preview.projectRevision,
        // #465 Q2: the policy travels only when the user chose one. A mapping
        // with no collision carries none, and a mapping with collisions cannot
        // be submitted until one is chosen.
        ...(state.policy === null ? {} : {occupiedPadPolicy: state.policy}),
      });
      dispatch({type: "installed", receipt});
      onInstalled?.(receipt.committedRevision);
    } catch (error) {
      dispatch({type: "failed", error: failure(error)});
    }
  };

  const selected = state.selected;
  const padPlan = selectPadPlan(state);
  const collisions = state.preview?.collisions ?? [];

  return (
    <section className="soundset-surface" aria-label="Sound Sets">
      <header className="soundset-header">
        <h2>Sound Sets</h2>
        <button
          type="button"
          disabled={session === undefined || busy}
          onClick={() => { void refresh(); }}
        >
          Refresh Catalog
        </button>
      </header>

      {state.catalogAvailable === false ? (
        <p className="soundset-offline" role="status">
          Catalog unreachable — showing {state.sets.length} cached{" "}
          {state.sets.length === 1 ? "Set" : "Sets"} from this Workspace
        </p>
      ) : null}

      {state.lastError === null ? null : (
        <div className="soundset-error" role="alert">
          <p>{state.lastError.message}</p>
          {soundSetReasonCopy(state.lastError) === null
            ? null
            : <p>{soundSetReasonCopy(state.lastError)}</p>}
          <button
            type="button"
            onClick={() => dispatch({type: "error-dismissed"})}
          >
            Dismiss
          </button>
        </div>
      )}

      <ul className="soundset-list" aria-label="Catalog Sound Sets">
        {state.sets.map((summary) => (
          <li key={summary.manifestSha256}>
            <h3>{summary.name}</h3>
            <dl>
              <dt>Publisher</dt>
              <dd>{summary.publisher}</dd>
              <dt>Version</dt>
              <dd>{summary.version}</dd>
              <dt>Sounds</dt>
              <dd>{summary.occupiedSlots.length} of 16</dd>
              <dt>Download</dt>
              <dd>{formatSetBytes(summary.totalBytes)}</dd>
              <dt>Licence</dt>
              <dd>{summary.license.spdxId}</dd>
              {summary.license.attribution === "" ? null : (
                <>
                  <dt>Attribution</dt>
                  <dd className="soundset-attribution">
                    {summary.license.attribution}
                  </dd>
                </>
              )}
            </dl>
            <button
              type="button"
              disabled={busy}
              onClick={() => { void inspect(summary); }}
            >
              Inspect {summary.name}
            </button>
          </li>
        ))}
      </ul>

      {state.sets.length === 0 && state.catalogAvailable !== null ? (
        <p className="soundset-empty" role="status">
          No Sound Set is available in this Workspace.
        </p>
      ) : null}

      {state.refused.length === 0 ? null : (
        <ul className="soundset-refused" aria-label="Unavailable Sound Sets">
          {state.refused.map((refusal) => (
            <li key={refusal.manifestSha256}>
              {refusal.setId} {refusal.version} — {refusal.code}
              {refusal.reason === null ? "" : ` (${refusal.reason})`}
            </li>
          ))}
        </ul>
      )}

      {selected === null ? null : (
        <section className="soundset-inspect" aria-label={`Sound Set ${selected.name}`}>
          <header>
            <h3>{selected.name}</h3>
            <button type="button" onClick={() => dispatch({type: "closed"})}>
              Close
            </button>
          </header>
          <p>{selected.publisher} · {selected.license.spdxId}</p>
          {selected.license.attribution === "" ? null : (
            <p className="soundset-attribution">
              Attribution: {selected.license.attribution}
            </p>
          )}
          {/* Audition attachment point 1 of 2: the set-level demo. */}
          {selected.demo === null ? null : (
            <p className="soundset-demo">
              <button
                type="button"
                className="soundset-audition"
                onClick={() => void audition()}
              >
                Audition set demo
              </button>{" "}
              · {formatSetBytes(selected.demo.byteLength)}
            </p>
          )}

          <ol className="soundset-slots" aria-label="Sound Set slots">
            {selected.slots.map((slot) => (
              <li key={slot.slot} data-empty={slotIsEmpty(slot) ? "true" : "false"}>
                <span className="soundset-slot-index">{slot.slot + 1}</span>
                {slotIsEmpty(slot) ? (
                  // No control, no affordance: an empty Set slot is not an
                  // action the user can take on the target Pad.
                  <span className="soundset-slot-empty">Empty in this Set</span>
                ) : (
                  /* Audition attachment point 2 of 2: one occupied slot. */
                  <span className="soundset-slot-sound">
                    <button
                      type="button"
                      className="soundset-audition"
                      aria-label={`Audition ${slot.name}`}
                      onClick={() => void audition(slot.slot)}
                    >
                      {slot.name}
                    </button>{" "}
                    · {slot.role} · {slot.audio?.sampleRate} Hz ·{" "}
                    {slot.audio?.channels === 1 ? "mono" : "stereo"}
                  </span>
                )}
              </li>
            ))}
          </ol>

          <button
            type="button"
            className="soundset-audition-stop"
            onClick={() => void stopAudition()}
          >
            Stop audition
          </button>

          <div className="soundset-target">
            <h4 id="soundset-target-bank">Install into Bank</h4>
            <BankSelector
              activeBank={state.targetBank}
              onSelect={(bank) => {
                dispatch({type: "bank-selected", bank});
                onBankChange?.(bank);
              }}
            />
            <button
              type="button"
              disabled={busy || projectRevision === null}
              onClick={() => { void preview(); }}
            >
              Preview mapping into Bank {bankName(state.targetBank)}
            </button>
            {projectRevision === null ? (
              <p role="status">Open a Project to install a Sound Set.</p>
            ) : null}
          </div>

          {state.preview === null ? null : (
            <div className="soundset-preview">
              <p role="status">
                {state.preview.proposed.length} of 16 slots map into Bank{" "}
                {bankName(state.preview.bankId as Bank)};{" "}
                {collisions.length} occupied{" "}
                {collisions.length === 1 ? "Pad" : "Pads"} in the way
              </p>
              <div className="pad-grid" aria-label="Proposed Bank mapping">
                {padPlan.map((outcome) => (
                  <div
                    className="pad"
                    key={outcome.pad}
                    data-plan={outcome.plan}
                  >
                    <strong>
                      {bankName(state.preview!.bankId as Bank)}{outcome.pad + 1}
                    </strong>
                    <span>
                      {outcome.plan === "install"
                        ? "Install"
                        : outcome.plan === "collision"
                          ? "Occupied"
                          : outcome.plan === "empty-in-set"
                            ? "Empty in Set — Pad unchanged"
                            : "Not in this mapping"}
                    </span>
                  </div>
                ))}
              </div>

              {collisions.length === 0 ? null : (
                <fieldset className="soundset-policy">
                  <legend>Occupied Pads</legend>
                  {(["keep", "replace"] as const).map((policy) => (
                    <label key={policy}>
                      <input
                        type="radio"
                        name="soundset-occupied-pad-policy"
                        value={policy}
                        checked={state.policy === policy}
                        onChange={() =>
                          dispatch({
                            type: "policy-selected",
                            policy: policy as OccupiedPadPolicy,
                          })}
                      />
                      {policy === "keep"
                        ? "Keep the Pads I already have"
                        : "Replace them with this Set"}
                    </label>
                  ))}
                </fieldset>
              )}

              <button
                type="button"
                disabled={!selectCanInstall(state) || projectRevision === null}
                onClick={() => { void install(); }}
              >
                {selectWriteCount(state) === null
                  ? `Install into Bank ${bankName(state.preview.bankId as Bank)}`
                  : `Install ${selectWriteCount(state)} of 16 into Bank ${
                    bankName(state.preview.bankId as Bank)}`}
              </button>
            </div>
          )}

          {state.receipt === null ? null : (
            <p className="soundset-receipt" role="status">
              Installed {state.receipt.installed.length}{" "}
              {state.receipt.installed.length === 1 ? "Pad" : "Pads"} into Bank{" "}
              {bankName(state.receipt.bankId as Bank)} at revision{" "}
              {state.receipt.committedRevision}
            </p>
          )}
        </section>
      )}
    </section>
  );
}
