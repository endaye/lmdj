# Stage 12 Capability / ArtifactSource implementation plan

2026-09-09 status addendum: C-Q1–C-Q5 direction and reference budgets have user
confirmation. Exact public constants and identities still require R1 closure;
see the [dated decision and Task split](2026-09-09-stage12-decision-followups.md).
It supersedes historical readiness below. K2 and Candidate APIs cannot each
reserve SDK 2.0.0 independently; B1/B2 have merged.

Date: 2026-09-08. Status: **draft for review, not implementation authorization**.
Relates to #467 and #472. This retained planning Task changes no product code.

Authority: [revised capability design](../design/2026-08-31-lmdj-stage12-capability-artifactsource-design.md),
[Artifact byte-access decision](../prd/decisions/2026-08-24-provider-artifact-byte-access.md),
[benchmark design](../design/2026-08-31-lmdj-stage12-provider-benchmark-design.md),
and [Candidate design](../design/2026-08-31-lmdj-stage12-candidate-adoption-lineage-design.md)
only as an interface constraint. C-Q1–C-Q5 in the revised design are explicit
approval gates. Do not implement an unresolved Contract/concurrency choice.

## Baseline and independent work

Read-only remote audit on 2026-09-08 found main at
`5eb314f52ea71c879a8a4e00f749135791c16879`, matching this worktree's base.
#467/#471/#472 remain open. #586 is closed and its generator, manifest and
five WAV files are present; `stage12_fixture_corpus_test.py` passes 15 tests.
Stage 10 #431/#436/#438 are complete. Stage 11 #672/#673/#674 and audition
#773 remain open. These are observations, not new release evidence.

The #467 design review can finish independently of Stage 11. **The full SDK
migration is not file-independent:** it changes a Facade execute call, proof
registration identities, transitive module pins, and eventually Assembly.
Do not repeat the umbrella's old claim that every SDK change touches no Stage
10/11 files. Source/schema experiments in an isolated branch do not authorize
landing stale manifests. K2 must reserve a serial integration window with the
Stage 11 owner before committing the live ABI transition.

Work graph:

```text
C-Q1..C-Q5 confirmed + fresh version allocation
  K1 Contract/profile and conformance
    K2 SDK v2 + complete existing-provider migration (serial shared files)
      K3 deterministic reference Provider (unregistered)
        K4 product registration / identity integration (serial Stage 11)
          K5 owner resolver wiring and host acceptance (serial Stage 11)

Independent now: benchmark B1 report validator, B2 onset scorer plans
No dependency on K1/K2/K3 for B1/B2 tool development
```

K labels are local draft identifiers, not allocated GitHub Issue numbers.
[Issue drafts](2026-09-08-lmdj-stage12-issue-drafts.md) have one body per Task.
Before implementation, obtain design decisions and authorized Issue allocation;
use one short-lived isolated worktree, one Task, one Conventional Commit.
Product registration is separate from Provider implementation, and Candidate
adoption remains outside this plan.

## Migration inventory

Re-run these searches at each implementation start; this list is pinned to the
baseline, not a guarantee about future main:

```bash
rg -l 'AttemptStore|public .*Provider|public Provider|AttemptResult run\(' packages providers tests tools products --glob '*pp' --glob '*.py'
rg -l 'provider-sdk|application-facade|web-runtime-platform' packages apps providers --glob module.json
```

| Current location | Required migration / regression |
| --- | --- |
| `packages/provider-sdk/include/lmdj/provider/provider.hpp` | Replace pure virtual three-argument run with approved context; owned inputs; lifetime-safe source/sink |
| `packages/provider-sdk/include/lmdj/provider/{attempt_store,registry,capability}.hpp` and `src/{attempt_store,registry,capability}.cpp` | Execution ingress budget/resolver; validator registration and dispatch; preserve singular Candidate until #471's separate decision; binding, policy and terminal validation |
| `packages/provider-sdk/src/durable_file.{hpp,cpp}` | Reuse existing durability primitives; edit only if C-Q5 proves a gap, with fault-injection evidence |
| `providers/local-proof-{success,failure}/src/provider.cpp` | Migrate both implementations and factory registration values; no v1 default delegate; explicit opaque-output policy; existing source-package digests regenerate from CMake |
| `tests/core/provider/conformance_test.cpp` | CountingProvider, InvalidOutcomeProvider, MultiPortProvider; all execute calls, request fixtures and policies |
| `tests/core/provider/spec_regression_test.cpp` | LeakingProvider, SinkThenFailProvider, OptionalOutputProvider, BlockingFailureProvider, MultiCapabilityProvider; retained callbacks, atomicity, concurrent Attempt isolation |
| `tests/core/provider/{attempt_isolation,attempt_ledger_invariant,host_settings_invariant}_test.cpp` | All execute call sites; terminal histories/duplicate IDs; proof input refs need actual matching owned bytes when bound |
| `tests/core/provider/durable_file_test.cpp` | Preserve fault coverage if durability primitives change |
| `tests/core/facade/assembly_loader_test.cpp` | ProofProvider mock and compiled registration fixtures |
| `packages/application-facade/src/application.cpp` | Current `attempt.run` calls three-argument execute. Migrate deliberately; do not infer a source path from Artifact hashes. K2 may preserve proof-only calls with explicit unavailable owner resolver for bound inputs; K5 supplies real owner access |
| `tests/core/facade/` | Assembly, provider settings, attempt and facade-surface regression; no Candidate adoption command changes |
| `products/lmdj/src/compiled_assembly.cpp` | Existing compiled module/provider identities and registration inventory; changed only in the coordinated identity Task |
| `tools/analysis-bench/` | Absent on this baseline: historical design reference only. Do not restore its Host input bridge |

