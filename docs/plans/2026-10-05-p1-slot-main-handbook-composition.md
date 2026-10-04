# Compose captured Main handbook update into P1 slot acquisition

## Problem and Task

The user requested current Main in the P1 branch. The prior real merge
`ec85ac924953fa59e308acb58b6b3169e61108f9` contains Main
`0050db4a4f360151dbcc13c30e1f1a2a4be14204`. A fresh remote read captured
`57f8803599a2eedee0312582971125a3596840f3`, which adds only the ESP32
firmware handbook and its index and plans. Import those four exact Main blobs
through a real ordered-parent merge. Preserve every P1 source, manifest,
snapshot, original result and earlier implementation byte outside those imports.
This captured import does not imply a strict-update merge gate or release.

## Declared files

- `docs/README.md`
- `docs/deploy/esp32-firmware.md`
- `docs/plans/2026-09-09-esp32-firmware-handbook.md`
- `docs/plans/2026-10-05-esp32-firmware-handbook-recovery.md`
- `docs/plans/2026-10-05-p1-slot-main-handbook-composition.md`

## Verification

Compare every prior tracked entry outside the four imports with its original
mode and blob, and all imports with captured Main. Verify the handbook's local
links against tracked files, parse its shell examples without executing them,
and compare its current entrypoint and pinned SDK statements with the retained
stable script. Run the complete official `scripts/docs-site.sh check` for the
documented source facts. Check staged path ownership, declared files and
whitespace, then inspect the committed tree, ordered parents and clean worktree.
Classify the complete current PR range and record its current input keys before
normal fast-forward push to the existing PR. Historical whole-lane results and
owner adoption remain tied to their original inputs and source; no result is
manufactured for this new commit. No new test or gate is introduced.

## Version Management

Version impact: none. This exact integrated handbook import and composition
plan allocate or change no Product, Module, Host, Provider or Contract identity.

## Documentation impact

Documentation impact: none
Reason: the imported independent experiment handbook and process index change
no portal route, diagram, projected identity, product behavior or acceptance rule.
The official portal check still verifies documented source facts in this tree.

## Acceptance boundary

This Task fulfils the captured Main import. The remaining P1 integration,
current-input verification, independent review and trusted device acceptance
remain separate obligations. No release, publication, deployment, Channel
promotion, branch cleanup or worktree cleanup is performed here.
