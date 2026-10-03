import {saveDefaultSeed, type DefaultSeed, type SeedStorage} from "../state/default_seed";
import type {CreatorSlotSoundSetRuntimeSession, ProjectView, SnapshotPublication} from "./runtime_types";
export interface SeedCommit {
  committedRevision: number;
  runtimeRevision: number | null;
  published: boolean;
}
export function createDefaultSeedController(options: {
  seed: DefaultSeed;
  storage: SeedStorage;
  session: CreatorSlotSoundSetRuntimeSession;
  current: () => ProjectView | null;
  commit: (slot: number, request: {commandId: string; expectedRevision: number},
    admit: () => boolean) => Promise<SeedCommit | null>;
  refresh: () => Promise<void>;
  changed: (seed: DefaultSeed) => void;
  failed?: (slot: number, error: unknown) => void;
  uuid?: () => string;
  pause?: () => Promise<void>;
}) {
  const seed = options.seed;
  let cancelled = false;
  const running = new Set<number>();
  const owns = () => !cancelled && options.current()?.projectId === seed.projectId;
  const persist = () => {saveDefaultSeed(options.storage, seed); options.changed(structuredClone(seed));};
  const identity = {setId: seed.setId, version: seed.version, manifestSha256: seed.manifestSha256};
  async function acquire(slot: number) {
    if (!owns() || running.has(slot)) return;
    const state = seed.slots[slot]!;
    const retired = () => state.phase === "retired";
    if (!["pending", "loading", "processing", "failed"].includes(state.phase)) return;
    running.add(slot);
    try {
      if (state.request === null && options.current()!.pads.some(pad => pad.slot === slot && pad.assetId !== null)) {
        state.phase = "retired"; persist(); return;
      }
      state.phase = "loading"; persist();
      await options.session.acquireSoundSetSlot({...identity, slotIndex: slot});
      if (!owns() || seed.slots[slot]!.phase === "retired") return;
      state.phase = "processing"; persist();
      // Only short authoring/publication work crosses the Project serial lane.
      for (let attempt = 0; attempt < 4 && owns(); attempt++) {
        if (retired()) return;
        const request = state.request ?? {commandId: options.uuid?.() ?? crypto.randomUUID(),
          expectedRevision: options.current()!.revision};
        try {
          const result = await options.commit(slot, request, () => {
            // The Host calls this only after acquiring its authoring token,
            // immediately before the Facade command. A queued candidate does
            // not own a receipt or the Pad while another edit is in flight.
            if (!owns() || retired()) return false;
            if (state.request === null) {
              if (options.current()!.pads.some(pad => pad.slot === slot && pad.assetId !== null)) {
                state.phase = "retired"; persist(); return false;
              }
              state.request = request;
              state.assignmentObserved = false;
              try {persist();} // Replay identity survives a lost commit response.
              catch (error) {state.request = null; throw error;}
            }
            return true;
          });
          if (result === null) {
            if (!owns() || retired()) return;
            attempt--;
            await (options.pause?.() ?? new Promise<void>(resolve => setTimeout(resolve, 100)));
            continue;
          }
          state.committedRevision = result.committedRevision;
          state.phase = result.published && result.runtimeRevision !== null &&
            result.runtimeRevision >= result.committedRevision ? "ready" : "saved-unavailable";
          persist();
          if (result.published && result.runtimeRevision !== null) {
            for (const prior of seed.slots) if (prior.phase === "saved-unavailable" &&
              prior.committedRevision !== null && prior.committedRevision <= result.runtimeRevision) prior.phase = "ready";
            persist();
          }
          return;
        } catch (error) {
          const code = (error as {code?: string}).code;
          if (code !== "REVISION_CONFLICT") throw error;
          await options.refresh();
          if (!owns() || retired()) return;
          // Missing history in an older journal cannot prove that no user
          // assignment preceded Undo. Only a newly admitted, unobserved
          // request may rebase; a known receipt never enters this refusal.
          if (state.assignmentObserved !== false ||
              options.current()!.pads.some(pad => pad.slot === slot && pad.assetId !== null)) {
            state.phase = "retired"; persist(); return;
          }
          if (state.request !== null) {
            state.request.expectedRevision = options.current()!.revision;
            persist();
          }
        }
      }
      if (owns()) {state.phase = "failed"; persist();}
    } catch (error) {
      if (owns() && seed.slots[slot]!.phase !== "retired") {
        options.failed?.(slot, error);
        state.phase = (error as {details?: {reason?: string}}).details?.reason === "soundset_occupied_conflict"
          ? "retired" : "failed";
        persist();
      }
    } finally {running.delete(slot);}
  }
  return {
    async start() {
      let next = 0;
      await Promise.all(Array.from({length: 4}, async () => {
        while (next < 16 && owns()) await acquire(next++);
      }));
    },
    retry: acquire,
    observeProject(project: ProjectView) {
      if (!owns() || project.projectId !== seed.projectId) return;
      let changed = false;
      for (const pad of project.pads) {
        if (pad.slot >= 16 || pad.assetId === null) continue;
        const slot = seed.slots[pad.slot]!;
        // A known request may replay its receipt after a lost response. If
        // Native refuses it as stale, an assignment seen before Undo forbids
        // rebasing an unknown command into a new automatic installation.
        if (slot.committedRevision === null && !["ready", "retired"].includes(slot.phase) &&
            (slot.request === null || !slot.assignmentObserved)) {
          if (slot.request === null) slot.phase = "retired";
          else slot.assignmentObserved = true;
          changed = true;
        }
      }
      if (changed) persist();
    },
    acceptPublication(publication: SnapshotPublication) {
      if (!owns() || publication.projectId !== seed.projectId || !publication.runtimeReady ||
          publication.snapshotError !== null || publication.runtimeRevision === null) return;
      for (const slot of seed.slots) if (slot.phase === "saved-unavailable" && slot.committedRevision !== null &&
        slot.committedRevision <= publication.runtimeRevision) slot.phase = "ready";
      persist();
    },
    cancel() {cancelled = true;},
  };
}
