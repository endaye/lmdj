# Creator P1: first use and unobstructed navigation

Status: implementation in progress. Issues: #1662, #1663, #1664, #1665.

## Approved product decisions

- Remove the dedicated audio activation button; musical gestures wake audio.
- Supply an original 16-Pad basic drum kit from an independent Cloudflare asset
  Worker, through Creator's same-origin Catalog proxy. Do not ship test fixtures.
- Seed only the first automatically created Project. Manual creation, import,
  duplicate, deletion and undo never silently refill user content.
- Empty Pad press starts capture immediately; release commits. There is no hold
  delay. First microphone permission request prepares capture and asks for a new
  press. Explicit Sample import and file drop remain available.
- System is a subpage of the bottom-right touch workspace. The four physical
  page keys remain; returning restores the creative page and transport continues.

## Task sequence and verification

Each Task is one declared Conventional Commit on an isolated short-lived branch.
Refresh the live integration head before starting the next Task. Do not close
issues on source-only evidence. Every new gate names its defect below.

### T1 — musical gesture audio wake (#1662)

Files: `apps/creator-web/src/app.tsx`,
`src/runtime/input_controller.ts`, `src/state/creator_state.ts`,
`src/components/{pad_surface,physical_controls,capture_panel,sample_surface,sample_controls,candidate_surface}.tsx`
under the Creator root; matching `test/{audio_lifecycle,creator_state,
input_controller,workspace_shell,sample_controls,candidate_surface}.test.*`; all existing
`tests/platform/web/creator/creator_web_*.spec.mjs` activation call sites;
`tests/platform/web/creator/fixtures/creator_audio.mjs`; shared
`tests/platform/web/candidate_journey.mjs` and its Creator registration; this plan; and
`apps/docs-site/docs/hosts/creator-web.mdx`.

Use the existing trusted event token. Wake synchronously in the accepted native
input callback, then await wake before the first admission. Preserve released
one-shots; suppress released gates, cancelled inputs and retired generations.
Coalesce overlapping activation, permit refusal retry, and never treat MIDI Note
bytes as browser activation. Record and MIDI permission clicks share the seam.

Lowest tests: input controller activation/release/cancel/refusal cases, lifecycle,
Creator state and workspace tests, plus TypeScript. Packaged browser journeys
assert the first gesture's real admission and preserve all later journey legs.
Required gates catch lost first presses, duplicate activation/admission, late
sustained playback, stale generation effects and removed-button dependencies.

### T2 — validated per-slot Sound Set acquisition (#1663)

Files: Project IO `soundset_store.hpp/.cpp`, Facade `soundset_catalog.cpp` and
`runtime_facade.hpp/.cpp`, Web Platform protocol/session/type files, their native
and JS component tests, current Project IO / Facade / Platform portal pages.

Add manifest validation, single-slot acquire and install through Facade. Host
fetches only Core-supplied hashes; Core owns license/schema/hash validation,
lineage, target-exclusive quota, revision and replay semantics. Reuse a single
assignment InstallSoundSet transaction. Existing whole-set install remains
atomic. Lowest tests: store partial acquisition and tamper refusal, facade slot
install/replay/quota/conflict, platform request validation. Reject bad bytes before
Truth mutation; distinguish durable commit from Runtime publication.

### T3 — original default kit and independent asset Worker (#1663)

Files: new `products/lmdj/assets/default-kit/` corpus and rights manifest,
`tools/asset-server/` generator/validator/Worker configuration,
`scripts/asset-server.sh`, deployment workflow, Catalog proxy configuration and
route tests, scope ownership, deployment documentation and current portal pages.

Generate sixteen original playable sounds with explicit rights evidence. Serve
immutable content hashes, validated Catalog manifest and health route independently
of Creator. Route through the existing same-origin Catalog proxy and retain CSP.
Lowest tests: deterministic kit generation, manifest/license/hash validation,
route/CORS/cache/error behavior. Live service readiness requires real GET/hash
verification; source tests alone do not demonstrate deployment.

### T4 — same-build offline reopen (#1663)

