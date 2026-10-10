# Product cut source/snapshot bootstrap

## Outcome and scope

Make the clean-source snapshot requirement compatible with a new Product Build's
required matching snapshot, without weakening either check. A cut uses an exact,
already-merged, CI-verified `main` implementation baseline and two linked atomic
Tasks: S0 supplies the committed allocation/freeze source; S1 supplies its
immutable snapshot. Each Task is one Conventional Commit. They ship together in
one PR only after the original complete checks pass.

The route covers the identity/dependency closure actually required by that
baseline, including Module, Host, Provider, Contract and Product settlement.
Compatible formalization of an existing registered Contract is an explicitly
declared adjunct, with schema, conformance, fixtures and grammar. Formalization
does not establish producer, consumer, DSP or Replay support. New behavior,
unmerged implementation, unrelated Contract changes and changes to generators,
validators, workflow or protection do not belong in an allocation cut.

**G0 is only the governance/Portal/skill change in this plan.** It allocates no
Product, Module or Contract version, creates or deletes no snapshot, implements
no runtime feature and performs no release, deployment, Channel or cleanup
operation. Future S0/S1 cuts need their own exact declared files, target Build,
channel, identity/compatibility evidence and applicable verification; this plan
does not allocate those values or authorize their retention deletions.

## Task-start premises

