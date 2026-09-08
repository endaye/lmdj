# LMDJ Deterministic Attempt Replay Provider Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.
>
> **Read Task 0 before anything else.** Investigation changed this track's
> shape: the feature as originally framed is not expressible through the
> current Provider interface, and the first task raises that as an open
> question rather than coding around it.

**Goal:** Make a recorded Provider execution replayable as a keyless,
deterministic regression fixture, so that when the first real Providers arrive
(stem separation, slicing, remote models) CI can cover them without calling an
external service. This is Track 1 of
[`2026-08-19-lmdj-dsh-derived-hardening.md`](2026-08-19-lmdj-dsh-derived-hardening.md).

**Why now.** The raw material already exists and is unusually good: every
terminal Attempt record carries provider identity (id, version,
source-package sha256, model identity), capability identity,
`parameters_sha256`, and content-addressed inputs and outputs, and a succeeded
attempt keeps its minted bytes on disk under
`<workspace_root>/.lmdj-workspace/attempts/<id>/artifacts/<sha256>`. "Recording"
is therefore not a new mechanism — it is *run the real Provider once and keep
the directory*. Built against the proof domain now this is cheap; retrofitted
after a nondeterministic backend ships it is not.

**Architecture:** `providers/` plus, depending on how Task 0 resolves,
`packages/provider-sdk`. A new Provider changes Product Assembly identity, so
this Task allocates a new `BUILD` and cannot declare
`Documentation impact: none`.

---

## Task 0 — Resolve how a Provider obtains recorded bytes (BLOCKING)

**This is not an implementation step. It is a question this plan must not
settle on its own.**

### The finding

`CLAUDE.md` states as an architecture invariant:

> Provider code receives Artifact inputs and an Artifact output sink; it never
> receives a mutable Project or Project bundle path.

The output sink half is implemented. **The input half is not.** A Provider
receives only content-addressed descriptors it has no supported way to read
(`packages/provider-sdk/include/lmdj/provider/provider.hpp:16-31`):

```cpp
using ArtifactSink =
    std::function<foundation::Result<foundation::ArtifactRef>(
        std::string port, std::span<const std::byte> bytes,
        std::string media_type)>;

virtual AttemptResult run(
    foundation::AttemptId attempt_id,
    const CapabilityRequest& request,
    ArtifactSink output) = 0;
```

`CapabilityRequest::inputs` is `std::vector<ArtifactBinding>`, and
`ArtifactBinding` is `{port, ArtifactRef}` where `ArtifactRef` is
`{sha256, media_type, byte_length}`
(`packages/provider-sdk/include/lmdj/provider/capability.hpp:91-109`,
`packages/foundation/include/lmdj/foundation/artifact.hpp:12-25`). No path, no
URI, no blob-store handle, and no resolver is passed. `AttemptStore::execute`
never opens an input artifact either: `validate_request`
(`packages/provider-sdk/src/attempt_store.cpp:629-667`) checks hash format,
media-type allow-listing, input-hash uniqueness and port cardinality, and
nothing else. Foundation's only byte-touching helper is
`describe_artifact(path, media_type)`, which hashes a file the caller already
located; it does not resolve a hash to a file.

Two further constraints bound any answer:

- The terminal Attempt record is **explicitly implementation-private**:
  "Their persisted JSON is an implementation-private format, not a versioned
  cross-language Contract"
  (`packages/provider-sdk/include/lmdj/provider/attempt_store.hpp:24-26`),
  enforced by tests asserting the record carries `"format":
  "terminal-attempt-v2"` and no `"contract"` key
  (`tests/core/provider/conformance_test.cpp:364-365`). A Provider parsing
  that file would take a private-format dependency from inside `providers/`,
  which the tree deliberately walls off.
- The provider source-package identity covers **exactly three files** —
  `include/**/factory.hpp` (exactly one match required), `module.json`, and
  `src/provider.cpp`
  (`scripts/version.py` `_provider_source_package_sha256`). A fixture added as
  a fourth file would sit outside the identity model: the lock would not change
  when the fixture changed.

### The three candidate resolutions

