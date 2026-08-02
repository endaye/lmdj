# Formal Native Host Acceptance — 2026-08-03

## Outcome

Automated, sanitizer, coverage, Product Proof, source-audit, objective CoreAudio
device, and operator-audibility gates pass for 5B. On 2026-08-03, the operator
replied `正常` after a dedicated replay and confirmed that the two physical Pad
sounds alternated low/high correctly and that the old low Voice remained audible
while a new high Voice began after live reload.

This candidate remains `1.0.11.0 · canary`. No push, Pull Request, merge, tag,
Release, deployment, publication, or Channel promotion occurred.

## Tested identity and environment

| Item | Evidence |
| --- | --- |
| Branch | `feat/formal-native-host` |
| Runtime target SHA | `685d95649fb6e1b8e309a843e06fd0849fd571d3` |
| Product / Host | Product `1.0.11.0`, Native Host `1.0.0` |
| Machine | MacBook Pro `Mac16,8`, Apple M4 Pro, 48 GB |
| OS | macOS `26.5.2` (`25F84`) |
| Output route | MacBook Pro Speakers, built-in, default output, 2 channels, 48 kHz |
| Project | `00000000-0000-4000-8000-000000000001` |
| Revisions | ready `9`; reload `10`; reset reload `11`; committed `12` |
| Audible replay | ready `12`; reload `13`; reset reload `14`; operator replied `正常` |
| Startup Pattern | `00000000-0000-4000-8000-000000000010` |
| Recorded Take | `00000000-0000-4000-8000-000000000210` |
| Recorded Pattern | `00000000-0000-4000-8000-000000000013` |

The physical fixture used two generated two-second, mono, PCM16, 48 kHz
one-shots:

- Pad `0:0`: low 220 Hz, Artifact SHA-256
  `2fc3e4d37d85bcc4c4f806f7cecd189a353763612df0cef0240d33e374bbf2bc`;
- Pad `0:1`: high 880 Hz, Artifact SHA-256
  `66aa0cdf7829109cfd8b9cec8c8ed16fd22794573460cc0f3708084e9124168e`.

The exported JSONL evidence is:

- [Host requests](evidence/2026-08-03-formal-native-host-requests.jsonl)
- [Host responses](evidence/2026-08-03-formal-native-host-responses.jsonl),
  SHA-256
  `f8031aac2f05bb84464a3d7f0b9f263b8917f0345abd5b284c0ff1be33e4b3da`

## Automated quality gates

| Gate | Result |
| --- | --- |
| `scripts/core.sh test dev full` | PASS, 40/40 |
| `scripts/core.sh test dev stress` | PASS, 2/2 |
| `scripts/core.sh test asan full` | PASS, 40/40; no ASan/LSan defect |
| `scripts/core.sh test asan stress` | PASS, 2/2 |
| `scripts/core.sh test tsan full` | PASS, 21/21 direct native tests; no TSan report |
| `scripts/core.sh test tsan stress` | PASS, 2/2 |
| `scripts/core.sh coverage check` | PASS; overall lines `80.01%`, branches `68.93%` |
| Authoring Domain coverage | PASS; lines `89.51%`, branches `89.04%` |
| Audio Runtime coverage | PASS; lines `89.81%`, branches `85.20%` |
| `scripts/core.sh proof` | PASS; 28/28 selected CTests, CLI/MCP parity, Golden Audio, Take recovery, package |
| Product Proof identity | `1.0.11.0`, `canary`, Assembly lock `MATCH` |
| Dependency / active-tree gates | PASS |
| Product version / Assembly lock | PASS |
| `git diff --check` | PASS |

TSan selects the `native` execution label so its runtime is never injected
into Python or shell Host processes. Its four-times timeout allowance changes
only the instrumentation budget, not the workload or test tier.

## Requirement completion matrix

