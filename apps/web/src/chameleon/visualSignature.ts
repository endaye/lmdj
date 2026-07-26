import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";

function hash(value: string): number {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return result >>> 0;
}

export function createVisualSignature(
  publicSeed: string,
  state: ChameleonVisualState,
): ChameleonVisualSignature {
  const seed = hash(`${publicSeed}:${state.phase}`);
  const accent =
    state.tone === "danger"
      ? "danger"
      : state.tone === "success"
        ? "success"
        : state.phase === "playing" && state.playbackRole
          ? state.playbackRole
          : "neutral";
  return {
    seed,
    angle: (seed % 361) / 10 - 18,
    offset: ((seed >>> 8) % 61) - 30,
    density: 2 + ((seed >>> 16) % 4),
    accent,
  };
}
