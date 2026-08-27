# LMDJ Long-Material Bank Shared Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved D1 long-material resource model — a Bank-shared prepared-PCM quota with no per-Pad cap, ingest (Host tier) / prepared (Core tier) split, long-file import with Host-side trim, a read-only remaining-quota query, and the deterministic `BANK_QUOTA_EXHAUSTED` failure class — as a testable Product Build with an immutable Portal snapshot.

**Authority:** [2026-08-26 D1+D2 decision](../../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md) (merged in [#339](https://github.com/endaye/lmdj/pull/339)). D2 requires no implementation: samples carry no BPM, global BPM drives the sequencer only, and the realtime engine stays zero-DSP — that is current behavior. The future per-Pad offline time-stretch capability is [#347](https://github.com/endaye/lmdj/issues/347) and is out of scope here.

**Architecture:** The quota model — validation rule, failure class, publication accounting — lives in Core and is Host-independent; every number is injected per Host manifest through the existing `lmdj::audio::RuntimePreparationLimits` structure. `PreparedSampleBank` already stores one independent `std::vector<float>` per slot and already accumulates per-Bank and live-bank byte accounting, so the decision's "variable-length layout" is satisfied by the existing storage: the implementation removes the per-Pad frame ceiling rather than rewriting the layout. Application Facade gains the read-only remaining-quota query and routes Captured and Imported selections through one deterministic commit validation. The Web Host supplies the ingest tier: long files decode via `decodeAudioData` in the JS heap (never the 512 MiB Wasm heap), trim happens Host-side, and only the committed selection crosses into Core.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, Emscripten `6.0.5`, Wasm AudioWorklet, JavaScript ES modules, React, TypeScript, Vitest, Playwright, Python 3.11, Docusaurus Architecture Portal.

## Global Constraints

- The approved decision is the D1+D2 decision file above. Any conflict returns to product review; an implementation Task must not silently choose a different semantic.
- Full-source retention and post-commit re-trim stay with the open [`project-bin-storage-model.md`](../../prd/questions/project-bin-storage-model.md) question. Until it is decided, re-trimming requires re-import.
- The prepared tier remains mono float PCM (the existing stereo→mono downmix is unchanged). The byte quota therefore admits ≈349.52 s of prepared material per Bank regardless of source channel count; the decision's "≈174.76 s stereo" figure was the conservative bound stated before this layer truth was pinned. Moving to stereo prepared PCM would be a new product decision, out of scope.
- The 512 MiB fixed Wasm heap (`ALLOW_MEMORY_GROWTH=0`) is unchanged. No Task may raise it.
- Execute each Task on a short-lived `feat/<task>` or `docs/<task>` branch in an isolated worktree. One Task, one Issue, one reviewable Conventional Commit, one Pull Request.
- Functional Tasks keep active manifests and the Product Build at their current values until Task 4's integration boundary. A Product Build allocated for testing requires an immutable Portal snapshot; Product Build or Assembly changes cannot declare `Documentation impact: none`.
- `PreparedSampleBank` publication changes touch lock-free/concurrent code: the `stress` tier must be run explicitly (`scripts/core.sh test dev stress`) in every Task that touches it, in addition to `full`.
- Every fail-closed message added or changed by this plan carries both `why` and `remedy` per the [`gate-failure-readability`](../../../.agents/pitfalls/gate-failure-readability.md) pitfall.
- Before every Task commit: run the Task-specific tests and `scripts/architecture-portal.sh check`; stage only declared files; run `git diff --cached --check`; inspect the staged and committed file lists.
- This plan authorizes local commits only. Push, Pull Request creation, merge, tag, Release, deployment, and Channel promotion require separate authorization per Task.

## Locked Quota Model Constants and Manifest Keys

All implementations use these values verbatim. Numbers are Web-manifest values; the Core structures carry no literals.

```text
RUNTIME_SAMPLE_RATE            = 48000            (unchanged)
BANK_QUOTA_BYTES               = 67,108,864       (decoded_float_pcm_bytes_per_bank, unchanged)
TOTAL_LIVE_BYTES               = 134,217,728      (decoded_float_pcm_bytes_total, unchanged)
BANK_QUOTA_FRAMES              = 16,777,216       (mono frames; = BANK_QUOTA_BYTES / 4; ≈349.52 s)
IMPORTED_WAV_BYTES             = 68,157,440       (65 MiB; re-scoped: commit-selection Artifact cap)
INGEST_SOURCE_BYTES            = 104,857,600      (100 MiB; NEW: Host ingest source-file cap)
INGEST_DECODED_FRAMES          = 43,200,000       (15 min @ 48 kHz; NEW: Host ingest decode cap)
CAPTURE_BUFFER_SECONDS         = 60               (unchanged Host capture value)
WASM_HEAP_BYTES                = 536,870,912      (unchanged)
decoded_frames_per_pad         = RETIRED          (removed from manifest, gate, limits struct)
```

Key semantics:

- `imported_wav_bytes` is re-scoped from "import file cap" to "commit-selection Artifact byte cap". 65 MiB covers a full-quota stereo PCM16 selection (16,777,216 frames × 2 ch × 2 B = 64 MiB payload) plus header allowance, so the Bank quota — never this byte cap — is the binding constraint.
- `ingest_source_bytes` and `ingest_decoded_frames` are Host-tier ingest bounds, declared in the manifest for identity/portal derivation but enforced in the Host (creator-web) before and after `decodeAudioData`. They bound JS-heap residency, not Core state.
- Commit admission is byte-exact: requested prepared bytes = selection mono frames × 4; admitted iff `requested ≤ BANK_QUOTA_BYTES − Σ(other Pads' prepared bytes in the target Bank)`, with `TOTAL_LIVE_BYTES` continuing to bound live/pending/retiring publication exactly as today.

## Locked Error Contract Shape

`lmdj.error.v1` gains one enum member, `BANK_QUOTA_EXHAUSTED` (Contract SemVer `1.0.0 → 1.1.0`, additive). The C++ `lmdj::foundation::ErrorCode` enum gains the matching member. Payload shape:

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

## Locked Facade Surface

```cpp
struct RemainingBankQuota {
  std::uint8_t bank;            // 0–3
  std::uint64_t quota_bytes;    // manifest decoded_float_pcm_bytes_per_bank
  std::uint64_t consumed_bytes; // Σ prepared bytes of the Bank's occupied Pads
  std::uint64_t remaining_bytes;
  std::uint64_t remaining_frames; // remaining_bytes / 4 (mono float @ 48 kHz)
};

foundation::Result<RemainingBankQuota> query_bank_quota(std::uint8_t bank) const;
```

The query and commit validation must agree byte-for-byte: a selection the query admits commits; one frame over fails with `BANK_QUOTA_EXHAUSTED`. Hosts consume the query only through the Facade; no Host recomputes quota from bundle contents.

## Dependency Order

```text
#342 (this plan)
  → Task 1 (#343) Core quota model + error Contract
      → Task 2 (#344) long-sample runtime + stress   [parallel with Task 3 after #343]
      → Task 3 (#345) Facade query + unified validation
          → Task 4 (#346) Web ingest tier, manifest, Creator UX, version integration, snapshot
```

## Task 1 (#343): Bank-Shared Quota Model in Core with BANK_QUOTA_EXHAUSTED

**Scope:** `packages/foundation`, `packages/audio-runtime` (limits + preparation validation), `packages/project-cooker` (verify no cap duplication), `contracts/error/`.

- [ ] Add `BANK_QUOTA_EXHAUSTED` to `lmdj::foundation::ErrorCode` (`packages/foundation/include/lmdj/foundation/error.hpp`) and its string mapping.
- [ ] Bump `contracts/error/lmdj.error.v1.schema.json`: add the enum member, set `x-lmdj-contract-version` to `1.1.0`; update `tests/conformance/schema_contract_test.py` vectors.
- [ ] Remove `maximum_decoded_frames_per_pad` (and `allows_decoded_frames_per_pad`) from `RuntimePreparationLimits`; keep `maximum_artifact_bytes`, `maximum_prepared_bank_bytes`, `maximum_live_bank_bytes`.
- [ ] In `prepared_sample_bank.cpp::from_snapshot`, drop the per-Pad frame check; keep artifact-byte, per-Bank, live-bank, and overflow checks. Failure at the Bank boundary reports `BANK_QUOTA_EXHAUSTED` with the locked payload shape and a why+remedy message.
- [ ] Audit `project-cooker` for any duplicated per-Pad frame ceiling; remove or route through the shared accounting helpers in `runtime_preparation_limits.hpp`.
- [ ] Tests: exact-boundary unit/component tests at `BANK_QUOTA_BYTES` (n admits, n+4 rejects), per-Pad-free admission of a single full-quota sample, rejection leaves the prior live Bank byte-identical, and `TOTAL_LIVE_BYTES` behavior unchanged at 134,217,728 / +1.
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress`.

**Acceptance:** validation is `quota − Σ(other Pads)` and nothing else; no `decoded_frames_per_pad` symbol remains in Core; error Contract 1.1.0 vectors pass.

## Task 2 (#344): Long-Sample Runtime Publication under Stress

**Scope:** `packages/audio-runtime` (engine + publication), stress tier.

- [ ] Verify `RealtimeEngine` voice arithmetic (positions, trim, loop points, ramps) is exact for samples up to `BANK_QUOTA_FRAMES` (`std::uint32_t` positions hold to 4.29 G frames; assert no intermediate narrows).
- [ ] Keep the per-slot `std::vector<float>` storage; document in the module README that the decision's variable-length requirement is satisfied by this existing layout (no arena rewrite).
- [ ] Stress-tier tests: publish/retire Banks containing one ≈full-quota Pad and 15 empty Pads under concurrent trigger load; assert live/pending/retiring accounting against `TOTAL_LIVE_BYTES`, no lock acquisition on the realtime read path, and no torn reads (ASAN full + stress on Linux and macOS gates).
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress` locally before commit.

**Acceptance:** a full-quota single-Pad Bank plays, publishes, and retires cleanly under stress; realtime path remains lock-free.

## Task 3 (#345): Facade Remaining-Quota Query and Unified Commit Validation

**Scope:** `packages/application-facade`, host parity in `apps/core-cli`, `apps/core-mcp`, `apps/native-host` (error surface only).

- [ ] Add `query_bank_quota` with the locked surface; consumed bytes derive from the same accounting helpers Task 1 centralizes, never a second formula.
- [ ] Replace the per-Pad frame checks at `application.cpp:2428` and `application.cpp:3157–3174` with the quota validation; Captured and Imported selections flow through the identical path.
- [ ] Emit `BANK_QUOTA_EXHAUSTED` with the locked payload; the message names the Bank, remaining frames/bytes, and the three remedies (shorten, free a Pad, target another Bank).
- [ ] Parity tests: CLI, MCP, and Native Host observe identical error payloads via the Facade only; query-then-commit agreement test (admit at exactly `remaining_frames`, reject at `remaining_frames + 1`).
- [ ] Run `scripts/core.sh test dev full`.

**Acceptance:** query and commit agree byte-for-byte across all Hosts; no Host parses bundle contents for quota.

## Task 4 (#346): Web Ingest Tier, Manifest, Creator UX, Version Integration, Snapshot

**Scope:** `packages/web-runtime-platform`, `apps/web-runtime-host`, `apps/creator-web`, `products/lmdj`, portal current pages, immutable snapshot.

- [ ] Manifest `resource_limits`: remove `decoded_frames_per_pad`; set `imported_wav_bytes = 68,157,440`; add `ingest_source_bytes = 104,857,600` and `ingest_decoded_frames = 43,200,000`. Update `manifest_gate.cpp` pins (`manifest_gate.cpp:161–167`) and the `control_runtime.cpp` limit mapping (`control_runtime.cpp:370`, `:628–630`) with why+remedy gate messages.
- [ ] creator-web import flow: file picker/drag → enforce `ingest_source_bytes` → `decodeAudioData` on the Host `AudioContext` (JS heap) → enforce `ingest_decoded_frames` → waveform/preview/trim on the decoded source → encode the selection to PCM16 WAV → the existing commit path.
- [ ] Replace the `COMMIT_MAX_FRAMES` constant (`apps/creator-web/src/capture/capture_buffer.ts:3`) with the Facade quota query: capture and import trim ceilings become `min(source frames, remaining_frames)`; the trim UI draws the selectable ceiling before commit.
- [ ] Quota-exhausted presentation: surface Bank, remaining time, and per-Pad usage from the error payload; non-blocking, selection preserved.
- [ ] Version integration (single boundary, after the functional steps merge): bump module/Host SemVers per **Version Management**, run a fresh version audit, allocate the next verified unused Product Build (do **not** reuse `1.0.37.0`, reserved by Stage 9), regenerate Assembly identity, update current portal pages.
- [ ] Immutable snapshot as a separate clean-commit step: `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`.
- [ ] Tests: Vitest for ingest bounds and trim ceilings; Playwright long-import journey (whole-song file → trim → commit at quota boundary → quota-exhausted refusal path); `scripts/core.sh test dev full`; `scripts/architecture-portal.sh check`.

**Acceptance:** a >65 MiB-source song imports and trims with no Wasm-heap growth; commit at exactly the remaining quota succeeds and one frame over fails legibly; the Product Build carries a verified immutable snapshot.

## Version Management

Exact numbers are re-verified against protected `main` at each Task's merge time; the allocations below are the plan's declared intent.

| Component | Current | Allocated | Task |
| --- | --- | --- | --- |
| `lmdj.error.v1` Contract | 1.0.0 | 1.1.0 (additive enum member) | 1 |
| audio-runtime | 0.5.1 | 0.6.0 (limits semantics, long-sample publication) | 1–2 |
| project-cooker | 0.3.0 | 0.4.0 only if its sources change in Task 1; otherwise none | 1 |
| application-facade | 1.4.5 | 1.5.0 (new query, validation change) | 3 |
| web-runtime-platform | 0.3.6 | 0.4.0 (manifest keys and gate) | 4 |
| web-runtime-host | 1.2.15 | 1.3.0 | 4 |
| creator-web | 1.5.5 | 1.6.0 | 4 |
| Project Contract | v2 (v3 pending Stage 9) | none — no schema change | — |
| Product Build | 1.0.36.0 | next verified unused at Task 4 integration (fresh exact-tag audit; `1.0.37.0` is reserved by Stage 9 and must not be consumed) | 4 |

Version impact of this plan document itself: none — documentation only; every impact above is paid by its implementation Task.

## Documentation Impact

This plan: required — the plan itself.

Implementation Tasks: required — affected portal routes are `/core/modules/audio-runtime/`, `/core/modules/application-facade/`, `/core/modules/web-runtime-platform/`, `/core/modules/project-cooker/` (only if Task 1 touches it), `/contracts/error-module-version/`, `/platform/web-runtime/`, `/hosts/creator-web/`, `/hosts/web-runtime/`, `/assembly/lmdj/`, `/product/workflows/`. Task 4 carries the Product Build snapshot obligation; Tasks changing Product Build or Assembly cannot declare `Documentation impact: none`.

## Issue Map

- [ ] #342 — this plan (docs)
- [ ] #343 — Task 1, blocked by #342
- [ ] #344 — Task 2, blocked by #343
- [ ] #345 — Task 3, blocked by #343 and #344
- [ ] #346 — Task 4, blocked by #345

Umbrella: [#341](https://github.com/endaye/lmdj/issues/341). Related, not gated by this plan: [#347](https://github.com/endaye/lmdj/issues/347) (future offline time-stretch design).

## Final Acceptance Boundary

The umbrella closes when all four Tasks are merged, the full and stress suites pass on the integrated head, and the allocated Product Build has a verified immutable Portal snapshot. Release, deployment, and Channel promotion remain separate authorization boundaries outside this plan.
