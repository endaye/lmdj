# Web Runtime Host Manual Diagnostic Project Design

Date: 2026-08-05

Status: Approved design; awaiting written-spec review.

Approval:

- The product owner selected explicit diagnostic-project loading (Option A) and
  approved the complete design on 2026-08-05.

## 1. Problem

The Formal Web Runtime Host presents an enabled `Activate audio` control as soon
as startup reaches `audio-suspended`. A fresh browser origin has no open Project
and no published Runtime Bank, however. The controller therefore creates the
real `AudioContext` and AudioWorklet, sends `audio.activate`, and receives
`HOST_STATE_INVALID` because the Control Runtime correctly requires a current
Bank owned by the active Project. The controller then enters terminal `failed`.

This is deterministic in both the Codex in-app browser and ordinary Chrome. It
is not a browser capability failure.

The existing Chromium Proof does not reproduce the human journey. Its helper
creates a Project, imports a WAV, assigns Pad 1, and publishes a Snapshot before
clicking `Activate audio`. The visible diagnostic page exposes none of those
preparation operations. Automated runtime proof remains valid for a prepared
Project, but it does not prove that the shipped diagnostic page is manually
usable.

## 2. Decision

Add an explicit `Load diagnostic project` action. The user must invoke it before
audio activation. The action creates or reopens one browser-local diagnostic
Project, generates a deterministic test tone in memory, assigns it to all 64
Pad Slots, and publishes a current Runtime Snapshot. `Activate audio` remains
disabled until that operation reaches `ready`.

The page does not prepare or mutate Project Truth automatically on load. This
keeps the write user-initiated and separates Project preparation from the
browser-required audio gesture.

## 3. Scope

This change includes:

1. a visible, accessible diagnostic-project control and status;
2. a deterministic in-memory PCM/WAV generator owned by the diagnostic Host;
3. idempotent Project create/open/inspect/import/assign/reload orchestration
   through the existing private Host protocol and Application Facade;
4. activation gating based on successful Runtime Bank publication;
5. retryable preparation errors and existing fail-closed handling for unknown
   mutation settlement;
6. unit, packaged Chromium, distribution, version, Assembly, and Portal proof;
7. a new Product Build and immutable Architecture Portal snapshot before team
   testing.

The change does not add Creator editing, user file import, Project deletion,
sample editing, MIDI Learn, a new public Contract, a new Host protocol version,
deployment, Release, or Channel promotion.

## 4. User Experience

The Runtime controls appear in this order:

1. `Load diagnostic project`;
2. `Activate audio`;
3. `Suspend audio`;
4. `Enable MIDI`.

Diagnostic-project status is one of:

- `idle`: no preparation attempt in this page lifetime;
- `loading`: exactly one preparation attempt owns admission;
- `ready`: Project Truth is open and the matching Runtime Bank is published;
- `error`: preparation failed without an unknown mutation outcome and may be
  retried;
- `restart-required`: the existing fail-closed settlement boundary requires a
  page restart before any retry.

While status is `idle`, `loading`, or `error`, `Activate audio` is disabled.
While `loading`, the load control is disabled and exposes `aria-busy="true"`.
After `ready`, the load control reports `Diagnostic project ready` and audio
activation is enabled. A live status element announces transitions without
putting private Project data into the DOM.

The Host state machine remains unchanged: successful page bootstrap still ends
at `audio-suspended`; diagnostic readiness is a separate UI/controller fact,
not a new Runtime lifecycle state.

## 5. Diagnostic Project

### 5.1 Browser-local identity

The Host stores one descriptor under the versioned browser-local key
`lmdj.web-runtime-host.diagnostic-project.v1`. The descriptor contains only
random UUIDs for the diagnostic Project, initial Pattern, and diagnostic Asset.
It is locator metadata, not Project Truth. The Project bundle opened through
Project I/O remains authoritative.

The descriptor is created before the first `project.open`/`project.create`
attempt so a restart after ambiguous settlement reuses the same identities.
The Host never creates a new descriptor merely because a preparation attempt
failed. This prevents unbounded diagnostic Project accumulation across reloads.

Malformed descriptor data is discarded before any Host request and replaced by
fresh UUIDs. The descriptor contains no user content, paths, audio bytes, or
Project revision.

### 5.2 Deterministic audio

The page generates a short mono, 48 kHz, 16-bit PCM WAV in memory. The tone is
deterministic, bounded below the Web Host import limit, and shaped with short
attack/release ramps to avoid clicks. No WAV, fixture directory, source map, or
test-only asset is added to the production distribution.

The same Asset is assigned to all 64 stable Pad Slots. This makes Pointer,
Keyboard, and MIDI input observable across the complete fixed Pad address space
without adding 64 stored audio assets.

### 5.3 Idempotent preparation

One serialized preparation operation performs:

1. validate or create the local descriptor;
2. attempt `project.open` with its Project ID;
3. on typed `NOT_FOUND`, create the Project with the descriptor's Pattern;
4. inspect authoritative Project Truth;
5. import the deterministic Asset only when absent;
6. assign the Asset only to Pad Slots that are not already correctly assigned,
   advancing `expected_revision` from each authoritative response;
