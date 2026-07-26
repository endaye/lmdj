import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";
import { Chameleon2D } from "./Chameleon2D";

const PHASE_GLYPH = {
  idle: "·",
  "drag-ready": "↓",
  uploading: "↑",
  queued: "Q",
  separating: "S",
  extracting: "E",
  patchifying: "P",
  ready: "✓",
  playing: "▶",
  error: "!",
} as const;

export function ChameleonSurface({
  state,
  signature,
  onActivate,
  onToggle,
  onDismiss,
}: {
  state: ChameleonVisualState;
  signature: ChameleonVisualSignature;
  onActivate: () => void;
  onToggle: () => void;
  onDismiss: () => void;
}) {
  if (state.placement === "stage") {
    return (
      <button
        type="button"
        className="chameleon-stage-trigger"
        data-testid="chameleon-stage-trigger"
        aria-label="Choose a WAV or MP3 to make a Patch"
        onClick={onActivate}
      >
        <Chameleon2D
          state={state}
          signature={signature}
          sharedTransition
        />
        <span className="chameleon-stage-trigger__label">
          <strong>
            {state.phase === "drag-ready" ? "DROP WAV OR MP3" : "DROP A TRACK"}
          </strong>
          <span>WAV / MP3 · click or drag</span>
        </span>
      </button>
    );
  }

  const expanded = state.placement === "floating";
  return (
    <div
      className={`chameleon-assistant${expanded ? " chameleon-assistant--expanded" : ""}`}
      data-testid="chameleon-assistant"
      data-phase={state.phase}
    >
      <button
        type="button"
        className="chameleon-dock"
        aria-label={`Chameleon assistant · ${state.label}`}
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <Chameleon2D
          state={state}
          signature={signature}
          compact
          sharedTransition
        />
        <span
          className="chameleon-dock__state"
          data-testid="chameleon-dock-state"
          aria-hidden="true"
        >
          {PHASE_GLYPH[state.phase]}
        </span>
        <span className="chameleon-dock__label">{state.label}</span>
      </button>
      {expanded && (
        <section
          className="chameleon-floating"
          data-testid="chameleon-floating"
          role={state.phase === "error" ? "alert" : "status"}
          aria-live={state.phase === "error" ? "assertive" : "polite"}
        >
          <button
            type="button"
            className="chameleon-floating__close"
            aria-label="Close assistant"
            onClick={onDismiss}
          >
            ×
          </button>
          <Chameleon2D state={state} signature={signature} />
          <strong>{state.label}</strong>
        </section>
      )}
    </div>
  );
}
