# LMDJ Sound Set audition byte path

日期：2026-09-08

状态：草案（待评审）

Issue: [#799](https://github.com/endaye/lmdj/issues/799)
Umbrella: [#470](https://github.com/endaye/lmdj/issues/470) ·
Predecessor: [#773](https://github.com/endaye/lmdj/issues/773) ·
Merged surface: [#796](https://github.com/endaye/lmdj/pull/796) (`9b742063`)

Baseline for every coordinate in this document: `origin/main` at `41a5a912`.
Every line number below was read with `git show origin/main:<path>`, never from
a working tree, and `9b742063` was re-confirmed an ancestor.

`main` moved repeatedly while this plan was written, and twice it moved in ways
that made the plan wrong rather than merely stale: #999 closed §2.7's gap and
delivered Task 1 before this document merged. Both were re-resolved and are now
recorded as history.

That is the rule this plan states twice and violated once: **re-resolve
findings, not only line numbers** (§6). A coordinate survives most commits; a
claim that something is missing is invalidated by the commit that adds it, and a
Task described against a tree that no longer exists will be implemented as a
no-op or a duplicate. Each Task re-resolves its own coordinates and its own
premises against the `main` it branches from. The table in §2.1 is evidence for
§3.1's pricing, not an index to edit against.

## 1. Outcome

`soundset.audition` resolves and gates a Sound Set audition source and reports
the geometry of the exact bytes a Runtime would play. It carries no audio.
This plan carries those bytes into the two Hosts that own a `RealtimeEngine`,
so a Sound Set is audible before install and S11-D5 — and the umbrella's own
headline word, *previewable* — becomes true.

The product owner's decision of 2026-09-08 — **audition PCM is published into a
bank slot reserved for auditions** — is settled and is not re-opened here. The
decision, the two rejected options with their reasons, and the four-bank-slot
engine correction are recorded in the design authority by
[#993](https://github.com/endaye/lmdj/pull/993) and are deliberately not
restated here. This document is the delivery plan only.

**Sequencing against #993.** At the time of writing, #993 is **open, not
merged**. §5 Task 5 must edit the same S11-D5 paragraph — to change "the
mechanism is not built" to built and close S11-D5 — so Task 5 branches from a
`main` that already contains #993. This plan does not resolve a conflict in the
design authority.

## 2. What is already true, measured

### 2.1 The bank slots the reserved slot is drawn from

Recorded here only because §3.1 prices an option against these exact
coordinates; the engine correction itself belongs to #993.

| Fact | Coordinate at `41a5a912` |
| --- | --- |
| `inline constexpr std::size_t kRealtimeBankCapacity = 4;` | `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp:31` |
| `std::array<BankSlot, kRealtimeBankCapacity> bank_slots_{};` | `realtime_engine.hpp:511` |
| `std::atomic<std::uint8_t> current_bank_slot_{kLegacyBankSlot};` | `realtime_engine.hpp:537` |
| `return PublishResult::bank_slots_full;` after the `empty` scan | `packages/audio-runtime/src/realtime_engine.cpp:578` |

`publish_sample_bank` scans `bank_slots_` for one in `BankState::empty` and
refuses only when none is free.

### 2.2 `ResolvedPlayback` is an envelope, and `previews_` is not a byte path

`struct ResolvedPlayback` is
`{start_frame, end_frame, trigger_mode, linear_gain, muted}` at
`packages/project-cooker/include/lmdj/cooker/runtime_snapshot.hpp:18`.

> **Correction to the coordinates circulated with this Task.** The struct is in
> **`project-cooker`**, not `packages/audio-runtime/include/lmdj/audio/`; that
> path does not exist. The preview write is at `realtime_engine.cpp:1504`
> (not 1373), the voice-start read at `:1553`, the frame count at `:1558`, and
> `current_sample`'s implementation at `:297` (not 221). The *substance* of the
> warning is correct and confirmed — only the line numbers had drifted.

At voice start the engine takes the envelope from `previews_[event.slot]` and
the *bytes* from `current_sample(event.slot)`, which is

```cpp
const auto bank_slot = current_bank_slot_.load(std::memory_order_relaxed);
return bank_slot == kLegacyBankSlot
           ? samples_[slot]
           : bank_slots_[bank_slot].bank->sample(slot);
```

**This is the load-bearing consequence, and it is the one thing the decision's
framing does not yet cover:** every byte a voice plays is fetched from
`bank_slots_[current_bank_slot_]`. Reserving a slot therefore does *not* by
itself make an audition audible. Either the reserved slot becomes
`current_bank_slot_` — which *is* the rejected "displace the Project's bank"
option wearing a different name — or the engine gains a voice-start path that
reads from the reserved slot explicitly. This plan does the latter, and §4.1 is
mostly about that path.

### 2.3 The refcounted drain this needs already exists

`struct Voice` (`realtime_engine.hpp:452-472`) already carries
`std::uint8_t bank_slot`, and `release_voice_bank` (`realtime_engine.cpp:271`)
decrements that slot's `active_voices`, flipping `retiring` → `reclaimable` at
zero. Voices are already accounted per bank slot, and `pattern_slot` is an
existing precedent for a voice sourcing from a slot that is not the current
bank. The audition path reuses this machinery rather than inventing a second
lifetime.

`apply_published_bank` (`:256`) must **not** be reused: it calls
`retire_current_bank()`, writes `current_bank_slot_` and overwrites
`availability_mask_`. Any of the three applied to an audition would either
displace the Project's bank or corrupt the Pad availability the Host reports.

### 2.4 An audition bank can be built without a Project snapshot

`PreparedSampleBank::empty(project_id, project_revision)` plus
`set_sample(slot, mono_pcm, playback)` are existing public API
(`packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp:188-196`).
A Sound Set has no `RuntimeSnapshot`, so `from_snapshot` does not apply; the
`empty` + `set_sample` path does, and needs no new construction API.

### 2.5 Only two Hosts own an engine

`RealtimeEngine` is constructed in exactly two places:
`apps/native-host/src/main.cpp` and
`packages/web-runtime-platform/src/control_runtime.cpp`. `core-cli` and
`core-mcp` own none, so audition stays metadata-only there — unchanged, and
that is correct rather than a gap.

### 2.6 The Facade is in-process with the Host runtime

`control_runtime.cpp:2817` calls `impl_->application.inspect_sample(...)` — a
typed C++ call returning a typed result, not a JSON round-trip. The audition
bytes therefore never need to cross the bridge or be base64-encoded; the Host
asks the Facade for decoded PCM through a typed method and publishes it. This
is the precedent §4.2 follows.

### 2.7 Delivered: the Web Host could not dispatch `soundset.audition`

**Fixed and merged before this plan did. Recorded as history, not as a live
gap** — re-resolved against `origin/main` per §6's own rule, which this section
is the first thing to have violated.

When this plan was drafted, `bridge.cpp`'s `supported_operation` allowlist and
`HOST_OPERATIONS` in `protocol.mjs` each listed seven `soundset.*` operations
and neither included `soundset.audition`. `supported_operation` fails closed, so
every audition request from the Web Host was rejected with
`bridge_protocol_error()` before reaching the handler written to serve it, while
`control_runtime.cpp` carried a payload validator and a deadline entry for it —
two entries no request could reach.

That was closed by [#999](https://github.com/endaye/lmdj/pull/999), merged as
`45756035`. At current `origin/main` the operation is present at
`bridge.cpp:288` and `protocol.mjs:76`, the allowlist is
`std::array<std::string_view, 73>` (`bridge.cpp:223`), and the two
`control_runtime` entries are reachable.

#999 also landed the gate that keeps it closed: `platform.web_runtime_source_boundary`
asserts every operation in `control_runtime`'s `soundset_operations` table is
admitted by `bridge.cpp` and sendable by `protocol.mjs`. The binding direction
is the point — comparing the two transports to each other cannot see a *shared*
omission, which is what this defect was. See
`.agents/pitfalls/parity-check-between-agreeing-copies.md`.

What remains for the Host task is only `soundset.audition.stop`.

## 3. Decisions this plan settles

### 3.1 Where the reserved slot comes from — **ruled: B, dedicated slot**

**Ruling, 2026-09-08, by the plan owner: a dedicated audition pool.** The
three findings below were independently re-verified at `b5d8ca93` before the
ruling rather than adopted from this document. Nothing in the owner's decision
is re-opened: audition PCM still lives in its own bank slot and still never
touches the Project's.

The deciding reason was the first one — rewriting those constants is a
threshold edit on numbers that measure real realtime headroom, which
Minimization §1 forbids outright.

**Correction carried to the owner.** The cost relayed when the option was
chosen was "hot-swap headroom drops from 4 to 3". Under this ruling the honest
number is **zero headroom cost**, plus a cost nobody priced: the new
voice-start path of §2.2. The plan owner is correcting #993 before it merges
and telling the owner both facts. The two rejected options are not revived by
this, because they were rejected on correctness — displacing still needs a
restore path surviving a mid-audition failure and still silences a Project in
use; a scratch pad slot still mutates a bank derived from Project Truth —
and cheaper-than-advertised does not answer either objection.

The record of both options is retained below, because §5 Task 2's constants and
§8's second blind spot are both stated relative to this choice.

**A. Carve one of the existing four.** Hot-swap headroom for Project banks
drops 4 → 3. This is the form the decision comment priced.

**B. A dedicated audition pool beside `bank_slots_`.** Project hot-swap headroom
stays at 4; cost is the pool's own `std::optional<PreparedSampleBank>` slots and
a sentinel range. The pool holds **two** slots, for the correctness reason in
§4.1 — a single slot cannot serve replace, because the incoming Bank would
overwrite one a draining voice is still reading. Two is the minimum, and it is
still zero Project headroom.

Why B, on evidence rather than taste:

- **A breaks an existing test's arithmetic, and the honest fix is not a
  threshold edit.** `applies_explicit_bank_slot_backpressure_until_reclaimed`
  (`tests/core/audio/realtime_engine_test.cpp:1169-1190`) publishes exactly
  four banks, asserts the fifth is `bank_slots_full`, and asserts
  `reclaim_retired_banks() == 3`. Under A those constants become 3 / 4th / 2.
  Rewriting them to match a reduced pool is precisely the "make it pass" move
  the Minimization Principle §1 forbids for thresholds — the numbers measure
  real realtime headroom.
- **A reduces a realtime property to buy a non-realtime feature.** Audition is
  a browsing convenience; Project bank hot-swap is the performance path.
- **B leaves the `publish_queue_full` unreachability argument intact.** The
  stress test asserts `static_assert(kRealtimeBankCapacity ==
  kRealtimePublishQueueCapacity)` and reasons that a full queue needs 4
  `pending` slots while reaching the push needs a 5th `empty`
  (`tests/core/audio/snapshot_publication_stress_test.cpp:244-262`). B changes
  neither capacity, so the argument and its `static_assert` stand unedited.
  Under A the equality still holds numerically while the *reasoning* silently
  changes — a comment that is true by luck is worse than one that is checked.

Under B, "reserve a bank slot for auditions" is satisfied exactly as decided —
audition PCM lives in its own bank slot and never touches the Project's — at
strictly lower cost than the decision assumed. If the ruling is A, the plan
still works; §5 Task 2's constants change and the two tests above are updated
with a comment naming the traded headroom.

### 3.2 Overlapping auditions: **replace**

Two requests, one reserved slot. The second **replaces** the first.

- Refusing breaks the primary interaction. The Facade's own comment
  (`application.cpp:8046-8048`) anticipates "an interactive surface that
  auditions slot after slot"; a user clicking preview down a 16-slot list must
  not have click *n+1* refused because click *n* is still ringing.
- Queueing makes a browsing user hear a backlog of sounds they have already
  moved past — the wrong behaviour for a preview, and it needs a queue the
  engine does not have.
- Replace costs nothing new: the previous audition's voices drain through the
  `retiring` → `reclaimable` refcount in §2.3.

Replace is defined as: mark the current audition bank `retiring`, stop its
voices with the ordinary release ramp (`kRealtimeRampFrames`, 2 ms — no click),
publish the new bank, start the new voice. A replace never fails for "slot
busy"; it can still fail for a source the Facade refuses.

### 3.3 Release semantics: who clears the slot

Four clearing paths, all required:

1. **Natural end.** A one-shot audition voice completes; the bank goes
   `retiring` and is reclaimed by the existing sweep. No Host action.
2. **Explicit stop.** A new Facade operation `soundset.audition.stop`,
   payload `{}` — Set identity is not needed because there is only ever one
   audition. Idempotent: stopping when nothing plays succeeds with
   `{"accepted": true}`. Idempotency is what keeps this inside the frozen
   error vocabulary — there is no "nothing to stop" condition to name.
3. **Replace**, per §3.2.
4. **Session teardown.** Project close and `host.close` clear the audition
   slot with the Project bank. Without this the slot outlives the session that
   created it.

`soundset.audition.stop` is the additive public-surface change. It is a
`command` with respect to the Host and a query with respect to Project Truth —
no Asset, no Pad, no revision — the same standing `soundset.audition` has.

### 3.4 Headroom: confirmed, with a named regression test

Under B, the four Project bank slots are untouched, so every existing
publication path — including the two that deliberately reach `bank_slots_full`
(`realtime_engine_test.cpp:1186`, `snapshot_publication_invariant_test.cpp:229`)
— keeps its exact current arithmetic. That is the confirmation #799 asked for,
and under B the honest answer is that the decision costs no Project headroom
at all.

The regression the decision creates is nonetheless real and gets a named test
(§5 Task 2): **an audition must never consume a Project bank slot.** The test
fills all four Project slots, then auditions, and asserts the audition
succeeds *and* that a fifth Project publication still returns
`bank_slots_full` rather than succeeding — i.e. the audition neither stole a
Project slot nor freed one. Under A this test is what would fail if someone
later "reclaimed" the reserved slot into the pool.

### 3.5 `soundset.audition` gains playback; its frozen identity is untouched

The playback side effect attaches to the existing `soundset.audition` in the
two Hosts that own an engine, rather than to a new `soundset.audition.play`.
Its identity, refusal order and error vocabulary are unchanged — a request
that is refused today is refused identically and plays nothing. The Facade's
own comment at `application.cpp:8010-8015` describes carrying the bytes as the
outstanding half of *this* operation, not as a sibling. Hosts with no engine
keep returning metadata only.

## 4. Mechanism

### 4.1 `audio-runtime`

Additive, no change to any existing signature.

**The pool holds two slots, not one, and that is a correctness requirement
rather than headroom.** A single slot cannot serve replace: the incoming Bank
has nowhere to go that is not the buffer a draining voice is mid-render on, so
overwriting it destroys bytes a voice is still reading for up to
`kRealtimeRampFrames`. A retiring audition keeps its own slot until
`active_voices` reaches zero and the sweep reclaims it — exactly why the Project
pool is larger than one. Two is the minimum. A third publication while both
drain is refused with `bank_slots_full`, and that refusal is deliberately kept
out of `bank_slot_rejections_`, which measures Project pressure.

**Publication is applied by the audio thread, on the Project protocol.** This
is the second correctness requirement and the one that is easiest to get wrong,
because the shortcut looks safe:

> An earlier revision of this plan said `publish_audition_bank` should share no
> code with `publish_sample_bank`, on the reasoning that an audition is not a
> Project Bank. Implemented that way it raced. Every Bank read on the
> voice-start path happens *before* `++active_voices`, so a control-thread
> `retire_audition` can observe `active_voices == 0` while a voice is between
> reading the Bank and counting itself against it, mark it reclaimable, and
> have the sweep free a `std::vector` that voice is still reading. It also read
> `active_voices` across threads, a data race in its own right. Caught in
> review on the implementing Pull Request, confirmed under ThreadSanitizer, and
> recorded here because the plan is where the shortcut was proposed.

So: `publish_audition_bank` primes a slot found `empty` and hands its index to
the audio thread through an audition publish queue; `render` applies and
retires inside the callback, which serialises retirement against voice starts.
The queue is sized to the audition pool, not shared with the Project queue, so
each pool keeps its own `publish_queue_full` unreachability argument — pushing
requires a slot found `empty`, a full queue requires every slot `pending`.

`active_voices` needs no atomic once the cross-thread access is gone; adding one
would imply a race that no longer exists.

The rest:

- `PadControlKind::audition_start` / `audition_stop`, and a voice-start branch
  that fetches bytes from the current audition slot instead of
  `current_sample(...)`, recording that slot in `Voice::bank_slot` so the
  existing per-slot refcount drains it.
- Audition slot indices are encoded above the Project range in
  `Voice::bank_slot`. The predicate for them must be a closed range:
  `kLegacyBankSlot` is `0xff` and therefore also above the audition base, so a
  bare `>= base` test misclassifies every legacy voice as an audition.
- An audition is not a Pad: `stop_slot`, `stop_all` and `release` must not
  reach it, and it publishes no Pad-keyed `RuntimeVoiceState` or trigger
  outcome. A performer stopping playback must not kill the Set being auditioned.
- No `events_pending` guard, unlike `publish_sample_bank`. That guard is
  Pad-pool-specific — it stops an in-flight press admitted against Bank N being
  served by Bank N+1 — and an audition writes no `availability_mask_`, so it can
  mis-serve no Pad event.

The audition bank is a `PreparedSampleBank::empty(...)` carrying one sample at
a fixed slot index, with the named sentinel identity of §3.1. That identity is
never read on the audition path, and a test pins that an audition bank never
becomes `current_bank_slot_` and never moves Pad availability.

### 4.2 `application-facade`

- A typed `Result<SoundSetAuditionAudio> audition_soundset(...)` returning the
  decoded PCM alongside the geometry the JSON envelope already reports, on the
  `inspect_sample` precedent of §2.6. Today `measure_decoded_audio`
  (`application.cpp:4396`) decodes and discards; this retains.
- `soundset.audition.stop` registered in the operation table
  (beside `application.cpp:212`) and dispatched (beside `:3953`).

**Registration hazard, called out because it fails quietly.** `dispatch()`
ends with a bare `return attempt_inspect(request);` (`application.cpp:3968`).
An operation that is added to a Host table but missed in the Facade dispatch
does not error — it silently runs `attempt_inspect`. Every Task below that
adds an operation therefore asserts the **exact** operation set, not merely
that its own entry is present.

### 4.3 Hosts

| Surface | Change |
| --- | --- |
| `bridge.cpp:288-294` + array length `:223` | add `soundset.audition.stop` only; **73 → 74**. `soundset.audition` is already there since #999; re-resolve the length before editing, because this row has been wrong once already |
| `protocol.mjs:76-82` | `soundset.audition.stop` only, for the same reason |
| `control_runtime.cpp:367` | payload validator for the stop operation (`exact_keys(payload, {})`) |
| `control_runtime.cpp:2154` | add stop to `soundset_operations`, not project-scoped |
| `bridge.cpp:209-219` `operation_deadline` | both audition operations join the 1-second interactive tier beside `sample.preview.set` — a preview is an interactive gesture, not a 30-second query |
| `apps/native-host/src/main.cpp:130` | `kSoundSetOperations` 5 → 6 |
| `apps/core-mcp/.../server.py` | stop operation registered; audition stays metadata-only |

### 4.4 Creator

The attachment point is already prepared and explicitly documented at
`apps/creator-web/src/components/soundset_surface.tsx:98-122`: a `<button>`
replaces the bare `<span>` at the `soundset-demo` paragraph and at the
`soundset-slot-sound` span. The comment's instruction — "do not add a third
surface, and do not reach past the Facade for bytes" — is honoured; a stop
control attaches to the same two sites.

## 5. Tasks

One Task is one reviewable Conventional Commit over its declared files.
Tasks 1–4 add no `module.json` bump; the Version Management section explains why the SemVer is paid once
in Task 5.

### Task 1 — reach the Web Host — **delivered as #999 (`45756035`)**

Closed §2.7 and landed the parity gate that keeps it closed. Recorded here for
the sequence; **an implementing Task must not repeat it.** Re-adding
`soundset.audition` to either transport would be a duplicate entry, and the
`std::array` length it relies on is already correct at 73.

The residue — registering `soundset.audition.stop` — belongs to Task 4, where
the operation it registers actually exists.

### Task 2 — the audition bank slot and voice path

**Delivered as [#1001](https://github.com/endaye/lmdj/pull/1001) (`e8c583b4`).**
The declared files and tests below include the stress-tier gate, which an
earlier revision of this plan described in §8.2 without any Task owning it — a
gate named in a document and declared by no Task is a gate nobody is obliged to
write.

> That omission is this plan committing the error its own §8 records, one
> section away from recording it. §8.2 asserted the gate as a delivered fact;
> §5 is what an implementer follows, and §5 did not require it. So the premise
> "the gate exists" would have been implemented as "the gate does not exist" by
> anyone working from the Task list — the plan's coverage claim about itself
> was the stale premise. See
> [`stale-premise-gets-implemented`](../../.agents/pitfalls/stale-premise-gets-implemented.md):
> a document is not exempt from it by being the document that states it, and a
> claim about your own coverage is the one nobody thinks to re-resolve.

- **Files:** `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`,
  `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`,
  `packages/audio-runtime/src/realtime_engine.cpp`,
  `tests/core/audio/realtime_engine_test.cpp`,
  `tests/core/audio/snapshot_publication_stress_test.cpp`
- **Tests (stress):** `test_audition_replacement_is_conserved_under_concurrency`
  races publish, start, stop and reclamation against a rendering thread, and
  asserts both that publications were accepted and that some were refused,
  because a concurrency test whose contention never fires asserts nothing.
  **Defect it catches:** retirement racing a voice start — the control thread
  observing `active_voices == 0` while a voice is between reading the Bank and
  counting itself against it, freeing a buffer still being read. **Run it under
  `tsan`, not only `dev`:** a plain build passes this test on the pre-fix code,
  because a freed read that stays mapped returns plausible bytes. The
  verification is `scripts/core.sh configure tsan` plus the stress binary, and
  it is not reached by `scripts/core.sh test dev full`.
- **Tests (unit/component):**
  - an audition voice renders the audition bank's PCM while
    `current_bank_slot_` still names the Project bank, asserted on rendered
    sample values, not on a state flag;
  - the §3.4 headroom test — four Project banks published, audition succeeds,
    fifth Project publication still `bank_slots_full`;
  - replace (§3.2) drains the incumbent: `active_voices` returns to zero and
    the retired audition bank becomes reclaimable;
  - an audition bank never becomes `current_bank_slot_` and never alters
    `availability_mask_`.
- **Defect it catches:** audition audio sourced from, or displacing, the
  Project's bank.

### Task 3 — Facade audition audio

**Delivered as [#1003](https://github.com/endaye/lmdj/pull/1003) (`7337ccef`).**
The stop operation moved out of this Task: it is a Host operation, not a Facade
one, because `sample.preview.set`/`.clear`, `sample.stop`, `trigger` and
`audio.activate` appear zero times in the Facade's operation table and are
served entirely by `control_runtime`. It resolves and gates nothing, so the
Facade has nothing to do. See Task 4a.

- **Files:** `packages/application-facade/src/application.cpp` and its public
  header, `tests/core/facade/soundset_facade_test.cpp`
- **Tests (component):** the typed method returns PCM whose frame count equals
  the geometry the JSON envelope reports for the same source — one decode,
  two consistent answers; the stop operation is idempotent; and the **exact**
  operation set is asserted, per the §4.2 fallthrough hazard.
- **Defect it catches:** a stop operation that reaches a Host table but not
  Facade dispatch, silently answering as `attempt_inspect`.

### Task 4a — Host wiring and the stop operation

**Delivered as [#1009](https://github.com/endaye/lmdj/pull/1009)** (open).
Task 4 as first written bundled Host wiring, the stop operation, the Creator
control, the parity table and an acceptance leg into one commit; that is two
Tasks by the one-behavior rule, so it was split. `soundset.audition.stop` is
registered in **three** Host tables, not five: not the Native Host's
`kSoundSetOperations` nor `apps/core-mcp`, both of which forward to the Facade
and would land a Host-only operation in the `attempt_inspect` fallthrough.

### Task 4b — the Creator control, parity table and acceptance leg

- **Files:** `packages/web-runtime-platform/src/control_runtime.cpp`,
  `bridge.cpp`, `web/protocol.mjs`, `apps/native-host/src/main.cpp`,
  `apps/core-mcp/lmdj_core_mcp/server.py`,
  `apps/creator-web/src/components/soundset_surface.tsx`, and the tests
  pinning those tables (`tests/host/performance_cli_test.py`,
  `packages/web-runtime-platform/test/protocol.test.mjs`)
- **Tests (component + platform):** the Creator's two audition controls
  dispatch and stop; the cross-Host parity case below; the acceptance leg
  below.
- **Cross-Host refusal parity (§8.4):** one table asserting the Web and
  Native Hosts refuse the same Set with the same code at each locked reason —
  identity, `soundset_license_ineligible`, `soundset_content_mismatch`,
  whole-Set `soundset_audio_unsupported`, `MISSING_ASSET`. Adds no error
  vocabulary. **Defect it catches:** one Host's refusal order drifting from
  the Facade's while that Host's own suite stays green — invisible to any
  per-Host test by construction.
- **Acceptance leg (far-side, per Task):** audition a Set, then assert the
  open Project's revision is **unchanged**, no Asset was created and no Pad
  assignment moved — the §6 invariant, asserted after the transition rather
  than before it. The perturbation obligation applies: change the assertion,
  run it, confirm it fails at that line with real product data on the received
  side, and record both values.

### Task 5 — SemVer, Assembly, Product Build, Portal snapshot

Separate Task because Version Management makes it one indivisible unit, and because it is the
only Task that allocates identity.

- **Files:** the four `module.json` files, `products/lmdj/version.json`,
  `products/lmdj/assembly.json`, `assembly.lock.json`, the Host manifests, the
  Portal pages listed under Documentation Impact, and the snapshot.
- **Tests:** `python3 scripts/version.py verify --version-file
  products/lmdj/version.json`, `python3 tests/build/version_test.py`,
  `scripts/docs-site.sh check`.

<!-- This heading and "Documentation Impact" are deliberately unnumbered.
     CLAUDE.md and version-management.md §11 require the literal string
     `## Version Management`, and the repository's other plans use the bare
     form, so a number here would break a literal search. The numbered
     sections run 1-8 without gaps around them. -->

## Version Management

Version impact: **required**, and paid once in Task 5.

| Domain | From | To | Reason |
| --- | --- | --- | --- |
| `audio-runtime` | `3.0.0` | `3.1.0` | additive public API: audition publish, control kinds, sentinel |
| `application-facade` | `3.1.0` | `3.2.0` | additive: typed audition audio method + `soundset.audition.stop` |
| `web-runtime-platform` | `4.0.0` | `4.1.0` | additive operation surface; dependency pins follow |
| Hosts (`native-host`, `core-mcp`, `web-runtime-host`, `creator-web`) | per `assembly.json` | MINOR | new operation in their tables |
| Contracts | — | **none** | no schema changes; `lmdj.soundset.v1` stays `1.1.0`. The audition carries no new persisted or cross-process shape |
| Product Build | `1.0.44.0` | next unoccupied | forced by the Assembly write below |

**Why the bumps cannot be spread across Tasks.** `scripts/version.py`'s
`_validate_component_source` (`scripts/version.py:615-637`) raises
`module source identity mismatch` when a `module.json` version differs from the
version `products/lmdj/assembly.json` pins for that module. So a `module.json`
bump forces the Assembly edit in the same Task; and a Product Assembly change
forces a Product Build allocation and an immutable Portal snapshot, which
CLAUDE.md forbids declaring `Documentation impact: none`. Tasks 1–4 therefore
change no `module.json`, and Task 5 pays the whole cascade — the same pattern
Stage 11 used at Task 6 (#673, closed), which the plan records as "pay SemVer
only for surfaces Tasks 1–5 actually changed".

Build allocation is audited immediately before mutation, never assumed from
this document. Snapshot and allocation ship as one Pull Request, two commits.

Tags: no tag is created by this plan. No release, publication, deployment or
Channel promotion is authorized or implied.

Rollback: the immutable `1.0.44.0` Build.

## 6. The invariant

Audition creates no Asset, touches no Pad assignment, and leaves the Project
revision unchanged.

The shape to copy is the zero-write `keep` install assertion in
`tests/platform/web/creator/creator_web_soundset.spec.mjs:427`:

```js
expect(kept.result.project_revision).toBe(kept.payload.expected_revision);
```

with a second at `:471` on the committed leg. Both are on `origin/main`, landed
by #978 as `b5d8ca93`, and the merged form has been perturbed by the plan owner
(expected 67, received 66), so this is a proven shape rather than a described
one.

> **Recorded because it nearly cost a Task.** An earlier revision of this plan
> asserted this assertion was *absent* from `origin/main` and existed only on
> two unmerged lanes. That was true at `968c4062` and false at `b5d8ca93` —
> and `b5d8ca93`, the commit that made it false, is #978 itself, the very head
> this document names as its baseline. Fifteen coordinates were re-resolved at
> that move; this conclusion was carried forward from the frame before it,
> because a conclusion does not look like a coordinate.
>
> The rule this plan therefore states for every Task: **re-resolve findings,
> not only line numbers.** An absence claim is the most perishable kind — it is
> invalidated by any commit that adds the thing, whereas a line number survives
> most commits. See `.agents/pitfalls/blind-search-reads-as-absence.md`.

> **The same family, one layer down: dates.** An earlier revision dated the
> §3.1 ruling 2026-09-09 and the document 2026-09-08, and a reviewer correctly
> read the ruling as future-dated. Both were the same instant. The authoring
> machine runs at UTC+8, where it was already 2026-09-09; GitHub stamps in UTC,
> where it was still `2026-09-08T16:xx:xxZ`, and so does every other artefact
> recording this decision — #993, the comments on #799 and #470, and the
> `gate-failure-readability` recurrence.
>
> The rule: **a durable record carries the clock the repository keeps, not the
> one the authoring machine keeps.** Take the date from a repository artefact
> (`git log -1 --format=%cI`, or a `gh api ... created_at`), never from local
> `date`. This is the absence-claim rule one layer down — a fact true where it
> was measured and false where it was written.

Task 4 still writes **its own** far-side revision assertion rather than
extending the one above: that one guards a zero-write `keep` install, and
Task 4's guards an audition. Different transitions, so they are not
duplicates, and #799 does not depend on the other lane.

## Documentation Impact

**Documentation impact: required** (Task 5 only; Tasks 1–4 declare `none`).

Affected portal pages:
- `/core/modules/application-facade`
- `/core/modules/audio-runtime`
- `/hosts/core-mcp`
- `/hosts/web-runtime-host`
- `/contracts/soundset`

Task 5 also updates `docs/plans/2026-09-06-lmdj-stage11-sound-set.md`: the
Locked Facade Surface table (`:130-136`) goes from five operations to six, and
the statements that S11-D5 is not closed (`:145-174`, and the S11-D5 row at
`:210`) become true and must be rewritten rather than left standing.

Those line numbers are read at `41a5a912` and **#993 will move them** — it
rewrites the same S11-D5 paragraph. Task 5 therefore re-resolves them against
the `main` it branches from, and does not reuse the numbers above. If #993 is
still unmerged when Task 5 is ready, that is a sequencing question for the
plan owner, not a conflict for this Task to resolve.

Editing `docs/plans/` is itself `Documentation impact: none`.

## 7. Frozen constraints honoured

- No new `lmdj.error.v1` code and no new `details.reason` token. The stop
  operation is idempotent (§3.3) specifically so that "nothing to stop" needs
  no vocabulary. Audition refusals reuse `soundset.audition`'s existing,
  settled order.
- `soundset.audition`'s identity, refusal order and error vocabulary unchanged
  (§3.5).
- No commit or force-push on `main`; no tag, release, deploy or Channel
  promotion; no threshold tuned to go green (§3.1 exists because the tempting
  edit was exactly that).
- One Task, one commit, one Pull Request. **One declared exception:** Task 5
  ships as one Pull Request with two commits, because a Product Build
  allocation and its immutable Portal snapshot must land together — the
  snapshot records the Build, so a Build merged without it is already
  unprovenanced — while staying separately reviewable. That is the existing
  repository practice for Build allocation, not a new licence to split; every
  other Task here is one commit.

## 8. What these checks cannot express

Named because a check whose blind spot is unnamed is a claim rather than a
gate. Each carries a disposition: absorbed into a Task here, or declined to a
filed Issue so the gap outlives this worktree. Nothing is left as a bare
observation.

1. **That an audition sounds correct** — *declined to a follow-up Issue.*
   Every test here asserts *which buffer* the bytes came from and *that* the
   geometry matches. None asserts the audition is not playing at the wrong rate
   or the wrong gain, so a resample defect in `prepare_runtime_pcm` passes this
   whole plan.

   What it would take is known, not speculative: the infrastructure already
   exists at `tests/fixtures/golden/` (`reference_render.py`,
   `one_bar_120bpm.wav` and its `.sha256`), and `offline_renderer_test.cpp`
   is the working precedent. Closing it means a Set-audio golden fixture plus
   a deterministic offline render of an audition, which needs an offline
   audition render path that does not exist — the audition is realtime-only by
   construction. **That is a feature, not a test**, and building it inside
   #799 would widen a byte-path Task into a render-path Task. Declined here and
   filed as [#994](https://github.com/endaye/lmdj/issues/994), which records
   what closing it needs. It is not in Stage 11's Final Acceptance Boundary,
   which does not name audition.

2. **Realtime safety of the audition path under contention** — *closed, and it
   was not a theoretical gap.* An earlier revision of this plan recorded this
   as an accepted gap, reasoning that the audition pool never enters the race
   `snapshot_publication_stress_test.cpp` runs, so the exposed surface was
   small. That reasoning was correct and the conclusion was wrong: a
   use-after-free lived in exactly this gap, and the single-threaded tests that
   were offered in its place could not see it. It was found by review and
   confirmed under ThreadSanitizer.

   `test_audition_replacement_is_conserved_under_concurrency` now races
   publish, start, stop and reclamation against a rendering thread. It is the
   named gate for this class: on the pre-fix code it is silent in a plain build
   and reports `data race ... in RealtimeEngine::retire_audition` under TSan.

   **The lesson this plan keeps:** "the exposed surface is small" is an
   argument for a cheaper test, never for no test. A gap named in a document is
   still a gap, and naming it honestly does not make the code safe — it only
   makes the eventual defect unsurprising.

3. **That the Native Host's audition actually plays** — *accepted, narrowed
   by §8.4.* The acceptance leg runs in the browser; native audition is
   covered by table assertions, so reachability rather than audibility. The
   parity case in 4 below removes the more likely half of this risk (diverging
   refusal), leaving only "the bytes reach a native voice", which shares the
   Task 2 engine tests with the Web path.

4. **Cross-Host refusal divergence** — *absorbed into Task 4, not declined.*
   Cheap and worth doing here: the refusal order is already locked and
   identical for all Set-reading operations (identity,
   `soundset_license_ineligible`, `soundset_content_mismatch`, whole-Set
   `soundset_audio_unsupported`, then `MISSING_ASSET`), so a parity case is a
   table over settled reasons rather than new judgment. Task 4 asserts that the
   Web and Native Hosts refuse the same Set with the same code for each locked
   reason. It adds no error vocabulary. The defect it catches: one Host's
   refusal order drifting from the Facade's while its own tests stay green,
   which is invisible to any per-Host suite by construction.
