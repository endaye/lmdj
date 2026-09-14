# Freeze candidate inputs from exact Git objects

Delivery base: `b79ea6246077a57a1a483b3ab804ed4317c239a9`.
Reapply Task `c7d861039a86123206cd7f8ec75dea29f8914f33`, preserving the
newer passive Git reader, bounded evidence readers and request aliases.

 The Assembly lock binds many component manifest identities,
not every Core/Host implementation byte. Candidate drift detection cannot use
that lock alone. Freeze complete committed path/mode/object identities except
an explicit documentation-only allowance; unknown paths remain included.

Declared files:

- tools/release/candidate_inputs.py
- tests/build/release_candidate_inputs_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-inputs.md

Allowed motion: docs/ except release-evidence, governance and quality; current
apps/docs-site/docs/, diagrams/ and static/diagrams/. Versioned snapshots,
Portal tooling, build/test inputs, governance and release allocation evidence
remain frozen. This is deliberately a candidate-input check, not the narrower
Portal snapshot projection and not a claim every included file is product code.
The guard catches incorporating unreviewed-to-this-request source/build/control
changes before the cut; ordinary main progress after candidate freeze does not
retarget the release. It does not add a general PR merge gate.

Direct committed symlink file/directory targets are included even when they
would otherwise be documentation-only. Absolute, escaping, dangling, chained,
intermediate-link and nested-link/Gitlink targets refuse without filesystem
resolution. Existing repository skill and Portal directory links remain valid.

Use hardened no-transport/no-replace/no-graft Git reads, complete nonshallow
ancestry, raw tracked modes/object IDs and canonical Product version parser.
Read no worktree version identity, execute no candidate source, fetch no object.
Recompute the frozen baseline before comparing current main. A matching lock
with changed Core/Host source must refuse. No new BUILD is allocated here.
The parent still owes authenticated main/request binding, baseline CI evidence,
allocation competition/reservation, real cut PR, snapshot/witness and full
candidate proof. Do not confuse the source guard with those transitions.

## Verification

Temporary real Git histories: unchanged and docs-only advancement succeed;
Core/Host edits with unchanged lock, version allocation, governance/tooling,
snapshot and unknown additions, deletion/mode changes refuse; dirty local
files do not change committed identity; forged baseline/shallow/missing/divergent
history and malformed Product version refuse. Preserve worktree/index/refs.
Run registered source/journal/driver suites, staged ownership, Portal and review.

Original-stack results remain historical, not current-head acceptance.
Current delivery evidence:

- `python3 tests/build/release_candidate_inputs_test.py`: 16/16, 23.943s,
  exit 0; `/tmp/lmdj-candidate-inputs-delivery-tests-v1.log`.
- Actual exact-base freeze and verify against
  `b79ea6246077a57a1a483b3ab804ed4317c239a9`: 4,533 selected inputs, including
  nine symlinks; projection digest
  `6d8368b083f6c907092ffeb458761173501ab91abca7e67e97dd95252c7943f9`.
  Git worktree status was identical before and after; exit 0, retained in
  `/tmp/lmdj-candidate-inputs-delivery-exact-base-v1.log`.
  The result field `observed_main` here is the supplied local base revision,
  not proof that this unmerged dependency stack is GitHub main.
- Independent reviewer `/root/release_journal_review` inspected the complete
  five-file Task and unchanged shared Git reader; no actionable finding.
  Independent candidate tests: 16/16, 22.438s, exit 0; diff check passed.
  This is local review, not owner adoption or remote PR merge eligibility.
- Registered CTest selection
  `^build\.release_(candidate_inputs|orchestration|orchestration_driver)$`:
  3/3, 25.71s, exit 0. Actual child populations: candidate 16, journal 21,
  driver 32, all passed, no skips. Log:
  `/tmp/lmdj-candidate-inputs-delivery-ctest-v1.log`; child output:
  `build/core/dev/Testing/Temporary/LastTest.log` in this worktree.
- After staging the five declared files, ownership/admission suite passed
  74/74 in 5.767s, exit 0:
  `/tmp/lmdj-candidate-inputs-delivery-scope-v1.log`.
- With Node 22 and locked dependencies, `scripts/docs-site.sh check` passed
  144/144 tests, no skips, and 47 page / built-route checks, exit 0:
  `/tmp/lmdj-candidate-inputs-delivery-docs-v1.log`.

No release, deployment, remote CI dispatch or production authorization
acceptance is exercised by this Task. Pitfall disposition: the input/linked
dependency invariant is expressed by direct source regressions; no new
process-only ledger entry. No test budget or gate has been weakened.

## Version Management

Version impact: none

Reason: internal passive candidate-input verifier, no actual Build allocation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
