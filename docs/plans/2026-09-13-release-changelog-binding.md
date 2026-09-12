# R3b.2: bind frozen changelog through publication and audit

Status: locally verified binding, stacked on frozen artifact `b4995f4f`.

## Scope

Add an optional inline `changelog` document to reviewed release intents, closed
and deeply immutable after parsing. It must exactly match the Web Hosts Product
tag, Build, profile and candidate. Existing historical entries omit it and retain
their original plan/marker bytes; no published history is rewritten.

For bound intents, prepare revalidates exact Git source scope before generating
output. Plan JSON contains the frozen document, so its canonical digest binds all
notes and exclusion reasons. One renderer produces release-notes.md; prepare
resume checks exact bytes. Draft creation refuses local notes drift. Remote
Draft and published verification reconstruct the plan from canonical authority
and check the entire rendered body, including its exact permanent marker.

Marker v4 carries the frozen document digest and rendered notes digest together
with the existing exact CI reference when present. Independent remote audit
validates that binding and the entire body too; a historical missing-marker
exception cannot excuse a bound changelog. Release inventory remains six assets.

The frozen inline document will also be the doc-site generator's source. Website
rendering, Git-triggered publishing, online validation and mandatory admission
for new orchestration requests remain subsequent work. Optional historical
compatibility is not the final new-release admission policy; do not mark the
single-command goal complete before that admission and both destinations exist.

Declared files:

- `tools/release/model.py`
- `tools/release/prepare.py`
- `tools/release/transitions.py`
- `tools/release/audit.py`
- `tests/build/release_changelog_binding_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/governance/version-management.md`
- `docs/plans/2026-09-13-release-changelog-binding.md`

## Verification

The new binding suite exercises prepare → Draft → verify → publish →
verify-published → independent remote metadata audit with existing fake signed
tag/API/assets fixtures. It asserts six assets and identical body across the
publication transition. One-fact faults cover local notes, Draft text, public
text, ledger drift, source failure, marker digest and legacy missing-marker
exceptions. The real-Git source suite remains the companion proof; mock Git/API
fixtures do not establish actual signatures, credentials, deployment or release.

Run release_changelog_binding, release_model, release_prepare,
release_transitions, release_audit, release_batch_binding and
release_self_test_evidence test scripts; staged scope, Python compilation,
Portal check and independent review. No existing verification leg is removed
and no coverage floor, gate or timeout is loosened.

Verified 2026-09-13: binding 13/13, real-Git changelog source 17/17, model 28/28,
prepare 45/45, transitions 66/66, audit 71/71, batch binding 14/14, self-test
evidence 19/19, skill 13/13 and staged ownership 74/74; Python compilation and
Portal check (46 routes/internal links) passed, all exit 0. The binding journey
also runs through the production complete-batch evidence GET/verifier against
real temporary Git and authenticated API fixtures, retaining all 16 suites.
Independent review identified free-text protocol names being counted as extra
markers; v4 now relies on actual marker uniqueness and exact body equality.
Legacy marker protection remains unchanged. A last-authority-read intent drift
test verifies publication is refused before PATCH. No new pitfall entry: these
defects are directly expressed by regression tests. No actual Release, signing
key, provider API or production deployment was used.

## Version Management

Version impact: none

Reason: repository-internal release intent/marker extension only, preserving
existing history; no Product Build allocation or public Contract identity change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document supported bound-changelog publication and outstanding mandatory
new-release admission/site integration separately.