Do not introduce JobRecord, CandidateIndex, plural AttemptResult candidates,
Project fields or a second Lineage model in K2. #471 proposes those APIs but
has not approved them; coordinate later before consuming the same SDK version.

## Task K1 — formal input/output contracts and conformance

Readiness: blocked on C-Q1, C-Q2 and exact descriptor constants from C-Q3.
No Stage 10/11 functional dependency. Proposed file ownership:

- Create `contracts/capability/sample.slice.v1.json`.
- Create `contracts/slice-points/lmdj.slice-points.v1.schema.json`.
- Create proposed `contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md` after
  C-Q1 approves this binary profile identity (not a JSON Schema for WAV bytes).
  If review selects another name, update this exact file list before K1 starts.
- Create `tests/fixtures/contracts/slice-points/valid.json` and `invalid.json`,
  each a named vector inventory consumed by the conformance test; include
  source-context metadata beside each payload. No generated smoke changes.
- Modify `tests/conformance/schema_contract_test.py` and, only for missing
  Schema keywords used by the new schema, `tests/conformance/json_schema.py`
  with `json_schema_test.py` regression coverage.
- Modify `apps/architecture-portal/docs/contracts/capability.mdx`; create proposed
  `apps/architecture-portal/docs/contracts/artifact-audio.mdx` and
  `apps/architecture-portal/docs/contracts/slice-points.mdx` after naming approval.
- Modify `scripts/ci/scope_policy.json` and `tests/build/ci_change_scope_test.py`
  only if staged new paths lack ownership.

Steps and acceptance:

1. Lock every field in design §10.2; validate the capability instance against
   the unchanged v2 schema, including non-null input profile identity.
2. Add vectors for empty silence, frame 0, final valid frame, EOF, negative,
   fraction, bool, duplicate/descending frames, wrong source/rate, unknown keys,
   duplicate JSON keys, NaN and invalid optional values. Schema tests prove
   shape; contextual fixtures prove source/frame-count checks separately.
3. Canonical serialization round trips without byte drift; rejected examples
   retain exact expected error layer. Contextual validation must not be falsely
   attributed to JSON Schema alone.
4. Run the following after registering all new tests; require nonzero discovery:

```bash
python3 tests/conformance/schema_contract_test.py
python3 tests/conformance/json_schema_test.py
python3 tests/core/provider/stage12_fixture_corpus_test.py
scripts/architecture-portal.sh check
```

Version impact: required for future K1. Proposed output Artifact Schema
`1.0.0`, capability instance Contract version `1.0.0`; input profile identity
and version await C-Q1. `lmdj.capability.v2` remains `2.0.0`.
Documentation impact: required. Affected portal pages:
`/contracts/capability/`, proposed `/contracts/artifact-audio/` and
`/contracts/slice-points/`; confirm route naming with C-Q1 before implementation.
No Product Build is allocated by K1; if tooling requires active Assembly registration of the new
contracts, move that registration into K4 rather than broadening K1 silently.

## Task K2 — SDK v2 and complete existing Provider migration

Readiness: K1, C-Q3–C-Q5 approval, fresh migration/version audit, and explicit
coordination of shared files with Stage 11. This is one coherent ABI migration,
not a succession of commits leaving uncompilable Providers on main.

