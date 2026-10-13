# SDK Headered Performance FX type closure

Date: 2026-10-13

Status: SOURCE candidate; verification and shipping await the coordinator's
shared-resource disposition. This is B1 under the Creator Desktop Final Goal.

## Premise refresh

Implementation base: `0909a3015d8f19ee91dab415cd682822e9d3d3b5`.
Parent: `dad44c45137f44377c4ffafb2098020eaabd64e3`.
Tree: `b6bf318fbb4aaf58d7bd2f0673849373b0df7f33`.
Own isolated branch: `fix/sdk-headered-fx-types`.

Root admitted the unique five-file SDK SOURCE writer after accepting capture
PR #2138, actual merge `7d27e33d209d4b0644339085d27c038d41e2393a`.
That predecessor's owned capture handle and original capture assertions remain
delivered. The historical B1 preparation is diagnosis, not current-head proof.
The clean bootstrap branch was fast-forwarded to the independently fetched
remote main above before this plan or product source was written.

At this base, the public `PerformanceHeaderedEvent` still includes every
`PerformanceRawEvent` arm. Consequently it lacks the no-ID headered engage,
admits legacy FX identities without a generation, and combines move/release
with optional `value`. The existing `wireHeaderedPerformanceEvent` already
enforces three distinct closed key sets; its implementation needs no change.
This type defect remains outstanding and is the only implementation target.

Successor PR #2139 changes the Creator consumer, not the SDK types, serializers,
owning SDK tests, compiler configuration or Module page. Its existing
`headeredFxEngage` cast identifies the same SDK gap. Consumer adoption/removing
that cast belongs to a later Task; B1 does not edit it or claim C1 integration.
PRs #2136, #2137 and #2142 introduce no conflicting SDK premise or scope change.

## One Task and declared paths

Exactly one eventual Conventional Commit, with these five paths only:

| Path | Change |
| --- | --- |
| `packages/web-runtime-platform/web/runtime_types.d.ts` | Exclude the legacy FX arms from HeaderedEvent; declare distinct engage, move and release shapes. |
| `packages/web-runtime-platform/test/runtime_session.test.mjs` | Add public-boundary headered and legacy serializer oracles, preserving every existing case and assertion. |
| `apps/creator-web/test/runtime_sdk_headered_fx.types.ts` | New compiler-only positive/negative assignments against actual exported SDK types and positive shared-method calls. |
| `apps/docs-site/docs/core/modules/web-runtime-platform.mdx` | Document exact FX inputs, Core-issued bindings, legacy/shared-method boundary and evidence limits. |
| `docs/plans/2026-10-13-sdk-headered-fx-type-closure.md` | This implementation, verification, documentation and version accounting. |

No runtime serializer, controller, worklet, Core, consumer, compiler config,
lockfile, manifest, Product Build, snapshot or Contract identity changes.
C1 Source11 and D03 Source5/shared Creator/browser reservations remain frozen.
The held native content and its Dispatch are outside all source, command and
evidence access. No old candidate is imported or foreign resource modified.

## Public contract and acceptance

- Engage is `{kind: "fx_engage", fx, value}`. The caller supplies neither
  `gestureId` nor `gestureGeneration`; Core returns both identities.
- Move requires `{kind: "fx_move", fx, value, gestureId, gestureGeneration}`.
- Release is `{kind: "fx_release", fx, gestureId, gestureGeneration}` with no
  value. Move/release echo the Core mapping, never invented legacy identities.
- Explicit optional `never` properties prohibit engage's identity fields and
  release's value on the approved nonfresh object boundary as well as literals.
  This is not a generic exact-object framework: TypeScript structural typing
  cannot replace runtime exact-key checks for arbitrary extra properties.
- Preserve `PerformanceRawEvent`, non-FX HeaderedEvent arms, Filter vocabulary,
  begin overload order and the shared `recordPerformanceEvent` union. The
  method intentionally accepts legacy input and cannot infer runtime profile.

The compiler fixture uses the actual SDK export, no copied interface, cast or
product suppression. Positives cover all seven non-filter FX names, required
move value, no-value release, retained Filter/Pad/HOLD inputs, legacy RawEvent
and shared method calls. Negatives target HeaderedEvent itself: fresh and
nonfresh legacy identities on engage, missing move/release identities,
missing engage/move value, wrong field types and a release carrying value.
Intentional `@ts-expect-error` assertions live only in this `.types.ts` fixture.
The original Creator configuration already includes `test`; `.test.ts` naming,
dummy Vitest suites and compiler include changes are unnecessary.

