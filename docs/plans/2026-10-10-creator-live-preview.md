# Creator touch and overview preview (#1921)

## Premises

Worktree/integration base: `414268d654adeae32dfb500f62c000f06e4f2b47`.
Live #1921 still has disconnected Sequence touch preview/cancel callbacks and
SampleOverview still reads only committed inspect playback. App encoder preview
is a working positive control; SampleSurface already produces synchronous
drafts. #1942 supplies mode-specific overview identity and is in packaged
verification; integrate its actual merged result before final verification.
Other owner's #1936 remains open at `b07e178dfd1c73c654697317aae71cd0f31ade42`;
do not change its bindings or worktree. Refresh its disposition before shipping.

The visual draft must not wait for a previous asynchronous audition response.
SampleSurface currently prefers auditionPlayback to a newer draft. Both screens
must select the same current draft, fall back immediately on cancellation or
failure, and reject a draft from another selected Pad or inspect revision.

## Task and declared files

One Task: connect existing visual previews and settle their ownership without
changing authoring operations, audio audition semantics or the encoder's 400 ms
commit policy. Touch gestures still commit once on release. Mode, Pattern,
Project, recording lock, cancellation and failure must not leak a draft.

- apps/creator-web/src/app.tsx
- apps/creator-web/src/components/sequence_touch_workspace.tsx
- apps/creator-web/src/components/value_slider.tsx
- apps/creator-web/src/components/sample_overview.tsx
- apps/creator-web/src/components/sample_surface.tsx
- apps/creator-web/src/components/waveform_editor.tsx
- apps/creator-web/src/state/sample_state.ts
- apps/creator-web/test/sample_overview.test.tsx
- apps/creator-web/test/value_slider.test.tsx
- apps/creator-web/test/sequence_surface.test.tsx
- apps/creator-web/test/sequence_grid_edit.test.tsx
- apps/creator-web/test/workspace_shell.test.tsx
- tests/platform/web/creator/creator_web_hardware_layout.spec.mjs
- tests/platform/web/creator/creator_web_sample_editor.spec.mjs
- tests/platform/web/creator/creator_web_sequence.spec.mjs
- apps/docs-site/docs/hosts/creator-web.mdx
- this plan

## Verification

First show the disconnected consumer with focused failing regressions. Cover
draft -> cancel, draft -> one commit, commit/preview failure -> authoritative
readout, unchanged revision/history during preview, object/mode changes and
recording locks. Preserve the existing 400 ms encoder tests and audio-suspension
rule: clearing a visual gesture must not call a Host preview operation while
audio is stopped. Verify native pointer/keyboard behavior at real focus, both
screen readouts, complete cancel/retry/Undo/Redo and persisted reopen journeys.

Run the affected component tests, TypeScript/build, actual browser journeys,
portal checks and the committed-head Creator batch lane. Every added assertion
names a behavioral defect; do not reduce existing journey legs or limits.
Physical iPad/Safari/audio-device acceptance remains explicitly unexecuted in
the existing acceptance issues; no release or deployment is included.

## Version Management

Version impact: none — visual Host drafts over existing operations; no schema,
Core/Contract, Product Build or Assembly identity change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Document live visual previews and their cancellation/commit boundary.

## Pitfall Impact

Pitfall impact: none — producer/consumer and gesture ownership regressions
express the invariant directly. Preserve native input and complete journey
guidance, including explicit limits of fault-injection and simulated devices.


## Implementation evidence (in progress)

- Red producer/consumer proofs: Sample upper selection stayed at committed trim;
  Sequence callback tests received no preview; slider no-op release/recording lock
  left shared drafts unsettled. Corrected focused set: 52 tests, then 205 related
  component tests passed. Full base-main component run passed 1173 tests/67 files
  before later lifecycle refinements; final integrated verification remains due.
- Full App regression demonstrated preview rejection restored the upper mask but
  left the lower trim at frame 2 and able to commit on a late pointer release.
  A controlled preview-active signal now clears that gesture without another
  Host cancellation request. This is a product invariant expressed by the test,
  not a new process gate.
- First native preview run: Tempo/reopen and complete Sequence settings journey
  passed; Sample failed after its existing reload leg because audio was suspended
  and `sample.preview.set` was refused. The former editor could still commit the
  stale visual draft after this refusal. Preserve editing before audio activation
  by keeping its draft visual and issuing no inaudible Host preview request;
  a running-audio preview failure still cancels. Add explicit component coverage
  for both states and retain the native full import/reopen/trim journey.
- Current independent #1920 packaged proof exposed three stale address-only
  Sequence row expectations; its owner worktree is correcting those separately.
  No #1920 test, identity or lifecycle scope is silently dropped by this Task.

## Precommit verification at base 414268d6

- Refreshed origin/main remains
  `414268d654adeae32dfb500f62c000f06e4f2b47`; #1936 remains open at the
  recorded head. No intervening implementation supersedes these premises.
- Full component suite after lifecycle fixes: 1176 tests in 67 files passed.
  Added Project/Pattern/recording-lock and stale-selected-Pad regressions then
  passed with their complete two-file suite (31 tests). TypeScript and Vite
  passed again after those additions.
- Real Chromium source UI against the verified packaged Runtime: all three
  complete Hardware/Sample/Sequence files, 21 passed and 1 existing capability
  skip. This includes native focused keyboard preview/cancel, pointer trim,
  exact revision/history assertions, rejection, Undo/Redo and persisted reopen.
  This is source-UI evidence, not the final committed-head packaged batch.
- Portal build passed with all 50 routes and internal links valid.
- Evidence retained under `/tmp/lmdj-ui-goal-20261009/`: final source run
  `1921-complete-source-1.log`, context cases `1921-context-transitions.log`,
  full components `1921-all-components-2.log`, build `1921-context-build.log`,
  portal `1921-portal.log`. Earlier red proofs remain alongside them.
- #1942 integration and the final packaged Creator batch remain outstanding.
  The verified local Task is committed before that integration; do not treat
  this commit as merged delivery or close #1921 from these source proofs.

## Integration premise refresh — 2026-10-10

Refreshed main: `ec15f9adf3ca7c3fd09c06d61b53e0bcdf189fe6`.
PR #1942 is merged and #1920 accepted. Its current-object metadata guards,
mode-specific identity/status projection and full Sequence category labels are
retained. SampleOverview still read committed playback at that main revision;
Sequence touch callbacks still did not produce the shared preview. Therefore
the #1921 producer/consumer and ownership fixes remain necessary. The two
Sample overview merge conflicts preserve both metadata/status regressions and
preview lifecycle regressions; neither set is replaced. Other-owner #1936 is
still open at `b07e178dfd1c73c654697317aae71cd0f31ade42`.

Integrated precommit verification passed: 183 affected component tests,
TypeScript/Vite, 50 portal routes/internal links, and staged ownership 77 tests.
Complete real Chromium Hardware/Sample/Sequence source journeys passed
22 tests with one WebKit-only capability skip (3.5 minutes), including the new
#1920 overview navigation journey. Evidence: `1921-integrated-source-3.log`.
The first two attempts used directories instead of the packed fixture files;
both were stopped with exit 143 and retained as invalid attempts, not passes.
The corrected invocation used each fixture directory's actual `bundle.lmdj`.
Final committed-head packaged proof and independent review remain due.
