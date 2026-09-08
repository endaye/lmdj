import type {
  Bank,
} from "./creator_state";
import type {
  OccupiedPadPolicy,
  SoundSetCatalog,
  SoundSetInspect,
  SoundSetInstallReceipt,
  SoundSetMapPreview,
  SoundSetRefusal,
  SoundSetSummary,
} from "../runtime/runtime_types";

export type SoundSetPhase =
  | "idle"
  | "listing"
  | "browsing"
  | "inspecting"
  | "previewing"
  | "installing";

export interface SoundSetError {
  code: string;
  reason: string | null;
  message: string;
}

export interface SoundSetState {
  phase: SoundSetPhase;
  // `null` until a listing has answered: "not asked yet" is not "unreachable".
  catalogAvailable: boolean | null;
  sets: readonly Readonly<SoundSetSummary>[];
  refused: readonly Readonly<SoundSetRefusal>[];
  selected: Readonly<SoundSetInspect> | null;
  targetBank: Bank;
  preview: Readonly<SoundSetMapPreview> | null;
  // #465 Q2: there is no default. A Bank with collisions cannot be installed
  // until the user has chosen `keep` or `replace`.
  policy: OccupiedPadPolicy | null;
  receipt: Readonly<SoundSetInstallReceipt> | null;
  lastError: SoundSetError | null;
}

export const initialSoundSetState: SoundSetState = {
  phase: "idle",
  catalogAvailable: null,
  sets: [],
  refused: [],
  selected: null,
  targetBank: 0,
  preview: null,
  policy: null,
  receipt: null,
  lastError: null,
};

export type SoundSetAction =
  | {type: "listing"}
  | {type: "listed"; catalog: Readonly<SoundSetCatalog>}
  | {type: "inspecting"}
  | {type: "inspected"; inspect: Readonly<SoundSetInspect>}
  | {type: "closed"}
  | {type: "bank-selected"; bank: Bank}
  | {type: "previewing"}
  | {type: "previewed"; preview: Readonly<SoundSetMapPreview>}
  | {type: "policy-selected"; policy: OccupiedPadPolicy}
  | {type: "installing"}
  | {type: "installed"; receipt: Readonly<SoundSetInstallReceipt>}
  | {type: "failed"; error: SoundSetError}
  | {type: "error-dismissed"};

// A preview is a statement about one Set on one Bank at one revision. Anything
// that changes which of those three a request would carry drops it, so no
// confirmation can be submitted against a mapping the user never saw.
function withoutPreview(state: SoundSetState): SoundSetState {
  return {...state, preview: null, policy: null, receipt: null};
}

export function reduceSoundSet(
  state: SoundSetState,
  action: SoundSetAction,
): SoundSetState {
  switch (action.type) {
    case "listing":
      return {...state, phase: "listing", lastError: null};
    case "listed":
      return {
        ...state,
        phase: "browsing",
        catalogAvailable: action.catalog.catalogAvailable,
        sets: action.catalog.sets,
        refused: action.catalog.refused,
      };
    case "inspecting":
      return {...withoutPreview(state), phase: "inspecting", lastError: null};
    case "inspected":
      return {
        ...withoutPreview(state),
        phase: "browsing",
        selected: action.inspect,
      };
    case "closed":
      return {...withoutPreview(state), phase: "browsing", selected: null};
    case "bank-selected":
      return {...withoutPreview(state), targetBank: action.bank};
    case "previewing":
      return {...state, phase: "previewing", lastError: null};
    case "previewed":
      return {
        ...state,
        phase: "browsing",
        preview: action.preview,
        // A fresh mapping is a fresh decision: a policy chosen against an
        // earlier collision set never carries over.
        policy: null,
        receipt: null,
      };
    case "policy-selected":
      return {...state, policy: action.policy};
    case "installing":
      return {...state, phase: "installing", lastError: null};
    case "installed":
      return {
        ...state,
        phase: "browsing",
        receipt: action.receipt,
        // The Bank has changed underneath the mapping the user confirmed.
        preview: null,
        policy: null,
      };
    case "failed":
      return {...state, phase: "browsing", lastError: action.error};
    case "error-dismissed":
      return {...state, lastError: null};
  }
}

export function selectBusy(state: SoundSetState): boolean {
  return state.phase === "listing" || state.phase === "inspecting" ||
    state.phase === "previewing" || state.phase === "installing";
}

// #465 Q2 and S11-D12 together: a mapping with no collision installs on the
// user's confirmation alone, and a mapping with collisions cannot be submitted
// until `keep` or `replace` has been chosen.
export function selectCanInstall(state: SoundSetState): boolean {
  if (state.preview === null || selectBusy(state)) {
    return false;
  }
  if (state.preview.collisions.length === 0) {
    return true;
  }
  return state.policy !== null;
}

// The three things one Pad can be under a mapping. `map_soundset` reports every
// empty Set slot in `kept`, so "the Set has nothing for this Pad" and "this Pad
// is untouched" are one fact — which is exactly S11-D12, and is why this
// surface never offers an empty slot as an action. The buckets are read from
// the mapping rather than re-derived from `proposed`, so a Pad Core did not
// classify shows as unknown instead of being quietly presented as untouched.
export type SoundSetPadPlan =
  | "install"
  | "collision"
  | "empty-in-set"
  | "unclassified";

export interface SoundSetPadOutcome {
  pad: number;
  plan: SoundSetPadPlan;
}

export function selectPadPlan(
  state: SoundSetState,
): readonly Readonly<SoundSetPadOutcome>[] {
  const preview = state.preview;
  if (preview === null) {
    return [];
  }
  const outcomes: SoundSetPadOutcome[] = [];
  for (let pad = 0; pad < 16; ++pad) {
    if (preview.collisions.includes(pad)) {
      outcomes.push({pad, plan: "collision"});
    } else if (preview.proposed.some((proposed) => proposed.pad === pad)) {
      outcomes.push({pad, plan: "install"});
    } else {
      outcomes.push({
        pad,
        plan: preview.kept.includes(pad) ? "empty-in-set" : "unclassified",
      });
    }
  }
  return outcomes;
}

// What a confirmed install would actually write, given the chosen policy, or
// `null` while a collision is still undecided — announcing the `replace` count
// under a policy the user has not chosen would pre-empt exactly the decision
// #465 Q2 requires them to make.
export function selectWriteCount(state: SoundSetState): number | null {
  const preview = state.preview;
  if (preview === null) {
    return 0;
  }
  if (preview.collisions.length > 0 && state.policy === null) {
    return null;
  }
  if (state.policy === "keep") {
    return preview.proposed.filter(
      (proposed) => !preview.collisions.includes(proposed.pad)).length;
  }
  return preview.proposed.length;
}
