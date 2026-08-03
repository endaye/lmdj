# LMDJ Formal Web Runtime Host Design

Date: 2026-08-03

Status: Approved for implementation planning. Three blocking items recorded in
[Design Review Outcome](#design-review-outcome-2026-08-03) must be resolved
inside the implementation plan before Task 1 begins.

Approvals:

- Architecture approach A approved by the product owner on 2026-08-03.
- Runtime and persistence design approved by the product owner on 2026-08-03.
- Host, input, and lifecycle design approved by the product owner on 2026-08-03.
- Acceptance and version design approved by the product owner on 2026-08-03.

## Design Review Outcome (2026-08-03)

A design review against the active Core source recorded three blocking items.
They do not reopen the approved architecture. Each names an assumption this
document previously asserted without evidence, and each is now resolved in the
section listed below with a concrete answer required in the implementation plan
before Task 1.

| ID | Blocking item | Resolved in |
| --- | --- | --- |
| B1 | The Core accepts only 48 kHz PCM, but a browser `AudioContext` rate is not guaranteed to be 48 kHz | §6.5 |
| B2 | Project I/O depends on POSIX primitives that OPFS does not provide | §6.3 |
| B3 | The `-pthread` plus Wasm Workers plus WasmFS flag combination is unproven, and the pinned emsdk identity is unverified | §7.1 |

Non-blocking review corrections are applied in §7.3, §9.2, §9.4, §10, §11, §12,
§13.2, §14, §15, §16.3, §18, §19, §20, and §21.

## 1. Purpose

Stage 6 turns the experimental Web Runtime Lab into a formal, product-neutral
Web Runtime Host for the active LMDJ Headless Core. The Host proves that the
same Application Facade, Project Truth, Runtime Snapshot, and C++ Audio Runtime
can run in the browser through WebAssembly, AudioWorklet, and OPFS without
creating a second Web-only Core.

The Stage 6 deliverable is a diagnostic and conformance Host. It is not the
Creator Editor or the public LMDJ product UI.

The target Product Build is:

```text
LMDJ 1.0.12.0 · canary
```

## 2. Existing Baseline

The implementation starts from Product Build `1.0.11.0`, which includes:

- the M1 Headless Core Proof;
- the versioned Application Facade and narrow C ABI;
- the C++ realtime engine, Prepared Sample Bank, Event Queue, and Capture Ring;
- the Formal Native Host with Project/Snapshot integration and Take capture;
- the Web Runtime Lab with AudioWorklet, WebAssembly, SharedArrayBuffer,
  Pointer, Web MIDI, lifecycle measurement, report export, and a frozen
  physical acceptance evaluator.

The Web Runtime Lab remains experimental measurement tooling. Stage 6 must not
rename it or silently promote its JavaScript audio engine into the formal Host.

## 3. Approved Scope

Stage 6 implements all of the following:

1. a pinned Emscripten toolchain and reproducible WebAssembly build;
2. a product-neutral Formal Web Runtime Host;
3. a Dedicated Control Worker that owns the Application Facade and Project
   access;
4. an OPFS Project I/O platform implementation;
5. a Wasm AudioWorklet that calls the shared C++ Audio Runtime;
6. SharedArrayBuffer-based realtime Trigger and Capture paths;
7. Pointer, Keyboard, and Web MIDI Host adapters;
8. explicit browser audio lifecycle and recovery behavior;
9. Project create/import/assign, Snapshot reload, realtime playback, Take
   capture, Take commit, restart, and recovery journeys;
10. deterministic static distribution and a cross-origin-isolated local server;
11. native Core regression gates plus Chromium and WebKit automation;
12. Product and Module version propagation for `1.0.12.0`.

## 4. Explicit Non-goals

Stage 6 does not implement:

- Creator Editor or production visual design;
- a service worker, installable PWA shell, offline update policy, or app icons;
- MIDI Learn or Controller Profile management UI;
- Sample editing, Sequence editing, Perform UI, or Sound Set UI;
- production Capability Providers or cloud Project storage;
- Bluetooth qualification;
- a JavaScript or ScriptProcessor audio fallback;
- a second Project contract or Web-only Project representation;
- product-level selective Take rebase or relaxed recording concurrency;
- deployment, GitHub Release, `beta`, or `stable` promotion.

The unresolved product-level recording concurrency question remains deferred to
the Sequence/Take product design. This diagnostic Host retains the current
strict conflict-and-seal behavior.

## 5. Locked Architecture

### 5.1 Selected approach

Stage 6 uses one Emscripten WebAssembly program with shared memory:

```text
Browser Main Thread
  ├─ user activation and Host status UI
  ├─ Pointer / Keyboard / Web MIDI adapters
  └─ request transport
          │
          ▼
Emscripten Dedicated Control Worker / pthread
  ├─ Application Facade
  ├─ Project I/O Web platform primitives
  ├─ OPFS mount and Project writer lease
  ├─ Runtime Snapshot preparation
  ├─ Prepared Sample Bank publication
  └─ Capture drain and Take persistence
          │ shared WebAssembly memory
          ▼
Wasm AudioWorklet
  ├─ Event Queue consumer
  ├─ C++ RealtimeEngine::render()
  ├─ Voice-start Capture Ring producer
  └─ stereo Audio Output
```

The Emscripten runtime may load supporting JavaScript glue, but realtime sample
mixing is C++ code from `packages/audio-runtime`. JavaScript glue may instantiate
and route the Worklet; it may not implement a second sampler, voice allocator,
queue, capture path, or timing model.

### 5.2 Rejected alternatives

#### Separate control and audio WASM modules

Rejected for Stage 6. Two independent modules would require a new serialized
Snapshot/Prepared Bank contract, duplicate runtime memory, and create another
versioned compatibility boundary before the single-module path is proven.

#### JavaScript AudioWorklet with a WASM control Core

Rejected. Reusing the Lab worklet as production runtime would create separate
Native and Web Audio Runtime implementations and invalidate the shared-engine
goal.

#### MEMFS copy-in/copy-out persistence

Rejected. Copying an OPFS bundle into MEMFS before a Facade call and copying it
back afterward creates a second persistence algorithm, weakens crash behavior,
and makes the Host aware of Bundle layout.

## 6. Component Responsibilities

### 6.1 `apps/web-runtime-host`

The Formal Web Runtime Host owns:

- preflight and typed capability reporting;
- the minimal diagnostic page;
- main-thread user activation;
- request/response correlation;
- input adapters and Host mapping settings;
- lifecycle observation;
- worker and Worklet bootstrap;
- privacy-bounded diagnostics;
- the cross-origin-isolated development/proof server.

It may parse Host protocol envelopes. It must not parse `.lmdj` files, Project
manifests, Assembly internals, Take journals, or Artifact bytes.

### 6.2 Application Facade

The Application Facade remains the only Project-facing entry point. The Web
Host uses the same Command and Query semantics as CLI, MCP, and Native Host.

Stage 6 may extend the Facade with host-neutral realtime session construction
and Web storage injection. It must not add browser-specific Domain behavior or
DOM concepts to the Facade.

### 6.3 Project I/O Web platform

Project I/O keeps its existing public `ProjectStore` and `TakeJournal` behavior.
Native and Web platform primitives are separated below the Project format and
transaction logic:

```text
ProjectStore / TakeJournal common logic
  └─ ProjectStoragePlatform
       ├─ Native POSIX implementation
       └─ Emscripten WasmFS + OPFS implementation
```

The platform boundary owns:

- opening paths without following symlinks;
- bundle writer acquisition and release;
- exclusive file creation;
- complete reads and writes;
- durable file flush;
- atomic publication/rename;
- directory durability barriers;
- removal and deterministic directory iteration;
- typed platform error conversion.

#### Primitive availability (B2)

The active Native implementation in `packages/project-io/src/` depends on
`fsync`, `flock`, `openat` with `O_DIRECTORY`, `O_NOFOLLOW`, `O_EXCL`, `rename`,
`fcntl`, and explicit symlink rejection. OPFS provides none of these under those
names, and some have no equivalent at all.

A rule that any missing OPFS primitive fails the Web build is therefore not
implementable as written: it would fail the build for primitives whose absence
is harmless, and it would hide the one case that genuinely has no substitute.
Each platform obligation is instead classified, and the classification is part
of this design:

| Obligation | Class | Web realization |
| --- | --- | --- |
| complete read and complete write | native | `FileSystemSyncAccessHandle` read/write |
| durable file flush | native | `FileSystemSyncAccessHandle.flush()` |
| exclusive file creation | native | create-if-absent plus handle acquisition |
| deterministic directory iteration | native | directory handle iteration ordered by the platform |
| removal | native | `removeEntry` |
| typed platform error conversion | native | typed mapping from `DOMException` |
| opening paths without following symlinks | vacuous | OPFS has no symlinks; the obligation is satisfied by absence, which is stronger than the Native guarantee, not weaker |
| bundle writer acquisition and release | equivalent | the exclusive `createSyncAccessHandle` lock replaces `flock`; §8.2 owns the lease protocol |
| atomic publication and rename | equivalent | `FileSystemFileHandle.move()`; the plan must record the observed overwrite and atomicity semantics per target browser, because `move()` is not specified as POSIX `rename` |
| directory durability barrier | absent | no OPFS equivalent exists |

The rules that follow from the classification are:

- A `native` or `equivalent` obligation that cannot be realized fails the Web
  build or Web Proof. It is never downgraded to a weaker guarantee.
- A `vacuous` obligation is recorded as satisfied by absence, with the reason,
  so that it is never mistaken for an unimplemented gap.
- An `absent` obligation requires a written recovery argument in the
  implementation plan explaining why the Project Store and Take Journal
  transaction and checkpoint rules still hold without it. If no such argument
  can be written, the affected transaction step is redesigned rather than
  relaxed.

The Web platform must pass the same Project Store, Take Journal, replay,
recovery, and fault-conformance cases that are meaningful in the browser. The
common transaction semantics above the platform boundary are never weakened to
accommodate a browser limitation.

### 6.4 Audio Runtime Web adapter

The Web adapter creates the Wasm AudioWorklet and binds it to the existing
`RealtimeEngine`. The audio callback may only:

- consume bounded Trigger events;
- apply an already-published Prepared Sample Bank;
- mix active voices;
- publish bounded Voice-start capture events;
- update lock-free telemetry;
- write output frames.

It may not allocate, lock, access files, call the Facade, perform network I/O,
log, throw, or wait.

### 6.5 Sample rate and render quantum (B1)

The active Core is fixed at 48 kHz and does not resample anywhere.
`packages/project-cooker/src/wav_reader.cpp` rejects any WAV whose sample rate
is not `48'000`, and `packages/audio-runtime/src/prepared_sample_bank.cpp`
rejects any Runtime Snapshot PCM whose `sample_rate` is not `48'000`.

A browser `AudioContext` does not guarantee that rate. Its rate follows the
output device unless a rate is requested at construction, and the observed
device rate differs across macOS, iPadOS, and Bluetooth output. A Prepared
Sample Bank cooked at 48 kHz and rendered by a Worklet running at another rate
is a pitch and duration defect, not a tolerance.

This is a locked constraint, not an implementation detail. The implementation
plan must select exactly one resolution and record it here:

- **A. Host-forced rate.** The Host constructs the context as
  `new AudioContext({ sampleRate: 48000 })` and the browser resamples to the
  device. The plan must state the typed Host failure used when a target browser
  refuses the requested rate or silently returns a different
  `AudioContext.sampleRate`, and the Host must verify the realized rate before
  leaving `core-ready`.
- **B. Runtime resampling.** Audio Runtime gains rate conversion. This changes
  the §18 justification for Audio Runtime `0.4.0` from a compatible adapter
  addition into a behavior change, and requires native tests at non-48 kHz
  rates.

Resolution A is the smaller change and is the expected choice, but it is not
settled by this document, because it can fail on a required physical target and
that failure is exactly what §17 defers.

Independently of that choice, the Host runs at the AudioWorklet render quantum
of 128 frames. `RealtimeEngine::render(left, right, frames)` must be proven
correct at `frames == 128` by a native test before the Web Proof depends on it.
The Formal Native Host does not exercise that block size.

## 7. Toolchain and Execution Topology

### 7.1 Toolchain identity

The Web build pins emsdk tag `6.0.5` at Git revision
`dfb9d1a46c3bb8f52e1e6324be23123b9d73c190`. Build and CI must reject a
different active `emcc` version.

Neither the tag nor the revision is verified by this document (B3). The first
implementation Task must confirm against the upstream emsdk repository that the
tag exists, that the revision exists, and that the tag resolves to that
revision. If either is wrong, the corrected identity is recorded here before any
Web source is written. A Web build against an unpinned or guessed toolchain is
not a Stage 6 artifact.

The minimum required build features are:

```text
-pthread
-sWASMFS
-sAUDIO_WORKLET
-sWASM_WORKERS
-sALLOW_MEMORY_GROWTH=0
```

This flag set is provisional. It loads three threading mechanisms into one
program: POSIX threads for the Control Worker, Wasm Workers for the Audio
Worklet, and the WasmFS OPFS backend's own proxying. §5.1 deliberately writes
"Dedicated Control Worker / pthread" because that layer is not yet decided.

Task 0 of the implementation plan is therefore a throwaway toolchain spike. It
produces no product source and must prove all of:

1. a program built with the exact flag set above loads and runs;
2. shared `WebAssembly.Memory` written by the Control Worker is observed by the
   Audio Worklet;
3. WasmFS OPFS synchronous file access succeeds from the thread that owns the
   Application Facade;
4. no main-thread proxying call deadlocks while the Worklet is rendering.

§5.1 and §7.1 are locked only after Task 0 passes. If the spike fails, the
Control Worker thread model returns to architecture review; it is not patched
inside a later Task.

The implementation plan must select and test a fixed initial/maximum shared
memory value. Memory cannot grow after the AudioWorklet shares it. An
out-of-memory condition is a typed Host failure, not permission to change the
memory topology at runtime.

Because the heap is fixed, the plan must publish a memory budget computed from
the known Core constants rather than a guessed total. It accounts at minimum for
`kRealtimeBankCapacity` Prepared Sample Banks of decoded mono float data across
64 Pad Slots, `kRealtimeQueueCapacity` and `kRealtimeCaptureCapacity` ring
storage, `kRealtimeVoiceCapacity` voice state, Asset import staging buffers, and
WasmFS OPFS buffers.

### 7.2 Worker ownership

The Application object, Project writer lease, OPFS mount, Runtime Snapshot, and
control-side Realtime Session state are created and destroyed in the Dedicated
Control Worker. The browser main thread never calls synchronous Project I/O.

The main thread is limited to APIs that require the Window or a direct user
gesture, including `AudioContext` activation and DOM input handling.

### 7.3 Cross-origin isolation

The Host server must return at least:

```text
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Content-Type: application/wasm
```

`Cache-Control: no-store` applies to `index.html` and the Product/Host manifest
only. Content-hashed assets are served immutable, which is what makes the §15
asset-hash inventory meaningful; a blanket `no-store` would contradict that
inventory and slow the Proof without adding a guarantee.

The Host must verify `crossOriginIsolated === true` and the availability of
SharedArrayBuffer before loading the shared-memory runtime.

## 8. OPFS and Project Semantics

### 8.1 Workspace layout

The Host owns one origin-private workspace root. Project paths presented to the
Facade are normalized absolute virtual paths below that root. User-visible
file-system handles are not Project Truth and are not required for Stage 6.

The Host may display a stable opaque Project ID. It may not reveal physical
browser storage paths because OPFS has no user-visible path identity.

### 8.2 Writer lease

Exactly one Control Worker may hold the writer lease for a Project. A second
tab or Worker requesting the same Project receives:

```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_BUSY",
    "message": "project is already open for writing",
    "details": {}
  }
}
```

The Host does not wait indefinitely, steal a lease, or open a writable shadow
copy. Stale-lease recovery must be based on the underlying OPFS handle lifetime
or a tested monotonic ownership protocol, never a wall-clock timeout alone.

### 8.3 Durability

Every successful mutating Facade Command returns only after Project I/O has
completed the platform durability sequence required by that Command. The Host
must not send a success response and flush later.

Worker shutdown attempts a clean close, but crash safety is proven through the
same transaction/checkpoint recovery rules rather than relying on an unload
event.

### 8.4 Restart and recovery

After page or Worker restart, the Host must be able to:

1. mount the same origin workspace;
2. open and inspect the Project through the Facade;
3. reproduce the last committed Project revision;
4. list recoverable Takes;
5. Cook and publish a new immutable Runtime Snapshot;
6. resume audio only after a new explicit user activation.

## 9. Realtime Session Data Flow

### 9.1 Start

1. Main thread completes preflight.
2. Control Worker mounts OPFS and creates the Application Facade.
3. The Host opens a Project and requests a Runtime Snapshot through the Facade.
4. Control Worker prepares a `PreparedSampleBank` outside the audio callback.
5. Control Worker publishes the Bank through the existing bounded publication
   path.
6. A user gesture creates or resumes the `AudioContext`.
7. The Worklet observes the published Bank and transitions to `running`.

### 9.2 Trigger

```text
DOM or Web MIDI event
  → Host adapter validates slot and velocity
  → bounded Shared Event Queue
  → RealtimeEngine consumes on next render quantum
  → exactly one Voice starts, a Voice is stolen, or a typed enqueue result
    is reported
```

An accepted Trigger has three possible runtime outcomes, not two. `EnqueueResult`
already enumerates the rejection cases, including `queue_full` and
`bank_transition`. Voice stealing is different: it happens inside `render()`
once `kRealtimeVoiceCapacity` active voices are exceeded, and it has no
`EnqueueResult` value. The Host must expose voice stealing as counted telemetry
so that a stolen voice is never silently counted as a normal Voice start.

The Host acknowledges acceptance into the Event Queue. It does not report an
audible onset as a browser fact. Physical onset remains external evidence.

### 9.3 Snapshot reload

Snapshot preparation and Sample Bank construction happen off the audio thread.
Publication is atomic at a render boundary. If preparation or publication
fails, the prior Bank remains active and the Host returns a typed error.

### 9.4 Capture

```text
take.begin through Facade
  → arm Capture Ring
  → render callback records actual Voice starts
  → Control Worker drains bounded batches
  → Facade appends realtime Take events
  → take.stop disarms and drains the final batch
  → explicit take.commit writes Pattern and Project revision
```

Queue drops, Capture Ring drops, processor errors, Worker failure, or incomplete
final drain seal the Take as `capture_incomplete`. They never produce a normal
commit.

## 10. Input Adapters

All input adapters call one Host route:

```text
trigger(slot: 0..63, velocity: 1..127)
```

Two Pad addressing forms exist, and the Host protocol must not blur them.
Project Truth addresses a Pad as `bank` plus `pad`; the domain model is four
Banks of sixteen Pad Slots
(`packages/authoring-domain/include/lmdj/domain/project.hpp`). The realtime
`TriggerEvent` carries one flat `slot` in `0..63`.

Facade-delegated operations such as `pad.assign` use the Project Truth form.
`trigger` uses the flat realtime form. The flattening happens once, in the Host
adapter, immediately before enqueue, and it must use the same ordering the Core
applies when building a Prepared Sample Bank. No other layer converts between
the two forms, and neither form is translated inside the Facade.

### 10.1 Pointer

- only the primary activation of a pad generates a Trigger;
- a pointer sequence cannot retrigger through compatibility mouse events;
- velocity is a fixed Host setting in `1..127`;
- disabled, unavailable, or out-of-range Pads do not enqueue.

### 10.2 Keyboard

- mapping uses physical `KeyboardEvent.code`, not localized text;
- key repeat is ignored;
- keydown triggers and keyup only clears Host pressed state;
- focus inside editable controls disables performance shortcuts;
- velocity is a fixed Host setting in `1..127`.

### 10.3 Web MIDI

- permission is requested only after an explicit user action;
- SysEx is always disabled;
- Note On velocity `0` is treated as Note Off and does not Trigger;
- Note On velocity `1..127` is preserved;
- disconnect clears pressed state and reports device loss;
- device name, manufacturer, stable ID, serial, and raw messages are never
  written to reports or Project Truth.

The default diagnostic mapping is a linear contiguous note range supplied as
Host/Workspace configuration. Mapping and any future Controller Profile are not
Project Truth. MIDI Learn remains outside Stage 6.

## 11. Host State Machine

The externally visible Host states are:

```text
cold
  → preflight
  → storage-ready
  → core-ready
  → audio-suspended
  → running
  → interrupted
  → recovering
  → audio-suspended
  → running
  → closed

any state → failed
```

`failed` is reachable from every state, including `preflight`, `storage-ready`,
and `core-ready`. A preflight rejection is a `failed` runtime instance, not an
undrawn edge.

`recovering` is a distinct state because the §11.2 recovery test has three
conditions and takes observable time. The Host is not `running` while those
conditions are still being satisfied.

### 11.1 State rules

- Trigger and Record are rejected before `running`.
- Rejected input is not queued for later replay.
- `audio-suspended` means the Core and Project may be ready while user
  activation is still required.
- `interrupted` stops new Trigger acceptance immediately.
- each interruption requires at most one explicit activation before returning
  to `running`; a session may be interrupted and reactivated any number of
  times, which is the normal iPadOS Safari pattern;
- `failed` is terminal for the current runtime instance;
- Project data remains reopenable after a runtime failure unless Project I/O
  itself reports corruption.

### 11.2 Lifecycle observations

The Host observes:

- `AudioContext.statechange`;
- `visibilitychange`;
- `pagehide` and `pageshow`;
- Worker error/message error;
- AudioWorklet `processorerror`;
- MIDI connect/disconnect;
- storage mount, lease, flush, and quota failures.

The Host must not claim recovery from visibility state alone. Recovery is
complete only when the AudioContext is `running`, the Worklet acknowledges the
current Runtime generation, and the first post-recovery Trigger has exactly one
runtime acknowledgement.

## 12. Host Protocol

### 12.1 Envelope

Every request contains:

```json
{
  "protocol_version": 1,
  "request_id": "lowercase-uuid",
  "operation": "host.operation",
  "payload": {}
}
```

Every response echoes `request_id` and `protocol_version` and uses the existing
success/error envelope shape. Notifications have an `event` field and no
`request_id`.

The transport rejects malformed UTF-8, duplicate request IDs, unknown fields,
oversized messages, unsupported operations, and wrong-state operations.

Strict unknown-field rejection removes forward compatibility, so
`protocol_version` is mandatory rather than decorative. It is the only
sanctioned way for a later Host to detect an incompatible peer instead of
failing on an unrecognized field. A mismatched `protocol_version` is a typed
rejection, never a best-effort parse.

### 12.2 Required operations

The formal Host supports at least:

```text
host.status
project.create
project.open
project.inspect
asset.import
pad.assign
snapshot.reload
audio.activate
audio.suspend
trigger
take.begin
take.stop
take.commit
take.recoverable.list
host.close
```

Capture operations use the `take.` prefix throughout this document and in the
implemented Host. `record.begin`, `record.stop`, and `record.commit` are not
alternative spellings; they do not exist. Like the §15 command names, these
operation names are part of the Stage 6 operator contract.

Project mutations and queries are delegated to the Application Facade. Host
operations only orchestrate browser/runtime state.

### 12.3 Required notifications

```text
host.state_changed
snapshot.published
snapshot.rejected
audio.interrupted
audio.recovered
midi.connected
midi.disconnected
runtime.warning
capture.sealed
```

`snapshot.published` carries the Runtime generation identifier, and
`host.status` reports both the current control-side generation and the
generation last acknowledged by the Worklet. Without an exposed generation the
§11.2 recovery test cannot be evaluated by the Host or asserted by the Browser
Proof.

Notifications are diagnostic facts, not persisted Project events.

## 13. Failure Policy

### 13.1 Preflight

Any missing mandatory primitive produces `UNSUPPORTED_WEB_RUNTIME` with an
ordered list of missing capabilities:

```text
secureContext
crossOriginIsolated
sharedArrayBuffer
webAssembly
audioWorklet
opfs
```

There is no fallback to ScriptProcessor, a JavaScript engine, IndexedDB, a
remote Project, or Bluetooth.

### 13.2 Runtime failure matrix

| Failure | Required behavior |
| --- | --- |
| OPFS unavailable | fail preflight; do not create an in-memory Project |
| quota or flush failure | Command returns typed persistence failure |
| Project writer held elsewhere | return `PROJECT_BUSY` |
| Assembly/version mismatch | fail closed before Project mutation |
| Snapshot Cook failure | retain prior active Bank |
| Bank publication failure | retain prior active Bank and generation |
| Event Queue full | reject Trigger and increment queue-drop telemetry |
| Worklet `processorerror` | enter `failed`; seal active Take |
| Capture Ring drop | seal active Take as `capture_incomplete` |
| Worker crash | stop accepting input; restart requires Project reopen |
| Worker unresponsive | typed request timeout, then `failed`; a Worker blocked on an OPFS handle held elsewhere does not crash and must not hang the Host indefinitely |
| shared heap exhausted | typed Host failure; never grow memory and never silently shrink the published Bank |
| realized `AudioContext.sampleRate` is not 48 kHz | fail before leaving `core-ready`; never render a 48 kHz Bank at another rate |
| audio suspended/interrupted | enter `interrupted`; require activation |
| MIDI permission denied | Pointer/Keyboard remain available; report denial |
| MIDI disconnected | clear MIDI state; do not synthesize Note Off events |

## 14. Security and Privacy

- The Host runs only in a secure context except the loopback development
  exception supported by browsers.
- Cross-origin isolation is mandatory.
- Provider secrets, API keys, raw MIDI messages, device identifiers, local
  paths, OPFS handles, and arbitrary Project bytes are excluded from logs and
  reports.
- Imported user audio remains in the origin-private workspace unless a future
  explicit export or Provider Command is authorized.
- The diagnostic server exposes only the built distribution root and rejects
  path traversal, directory listing, range abuse, and unknown methods.
- Content Security Policy must permit only the exact worker/worklet/WASM assets
  required by the built Host; no remote script dependency is allowed. The policy
  is recorded as concrete directives rather than as an intent, because a policy
  that reads correctly as prose can still break the runtime: WebAssembly
  compilation requires `'wasm-unsafe-eval'` in `script-src` on Chromium, and the
  Emscripten worker and worklet bootstrap may require `worker-src 'self' blob:`.
  The implementation plan records the exact directive set, and the Browser Proof
  runs with that policy applied. A Host that passes only when CSP is absent is
  not a passing Host.

## 15. Build and Distribution

Stage 6 adds one stable entry command, parallel to `scripts/core.sh`:

```bash
scripts/web-runtime-host.sh configure
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh test
scripts/web-runtime-host.sh proof
scripts/web-runtime-host.sh serve
scripts/web-runtime-host.sh clean
```

The exact command names are part of the Stage 6 operator contract. `proof`
builds from a clean Web configuration, runs native-independent tests, packages
the Host, starts the cross-origin-isolated server, executes browser automation,
and verifies the distribution inventory.

The distribution contains only deterministic runtime assets and identity
metadata, including:

```text
index.html
host JavaScript modules
Control Worker asset
AudioWorklet asset
WebAssembly module
Product/Host manifest
asset hashes
```

The cross-origin-isolated server named in §6.1 is a development and Proof tool.
It is not part of the distribution. The inventory check asserts its absence as
positively as it asserts the presence of the runtime assets.

No source tree, absolute local path, development dependency, source map,
unapproved fixture audio, or secret is shipped in the canary package.

## 16. Automated Acceptance

### 16.1 Native regression

Every Stage 6 integration candidate must pass:

```bash
scripts/core.sh proof
scripts/core.sh test asan full
scripts/core.sh test tsan full
scripts/core.sh test stress full
scripts/core-coverage.sh
scripts/web-runtime-lab.sh test
```

CI must retain macOS, Ubuntu, ASan, Coverage, TSan, and Stress lanes.

### 16.2 Web unit and conformance tests

Tests cover:

- Host protocol shape, size, state, and idempotency;
- input mapping and duplicate suppression;
- lifecycle state transitions;
- typed failure mapping;
- OPFS platform primitives;
- Project Store and Take Journal Web conformance;
- Event Queue and Capture Ring memory layout;
- version/manifest/distribution inventory;
- privacy-bounded diagnostics.

### 16.3 Browser Proof

Chromium executes the complete automated journey:

1. verify isolation and mandatory primitives;
2. mount an empty OPFS workspace;
3. create a Project through the Facade;
4. import deterministic WAV fixtures and assign Pads;
5. Cook and publish a Runtime Snapshot;
6. activate audio through a real page gesture;
7. dispatch 500 valid Trigger events and prove zero lost and zero duplicate
   runtime acknowledgements;
8. begin a Take, dispatch 20 Trigger events inside the Take and one further
   Trigger after `take.stop`, drain, and commit, proving the committed Take
   contains exactly the 20 in-Take events;
9. inspect the committed Project revision and Pattern;
10. restart page and Worker, reopen the same OPFS Project, and republish;
11. exercise suspend/recovery and failure injection;
12. close cleanly with zero runtime queue/capture drops.

Step 7 is bounded by Core constants and must be written against them rather than
against a round number. `kRealtimeQueueCapacity` is 1024, so 500 undrained
events fit. `kRealtimeVoiceCapacity` is 128, so the fixture length and dispatch
pacing must keep concurrent voices below that bound; otherwise the run steals
voices and the zero-loss assertion becomes timing-dependent rather than
deterministic. The Proof records the fixture duration and pacing it relies on,
and asserts zero `bank_transition` results and zero voice-steal events for the
duration of the step. If a Core constant later changes, this step is re-derived
from the new constants, not re-tuned until it passes.

Playwright WebKit executes capability, OPFS, restart, protocol, and lifecycle
smoke wherever the automation runtime exposes the required APIs. WebKit
automation is not physical Safari evidence. A missing WebKit CI capability is
reported as an explicit platform limitation and may not be relabeled as a
passing Safari gate.

### 16.4 Clean distribution acceptance

The built Host is copied into a fresh temporary directory. The proof server and
browser tests run from that directory without the source tree, `NODE_PATH`,
`PYTHONPATH`, build directory lookup, or network package fetches.

## 17. Physical Gate Deferral

The approved physical gate still contains five required rows:

1. macOS Safari Pointer performance;
2. macOS Chrome Pointer performance;
3. macOS Chrome Physical MIDI performance;
4. iPadOS Safari Touch performance;
5. iPadOS Safari Touch lifecycle.

The product owner explicitly approved starting and completing the Stage 6
canary implementation before these rows are complete. Their status remains:

```text
deferred / unverified
```

This deferral means:

- the values are not implementation parameters;
- automation cannot mark the rows passed;
- Stage 6 may reach an implemented and merged canary state;
- Web/PWA physical viability is not yet proven;
- no `beta` or `stable` promotion is allowed;
- a later failed required row returns the platform decision to product and
  architecture review.

## 18. Version Management

### 18.1 Target identities

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.11.0` | `1.0.12.0` | adds an Assembly-listed Formal Web Runtime Host |
| Web Runtime Host | absent | `1.0.0` | first formal Host surface |
| Project I/O | `0.3.0` | `0.4.0` | adds a compatible Web storage platform |
| Audio Runtime | `0.3.0` | `0.4.0` | adds a compatible Web AudioWorklet adapter |
| Application Facade | `1.1.0` | `1.2.0` | adds compatible realtime/Web composition support |
| Core CLI | `1.0.2` | `1.0.3` | exact Facade dependency update only |
| Core MCP | `1.0.2` | `1.0.3` | exact Facade dependency update only |
| Native Test Host | `1.0.0` | `1.0.1` | exact Facade/Audio dependency update only |
| Contracts | current | unchanged | no wire Contract change |
| Providers | current | unchanged | no Provider behavior change |

The Audio Runtime reason above assumes B1 resolves to option A, the Host-forced
48 kHz `AudioContext`. If B1 resolves to option B, Audio Runtime gains
resampling behavior, and its reason — and possibly its target — must be
restated here before the implementation plan is approved.

The implementation plan must update every exact dependency and regenerate
`products/lmdj/assembly.lock.json` through `scripts/version.py lock`.

### 18.2 Channel and tag

The candidate remains `canary`. After squash merge to `main`, successful full
CI, merged-main Proof, and exact identity verification, the Integration Owner
may create signed annotated tag:

```text
lmdj-v1.0.12.0
```

Tag creation, tag push, GitHub Release, deployment, publication, and Channel
promotion are separately authorized states. This design authorizes none of
them by itself.

## 19. Rollback

Rollback reuses immutable Product Build `1.0.11.0`; tags are never moved.

OPFS data written by `1.0.12.0` must remain valid `lmdj.project.v1` Project
Truth. If the Host is withdrawn, users can reopen the same Project through a
compatible later Host.

That guarantee is about format, not reachability. Product Build `1.0.11.0` has
no Web Host, and §4 excludes export, so a rollback leaves origin-private Project
data in place with no Host able to open it until a later Web Host ships. For a
canary diagnostic Host this is accepted, and it is stated here rather than left
implied by the format guarantee. If the implementation plan chooses to remove
the hazard, a bundle download is the only sanctioned escape hatch: the Host
hands the already serialized bundle bytes to the browser as a download and still
does not parse them, so the §6.1 boundary holds.

Stage 6 may add storage metadata outside Project Truth, but it must be
versioned, disposable, and reconstructible.

## 20. Definition of Stage 6 Complete

Stage 6 implementation is complete only when all of these are true:

- B1, B2, and B3 are resolved, and the resolutions are recorded in §6.5, §6.3,
  and §7.1 of this document rather than only in the plan;
- the approved implementation plan is fully executed;
- the Formal Web Runtime Host exists in active `apps/` source;
- the Product Assembly lists exact target identities for `1.0.12.0`;
- Emscripten `6.0.5` clean-build reproducibility is verified;
- OPFS create/mutate/restart/recovery behavior is proven through the Facade;
- C++ Audio Runtime renders inside the Wasm AudioWorklet;
- Pointer, Keyboard, and Web MIDI use one Trigger path;
- Take capture and explicit commit succeed through the formal journey;
- failure, lifecycle, privacy, and distribution gates pass;
- native Core Proof and all required CI lanes remain green;
- the branch receives review, is squash-merged to `main`, and merged `main` is
  reverified;
- the signed Product tag is created and pushed only after separate approval.

The five deferred physical rows are explicitly excluded from the canary
implementation-complete claim, but they remain mandatory before any Web/PWA
physical-pass, `beta`, or `stable` claim.

## 21. Spec Self-review Checklist

- No retired `lmdj.patch.v1` or `lmdj.materials.v1` contract is restored.
- Host, Project, Runtime, and audio-thread responsibilities are separated.
- OPFS does not create a second Project parser or persistence algorithm.
- No fallback produces a second Audio Runtime.
- Product-level Take concurrency remains unresolved rather than silently
  redesigned.
- Creator UI and PWA packaging remain outside Stage 6.
- Version identities are exact and independent.
- Automated WebKit is not represented as physical Safari.
- Deferred physical evidence is not represented as passed.
- The 48 kHz Core constraint is stated and resolved rather than assumed away
  (B1).
- Absent OPFS primitives are classified rather than promised (B2).
- The Emscripten flag combination and emsdk identity are marked provisional
  until Task 0 (B3).
- Capture operations use one `take.` naming, and Pad addressing distinguishes
  Project Truth `bank`/`pad` from the flat realtime slot.

## 22. References

- [LMDJ Playable Beat Instrument Core Redesign](2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
- [Formal Native Realtime Host Design](2026-08-02-lmdj-formal-native-realtime-host-design.md)
- [Web Realtime Audio Threshold Decision](../../architecture/2026-08-01-web-realtime-audio-threshold-decision.md)
- [Version Management](../../governance/version-management.md)
- [Git Workflow](../../governance/git-workflow.md)
- [Emscripten Wasm Audio Worklets API](https://emscripten.org/docs/api_reference/wasm_audio_worklets.html)
- [Emscripten File System API](https://emscripten.org/docs/api_reference/Filesystem-API.html)
- [MDN Origin Private File System](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system)
- [MDN FileSystemSyncAccessHandle](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle)
- [MDN crossOriginIsolated](https://developer.mozilla.org/en-US/docs/Web/API/Window/crossOriginIsolated)