- The implementation source audit and this isolated branch start at freshly
  fetched `origin/main` `806a58b2fa4c9f556b8b4158577a3f9202f85969`. D0 PR
  [#2003](https://github.com/endaye/lmdj/pull/2003) merged that source. Its
  live-control syntax plan exposes a real Project Contract/Assembly version
  settlement prerequisite, separate from P0 producer implementation.
- The root checkout was independently observed at
  `4a2b26f03a1e628882e907c92a9b9411b48e110d` during this Task's start. Root
  checkout updates and other agents' shipping are not this Task's edits. G0
  does not switch, reset, stage or modify that checkout.
- Live open PR file lists for #2000, #2001, #2002 and #2004 did not intersect
  these eight paths at Task start. Fifteen local worktrees were inspected;
  none had an uncommitted overlap with these paths. Local Orca ownership was
  refreshed. Remote worker ownership was not established by that local
  response and is not reported as absent. Fresh overlap/head review remains
  required before shipping.
- [#1822](https://github.com/endaye/lmdj/issues/1822) remains open. Its approved
  product decisions are not reopened here. The pending Mute tail decision
  blocks M1, not this governance change or P0's independent preparation.
- Read `AGENTS.md`, `issue-done` Task-start/verification/shipping rules,
  pitfall-ledger contract and all open `area:docs-governance` entries. The
  existing `portal-snapshot-not-deferrable` history is preserved. This Task
  records its own observed recurrence and absorbs it into an eligible skill
  mechanism, rather than creating a sibling ledger entry or a new gate.
- The independent version-route review identified that a Contract-only
  exception would not cover the Goal's eventual ordinary Module/Host identity
  settlement. G0 therefore specifies the generic verified-main identity cut,
  with a compatible registered-Contract adjunct explicitly declared.

A handoff refresh observed `origin/main`
`5d31f21bb7b5f91014881c05b0ef7f4708c03b29`: #2002 added one independent
Pad/Bar observation pitfall, one plan and two Creator tests. None intersects
G0's eight files, owning version/snapshot tools or bootstrap premises. G0 keeps
its explicit `806a58b2` worktree base; this refresh is not attributed to G0.

These are source/ownership premises, not claims that this docs draft or a later
allocation source has passed exact-main CI. A later main advance alone does not
require rebasing G0; actual conflicts and changed owning premises do require
reassessment and affected checks under canonical workflow.

## Owning source/tool facts

| Source | Actual fact and defect the proposal addresses |
| --- | --- |
| `docs/governance/version-management.md` §2.3/2.4/9 | Assembly/Contract identity settlement requires a new BUILD and generated lock; PATCH cannot absorb it. A source Build/snapshot need not initiate a Release. |
| `apps/docs-site/scripts/lib/repo-facts.mjs` | Current facts verify the active Assembly/lock, selected registered Contract versions and schema hashes. Keeping an old identity/hash over new syntax is not a valid route. |
| `apps/docs-site/scripts/lib/version-docs.mjs`, `validateReleaseSnapshot` | A wholly absent new Build snapshot produces exactly the three missing prerequisites below. Old Build identity or partial/invalid snapshot errors are different failures. |
| `apps/docs-site/package.json` | Full `check` reaches release-docs before typecheck/build/routes. Separate entire `check:current` execution covers that far side; an early-stopped full-check prefix cannot prove it. |
| `version-docs.mjs`, `freezeVersion` | Official freezing requires matching active Build, clean worktree and actual HEAD. It runs entire current checks, generates the boundary, then runs original full check. A synthetic source SHA is rejected. |
| `version-docs.mjs`, `resumeVersion` | Resume validates the complete original uncommitted freeze, its source/channel/metadata/inventory/provenance and full check; it does not create missing output or overwrite a failed freeze. |
| `apps/docs-site/scripts/lib/snapshot-provenance.mjs` | Baseline, raw freeze source and introducing commit have different roles. Projection/witness validation binds actual bytes/identities, not a fabricated main ancestor. The audited source declares 52 current docs and 10 diagram IDs; future boundaries are read from their actual source, not guessed from these counts. |
| `scripts/docs-site.sh` | Stable operations are `check`, `version`, `resume-version`, `witness` and `verify-witness`; freezing/resume use the actual source revision. G0 changes none of their implementation. |
| `scripts/version.py` | Existing owning verify/lock interfaces establish version and dependency consistency; G0 invents no allocation command or validator exemption. |

The original whole-check prerequisite and clean-source freeze requirement form
an allocation bootstrap cycle. The explicit source checkpoint is a bounded
phase definition, not an alternate green verdict or a general failed-check
commit exception.

## Canonical S0/S1 phase contract

A future cut plan declares the exact implementation baseline, version/identity
closure, registered-Contract adjunct (if any), source/current files and applicable
owning checks before S0. Any canonical retention adjustment needs its own exact
inventory and applicable authorization in that S0 source scope; it is not hidden
in the S1 generator boundary. No Build number or source SHA is guessed here.

### S0 — clean source checkpoint

1. Perform only the cut's declared allocation/identity/lock/deterministic-current
   changes and compatible Contract adjunct. Prove each change against the exact
   already-merged baseline's public API, ABI, behavior and real dependencies.
2. Pass all owning source, version and conformance checks and the entire Portal
   `check:current`. Also actually run `scripts/docs-site.sh check` and retain its
   real exit status, complete output and identities.
3. The only permitted nonzero whole-check condition is a new Build **B** whose
   versions entry, snapshot source and metadata are all absent, with the exact
   complete error set:

   ```text
   Product Build B is missing from versions.json
   Product Build B snapshot source is missing
   Product Build B metadata is missing
   ```

   B is the future cut's actual declared Build. Existing or partial snapshot
   bytes, another Build's missing snapshot, identity/hash mismatch or any other
   unit/current/diagram/changelog/type/build/route/provenance failure stops S0.
   The nonzero result stays nonzero in evidence; it is never reported as PASS.
4. Commit only declared S0 files, one Conventional Commit, after branch/staged
   scope/whitespace checks. Record its real full SHA and verified-main baseline
   separately. This is a local clean freeze checkpoint, with no standalone
   push, PR, merge, distribution or Task-complete qualification.

### S1 — matching immutable snapshot and shipping

1. At that unchanged, clean S0 HEAD run the existing official
   `scripts/docs-site.sh version PRODUCT_BUILD CHANNEL`. Inspect its actual
   generated boundary and stage only that boundary for S1. Do not add current
   source edits, old snapshot deletions or hand-edited metadata.
2. Require the original complete Portal check and every applicable cut Task
   check to pass before S1's one Conventional Commit. The two linked Tasks may
   then ship in one PR under unchanged exact-head review, batch-only evidence,
   conflict/conversation/finding checks and live protection. S0 never ships
   alone. Accepted-risk, old snapshots, old PASS or current-only results cannot
   replace this final complete check.
3. Keep the CI-verified implementation baseline, allocation/freeze source and
   actual squash-main target distinct. Freeze source projection stays unchanged.
   Validate the frozen source and branch projection before merge, without
   inventing a future main SHA. After merge validate byte-identical squash
   projection against the actual introducing SHA; if required, an official
   witness belongs in its
   own applicable Task. A snapshot-only Task whose Build/BOM is already in main
   retains the first/only-commit direct-parent preference.
4. If freezing is interrupted, preserve original source HEAD, logs and generated
   bytes. `scripts/docs-site.sh resume-version PRODUCT_BUILD CHANNEL SOURCE_SHA`
   only validates a complete original freeze. Partial, mismatched or unverifiable
   results remain stopped for explicit reconciliation; no generic delete/refreeze
   or metadata edits conceal the failure.

A Release intent binds the actual protected-main squash target only after it
exists. Source allocation/snapshot does not grant Release or cleanup authority.
Baseline CI is not the actual target's candidate verification.

## G0 implementation Task

Task G0: one docs-only Conventional Commit in
`docs/product-cut-snapshot-bootstrap`, isolated ordinary worktree. The exact
**eight** declared files are:

1. `docs/governance/version-management.md`
2. `docs/governance/git-workflow.md`
3. `docs/governance/architecture-portal.md`
4. `.agents/pitfalls/portal-snapshot-not-deferrable.md`
5. `apps/docs-site/docs/operations/documentation-governance.mdx`
6. `apps/docs-site/docs/operations/version-and-release.mdx`
7. `docs/plans/2026-10-11-product-cut-snapshot-bootstrap.md`
8. `.agents/skills/issue-done/SKILL.md`

The skill addition points prerequisite verification to the canonical phase
sequence and explicitly preserves final full checks and exact-head shipping.
The qualifying recurrence is therefore absorbed by a concrete skill mechanism;
no new fuzzy policy gate or validator change is introduced. Its GitHub
occurrence points to the actual retained #1822 Goal, with this plan providing
the concrete source/tool observation; the original occurrence is unchanged.

### Lowest-tier verification and completion boundary

| Check | Defect caught |
| --- | --- |
| Existing Python `lint_entry` on the changed pitfall (and existing ledger suite before shipping) | Invalid recurrence/date/agent attribution, malformed exit, missing enforcing skill or skipped recurrence-2 absorption/escalation. |
| Declared-file/status/diff check plus relative links, frontmatter source paths and source-count inspection | Undeclared edits, broken canonical mechanism links or Portal claims inconsistent with the audited owning source. |
| Original `scripts/docs-site.sh check` | Portal unit/metadata/current facts/diagrams/changelogs/type/build/routes/links or existing immutable snapshot/provenance broken by this docs Task. G0 is not an allocation Task and has no missing-snapshot exception. |
| Existing `python3 tests/build/ci_change_scope_test.py` before push | A new plan or skill/governance path becoming unowned or causing conservative lane-selection regression. |
| Existing PR-body lint and applicable local scope/batch-evidence validation | Accidental closing of retained #1822, missing docs declaration, or substituting non-exact evidence for selected batch-only obligations. |

Concrete owning commands include:

```bash
scripts/docs-site.sh check
python3 tests/build/ci_pitfall_ledger_test.py
python3 tests/build/ci_change_scope_test.py
python3 tests/build/ci_pr_body_lint.py --body-file /ABSOLUTE/EXTERNAL/G0-PR-BODY.md
scripts/local-ci.sh --list --pr-body /ABSOLUTE/EXTERNAL/G0-PR-BODY.md
```

The new docs route itself adds no tests that mirror prose. Use the existing
owning validators. Before commit, inspect current non-main branch, exact staged
file list and `git diff --cached --check`; after commit inspect committed files
and final status. Resolve independent review findings before any shipping.

At initial candidate handoff, only source reading and lightweight
Python/link/scope/ledger/diff checks are permitted. Mandatory full Portal is
**not run yet** and remains required before G0 commit. Parent coordinates the
exclusive heavy-resource window and reads all eight actual diffs first. No
commit, push, PR or merge occurs merely because another heavy lane finishes.
This preparation boundary is not a new repository-wide approval requirement.

## Version Management

Version impact: none. G0 changes governance text, two current Portal pages,
this plan and the skill/ledger mechanism only. It changes no active Product,
Module, Host, Provider or Contract identity/schema/Assembly/lock, version tool,
runtime API/ABI or immutable snapshot. It neither allocates a future Build nor
settles the Goal's later version debt. A future identity cut must declare and
verify its actual version closure under the updated canonical policy.

## Documentation impact

Documentation impact: required. Update `/operations/documentation-governance/`
and `/operations/version-and-release/` in this same Task, alongside the three
canonical governance documents and the enforcing skill/ledger. No diagram
architecture changes or Product projections are introduced. The current pages'
source inventory counts are corrected from stale 37/41 to the actual audited 52;
all generated snapshot boundaries remain owned by unchanged tools.
