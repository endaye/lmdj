# LMDJ DSH-Derived Hardening Goal

> **For agentic workers:** This is a goal document, not an executable
> implementation plan. Each track below exits into its own plan under
> `docs/superpowers/plans/` with its own `## Version Management` and
> documentation-impact declaration before any code is written. Do not
> implement directly from this document.

**Goal:** Adopt three engineering disciplines identified by the 2026-08-19
DeepSeek Harness (dsh 0.1.0-rc.5) architecture study — deterministic Attempt
replay, event-layer contract discipline, and a runtime invariant registry —
while explicitly **not** importing dsh's dynamic plugin loading, default
providers, or plugin-contributed API surface. The closed-world, link-time,
doubly-declared, content-hashed assembly stays exactly as it is.

**Source.** A comparative study of the DeepSeek Harness plugin architecture
("everything is a plugin", Cordis-based, ~213 packages) against this repo's
Provider architecture. The study's conclusion, restated so this document is
self-contained: dsh's value to LMDJ is not its dynamic composition — which
trades away isolation, identity, and reproducibility that LMDJ's product shape
requires — but three disciplines that grew around that dynamism and are fully
compatible with a closed world. Each lands on a gap this repo already knows it
has: spec §12.3 (Job) and §12.4 (Event) of
`docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
are designed but unimplemented; `AttemptStatus` implements two of the spec's
seven states; `ExecutionPolicy` declares `timeout_ms`/`max_attempts` that
`AttemptStore::execute` does not enforce; and only two proof Providers have
ever exercised the provider-sdk's ergonomics.

**Architecture:** This document is documentation only. The tracks it seeds
will touch `packages/provider-sdk`, `packages/application-facade`, a new
`providers/` implementation, possibly a new `packages/` module, and the
architecture portal — each under its own future plan and version declaration.

---

## Track 1 — Deterministic Attempt replay Provider

**What.** A proof-domain replay Provider: it takes a previously recorded
terminal Attempt (the canonical-JSON record under
`<workspace>/attempts/<attempt_id>.json` plus the content-addressed artifacts
it minted) and deterministically re-emits the same outputs through the normal
`ArtifactSink`. Recording is not a new mechanism — it is "run the real
Provider once and keep the Attempt directory".

**Why.** The raw material already exists and is better than what dsh started
with: every terminal Attempt records provider identity (id, version,
source-package sha256, model identity), capability identity, `parameters_sha256`,
and content-addressed inputs and outputs. dsh proved the payoff of treating
the production record as the test fixture: keyless, deterministic CI for
pipelines whose real backends are nondeterministic or remote. When the first
real Providers arrive (stem separation, slicing, remote models), this is the
only path to regression coverage that does not call external services. Built
against the proof domain now, it is cheap; retrofitted after real Providers
ship, it is not.

**Constraints.**

- The replay Provider is an ordinary Provider: its own `providers/` directory,
  source-package hash, `compiled_assembly.cpp` entry, `assembly.json` entry,
  regenerated lock, and a new `BUILD`. No bypass of the Registry, the
  bidirectional policy gate, or explicit selection.
- Replay must fail closed: a record whose artifact hashes do not verify, or
  whose capability identity does not match the request, is `PROVIDER_FAILED`,
  never a silent partial replay.
- This track doubles as the "second real exercise of the provider-sdk"
  probe: the replay capability should deliberately use descriptor features the
  two existing proof Providers do not (multiple output ports, larger
  artifacts), so descriptor expressiveness is tested before a real Provider
  depends on it.

**Exit — met.**
[`2026-08-19-lmdj-attempt-replay-provider.md`](2026-08-19-lmdj-attempt-replay-provider.md).

That plan is **blocked at its Task 0**, and the block is the track's main
finding: the feature is not expressible through the current Provider
interface. `Provider::run` receives a write-only `ArtifactSink` and
content-addressed descriptors with no path and no resolver, so the input half
of `CLAUDE.md`'s "Provider code receives Artifact inputs and an Artifact
output sink" is unimplemented. The gap already has an owner —
[`docs/prd/questions/provider-artifact-byte-access.md`](../../prd/questions/provider-artifact-byte-access.md),
status *待架构设计* — and the replay Provider is recorded there as a second
independent consumer rather than as a new question. Tasks 1–4 wait on that
decision.

## Track 2 — Event-layer contract discipline (rider on spec §12.4)

**What.** Two commitments that bind the future Event-layer implementation,
recorded now while nothing is built:

1. **Dispatch semantics are part of the Contract.** Every event declares, at
   its definition site and in its Contract, whether it is notify-only or an
   interception point, whether listeners are awaited, and in what order.
   dsh's four modes (emit / waterfall / parallel / serial) are the reference
   vocabulary; LMDJ need not adopt all four, but whichever subset exists must
   be declared per event, not left as an implementation detail.
2. **A generated producer/consumer matrix.** Which module emits and which
   Hosts/modules consume each event is generated from source and published
   through the architecture portal with the same freshness gating the portal
   already applies to identity facts. Hand-maintained event tables are
   prohibited from the start, matching the portal's existing "derived, never
   typed" rule.

**Why.** dsh's event bus works at ~60 events and 13 listeners on a single
interception point because these two disciplines were present from early on;
their absence is expensive to retrofit. LMDJ is at the one moment where
adopting them costs a paragraph in a plan instead of a migration. If Facade
interception points are ever wanted (approval, throttling, telemetry around
`provider.run`), they must appear as fixed, enumerated hook points inside the
Facade — never open listener registration from Providers, which would breach
the "Providers extend compute, never API surface" asymmetry.

**Not settled here.** The event taxonomy itself — how spec §12.4's event list
partitions into authoring/Project events, Runtime/Snapshot events, and
Provider/Attempt events, and which contract family versions them — is a
product-level Contract question. Per `CLAUDE.md`, it must be routed through
`docs/prd/open-questions.md` and the decision log, not decided inside the
implementation Task.

**Exit — standing, no work due.** These constraints are inherited verbatim by
whichever future plan implements spec §12.4; that plan owns the taxonomy
decision routing. Nothing is actionable until §12.4 is scheduled, which is the
point of recording the constraints now: they cost a paragraph today and a
migration later.

## Track 3 — Runtime invariant registry

**What.** A small runtime-invariant subsystem that checks relations only
observable in a running system, executed in the `full`/`stress` test tiers
(and available to soak runs), with dsh's exclusion rule adopted verbatim:
anything the type system, load-time validation, or a unit test already
guarantees is *not* a runtime invariant.

**Candidate invariants, all already promised by spec or code comments but
currently unwatched at runtime:**

- Snapshot publish atomicity: a rejected publish leaves the previous Snapshot
  serving, never a torn state (spec §11).
- Attempt ledger consistency: every terminal Attempt record's `minted_outputs`
  agrees byte-for-byte with the content-addressed files under its `artifacts/`
  directory, and no orphan attempt directories exist without a terminal
  record.
- Cross-instance writer exclusion: a second `ProjectStoragePlatform` or
  process is refused with `project_busy` while a lease is held. Note that
  leases are **reentrant within one platform instance** by design, so
  "never two live leases" would be the wrong invariant to check.
- `host-settings.json` canonical form: the file on disk is always byte-identical
  to `canonical_json(settings) + "\n"` after any mutation path.

**Why.** LMDJ's conformance suite is entirely build-time; the only runtime
guards are fail-closed validations at load. dsh demonstrated that a
per-package invariant registry scales to 200+ packages precisely because of
the strict exclusion rule, and that the highest-value checks are cheap ledger
comparisons — the Attempt ledger check above would also convert several
implicit assumptions in `attempt_store.cpp` into observed facts before the
out-of-process `workers/provider-host` makes them harder to observe.

**Whether this is a new `packages/` module or a test-tier harness is a
boundary decision for its own plan** — a new Core Module means root CMake,
module graph, assembly, portal page, and a new `BUILD`, which the plan must
weigh against a `tests/`-owned harness that needs none of that.

**Exit — met, and partly implemented.**
[`2026-08-19-lmdj-runtime-invariant-harness.md`](2026-08-19-lmdj-runtime-invariant-harness.md).

That plan settles the boundary question against a Core Module: a registry
listed in `assembly.json` is inventory-cross-checked at runtime and would bump
the Product Build per invariant added, making the observer part of what it
observes. It is a `tests/` harness.

Its Tasks 1–3 are implemented — `provider.attempt_ledger_invariant` (12
relations), `provider.host_settings_invariant` (4), and
`audio.snapshot_publication_invariant` (6), each carrying corruption cases that
prove the harness can fail. Two of this track's findings are pinned as
executable facts rather than prose: **F1** (an orphan Attempt reservation burns
its id permanently) and **F3** (an orphaned settings lock blocks every write
forever while reads keep succeeding). Task 4 is satisfied incrementally through
those registrations. Deferred with reasons recorded in the plan: the stress-tier
variant of Task 3, the live-Bank identity check, and the fixes for F1–F4.

The adopted exclusion rule removed work rather than decorating the plan — it
struck a host-settings id check that the Registry and `read_host_settings`
already enforce, reduced Snapshot atomicity to counter relations, and dropped
the writer-lease invariant whose phrasing was wrong (corrected above).

---

## Sequencing

Per the current stage sequence (finish Stage 8a/8b, cleanup pass, then
Stage 9):

- **Track 3** is the natural cleanup-pass candidate if the test-harness shape
  is chosen — no assembly identity change, immediate value for the concurrent
  code the stress tier already targets.
- **Track 1** must land before the first real (non-proof) Provider is
  planned, since its entire premise is that recording exists before the first
  nondeterministic backend does.
- **Track 2** has no schedule of its own; it activates whenever spec §12.4 is
  scheduled and costs nothing until then.

## Explicitly rejected imports (anti-goals)

The study is equally clear about what not to copy. These are recorded so a
future reader of "we adopted dsh ideas" does not over-read the scope:

- **No runtime plugin loading, discovery, or hot swap.** The assembly stays
  closed at link time; `assembly.json` stays a whitelist over the compiled
  catalog, never a discovery mechanism.
- **No default Providers and no silent fallback.** `PROVIDER_NOT_FOUND` on
  missing selection remains correct behavior (spec §24 rejection stands).
- **No Provider-contributed API surface.** Providers extend compute only;
  Facade operations, events, and Host affordances remain core-owned.
- **No contract code generation.** The four contract layers keep their
  per-language reimplementation plus independent fail-closed enforcement
  points; dsh's Typert approach binds contracts to one language's compiler.

## Version Management

**Version impact: none.** This is a goal document; it changes no Core Module,
Contract, Provider, Host, Product Assembly, or lock content. Each track's
implementation plan carries its own `## Version Management` section; Track 1
at minimum allocates a new `BUILD` (assembly identity changes), and Track 3's
version impact depends on the module-versus-harness boundary decision.

## Documentation impact

**Documentation impact: none.** This plan adds a planning document only; no
architecture-portal route changes and no manifest-derived facts change. The
portal-facing documentation work (Track 2's generated event matrix, Track 1's
provider page) belongs to the tracks' own plans.
