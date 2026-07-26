import { useState, type CSSProperties } from "react";
import chameleonImage from "../assets/chameleon-line-logo-approved-v1.png";
import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";

export function Chameleon2D({
  state,
  signature,
  compact = false,
  sharedTransition = false,
}: {
  state: ChameleonVisualState;
  signature: ChameleonVisualSignature;
  compact?: boolean;
  sharedTransition?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const style = {
    "--chameleon-angle": `${signature.angle}deg`,
    "--chameleon-angle-negative": `${-signature.angle}deg`,
    "--chameleon-offset": `${signature.offset}px`,
    "--chameleon-density": signature.density,
    "--chameleon-step": `${12 * signature.density}px`,
  } as CSSProperties;
  return (
    <span
      className={[
        "chameleon-2d",
        compact ? "chameleon-2d--compact" : "",
        sharedTransition ? "chameleon-2d--shared" : "",
      ].filter(Boolean).join(" ")}
      data-testid="chameleon-2d"
      data-phase={state.phase}
      data-tone={state.tone}
      data-motion={state.motion}
      data-accent={signature.accent}
      style={style}
      aria-hidden="true"
    >
      <span className="chameleon-2d__pattern" />
      {!failed && (
        <img
          src={chameleonImage}
          alt=""
          draggable={false}
          onError={() => setFailed(true)}
        />
      )}
      {failed && (
        <span
          className="chameleon-2d__fallback"
          data-testid="chameleon-fallback"
        >
          CH
        </span>
      )}
    </span>
  );
}
