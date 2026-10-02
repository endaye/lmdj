import type {SoundSetIdentity} from "../runtime/runtime_types";
export const DEFAULT_SEED_KEY = "lmdj.creator.default-seed.v1";
export type SeedPhase = "pending" | "loading" | "processing" | "ready" | "failed" | "saved-unavailable" | "retired";
export interface SeedSlot {
  phase: SeedPhase;
  request: {commandId: string; expectedRevision: number} | null;
  committedRevision: number | null;
}
export interface DefaultSeed extends SoundSetIdentity {
  projectId: string;
  slots: SeedSlot[];
}
export interface SeedStorage {getItem(key: string): string | null; setItem(key: string, value: string): void;}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PHASES = new Set<SeedPhase>(["pending", "loading", "processing", "ready", "failed", "saved-unavailable", "retired"]);
export function readDefaultSeed(storage: SeedStorage, identity: SoundSetIdentity): DefaultSeed | null {
  const raw = storage.getItem(DEFAULT_SEED_KEY);
  if (raw === null) return null;
  const seed = JSON.parse(raw) as DefaultSeed;
  if (seed === null || seed.setId !== identity.setId || seed.version !== identity.version ||
      seed.manifestSha256 !== identity.manifestSha256 || !UUID.test(seed.projectId) ||
      !Array.isArray(seed.slots) || seed.slots.length !== 16 || seed.slots.some(slot =>
        slot === null || !PHASES.has(slot.phase) ||
        (slot.committedRevision !== null && (!Number.isSafeInteger(slot.committedRevision) || slot.committedRevision < 0)) ||
        (slot.request !== null && (!UUID.test(slot.request.commandId) ||
          !Number.isSafeInteger(slot.request.expectedRevision) || slot.request.expectedRevision < 0)))) {
    throw new Error("Default seed journal is invalid; existing content is preserved");
  }
  return seed;
}
export function saveDefaultSeed(storage: SeedStorage, seed: DefaultSeed): void {
  storage.setItem(DEFAULT_SEED_KEY, JSON.stringify(seed));
}
export function claimDefaultSeed(storage: SeedStorage, identity: SoundSetIdentity, projectId: string): DefaultSeed | null {
  if (readDefaultSeed(storage, identity) !== null) return null;
  if (!UUID.test(projectId)) throw new Error("Default seed Project identity is invalid");
  const seed: DefaultSeed = {...identity, projectId,
    slots: Array.from({length: 16}, () => ({phase: "pending", request: null, committedRevision: null}))};
  saveDefaultSeed(storage, seed);
  return seed;
}