| Option | Shape | Cost | Consequence |
| --- | --- | --- | --- |
| **A. Read side in the SDK** | Add an `ArtifactSource` read callback symmetric to `ArtifactSink`, resolving only the request's *declared* input ports | `packages/provider-sdk` minor bump, cascading module versions; capability-gated so no ambient filesystem authority | Makes the stated `CLAUDE.md` invariant actually true; the replay Provider then needs no special power at all |
| **B. Fixture embedded in `src/provider.cpp`** | Recorded bytes as a byte-array literal inside the one file already covered by the source-package hash | No core change; fixture becomes part of `artifact_sha256`, i.e. self-verifying | Works only for small fixtures; a real stem-separation output is megabytes; each new fixture is a new provider version and `BUILD` |
| **C. Fixture root via `parameters`** | Host passes a directory path in `CapabilityRequest::parameters`; provider reads it | No core change | **Recommend against.** Parameters are hashed, never stored, so the record cannot say which fixture was replayed; and it grants ambient filesystem authority to Provider code, which is the opposite of the artifact-port model |

### The question was open — and is now settled

`docs/prd/questions/provider-artifact-byte-access.md` (status *待架构设计*)
owned exactly this gap and recorded that it is **bidirectional**: `ArtifactRef`
carries no Schema provenance, `AttemptStore` has no input Artifact resolver,
and the output side has no read access either, so a Host can only rebuild paths
from the private `.lmdj-workspace/attempts/` layout. It also recorded that the
2026-08-16 analysis-bench prototype's Host injection bridge was a stopgap that
**must not graduate into a formal interface**.

