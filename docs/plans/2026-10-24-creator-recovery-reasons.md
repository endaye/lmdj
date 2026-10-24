# Readable recording recovery reasons

Parent: #2112. Partial delivery for #2229.

## Premises at the integration base

Base: `60d4f647855d952b838a7fe6047776da3f393296`.

- Delivered: #2448/#2450/#2451/#2485/#2486 cover retry/takeover presentation
  and the original close result. Do not repeat those changes.
- Outstanding: `SequenceTouchWorkspace` and Perform Replay render
  `candidate.reason` verbatim. The Perform controller also derives its visible
  recovery status by replacing underscores. `owner_lost` is a concrete
  positive control: the existing packaged Sequence owner-loss journey actually
  requires that internal token in the visible recovery region. This does not
  meet the #1680 user-language rule or #2229 readable owner-loss outcome.
- Producer facts: Sequence recovery seals a no-longer-live admission owner as
  `owner_lost`; Performance listing may still return its original `active`
  journal before an explicit Apply/Discard reconciles it. Do not infer a new
  owner state from a browser crash or rename `active` as confirmed owner loss.
  The Facade and SDK retain original strings. Producer states are active,
  switching, stopped, recovery_required, owner_lost and abandoned; sealed
  reasons and future strings also require a safe presentation fallback.
- Delivered: the original complete Sequence keep/apply/fresh-record/reopen and
  real-process Performance apply/save/replay/discard/reopen journeys exist.
  Reuse every leg. Recovery policy, candidate identity, raw reason, counts,
  fingerprint, Project Truth and timing are outside this presentation change.

## Task and declared files

One Conventional Commit over twelve files:

1. `apps/creator-web/src/state/error_messages.ts`
2. `apps/creator-web/src/state/perform_state.ts`
3. `apps/creator-web/src/components/sequence_touch_workspace.tsx`
4. `apps/creator-web/src/components/perform_surface.tsx`
5. `apps/creator-web/test/error_messages.test.ts`
6. `apps/creator-web/test/sequence_surface.test.tsx`
7. `apps/creator-web/test/perform_surface.test.tsx`
8. `tests/platform/web/creator/creator_web_sequence.spec.mjs`
9. `tests/platform/web/creator/creator_web_perform.spec.mjs`
10. `apps/docs-site/docs/hosts/creator-web.mdx`
11. `apps/docs-site/docs/hosts/creator-interactions.mdx`
12. `docs/plans/2026-10-24-creator-recovery-reasons.md`

Use the existing user-message catalog for short readable reason labels. A known
`owner_lost` says the recording Session ended, while `active` only says the
recording is unfinished. Unknown reasons say review is needed, never expose
arbitrary codes/private strings or pretend the recording is complete. Apply
the same wording to the Perform status without changing the candidate itself.
Do not add automatic recovery, retry, generic modal or diagnostic Contract.
The original raw reason stays available through the existing SDK recovery list;
System report and recovery entry points remain as they are.

## Verification

- First establish mounted Sequence/Perform RED at their real text assertions,
  with existing unknown/owner-loss candidate fixtures; verify the raw candidate
  and recovery actions are unchanged after the fix.
- Exact catalog expectations for each named reason and safe unknown/private
  input fallback. No agreement-only oracle between consumers and formatter.
- Complete Creator UI unit suite, types/build, full Portal and staged/committed
  ownership. Preserve existing warnings and negative evidence.
- Official clean ordinary Node26/Emscripten6.0.5 package. Run both complete
  Sequence owner-loss journeys and the complete real-process Performance
  apply/save/replay/discard/reopen journey. At the UI assertion also inspect
  the actual SDK candidates, asserting the original raw producer reason.
- Preserve all original crash, explicit decision, heard-tail, held-input,
  revision, draft save/discard and persistence assertions and original budgets.
  The original genuine owner loss must not be replaced by a manufactured
  candidate or lifecycle event. Any unexecuted leg remains a gap.
- The packager requires a clean source: after owning tests/build/Portal and
  staged checks, commit the declared Task, then package and complete browser
  verification on that exact clean head before push/PR. Do not bypass clean
  source or call a source commit completed browser/candidate evidence.
- Refresh main premises before commit and guarded merge, obtain independent
  current-head review and inspect all findings/threads/protection/freeze.

## Version Management

Creator Host PATCH impact: compatible user-language correction, absorbed into
the existing higher #2237 same-domain debt. No SDK/API/ABI, stored reason,
Project schema, manifest, Product Build, Assembly or snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/

Explain readable recovery reasons, neutral unknowns and original SDK values;
do not imply Apply/Discard is automatic or an active journal proves owner loss.

## Pitfall disposition

This product regression is expressed by its tests. Apply the existing complete
journey, independent oracle, synthetic-side-effects and retained-evidence rules.
No new process-ledger mechanism or frozen release/CI path belongs to this Task.
