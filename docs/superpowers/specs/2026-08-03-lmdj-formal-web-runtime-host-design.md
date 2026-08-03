# LMDJ Formal Web Runtime Host Design

Date: 2026-08-03

Status: Approved for implementation planning.

Approvals:

- Architecture approach A approved by the product owner on 2026-08-03.
- Runtime and persistence design approved by the product owner on 2026-08-03.
- Host, input, and lifecycle design approved by the product owner on 2026-08-03.
- Acceptance and version design approved by the product owner on 2026-08-03.
- The revised design review version was reapproved by the product owner on
  2026-08-03.
- Durable Journal append Option A was approved by the product owner on
  2026-08-03.

## Design Review Outcome (2026-08-03)

Two reviews against the active Core source and current Web platform
specifications recorded six blocking assumptions. The revised design resolves
each assumption explicitly rather than delegating an architecture choice to the
implementation plan:

| ID | Blocking assumption | Locked resolution |
| --- | --- | --- |
| B1 | The Core accepts only 48 kHz PCM | the Host requires a realized 48 kHz `AudioContext`; Runtime resampling is outside Stage 6 (§6.5) |
| B2 | POSIX persistence primitives can be mapped to OPFS by name | Project I/O exposes semantic storage obligations with explicit Native, Web-equivalent, vacuous, and absent realizations (§6.3) |
| B3 | The exact Emscripten thread, AudioWorklet, and OPFS topology already works | a committed Web Toolchain Conformance gate must pass before product source begins (§7.1) |
| B4 | A fixed Wasm heap can hold every Project-valid Artifact and Bank | the diagnostic Host publishes strict Web preparation limits and refuses oversized runtime material without changing Project Truth (§7.2) |
| B5 | enqueue acceptance proves exactly one runtime Voice start | Audio Runtime publishes one sequence-addressed runtime outcome for every dequeued Trigger (§9.2) |
| B6 | a strict Host protocol can remain versionless and outside Contract policy | the protocol is a distribution-private, same-build transport governed by Web Runtime Host SemVer (§12) |

The review also corrects cache scope, Take operation naming, Pad addressing,
lifecycle transitions, CSP requirements, distribution inventory, Browser Proof
bounds, rollback reachability, and version reasoning.

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
6. SharedArrayBuffer-based realtime Trigger, runtime-outcome, and Capture
   paths;
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
  ├─ Trigger Outcome drain
  └─ Capture drain and Take persistence
          │ shared WebAssembly memory
          ▼
Wasm AudioWorklet
  ├─ Event Queue consumer
  ├─ C++ RealtimeEngine::render()
  ├─ Trigger Outcome Ring producer
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

A rule that maps those POSIX calls one-for-one is therefore invalid. The
platform boundary exposes semantic storage obligations instead. Native remains
free to implement them with POSIX primitives, while Web must implement the same
observable result with OPFS:

| Obligation | Class | Web realization |
| --- | --- | --- |
| complete read and complete write | native | `FileSystemSyncAccessHandle` read/write |
| durable file flush | native | `FileSystemSyncAccessHandle.flush()` |
| exclusive Project writer | equivalent | one dedicated lease file held by an exclusive `FileSystemSyncAccessHandle` for the writer lifetime |
| collision-safe immutable file creation | equivalent | under the writer lease, persist a Project-neutral storage intent, reject an existing name, loop over short writes, verify final length and hash, flush, then acknowledge |
| deterministic directory iteration | equivalent | collect the complete OPFS iterator and sort names by unsigned UTF-8 byte order before common logic observes them |
| recoverable whole-file replacement | equivalent | persist a Project-neutral storage intent before touching the destination, write through `createWritable({keepExistingData: false})`, and reconcile exact previous-or-next state after restart |
| removal | native | idempotent `removeEntry`; a missing entry is already removed |
| typed platform error conversion | native | typed mapping from `DOMException` |
| opening paths without following symlinks | vacuous | OPFS has no symlinks; the obligation is satisfied by absence, which is stronger than the Native guarantee, not weaker |
| directory durability barrier | absent | no OPFS equivalent exists |

