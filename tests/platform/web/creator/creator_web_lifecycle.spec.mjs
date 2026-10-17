import {clickCreatorSystemAction, showSampleDetails, showSamplePage} from "./fixtures/creator_navigation.mjs";
import {wakeAudioWithPad} from "./fixtures/creator_audio.mjs";
import {readFile} from "node:fs/promises";

import {expect, test} from "./fixtures/refusal_diagnostics.mjs";
import {openProjectPageAfterBoot, waitForProjectReopen} from "./fixtures/creator_boot.mjs";


const bundle = process.env.LMDJ_CREATOR_WEB_BUNDLE;
if (!bundle) throw new Error("LMDJ_CREATOR_WEB_BUNDLE is required");
// openProjectJourney owns three independently bounded 30-second Project
// operations: open, inspect, and snapshot reload. The UI hang detector covers
// their 90-second protocol ceiling plus bounded runner/render settling time.
const OPEN_TRANSITION_TIMEOUT_MS = 3 * 30_000 + 35_000;
// Every audio lifecycle gesture owns one independently bounded 30-second
// Runtime request, so the state that follows an accepted gesture is promised
// only within that bound plus bounded render settling. Playwright's 5-second
// default is tighter than anything the product guarantees.
const AUDIO_TRANSITION_TIMEOUT_MS = 30_000 + 5_000;