**Settled 2026-08-24** by
[`docs/prd/decisions/2026-08-24-provider-artifact-byte-access.md`](../prd/decisions/2026-08-24-provider-artifact-byte-access.md)
([#206](https://github.com/endaye/lmdj/issues/206)); the question file was
deleted in the same Task, per convention. The ruling: the formal read interface
is a capability-gated `ArtifactSource` in provider-sdk (option A), deliberately
**not implemented yet** — its trigger is the first formal Capability that must
parse structured Artifact bytes. Option C is permanently rejected. Option B is
sanctioned as this track's stopgap, so **this plan proceeds with Tasks 1–4 as
written**, scoped to small proof-domain fixtures.

### What Task 0 must produce

- [x] Add the replay-Provider driver to
  `docs/prd/questions/provider-artifact-byte-access.md` — per
  `docs/prd/open-questions.md`'s convention, a status or content change edits
  only that question's own file. Record that this consumer needs the *input*
  read side specifically, and that its fixture alternative (option B) is what
  makes waiting tolerable.
- [x] Do **not** create a new question file, and do not restate the gap in
  `docs/prd/open-questions.md`, which carries conventions only and no index.
- [x] When the question is settled, the deciding Task writes the decision file
  and deletes the question file in the same commit, per
  `docs/prd/decisions/README.md`. **Done 2026-08-24** by
  [`2026-08-24-lmdj-provider-artifact-byte-access-decision.md`](2026-08-24-lmdj-provider-artifact-byte-access-decision.md):
  decision
  [`docs/prd/decisions/2026-08-24-provider-artifact-byte-access.md`](../prd/decisions/2026-08-24-provider-artifact-byte-access.md),
  question file deleted.
- [x] Only then continue. If the answer is **A**, that SDK work is its own
  Task and its own plan, and this plan resumes afterwards with a Provider that
  needs no privilege. If the answer is **B**, continue with Tasks 1–4 below as
  written, scoped explicitly to small proof-domain fixtures. **Resolved
  2026-08-24:** the decision sanctions **B** for this track now, with **A** as
  the formal interface deferred to its own trigger — so Tasks 1–4 proceed as
  written.

**Why this may not be settled inside this Task.** Expanding what Provider code
can read is a Capability-layer architecture decision, not an implementation
detail, and `CLAUDE.md` is explicit: "Do not silently settle an open
product-level Contract or concurrency question inside an implementation Task."

---

## Tasks 1–4 (assume resolution B; revise if Task 0 answers A)

### Task 1 — The replay capability descriptor probes untouched fields

Both shipped proof Providers declare byte-identical descriptors, so most of
`CapabilityDescriptor` has never been exercised by a *registered* Provider.
This track's secondary purpose is to change that.

- [ ] New capability `proof.replay.v1` (contract version `1.0.0`) declaring,
  deliberately, the fields the two proof Providers leave untouched:
  - `max_output_bytes` **non-zero** — currently `0` on both shipped
    Providers, which means they can only ever emit empty artifacts
    (`attempt_store.cpp:1527-1533` rejects `bytes.size() > max_output_bytes`).
  - **Two output ports**, one `required`, one optional, so the
    required/optional combination is proven on a registered Provider.
  - `determinism` — keep `deterministic`, since replay is by definition
    deterministic; note in the descriptor comment that `seeded` and
    `nondeterministic` remain unexercised on any registered Provider.
  - A concrete `media_types` list on an input port rather than `{"*/*"}`.
- [ ] Descriptor must satisfy every registry rule
  (`packages/provider-sdk/src/registry.cpp:123-186`): port names
  `^[a-z][a-z0-9_]*$`, unique non-empty media types, dotted lowercase
  `schema_id`, semver `schema_version`, `max_count != 0`, non-empty
  `output_artifacts` and `platforms`, `error_codes` a subset of the fixed 13,
  and `implementation->capabilities()` sorted equal to the descriptor ids.
- [ ] Its contract JSON must validate against
  `contracts/capability/lmdj.capability.v2.schema.json` key-for-key, following
  the existing check at
  `tests/core/provider/spec_regression_test.cpp:232-275`.

**Verification:** `ctest -L provider`; the capability-shape test above.

### Task 2 — The Provider, fail-closed on any fixture mismatch

- [ ] `providers/local-proof-replay/` in the mandatory four-file shape:
  `module.json` (5 keys, `dependencies: {"provider-sdk": "1.1.1"}` exactly),
  `CMakeLists.txt` cloned from `providers/local-proof-success/CMakeLists.txt`
  with every identity string substituted, `include/lmdj/providers/
  local_proof_replay/factory.hpp` (exactly one `factory.hpp` in the tree), and
  `src/provider.cpp` carrying the `#error` guard on
  `LMDJ_LOCAL_PROOF_REPLAY_SOURCE_PACKAGE_SHA256`.
- [ ] The CMake manifest string must be reproduced byte-identically by
  `scripts/version.py`'s `_provider_source_package_sha256`, or `version.py
  lock`/`verify` will disagree with the compiled constant. Keys are canonical
  order (`files`, `format`, `provider_id`, `provider_version`), the file array
  is sorted by repo-relative path, and the document ends with `\n`.
- [ ] `run()` compares the request against the embedded fixture and **fails
  closed**: a fixture whose recorded artifact hashes do not verify against the
  embedded bytes, or whose capability identity does not match the request, is
  `ErrorCode::provider_failed` — never a silent partial replay. Note the SDK
  only accepts a provider error when `code == provider_failed` **and** nothing
  was minted (`attempt_store.cpp:1671-1675`).
- [ ] Two facts the sink imposes on any replay: two artifacts with identical
  bytes cannot both be minted in one attempt (`attempt_store.cpp:1581-1591`,
  and `valid_output_bindings` requires unique sha256 across outputs), and the
  returned candidate outputs must be exactly the minted set — no fabrication
  (`same_bindings`, `attempt_store.cpp:1668-1689`).

**Verification:** `ctest -L provider` including a new fail-closed case per
mismatch kind.

### Task 3 — Registration chain and the inventory tests it breaks

Adding a third Provider is not a local change. Every step below is mandatory,
and the last row is the one that surprises.

- [ ] `add_subdirectory(providers/local-proof-replay)` in the root
  `CMakeLists.txt`, after `packages/provider-sdk` and before
  `tests/core/provider`; add any new test target to the coverage list at
  `CMakeLists.txt:76-111` (a missing named target is a `FATAL_ERROR`).
- [ ] `products/lmdj/CMakeLists.txt` links the new static library.
- [ ] `products/lmdj/src/compiled_assembly.cpp` gains an include and a
  `CompiledProvider{id, version, factory, model_identity}` entry.
- [ ] `products/lmdj/assembly.json` gains a `providers[]` entry (exactly the
  4 keys `id`, `version`, `capabilities`, `model_identity`).
- [ ] Regenerate the lock with `python3 scripts/version.py lock` — never by
  hand. Note that editing `compiled_assembly.cpp` changes
  `product_assembly.sha256` even before the provider entry is added.
- [ ] **Update every test that hard-codes the two-Provider inventory.**
  Verified list: `tests/core/facade/c_api_test.cpp:290-293`,
  `tests/host/cli_test.py:261-263`, `tests/host/mcp_stdio_test.py:772-775`,
  `tests/e2e/headless_core_proof.py:490-493` (plus its lock-sha cross-check at
  502-506), `tests/core/facade/assembly_loader_test.cpp:168-201` (positional
  catalog), `:230`, `:263`, `tests/core/provider/conformance_test.cpp:235`,
  `:251`, `tests/core/provider/spec_regression_test.cpp:235`, and
  `apps/architecture-portal/test/repo-facts.test.mjs:31`.
- [ ] Portal page: every provider id in the Assembly Lock must map to exactly
  one page (`apps/architecture-portal/scripts/validate-docs.mjs:50-70`).
  Either extend `apps/architecture-portal/docs/providers/local-proof.mdx`'s
  front-matter provider list or add a page.

**Verification:** `scripts/core.sh test dev full`; `python3
scripts/version.py verify --version-file products/lmdj/version.json`;
`scripts/architecture-portal.sh check`.

### Task 4 — The recording path, documented rather than automated

- [ ] Document how a recording is produced and what of it is comparable. A
  replayed record is **not** byte-identical to the original: `started_at` and
  `ended_at` come from `TimestampSource`, and `provider.{id,version,
  artifact_sha256}` are the replay Provider's. Only `artifacts`,
  `minted_outputs`, `candidate_outputs`, `candidate_ids`, `status` and
  `request.*` can match, so a regression assertion compares that projection,
  not whole files.
- [ ] Note that `candidate_ids` carries the Provider-chosen `CandidateId`
  (both proof Providers use `attempt_id.value()`), so matching a recording
  requires reusing the recorded candidate id, which must satisfy
  `valid_file_id`.
- [ ] Note that a **failed** recorded attempt has no artifacts on disk at all
  (`cleanup_attempt_outputs` plus `remove_all` of the reservation directory,
  `attempt_store.cpp:1728-1735`, `1758-1765`), and its message and details were
  redacted at record time. Only succeeded attempts carry replayable bytes.

**Verification:** documentation review only; no code.

---

## Global Constraints

- The replay Provider is an **ordinary Provider**. No bypass of the Registry,
  the bidirectional policy gate
  (`validate_request`, `attempt_store.cpp:600-705`), or explicit per-capability
  selection. `PROVIDER_NOT_FOUND` on unselected capability stays correct.
- No new granted permission unless unavoidable. `proof.execute` is the only
  permission `assembly.json`'s `provider_policy.granted_permissions` grants;
  reusing it avoids an assembly-policy edit.
- Provider code gains no ambient authority. Whatever Task 0 decides, the
  Provider must not read paths outside what the resolution sanctions.
- This PR will run the **full 15-lane CI matrix** regardless of the
  `providers/` focused mapping, because it necessarily edits root
  `CMakeLists.txt` and `products/lmdj/` — both `full_rules` entries in
  `scripts/ci/scope_policy.json`.

## Version Management

**Version impact: Product Build and Provider.**

- New Provider `local.proof.replay` at `1.0.0` with its own source-package
  hash, recorded in `assembly.lock.json` by `scripts/version.py lock`.
- `model_identity: null`, with the loaded implementation artifact hash
  standing in, per `docs/governance/version-management.md` for pure-code
  Providers.
- Product Assembly identity changes, so `PATCH` is illegal: this allocates a
  new `BUILD` (`1.0.24.0` if it lands next).
- If Task 0 resolves to **A**, `packages/provider-sdk` takes a **minor** bump
  for the added read side, and every module declaring a dependency on it
  updates that pinned version — `tests/conformance/module_graph_test.py`
  requires dependency versions to match the depended module's actual declared
  version.

## Documentation impact

**Documentation impact: required.**

Affected portal pages: `/providers/local-proof` (or a new provider page), and
any Assembly/Lock inventory page that enumerates Providers. A Product Build or
Assembly change may never declare `none`
(`docs/governance/architecture-portal.md`).

## Out of scope

- Automating the recording step as a script or CLI operation. Task 4
  documents the manual path; automation is a later Task if it earns itself.
- Replaying **failed** attempts. Their bytes are gone and their errors were
  redacted at record time; failure isolation is already covered by
  `local.proof.failure`.
- Any real (non-proof) Provider. This track exists so that when one arrives,
  the recording mechanism predates it.
- Job, progress, cancellation, or timeout behaviour. `progress_events` stays
  empty because `Provider::run` has no progress callback at all, and
  `ExecutionPolicy::timeout_ms`/`max_attempts` are declarative today — nothing
  enforces them.