The runtime additions start the profile through public begin, then assert
complete engage/move/release wire payloads, opaque Core cursor progression and
returned mapping projection. Matching move/release identities come from the
public engage receipt. Invalid shapes reject before transport; a subsequent
valid event asserts the same expected sequence, the far side of each refusal.
The legacy case keeps its ID-bound shapes and wire, and rejects no-ID engage
and headered-only generation keys. Existing raw bridge, real capture pipeline,
dual-ready gate, Core mapping and original serializer tests remain intact.
Fixture receipts are SDK/protocol evidence, not real Core DSP execution.

## Verification plan

Initial SOURCE phase runs no install, test, type, Portal or build command.
All commands below are future argv, subject to Root's concrete resource window.

| Owning check | Defect covered | Status |
| --- | --- | --- |
| Complete SDK runtime-session/capture-controller/worklet suites | Public serializer/profile mismatch, mapping/cursor loss and capture regression | UNRUN |
| Entire original Creator TypeScript configuration with its locked compiler | Exported HeaderedEvent accepts invalid FX or rejects valid input; existing legacy consumers break | UNRUN |
| Complete unchanged Portal check | Module API documentation, metadata, source facts, build, routes and links drift | UNRUN |
| New-file scope ownership check before eventual push | Newly added fixture/plan omitted from canonical change ownership | UNRUN |

From repository root, with a pinned Node 26 executable:

```sh
node --test packages/web-runtime-platform/test/runtime_session.test.mjs packages/web-runtime-platform/test/performance_master_capture.test.mjs packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs
bash scripts/docs-site.sh check
python3 tests/build/ci_change_scope_test.py
```

From `apps/creator-web`, using the lockfile's TypeScript 7.0.2 launcher:

```sh
node ./node_modules/typescript/bin/tsc --noEmit --project tsconfig.json
```

Pin the actual executable, installed compiler/native backend, package/lock and
original configuration bytes before execution. Dependencies must be installed
from the unchanged lockfiles only when admitted; do not use global `tsc`,
`npx` downloads or a bespoke configuration. Preserve complete raw logs, natural
child and actual caller exits, including failures. Do not filter test names,
widen budgets, remove assertions/journeys or borrow predecessor passes.

No new universal gate is introduced. Browser/OPFS, hearing, native/Wasm/stress,
packaged replay and full candidate acceptance remain separate and unverified;
they require their original owning journeys and cannot be cleared by these
compiler/SDK/Portal checks. C1 integration and Goal completion remain later.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/
Reason: the public HeaderedEvent FX type shapes and compatibility boundary change.
The Module topology is unchanged, so no source diagram change is required.

## Version Management

Version impact: public Module type/API narrowing, retained for Goal V1.
The base manifest records `web-runtime-platform` 5.8.0, API version 2,
Application Facade dependency 6.7.0 and Audio Runtime dependency 5.2.0.
These are observed base facts, not newly allocated identities.

Correct no-ID headered engage becomes expressible; previously admitted invalid
HeaderedEvent FX forms become compile errors, including specified nonfresh
objects. RawEvent and valid legacy runtime inputs stay compatible. This public
type narrowing is real compatibility debt; unchanged manifests do not make its
version impact none. Runtime serialization and C++ ABI layout do not change.

Goal V1 must assess the narrowing under independent Module SemVer and settle
the actual API/dependency closure at a verified integrated cut, together with
existing upstream debts. Target Module/API identity, Product Build and Channel
are deliberately unallocated here. No manifest, Assembly/lock, schema, snapshot,
tag or migration is produced; Project/Contract wire formats remain unchanged.
Any later identity cut needs its own declared inputs, owning checks and snapshot
provenance. There is no Release, deployment or Channel promotion in this Task.
Rollback of this source Task means an ordinary reviewed revert; it does not
rewrite any immutable release identity.

## Shipping boundary and pitfall disposition

After Root supplies verification/shipping disposition, follow current
`issue-done`: one declared Conventional Commit, safe push/PR, genuine independent
current-head review, findings/conversations/protection/conflict checks, guarded
squash and actual integrated provenance. Refresh relevant main premises again.
Initial source packet is neither verification nor Task settlement; no staging,
commit, push, PR, review, merge, worker completion or cleanup occurs in this phase.

Applicable open core/Creator pitfalls were read. Preserve deferred evidence as
debt, source/fixture/native evidence separately, and working bytes before any
later admitted mutation proof. This type defect is fully expressible in the
owning compiler/serializer fixtures, so it introduces no separate process
pitfall entry; any newly observed process recurrence requires its own disposition.