7. call `snapshot.reload` for the diagnostic Pattern;
8. require `runtime_ready: true` and a positive generation;
9. publish controller readiness and enable audio activation.

`DUPLICATE_ID` from a create/open race is resolved by reopening and inspecting
the same Project. The controller never assumes a mutation succeeded from its
request alone; it uses returned revisions and a final authoritative inspect and
Snapshot result.

Reloading the page requires another explicit Load click. That click reopens and
republishes the same diagnostic Project without repeating correct imports or
assignments.

## 6. Failure Semantics

Preparation is synchronously serialized. Repeated Load clicks cannot issue
parallel Project mutations. Audio activation checks `diagnostic_ready` before
creating an `AudioContext` or starting the AudioWorklet, even if invoked through
the controller API rather than the disabled DOM button.

Typed, settled preparation errors set the visible state to `error`, retain only
an allowlisted error code, and leave the Host at `audio-suspended` so the user
may retry. Unknown or late mutation settlement continues to use the existing
`HOST_RESTART_REQUIRED` terminal path; the design does not weaken publication
claim or cancellation safety.

Page hide, Worker failure, Worklet failure, protocol mismatch, and clean close
retain the existing lifecycle rules. Hiding the page invalidates the current
preparation admission. An already claimed Project mutation may still settle
authoritatively, but the controller returns diagnostic preparation to `error`
after the page becomes visible and requires another explicit Load click. That
retry reopens, inspects, repairs only missing state, and republishes the Bank
before it may enable activation.

## 7. Privacy and Distribution

The diagnostic flow performs no network request outside the same-origin Host,
does not request a user file, and does not expose Project contents. Public
diagnostics add only:

- `diagnostic_project_state`;
- `diagnostic_project_error_code` from the existing typed allowlist;
- `diagnostic_project_generation` when positive.

Project, Pattern, Asset, request, command, and storage identities remain absent
from the DOM diagnostics. Existing CSP, manifest integrity, deterministic
inventory, cache, no-follow, and source/fixture rejection rules remain
mandatory.

## 8. Acceptance

Test-driven implementation begins with a failing packaged-browser regression
that performs the visible journey without the hidden `createPreparedProject`
helper:

```text
fresh origin
  -> page reaches audio-suspended
  -> Activate audio is disabled
  -> click Load diagnostic project
  -> diagnostic state becomes ready
  -> click Activate audio
  -> Host state becomes running
  -> click representative Pointer and Keyboard Pads
  -> admitted sequences receive unique voice_started outcomes
```

Additional tests cover:

- all 64 Pad Slots reference the one diagnostic Asset;
- a repeated Load call is serialized and mutation-idempotent;
- reload reopens the same Project and republishes a Bank;
- direct controller activation before readiness does not create an
  `AudioContext`, send `audio.activate`, or terminally fail;
- settled preparation errors remain retryable and privacy-bounded;
- unknown settlement remains `restart-required`;
- packaged inventory contains no diagnostic WAV or test fixture;
- the existing prepared-Project twelve-step journey and lifecycle/failure
  matrix remain green.

Required gates are the targeted Node and Chromium regressions,
`scripts/web-runtime-host.sh proof`, `scripts/web-runtime-lab.sh test`,
`scripts/core.sh proof`, version/Assembly verification, and
`scripts/architecture-portal.sh check`. A real Chrome manual smoke records Load,
Activate, `running`, audible Pad playback, suspend, and recovery. It does not
replace any of the five deferred physical acceptance rows.

## 9. Version Management

- Web Runtime Host: `1.0.0` to `1.1.0`. The new visible diagnostic-project
  preparation capability is backward-compatible but additive, so Host SemVer
  uses MINOR rather than PATCH.
- Product Build: `1.0.14.0` to `1.0.15.0`. The Assembly locks a new Host version;
  Assembly changes require a new BUILD rather than Product PATCH.
- Channel: remains `canary`.
- Application Facade, Audio Runtime, Project I/O, Project Cooker, Contracts,
  Providers, and private Host protocol version: unchanged.
- Tag, GitHub Release, deployment, publication, and Channel promotion: outside
  this change and require separate authorization.

## 10. Documentation Impact

Documentation impact: required.

Affected current Portal routes:

- `/hosts/web-runtime/`;
- `/platform/web-runtime/`;
- `/operations/testing-and-proof/`;
- `/operations/version-and-release/`.

The implementation updates the current Formal Web Host acceptance record,
Product/Host manifests, generated Assembly Lock, Portal current truth, source
diagrams if their facts change, and navigation/inventory tests. Because
`1.0.15.0` is allocated for manual team testing, the implementation creates an
immutable `1.0.15.0` canary Portal snapshot with the exact reviewed revision and
Assembly Lock hash. Existing immutable snapshots, including `1.0.14.0`, remain
unchanged.

## 11. Review Boundary

Approval of this design authorizes implementation planning only. It does not
authorize push, Pull Request creation, merge, tag creation or push, GitHub
Release, deployment, publication, physical-pass claims, or Channel promotion.
