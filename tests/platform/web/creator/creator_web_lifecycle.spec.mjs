import {readFile} from "node:fs/promises";

import {expect, test} from "@playwright/test";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
const MAX_OPEN_ATTEMPTS = 8;
const BUSY_RETRY_INTERVAL_MS = 500;
// openProjectJourney owns three independently bounded 30-second Project
// operations: open, inspect, and snapshot reload. The UI hang detector covers
// their 90-second protocol ceiling plus bounded runner/render settling time.
const OPEN_TRANSITION_TIMEOUT_MS = 3 * 30_000 + 35_000;
// Every audio lifecycle gesture owns one independently bounded 30-second
// Runtime request, so the state that follows an accepted gesture is promised
// only within that bound plus bounded render settling. Playwright's 5-second
// default is tighter than anything the product guarantees.
const AUDIO_TRANSITION_TIMEOUT_MS = 30_000 + 5_000;

async function projectOpenOutcome(heading, open, retry) {
  if (await heading.isVisible()) return "ready";
  if (await retry.isVisible()) return "busy";
  if (await open.isVisible() && await open.isEnabled()) return "open";
  return "pending";
}

async function waitForProjectOpenOutcome(heading, open, retry) {
  let outcome = "pending";
  await expect.poll(async () => {
    outcome = await projectOpenOutcome(heading, open, retry);
    return outcome;
  }, {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("pending");
  return outcome;
}

async function waitForOpenActionTransition(heading, open, retry) {
  await expect.poll(async () =>
    await projectOpenOutcome(heading, open, retry),
  {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("open");
}

async function waitForProjectInventory(page) {
  const open = page.getByRole("button", {name: "Open Project 00000000"});
  const retry = page.getByRole("button", {name: "Retry project"});
  const alert = page.getByRole("alert");
  for (let attempt = 0; attempt < MAX_OPEN_ATTEMPTS; attempt += 1) {
    await expect.poll(async () =>
      await open.isVisible() ? "open" : await retry.isVisible() ? "retry" : "",
    {timeout: OPEN_TRANSITION_TIMEOUT_MS}).not.toBe("");
    if (await open.isVisible()) return open;
    await expect(alert).toContainText(
      "The local Project is busy in another tab or process.",
    );
    await retry.click();
  }
  await expect(open).toBeVisible();
  return open;
}

async function installPackagedRecoveryProbe(page) {
  await page.addInitScript(() => {
    let currentGeneration = 0;
    let suppressNextOutcome = false;
    const generations = new Map();
    const boundaries = [];
    const runtimeHistory = [];
    const suppressedOutcomes = [];

    const generationRecord = (generation) => {
      let record = generations.get(generation);
      if (!record) {
        record = {
          audioContexts: new Set(),
          broadcastChannels: new Set(),
          midiListeners: new Set(),
          windowLifecycleListeners: new Set(),
        };
        generations.set(generation, record);
      }
      return record;
    };
    const counts = () => {
      const result = {};
      const activeGenerations = [];
      for (const [generation, record] of generations) {
        result[generation] = {
          audio_contexts: record.audioContexts.size,
          broadcast_channels: record.broadcastChannels.size,
          midi_listeners: record.midiListeners.size,
          window_lifecycle_listeners: record.windowLifecycleListeners.size,
        };
        if (Object.values(result[generation]).some((value) => value > 0)) {
          activeGenerations.push(generation);
        }
      }
      return {
        active_generations: activeGenerations.sort((left, right) => left - right),
        created_generations: currentGeneration,
        generations: result,
      };
    };

    const nativeWindowAdd = window.addEventListener.bind(window);
    const nativeWindowRemove = window.removeEventListener.bind(window);
    const lifecycleTypes = new Set(["blur", "pagehide", "pageshow"]);
    const lifecycleEntries = [];
    window.addEventListener = (type, listener, options) => {
      if (lifecycleTypes.has(type)) {
        const capture = typeof options === "boolean"
          ? options
          : options?.capture === true;
        const duplicate = lifecycleEntries.some((entry) =>
          entry.active && entry.type === type && entry.listener === listener &&
          entry.capture === capture);
        if (!duplicate) {
          const entry = {
            active: true,
            capture,
            generation: currentGeneration,
            listener,
            type,
          };
          lifecycleEntries.push(entry);
          generationRecord(currentGeneration).windowLifecycleListeners.add(entry);
        }
      }
      return nativeWindowAdd(type, listener, options);
    };
    window.removeEventListener = (type, listener, options) => {
      const capture = typeof options === "boolean"
        ? options
        : options?.capture === true;
      const entry = lifecycleEntries.find((candidate) =>
        candidate.active && candidate.type === type &&
        candidate.listener === listener && candidate.capture === capture);
      if (entry) {
        entry.active = false;
        generationRecord(entry.generation).windowLifecycleListeners.delete(entry);
      }
      return nativeWindowRemove(type, listener, options);
    };

    const NativeBroadcastChannel = window.BroadcastChannel;
    const broadcastOwners = new WeakMap();
    const nativeBroadcastClose = NativeBroadcastChannel.prototype.close;
    NativeBroadcastChannel.prototype.close = function close() {
      const owner = broadcastOwners.get(this);
      if (owner !== undefined) {
        generationRecord(owner).broadcastChannels.delete(this);
        broadcastOwners.delete(this);
      }
      return nativeBroadcastClose.call(this);
    };
    window.BroadcastChannel = new Proxy(NativeBroadcastChannel, {
      construct(target, argumentsList) {
        const channel = Reflect.construct(target, argumentsList, target);
        broadcastOwners.set(channel, currentGeneration);
        generationRecord(currentGeneration).broadcastChannels.add(channel);
        return channel;
      },
    });

    const NativeAudioContext = window.AudioContext;
    const audioOwners = new WeakMap();
    const nativeAudioClose = NativeAudioContext.prototype.close;
    NativeAudioContext.prototype.close = async function close() {
      const result = await nativeAudioClose.call(this);
      const owner = audioOwners.get(this);
      if (owner !== undefined) {
        generationRecord(owner).audioContexts.delete(this);
        audioOwners.delete(this);
      }
      return result;
    };
    window.AudioContext = new Proxy(NativeAudioContext, {
      construct(target, argumentsList) {
        const context = Reflect.construct(target, argumentsList, target);
        audioOwners.set(context, currentGeneration);
        generationRecord(currentGeneration).audioContexts.add(context);
        return context;
      },
    });

    const trackMidiTarget = (target, acceptedTypes) => {
      const nativeAdd = target.addEventListener.bind(target);
      const nativeRemove = target.removeEventListener.bind(target);
      const entries = [];
      target.addEventListener = (type, listener, options) => {
        if (acceptedTypes.has(type)) {
          const entry = {generation: currentGeneration, listener, type};
          entries.push(entry);
          generationRecord(currentGeneration).midiListeners.add(entry);
        }
        return nativeAdd(type, listener, options);
      };
      target.removeEventListener = (type, listener, options) => {
        const index = entries.findIndex((entry) =>
          entry.type === type && entry.listener === listener);
        if (index >= 0) {
          const [entry] = entries.splice(index, 1);
          generationRecord(entry.generation).midiListeners.delete(entry);
        }
        return nativeRemove(type, listener, options);
      };
      return target;
    };
    const midiInput = trackMidiTarget(new EventTarget(), new Set(["midimessage"]));
    Object.defineProperties(midiInput, {
      state: {value: "connected"},
      type: {value: "input"},
    });
    const midiAccess = trackMidiTarget(new EventTarget(), new Set(["statechange"]));
    Object.defineProperty(midiAccess, "inputs", {
      value: new Map([["synthetic", midiInput]]),
    });
    Object.defineProperty(navigator, "requestMIDIAccess", {
      configurable: true,
      value: async () => midiAccess,
    });

    const runtimeTransport = () => {
      const transport = window.lmdjWebRuntimeHost?.transport;
      if (!transport) throw new Error("packaged Runtime transport is unavailable");
      return transport;
    };
    const transport = Object.freeze({
      send(...arguments_) {
        return runtimeTransport().send(...arguments_);
      },
      subscribe(listener) {
        return runtimeTransport().subscribe((notification) => {
          if (
            suppressNextOutcome &&
            notification?.event === "runtime.trigger_outcomes"
          ) {
            suppressNextOutcome = false;
            suppressedOutcomes.push({
              generation: currentGeneration,
              sequences: notification.payload?.events?.map(({sequence}) => sequence) ?? [],
            });
            return;
          }
          listener(notification);
        });
      },
      subscribeFailure(listener) {
        return runtimeTransport().subscribeFailure(listener);
      },
    });

    Object.defineProperty(window, "__LMDJ_WEB_HOST_SEAMS__", {
      configurable: false,
      get() {
        boundaries.push({generation: currentGeneration + 1, before: counts()});
        currentGeneration += 1;
        generationRecord(currentGeneration);
        return {
          transport,
          onDiagnostics(value) {
            const last = runtimeHistory.at(-1);
            const next = {
              error_code: value.error_code,
              generation: currentGeneration,
              state: value.state,
            };
            if (
              last?.error_code !== next.error_code ||
              last?.generation !== next.generation ||
              last?.state !== next.state
            ) {
              runtimeHistory.push(next);
            }
          },
        };
      },
    });
    window.__creatorRuntimeProbe = Object.freeze({
      armOutcomeSuppression() {
        suppressNextOutcome = true;
      },
      snapshot() {
        return {
          ...counts(),
          boundaries: structuredClone(boundaries),
          runtime_history: structuredClone(runtimeHistory),
          suppressed_outcomes: structuredClone(suppressedOutcomes),
        };
      },
    });
  });
}

async function importAndActivate(page) {
  await expect(page.getByTestId("creator-phase")).toHaveText("empty", {
    timeout: 30_000,
  });
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function report(page) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export report"}).click();
  return JSON.parse(await readFile(await (await pending).path(), "utf8"));
}

// A synthetic lifecycle edge never suspends the AudioContext, so the Runtime
// keeps the recovery epoch it opened, re-enters `recovering` on its own and
// asks only for the one probe Trigger; the Host never parks at
// `audio-suspended` and therefore never needs an Activate gesture here. The
// Runtime accepts an Activate gesture only while parked at `audio-suspended`,
// and the Creator disables "Activate audio" in every other Host state, so the
// surface never offers a gesture that is guaranteed to be refused. "Audio
// suspended" is published as soon as the Host reaches `interrupted`, which is
// where the interruption starts; wait for the guaranteed recovery instead.
async function recoverFromLifecycleEdge(page) {
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function enterLoopToggleSample(page) {
  await page.getByRole("button", {name: "Sample"}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  await expect(page.getByText(/^Asset /)).toBeVisible({timeout: 30_000});
  const loop = page.getByRole("button", {name: "Loop"});
  if (await loop.getAttribute("aria-pressed") !== "true") {
    await loop.click();
    await expect(loop).toHaveAttribute("aria-pressed", "true", {timeout: 30_000});
  }
  const hold = page.getByRole("button", {name: "Hold"});
  await expect(hold).toBeEnabled();
  if (await hold.getAttribute("aria-pressed") !== "true") {
    await hold.click();
  }
  await expect(hold).toHaveAttribute("aria-pressed", "true", {timeout: 30_000});
}

async function armPadOutcomeObservation(pad) {
  await pad.evaluate((element) => {
    element.removeAttribute("data-proof-outcome-observed");
    const observeOutcome = () => {
      const outcome = element.getAttribute("data-outcome");
      if (outcome !== null && outcome !== "idle") {
        element.setAttribute("data-proof-outcome-observed", outcome);
        return true;
      }
      return false;
    };
    if (observeOutcome()) return;
    const observer = new MutationObserver((records) => {
      const observed = records.some((record) =>
        record.oldValue !== null && record.oldValue !== "idle"
      );
      if (observed || observeOutcome()) {
        element.setAttribute("data-proof-outcome-observed", "true");
        observer.disconnect();
      }
    });
    observer.observe(element, {
      attributes: true,
      attributeFilter: ["data-outcome"],
      attributeOldValue: true,
    });
  });
}

async function latchLoopToggle(page) {
  await expect(page.getByRole("button", {name: "Loop"}))
    .toHaveAttribute("aria-pressed", "true", {timeout: 30_000});
  const pad = page.getByRole("button", {name: "Pad A1 — assigned"});
  await expect(pad).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
  await pad.focus();
  await page.keyboard.down("Enter");
  await expect(pad).toHaveAttribute("data-outcome", "started", {timeout: 30_000});
  await page.keyboard.up("Enter");
}

async function reopenWithVisibleBusyRetry(page) {
  const heading = page.getByRole("heading", {name: "Project 00000000"});
  const open = page.getByRole("button", {
    name: "Open Project 00000000",
  });
  const alert = page.getByRole("alert");
  const retry = page.getByRole("button", {name: "Retry project"});
  let actionKind = "open";
  let action = open;
  for (let attempt = 0; attempt < MAX_OPEN_ATTEMPTS; attempt += 1) {
    await action.click();
    if (actionKind === "open") {
      await waitForOpenActionTransition(heading, open, retry);
    }
    const outcome = await waitForProjectOpenOutcome(heading, open, retry);
    if (outcome === "ready") break;
    if (outcome === "busy") {
      await expect(alert).toContainText(
        "The local Project is busy in another tab or process.",
      );
      // A reload can briefly overlap the previous document's asynchronous
      // writer release. Model a deliberate user retry instead of hammering the
      // visible action fast enough to exhaust the bounded attempt budget.
      await page.waitForTimeout(BUSY_RETRY_INTERVAL_MS);
      actionKind = "busy";
      action = retry;
    } else {
      // A timed-out request may be followed by the one allowed automatic
      // Runtime replacement. The replacement intentionally requires another
      // explicit Open gesture instead of silently resuming the Project.
      actionKind = "open";
      action = open;
    }
  }
  await expect(heading).toBeVisible();
  await expect(alert).toHaveCount(0);
}

test("suspend, restart, and reopen clear an active loop toggle before reactivation", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(360_000);
  await page.goto("/index.html");
  await importAndActivate(page);
  await enterLoopToggleSample(page);
  await latchLoopToggle(page);
  await page.getByRole("button", {name: "Suspend audio"}).click();
  // An explicit Suspend publishes "Audio suspended" only after the Runtime has
  // committed the suspend, so the Host is already parked and the Activate
  // gesture that follows is guaranteed to be accepted.
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await latchLoopToggle(page);

  await page.reload();
  await waitForProjectInventory(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await reopenWithVisibleBusyRetry(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await enterLoopToggleSample(page);
  await latchLoopToggle(page);
  const value = await report(page);
  expect(value.state).toBe("running");
  expect(value.sample).toEqual({
    project_revision: expect.any(Number),
    runtime_revision: expect.any(Number),
    operation_outcomes: [],
    trigger_mode_coverage: [],
  });
  expect(value.sample.runtime_revision).toBe(value.sample.project_revision);
  expect(JSON.stringify(value.sample)).not.toMatch(
    /file_name|opfs|project_json|waveform_buckets|audio_bytes/i,
  );
});

test("blur and hidden lifecycle edges clear each fresh loop toggle", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importAndActivate(page);
  await enterLoopToggleSample(page);
  await latchLoopToggle(page);

  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: 30_000,
  });
  await recoverFromLifecycleEdge(page);
  await latchLoopToggle(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: 30_000,
  });
  await page.evaluate(() => {
    delete document.visibilityState;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await recoverFromLifecycleEdge(page);
  await latchLoopToggle(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
});

test("persisted page lifecycle retains the Project and live input surface", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await page.goto("/index.html");
  await importAndActivate(page);

  await page.evaluate(() => {
    window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
    window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true}));
  });

  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible();
  await expect(page.getByTestId("creator-phase")).not.toHaveText("closed");
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
    timeout: 30_000,
  });
  const pad = page.getByRole("button", {name: "Pad A1 — assigned"});
  await armPadOutcomeObservation(pad);
  await page.keyboard.down("KeyQ");
  await expect(pad).toHaveAttribute("data-proof-outcome-observed", /.+/, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
  const value = await report(page);
  expect([
    value.state,
    value.trigger_admitted_count,
    value.trigger_outcome_count,
  ]).toEqual(["running", 1, 1]);
  await page.keyboard.up("KeyQ");
});

test("packaged recovery timeout cleans one generation before automatic replacement", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installPackagedRecoveryProbe(page);
  await page.goto("/index.html");
  await importAndActivate(page);
  await page.getByRole("button", {name: "Enable MIDI"}).click();

  const initial = await page.evaluate(() => window.__creatorRuntimeProbe.snapshot());
  expect(initial.created_generations).toBe(1);
  expect(initial.active_generations).toEqual([1]);
  expect(initial.generations[1].audio_contexts).toBe(1);
  expect(initial.generations[1].broadcast_channels).toBe(1);
  expect(initial.generations[1].midi_listeners).toBe(2);
  expect(initial.generations[1].window_lifecycle_listeners).toBeGreaterThan(0);

  await page.evaluate(() => {
    window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
    window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true}));
  });
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
    timeout: 30_000,
  });
  await page.evaluate(() => window.__creatorRuntimeProbe.armOutcomeSuppression());
  await page.keyboard.press("KeyA");
  await expect.poll(() => page.evaluate(() =>
    window.__creatorRuntimeProbe.snapshot().runtime_history.some((value) =>
      value.generation === 1 && value.state === "restart-required" &&
      value.error_code === "HOST_TIMEOUT")), {timeout: 10_000}).toBe(true);
  await expect(page.getByTestId("creator-phase")).toHaveText("ready", {
    timeout: 120_000,
  });
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await page.getByRole("button", {name: "Enable MIDI"}).click();

  await expect.poll(() => page.evaluate(() =>
    window.__creatorRuntimeProbe.snapshot()), {timeout: 30_000}).toMatchObject({
    active_generations: [2],
    created_generations: 2,
    generations: {
      1: {
        audio_contexts: 0,
        broadcast_channels: 0,
        midi_listeners: 0,
        window_lifecycle_listeners: 0,
      },
      2: {
        audio_contexts: 0,
        broadcast_channels: initial.generations[1].broadcast_channels,
        midi_listeners: initial.generations[1].midi_listeners,
        window_lifecycle_listeners:
          initial.generations[1].window_lifecycle_listeners,
      },
    },
    suppressed_outcomes: [{generation: 1}],
  });
  const replaced = await page.evaluate(() => window.__creatorRuntimeProbe.snapshot());
  const secondBoundary = replaced.boundaries.find(({generation}) => generation === 2);
  // Session close owns the AudioContext and BroadcastChannel and therefore
  // must release them before the replacement factory runs. MIDI and window
  // listeners belong to Workspace's React effect: their cleanup is required
  // before the replacement becomes ready (proved by the steady-state snapshot
  // above), but is intentionally not ordered against pure factory invocation.
  expect(secondBoundary.before.generations[1].audio_contexts).toBe(0);
  expect(secondBoundary.before.generations[1].broadcast_channels).toBe(0);

  await page.getByRole("button", {name: "Activate audio"}).click();
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: 30_000,
  });
});
test.describe("synthetic Web MIDI", () => {
  test.beforeEach(async ({page}) => {
    await page.addInitScript(() => {
      const listeners = new Set();
      const input = {
        type: "input",
        state: "connected",
        addEventListener(type, listener) {
          if (type === "midimessage") listeners.add(listener);
        },
        removeEventListener(type, listener) {
          if (type === "midimessage") listeners.delete(listener);
        },
      };
      const access = new EventTarget();
      access.inputs = new Map([["synthetic", input]]);
      Object.defineProperty(navigator, "requestMIDIAccess", {
        configurable: true,
        value: async () => access,
      });
      window.__creatorMidi = {
        emit(note, velocity = 100) {
          for (const listener of listeners) {
            listener({data: new Uint8Array([0x90, note, velocity])});
          }
        },
        listenerCount() {
          return listeners.size;
        },
      };
    });
  });

  test("notes 36 through 51 map to the selected Bank and listeners clean up", async ({page, browserName}) => {
    test.skip(browserName !== "chromium");
    test.setTimeout(180_000);
    await page.goto("/index.html");
    await importAndActivate(page);
    await page.getByRole("button", {name: "Bank C"}).click();
    await page.getByRole("button", {name: "Enable MIDI"}).click();
    await page.evaluate(() => {
      for (let note = 36; note <= 51; note += 1) window.__creatorMidi.emit(note);
    });
    await expect.poll(async () => {
      const value = await report(page);
      return [value.trigger_admitted_count, value.trigger_outcome_count];
    }, {timeout: 30_000}).toEqual([16, 16]);
    await page.evaluate(() => {
      window.dispatchEvent(new PageTransitionEvent("pagehide"));
    });
    await expect.poll(() => page.evaluate(() => window.__creatorMidi.listenerCount()))
      .toBe(0);
    await page.reload();
  });
});

test("a denied MIDI permission does not mutate Runtime state or Trigger counts", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "requestMIDIAccess", {
      configurable: true,
      value: async () => { throw new DOMException("denied", "NotAllowedError"); },
    });
  });
  await page.goto("/index.html");
  await importAndActivate(page);
  await page.getByRole("button", {name: "Enable MIDI"}).click();
  const value = await report(page);
  expect([
    value.state,
    value.trigger_admitted_count,
    value.trigger_outcome_count,
    value.trigger_rejected_count,
  ]).toEqual(["running", 0, 0, 0]);
});
