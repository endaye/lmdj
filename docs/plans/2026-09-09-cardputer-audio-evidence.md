# Cardputer ADV bounded audio evidence consolidation

Date: 2026-09-09. Documentation baseline:
`9d4bf08361966e6062bc6c109706e769b2cc3161`.

The user confirmed two identical 1000-Hz direct/Core auditions, then confirmed
the independent baseline/double/baseline level audition had the expected
pattern and no harshness or breakup. The next “继续” is handled as one
evidence/documentation Task, not another device experiment or a production
Host/volume decision.

## Task and declared files

Retain the chronological failed/pending observations and the later exact-image
human confirmations, reconcile current Portal evidence, and name all remaining
full-Host acceptance gaps. One Conventional Commit contains:

- `docs/plans/2026-09-09-cardputer-audio-evidence.md`
- `docs/research/2026-09-09-cardputer-audio-hearing.md`
- `docs/plans/2026-09-09-cardputer-allocation-order.md`
- `docs/research/2026-09-09-cardputer-allocation-order.md`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/platform/native-audio.mdx`

No product/probe code, toolchain installation, firmware/reset, original backup,
raw evidence, CI/gate, diagram edge, Product Assembly or default gain changes.
Existing diagnostic sources, binaries and raw records remain external; this
Task does not promote a probe into a supported Host or upload private logs.

## Verification

Lowest-tier baseline: current Portal metadata/source-path validation before
editing its pages. Re-read actual native/build/device receipts and verify
their byte lengths/digests. Run the existing offline full-journey checkers
against both retained 1000-Hz Core runs and the standalone frequency/level
runs; these do not reset or communicate with the board.

Map every exercised load/start/receipt/stop/silence/unload/refusal/retry/cleanup
leg to the retained far-side check. New-content replacement, physical
disconnect policy, Pattern interaction, sustained musical load, physical
I2S/analog capture, p99.9/underrun and a complete product Host remain gaps.
Human observations come from the user's responses, not serial PASS markers.

Run `scripts/docs-site.sh check` for affected Portal pages, `git diff --check`,
and a local report/link/identity audit. After exact-path staging, run
`python3 tests/build/ci_change_scope_test.py`; inspect the complete staged
diff, commit, classify the final range, validate the PR body and obtain
current-head review before an authorized squash merge. No new global gate,
threshold change, omitted lane ownership or shortened acceptance journey.

Pitfall impact: none — reason: this Task applies the existing exact-identity,
human-hearing and full-journey guidance; it introduces no new process defect
or product fix. Earlier failed probe/verifier attempts stay visible.

## Version Management

Version impact: none
Reason: evidence-only documentation; no API/ABI, Contract, Provider, Host,
Product Build, Assembly, package distribution or default audio policy changes.
No tag, snapshot allocation, Release, deployment, Channel promotion or cleanup.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /platform/native-audio/
Reason: current pages must distinguish exact-image human hearing from native/
digital automation and retain the full Cardputer Host acceptance boundary.
No component ownership or dataflow edge changes; diagrams remain unchanged.
