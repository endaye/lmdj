import type {
  LocalProjectSummary,
  ProjectPadView,
  ProjectView,
  SampleCommit,
  SampleInspect,
} from "../runtime/runtime_types";
import {
  initialSampleState,
  preparedSampleState,
  reduceSampleState,
  type SamplePendingAction,
  type SampleStateAction,
  type SampleState,
} from "./sample_state";

export type SampleProjectionRefresh =
  | Readonly<{
      type: "mutation-committed";
      pending: Readonly<SamplePendingAction>;
      inspect: Readonly<SampleInspect> | null;
      commit: Readonly<SampleCommit>;
    }>
  | Readonly<{
      type: "mutation-conflicted";
      pending: Readonly<SamplePendingAction>;
      inspect: Readonly<SampleInspect>;
    }>;

export type {
  LocalProjectSummary,
  ProjectPadView,
  ProjectView,
} from "../runtime/runtime_types";

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
  | "recovering"
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
    errorDetails?: Readonly<Record<string, unknown>>;
  };
  audio: {
    phase: "inactive" | "activating" | "recovering" | "running" | "suspended";
  };
  transfer: {
    phase: "idle" | "importing";
    completedBytes: number;
    totalBytes: number;
  };
  activeBank: Bank;
  pressed: ReadonlyMap<number, PressOutcome>;
  sample: SampleState;
  sampleProjectionRefresh: SampleProjectionRefresh | null;
}

export type CreatorAction =
  | {
      type: "runtime-changed";
      phase: CreatorState["runtime"]["phase"];
      errorCode: string | null;
      errorDetails?: Readonly<Record<string, unknown>>;
    }
  | {type: "projects-listing"}
  | {type: "projects-loaded"; projects: LocalProjectSummary[]}
  | {type: "project-opening"}
  | {type: "project-ready"; project: ProjectView}
  | {
      type: "project-error";
      errorCode: string;
      errorDetails?: Readonly<Record<string, unknown>>;
    }
  | {type: "transfer-started"; totalBytes: number}
  | {type: "transfer-progressed"; completedBytes: number}
  | {type: "transfer-ended"}
  | {type: "audio-changed"; phase: CreatorState["audio"]["phase"]}
  | {type: "bank-selected"; bank: Bank}
  | {type: "pad-pressed"; slot: number; outcome: PressOutcome}
  | {type: "pad-released"; slot: number}
  | {type: "sample-action"; action: SampleStateAction}
  | {type: "sample-projection-refresh-started"; action: SampleProjectionRefresh}
  | {
      type: "sample-project-refreshed";
      project: ProjectView;
      action: SampleProjectionRefresh;
    }
  | {type: "sample-projection-refresh-failed"; errorCode: string}
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
    errorDetails: {},
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
  sample: initialSampleState,
  sampleProjectionRefresh: null,
};

function hasReadyProject(state: CreatorState): boolean {
  return state.project.phase === "ready" && state.project.current !== null;
}

export function isCreatorActionAllowed(
  state: CreatorState,
  action: CreatorAction,
): boolean {
  switch (action.type) {
    case "runtime-changed":
      return true;
    case "projects-listing":
      return state.runtime.phase === "ready" &&
        state.transfer.phase === "idle" &&
        state.project.phase !== "opening";
    case "projects-loaded":
      return state.runtime.phase === "ready" && state.project.phase === "listing";
    case "project-opening":
      return state.runtime.phase === "ready" &&
        state.transfer.phase === "idle" &&
        ["empty", "ready", "error"].includes(state.project.phase);
    case "project-ready":
      return state.runtime.phase === "ready" &&
        (state.project.phase === "opening" || state.transfer.phase === "importing");
    case "project-error":
      return state.runtime.phase === "ready" && (
        state.project.phase === "listing" ||
        state.project.phase === "opening" ||
        state.transfer.phase === "importing" ||
        state.audio.phase === "activating"
      );
    case "transfer-started":
      return selectCanImportProject(state) &&
        Number.isSafeInteger(action.totalBytes) && action.totalBytes >= 0;
    case "transfer-progressed":
      return state.transfer.phase === "importing" &&
        Number.isSafeInteger(action.completedBytes) &&
        action.completedBytes >= state.transfer.completedBytes &&
        action.completedBytes <= state.transfer.totalBytes;
    case "transfer-ended":
      return state.transfer.phase === "importing";
    case "audio-changed":
      if (action.phase === "inactive") {
        return state.audio.phase !== "inactive";
      }
      if (action.phase === "activating") {
        return selectCanActivateAudio(state);
      }
      if (action.phase === "recovering") {
        return state.runtime.phase === "ready" && hasReadyProject(state) &&
          state.transfer.phase === "idle" && state.audio.phase === "suspended";
      }
      if (action.phase === "running") {
        return state.runtime.phase === "ready" && hasReadyProject(state) &&
          state.transfer.phase === "idle" &&
          ["inactive", "activating", "recovering", "suspended"]
            .includes(state.audio.phase);
      }
      return state.runtime.phase === "ready" && hasReadyProject(state) &&
        state.transfer.phase === "idle" &&
        ["activating", "recovering", "running"].includes(state.audio.phase);
    case "bank-selected":
      return state.runtime.phase === "ready" && hasReadyProject(state) &&
        state.transfer.phase === "idle";
    case "pad-pressed": {
      if (!selectCanTrigger(state)) return false;
      const firstSlot = state.activeBank * 16;
      if (
        action.slot < firstSlot ||
        action.slot >= firstSlot + 16 ||
        state.project.current?.pads[action.slot]?.assetId == null
      ) {
        return false;
      }
      const current = state.pressed.get(action.slot);
      return action.outcome === "admitted"
        ? current === undefined
        : current === "admitted";
    }
    case "pad-released":
      return state.pressed.has(action.slot);
    case "sample-action":
      return true;
    case "sample-projection-refresh-started":
    case "sample-project-refreshed":
    case "sample-projection-refresh-failed":
      return true;
    case "pressed-cleared":
      return true;
  }
}