`FileSystemDirectoryHandle` iteration order is explicitly unspecified, so
platform order is never treated as deterministic. `getFileHandle({create:
true})` is not `O_EXCL`, and `FileSystemFileHandle.move()` is not part of the
portable Stage 6 storage contract. Common transaction logic must call the
semantic obligations above instead of depending on either behavior.

Take Journal repair uses the approved semantic operation
`append_durable(path, valid_prefix_length, bytes)`. Common `TakeJournal` logic
reads and validates the Journal and supplies the byte offset immediately after
the last complete durable record. The platform does not parse JSONL, inspect
newlines, infer a repair boundary, or decide whether a record is complete.
Under its exclusive regular-file operation, the platform rejects a prefix
beyond the current file length without mutation, truncates exactly to a shorter
valid prefix, appends all supplied bytes, and performs exactly one file flush
after the truncate-and-append sequence. Same-platform Journal appends are
serialized in common code across `TakeJournal` instances so that an
acknowledged append cannot be removed by a later stale prefix. Native and Web
implementations must pass the same clean-prefix, torn-tail, arbitrary-binary,
oversized-prefix, and concurrent-append cases.

The writer lease is stored below the Host workspace metadata root under the
SHA-256 of the normalized Project virtual path. It is outside Project Truth.
The first Control Worker creates or opens that stable lease file and holds its
default exclusive SyncAccessHandle until Project close. Acquisition is
reference-counted and reentrant only for equivalent normalized paths on the
same `ProjectStoragePlatform` instance, allowing a Host-lifetime lease to
contain nested Store and Journal mutations. A distinct platform instance or
page receives `PROJECT_BUSY`; it does not wait, steal, delete the stable lease
entry, or fall back to a wall-clock stale timeout.

Web replacement and immutable creation use the versioned,
Project-neutral `lmdj.storage.intent.v1` protocol. Intents live under
`.lmdj-host/storage-intents/<sha256(normalized-project-path)>/`, keyed by the
SHA-256 of the normalized destination, and never enter Project Truth. Each
intent records the destination, operation, expected new hash and length, and
the exact previous state as either absent or a hash and length. The intent is
completely written, verified, flushed, and closed before the destination is
touched.

Immediately after the external writer handle is acquired and before the lease
is returned, recovery deterministically scans that lease's intents. An exact
new or exact previous destination state is accepted and the intent is removed.
For a previously absent destination, any unexpected partial destination is
removed and absence is verified before retry. For a previously existing
destination, an unexpected partial or missing destination fails closed with a
typed storage error and preserves both destination and intent as evidence;
recovery never invents prior bytes. The protocol parses no Project bundle,
manifest, JSONL, or Journal semantics and uses neither `move()` nor a claimed
directory durability primitive.

`create_immutable` loops until every byte is written, verifies the final length
and content hash, flushes exactly as required, and acknowledges only after the
intent is removed. An interrupted partial immutable remains unacknowledged and
is removed by the previously-absent recovery rule before retry.

The directory durability barrier remains genuinely absent. Correctness does not
claim a POSIX disk-order guarantee that OPFS cannot express; it depends on the
intent reconciliation above. The committed Web storage conformance suite must
inject real page termination before write, during write, before close, after
close, and before cleanup for both absent and existing destinations, then reopen
through the production bridge and prove exactly absent/old or new across all ten
cases. It must also prove an unexpected partial destination with a recorded
prior existing state fails closed and preserves evidence. If either Chromium or
an otherwise-capable WebKit target violates these outcomes, B2 fails and the
storage algorithm returns to architecture review.

WasmFS mount failure still returns a non-null Web platform. Every operation on
that unavailable platform returns a typed storage error, avoiding a Host-side
null dereference.

The rules that follow from the classification are:

- A `native` or `equivalent` obligation that cannot be realized fails the Web
  build or Web Proof. It is never downgraded to a weaker guarantee.
- A `vacuous` obligation is recorded as satisfied by absence, with the reason,
  so that it is never mistaken for an unimplemented gap.
- An `absent` obligation requires a written recovery argument in the
  design explaining why the Project Store and Take Journal transaction and
  checkpoint rules still hold without it. The recovery argument above is the
  Stage 6 answer; the implementation plan must translate each step into a named
  test and may not replace it with weaker prose.

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
- publish one bounded runtime outcome for every dequeued Trigger;
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