async function installPackagedRecoveryProbe(page) {
  await page.addInitScript(() => {
    let currentGeneration = 0;
    let suppressNextOutcome = false;
    const generations = new Map();
    const boundaries = [];
    const runtimeHistory = [];
    const suppressedOutcomes = [];
    const latestDiagnostics = new Map();
    const negotiatedProfileGenerations = new Set();
    const profileFaults = [];
    const profileCapabilityReplies = [];
    const generationTransports = new Map();
    const terminalTransportHistory = [];
    const terminalTransportStates = new Map();
    function observeTerminalTransport(generation, nativeTransport) {
      const state = {generation, terminated: nativeTransport.terminated,
        terminal_owner_released: nativeTransport.terminalOwnerReleased};
      const previous = terminalTransportStates.get(generation);
      if (!previous || previous.terminated !== state.terminated ||
          previous.terminal_owner_released !== state.terminal_owner_released) {
        terminalTransportStates.set(generation, state);
        terminalTransportHistory.push({...state, observed_at_ms: performance.now()});
      }
      return state;
    }
    const terminalTransportsSnapshot = () => [...generationTransports].map(
      ([generation, nativeTransport]) => observeTerminalTransport(generation, nativeTransport));
    let armedDiagnostics = null;
    let armedProfileNegotiated = null;
    let armedGeneration = null;
    let profileFault = null;
    let releaseProfileReply = null;
    let releaseRequested = null;

    const sameTicket = (left, right) =>
      left !== null && right !== null && typeof left === "object" &&
      typeof right === "object" && Object.keys(left).length === 4 &&
      Object.keys(right).length === 4 && ["command_id", "runtime_generation",
        "frame_epoch", "ticket"].every(key => left[key] === right[key]);
    const requestTicket = request => ({command_id: request.payload.command_id,
      runtime_generation: request.payload.runtime_generation,
      frame_epoch: request.payload.frame_epoch, ticket: request.payload.input_serial});
    function releaseHeldOutcome(reason) {
      releaseRequested = reason;
      if (profileFault === null || releaseProfileReply === null) return;
      profileFault.delivery_release = {reason, observed_at_ms: performance.now()};
      const release = releaseProfileReply;
      releaseProfileReply = null;
      release();
    }

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
        // The Creator's tab-takeover channel (#1679) lives as long as the
        // page, not a Runtime generation; the Session-owned channels are what
        // this probe accounts for.
        if (argumentsList[0] === "lmdj.creator.project-takeover.v1") return channel;
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

    function createProbeTransport(generation) {
      // The factory precedes loadPackagedRuntime. Bind only after the new
      // script exposes its own Host. Calls follow that same Host's transport
      // decorators (including the real Pad admission observer), never another
      // generation's global Host. Terminal receipts retain the original owner.
      const previousHost = window.lmdjWebRuntimeHost;
      let boundHost = null;
      let boundNativeTransport = null;
      const runtimeTransport = () => {
        if (boundHost === null) {
          const candidate = window.lmdjWebRuntimeHost;
          if (!candidate?.transport || candidate === previousHost) {
            throw new Error("this generation's packaged Runtime transport is unavailable");
          }
          boundHost = candidate;
          boundNativeTransport = candidate.transport;
          generationTransports.set(generation, boundNativeTransport);
        }
        return boundHost.transport;
      };
      async function forwardRequest(lane, arguments_) {
        const [request] = arguments_;
        const nativeTransport = runtimeTransport();
        const diagnostics = latestDiagnostics.get(generation);
        const selectsProfilePress = suppressNextOutcome &&
          armedGeneration === generation && profileFault === null &&
          request?.operation === "pattern.transport.input.request" &&
          request.payload?.kind === "press" &&
          armedDiagnostics?.state === "recovering" &&
          armedDiagnostics.recovery_probe_ready === true &&
          diagnostics?.state === "recovering";
        if (selectsProfilePress) {
          // Reserve this real request before forwarding. No unrelated legacy
          // notification may stand in for this profile completion.
          suppressNextOutcome = false;
          profileFault = {generation, armed_diagnostics: structuredClone(armedDiagnostics),
            press_request: structuredClone(request),
            press_ticket: requestTicket(request), admission_response: null,
            consume_request: null, consume_response: null,
            held_at_ms: null, delivery_release: null, sdk_failure: null};
          profileFaults.push(profileFault);
        }
        // Every original request and option reaches the original actual
        // transport unchanged, including the consuming request under proof.
        const response = await nativeTransport[lane](...arguments_);
        if (request?.operation === "pattern.transport.count-in.capabilities") {
          profileCapabilityReplies.push({generation, request: structuredClone(request),
            response: structuredClone(response)});
        }
        if (request?.operation === "pattern.transport.count-in.capabilities" &&
            response?.ok === true && response.request_id === request.request_id &&
            response.result?.supported === true && response.result.negotiated === true &&
            response.result.input_capacity > 0) {
          negotiatedProfileGenerations.add(generation);
        }
        const fault = profileFault;
        if (selectsProfilePress && fault?.generation === generation) {
          fault.admission_response = structuredClone(response);
        }
        if (fault?.generation === generation && fault.consume_response === null &&
            request?.operation === "pattern.transport.input.inspect" &&
            request.payload?.consume === true &&
            sameTicket(fault.press_ticket, {
              command_id: request.payload.command_id,
              runtime_generation: request.payload.runtime_generation,
              frame_epoch: request.payload.frame_epoch, ticket: request.payload.ticket,
            }) && response?.ok === true && response.request_id === request.request_id &&
            response.result?.complete === true && response.result.durable_settled === true &&
            sameTicket(fault.press_ticket, response.result.ticket) &&
            sameTicket(fault.press_ticket, fault.admission_response?.result?.ticket) &&
            response.result.native_result?.sequence ===
              fault.admission_response?.result?.status?.admission?.sequence) {
          fault.consume_request = structuredClone(request);
          fault.consume_response = structuredClone(response);
          fault.held_at_ms = performance.now();
          // Native has really consumed this exact input. Only delivery of its
          // unchanged reply to the SDK is delayed; this is no fake ACK/result.
          suppressedOutcomes.push({generation, kind: "profile-consume-response",
            ticket: structuredClone(fault.press_ticket)});
          await new Promise(resolve => {
            releaseProfileReply = resolve;
            if (releaseRequested !== null) releaseHeldOutcome(releaseRequested);
          });
        }
        return response;
      }
      return Object.freeze({
        send(...arguments_) { return forwardRequest("send", arguments_); },
        get sendRetained() {
          const nativeTransport = boundHost?.transport;
          return typeof nativeTransport?.sendRetained === "function"
            ? (...arguments_) => forwardRequest("sendRetained", arguments_)
            : undefined;
        },
        terminate(...arguments_) { return runtimeTransport().terminate(...arguments_); },
        get terminated() {
          return boundNativeTransport === null ? undefined
            : observeTerminalTransport(generation, boundNativeTransport).terminated;
        },
        get terminalOwnerReleased() {
          return boundNativeTransport === null ? undefined
            : observeTerminalTransport(generation, boundNativeTransport).terminal_owner_released;
        },
        subscribe(listener) {
          return runtimeTransport().subscribe((notification) => {
            if (
              suppressNextOutcome && armedGeneration === generation &&
              notification?.event === "runtime.trigger_outcomes"
            ) {
              suppressNextOutcome = false;
              suppressedOutcomes.push({
                generation,
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
    }

    Object.defineProperty(window, "__LMDJ_WEB_HOST_SEAMS__", {
      configurable: false,
      get() {
        boundaries.push({generation: currentGeneration + 1, before: counts(),
          terminal_transports: terminalTransportsSnapshot()});
        currentGeneration += 1;
        generationRecord(currentGeneration);
        const generation = currentGeneration;
        return {
          transport: createProbeTransport(generation),
          onDiagnostics(value) {
            latestDiagnostics.set(generation, {generation, state: value.state,
              error_code: value.error_code,
              recovery_probe_ready: value.recovery_probe_ready === true,
              observed_at_ms: performance.now()});
            if (profileFault?.generation === generation && profileFault.sdk_failure === null &&
                value.state === "restart-required" && value.error_code === "HOST_TIMEOUT") {
              profileFault.sdk_failure = {generation,
                state: value.state, error_code: value.error_code,
                observed_at_ms: performance.now()};
              releaseHeldOutcome("observed-sdk-host-timeout");
            }
            const last = runtimeHistory.at(-1);
            // Error details and activation refusal name the failing branch of
            // a refused or sealed activation (#2345).
            const next = {
              error_code: value.error_code,
              error_details: structuredClone(value.error_details ?? {}),
              activation_refusal: value.activation_refusal ?? null,
              generation,
              state: value.state,
            };
            if (
              last?.error_code !== next.error_code ||
              last?.generation !== next.generation ||
              last?.state !== next.state ||
              last?.activation_refusal !== next.activation_refusal ||
              JSON.stringify(last?.error_details) !==
                JSON.stringify(next.error_details)
            ) {
              runtimeHistory.push(next);
            }
          },
        };
      },
    });
    window.__creatorRuntimeProbe = Object.freeze({
      armOutcomeSuppression() {
        const actual = latestDiagnostics.get(currentGeneration);
        if (actual?.state !== "recovering" || actual.recovery_probe_ready !== true) {
          throw new Error("Recovery fault requires the actual armed SDK probe window");
        }
        const latestReply = profileCapabilityReplies.filter(entry =>
          entry.generation === currentGeneration).at(-1);
        const genuinelyUnnegotiated = latestReply !== undefined &&
          latestReply.response?.request_id === latestReply.request.request_id &&
          ((latestReply.response.ok === false &&
            latestReply.response.error?.code === "HOST_PROTOCOL_MISMATCH") ||
          (latestReply.response.ok === true && latestReply.response.result?.negotiated === false &&
            typeof latestReply.response.result.supported === "boolean"));
        if (!negotiatedProfileGenerations.has(currentGeneration) && !genuinelyUnnegotiated) {
          throw new Error("Recovery fault has no actual negotiated or unnegotiated profile evidence");
        }
        armedGeneration = currentGeneration;
        armedDiagnostics = structuredClone(actual);
        armedProfileNegotiated = negotiatedProfileGenerations.has(currentGeneration);
        releaseRequested = null;
        suppressNextOutcome = true;
      },
      releaseHeldOutcome,
      snapshot() {
        return {
          ...counts(),
          boundaries: structuredClone(boundaries),
          runtime_history: structuredClone(runtimeHistory),
          suppressed_outcomes: structuredClone(suppressedOutcomes),
          profile_negotiated_generations: [...negotiatedProfileGenerations],
          profile_capability_replies: structuredClone(profileCapabilityReplies),
          armed_diagnostics: structuredClone(armedDiagnostics),
          armed_profile_negotiated: armedProfileNegotiated,
          profile_faults: structuredClone(profileFaults),
          terminal_transports: terminalTransportsSnapshot(),
          terminal_transport_history: structuredClone(terminalTransportHistory),
        };
      },
    });
  });
}

async function importAndActivate(page) {
  await openProjectPageAfterBoot(page);
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", {name: "Import .lmdj"}).click();
  await (await chooserPromise).setFiles(bundle);
  await expect(page.getByRole("heading", {name: "Project 00000000"}))
    .toBeVisible({timeout: 120_000});
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function report(page) {
  const pending = page.waitForEvent("download");
  await clickCreatorSystemAction(page, "Export report");
  return JSON.parse(await readFile(await (await pending).path(), "utf8"));
}

// A synthetic lifecycle edge never suspends the AudioContext, so the Runtime
// keeps the recovery epoch it opened, re-enters `recovering` on its own and
// asks only for the one probe Trigger; the Host never parks at
// `audio-suspended` and therefore never needs an Activate gesture here. The
// Runtime accepts an Activate gesture only while parked at `audio-suspended`,
// and musical gestures request activation only while parked there. "Audio
// suspended" is published as soon as the Host reaches `interrupted`, which is
// where the interruption starts; wait for the guaranteed recovery instead.
async function recoverFromLifecycleEdge(page) {
  await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
}

async function installLifecycleNativeProof(page) {
  await page.addInitScript(() => {
    window.__lifecycleNativeProof = {suspends: [], voices: [], outcomes: [], consumed: [], inputRpc: []};
    let exposed;
    Object.defineProperty(window, "lmdjWebRuntimeHost", {
      configurable: true,
      get() { return exposed; },
      set(nativeHost) {
        const nativeTransport = nativeHost.transport;
        // Observe actual transport receipts only; never issue a synthetic
        // inspection or consume. Admission cannot enter the proof counter.
        const inputAdmissions = new Map();
        const consumedInputs = new Set();
        const ticketKey = ticket => JSON.stringify([ticket?.command_id,
          ticket?.runtime_generation, ticket?.frame_epoch, ticket?.ticket]);
        const observeInput = (request, response) => {
          if (request?.operation === "pattern.transport.input.request" &&
              request.payload?.kind === "press" && response?.ok === true &&
              response.request_id === request.request_id) {
            const ticket = {command_id: request.payload.command_id,
              runtime_generation: request.payload.runtime_generation,
              frame_epoch: request.payload.frame_epoch, ticket: request.payload.input_serial};
            const sameTicket = value => Object.keys(ticket).length === Object.keys(value ?? {}).length &&
              Object.entries(ticket).every(([key, expected]) => value?.[key] === expected);
            if (sameTicket(response.result?.ticket) && sameTicket(response.result?.status?.ticket)) {
              inputAdmissions.set(ticketKey(ticket), structuredClone({request, response}));
            }
          }
          if (request?.operation !== "pattern.transport.input.inspect" ||
              request.payload?.consume !== true || response?.ok !== true ||
              response.request_id !== request.request_id) return null;
          const key = ticketKey(request.payload);
          const original = inputAdmissions.get(key);
          if (!original || consumedInputs.has(key)) return null;
          const status = response.result;
          const admission = original.response.result.status.admission;
          const native = status?.native_result;
          if (!admission?.authority) return null;
          const ticket = original.response.result.ticket;
          const decimal = value => typeof value === "string" && /^[1-9][0-9]*$/.test(value) &&
            BigInt(value) <= 18446744073709551615n;
          if (Object.keys(ticket).length !== Object.keys(status?.ticket ?? {}).length ||
              !Object.entries(ticket).every(([field, expected]) => status.ticket[field] === expected) ||
              status.complete !== true || status.durable_settled !== true || status.error !== null ||
              (admission.authority.recording === true && status.retained !== true) ||
              !native || native.disposition !== "voice_started" ||
              JSON.stringify(status.admission) !== JSON.stringify(admission) ||
              !decimal(native.sequence) || native.sequence !== admission.sequence ||
              !decimal(native.acceptance_ordinal) || native.acceptance_ordinal !== admission.acceptance_ordinal ||
              native.runtime_generation !== ticket.runtime_generation || native.frame_epoch !== ticket.frame_epoch ||
              native.slot !== original.request.payload.slot || native.held_press_sequence !== null ||
              JSON.stringify(native.authority) !== JSON.stringify(admission.authority) ||
              !Number.isSafeInteger(native.runtime_frame) || native.runtime_frame < 0 ||
              !Number.isSafeInteger(Number(native.sequence)) || Number(native.sequence) <= 0) return null;
          consumedInputs.add(key);
          return {payload: original.request.payload, ok: response.ok, sequence: Number(native.sequence),
            operation: "pattern.transport.input.inspect", status: structuredClone(status),
            evidence: {admission: original, consume: structuredClone({request, response})}};
        };
        nativeTransport.subscribe((notification) => {
          if (notification?.event === "runtime.voice_state") {
            window.__lifecycleNativeProof.voices.push(...structuredClone(notification.payload.events));
          }
        });
        nativeHost.transport = Object.freeze({
          async send(...args) {
            const request = args[0];
            const inputRpc = ["pattern.transport.input.request", "pattern.transport.input.inspect"]
              .includes(request?.operation)
              ? {request: structuredClone(request), began: performance.now(),
                response: null, error: null, ended: null} : null;
            if (inputRpc) window.__lifecycleNativeProof.inputRpc.push(inputRpc);
            let response;
            try {
              response = await nativeTransport.send(...args);
              if (inputRpc) inputRpc.response = structuredClone(response);
            } catch (error) {
              if (inputRpc) inputRpc.error = {code: error.code ?? null,
                message: String(error.message), details: structuredClone(error.details ?? {})};
              throw error;
            } finally {
              if (inputRpc) inputRpc.ended = performance.now();
            }
            const consumed = observeInput(args[0], response);
            if (consumed) window.__lifecycleNativeProof.consumed.push(consumed);
            if (args[0]?.operation === "audio.suspend") {
              window.__lifecycleNativeProof.suspends.push({
                request: structuredClone(args[0]), response: structuredClone(response),
              });
            }
            return response;
          },
          subscribe(...args) { return nativeTransport.subscribe(...args); },
          subscribeFailure(...args) { return nativeTransport.subscribeFailure(...args); },
          terminate(...args) { return nativeTransport.terminate(...args); },
          get terminated() { return nativeTransport.terminated; },
          get terminalOwnerReleased() { return nativeTransport.terminalOwnerReleased; },
        });
        exposed = nativeHost;
      },
    });
  });
}

async function expectNativeLoopClear(page, afterSuspend) {
  // Native audio.suspend acknowledges its quiesce-and-stop barrier before
  // returning. Observe that real reply; never substitute a UI label for it.
  await expect.poll(() => page.evaluate((after) =>
    window.__lifecycleNativeProof.suspends.slice(after).some(({request, response}) =>
      response.ok === true && response.request_id === request.request_id &&
      response.result.state === "audio-suspended" && response.result.changed === true),
  afterSuspend), {timeout: 30_000}).toBe(true);
  await expect(page.getByRole("button", {
    name: "Pad A01 — assigned — Key Z", exact: true,
  })).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
}

async function latchObservedLoopToggle(page) {
  // The public Session is attached after the raw Runtime namespace is exposed.
  // Subscribe before the musical gesture, including after a real replacement.
  await page.evaluate(() => {
    const session = window.lmdjWebRuntimeHost.session;
    if (window.__lifecycleOutcomeSession === session) return;
    window.__lifecycleOutcomeUnsubscribe?.();
    window.__lifecycleOutcomeSession = session;
    window.__lifecycleOutcomeUnsubscribe = session.subscribeRuntimeOutcome(outcome => {
      window.__lifecycleNativeProof.outcomes.push(structuredClone(outcome));
    });
  });
  const before = await page.evaluate(() => ({
    voices: window.__lifecycleNativeProof.voices.length,
    outcomes: window.__lifecycleNativeProof.outcomes.length,
    consumed: window.__lifecycleNativeProof.consumed.length,
  }));
  await latchLoopToggle(page);
  await expect.poll(() => page.evaluate((after) => {
    const proof = window.__lifecycleNativeProof;
    return proof.voices.slice(after.voices).some((voice) =>
      voice.slot === 0 && voice.state === "started" &&
      proof.outcomes.slice(after.outcomes).some((outcome) =>
        outcome.sequence === voice.sequence && outcome.outcome === "voice_started" &&
        proof.consumed.slice(after.consumed).some(input => input.sequence === voice.sequence &&
          input.status.native_result.slot === voice.slot &&
          input.status.native_result.runtime_frame === outcome.runtimeFrame)));
  }, before), {timeout: 30_000}).toBe(true);
}

async function enterLoopToggleSample(page) {
  await page.getByRole("button", {name: "Sample", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Sample editor"})).toBeVisible();
  const details = await showSampleDetails(page);
  await expect(details.locator("div").filter({has: page.locator("dt", {hasText: /^Asset ID$/})})
    .locator("dd")).toHaveText(/^[0-9a-f-]{36}$/, {timeout: 30_000});
  await showSamplePage(page, "Playback");
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

async function armPadOutcomeObservation(pad, acceptedOutcomes = null) {
  await pad.evaluate((element, acceptedOutcomes) => {
    element.removeAttribute("data-proof-outcome-observed");
    const matchesOutcome = (value) => value !== null && value !== "idle" &&
      (acceptedOutcomes === null || acceptedOutcomes.includes(value));
    const observeOutcome = () => {
      const outcome = element.getAttribute("data-outcome");
      if (matchesOutcome(outcome)) {
        element.setAttribute("data-proof-outcome-observed", outcome);
        return true;
      }
      return false;
    };
    if (observeOutcome()) return;
    const observer = new MutationObserver((records) => {
      const observed = records.some((record) => matchesOutcome(record.oldValue));
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
  }, acceptedOutcomes);
}

async function latchLoopToggle(page) {
  await expect(page.getByRole("button", {name: "Loop"}))
    .toHaveAttribute("aria-pressed", "true", {timeout: 30_000});
  const pad = page.getByRole("button", {name: "Pad A01 — assigned — Key Z", exact: true});
  await expect(pad).toHaveAttribute("data-outcome", "idle", {timeout: 30_000});
  await pad.focus();
  await page.keyboard.down("Enter");
  await expect(pad).toHaveAttribute("data-outcome", "started", {timeout: 30_000});
  await page.keyboard.up("Enter");
}

test("suspend, restart, and reopen clear an active loop toggle before reactivation", async ({page, browserName}) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(360_000);
  await page.goto("/index.html");
  await importAndActivate(page);
  await enterLoopToggleSample(page);
  await latchLoopToggle(page);
  await clickCreatorSystemAction(page, "Suspend audio");
  // An explicit Suspend publishes "Audio suspended" only after the Runtime has
  // committed the suspend, so the Host is already parked and the Activate
  // gesture that follows is guaranteed to be accepted.
  await expect(page.getByTestId("audio-state")).toHaveText("Audio suspended", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await wakeAudioWithPad(page);
  await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
    timeout: AUDIO_TRANSITION_TIMEOUT_MS,
  });
  await latchLoopToggle(page);

  await page.reload();
  // The imported Project is remembered, so the reload reopens it by itself,
  // with any writer-release PROJECT_BUSY retried as a user would.
  await waitForProjectReopen(page, "00000000", {timeout: OPEN_TRANSITION_TIMEOUT_MS});
  await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
  await wakeAudioWithPad(page);
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

test("blur and hidden lifecycle edges clear each fresh loop toggle", async ({page, browserName}, testInfo) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(180_000);
  await installLifecycleNativeProof(page);
  await page.goto("/index.html");
  await importAndActivate(page);
  await enterLoopToggleSample(page);
  try {
    await latchObservedLoopToggle(page);
    const beforeBlurSuspend = await page.evaluate(() =>
      window.__lifecycleNativeProof.suspends.length);
    await page.evaluate(() => window.dispatchEvent(new Event("blur")));
    await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
      timeout: 30_000,
    });
    await expectNativeLoopClear(page, beforeBlurSuspend);
    await recoverFromLifecycleEdge(page);
    await latchObservedLoopToggle(page);
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
      timeout: AUDIO_TRANSITION_TIMEOUT_MS,
    });
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));

    const beforeHiddenSuspend = await page.evaluate(() =>
      window.__lifecycleNativeProof.suspends.length);
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    // Preserve the original30s state boundary. While hidden, require the
    // Native stop receipt and idle Pad; the fresh probe belongs after return.
    await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
      timeout: 30_000,
    });
    await expectNativeLoopClear(page, beforeHiddenSuspend);
    await page.evaluate(() => {
      delete document.visibilityState;
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await recoverFromLifecycleEdge(page);
    await latchObservedLoopToggle(page);
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
      timeout: AUDIO_TRANSITION_TIMEOUT_MS,
    });
  } finally {
    await testInfo.attach("native-lifecycle-proof", {
      body: JSON.stringify(await page.evaluate(() => window.__lifecycleNativeProof)),
      contentType: "application/json",
    });
  }
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
  const pad = page.getByTestId("pad-matrix").getByRole("button", {name: /^Pad A01 — assigned/});
  await armPadOutcomeObservation(pad);
  await page.keyboard.down("KeyZ");
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
  ]).toEqual(["running", 2, 2]);
  await page.keyboard.up("KeyZ");
});

test("packaged recovery timeout cleans one generation before automatic replacement", async ({page, browserName}, testInfo) => {
  test.skip(browserName !== "chromium");
  test.setTimeout(240_000);
  await installPackagedRecoveryProbe(page);
  await page.goto("/index.html");
  await importAndActivate(page);
  await clickCreatorSystemAction(page, "Enable MIDI");

  const initial = await page.evaluate(() => window.__creatorRuntimeProbe.snapshot());
  expect(initial.created_generations).toBe(1);
  expect(initial.active_generations).toEqual([1]);
  expect(initial.generations[1].audio_contexts).toBe(1);
  expect(initial.generations[1].broadcast_channels).toBe(1);
  expect(initial.generations[1].midi_listeners).toBe(2);
  expect(initial.generations[1].window_lifecycle_listeners).toBeGreaterThan(0);

  try {
    await page.evaluate(() => {
      window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
      window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true}));
    });
    await expect(page.getByTestId("audio-state")).toHaveText("Audio recovering", {
      timeout: 30_000,
    });
    await page.evaluate(() => window.__creatorRuntimeProbe.armOutcomeSuppression());
    await page.keyboard.press("KeyZ");
    await expect.poll(() => page.evaluate(() =>
      window.__creatorRuntimeProbe.snapshot().runtime_history.some((value) =>
        value.generation === 1 && value.state === "restart-required" &&
        value.error_code === "HOST_TIMEOUT")), {timeout: 10_000}).toBe(true);
    const faultProof = await page.evaluate(() => window.__creatorRuntimeProbe.snapshot());
    expect(faultProof.armed_diagnostics).toMatchObject({generation: 1,
      state: "recovering", recovery_probe_ready: true});
    expect(typeof faultProof.armed_profile_negotiated).toBe("boolean");
    if (faultProof.profile_negotiated_generations.includes(1)) {
      // Positive actual negotiation must never pass via the legacy drop path.
      expect(faultProof.armed_profile_negotiated).toBe(true);
      expect(faultProof.profile_faults).toHaveLength(1);
      const fault = faultProof.profile_faults[0];
      expect(fault.generation).toBe(1);
      expect(fault.armed_diagnostics).toEqual(faultProof.armed_diagnostics);
      expect(fault.press_request.operation).toBe("pattern.transport.input.request");
      expect(fault.press_request.payload.kind).toBe("press");
      expect(fault.press_ticket).toEqual(fault.admission_response.result.ticket);
      expect(fault.press_ticket).toEqual(fault.admission_response.result.status.ticket);
      expect(fault.consume_request.operation).toBe("pattern.transport.input.inspect");
      expect(fault.consume_request.payload).toEqual({...fault.press_ticket, consume: true});
      expect(fault.consume_response.request_id).toBe(fault.consume_request.request_id);
      expect(fault.consume_response.ok).toBe(true);
      expect(fault.consume_response.result).toMatchObject({ticket: fault.press_ticket,
        complete: true, durable_settled: true, error: null,
        admission: fault.admission_response.result.status.admission,
        native_result: {sequence: fault.admission_response.result.status.admission.sequence,
          disposition: "voice_started", slot: fault.press_request.payload.slot,
          held_press_sequence: null}});
      const native = fault.consume_response.result.native_result;
      const admission = fault.admission_response.result.status.admission;
      expect(native.runtime_generation).toBe(fault.press_ticket.runtime_generation);
      expect(native.frame_epoch).toBe(fault.press_ticket.frame_epoch);
      expect(native.acceptance_ordinal).toBe(admission.acceptance_ordinal);
      expect(native.authority).toEqual(admission.authority);
      expect(Number.isSafeInteger(native.runtime_frame)).toBe(true);
      expect(native.runtime_frame).toBeGreaterThanOrEqual(0);
      expect(fault.held_at_ms).not.toBeNull();
      expect(fault.sdk_failure).toMatchObject({generation: 1,
        state: "restart-required", error_code: "HOST_TIMEOUT"});
      expect(fault.sdk_failure.observed_at_ms).toBeGreaterThanOrEqual(fault.held_at_ms);
      expect(fault.delivery_release.reason).toBe("observed-sdk-host-timeout");
      expect(fault.delivery_release.observed_at_ms).toBeGreaterThanOrEqual(
        fault.sdk_failure.observed_at_ms);
      expect(faultProof.suppressed_outcomes).toEqual([{generation: 1,
        kind: "profile-consume-response", ticket: fault.press_ticket}]);
    } else {
      expect(faultProof.armed_profile_negotiated).toBe(false);
      expect(faultProof.profile_faults).toEqual([]);
      const latestReply = faultProof.profile_capability_replies.filter(entry =>
        entry.generation === 1).at(-1);
      expect(latestReply).toBeDefined();
      expect(latestReply.response.request_id).toBe(latestReply.request.request_id);
      expect((latestReply.response.ok === false &&
        latestReply.response.error?.code === "HOST_PROTOCOL_MISMATCH") ||
        (latestReply.response.ok === true && latestReply.response.result?.negotiated === false &&
          typeof latestReply.response.result.supported === "boolean")).toBe(true);
      expect(faultProof.suppressed_outcomes).toHaveLength(1);
      expect(faultProof.suppressed_outcomes[0].generation).toBe(1);
      expect(faultProof.suppressed_outcomes[0].sequences).toBeInstanceOf(Array);
      expect(faultProof.suppressed_outcomes[0].sequences.length).toBeGreaterThan(0);
    }

    await expect(page.getByTestId("creator-phase")).toHaveText("ready", {
      timeout: 120_000,
    });
    await expect(page.getByRole("heading", {name: "Project 00000000"}))
      .toBeVisible();
    await expect(page.getByTestId("audio-state")).toHaveText("Audio inactive");
    await clickCreatorSystemAction(page, "Enable MIDI");

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
          // Enable MIDI is now an explicit audio wake gesture.
          audio_contexts: 1,
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
    // Read the old Native transport itself, not a resource count or the
    // replacement's transport. Its formal full-owner receipt must precede
    // replacement factory invocation.
    expect(secondBoundary.terminal_transports).toContainEqual({generation: 1,
      terminated: true, terminal_owner_released: true});

    await wakeAudioWithPad(page);
    await expect(page.getByTestId("audio-state")).toHaveText("Audio running", {
      timeout: 30_000,
    });
  } finally {
    // Failure must release the genuine saved reply too. This cleanup does not
    // assert that the SDK received it or any physical owner was retired.
    if (!page.isClosed()) {
      const proof = await page.evaluate(() => {
        window.__creatorRuntimeProbe.releaseHeldOutcome("test-finally");
        return window.__creatorRuntimeProbe.snapshot();
      });
      await testInfo.attach("actual-recovery-fault-proof", {
        body: JSON.stringify(proof), contentType: "application/json",
      });
    }
  }

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
    const bank = name => page.getByTestId("physical-controls").getByRole("button", {name, exact: true});
    await bank("Bank C").click();
    await clickCreatorSystemAction(page, "Enable MIDI");
    await page.evaluate(() => {
      for (let note = 36; note <= 51; note += 1) window.__creatorMidi.emit(note);
    });
    await expect.poll(async () => {
      const value = await report(page);
      return [value.trigger_admitted_count, value.trigger_outcome_count];
    }, {timeout: 30_000}).toEqual([17, 17]);
    // Report entered System, which released the held notes. The same note
    // numbers now address the newly selected Bank.
    await bank("Bank A").click();
    const padA01 = page.getByRole("button", {name: /^Pad A01 — assigned — Key /});
    await armPadOutcomeObservation(padA01);
    await page.evaluate(() => window.__creatorMidi.emit(36));
    await expect(padA01).toHaveAttribute("data-proof-outcome-observed", /.+/);
    await expect.poll(async () => {
      const value = await report(page);
      return [value.trigger_admitted_count, value.trigger_outcome_count];
    }, {timeout: 30_000}).toEqual([18, 18]);
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
  await clickCreatorSystemAction(page, "Enable MIDI");
  const value = await report(page);
  expect([
    value.state,
    value.trigger_admitted_count,
    value.trigger_outcome_count,
    value.trigger_rejected_count,
  ]).toEqual(["running", 1, 1, 0]);
});
