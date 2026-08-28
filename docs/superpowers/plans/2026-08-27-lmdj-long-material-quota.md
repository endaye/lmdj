# LMDJ Long-Material Bank Shared Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved D1 long-material resource model — a Bank-shared prepared-PCM quota with no per-Pad cap, ingest (Host tier) / prepared (Core tier) split, long-file import with Host-side trim, a read-only remaining-quota query, and the deterministic `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` failure classes — as a testable Product Build with an immutable Portal snapshot.

**Authority:** [2026-08-26 D1+D2 decision](../../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md) (merged in [#339](https://github.com/endaye/lmdj/pull/339)) as amended by the [2026-08-28 quota-accounting amendment](../../prd/decisions/2026-08-28-long-material-quota-accounting.md) (#357). D2 requires no implementation: samples carry no BPM, global BPM drives the sequencer only, and the realtime engine stays zero-DSP — that is current behavior. The future per-Pad offline time-stretch capability is [#347](https://github.com/endaye/lmdj/issues/347) and is out of scope here.

**Readiness:** The [#357](https://github.com/endaye/lmdj/issues/357) decision amendment resolves the 2026-08-27 readiness-audit accounting gap: `decoded_float_pcm_bytes_total` bounds one Project revision (equivalently one 64-Pad generation), the per-user-Bank quota is its inner partition, and live/pending/retiring publication residency is the separate named quantity `decoded_float_pcm_bytes_resident` = 2 × total, enforced by the existing publication-owner ledger. Implementation Tasks copy the amendment's values and semantics verbatim; #343 starts only from the merged amendment.

**Architecture:** The quota model — validation rule, failure classes, publication accounting — lives in Core and is Host-independent; every number is injected per Host manifest through `lmdj::audio::RuntimePreparationLimits`. The current `PreparedSampleBank` already stores one independent `std::vector<float>` per each of 64 slots, so no offset-table or arena rewrite is required; its single generation-wide byte counter becomes the amendment's two-level ledger (per-user-Bank plus generation total), while publication residency stays with the publication owner's reclaim→reserve→publish ledger under `maximum_resident_bytes`. Application Facade exposes the revision-bound `sample.quota` effective-headroom query and routes Captured and Imported selections through the same commit validation. The Web Host supplies the ingest tier: bounded source admission precedes expensive decode outside the Wasm heap, trim happens Host-side, and only the committed selection crosses into Core.

**Tech Stack:** C++20, CMake 3.24+, JSON Schema, nlohmann/json, Emscripten `6.0.5`, Wasm AudioWorklet, JavaScript ES modules, React, TypeScript, Vitest, Playwright, Python 3.11, Docusaurus Architecture Portal.

## Global Constraints

- The approved decision is the D1+D2 decision file as amended by the 2026-08-28 quota-accounting amendment. Any conflict returns to product review; an implementation Task must not silently choose a different semantic.
- #357 is Task 0 and blocks every implementation Task. Downstream Tasks copy the merged amendment's accounting domains, surfaces, and values verbatim; an implementation branch may not infer or re-derive a total-accounting, query-consistency, source-format, channel, or decode-memory rule.
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

## Decided Quota and Ingest Values (locked by #357)

These values and ownership domains are locked by the [2026-08-28 amendment](../../prd/decisions/2026-08-28-long-material-quota-accounting.md). Downstream Tasks copy them verbatim. Numbers remain Web-manifest values and Core structures carry no product literals.

```text
RUNTIME_SAMPLE_RATE            = 48000            (unchanged)
BANK_QUOTA_BYTES               = 67,108,864       (decoded_float_pcm_bytes_per_bank; per 16-Pad user Bank at one Project revision)
PROJECT_QUOTA_BYTES            = 134,217,728      (decoded_float_pcm_bytes_total; all four user Banks at one Project revision = one generation)
RESIDENT_BYTES                 = 268,435,456      (decoded_float_pcm_bytes_resident, NEW; live+pending+retiring publication residency = 2 × total)
BANK_QUOTA_FRAMES              = 16,777,216       (mono frames; = BANK_QUOTA_BYTES / 4; ≈349.52 s)
IMPORTED_WAV_BYTES             = 68,157,440       (65 MiB; commit-selection Artifact cap = maximum_artifact_bytes)
INGEST_SOURCE_BYTES            = 104,857,600      (100 MiB; Host source-file cap, checked before reading content)
INGEST_DECODED_FRAMES          = 43,200,000       (15 min @ 48 kHz; Host decode cap, 48 kHz-normalized)
INGEST_CHANNELS                = 2                (Host source channel cap)
CAPTURE_BUFFER_SECONDS         = 60               (unchanged Host capture value)
WASM_HEAP_BYTES                = 536,870,912      (unchanged)
decoded_frames_per_pad         = RETIRED          (removed from manifest, gate, limits struct)
```

Locked semantics (amendment entries in parentheses):

- Ownership domains (A1): `per_bank` and `total` are deterministic Project-Truth quotas at one revision; `total` is simultaneously the byte bound of any single `PreparedSampleBank` generation because a generation materializes all 64 Pads. `resident` is the separate publication-residency envelope owned by the publication owner's existing reclaim→reserve→publish ledger; residency exhaustion is transient Attempt/Host-state backpressure (Web: `WEB_RUNTIME_RESOURCE_LIMIT`, `resource` renamed `resident_pcm_bytes`), retryable by construction (resident = 2 × total), and never one of the two quota error codes. The publication owner must reclaim and satisfy `reserved ≤ resident − total` before starting an expensive cook (A4 pre-check) — this is what keeps the A3 peak math valid in every ordering. Four simultaneously full Banks (256 MiB) are not supported — that is the approved 128 MiB total's inherent meaning.
- `RuntimePreparationLimits` fields (A1.4): `maximum_artifact_bytes` (kept), `maximum_user_bank_bytes` (new), `maximum_generation_bytes` (renamed from `maximum_prepared_bank_bytes`), `maximum_resident_bytes` (renamed from `maximum_live_bank_bytes`); `maximum_decoded_frames_per_pad` and `allows_decoded_frames_per_pad` are deleted.
- Accounting (A2): per-Pad bytes = `prepared_frames × 4` with `prepared_frames = ceil(source_frames × 48000 / source_sample_rate)`; trim never reduces accounting; commit validation excludes the target Pad's current bytes (assignment replaces).
- Heap math (A3): worst in-heap peak is the `from_snapshot` phase at 3 × total + per-Bank = 469,762,048 bytes (448 MiB), leaving a ≤ 64 MiB static envelope inside the fixed 512 MiB heap; steady state is one live generation ≤ 128 MiB and post-publication residency ≤ 256 MiB.
- `imported_wav_bytes` (A8) is the commit-selection Artifact (PCM16 WAV) byte cap. 65 MiB covers a full-quota stereo PCM16 selection (16,777,216 frames × 2 ch × 2 B = 64 MiB payload) plus header allowance, so the Bank/Project quota — never this byte cap — is the binding constraint. Capture uses the identical path and cap.
- Ingest bounds (A7) are Host-tier manifest values enforced before expensive decode whenever the format metadata makes that decidable (WAV, FLAC STREAMINFO, MP4 mdhd exact; MP3 via Xing/VBRI, else CBR estimate, else deferred); post-decode exact checks remain mandatory. Supported containers/codecs, channel bounds, failure copy, and buffer-release lifecycle are locked in A7 §12–16.

## Error Contract Requirement

`lmdj.error.v1` gains two enum members in one additive bump, `BANK_QUOTA_EXHAUSTED` and `PROJECT_QUOTA_EXHAUSTED` (Contract SemVer `1.0.0 → 1.1.0`). The C++ `lmdj::foundation::ErrorCode` enum gains the matching members. The binding constraint is the smaller remaining quantity; on a tie, report `BANK_QUOTA_EXHAUSTED` (an in-Bank remedy fixes both). A global failure must never be mislabeled as target-Bank exhaustion, and neither code is ever used for publication-residency backpressure (A6). The Bank-boundary payload has this minimum shape:

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

The `PROJECT_QUOTA_EXHAUSTED` payload is isomorphic, carrying `project_used_bytes` / `project_quota_bytes` / `project_remaining_bytes` and the four per-Bank usage totals. Rejection is deterministic and non-destructive: Project Truth and the live Bank are unchanged, matching the [2026-08-24 non-destructive refusal precedent](../../prd/decisions/2026-08-24-refused-audio-activation-non-destructive.md).

## Facade Query Surface (locked by #357, A5)

The query operation is `sample.quota` (query kind). The request is exactly `{"operation", "project_path", "slot"}` where `slot` is the existing `{"bank", "pad"}` target-Pad identity (the Bank derives from the slot). The result carries `project_revision`, `slot`, `bank_quota_bytes` / `bank_used_bytes` / `bank_remaining_bytes`, `project_quota_bytes` / `project_used_bytes` / `project_remaining_bytes`, `effective_remaining_bytes = min(bank_remaining_bytes, project_remaining_bytes)`, `effective_remaining_frames = effective_remaining_bytes / 4`, and a `consumed` list of every non-empty Pad in the target Bank with `prepared_bytes` / `prepared_frames`. `bank_used_bytes` and `project_used_bytes` exclude the target Pad's current bytes (assignment replaces); `consumed` includes the target Pad's current value for Host presentation.

Revision binding: the result is valid only for the returned `project_revision`; Captured and Imported selections both carry it through `sample.import.begin`'s existing `expected_revision` field, and drift yields the existing `REVISION_CONFLICT`. Quota derives from Project Truth alone — publication residency never enters query or commit adjudication, so reservation drift cannot exist by construction; publication backpressure is a post-commit transient Attempt state (A4). For an unchanged Project revision, query and commit validation agree byte-for-byte: a selection at `effective_remaining_frames` commits, while `effective_remaining_frames + 1` (four prepared bytes) fails with the binding quota category. Hosts consume the query only through the Facade; no Host parses the Project bundle or recomputes quota.

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

**Scope:** PRD/architecture decision amendment only; no product code, manifest, Contract, or version mutation. Delivered by the [2026-08-28 amendment](../../prd/decisions/2026-08-28-long-material-quota-accounting.md).

- [x] Reconcile the four 16-Pad user Banks with the current 64-Pad `RuntimeSnapshot` / `PreparedSampleBank` generation and name the exact ownership domain of every byte limit (A1).
- [x] Provide peak and steady-state memory math for current/pending/retiring generations inside the fixed 512 MiB Wasm heap, including decoded Project/Cooker inputs and temporary preparation allocations (A3).
- [x] Lock the publication strategy, non-destructive failure categories, exact Facade request/result types, Project revision binding, and query/commit race semantics (A4–A6).
- [x] Lock Web supported source formats, pre-decode metadata admission, duration/frame/channel bounds, post-decode exact checks, buffer-release lifecycle, and why+remedy failures (A7–A8).
- [x] Define automated fixtures and the #359 macOS Safari / physical iPadOS Safari memory procedure with exact evidence fields and pass/fail thresholds (A9).
- [ ] Update this plan and #341/#343–#346/#359 with the decided values and surfaces; run `scripts/architecture-portal.sh check` (plan updated in the amendment Task; Issue bodies are replaced when the amendment merges, before #343 starts).

**Acceptance:** no provisional input remains; an implementer can calculate the same admission and publication result from the decision, Facade query, and Task tests without choosing a product or concurrency semantic.

## Task 1 (#343): Bank-Shared Quota Model in Core with BANK_QUOTA_EXHAUSTED

**Scope:** `packages/foundation`, `packages/audio-runtime` (limits + preparation validation), `packages/project-cooker` (verify no cap duplication), `contracts/error/`.

- [ ] Start only from the merged #357 amendment and copy its exact accounting fields, ownership domains, failure categories, and values into tests before changing implementation.
- [ ] Add `BANK_QUOTA_EXHAUSTED` and `PROJECT_QUOTA_EXHAUSTED` to `lmdj::foundation::ErrorCode` (`packages/foundation/include/lmdj/foundation/error.hpp`) and their string mappings.
- [ ] Bump `contracts/error/lmdj.error.v1.schema.json`: add both enum members, set `x-lmdj-contract-version` to `1.1.0`; update `tests/conformance/schema_contract_test.py` vectors.
- [ ] Remove `maximum_decoded_frames_per_pad` (and `allows_decoded_frames_per_pad`) from `RuntimePreparationLimits`; add `maximum_user_bank_bytes`, rename `maximum_prepared_bank_bytes` → `maximum_generation_bytes` and `maximum_live_bank_bytes` → `maximum_resident_bytes` (amendment A1.4); no other fields.
- [ ] In `prepared_sample_bank.cpp::from_snapshot`, drop the per-Pad frame check and replace the current single generation-wide accumulator with the amendment's two-level ledger: per-user-Bank sums against `maximum_user_bank_bytes` (`BANK_QUOTA_EXHAUSTED`) and the generation total against `maximum_generation_bytes` (`PROJECT_QUOTA_EXHAUSTED`); the binding constraint is the smaller remaining, tie → Bank. Publication residency stays with the publication owner's ledger under `maximum_resident_bytes` and keeps its transient Attempt/Host-state category with a why+remedy message.
- [ ] Audit `project-cooker` and Application Facade preparation helpers for duplicated caps; route every layer through shared overflow-checked accounting helpers in `runtime_preparation_limits.hpp`.
- [ ] Tests: for each user Bank, exact boundary admits and one mono frame (`+4` prepared bytes) rejects with `BANK_QUOTA_EXHAUSTED`; a single Pad can consume the entire approved Bank quota; the generation total admits at exactly 134,217,728 bytes and rejects `+4` with `PROJECT_QUOTA_EXHAUSTED`; the tie case reports `BANK_QUOTA_EXHAUSTED`; residency admits at exactly 268,435,456 bytes and rejects `+4` with the transient publication category; every rejection leaves Project Truth and the prior live generation byte-identical.
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress`.

**Acceptance:** Core implements the complete #357 ledger without a Host literal or duplicated formula; no `decoded_frames_per_pad` symbol remains in Core; error Contract 1.1.0 vectors pass.

## Task 2 (#344): Long-Sample Runtime Publication under Stress

**Scope:** `packages/audio-runtime` (engine + publication), stress tier.

- [ ] Verify `RealtimeEngine` voice arithmetic (positions, trim, loop points, ramps) is exact for samples up to 16,777,216 prepared frames — the full-Bank single Pad approved by the amendment (`std::uint32_t` positions hold to 4.29 G frames; assert no intermediate narrows).
- [ ] Keep the per-slot `std::vector<float>` storage; document in the module README that the decision's variable-length requirement is satisfied by this existing layout (no arena rewrite).
- [ ] Stress-tier tests: publish/retire every maximum valid generation shape required by the amendment — one full-quota 16,777,216-frame Pad with 15 empty Pads in a user Bank, and a full 134,217,728-byte generation — under concurrent trigger load; assert the reclaim→reserve→publish residency ledger against `maximum_resident_bytes` = 268,435,456, no lock acquisition on the realtime read path, and no torn reads (ASAN full + stress on Linux and macOS gates).
- [ ] Run `scripts/core.sh test dev full` and `scripts/core.sh test dev stress` locally before commit.

**Acceptance:** a full-quota single-Pad Bank plays, publishes, and retires cleanly under stress; realtime path remains lock-free.

## Task 3 (#345): Facade Remaining-Quota Query and Unified Commit Validation

**Scope:** `packages/application-facade`, host parity in `apps/core-cli`, `apps/core-mcp`, `apps/native-host` (error surface only).

- [ ] Add the `sample.quota` query exactly as locked in amendment A5 (request `{"operation", "project_path", "slot"}`; result fields and target-Pad-exclusive used-bytes semantics as specified). Target-Bank and effective headroom derive from the same Task 1 accounting helpers, never a second formula; the response includes the Project revision used for the calculation.
- [ ] Replace the per-Pad frame checks currently at `application.cpp:3597–3607` and `application.cpp:4290–4296` with unified quota validation; Captured and Imported selections flow through the identical path and carry the query's revision via `sample.import.begin`'s existing `expected_revision`.
- [ ] Emit the binding failure category per amendment A6. A Bank failure names the Bank, effective remaining frames/bytes, and the three remedies (shorten, free a Pad, target another Bank); a `PROJECT_QUOTA_EXHAUSTED` failure carries project totals plus per-Bank usage and must not masquerade as Bank exhaustion.
- [ ] Parity tests: CLI, MCP, and Native Host observe identical error payloads via the Facade only; with unchanged revision, query-then-commit admits exactly `effective_remaining_frames` and rejects `effective_remaining_frames + 1`; revision drift returns `REVISION_CONFLICT`.
- [ ] Run `scripts/core.sh test dev full`.

**Acceptance:** query and commit agree byte-for-byte across all Hosts under the unchanged-revision precondition; no Host parses bundle contents for quota.

## Task 4 (#346): Web Ingest Tier, Manifest, Creator UX, Version Integration, Snapshot

**Scope:** `packages/web-runtime-platform`, `apps/web-runtime-host`, `apps/creator-web`, `products/lmdj`, portal current pages, immutable snapshot.

- [ ] Manifest `resource_limits` (amendment A10 key set): remove `decoded_frames_per_pad`; keep `decoded_float_pcm_bytes_per_bank` = 67,108,864 and `decoded_float_pcm_bytes_total` = 134,217,728 under their amended semantics; add `decoded_float_pcm_bytes_resident` = 268,435,456, `ingest_source_bytes` = 104,857,600, `ingest_decoded_frames` = 43,200,000, `ingest_channels` = 2; set `imported_wav_bytes` = 68,157,440. Update `manifest_gate.cpp`, `control_runtime.cpp`, `packages/web-runtime-platform/CMakeLists.txt`, generated identity inputs, and why+remedy gate messages without hand-entering Product identity.
- [ ] `control_runtime.cpp` publication ledger (amendment A4): keep the reclaim→reserve→publish order with `maximum_resident_bytes` = 268,435,456 as the ceiling, rename the failure `resource` to `resident_pcm_bytes` with a retry-oriented why+remedy message, and add the A4 pre-check — reclaim, then require `reserved_live_bytes ≤ resident − total` before `prepare_runtime_snapshot` begins.
- [ ] creator-web import flow (amendment A7): file picker/drag → enforce `ingest_source_bytes` before reading content → sniff container (WAV/MP3/M4A-AAC/FLAC only, fail-closed) → pre-decode duration/frame/channel admission where metadata is decidable → `decodeAudioData` on a 48,000 Hz `OfflineAudioContext` outside the Wasm heap → exact post-decode bounds (≤ 43,200,000 frames, ≤ 2 channels) → waveform/preview/trim on the single decoded copy → encode the selection to PCM16 WAV → existing commit path → release the decoded buffer at the A7 §15 lifecycle points (commit success, cancel, replace, Project close, background-eviction recovery).
- [ ] Replace `COMMIT_MAX_FRAMES` (`apps/creator-web/src/capture/capture_buffer.ts:3`) with the `sample.quota` query: capture and import trim ceilings become `min(source frames, effective_remaining_frames)` for the returned Project revision; the trim UI draws the selectable ceiling before commit.
- [ ] Quota-exhausted presentation: surface Bank, remaining time, and per-Pad usage from the error payload; non-blocking, selection preserved.
- [ ] Version integration (single boundary after Tasks 1–3 merge): re-audit protected `main`, bump Module/Host SemVers and the error Contract per **Version Management**, allocate the next verified unused Product Build after current `1.0.37.0`, regenerate Assembly identity, and update current portal pages.
- [ ] Commit the complete verified source/Assembly/current-page change, require a clean worktree, then run `scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL` and commit only the generated immutable snapshot as the second Task-local commit. Re-run the Portal check on the complete two-commit PR tree; the queue squash is the single `main` commit.
- [ ] Tests: Vitest for pre/post-decode bounds, release lifecycle, effective trim ceilings, and failure copy; Playwright whole-song journey (metadata admission → decode → trim → commit at effective boundary → one-frame-over refusal); `scripts/core.sh test dev full`; `scripts/architecture-portal.sh check`.

**Acceptance:** every #357-approved automated fixture imports or rejects before the specified expensive boundary; source decoding stays outside the fixed Wasm heap; unchanged-revision commit succeeds at exact effective headroom and one frame over fails legibly; buffers release at the approved lifecycle points; the Product Build carries a verified immutable snapshot. This automated acceptance does not close #359.

## Task 5 (#359): Physical Safari Ingest-Memory Acceptance

**Scope:** Exact Product Build from Task 4; macOS Safari and physical iPadOS Safari evidence only.

- [ ] Run the amendment A9 fixtures (`LM-OK-SONG`, `LM-OK-BOUNDARY-INGEST`, `LM-REJ-FRAMES`, `LM-REJ-SOURCE`, `LM-REJ-CH`, `LM-OK-COMMIT-BOUNDARY`, `LM-REJ-COMMIT-PLUS-4B`, and the lifecycle sequences) through import, metadata admission, decode, waveform/preview/trim, commit/refusal, cancel, replace, re-import, and background/recovery cleanup, with the A9 §19 measurement method and §21 pass/fail thresholds.
- [ ] Record device model, OS/browser versions, Product Build, full Git SHA, fixture hashes and encoded/decoded dimensions, observed peak/released memory, and any page reload or process termination under `docs/release-evidence/`.
- [ ] Verify source decode length is not misreported as Wasm residency and that cancel/re-import/post-commit release does not retain the prior full decoded source.
- [ ] Update the canonical manual-verification ledger. Unsupported, failed, or incomplete rows stay `unverified` and block #341 closure.

**Acceptance:** all #357-required Safari rows pass on the exact Task 4 Build with locatable evidence; browser automation or desktop simulation never substitutes for physical iPadOS.

## Version Management

Current identities below are from protected `main` at `9b5c2929a2cf6cf86ce39e495920b852a01c740d` after Stage 9. Allocation classes are confirmed by amendment A10 (`audio-runtime` 2.0.0, `application-facade` 2.1.0, `lmdj.error.v1` 1.1.0 with two members, `project-cooker` none, `web-runtime-platform` 2.0.0); Task 4 re-verifies exact unused numbers immediately before integration.

| Component | Current | Allocated | Task |
| --- | --- | --- | --- |
| `lmdj.error.v1` Contract | 1.0.0 | 1.1.0 (two additive enum members) | 1 |
| audio-runtime | 1.0.0 | 2.0.0 (confirmed: limits-field removal/rename is breaking) | 1–2, integrated in 4 |
| project-cooker | 1.0.0 | none (confirmed: quota validation lives in Facade callbacks and `from_snapshot`; Task 1 audit re-checks and returns to review on any surface change) | 1, integrated in 4 |
| application-facade | 2.0.0 | 2.1.0 (confirmed: additive `sample.quota` query and error classes; no breaking surface) | 3, integrated in 4 |
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
- [x] #358 — readiness correction (docs), completed by #368
- [ ] #357 — Task 0 decision amendment ([2026-08-28 amendment](../../prd/decisions/2026-08-28-long-material-quota-accounting.md)), blocks all implementation
- [ ] #343 — Task 1, blocked by #357
- [ ] #344 — Task 2, blocked by #357 and #343; parallel with #345 after #343
- [ ] #345 — Task 3, blocked by #357 and #343; parallel with #344 after #343
- [ ] #346 — Task 4, blocked by #357, #344, and #345
- [ ] #359 — Task 5 physical acceptance, blocked by #357 and #346

Umbrella: [#341](https://github.com/endaye/lmdj/issues/341). Related, not gated by this plan: [#347](https://github.com/endaye/lmdj/issues/347) (future offline time-stretch design).

## Final Acceptance Boundary

The umbrella closes only when Task 0 and Tasks 1–4 are merged, the full and stress suites pass on the integrated head, the allocated Product Build has a verified immutable Portal snapshot, and #359 records passing macOS Safari and physical iPadOS Safari evidence. Release, deployment, and Channel promotion remain separate authorization boundaries outside this plan.