A context that omits `sampleRate` follows the preferred output-device rate,
which can differ across macOS, iPadOS, and external outputs. Rendering a 48 kHz
Prepared Sample Bank in a Worklet running at another rate is a pitch and
duration defect, not a tolerance.

Stage 6 therefore locks the Host-forced solution. The main thread constructs:

```javascript
new AudioContext({sampleRate: 48000})
```

The Host verifies `audioContext.sampleRate === 48000` before leaving
`core-ready`. Constructor rejection or any other realized rate produces
`UNSUPPORTED_WEB_RUNTIME` with `expected_sample_rate` and
`observed_sample_rate`; no Snapshot is published and no Trigger is accepted.
Runtime resampling is explicitly outside Stage 6. If a required physical target
cannot realize the requested context rate, that row fails and returns the Web
platform decision to architecture review rather than silently adding a
resampler.

The Host targets the default AudioWorklet render quantum of 128 frames and
passes the actual callback frame count to
`RealtimeEngine::render(left, right, frames)`. A native test must prove exact
behavior at `frames == 128`, and the Toolchain Conformance gate must observe a
128-frame Worklet callback before product source begins. A different realized
quantum is `UNSUPPORTED_WEB_RUNTIME` for Stage 6; it is not truncated, padded,
or processed with a JavaScript fallback.

## 7. Toolchain and Execution Topology

### 7.1 Toolchain identity

The Web build pins all three layers of the Emscripten identity:

```text
emsdk tag:                6.0.5
emsdk Git revision:       dfb9d1a46c3bb8f52e1e6324be23123b9d73c190
emscripten-releases rev:  dbd755b5da399329c2576f6e3dfa7f419f5d8409
```

The tag-to-revision and release mapping were verified against the upstream
emsdk repository on 2026-08-03. Configure, build, and CI must reject a different
active `emcc` identity and record `emcc --version` in the build manifest. A Web
build against an unpinned or guessed toolchain is not a Stage 6 artifact.

The minimum required build features are:

```text
-pthread
-sWASMFS
-sAUDIO_WORKLET
-sWASM_WORKERS
-sINITIAL_MEMORY=536870912
-sALLOW_MEMORY_GROWTH=0
```

Emscripten documents that `-pthread` may be combined with a Wasm AudioWorklet,
which itself runs as a Wasm Worker. What remains unproven is the exact
combination with the WasmFS OPFS backend and the Stage 6 Control Worker.

Task 0 of the implementation plan is therefore a committed **Web Toolchain
Conformance** gate, not a throwaway manual spike. It adds a minimal fixture and
runner below `tests/platform/web/toolchain/`, is executed by Web Proof and CI,
contains no Product behavior, and must prove all of:

1. the exact identities and flag set above configure, build, load, and run;
2. shared `WebAssembly.Memory` written by the Control Worker is observed by the
   Audio Worklet;
3. the Worklet callback reports exactly 128 frames per channel;
4. WasmFS OPFS synchronous file access succeeds from the thread that will own
   the Application Facade;
5. the §6.3 writer lease, sorted iteration, flush, whole-file replacement, and
   restart cases pass;
6. no main-thread proxying call deadlocks while the Worklet is rendering;
7. Chromium passes the full gate and WebKit either passes or reports a specific
   missing mandatory primitive rather than a false pass.

No source is added below `apps/`, `packages/`, or `products/` until Task 0 is
green. If the gate fails, the Control Worker/storage topology returns to
architecture review; it is not patched opportunistically inside a later Task.

### 7.2 Fixed shared heap and Web preparation limits (B4)

The shared Wasm heap is fixed at 512 MiB and cannot grow after the AudioWorklet
shares it. Project I/O permits an Artifact of up to 64 MiB, but a Project-valid
Artifact is not automatically Web-runtime-playable: decoded float PCM copied
across 64 Pads can exceed the wasm32 address space. Stage 6 resolves that gap
with explicit Host capability limits rather than changing Project Truth:

| Resource | Stage 6 Web limit |
| --- | ---: |
| imported WAV bytes | 1,048,576 bytes |
| decoded frames per assigned Pad | 240,000 frames (5 seconds at 48 kHz) |
| decoded float PCM in one Prepared Sample Bank | 67,108,864 bytes (64 MiB) |
| decoded float PCM across all live, pending, and retiring Banks | 134,217,728 bytes (128 MiB) |

The heap budget is:

| Reservation | Bytes |
| --- | ---: |
| all Prepared Sample Banks | 134,217,728 |
| Cooked Snapshot PCM and bounded decode scratch | 100,663,296 |
| WasmFS, OPFS bridge, and storage staging | 67,108,864 |
| thread stacks, static data, queues, Capture Ring, and Trigger Outcome Ring | 33,554,432 |
| general C++ heap and safety reserve | 201,326,592 |
| **fixed total** | **536,870,912** |

The Web Host passes immutable `RuntimePreparationLimits` into the
Application Facade. Artifact byte length is checked from Project metadata before
a full read, decoded frame count is checked before float Bank allocation, and
the aggregate Bank budget is reserved before construction. The Host never
parses Project files to enforce these limits.

An oversized import or Snapshot preparation returns the Host-local
`WEB_RUNTIME_RESOURCE_LIMIT` error with `resource`, `observed`, and `limit`
details. `project.open` and `project.inspect` remain available for an otherwise
valid oversized Project; only the unsupported import or runtime publication is
rejected. The prior active Bank remains unchanged. These limits are emitted in
the Product/Host manifest and `host.status`, are covered at exact boundary and
boundary-plus-one values, and do not alter `lmdj.project.v1`.

If allocation fails while all declared limits are satisfied, the Host enters
`failed` with an internal error and Web Proof fails. An out-of-memory condition
is never permission to grow memory, discard Pads, shorten samples, or silently
reduce a published Bank.

### 7.3 Worker ownership

The Application object, Project writer lease, OPFS mount, Runtime Snapshot, and
control-side Realtime Session state are created and destroyed in the Dedicated
Control Worker. The browser main thread never calls synchronous Project I/O.

The main thread is limited to APIs that require the Window or a direct user
gesture, including `AudioContext` activation and DOM input handling.

### 7.4 Cross-origin isolation

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

The lease is the §6.3 workspace-metadata lock file and its exclusive
SyncAccessHandle. The Host does not wait indefinitely, steal a lease, open a
writable shadow copy, or use a wall-clock stale timeout. Browser/Worker failure
releases the handle; the multi-tab conformance test must prove the next Worker
can then acquire it without deleting or rewriting the lock file.

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
3. The Host opens a Project and requests a Runtime Snapshot through the Facade
   with the immutable §7.2 preparation limits.
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
  → exactly one sequence-addressed runtime outcome is published
