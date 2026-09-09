import {describe, expect, test} from "vitest";

import {
  creatorReducer,
  initialCreatorState,
  isCreatorActionAllowed,
  selectCanActivateAudio,
  selectCanTrigger,
  selectCreatorPhase,
  selectVisiblePads,
  type CreatorState,
  type CreatorAction,
  type ProjectView,
} from "../src/state/creator_state";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 4,
  bpm: 120,
  assetCount: 2,
  assignedPadCount: 2,
  bundleDigest: "a".repeat(64),
  key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({
    slot,
    assetId: slot === 0 || slot === 32 ? `asset-${slot}` : null,
  })),
  patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 1}],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

function readyState(): CreatorState {
  return {
    ...initialCreatorState,
    project: {phase: "ready", projects: [], current: project},
    runtime: {phase: "ready", errorCode: null},
  };
}

describe("Creator state", () => {
  test("Candidate commit invalidates playable audio until its revision is published", () => {
    const before = {...readyState(), sample: {...initialCreatorState.sample,
      savedRevision: 4, runtimeRevision: 4}};
    const stale = creatorReducer(before, {type: "candidate-audio-invalidated",
      projectId: project.projectId, revision: 5});
    expect(stale.project).toBe(before.project);
    expect(stale.sample.savedRevision).toBe(5);
    expect(stale.sample.runtimeRevision).toBe(4);
    const refreshed = creatorReducer(stale, {type: "project-revision-updated", revision: 5});
    const ready = creatorReducer(refreshed, {type: "candidate-audio-published",
      projectId: project.projectId, revision: 5, runtimeRevision: 5});
    expect(ready.sample.savedRevision).toBe(ready.sample.runtimeRevision);
  });

  test("Candidate preparation failure retains the known older Runtime revision", () => {
    const state = {...readyState(), project: {...readyState().project,
      current: {...project, revision: 5}}, sample: {...initialCreatorState.sample,
      savedRevision: 5, runtimeRevision: 4}};
    const failed = creatorReducer(state, {type: "candidate-audio-published",
      projectId: project.projectId, revision: 5, runtimeRevision: 4});
    expect(failed.project).toBe(state.project);
    expect(failed.sample.savedRevision).toBe(5);
    expect(failed.sample.runtimeRevision).toBe(4);
  });

  test.each([
    {projectId: "other", revision: 5, runtimeRevision: 5},
    {projectId: project.projectId, revision: 4, runtimeRevision: 4},
    {projectId: project.projectId, revision: 5, runtimeRevision: 6},
  ])("rejects stale or foreign Candidate publication %j", (publication) => {
    const state = {...readyState(), project: {...readyState().project,
      current: {...project, revision: 5}}, sample: {...initialCreatorState.sample,
      savedRevision: 5, runtimeRevision: 4}};
    expect(isCreatorActionAllowed(state, {type: "candidate-audio-published", ...publication})).toBe(false);
  });

  test("derives the exact orthogonal phase priority", () => {
    expect(selectCreatorPhase(initialCreatorState)).toBe("booting");
    expect(selectCreatorPhase({
      ...readyState(),
      project: {phase: "empty", projects: [], current: null},
    })).toBe("empty");
    expect(selectCreatorPhase({
      ...readyState(),
      transfer: {phase: "importing", completedBytes: 4, totalBytes: 8},
      audio: {phase: "running"},
    })).toBe("importing");
    expect(selectCreatorPhase({
      ...readyState(),
      project: {...readyState().project, phase: "opening"},
      audio: {phase: "running"},
    })).toBe("opening");
    expect(selectCreatorPhase(readyState())).toBe("ready");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "activating"},
    })).toBe("activating");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "running"},
    })).toBe("running");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "suspended"},
    })).toBe("suspended");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "unsupported", errorCode: "UNSUPPORTED_WEB_RUNTIME"},
    })).toBe("unsupported");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "restart-required", errorCode: "HOST_RESTART_REQUIRED"},
    })).toBe("restart-required");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "closed", errorCode: null},
    })).toBe("closed");
    expect(selectCreatorPhase({
      ...readyState(), project: {...readyState().project, phase: "error"},
    })).toBe("failed");
  });

  test("selects one stable Bank and keeps pressed state immutable", () => {
    const bankC = creatorReducer(readyState(), {
      type: "bank-selected", bank: 2,
    });
    expect(selectVisiblePads(bankC).map(({slot}) => slot)).toEqual(
      Array.from({length: 16}, (_, index) => 32 + index),
    );
    const running = {
      ...bankC,
      audio: {phase: "running"} as const,
    };
    const pressed = creatorReducer(running, {
      type: "pad-pressed", slot: 32, outcome: "admitted",
    });
    expect(running.pressed.has(32)).toBe(false);
    expect(pressed.pressed.get(32)).toBe("admitted");
    const released = creatorReducer(pressed, {type: "pad-released", slot: 32});
    expect(released.pressed.has(32)).toBe(false);
  });

  test("gates activation and Trigger from authoritative substate", () => {
    const ready = readyState();
    expect(selectCanActivateAudio(ready)).toBe(true);
    expect(selectCanTrigger(ready)).toBe(false);
    const running = {...ready, audio: {phase: "running"} as const};
    expect(selectCanActivateAudio(running)).toBe(false);
    expect(selectCanTrigger(running)).toBe(true);
    expect(selectCanTrigger({
      ...running,
      transfer: {phase: "importing", completedBytes: 0, totalBytes: 1},
    })).toBe(false);
  });

  test("atomically replaces the complete Project projection without resetting audio", () => {
    const current = {
      ...readyState(),
      audio: {phase: "running"} as const,
      project: {
        phase: "ready" as const,
        projects: [{
          projectId: project.projectId,
          patternId: project.patternId,
          revision: project.revision,
          bpm: project.bpm,
          assetCount: project.assetCount,
          assignedPadCount: project.assignedPadCount,
          bundleDigest: project.bundleDigest,
        }],
        current: project,
      },
    };
    const patternId = "33333333-3333-4333-8333-333333333333";
    const refreshed: ProjectView = {
      ...project,
      revision: 5,
      patternSlots: Object.freeze([
        patternId,
        ...Array<string | null>(15).fill(null),
      ]),
      patterns: [...project.patterns, {patternId, bars: 4}],
    };

    const token = Object.freeze({
      id: "refresh-1",
      projectId: project.projectId,
      patternId: project.patternId,
      baseRevision: project.revision,
    });
    const refreshing = creatorReducer(current, {
      type: "project-projection-refresh-started",
      token,
    });
    const next = creatorReducer(refreshing, {
      type: "project-projection-refreshed",
      project: refreshed,
      token,
    });

    expect(next.project.current).toBe(refreshed);
    expect(next.project.projects).toContainEqual(expect.objectContaining({revision: 5}));
    expect(next.audio.phase).toBe("running");
    expect(next.sample).toBe(current.sample);
    expect(next.projectProjectionRefresh).toBeNull();
  });

  test("drops stale Project truth when a projection refresh fails", () => {
    const current = {
      ...readyState(),
      audio: {phase: "running"} as const,
      pressed: new Map([[0, "started" as const]]),
    };
    const token = Object.freeze({
      id: "refresh-2",
      projectId: project.projectId,
      patternId: project.patternId,
      baseRevision: project.revision,
    });
    const refreshing = creatorReducer(current, {
      type: "project-projection-refresh-started",
      token,
    });
    const next = creatorReducer(refreshing, {
      type: "project-projection-refresh-failed",
      errorCode: "HOST_PROTOCOL_MISMATCH",
      token,
    });

    expect(next.project).toEqual({phase: "error", projects: [], current: null});
    expect(next.pressed.size).toBe(0);
    expect(selectCanTrigger(next)).toBe(false);
  });

  test("ignores a stale projection refresh after Project or Runtime ownership changes", () => {
    const token = Object.freeze({
      id: "refresh-stale",
      projectId: project.projectId,
      patternId: project.patternId,
      baseRevision: project.revision,
    });
    const refreshing = creatorReducer(readyState(), {
      type: "project-projection-refresh-started",
      token,
    });
    const nextProject = {...project, projectId: "44444444-4444-4444-8444-444444444444"};
    const opening = {...refreshing, project: {...refreshing.project, phase: "opening" as const}};
    const replaced = creatorReducer(opening, {type: "project-ready", project: nextProject});

    expect(creatorReducer(replaced, {
      type: "project-projection-refresh-failed",
      errorCode: "HOST_PROTOCOL_MISMATCH",
      token,
    })).toBe(replaced);

    const terminal = creatorReducer(refreshing, {
      type: "runtime-changed",
      phase: "closed",
      errorCode: null,
    });
    expect(creatorReducer(terminal, {
      type: "project-projection-refreshed",
      project: {...project, revision: project.revision + 1},
      token,
    })).toBe(terminal);
  });

  test("restores a failed activation only while the attempt still owns the phase", () => {
    const activating = creatorReducer(readyState(), {
      type: "audio-changed",
      phase: "activating",
    });
    const restored = creatorReducer(activating, {
      type: "audio-activation-restored",
      phase: "suspended",
    });
    expect(restored.audio.phase).toBe("suspended");

    const published = creatorReducer(activating, {
      type: "audio-changed",
      phase: "running",
    });
    expect(creatorReducer(published, {
      type: "audio-activation-restored",
      phase: "suspended",
    })).toBe(published);
  });

  test.each<[string, CreatorState, CreatorAction]>([
    ["list while Runtime is booting", initialCreatorState, {type: "projects-listing"}],
    ["load before listing", readyState(), {type: "projects-loaded", projects: []}],
    ["open while listing", {
      ...readyState(), project: {...readyState().project, phase: "listing"},
    }, {type: "project-opening"}],
    ["publish Project before open or import", readyState(), {
      type: "project-ready", project,
    }],
    ["report Project error while idle", readyState(), {
      type: "project-error", errorCode: "IO_ERROR",
    }],
    ["start transfer while audio runs", {
      ...readyState(), audio: {phase: "running"},
    }, {type: "transfer-started", totalBytes: 8}],
    ["progress outside transfer", readyState(), {
      type: "transfer-progressed", completedBytes: 4,
    }],
    ["end absent transfer", readyState(), {type: "transfer-ended"}],
    ["activate without Project", {
      ...readyState(), project: {phase: "empty", projects: [], current: null},
    }, {type: "audio-changed", phase: "activating"}],
    ["recover without suspend", readyState(), {
      type: "audio-changed", phase: "recovering",
    }],
    ["select Bank while importing", {
      ...readyState(),
      transfer: {phase: "importing", completedBytes: 0, totalBytes: 8},
    }, {type: "bank-selected", bank: 1}],
    ["press while audio is inactive", readyState(), {
      type: "pad-pressed", slot: 0, outcome: "admitted",
    }],
    ["release a Pad that is not pressed", readyState(), {
      type: "pad-released", slot: 0,
    }],
  ])("rejects illegal %s from the reducer boundary", (_name, state, action) => {
    expect(isCreatorActionAllowed(state, action)).toBe(false);
    expect(creatorReducer(state, action)).toBe(state);
  });

  test("keeps lifecycle cleanup legal after the Runtime becomes terminal", () => {
    const state: CreatorState = {
      ...readyState(),
      runtime: {phase: "restart-required", errorCode: "HOST_TIMEOUT"},
      transfer: {phase: "importing", completedBytes: 4, totalBytes: 8},
      pressed: new Map([[0, "admitted"]]),
    };
    const cleared = creatorReducer(state, {type: "pressed-cleared"});
    expect(cleared.pressed.size).toBe(0);
    const ended = creatorReducer(cleared, {type: "transfer-ended"});
    expect(ended.transfer.phase).toBe("idle");
  });

  test.each([
    {
      name: "initial nonpublished commit",
      currentRevision: 5,
      runtimeRevision: 4,
      runtimePublished: false,
      snapshotError: {code: "COOK_FAILED", message: "Cook failed", details: {}},
    },
    {
      name: "published delayed replay",
      currentRevision: 7,
      runtimeRevision: 7,
      runtimePublished: true,
      snapshotError: null,
    },
    {
      name: "nonpublished delayed replay",
      currentRevision: 7,
      runtimeRevision: 4,
      runtimePublished: false,
      snapshotError: {code: "COOK_FAILED", message: "Cook failed", details: {}},
    },
  ] as const)("atomically refreshes Project truth after $name", ({
    currentRevision,
    runtimeRevision,
    runtimePublished,
    snapshotError,
  }) => {
    const assetId = "33333333-3333-4333-8333-333333333333";
    const replayAssetId = "44444444-4444-4444-8444-444444444444";
    const before = creatorReducer(creatorReducer(creatorReducer({
      ...readyState(),
      project: {
        ...readyState().project,
        projects: [{
          projectId: project.projectId,
          patternId: project.patternId,
          revision: project.revision,
          bpm: project.bpm,
          assetCount: project.assetCount,
          assignedPadCount: project.assignedPadCount,
          bundleDigest: project.bundleDigest,
        }],
      },
      audio: {phase: "running"},
    }, {
      type: "sample-action",
      action: {type: "slot-selected", slot: 1},
    }), {
      type: "sample-action",
      action: {
        type: "inspect-stored",
        inspect: {
          projectRevision: 4,
          slot: 1,
          assetId: null,
          playback: {
            trimStartFrame: 0,
            trimEndFrame: null,
            triggerMode: "one_shot",
            gainMillidb: 0,
            muted: false,
          },
          metadata: null,
          waveformCacheIdentity: null,
        },
      },
    }), {
      type: "sample-action",
      action: {
        type: "pending-began",
        pending: {kind: "import", slot: 1, expectedRevision: 4},
      },
    });
    const refreshedProject: ProjectView = {
      ...project,
      revision: currentRevision,
      assetCount: currentRevision === 5 ? 3 : 4,
      assignedPadCount: currentRevision === 5 ? 3 : 4,
      bundleDigest: (currentRevision === 5 ? "b" : "c").repeat(64),
      pads: project.pads.map((pad) => {
        if (pad.slot === 1) return {...pad, assetId};
        if (currentRevision > 5 && pad.slot === 2) {
          return {...pad, assetId: replayAssetId};
        }
        return pad;
      }),
    };

    const refreshAction = {
      type: "mutation-committed" as const,
      pending: {kind: "import" as const, slot: 1, expectedRevision: 4},
      inspect: {
        projectRevision: currentRevision,
        slot: 1,
        assetId,
        playback: {
          trimStartFrame: 0,
          trimEndFrame: 8,
          triggerMode: "gate" as const,
          gainMillidb: 0,
          muted: false,
        },
        metadata: {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 8},
        waveformCacheIdentity: `${"b".repeat(64)}/1/max-abs-mirror/1`,
      },
      commit: {
        committedRevision: 5,
        runtimeRevision,
        runtimePublished,
        snapshotError,
      },
    };
    const refreshing = creatorReducer(before, {
      type: "sample-projection-refresh-started",
      action: refreshAction,
    });
    const after = creatorReducer(refreshing, {
      type: "sample-project-refreshed",
      project: refreshedProject,
      action: refreshAction,
    });

    expect(after.project.current).toEqual(refreshedProject);
    expect(after.project.projects).toEqual([{
      projectId: refreshedProject.projectId,
      patternId: refreshedProject.patternId,
      revision: currentRevision,
      bpm: refreshedProject.bpm,
      assetCount: refreshedProject.assetCount,
      assignedPadCount: refreshedProject.assignedPadCount,
      bundleDigest: refreshedProject.bundleDigest,
    }]);
    expect(after.sample.selectedSlot).toBe(1);
    expect(after.sample.inspect?.assetId).toBe(assetId);
    expect(after.sample.savedRevision).toBe(currentRevision);
    expect(after.sample.runtimeRevision).toBe(runtimeRevision);
    expect(after.sample.pendingAction).toBeNull();
    expect(after.sample.lastError).toEqual(snapshotError === null ? null : {
      code: "COOK_FAILED",
      message: "Sample runtime preparation failed",
      retryPrepare: true,
    });
    expect(after.audio).toBe(before.audio);
    expect(after.runtime).toBe(before.runtime);
  });

  test("retains a committed mutation while its authoritative inspect is pending", () => {
    const pending = {kind: "update" as const, slot: 1, expectedRevision: 4};
    const selected = creatorReducer(creatorReducer(creatorReducer({
      ...readyState(),
      audio: {phase: "running"},
    }, {
      type: "sample-action",
      action: {type: "slot-selected", slot: 1},
    }), {
      type: "sample-action",
      action: {
        type: "inspect-stored",
        inspect: {
          projectRevision: 4,
          slot: 1,
          assetId: null,
          playback: {
            trimStartFrame: 0,
            trimEndFrame: null,
            triggerMode: "one_shot",
            gainMillidb: 0,
            muted: false,
          },
          metadata: null,
          waveformCacheIdentity: null,
        },
      },
    }), {
      type: "sample-action",
      action: {type: "pending-began", pending},
    });
    const commit = {
      committedRevision: 5,
      runtimeRevision: 5,
      runtimePublished: true,
      snapshotError: null,
    };
    const unresolved = {
      type: "mutation-committed" as const,
      pending,
      inspect: null,
      commit,
    };

    const refreshing = creatorReducer(selected, {
      type: "sample-projection-refresh-started",
      action: unresolved,
    });
    expect(refreshing.sample.pendingAction).toEqual(pending);
    expect(refreshing.sampleProjectionRefresh).toEqual(unresolved);

    const inspect = {
      projectRevision: 5,
      slot: 1,
      assetId: null,
      playback: {
        trimStartFrame: 0,
        trimEndFrame: null,
        triggerMode: "gate" as const,
        gainMillidb: 0,
        muted: false,
      },
      metadata: null,
      waveformCacheIdentity: null,
    };
    const refreshedProject = {
      ...project,
      revision: 5,
      bundleDigest: "d".repeat(64),
    };
    const resolved = {...unresolved, inspect};
    const after = creatorReducer(refreshing, {
      type: "sample-project-refreshed",
      project: refreshedProject,
      action: resolved,
    });
    expect(after.sample.savedRevision).toBe(5);
    expect(after.sample.pendingAction).toBeNull();
    expect(after.sampleProjectionRefresh).toBeNull();
    expect(after.audio).toBe(selected.audio);
  });
});