Files: Creator service-worker source/registration and package generator,
shared asset role definitions, identity validators and package/browser tests,
current Creator and Web Platform documentation.

Cache complete same-build shell, manifest, JS, Wasm and worklets with security
headers. A failed update cannot evict the last complete build; replacement happens
at a safe next open, never mid-performance. Preserve historical asset inventories.
Lowest tests: role compatibility, complete/partial cache replacement and packaged
online-to-offline reopen with stored samples. Catch misleading OPFS-only offline
claims, mixed-build assets and unsafe controller replacement.

### T5 — default Bank A streaming boot (#1663)

Files: Creator boot/controller/state and new streaming initialization journal,
Pad status rendering, associated unit/browser tests, current Creator portal page.

Bind the seed to the exact default Set and first auto-created Project. Download at
most four assets concurrently outside the serial authoring queue; validate and
commit each slot independently. Ready means verified durable commit plus Runtime
publication. Loading/processing/failed is distinct from empty. Persist terminal
ownership so delete/reload/undo never resurrects content; retry revision conflict
only while the owned target remains empty. Lowest tests cover progressive play,
partial failure/retry, reload, deletion, competing edits and manual-project refusal.

### T6 — immediate empty-Pad capture (#1664)

Files: Creator capture controller/buffer/state, input controller, Capture/Sample
and Perform surfaces, sample commit helpers, any minimal Facade/Platform capture
API seam and its tests, product decision/design files, current portal pages.

Pointer/key press starts the remembered mic/master source, release seals and
commits. First mic permission prepares only; require another press. Use the native
post-FX master tap and existing sample ingest path, max 60 seconds, trim leading
strict digital silence only, refuse all-silent take, preserve Undo. Recording
owners are exclusive; Sequence playback may continue. Cancel/blur/navigation
releases resources and retains an explicit save/discard take without auto-commit.
Replace manual Perform resample frame UI while preserving saved replay.
Lowest tests: permission/release races, source ownership, trim/silence/limit,
revision conflict/retry, cancellation and packaged mic/master capture journeys.

### T7 — contextual navigation and System (#1665)

Files: Creator App, mode/state and System/Project/Sample/Provider/MIDI/diagnostics
components, styles, interaction/accessibility/browser tests, current portal page.

Project owns content/library/import/export/Sound Sets; Sample Tools owns Slice.
System owns actual settings, MIDI/devices, Provider management and diagnostics.
Attempt authorization remains next to its action. Keep four page keys, read-only
upper MIDI state, contextual recovery, focus return and uninterrupted transport.
Lowest tests: entry reachability, keyboard/touch focus, permission context and
transport continuity across System navigation.

### T8 — coordinated version settlement and integration proof

Files: live module/Host manifests and generated Assembly identities allocated by
version tooling, immutable canary portal snapshot and version-index records.

Run Creator and Web Runtime proofs sequentially because their build roots are
shared/destructive. Run selected committed-head batch-only lanes and portal check.
Record exact source/artifact identities. Real macOS Chrome, Safari and iPad touch
and audible acceptance remain separate rows; unsupported WebKit is not Safari
acceptance. No release/tag/publication/Creator deployment or Channel promotion is
initiated by this implementation request.

## Version Management

Plan Version impact: none — this document allocates no identity. Feature commits
carry version debt into one explicit settlement Task. Read live manifests at T8;
IO/Facade/Platform additions require MINOR increments, and the Creator offline
asset-inventory change requires a Host MAJOR increment with historical compatibility.
Combine outstanding debt and allocate the next available M2 Product Build through
`scripts/version.py`; do not hand-enter identities. Any allocated testing Build
includes `scripts/docs-site.sh version PRODUCT_BUILD canary` immutable snapshot.

## Documentation impact

Documentation impact: required — current `/hosts/creator-web/`,
`/core/modules/project-io/`, `/core/modules/application-facade/`,
`/core/modules/web-runtime-platform/` and `/platform/web-runtime/` pages and relevant
source diagrams change with their owning Task. Frozen historical snapshots remain
immutable. Run `scripts/docs-site.sh check` for each affected Task.