```

The Trigger path exposes two distinct facts:

1. `trigger` returns an admission response after `enqueue()`. A rejected
   Trigger returns the exact `EnqueueResult`; an accepted Trigger returns its
   monotonically increasing `sequence` and `status: "enqueued"`.
2. After dequeue, the audio callback publishes exactly one
   `RuntimeTriggerOutcomeEvent` for that sequence to a product-neutral bounded
   Trigger Outcome Ring.

The Stage 6 outcomes are:

```text
voice_started    a free Voice was initialized
voice_capacity   all kRealtimeVoiceCapacity entries were active; no Voice began
```

The active `RealtimeEngine` does not steal a Voice. When all 128 Voice entries
are active it increments `voice_drops` and discards the dequeued Trigger. The
`voice_capacity` outcome makes that drop sequence-addressable instead of
mistaking enqueue acceptance for audible execution.

The Trigger Outcome Ring has capacity 4,096. The Control Worker drains bounded
batches and emits the distribution-private `runtime.trigger_outcomes`
notification containing ordered `{sequence, outcome, runtime_frame}` entries.
An Outcome Ring drop increments `runtime_outcome_drops`, enters `failed`, and
seals an active Take; a diagnostic Host that loses its proof of execution cannot
continue as healthy.

`voice_started` is a C++ runtime fact, not a physical audible-onset fact.
Physical onset remains external evidence.

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

| Current state | Event or completed condition | Next state |
| --- | --- | --- |
| `cold` | Host bootstrap begins | `preflight` |
| `preflight` | mandatory capability checks pass | `storage-ready` |
| `storage-ready` | OPFS mount and Facade construction pass | `core-ready` |
| `core-ready` | Project open and Snapshot preparation pass | `audio-suspended` |
| `audio-suspended` | explicit `audio.activate` succeeds and Worklet acknowledges the current generation | `running` |
| `running` | explicit `audio.suspend` succeeds | `audio-suspended` |
| `running` | browser or device interruption begins | `interrupted` |
| `interrupted` | recovery attempt begins | `recovering` |
| `recovering` | Context runs and Worklet acknowledges without another gesture | `running` |
| `recovering` | browser requires a new gesture | `audio-suspended` |
| any nonterminal state | `host.close` completes cleanly | `closed` |
| any nonterminal state | fatal capability, storage, Worker, Worklet, protocol, or resource failure | `failed` |

`failed` and `closed` are terminal externally visible states. Failure cleanup
still releases Workers, audio resources, OPFS handles, and the writer lease, but
does not relabel the terminal state as `closed`. `recovering` is distinct because
the §11.2 recovery test has three observable conditions and the Host is not
`running` while they are incomplete.

### 11.1 State rules

- Trigger and `take.begin` are rejected before `running`.
- Rejected input is not queued for later replay.
- `audio-suspended` means the Core and Project may be ready while user
  activation is still required.
- `interrupted` stops new Trigger acceptance immediately.
- interruption seals an active Take as `capture_incomplete`; it never resumes
  the same Take after recovery;
- each interruption requires at most one explicit activation before returning
  to `running`; a session may be interrupted and reactivated any number of
  times, which is the normal iPadOS Safari pattern;
- `audio.suspend` is idempotent in `audio-suspended` and rejected in all earlier
  or terminal states;
- `host.close` drains or seals an active Take, flushes committed Project state,
  closes audio, releases the writer lease, and only then reports `closed`;
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
`voice_started` runtime outcome for its sequence.

## 12. Host Protocol

The Host Protocol is a distribution-private transport between the main-thread
diagnostic shell and its same-build Control Worker. It is not a public API, a
cross-version compatibility promise, or a new entry in `contracts/`. Main
thread, Worker, Worklet, Wasm, Product/Host manifest, and asset inventory must
all carry the same Product Build, Web Runtime Host version, and manifest hash.
A mismatch fails before OPFS mount or Project mutation.

`protocol_version` versions the private dispatch schema within Web Runtime Host
`1.0.0`. Mixed protocol versions are never negotiated. If a future external
consumer needs this surface, that work must create a stable Contract ID, schema,
fixtures, conformance tests, and Assembly identity in a separate design.

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
`ok` plus `error {code, message, details}` envelope shape. Facade errors preserve
their Contract error code. Host-local failures use exact codes tested with Web
Runtime Host `1.0.0`, including `UNSUPPORTED_WEB_RUNTIME`, `PROJECT_BUSY`,
`WEB_RUNTIME_RESOURCE_LIMIT`, `HOST_STATE_INVALID`, `HOST_TIMEOUT`, and
`HOST_PROTOCOL_MISMATCH`. Notifications have an `event` field and no
`request_id`.

The transport rejects malformed UTF-8, duplicate request IDs, unknown fields,
unsupported operations, and wrong-state operations. A JSON envelope is at most
65,536 UTF-8 bytes. `asset.import` transfers one ArrayBuffer sidecar rather than
embedding bytes in JSON; its exact maximum is the §7.2 1,048,576-byte import
limit. The envelope declares the sidecar byte length and SHA-256, and the Worker
verifies both before passing an Artifact input to the Facade.

Strict unknown-field rejection removes forward compatibility, so
`protocol_version` is mandatory rather than decorative. A mismatched version or
manifest hash is `HOST_PROTOCOL_MISMATCH`, never a best-effort parse.

Request deadlines use monotonic time and are exact:

| Operation class | Deadline |
| --- | ---: |
| `host.status`, audio state operations, and `trigger` | 1 second |
| Project, Asset, Snapshot, and Take operations | 30 seconds |
| `host.close` | 10 seconds |

A deadline produces `HOST_TIMEOUT` and then `failed`. The Host does not return a
timeout while allowing the same Worker to publish a late Project mutation.

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
operation names are the exact Web Runtime Host `1.0.0` local operator surface,
not a separate public wire Contract.

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
runtime.trigger_outcomes
capture.sealed
```

