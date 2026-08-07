export interface LocalProjectSummary {
  projectId: string;
  patternId: string;
  revision: number;
  bpm: number;
  assetCount: number;
  assignedPadCount: number;
  bundleDigest: string;
}

export interface ProjectPadView {
  slot: number;
  assetId: string | null;
}

export interface ProjectView extends LocalProjectSummary {
  key: "—";
  pads: readonly ProjectPadView[];
}

export type CreatorPhase =
  | "failed"
  | "closed"
  | "restart-required"
  | "unsupported"
  | "booting"
  | "importing"
  | "opening"
  | "empty"
  | "activating"
  | "running"
  | "suspended"
  | "ready";

export type Bank = 0 | 1 | 2 | 3;
export type PressOutcome = "admitted" | "started" | "capacity";

export interface CreatorState {
  project: {
    phase: "listing" | "empty" | "opening" | "ready" | "error";
    projects: LocalProjectSummary[];
    current: ProjectView | null;
  };
  runtime: {
    phase:
      | "booting"
      | "unsupported"
      | "ready"
      | "restart-required"
      | "failed"
      | "closed";
    errorCode: string | null;
  };
  audio: {
    phase: "inactive" | "activating" | "running" | "suspended";
  };
  transfer: {
    phase: "idle" | "importing";
    completedBytes: number;
    totalBytes: number;
  };
  activeBank: Bank;
  pressed: ReadonlyMap<number, PressOutcome>;
}

export type CreatorAction =
  | {
      type: "runtime-changed";
      phase: CreatorState["runtime"]["phase"];
      errorCode: string | null;
    }
  | {type: "projects-loaded"; projects: LocalProjectSummary[]}
  | {type: "project-opening"}
  | {type: "project-ready"; project: ProjectView}
  | {type: "project-error"}
  | {type: "transfer-started"; totalBytes: number}
  | {type: "transfer-progressed"; completedBytes: number}
  | {type: "transfer-ended"}
  | {type: "audio-changed"; phase: CreatorState["audio"]["phase"]}
  | {type: "bank-selected"; bank: Bank}
  | {type: "pad-pressed"; slot: number; outcome: PressOutcome}
  | {type: "pad-released"; slot: number}
  | {type: "pressed-cleared"};

export const initialCreatorState: CreatorState = {
  project: {
    phase: "listing",
    projects: [],
    current: null,
  },
  runtime: {
    phase: "booting",
    errorCode: null,
  },
  audio: {
    phase: "inactive",
  },
  transfer: {
    phase: "idle",
    completedBytes: 0,
    totalBytes: 0,
  },
  activeBank: 0,
  pressed: new Map(),
};

export function creatorReducer(
  state: CreatorState,
  action: CreatorAction,
): CreatorState {
  switch (action.type) {
    case "runtime-changed":
      return {
        ...state,
        runtime: {phase: action.phase, errorCode: action.errorCode},
      };
    case "projects-loaded":
      return {
        ...state,
        project: {
          phase: action.projects.length === 0 ? "empty" : "ready",
          projects: [...action.projects],
          current: state.project.current,
        },
      };
    case "project-opening":
      return {
        ...state,
        project: {...state.project, phase: "opening"},
      };
    case "project-ready":
      return {
        ...state,
        project: {...state.project, phase: "ready", current: action.project},
        audio: {phase: "inactive"},
      };
    case "project-error":
      return {
        ...state,
        project: {...state.project, phase: "error"},
      };
    case "transfer-started":
      return {
        ...state,
        transfer: {
          phase: "importing",
          completedBytes: 0,
          totalBytes: action.totalBytes,
        },
      };
    case "transfer-progressed":
      return {
        ...state,
        transfer: {...state.transfer, completedBytes: action.completedBytes},
      };
    case "transfer-ended":
      return {
        ...state,
        transfer: {phase: "idle", completedBytes: 0, totalBytes: 0},
      };
    case "audio-changed":
      return {...state, audio: {phase: action.phase}};
    case "bank-selected":
      return {...state, activeBank: action.bank, pressed: new Map()};
    case "pad-pressed": {
      const pressed = new Map(state.pressed);
      pressed.set(action.slot, action.outcome);
      return {...state, pressed};
    }
    case "pad-released": {
      const pressed = new Map(state.pressed);
      pressed.delete(action.slot);
      return {...state, pressed};
    }
    case "pressed-cleared":
      return {...state, pressed: new Map()};
  }
}

export function selectCreatorPhase(state: CreatorState): CreatorPhase {
  if (state.runtime.phase === "failed" || state.project.phase === "error") {
    return "failed";
  }
  if (state.runtime.phase === "closed") return "closed";
  if (state.runtime.phase === "restart-required") return "restart-required";
  if (state.runtime.phase === "unsupported") return "unsupported";
  if (state.runtime.phase === "booting" || state.project.phase === "listing") {
    return "booting";
  }
  if (state.transfer.phase === "importing") return "importing";
  if (state.project.phase === "opening") return "opening";
  if (state.project.phase === "empty") return "empty";
  if (state.audio.phase === "activating") return "activating";
  if (state.audio.phase === "running") return "running";
  if (state.audio.phase === "suspended") return "suspended";
  return "ready";
}

export function selectVisiblePads(
  state: CreatorState,
): readonly ProjectPadView[] {
  const firstSlot = state.activeBank * 16;
  const source = new Map(
    state.project.current?.pads.map((pad) => [pad.slot, pad]) ?? [],
  );
  return Object.freeze(Array.from({length: 16}, (_, index) => {
    const slot = firstSlot + index;
    return source.get(slot) ?? {slot, assetId: null};
  }));
}

export function selectCanActivateAudio(state: CreatorState): boolean {
  return state.runtime.phase === "ready" &&
    state.project.phase === "ready" &&
    state.project.current !== null &&
    state.transfer.phase === "idle" &&
    (state.audio.phase === "inactive" || state.audio.phase === "suspended");
}

export function selectCanTrigger(state: CreatorState): boolean {
  return state.runtime.phase === "ready" &&
    state.project.phase === "ready" &&
    state.project.current !== null &&
    state.transfer.phase === "idle" &&
    state.audio.phase === "running";
}