| Design requirement | Automated evidence | Physical evidence | Result |
| --- | --- | --- | --- |
| All-Pad immutable Runtime Snapshot and one deduplicated decode pass | Cooker component and determinism tests | ready reports two resolved fixture Pads | PASS |
| Typed Facade Snapshot preparation and atomic Take batch append | Facade, Project I/O, fault-matrix, CLI/MCP parity tests | 21 events persisted and Project inspect confirmed them | PASS |
| PCM16 Bank preparation and fixed-slot publication | Prepared Bank and Engine component tests | three accepted/applied Bank generations, zero publish drops | PASS |
| Old Voice pins old Bank; new Trigger uses new Bank | Bank swap component test | operator heard the old low Voice continue while the new high Voice began after reload | PASS |
| Capture only successful Voice starts with exact bounded ring behavior | Capture component and 100,000-event TSan stress | 21 captured equals 21 persisted; zero Capture drops | PASS |
| Formal Host strict JSONL, single Trigger producer, Facade-only Project access | Host source-boundary and black-box tests | real Host transcript contains 54 requests and 55 responses | PASS |
| Failed reload, Writer failure, revision conflict, stop/restart recovery | Host black-box failure paths and CoreAudio cleanup matrix | stop rejected Trigger; restart completed exactly one new Voice | PASS |
| Assembly, module versions, distribution, Product Build | version, graph, lock, package, and Proof gates | ready reports Host `1.0.0`, Product `1.0.11.0` | PASS |
| Apple Project→Snapshot→CoreAudio→Capture closed loop | Apple smoke plus all automated gates | objective seven-step run completed on built-in speakers | PASS |
| Two-Pad audible mapping and uninterrupted live reload | Not automatable | operator replied `正常` after the dedicated low/high and live-reload replay | PASS |

## Apple physical seven-step gate

| Step | Evidence | Result |
| --- | --- | --- |
| 1. ready | CoreAudio backend; revision `9`; two resolved Pads | PASS |
| 2. Trigger at least 20 times across two Pads | 20 alternating requests accepted; later telemetry has zero queue/voice drops; dedicated replay heard as low/high alternating | PASS |
| 3. Live reload while a Voice is active | low Voice triggered; Project changed to revision `10`; reload applied; new high Voice accepted; reset reload reached revision `11`; dedicated revision `12`→`14` replay audibly confirmed old-low/new-high overlap | PASS |
| 4. record 20+1, stop, commit, inspect | `captured_events=21`, `persisted_events=21`, failures `0`, clean `true`; commit revision `12`; Take and Pattern found | PASS |
| 5. stop/reject/start/no replay | stopped Trigger returned `INVALID_ARGUMENT`; after start exactly one event was enqueued, dequeued, and completed | PASS |
| 6. zero-drop telemetry | queue, Voice, Capture, publish, callback-failure, deadline-overrun, and device-overload counters all `0` | PASS |
| 7. quit | response state `stopped`, process exit `0`, stderr empty | PASS |

## Realtime and failure-path source audit

The callback chain is limited to
`CoreAudioOutputStateMachine::render_callback` → `RealtimeEngine::render`.
The render path and its reachable Bank/Voice/Capture helpers use only fixed
arrays, pre-owned sample pointers, lock-free atomics, bounded loops, and
`FixedSpscQueue::try_pop/try_push`:

- Bank apply changes slot state and atomic identities only. `PreparedSampleBank`
  allocation and conversion happen on the control thread before publication.
- Voice start stores a raw pointer into the current immutable Bank and increments
  its callback-owned active count. Voice completion only changes flags/counters
  and marks a retiring Bank reclaimable.
- Bank reclamation, including the optional/vector destruction, is a separate
  control-thread call and is never reachable from render.
- Capture push writes a trivially-copyable event into the fixed 4,096-entry
  ring. Overflow increments a counter and changes Capture to `corrupted`.
- The allocation counter test covers initial render, callback-boundary Bank
  apply, Voice completion, and Capture push, and observes zero allocations and
  zero deallocations.
- No callback-reachable path contains a mutex, condition variable, sleep,
  filesystem, Project Store, Take Journal, Provider, network, JSON, exception,
  locale, iostream, logging, or Application Facade call.
- `CaptureWriter` is a separate `jthread`; its vector allocation, sleep, mutex,
  Facade batch append, and persistence are therefore outside the callback.
- CoreAudio stop disables the callback, drains in-flight calls, then disposes;
  an unprovable cleanup enters terminal `failed` and quarantines callback
  storage instead of freeing potentially reachable memory.

Failure review found the following explicit outcomes:

- Capture overflow → `corrupted`, stale events cleared on restart;
- Writer append failure → Take sealed as `capture_incomplete`;
- failed Snapshot reload → old Bank remains current and playable;
- revision conflict → Take sealed as `revision_conflict`;
- stop → queued events and active Voices cancelled, pending Banks made
  reclaimable, old events not replayed after restart;
- terminal CoreAudio cleanup failure → restart rejected and process exits by
  the terminal path without releasing callback-reachable storage.

## Evidence boundary

The stdin and `--no-device` paths prove portable Host behavior; they do not
prove Keyboard, MIDI, or Pointer input latency. This Apple gate proves the
current Mac's Project→Snapshot→CoreAudio→Capture loop only. Product GUI/input
adapters, physical MIDI/Keyboard/Pointer tests, selective Take rebase,
quantization, Beta/Stable release quality, tag signing, Release publication,
and deployment remain outside 5B.