Files: every existing source/header/test in the migration inventory (excluding
K3's new Provider), `packages/provider-sdk/CMakeLists.txt`,
`tests/core/provider/CMakeLists.txt`, new
`tests/core/provider/artifact_source_test.cpp` and
`tests/core/provider/output_validation_test.cpp`; SDK, proof Provider and
Facade manifests plus transitive pin/compiled identity files identified in
Version Management. Include current SDK/Provider/affected module pages and
`apps/architecture-portal/diagrams/provider-sdk.architecture.json`.
Declare the refreshed exact identity file set before starting; if it requires a
Product Build, this Task also owns that Build's immutable snapshot per policy.
K4 still owns registration of the new sample-slice Provider, not this ABI repair.

Steps:

1. Add approved owner ingress resolver, budget, owning input handles and shared
   callback state. Validate all bindings before any owner read; verify aggregate
   lengths before allocations and hash/length after immutable staging.
2. Migrate every named Provider/mock/call site. Preserve proof behavior with
   honest explicit input availability. Compile a negative v1 Provider fixture
   and assert it cannot satisfy/register the new interface.
3. Register consumer-owned validators, including explicit proof opaque-output
   handling. Refuse missing structured validators at registration; validate all
   present outputs before publication. Propagate only approved declared domain
   failures; injected SDK owner/policy failures keep SDK authority.
4. Test full sequence: reserve → validate inputs → run → stage outputs → byte
   validator → durable publication/terminal → inspect → restart/inspect. Inject
   failure between each persistence step. Assert no visible success/Candidate
   without complete validated bytes and terminal, and no mutation of old terminal
   history. Document the approved crash cleanup outcome, not just happy-path I/O.
5. Test retained source/sink after run, handle after return, owner mutable alias,
   overlapping attempts, invalid occurrence, wrong-port/same-hash duplicates,
   aggregate budget exact/+1, arithmetic overflow, input unavailable/mismatch,
   output count/size/Schema failures and Provider exceptions. A failed sink call
   must poison the attempt according to C-Q4 even if Provider ignores it.

Verification:

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --preset dev -N -R '^provider\.'
ctest --preset dev -R '^(provider\.|facade\.)' --output-on-failure
scripts/core.sh test dev stress
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
bash scripts/verify-core-dependencies.sh
scripts/architecture-portal.sh check
```

Register new lifetime/concurrent tests in appropriate tiers; `stress` execution
is required when concurrency changes, with sanitizer runs retained separately.
Do not call an empty regex run proof. Version impact: required, SDK MAJOR
proposal `2.0.0` and cascade below. Documentation impact: required. Affected
portal pages: `/core/modules/provider-sdk/`, `/providers/local-proof/`,
`/core/modules/application-facade/`, plus every identity route changed by the
fresh cascade. This Task cannot claim complete independence from Stage 11.

## Task K3 — deterministic sample-slice reference Provider

Readiness: K1/K2, approved C-Q2 algorithm/parameters and C-Q3 platform limits.
It is a reference implementation, not automatic production selection.

Files: create `providers/local-sample-slice/{CMakeLists.txt,module.json}`,
`providers/local-sample-slice/include/lmdj/providers/local_sample_slice/factory.hpp`,
`providers/local-sample-slice/src/provider.cpp`,
`providers/local-sample-slice/include/lmdj/providers/local_sample_slice/validation.hpp`,
`providers/local-sample-slice/src/validation.cpp`,
`tests/core/provider/sample_slice_test.cpp`; modify root `CMakeLists.txt`,
`tests/core/provider/CMakeLists.txt`, ownership routing if necessary; create
`apps/architecture-portal/docs/providers/local-sample-slice.mdx` and update
`apps/architecture-portal/docs/providers/overview.mdx`.

The approved Task must pick one consumer-owned validation module/file set;
recommend the new Provider package's reusable output-validator factory, invoked
by Registry execution rather than trusted because Provider returned success.
Expose this validator independently to tests and future consumers. No SDK code
may depend on this specific Artifact Schema. Confirm that ownership in C-Q1/K1.

Implement the approved integer onset detector using only source handles and
output sink. Do not detect corpus IDs/hashes or return the expected fixture
onsets. Use algorithm-level unseen pulse/silence/overlap inputs as well as the
committed corpus. Require identical bytes across two runs, malformed input
failures with preserved codes, source/rate binding, output required count,
nonempty audio handling, and no source/Project mutation. Score quality with B2
when available; a reference result is valid evidence even if quality is poor.
No threshold that turns this into a selected production Provider is invented.

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --preset dev -R '^provider\.(sample_slice|artifact_source|output_validation|conformance)$' --output-on-failure
python3 tests/core/provider/stage12_fixture_corpus_test.py
bash scripts/verify-core-dependencies.sh
scripts/architecture-portal.sh check
```

Version impact: required, proposed new Provider `1.0.0`; exact provider ID and
source-package identity generated/confirmed in the approved Task. No checkpoint
or Product Build allocation. Documentation impact: required. Affected portal
pages: `/providers/local-sample-slice/`, `/providers/overview/`. Keep the Provider
unregistered in Product Assembly until K4.

## Task K4 — product registration, versions and current Portal

Readiness: K3, reviewed benchmark evidence and explicit decision to include the
reference Provider, fresh main and Stage 11 #673 integration coordination.
Not ready for independent implementation now. A source-only smoke pass neither
selects a production Provider nor authorizes a release.

Files: `products/lmdj/{assembly.json,assembly.lock.json,version.json,CMakeLists.txt}`,
`products/lmdj/src/compiled_assembly.cpp`, affected Module/Host/Provider manifests
and registration factories, `tools/web-runtime/runtime-identity.json` and its
existing generator output set, `tests/core/facade/assembly_loader_test.cpp`,
`tests/conformance/{module_graph,version_lock,schema_contract}_test.py`, current
Portal `/assembly/lmdj/`, `/product/capability-map/`, `/providers/overview/`,
`/contracts/capability/`, affected module routes and source diagrams; immutable
snapshot files generated only by the stable portal version command. Refresh
and declare exact files after the allocation audit; never handwrite digests.

Register schema and Provider identities, pin all dependencies, regenerate
Assembly lock and Runtime identity using repository-owned tooling, update
current capability availability honestly, freeze the allocated Product Build's
snapshot under the canonical clean-source procedure. Validate real repository
identity, not only a fixture clone. Run version verification, module graph,
lock/schema conformance, complete product proof, and portal check. Inspect
post-merge snapshot provenance only after separately authorized merge.

K4 registers the implementation identity, but must not auto-select it for users
or describe a usable Host slicing journey before K5. Current Portal separates
registered Provider conformance from missing owner wiring and adoption/UI.
The existing typed missing-input refusal remains visible until owner wiring.

```bash
python3 scripts/version.py verify --version-file products/lmdj/version.json
python3 tests/build/version_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/schema_contract_test.py
scripts/core.sh proof
scripts/architecture-portal.sh check
```

Run `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL` with the
actually allocated values only, on the clean integration source commit; retain
its generated files in the same integration PR. The generator requires a
clean integration source commit before snapshot generation. At K4 allocation,
split this family into K4a (identity allocation) and K4b (generated snapshot),
each one implementation Task and one Conventional Commit, delivered in the
same integration PR. K4b owns only the exact generator output set; K4a owns
the mutable source/identity files above. Never send K4a as a standalone PR
that leaves its Build without a snapshot. Apply the same two-Task sequence
if K2 or K5 needs a Product Build; allocate its snapshot child explicitly.

Version impact: required; exact Product Build/Channel and new baseline-dependent
versions are **unallocated** until the audit. Documentation impact: required,
routes above. No tag, release, publication, deployment or Channel promotion is
part of this Task. Rollback is a separate corrective Build or previously
verified immutable deployment; never reuse or move allocated identities.

## Task K5 — real owner resolver wiring and Host acceptance

Post-K4 owner API, permission surface, exact-file proposal and per-Host journey
review: [K5 owner-resolution proposal](2026-09-09-stage12-k5-owner-resolution.md).
The proposal is not yet an approved implementation or completed acceptance.

Readiness: K4 plus reviewed ownership API and Stage 11 Facade/Creator file
coordination. This is a separately planned follow-up, not hidden in K2.

Files to declare after ownership review: `packages/application-facade/` public
config/header and execute implementation, Artifact owner public read API in
its actual owning module (not guessed here), `tests/core/facade/` attempt tests,
Host bindings only where required by the approved resolver injection, current
Facade/Host pages and diagrams, identity cascade/snapshot if allocated. Refine
this into exact files and versions before authorizing implementation.

Acceptance must cross Host → Facade → owner resolver → SDK → Provider →
validated terminal → inspect → Host restart → inspect. Check hash **and length**,
unavailable input, corrupt bytes, wrong binding, permissions, no filesystem
paths in request parameters, zero Project/revision change, no Candidate adoption,
and no claim of a usable production slicing journey without matching owner
wiring. Run
`core.sh configure/build`, Facade/Provider tests, affected CLI/MCP/native/Web
journeys, version checks and portal check. Platforms unavailable locally are
explicit gaps, never inferred passes. Product-facing slicing/preview/adoption
UI remains #471's separate plan.

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --preset dev -N -R '^(provider\.|facade\.|host\.)'
ctest --preset dev -R '^(provider\.|facade\.|host\.)' --output-on-failure
python3 tests/conformance/module_graph_test.py
python3 tests/conformance/version_lock_test.py
scripts/architecture-portal.sh check
```

Before starting, map each approved Host journey to its actual nonempty test
registration/command (including Web/native platform-specific commands); the
regex alone does not prove every Host was exercised.

Version impact: required at future integration; allocate against the actual
post-K4 baseline. Documentation impact: required. Affected portal pages:
`/core/modules/application-facade/` plus actual owner and affected Host routes.
The owner-read API and all new production Host wiring remain separately
unapproved; C-Q1–C-Q5 do not authorize that integration. K5 is deliberately
gated; an exact-file plan is a prerequisite,
not a claim of current executability.

## Version Management

Version impact: none **for this retained planning commit**. No active manifests,
Contract files, Product identity, Channel, lock or snapshots change.

Future implementation impact must be allocated before each Task. Baseline
manifest values read from main, with proposed semantic direction:

| Component | Observed baseline | Future allocation rule |
| --- | --- | --- |
| provider-sdk | 1.1.4, api_version 2 | MAJOR proposal 2.0.0 for replacement run ABI; numeric api_version reviewed separately |
| local-proof-success/failure | 1.0.5 each | Update dependency to SDK v2 and factory values; breaking Provider implementation interface warrants MAJOR proposal 2.0.0, subject to policy review |
| application-facade | 3.0.0 | Re-evaluate exported Provider types/config; MAJOR if public API breaks, otherwise PATCH for dependency-only migration; Stage 11 allocation takes precedence |
| web-runtime-platform | 3.0.0 | Pin actual Facade target; determine bump by exported changes |
| core-cli/core-mcp/native-host | 3.0.0 each | Pin actual Facade target; independent Host SemVer assessment |
| creator-web/web-runtime-host | 3.0.0 each | Pin web-runtime-platform target; no unsolicited feature claims |
| foundation/authoring-domain/project-io/project-cooker/audio-runtime | 0.3.0 / 2.0.0 / 2.0.0 / 1.1.0 / 3.0.0 | No feature change here; do not reverse Stage 11's later allocations |
| new slice Provider/output Schema/Capability instance | absent | proposed 1.0.0 initial identities after design approval |
| WAV profile | absent formal profile | C-Q1 determines exact identity and initial version |
| Product Build / Channel | derive from `products/lmdj/version.json` at integration | No number reserved by this draft; K2/K4/K5 audit collisions and freeze any allocated Build's snapshot |

Re-run dependency closure over every `module.json`, Assembly/lock and compiled
component manifest. Do not merely edit SDK's manifest while factories and locks
still report old versions. K1 compatibility vectors distinguish Schema shape
from source-context validation; K2 breaks the old execution ABI without fallback;
Project Contracts and Lineage do not change in this workstream.

Tag names/target/message are not allocated; tagging requires a separate exact
candidate plan and verified target under version policy. No tag or remote mutation
is authorized here. Rollback retains existing immutable identities and uses a
new corrective change; no tag/Build reuse. Existing runtime manifests remain
untouched in this planning Task.

## Documentation Impact

Documentation impact: none for this commit. Reason: retained unapproved design,
implementation sequencing and Issue drafts do not change current Portal facts.
The future Tasks above name required routes and must update their current pages
and source diagrams in the same Task. Check portal before this documentation
commit because the revised design records concrete source facts and #467 asks
for it; this does not create a snapshot or production publication.

## This planning Task's declared files and verification

One reviewable documentation commit owns exactly:

- revised `docs/design/2026-08-31-lmdj-stage12-capability-artifactsource-design.md`;
- this plan;
- `docs/plans/2026-09-08-lmdj-stage12-benchmark-tools.md`;
- `docs/plans/2026-09-08-lmdj-stage12-issue-drafts.md`;
- `docs/quality/2026-09-08-stage12-readiness-audit.md`.

Validate relative Markdown links and named existing source paths, inspect each
requirement against actual code, run the existing 15-test smoke corpus suite,
portal check, and staged new-path ownership via
`python3 tests/build/ci_change_scope_test.py`; inspect complete staged diff and
`git diff --cached --check` before Conventional Commit. Local Issue drafts are
not remotely created Issues. C-Q1–C-Q5 remain unapproved until explicit review;
this commit cannot by itself satisfy #467's approved-design acceptance.
