# T3 — Runtime Facade lifecycle

Authority: the B2 plan T3 and the user's 2026-09-09 confirmation of the
epoch/sequence, receipt and callback-drain rules. Base revision:
`6445722d91e34db1cde3f2f997f863388d566a32` (includes T2).

## Scope and decisions

One narrow, Host-neutral Facade owns content validation, resource admission,
immutable preparation, publication and empty/ready/running/draining/stopped
lifecycle. A single serialized control producer and one non-reentrant render
consumer are required. No Project IO, Provider, transport, firmware, FX,
Product Assembly, T4 probe or physical-device acceptance is added.

Each successful start returns an opaque process-local epoch. Commands require
that exact epoch and the next sequence, starting at one. Stale, duplicate and
out-of-order commands are rejected without replay. Queue-full does not consume
the sequence; the original command may retry. Accepted means queued, not yet
applied or audible. Completion is reported only after render consumption;
voice refusal remains distinct. Stop closes callback admission before waiting
for the admitted callback to return; only then may Engine stop/reclaim or
unload execute. Reset empties content and invalidates old commands; counters
never wrap. Hosts must stop invoking render before destroying the Facade.

The receive/validate/prepare stages are one synchronous `load` over borrowed,
complete immutable bytes. Only ready is published at its successful return;
there is no incremental transport/session API in T3. Core retains and returns
the complete published identity. Failed construction leaves no identity or
playback owner. Pending command receipts survive unload/reset until polled;
starting a new epoch requires draining those receipts first.

## Declared files

- `docs/plans/2026-09-09-runtime-facade-lifecycle.md`
- `packages/project-cooker/include/lmdj/cooker/runtime_content_types.hpp`
- `packages/project-cooker/include/lmdj/cooker/runtime_content.hpp`
- `packages/project-cooker/src/runtime_content.cpp`
- `packages/application-facade/include/lmdj/facade/runtime_facade.hpp`
- `packages/application-facade/src/runtime_facade.cpp`
- `packages/application-facade/CMakeLists.txt`
- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- `packages/audio-runtime/src/prepared_sample_bank.cpp`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `tests/core/facade/runtime_facade_test.cpp`
- `tests/core/facade/runtime_facade_stress_test.cpp`
- `tests/core/cooker/runtime_content_test.cpp`
- `CMakeLists.txt`
- `CMakePresets.json`
- `scripts/ci/scope_policy.json` (only if new exact paths require ownership)
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/project-cooker.mdx`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/diagrams/project-cooker.architecture.json`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`
- `apps/docs-site/static/diagrams/project-cooker.html`
- `apps/docs-site/static/diagrams/project-cooker.svg`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

Cooker inspection shares the complete T2 validator before allocating PCM.
The type-only header prevents the Host surface from exposing Snapshot/Engine.
Canonical Pattern preparation avoids an unnecessary overlay merge workspace;
the desktop overlay path retains its existing semantics. Resource reporting
includes encoded input, unique PCM, per-Pad float expansion, fixed Engine,
metadata and preparation workspace, plus explicit Host/platform reserve. It is
not a measurement of allocator overhead or a proof that ESP32 RAM suffices.

## Verification

Lowest tier: separate component tests for complete identity/inspection,
admission budget and failure-to-empty/retry, command rejection and receipts,
epoch/counter exhaustion, silent stopped callbacks and full lifecycle journeys.
Concurrent stress exercises render against stop/drain/unload/reset, with
far-side silence and stale-command rejection. ASan and TSan run the relevant
native tests; runtime startup failure is an explicit evidence gap, never PASS.
Existing cooker/audio/facade tests retain desktop regression coverage. Add new
test targets to coverage registration; exclude busy-spinning stress from the
coverage preset. Run coverage check, dependency/active-tree/ownership tests and
the portal check before shipping. No new global gate or lowered threshold.

### Journey-to-evidence map

| Design transition | Far-side assertion |
| --- | --- |
| empty → receive/validate | Complete-byte limits and every malformed wire case reject; inspection allocates no PCM; empty has no published identity and renders silence |
| validated → ready | Complete Core-retained SHA-256/length equals input; every observed load allocation failure stays empty/silent and a clean retry reaches ready |
| ready → playing | Successful start yields a new opaque epoch; the first Pattern callback produces nonzero output |
| commands → consumption | Before render there is no receipt; afterward exact sequence/epoch and applied/voice-started/refused outcome; full retry consumes the original next sequence once |
| playing → stop/drain | Paused admitted callback prevents finish_stop/unload; resume permits completion, closed/reentrant callbacks are silent, pending commands are cancelled |
| stopped → empty → failed load → retry | Unload removes owners/identity; failed load remains empty/silent; a valid retry plays the Pattern and rejects the preceding epoch |
| reset → reload | Reset stays empty with no identity, retains terminal receipts, and never revives the prior epoch; a new Facade also rejects foreign epochs |

The production-path stress keeps render calls active across 300 complete
generations. The deterministic component uses the existing Engine-only hook
variant; no fake transition or hook enters the production Facade. Transport
disconnect policy, firmware, device output/deadline/underrun and actual RAM
measurements are deliberately not substituted by these native assertions.

### Local verification record

- Dev full build and `scripts/core.sh test dev full`: 132/132 PASS; separate
  `scripts/core.sh test dev stress`: 12/12 PASS. Final Cooker/Facade changes
  were rebuilt and the four affected unit/component/stress registrations passed.
- Final ASan selection (Cooker content, prepared Bank, Engine, Facade component,
  deterministic quiescence and production stress): 6/6 PASS. Final TSan Facade
  selection: 3/3 PASS, including actual execution of the 300-generation stress.
- Final `scripts/core.sh coverage check`: 139/139 tests and all floors PASS;
  overall line/branch 83.83%/70.44%, Facade 87.10%/73.24%, Audio Runtime
  90.47%/81.27%, Cooker 93.24%/86.08%. No floor or budget changed.
- `scripts/docs-site.sh check`: 86 tests, 39 current pages, 10 diagrams/20
  generated outputs and 42 rendered routes/internal links PASS. Existing npm
  dependency advisories remain; this Task does not update dependencies.
- Vendored dependency, active-tree and version checks PASS; staged ownership
  suite 66/66 PASS including new-file and top-level admission.
- Red controls found and fixed two real boundaries: stream hex conversion
  could swallow allocation failure and publish a truncated sample identity;
  inspection resource failure was incorrectly classified as invalid content.
  Unit/component allocation-site sweeps now reject without partial publication
  and preserve successful retry. The initial coverage run caught the latter;
  the fresh final full run above is the completion evidence.

These are local source checks, not remote full-lane, firmware or device proof.
Current-head independent review and actual shipping state belong to the PR.

## Version Management

Version impact: additive Module MINOR capability, staged in source alongside
T2 until the subsequent B2 integration allocates matching Module/Assembly
identities. Contract wire version is unchanged. No Product Build, tag,
snapshot, release or deployment is allocated by T3.
Before any B2 Package/Build distribution, allocate against then-live Module
manifests, lock all consumers and the selected Contract in a fresh Product
BUILD, and freeze its immutable Portal snapshot. This follows the same explicit
staged allocation boundary as the T2 plan; source integration is not a release.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /core/modules/project-cooker/ /core/modules/audio-runtime/
Reason: new public runtime-only lifecycle, resource admission and concurrency
ownership need current pages and corresponding source diagrams.
