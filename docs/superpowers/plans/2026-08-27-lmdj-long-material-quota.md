# LMDJ Long-Material Bank Shared Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved D1 long-material resource model — a Bank-shared prepared-PCM quota with no per-Pad cap, ingest (Host tier) / prepared (Core tier) split, long-file import with Host-side trim, a read-only remaining-quota query, and the deterministic `BANK_QUOTA_EXHAUSTED` failure class — as a testable Product Build with an immutable Portal snapshot.

**Authority:** [2026-08-26 D1+D2 decision](../../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md) (merged in [#339](https://github.com/endaye/lmdj/pull/339)). D2 requires no implementation: samples carry no BPM, global BPM drives the sequencer only, and the realtime engine stays zero-DSP — that is current behavior. The future per-Pad offline time-stretch capability is [#347](https://github.com/endaye/lmdj/issues/347) and is out of scope here.

**Readiness:** Implementation is blocked by [#357](https://github.com/endaye/lmdj/issues/357). The 2026-08-27 readiness audit found that the approved 64 MiB per-user-Bank quota does not yet compose unambiguously with the existing 64-Pad `RuntimeSnapshot` / `PreparedSampleBank` generation and the 128 MiB live/pending/retiring publication limit. #357 must merge a durable decision amendment and replace the provisional accounting and ingest-memory inputs below before #343 starts.

**Architecture:** The quota model — validation rule, failure class, publication accounting — lives in Core and is Host-independent; every number is injected per Host manifest through `lmdj::audio::RuntimePreparationLimits`. The current `PreparedSampleBank` already stores one independent `std::vector<float>` per each of 64 slots, so no offset-table or arena rewrite is required; however, its byte counter is generation-wide rather than a four-user-Bank ledger. #357 locks the missing per-Bank, active-generation, and live/pending/retiring accounting semantics. Application Facade then exposes a revision-bound effective-headroom query and routes Captured and Imported selections through the same commit validation. The Web Host supplies the ingest tier: bounded source admission precedes expensive decode outside the Wasm heap, trim happens Host-side, and only the committed selection crosses into Core.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, Emscripten `6.0.5`, Wasm AudioWorklet, JavaScript ES modules, React, TypeScript, Vitest, Playwright, Python 3.11, Docusaurus Architecture Portal.

## Global Constraints

- The approved decision is the D1+D2 decision file above. Any conflict returns to product review; an implementation Task must not silently choose a different semantic.
- #357 is Task 0 and blocks every implementation Task. Its decision amendment must replace every provisional input marked in this plan; an implementation branch may not infer the missing total-accounting, query-consistency, source-format, channel, or decode-memory rules.
- Full-source retention and post-commit re-trim stay with the open [`project-bin-storage-model.md`](../../prd/questions/project-bin-storage-model.md) question. Until it is decided, re-trimming requires re-import.
- The prepared tier remains mono float PCM (the existing stereo→mono downmix is unchanged). The byte quota therefore admits ≈349.52 s of prepared material per Bank regardless of source channel count; the decision's "≈174.76 s stereo" figure was the conservative bound stated before this layer truth was pinned. Moving to stereo prepared PCM would be a new product decision, out of scope.
- The 512 MiB fixed Wasm heap (`ALLOW_MEMORY_GROWTH=0`) is unchanged. No Task may raise it.
- Execute each Task on a short-lived `feat/<task>` or `docs/<task>` branch in an isolated worktree. One Task, one Issue, one atomic reviewable Pull Request, and one squash commit on `main`.
- Ordinary Task branches use one reviewable Conventional Commit. Task 4 is the narrow exception required by the clean-source Portal freeze: its branch records the verified source/Assembly commit first, runs `scripts/architecture-portal.sh version` only from that clean commit, then adds the generated immutable snapshot in a second Task-local commit. The PR remains one atomic diff and is squash-merged once; no manual history rewrite may invalidate snapshot provenance.
- Functional Tasks keep active manifests and the Product Build at their current values until Task 4's integration boundary. A Product Build allocated for testing requires an immutable Portal snapshot; Product Build or Assembly changes cannot declare `Documentation impact: none`.
- `PreparedSampleBank` publication changes touch lock-free/concurrent code: the `stress` tier must be run explicitly (`scripts/core.sh test dev stress`) in every Task that touches it, in addition to `full`.
- Automated browser tests do not prove Safari or iPadOS memory behavior. Physical acceptance is isolated in #359 and blocks umbrella closure, while failures or unavailable measurements remain `unverified`.
- Every fail-closed message added or changed by this plan carries both `why` and `remedy` per the [`gate-failure-readability`](../../../.agents/pitfalls/gate-failure-readability.md) pitfall.
- Before every Task commit: run the Task-specific tests and `scripts/architecture-portal.sh check`; stage only declared files; run `git diff --cached --check`; inspect the staged and committed file lists.
- This plan authorizes local commits only. Push, Pull Request creation, merge, tag, Release, deployment, and Channel promotion require separate authorization per Task.

## Provisional Quota and Ingest Inputs for Task 0

These are the values approved or proposed before the readiness audit. They are inputs to #357, not implementation authorization. #357 must retain, replace, or split each value with byte-exact memory math; downstream Tasks use only the values in the merged amendment. Numbers remain Web-manifest values and Core structures carry no product literals.

```text
RUNTIME_SAMPLE_RATE            = 48000            (unchanged)
BANK_QUOTA_BYTES               = 67,108,864       (decoded_float_pcm_bytes_per_bank, unchanged)
TOTAL_LIVE_BYTES               = 134,217,728      (decoded_float_pcm_bytes_total, unchanged)
BANK_QUOTA_FRAMES              = 16,777,216       (mono frames; = BANK_QUOTA_BYTES / 4; ≈349.52 s)
IMPORTED_WAV_BYTES             = 68,157,440       (65 MiB; re-scoped: commit-selection Artifact cap)
INGEST_SOURCE_BYTES            = 104,857,600      (100 MiB proposal; Host source-file cap)
INGEST_DECODED_FRAMES          = 43,200,000       (15 min @ 48 kHz proposal; Host decode cap)
CAPTURE_BUFFER_SECONDS         = 60               (unchanged Host capture value)
WASM_HEAP_BYTES                = 536,870,912      (unchanged)
decoded_frames_per_pad         = RETIRED          (removed from manifest, gate, limits struct)
```

Task 0 must lock these semantics:

- `imported_wav_bytes` is re-scoped from "import file cap" to "commit-selection Artifact byte cap". 65 MiB covers a full-quota stereo PCM16 selection (16,777,216 frames × 2 ch × 2 B = 64 MiB payload) plus header allowance, so the Bank quota — never this byte cap — is the binding constraint.
- `ingest_source_bytes` and decoded-duration/frame/channel limits are Host-tier bounds, declared in the manifest for identity/portal derivation and enforced before expensive decode whenever the approved format metadata makes that decidable. Post-decode exact checks remain mandatory. The amendment must name supported source containers/codecs, channel bounds, failure behavior, and when decoded buffers are released.
- Requested prepared bytes remain `selection_mono_frames × 4`. Effective commit headroom is the minimum of every applicable approved constraint, including the target user Bank and any active-generation or publication reservation limit. A Bank-only calculation is forbidden when another limit can reject the same unchanged-revision commit.
- `decoded_float_pcm_bytes_total` must be assigned one unambiguous ownership domain: active generation, all user Banks, live/pending/retiring generations, or newly split named quantities. The current implementation's generation-wide counter is not evidence that the approved per-user-Bank model is already implemented.

## Error Contract Requirement

`lmdj.error.v1` gains one enum member, `BANK_QUOTA_EXHAUSTED` (Contract SemVer `1.0.0 → 1.1.0`, additive). The C++ `lmdj::foundation::ErrorCode` enum gains the matching member. #357 decides whether a distinct total/publication failure code is required; it must not mislabel a global reservation failure as target-Bank exhaustion. The Bank-boundary payload has this minimum shape:

```json
{
  "contract": "lmdj.error.v1",
  "code": "BANK_QUOTA_EXHAUSTED",
  "message": "<why: requested N bytes but Bank B has only M bytes free under its 67,108,864-byte prepared-PCM quota> — <remedy: shorten the selection to ≤ K frames, free another Pad in Bank B, or target a different Bank>",
  "details": {
    "bank": 1,
    "requested_bytes": 25000000,
    "remaining_bytes": 12000000,
    "quota_bytes": 67108864,
    "consumed": [{"pad": 3, "bytes": 40108864}, {"pad": 7, "bytes": 15000000}]
  }
}
```

Rejection is deterministic and non-destructive: Project Truth and the live Bank are unchanged, matching the [2026-08-24 non-destructive refusal precedent](../../prd/decisions/2026-08-24-refused-audio-activation-non-destructive.md).

## Facade Query Requirements

#357 must lock an exact request and result type before Task 3 starts. The surface must identify the Project and target Bank, return the Project revision used for accounting, distinguish target-Bank remaining bytes from effective commit remaining bytes, and expose `effective_remaining_frames = effective_remaining_bytes / 4`. The later import/capture commit must carry the same expected revision.

For an unchanged Project revision and unchanged publication reservation state, query and commit validation agree byte-for-byte: a selection at `effective_remaining_frames` commits, while `effective_remaining_frames + 1` (four prepared bytes) fails with the precise approved quota/publication category. Revision or reservation drift produces its own existing conflict/state outcome rather than a false quota promise. Hosts consume the query only through the Facade; no Host parses the Project bundle or recomputes quota.

## Dependency Order

```text
#358 (this plan correction)
  → Task 0 (#357) accounting + Web ingest-memory decision amendment
      → Task 1 (#343) Core quota model + error Contract
          ├─→ Task 2 (#344) long-sample runtime + stress
          └─→ Task 3 (#345) Facade query + unified validation
                    [Tasks 2 and 3 run in parallel after #343]
              → Task 4 (#346) Web ingest tier, manifest, Creator UX, version integration, snapshot
                  → Task 5 (#359) macOS Safari + physical iPadOS memory acceptance
```

## Task 0 (#357): Reconcile Quota Publication and Web Decode-Memory Accounting

**Scope:** PRD/architecture decision amendment only; no product code, manifest, Contract, or version mutation.

- [ ] Reconcile the four 16-Pad user Banks with the current 64-Pad `RuntimeSnapshot` / `PreparedSampleBank` generation and name the exact ownership domain of every byte limit.
- [ ] Provide peak and steady-state memory math for current/pending/retiring generations inside the fixed 512 MiB Wasm heap, including decoded Project/Cooker inputs and temporary preparation allocations.
- [ ] Lock the publication strategy, non-destructive failure categories, exact Facade request/result types, Project revision binding, and query/commit race semantics.
- [ ] Lock Web supported source formats, pre-decode metadata admission, duration/frame/channel bounds, post-decode exact checks, buffer-release lifecycle, and why+remedy failures.
- [ ] Define automated fixtures and the #359 macOS Safari / physical iPadOS Safari memory procedure with exact evidence fields and pass/fail thresholds.
- [ ] Update this plan and #341/#343–#346/#359 with the decided values and surfaces; run `scripts/architecture-portal.sh check`.

**Acceptance:** no provisional input remains; an implementer can calculate the same admission and publication result from the decision, Facade query, and Task tests without choosing a product or concurrency semantic.

## Task 1 (#343): Bank-Shared Quota Model in Core with BANK_QUOTA_EXHAUSTED

**Scope:** `packages/foundation`, `packages/audio-runtime` (limits + preparation validation), `packages/project-cooker` (verify no cap duplication), `contracts/error/`.

- [ ] Start only from the merged #357 amendment and copy its exact accounting fields, ownership domains, failure categories, and values into tests before changing implementation.
- [ ] Add `BANK_QUOTA_EXHAUSTED` to `lmdj::foundation::ErrorCode` (`packages/foundation/include/lmdj/foundation/error.hpp`) and its string mapping.
- [ ] Bump `contracts/error/lmdj.error.v1.schema.json`: add the enum member, set `x-lmdj-contract-version` to `1.1.0`; update `tests/conformance/schema_contract_test.py` vectors.
- [ ] Remove `maximum_decoded_frames_per_pad` (and `allows_decoded_frames_per_pad`) from `RuntimePreparationLimits`; add or rename only the Bank/generation/publication fields approved by #357.
- [ ] In `prepared_sample_bank.cpp::from_snapshot`, drop the per-Pad frame check and replace the current single generation-wide accumulator with the exact #357 ledger. Bank-boundary failure reports `BANK_QUOTA_EXHAUSTED`; any separate generation/publication failure uses its own approved category and why+remedy message.
- [ ] Audit `project-cooker` and Application Facade preparation helpers for duplicated caps; route every layer through shared overflow-checked accounting helpers in `runtime_preparation_limits.hpp`.
- [ ] Tests: for each user Bank, exact boundary admits and one mono frame (`+4` prepared bytes) rejects; a single Pad can consume the entire approved Bank quota; every active-generation and live/pending/retiring boundary from #357 has boundary and boundary-plus-one coverage; every rejection leaves Project Truth and the prior live generation byte-identical.
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress`.

**Acceptance:** Core implements the complete #357 ledger without a Host literal or duplicated formula; no `decoded_frames_per_pad` symbol remains in Core; error Contract 1.1.0 vectors pass.

## Task 2 (#344): Long-Sample Runtime Publication under Stress

**Scope:** `packages/audio-runtime` (engine + publication), stress tier.

- [ ] Verify `RealtimeEngine` voice arithmetic (positions, trim, loop points, ramps) is exact for samples up to the maximum prepared frames approved by #357 (`std::uint32_t` positions hold to 4.29 G frames; assert no intermediate narrows).
- [ ] Keep the per-slot `std::vector<float>` storage; document in the module README that the decision's variable-length requirement is satisfied by this existing layout (no arena rewrite).
- [ ] Stress-tier tests: publish/retire every maximum valid generation shape required by #357, including one ≈full-quota Pad and 15 empty Pads in a user Bank, under concurrent trigger load; assert the approved live/pending/retiring ledger, no lock acquisition on the realtime read path, and no torn reads (ASAN full + stress on Linux and macOS gates).
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress` locally before commit.

**Acceptance:** a full-quota single-Pad Bank plays, publishes, and retires cleanly under stress; realtime path remains lock-free.

## Task 3 (#345): Facade Remaining-Quota Query and Unified Commit Validation

**Scope:** `packages/application-facade`, host parity in `apps/core-cli`, `apps/core-mcp`, `apps/native-host` (error surface only).

- [ ] Add the exact #357 query request/result surface. Target-Bank and effective headroom derive from the same Task 1 accounting helpers, never a second formula; the response includes the Project revision used for the calculation.
- [ ] Replace the per-Pad frame checks currently at `application.cpp:3597–3607` and `application.cpp:4290–4296` with unified quota validation; Captured and Imported selections flow through the identical path and carry the query's expected revision.
- [ ] Emit the precise #357 failure category. A Bank failure names the Bank, effective remaining frames/bytes, and the three remedies (shorten, free a Pad, target another Bank); a generation/publication failure must not masquerade as Bank exhaustion.
- [ ] Parity tests: CLI, MCP, and Native Host observe identical error payloads via the Facade only; with unchanged revision/reservation, query-then-commit admits exactly `effective_remaining_frames` and rejects `effective_remaining_frames + 1`; revision/reservation drift returns its approved conflict/state outcome.
- [ ] Run `scripts/core.sh test dev full`.

**Acceptance:** query and commit agree byte-for-byte across all Hosts under the #357 revision/reservation precondition; no Host parses bundle contents for quota.

## Task 4 (#346): Web Ingest Tier, Manifest, Creator UX, Version Integration, Snapshot

**Scope:** `packages/web-runtime-platform`, `apps/web-runtime-host`, `apps/creator-web`, `products/lmdj`, portal current pages, immutable snapshot.

- [ ] Manifest `resource_limits`: remove `decoded_frames_per_pad`; add the exact artifact, ingest, per-Bank, active-generation, and publication keys/values approved by #357. Update `manifest_gate.cpp`, `control_runtime.cpp`, `packages/web-runtime-platform/CMakeLists.txt`, generated identity inputs, and why+remedy gate messages without hand-entering Product identity.
- [ ] creator-web import flow: file picker/drag → enforce source-byte cap → parse the #357-approved metadata needed for pre-decode duration/frame/channel admission → reject before expensive decode when outside the envelope → `decodeAudioData` outside the Wasm heap → enforce exact post-decode bounds → waveform/preview/trim → encode the selection to PCM16 WAV → existing commit path → release source buffers at the approved lifecycle points.
- [ ] Replace `COMMIT_MAX_FRAMES` (`apps/creator-web/src/capture/capture_buffer.ts:3`) with the Facade effective-headroom query: capture and import trim ceilings become `min(source frames, effective_remaining_frames)` for the returned Project revision; the trim UI draws the selectable ceiling before commit.
- [ ] Quota-exhausted presentation: surface Bank, remaining time, and per-Pad usage from the error payload; non-blocking, selection preserved.
- [ ] Version integration (single boundary after Tasks 1–3 merge): re-audit protected `main`, bump Module/Host SemVers and the error Contract per **Version Management**, allocate the next verified unused Product Build after current `1.0.37.0`, regenerate Assembly identity, and update current portal pages.
- [ ] Commit the complete verified source/Assembly/current-page change, require a clean worktree, then run `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL` and commit only the generated immutable snapshot as the second Task-local commit. Re-run the Portal check on the complete two-commit PR tree; the queue squash is the single `main` commit.
- [ ] Tests: Vitest for pre/post-decode bounds, release lifecycle, effective trim ceilings, and failure copy; Playwright whole-song journey (metadata admission → decode → trim → commit at effective boundary → one-frame-over refusal); `scripts/core.sh test dev full`; `scripts/architecture-portal.sh check`.

**Acceptance:** every #357-approved automated fixture imports or rejects before the specified expensive boundary; source decoding stays outside the fixed Wasm heap; unchanged-revision commit succeeds at exact effective headroom and one frame over fails legibly; buffers release at the approved lifecycle points; the Product Build carries a verified immutable snapshot. This automated acceptance does not close #359.

## Task 5 (#359): Physical Safari Ingest-Memory Acceptance

**Scope:** Exact Product Build from Task 4; macOS Safari and physical iPadOS Safari evidence only.

- [ ] Run the #357-approved normal-boundary and rejection fixtures through import, metadata admission, decode, waveform/preview/trim, commit/refusal, cancel, replace, re-import, and background/recovery cleanup.
- [ ] Record device model, OS/browser versions, Product Build, full Git SHA, fixture hashes and encoded/decoded dimensions, observed peak/released memory, and any page reload or process termination under `docs/release-evidence/`.
- [ ] Verify source decode length is not misreported as Wasm residency and that cancel/re-import/post-commit release does not retain the prior full decoded source.
- [ ] Update the canonical manual-verification ledger. Unsupported, failed, or incomplete rows stay `unverified` and block #341 closure.

**Acceptance:** all #357-required Safari rows pass on the exact Task 4 Build with locatable evidence; browser automation or desktop simulation never substitutes for physical iPadOS.

## Version Management

Current identities below are from protected `main` at `9b5c2929a2cf6cf86ce39e495920b852a01c740d` after Stage 9. #357 must re-audit and confirm the allocation class; Task 4 re-verifies exact unused numbers immediately before integration.

| Component | Current | Allocated | Task |
| --- | --- | --- | --- |
| `lmdj.error.v1` Contract | 1.0.0 | 1.1.0 (additive enum member) | 1 |
| audio-runtime | 1.0.0 | 2.0.0 if the public limits surface removal remains breaking; #357 must confirm | 1–2, integrated in 4 |
| project-cooker | 1.0.0 | 1.1.0 only if its public behavior/sources change; otherwise none | 1, integrated in 4 |
| application-facade | 2.0.0 | 2.1.0 for the additive query; #357 must confirm if another breaking surface is required | 3, integrated in 4 |
| web-runtime-platform | 1.0.0 | 2.0.0 for the breaking manifest-key migration | 4 |
| web-runtime-host | 2.0.0 | 2.1.0 | 4 |
| creator-web | 2.0.0 | 2.1.0 | 4 |
| Project Contract | `lmdj.project.v3` 3.0.0 | none — no Project schema change | — |
| Product Build | 1.0.37.0 | next verified unused at Task 4 integration; never pre-allocate or reuse a consumed number | 4 |

Version impact of this plan document itself: none — documentation only; every impact above is paid by its implementation Task.

## Documentation Impact

This plan: required — the plan itself.

Implementation Tasks: required — affected portal routes are `/core/modules/audio-runtime/`, `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`, `/core/modules/project-cooker/` (only if Task 1 touches it), `/contracts/error-module-version/`, `/platform/web-runtime/`, `/hosts/creator-web/`, `/hosts/web-runtime/`, `/assembly/lmdj/`, `/product/workflows/`. Task 4 carries the Product Build snapshot obligation; Tasks changing Product Build or Assembly cannot declare `Documentation impact: none`. Task 5 updates physical evidence and the canonical manual-verification ledger without changing product identity.

## Issue Map

- [x] #342 — original plan (docs), completed by #353
- [ ] #358 — this readiness correction (docs)
- [ ] #357 — Task 0 decision amendment, blocks all implementation
- [ ] #343 — Task 1, blocked by #357
- [ ] #344 — Task 2, blocked by #357 and #343; parallel with #345 after #343
- [ ] #345 — Task 3, blocked by #357 and #343; parallel with #344 after #343
- [ ] #346 — Task 4, blocked by #357, #344, and #345
- [ ] #359 — Task 5 physical acceptance, blocked by #357 and #346

Umbrella: [#341](https://github.com/endaye/lmdj/issues/341). Related, not gated by this plan: [#347](https://github.com/endaye/lmdj/issues/347) (future offline time-stretch design).

## Final Acceptance Boundary

The umbrella closes only when Task 0 and Tasks 1–4 are merged, the full and stress suites pass on the integrated head, the allocated Product Build has a verified immutable Portal snapshot, and #359 records passing macOS Safari and physical iPadOS Safari evidence. Release, deployment, and Channel promotion remain separate authorization boundaries outside this plan.
