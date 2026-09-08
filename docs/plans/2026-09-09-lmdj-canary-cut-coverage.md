# T2c — Moving-main coverage checks

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tools/canary/cut.py`
- `tests/build/ci_canary_cut_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress only).

Implement read-only pre-merge and post-squash coverage checks on actual Git
objects. The caller supplies authenticated assessed target, current reviewed
base/head, observed main and trusted control identities plus the complete
declared allocation output inventory. Require one reviewed commit and a single
parent squash. Enumerate all intervening first-parent commits, not just endpoint
diffs. Use the existing historical/current policy union for explanatory-docs
exceptions; no arbitrary caller-supplied irrelevant-path allowlist.

Before merge compare every reviewed output's original mode/object against the
current merge base. After merge require the entire squash delta (paths, modes,
old/new Git objects) to equal the exact reviewed delta. Renames become explicit
delete/add pairs. Unexpected files, changed output bytes, deletions or mode
changes remain visible. Reverted intervening product edits still require renewed
assessment. A later main does not retarget an already merged candidate.

Return sealed `covered` or `needs-assessment` coverage data, never release
admission. Malformed/missing histories or unknown source states fail closed with
why/remedy. No model execution, writes, version allocation, lease, occupancy
claim, automatic merge, signing, publication or deployment. Authenticating the
reviewed GitHub head/receipt and canonical allocation outputs, three-attempt
fenced cut coordination and post-squash snapshot witness remain separate required
work. A declaration alone cannot prove an allocation is metadata-only.

## Verification

Missing-module red, then real temporary Git histories: unchanged base, harmless
docs, routed docs, foundational changes, intermediate edit/revert, moved output
preimage, exact squash, tampered/extra/deleted/mode-changed output, multiple-parent
merge, later main, side-branch/missing objects, changed policy, undeclared files,
replay and dirty-tree immunity. Full canary and CI contract tests, staged
ownership, Portal check and final range/PR declarations. No fixture substitutes
for live cut contention, candidate allocation or provider/Release evidence.

## Version Management

Version impact: none
Reason: internal Git coverage tooling; no active manifest, Assembly, Product or
snapshot is allocated or changed.

## Documentation Impact

Documentation impact: none
Reason: no operator entry point, active trigger or Portal fact changes. A future
cut coordinator must document its operator and release boundaries separately.
