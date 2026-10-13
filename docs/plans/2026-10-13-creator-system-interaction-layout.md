# Creator System Interaction UI (U11)

## Premises and scope

Root owns U11 under umbrella #2112 and the active multi-agent Goal. Base and
initial main: `fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`. Pre-commit refresh
is `45c8f479aa350cd490a100044a4723428976e2be`: U02a changes rail labels and
SHIFT order, not the System settings or source-selection contract. Its Portal
edits are separate sections; no successor delivers this Task.
Before the clean-source checkpoint, U04 merged as
`50ecc7107a3347878e1d5aa7f72b031d7d58eb98`. The owned 11-file staged patch
was saved with byte hashes, stashed, rebased and applied by its exact stash
object; every owned added/deleted line was preserved. Four shared files gained
the intervening main changes and the other seven stayed byte-identical. The
Project list does not deliver System settings; refresh the complete component
selection and Portal against this combined source before freezing it.
Figma `GPFarNiZNsjLQzfG9kR8DO`, frame `406:2399`, was read with its screenshot.
The current System already supplies Suspend audio, MIDI, Pad recording source,
report export, Provider revocation and diagnostics. No capability is missing.
Its native source selector and ungrouped controls do not match the compact
status card, segmented source selection and disclosure order in the new frame.
No successor in current main delivers this layout.

Preserve real audio/MIDI status, all handler gates, source persistence in Host
settings, capture-time source lock, Provider permission subscriptions, and
ongoing music. Keep Project details mounted so disclosure state survives a
System visit. Opening System focuses its heading; returning restores the Logo
entry. No Project write or audio change is caused merely by opening System.

Declared files (one atomic Task):

- `apps/creator-web/src/components/system_surface.tsx`
- `apps/creator-web/src/components/system_surface.css` (new)
- `apps/creator-web/src/app.tsx` (System/settings/details mounting only)
- `apps/creator-web/test/system_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx` (System/source cases only)
- `tests/platform/web/creator/creator_web_system.spec.mjs`
- `tests/platform/web/creator/creator_web_capture.spec.mjs` (source gesture only)
- `tests/platform/web/creator/creator_web_perform.spec.mjs` (source gesture only)
- `apps/docs-site/docs/hosts/creator-web.mdx` (System paragraph only)
- `apps/docs-site/docs/hosts/creator-interactions.mdx` (System rows only)
- this plan.

U04 owns Project, U09 owns Sound Sets, and U03 owns overview source. Their App
and documentation sections are separate; Root serializes shared-file integration
and heavy checks. Do not write global `styles.css`, capture/transport controllers,
Runtime, SDK or Core. The authorized Portal sections were edited after the U03
document freeze and are now frozen for the other owners.

## Verification

Run complete `system_surface` and `workspace_shell` component files plus full
TypeScript check. Existing Provider race tests remain. New component checks
cover native button activation of segmented selection, disabled capture-time mutation, truthful
status and retained details/focus through System hide/show.

Fresh normal Creator build/package, then the complete System browser file,
and the complete affected empty-Pad microphone and master-resampling journeys
in their owning capture/Perform specs with unchanged deadlines and every leg.
The only source-gesture substitutions are shared TouchSegment buttons replacing the
old native select; retain PCM, persistence, reopen and identity assertions.
Add actual layout checks at the supported viewports, focus return and device
source persistence while verifying Project Truth is unchanged. Run full Portal
check and new-file ownership tests. No new universal gate.

Packaging requires a clean tree: after all dirty-executable checks pass, make
one local source checkpoint, then fresh build/package/browser. It is not a
shipping claim. Amend the unpublished checkpoint if fixes are necessary, repeat
affected checks on the final artifact, and push only after all Task checks pass.
Retain every failed receipt. Physical touch/MIDI/listening and final integrated
candidate remain separate; small-screen effective 44 px geometry is pending D0.

Current source verification: the complete `system_surface` and `workspace_shell`
files passed 198/198 tests (77.15 s, `/tmp/lmdj-u11-components.log`); whole
TypeScript check passed (`/tmp/lmdj-u11-tsc.log`). Syntax checks passed for all
three changed browser files, and whitespace checks passed. Portal, fresh normal
build/package, all four System browser cases and the two complete affected
capture/Perform journeys remain UNRUN pending the serialized heavy window.
Whole Portal on the initial source subsequently passed: 177 tests, 52 current
pages, 10 source diagrams / 20 outputs, 50 built routes and internal links
(`/tmp/lmdj-u11-portal.log`, exit 0). The staged ownership suite passed all
77 tests (`/tmp/lmdj-u11-staged-scope.log`, exit 0). Source review by independent
Codex `control_kit` found no actionable findings across all 11 files; browser
geometry and actual capture journeys remain outstanding, not inferred from it.
After integrating `50ecc710`, the complete component selection passed 200/200
tests in 71.52 s, full TypeScript passed, and the complete Portal check again
passed 177 tests / 50 routes and internal links. Receipts use the
`/tmp/lmdj-u11-*-50ecc710.log` prefix. This qualifies the local clean-source
checkpoint only; fresh build/package and all declared browser journeys remain
UNRUN until the resulting artifact is actually exercised.

## Review correction

The initial published head `97f77f39a65cc6738518b75dda4f7cea32a63174`
passed its normal build/package, four complete System browser cases and both
complete microphone/Perform journeys. PR #2121's trusted review identified
one actionable wording issue: source changes are also locked during permission,
preparation and review, not only while recording. Replace the disabled hint
with neutral availability wording, preserving the controller and all gates.
The owning component assertion checks the corrected copy. The other three
findings were independently checked: the source segments have no local state
and retain the previous conditional mount; all six audio phase words describe
the actual state; Export report remains within the named System region.
These dispositions will be recorded on their review threads. The copy repair
requires its owning component file and TypeScript checks; the next normal
artifact will rerun the complete System browser file. The two unaffected
capture journeys remain passed on the prior artifact, with no changed handler,
state machine, gesture, persistence or assertions. A later integrated candidate
must still verify its complete scope.

## Version Management

Version impact: none
Reason: UI presentation and equivalent device-setting gestures only; no
Product Build, Module, Host, Provider or Contract identity allocation. Retain
the existing Creator version debt for the separately selected candidate.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web /hosts/creator-interactions
Reason: source selection and System layout change, while all existing music,
permission and reporting behavior remains reachable.

## Pitfall Impact

Pitfall impact: none — existing worktree, complete-journey and native-input
guidance applies. Reassess before shipping if a new process defect is found.

## Authority

The Goal authorizes implementation, verification, commit, push, PR, independent
current-head review and guarded squash merge. No release, deploy or cleanup.