`snapshot.published` carries the Runtime generation identifier, and
`host.status` reports both the current control-side generation and the
generation last acknowledged by the Worklet. Without an exposed generation the
§11.2 recovery test cannot be evaluated by the Host or asserted by the Browser
Proof.

`runtime.trigger_outcomes` carries a non-empty ordered batch drained from the
Trigger Outcome Ring. Each entry has the admitted Trigger `sequence`, the exact
`voice_started` or `voice_capacity` outcome, and the absolute
`runtime_frame` at which the callback processed it. Sequences are never
coalesced or synthesized by the main thread.

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
opfsSyncAccessHandle
opfsWritableReplace
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
| Voice capacity exhausted after dequeue | publish `voice_capacity` for that sequence and increment `voice_drops` |
| Trigger Outcome Ring drop | enter `failed`; seal active Take |
| Worklet `processorerror` | enter `failed`; seal active Take |
| Capture Ring drop | seal active Take as `capture_incomplete` |
| Worker crash | stop accepting input; restart requires Project reopen |
| Worker unresponsive | typed request timeout, then `failed`; a Worker blocked on an OPFS handle held elsewhere does not crash and must not hang the Host indefinitely |
| declared Web resource limit exceeded | reject the operation with `WEB_RUNTIME_RESOURCE_LIMIT`; retain prior Bank |
| shared heap exhausted within declared limits | enter `failed`; fail Web Proof |
| realized `AudioContext.sampleRate` is not 48 kHz | fail before leaving `core-ready`; never render a 48 kHz Bank at another rate |
| realized Worklet quantum is not 128 frames | fail before leaving `core-ready` |
| audio suspended/interrupted | enter `interrupted`; seal active Take; require recovery and at most one activation |
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
  required by the built Host; no remote or inline script dependency is allowed.

The server applies this exact policy to the Host document:

```text
default-src 'none';
base-uri 'none';
object-src 'none';
frame-ancestors 'none';
form-action 'none';
script-src 'self' 'wasm-unsafe-eval';
worker-src 'self' blob:;
child-src 'self' blob:;
connect-src 'self';
style-src 'self';
img-src 'self';
media-src 'self' blob:;
manifest-src 'self'
```

`'wasm-unsafe-eval'` permits WebAssembly compilation without permitting general
`'unsafe-eval'`. `blob:` is limited to Worker/Worklet bootstrap and local media.
The Browser Proof runs with this policy applied. A Host that passes only when
CSP is absent or weakened is not a passing Host.

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