function samePendingMutation(
  left: SampleProjectionRefresh,
  right: SampleProjectionRefresh,
): boolean {
  return left.type === right.type && left.pending.kind === right.pending.kind &&
    left.pending.slot === right.pending.slot &&
    left.pending.expectedRevision === right.pending.expectedRevision &&
    (left.type !== "mutation-committed" ||
      (right.type === "mutation-committed" && left.commit === right.commit));
}

export function creatorReducer(
  state: CreatorState,
  action: CreatorAction,
): CreatorState {
  if (!isCreatorActionAllowed(state, action)) return state;
  switch (action.type) {
    case "runtime-changed":
      return {
        ...state,
        runtime: {
          phase: action.phase,
          errorCode: action.errorCode,
          errorDetails: action.errorDetails ?? {},
        },
      };
    case "projects-listing":
      return {
        ...state,
        project: {...state.project, phase: "listing"},
        runtime: {...state.runtime, errorCode: null, errorDetails: {}},
      };
    case "projects-loaded":
      return {
        ...state,
        project: {
          phase: action.projects.length === 0 ? "empty" : "ready",
          projects: [...action.projects],
          current: state.project.current,
        },
        runtime: {...state.runtime, errorCode: null, errorDetails: {}},
      };
    case "project-opening":
      return {
        ...state,
        project: {...state.project, phase: "opening"},
        runtime: {...state.runtime, errorCode: null, errorDetails: {}},
      };
    case "project-ready":
      return {
        ...state,
        project: {...state.project, phase: "ready", current: action.project},
        runtime: {...state.runtime, errorCode: null, errorDetails: {}},
        audio: {phase: "inactive"},
        sample: preparedSampleState(action.project.revision),
        sampleProjectionRefresh: null,
      };
    case "project-error":
      return {
        ...state,
        project: {...state.project, phase: "error"},
        runtime: {
          ...state.runtime,
          errorCode: action.errorCode,
          errorDetails: action.errorDetails ?? {},
        },
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
    case "sample-action": {
      if (action.action.type === "inspect-stored") {
        const currentProject = state.project.current;
        const inspected = action.action.inspect;
        const inspectedRevision = inspected !== null &&
            typeof inspected === "object" &&
            Object.hasOwn(inspected, "projectRevision") &&
            Number.isSafeInteger((inspected as {projectRevision?: unknown}).projectRevision)
          ? (inspected as {projectRevision: number}).projectRevision
          : null;
        if ((currentProject === null && state.project.phase === "error") ||
          (inspectedRevision !== null &&
            currentProject !== null &&
            inspectedRevision !== currentProject.revision)) {
          return state;
        }
      }
      if (action.action.type === "waveform-stored") {
        const current = state.sample.inspect;
        const viewport = state.sample.viewport;
        const request = action.action.request;
        const envelope = action.action.envelope;
        const envelopeRevision = envelope !== null &&
            typeof envelope === "object" &&
            Object.hasOwn(envelope, "projectRevision") &&
            Number.isSafeInteger((envelope as {projectRevision?: unknown}).projectRevision)
          ? (envelope as {projectRevision: number}).projectRevision
          : null;
        if (current === null || viewport === null ||
          request.slot !== current.slot ||
          request.waveformCacheIdentity !== current.waveformCacheIdentity ||
          request.window.startFrame !== viewport.startFrame ||
          request.window.endFrame !== viewport.endFrame ||
          (envelopeRevision !== null &&
            envelopeRevision !== current.projectRevision)) {
          return state;
        }
      }
      return {...state, sample: reduceSampleState(state.sample, action.action)};
    }
    case "sample-projection-refresh-started": {
      if (state.sampleProjectionRefresh !== null) {
        throw new TypeError("Sample Project refresh is already active");
      }
      if (action.action.type === "mutation-committed" &&
        action.action.inspect === null) {
        const pending = state.sample.pendingAction;
        if (pending === null || pending.kind !== action.action.pending.kind ||
          pending.slot !== action.action.pending.slot ||
          pending.expectedRevision !== action.action.pending.expectedRevision ||
          action.action.commit.committedRevision !== pending.expectedRevision + 1) {
          throw new TypeError("Sample Project refresh identity does not match");
        }
      } else {
        reduceSampleState(state.sample, action.action);
      }
      return {
        ...state,
        sampleProjectionRefresh: Object.freeze({...action.action}),
      };
    }
    case "sample-project-refreshed": {
      const current = state.project.current;
      const refresh = state.sampleProjectionRefresh;
      if (current === null ||
        refresh === null || !samePendingMutation(refresh, action.action) ||
        (action.action.type === "mutation-committed" &&
          action.action.inspect === null) ||
        current.projectId !== action.project.projectId ||
        current.patternId !== action.project.patternId) {
        throw new TypeError("Sample Project refresh identity does not match");
      }
      const sample = reduceSampleState(state.sample, action.action);
      if (sample.savedRevision !== action.project.revision ||
        (sample.inspect !== null &&
          sample.inspect.projectRevision !== action.project.revision)) {
        throw new TypeError("Sample Project refresh revision does not match");
      }
      const summary: LocalProjectSummary = {
        projectId: action.project.projectId,
        patternId: action.project.patternId,
        revision: action.project.revision,
        bpm: action.project.bpm,
        assetCount: action.project.assetCount,
        assignedPadCount: action.project.assignedPadCount,
        bundleDigest: action.project.bundleDigest,
      };
      let replaced = false;
      const projects = state.project.projects.map((project) => {
        if (project.projectId !== summary.projectId ||
          project.patternId !== summary.patternId) return project;
        replaced = true;
        return summary;
      });
      if (!replaced) projects.push(summary);
      return {
        ...state,
        project: {
          phase: "ready",
          projects,
          current: action.project,
        },
        sample,
        sampleProjectionRefresh: null,
      };
    }
    case "sample-projection-refresh-failed": {
      const refresh = state.sampleProjectionRefresh;
      if (refresh === null || action.errorCode.length === 0) {
        throw new TypeError("Sample Project refresh failure is invalid");
      }
      const cancelled = reduceSampleState(state.sample, {
        type: "operation-cancelled",
        pending: refresh.pending,
      });
      const committed = refresh.type === "mutation-committed";
      return {
        ...state,
        project: {phase: "error", projects: [], current: null},
        runtime: {...state.runtime, errorCode: action.errorCode},
        pressed: new Map(),
        sample: Object.freeze({
          ...cancelled,
          inspect: null,
          waveform: null,
          viewport: null,
          draft: null,
          auditionPlayback: null,
          voices: Object.freeze([]),
          playhead: null,
          savedRevision: null,
          runtimeRevision: committed ? refresh.commit.runtimeRevision : null,
          lastError: Object.freeze({
            code: action.errorCode,
            message: committed
              ? "Sample was saved, but current Project truth could not be refreshed"
              : "Project changed, but current Project truth could not be refreshed",
            retryPrepare: false,
          }),
        }),
        sampleProjectionRefresh: null,
      };
    }
    case "pressed-cleared":
      return state.pressed.size === 0 ? state : {...state, pressed: new Map()};
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
  if (state.audio.phase === "recovering") return "recovering";
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

function selectCanChangeProject(state: CreatorState): boolean {
  return state.runtime.phase === "ready" &&
    (state.project.phase === "empty" ||
      state.project.phase === "ready" ||
      state.project.phase === "error") &&
    state.transfer.phase === "idle" &&
    (state.audio.phase === "inactive" || state.audio.phase === "suspended");
}

export function selectCanOpenProject(state: CreatorState): boolean {
  return selectCanChangeProject(state);
}

export function selectCanImportProject(state: CreatorState): boolean {
  return selectCanChangeProject(state);
}

export function selectCanTrigger(state: CreatorState): boolean {
  return state.runtime.phase === "ready" &&
    state.project.phase === "ready" &&
    state.project.current !== null &&
    state.transfer.phase === "idle" &&
    (state.audio.phase === "running" || state.audio.phase === "recovering");
}
