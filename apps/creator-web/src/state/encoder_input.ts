// One encoder turn over a committed value. Each detent previews at once; the
// turn commits once, after it has rested for idleMs, so one turn is one
// Authoring commit and one undo entry. A turn that ends where it started
// commits nothing. The 400 ms rest is the Desktop Final plan's proposed rule
// (T6), pending owner confirmation.
export const ENCODER_IDLE_COMMIT_MS = 400;

export interface EncoderTurnOptions {
  min: number;
  max: number;
  idleMs?: number;
  schedule(callback: () => void, delayMs: number): unknown;
  clear(handle: unknown): void;
  onPreview(value: number | null): void;
  onCommit(value: number): void;
}

export interface EncoderTurn {
  // Adds detents to the turn. A new turn starts from the last value this
  // encoder asked to commit until `committed` (Truth) catches up with it, so
  // a turn begun while the previous commit is still in flight continues from
  // that commit instead of the stale committed value.
  turn(detents: number, committed: number): void;
  // Drops the turn without committing, as when recording locks the value.
  cancel(): void;
  // Forgets the in-flight request after a failed commit, so the next turn
  // starts from the committed value again.
  forget(): void;
}

export function createEncoderTurn(options: EncoderTurnOptions): EncoderTurn {
  const idleMs = options.idleMs ?? ENCODER_IDLE_COMMIT_MS;
  let current: {base: number; value: number} | null = null;
  let requested: number | null = null;
  let timer: unknown = null;
  const clearTimer = () => {
    if (timer !== null) options.clear(timer);
    timer = null;
  };
  return {
    turn(detents, committed) {
      if (!Number.isFinite(detents) || detents === 0) return;
      if (requested !== null && requested === committed) requested = null;
      if (current === null) {
        const start = requested ?? committed;
        current = {base: start, value: start};
      }
      current.value = Math.min(options.max, Math.max(options.min, current.value + Math.trunc(detents)));
      options.onPreview(current.value);
      clearTimer();
      timer = options.schedule(() => {
        timer = null;
        const settled = current;
        current = null;
        options.onPreview(null);
        if (settled !== null && settled.value !== settled.base) {
          requested = settled.value;
          options.onCommit(settled.value);
        }
      }, idleMs);
    },
    forget() {
      requested = null;
    },
    cancel() {
      clearTimer();
      if (current !== null) {
        current = null;
        options.onPreview(null);
      }
    },
  };
}