The Product/Host manifest binds the Product Build, Web Runtime Host SemVer,
private protocol version, complete emsdk/Emscripten identities, fixed heap size,
all §7.2 resource limits, and every content-hashed runtime asset. The main
thread and Control Worker validate the manifest hash before initialization.

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
scripts/core.sh test release stress
scripts/core-coverage.sh check
scripts/web-runtime-lab.sh test
```

CI must retain macOS, Ubuntu, ASan, Coverage, TSan, and Stress lanes.

### 16.2 Web unit and conformance tests

Tests cover:

- Host protocol shape, size, state, and idempotency;
- input mapping and duplicate suppression;
- lifecycle state transitions;
- typed failure mapping;
- OPFS writer lease, sorted iteration, semantic replacement, interruption, and
  restart recovery;
- Project Store and Take Journal Web conformance;
- exact §7.2 resource-limit boundaries and boundary-plus-one failures;
- Event Queue, Trigger Outcome Ring, and Capture Ring memory layout and drops;
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
7. dispatch 500 valid Trigger events and compare every admitted sequence with
   exactly one `voice_started` runtime outcome, proving zero missing, duplicate,
   `voice_capacity`, queue-drop, or Outcome Ring-drop results;
8. begin a Take, dispatch 20 Trigger events inside the Take and one further
   Trigger after `take.stop`, drain, and commit, proving the committed Take
   contains exactly the 20 in-Take events;
9. inspect the committed Project revision and Pattern;
10. restart page and Worker, reopen the same OPFS Project, and republish;
11. exercise suspend/recovery and failure injection;
12. close cleanly with zero runtime queue/capture drops.

Step 7 is bounded by Core constants and must be written against them rather than
against a round number. `kRealtimeQueueCapacity` is 1024 and the Trigger Outcome
Ring capacity is 4096, so 500 undrained admissions and outcomes fit.
`kRealtimeVoiceCapacity` is 128, so fixture duration and dispatch pacing must
keep concurrent Voices below that bound; otherwise the engine reports
`voice_capacity` and the zero-execution-loss assertion correctly fails. The
Proof records the fixture duration and pacing, retains all admitted sequences,
drains all sequence-addressed outcomes, and asserts zero `bank_transition`,
`voice_drops`, queue drops, and Outcome Ring drops. If a Core constant later
changes, this step is re-derived from the new constants, not re-tuned until it
passes.

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
| Project I/O | `0.3.0` | `0.4.0` | adds compatible semantic storage obligations and a Web platform |
| Audio Runtime | `0.3.0` | `0.4.0` | adds a compatible Web AudioWorklet adapter and Trigger Outcome Ring |
| Application Facade | `1.1.0` | `1.2.0` | adds compatible realtime composition and immutable runtime-preparation limits |
| Core CLI | `1.0.2` | `1.0.3` | exact Facade dependency update only |
| Core MCP | `1.0.2` | `1.0.3` | exact Facade dependency update only |
| Native Test Host | `1.0.0` | `1.0.1` | exact Facade/Audio dependency update only |
| Contracts | current | unchanged | the same-build Host transport is private and no public wire Contract changes |
| Providers | current | unchanged | no Provider behavior change |

The Host-forced 48 kHz decision adds no Runtime resampling behavior. A future
resampling design is a separate Audio Runtime version decision and is not folded
into `0.4.0`.

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
implied by the format guarantee. Stage 6 does not add a bundle download or any
other export escape hatch. Export requires a separately approved design,
version decision, and acceptance path.

Stage 6 may add storage metadata outside Project Truth, but it must be
versioned, disposable, and reconstructible.

## 20. Definition of Stage 6 Complete

Stage 6 implementation is complete only when all of these are true:

- B1 through B6 have the locked design resolutions recorded in this document;
- the committed Web Toolchain Conformance gate passes before Product source is
  added;
- the approved implementation plan is fully executed;
- the Formal Web Runtime Host exists in active `apps/` source;
- the Product Assembly lists exact target identities for `1.0.12.0`;
- Emscripten `6.0.5` clean-build reproducibility is verified;
- OPFS create/mutate/restart/recovery behavior is proven through the Facade;
- C++ Audio Runtime renders inside the Wasm AudioWorklet;
- the exact fixed heap and Web preparation-limit boundaries are proven;
- Pointer, Keyboard, and Web MIDI use one Trigger path;
- every admitted Browser Proof Trigger has exactly one sequence-addressed
  runtime outcome with zero Outcome Ring drops;
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
- OPFS obligations are semantic, deterministic iteration is explicitly sorted,
  and the absent directory barrier has a concrete recovery argument (B2).
- Emscripten identities are exact and the combined topology has a committed
  pre-Product conformance gate (B3).
- The fixed heap has exact Web preparation limits and no silent degradation
  path (B4).
- Enqueue admission, runtime outcome, Voice capacity, and physical onset are
  distinct facts (B5).
- The Host Protocol is explicitly same-build private transport rather than an
  undeclared public Contract (B6).
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
- [Emscripten Settings Reference](https://emscripten.org/docs/tools_reference/settings_reference.html)
- [emsdk 6.0.5 release mapping](https://raw.githubusercontent.com/emscripten-core/emsdk/6.0.5/emscripten-releases-tags.json)
- [WHATWG File System Standard](https://fs.spec.whatwg.org/)
- [Web Audio API](https://webaudio.github.io/web-audio-api/)
- [MDN Origin Private File System](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system)
- [MDN FileSystemSyncAccessHandle](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle)
- [MDN crossOriginIsolated](https://developer.mozilla.org/en-US/docs/Web/API/Window/crossOriginIsolated)
