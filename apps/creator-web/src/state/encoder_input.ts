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
  // Adds detents to the turn; `committed` is the value a new turn starts from.
  turn(detents: number, committed: number): void;
  // Drops the turn without committing, as when recording locks the value.
  cancel(): void;
}

export function createEncoderTurn(options: EncoderTurnOptions): EncoderTurn {
  const idleMs = options.idleMs ?? ENCODER_IDLE_COMMIT_MS;
  let current: {base: number; value: number} | null = null;
  let timer: unknown = null;
  const clearTimer = () => {
    if (timer !== null) options.clear(timer);
    timer = null;
  };
  return {
    turn(detents, committed) {
      if (!Number.isFinite(detents) || detents === 0) return;
      current ??= {base: committed, value: committed};
      current.value = Math.min(options.max, Math.max(options.min, current.value + Math.trunc(detents)));
      options.onPreview(current.value);
      clearTimer();
      timer = options.schedule(() => {
        timer = null;
        const settled = current;
        current = null;
        options.onPreview(null);
        if (settled !== null && settled.value !== settled.base) options.onCommit(settled.value);
      }, idleMs);
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
