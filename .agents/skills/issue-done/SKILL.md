---
name: issue-done
description: Universal skill for shipping a completed local task/issue to main - handles verification, Conventional Commit, push, PR creation with governance declarations, current-head review, authorized merge, and safe local worktree/branch cleanup.
---

# Issue Done (Local Issue/Task → Main & Cleanup)

This skill defines the canonical, universal workflow for taking a locally completed GitHub issue/task in an isolated worktree branch, verifying it, creating a Conventional Commit, pushing, opening a Pull Request, checking current-head review and, when authorized, squash-merging into `main`, and cleaning up the branch and worktree.

The current merge procedure retains PR review/conflict/conversation protection,
not retired full-CI or strict-update gates. Automatic incremental activation
requires its own platform evidence; manual controls alone do not prove it.
An unmerged draft does not override current `main` governance or live protection.
This skill grants no new authority: push, PR creation, merge, Issue mutation and
cleanup require the user's applicable authorization; stop at its boundary.

Compatible with: **Antigravity (AGY)**, **Codex / OpenAI**, **Claude Code**, **Kimi**, **Cursor**, **GitHub Copilot**, and human contributors.

---

## 1. Prerequisites & Verification Check

Before starting the shipping pipeline:

1. **Verify Task Branch**: Confirm you are on a short-lived task branch (`feat/<task>`, `fix/<task>`, or `docs/<task>`), **NEVER** on `main`.
   ```bash
   git branch --show-current
   ```
2. **Local Pre-flight & Tests**:
   Run the Task's declared, relevant verification; do not substitute an automatic
   full lane set or an unrelated portal build. For example:
   ```bash
   scripts/local-ci.sh --lanes <task-relevant-lanes>
   # or, for a Task whose verification calls for fast core tests:
   scripts/core.sh test dev fast
   ```
   When the Task is already committed, inspect
   `git diff --diff-filter=A --name-only origin/main...HEAD`. If it adds files,
   run `python3 tests/build/ci_change_scope_test.py` before push even when the
   staged diff is empty. Confirm both path ownership and top-level admission.
3. **Inspect Working Tree**: Ensure there are no uncommitted or untracked changes left behind unintentionally.
   ```bash
   git status --short
   ```
4. **Map acceptance journeys to far-side evidence**: When the Issue, design,
   plan, or acceptance ledger names a multi-step journey, enumerate every leg
   in order before declaring verification complete. For each transition,
   record an observable assertion after the transition, including every named
   crash/retry, failure-to-discard/abort, stop, reload/reopen, and
   persisted-truth leg. Persisted artifacts must be checked by their complete
   required identity (for example digest and byte length, not only media type).
   If a leg was not exercised, keep it as an explicit acceptance gap; a green
   prefix of the journey is not a pass for the full journey.
5. **Apply the minimization principle** before declaring the Task complete
   ([`docs/governance/minimization-principle.md`](../../../docs/governance/minimization-principle.md)):
   - every new or changed test fails for one reason, and that reason names
     the defect;
   - every new required check names the defect it catches, meets the gate
     admission criteria, and fails with `why` and `remedy`; anything that
     cannot is advisory, not required;
   - the diff is one behavior over the Task's declared files, and any
     control-plane path is split into its own Pull Request (§4);
   - no coverage floor, timeout, stress budget, lane selection, or journey
     leg was reduced to make a run green. If one was, the Task is not done;
     restore it and fix the cause.

---

## 2. Pitfall Ledger: Record or Bump

Before committing, decide whether this Task taught the repository something it
could not read off the code. `.agents/pitfalls/` is the shared memory every
agent brand and every human reads; the contract is
[`docs/governance/pitfall-ledger.md`](../../../docs/governance/pitfall-ledger.md).

1. **Decide whether it qualifies**:
   - **In scope**: a process or invariant defect whose root cause is not
     derivable from the product code — release/CI ordering, provenance,
     governance timing, tool-boundary behaviour.
   - **Out of scope**: a product-logic defect whose regression test fully
     expresses the invariant. That test is its exit; do not write an entry.
2. **Dedup before creating** — a near match is another recurrence of an
   existing pitfall, not a sibling file:
   ```bash
   ls .agents/pitfalls/
   grep -rn "<keyword>" .agents/pitfalls/
   ```
3. **Bump or create, in the same commit as the fix**:
   - Existing entry: append one occurrence to `recurrences:` with today's date,
     the Pull Request or commit URL, and `observed_by:` naming the agent or
     model that hit it.

     `observed_by` is **self-reported by the agent writing the entry, at the
     moment it writes**. Never infer it from the commit author, the Pull
     Request author, or the Git identity: concurrent sessions share one
     identity, and a branch can also carry commits made through the GitHub web
     interface, so that metadata cannot say which agent did the work. If you
     cannot state it from your own record of what you did, write `unknown`
     rather than a guess. See
     [`cross-agent-commit-attribution`](../../pitfalls/cross-agent-commit-attribution.md).
   - New entry: copy `.agents/pitfalls/TEMPLATE` to
     `.agents/pitfalls/<id>.md`, where `<id>` matches the filename stem.
4. **Escalate at recurrence 2** — when the bump takes the entry's recurrence
   count to 2 or more, this same Task must either:
   - land an eligible mechanism, record it in `exit` as `skill:<path>` or
     `gate:<test path>`, and set `status: absorbed`; or
   - open an escalation Issue, link it from the entry, and leave the entry
     `open`.

   A mechanism becomes a gate only when all three admission criteria hold: the
   invariant is settled, violation is mechanically decidable, and the check is
   deterministic. Otherwise it exits to a skill section. Any gate you add must
   fail with a message naming both the violated invariant and its remedy.

### Writing a contract test that scans source text

When a contract test asserts a string is **absent** from a file, scan the
directives rather than the raw source. Anything worth forbidding is worth
explaining, the explanation lands in a comment in the same file, and the scan
reads both:

```python
directives = "\n".join(
    line for line in source.splitlines()
    if not line.lstrip().startswith("#")
)
```

Presence assertions can keep reading the raw source; only absence has the blind
spot. Where the banned string is a path the file must also declare, constrain
the declaration rather than loosening the gate. See
[`gate-matches-its-own-prose`](../../pitfalls/gate-matches-its-own-prose.md).

### Pitfalls that bite at this step

Read these before shipping; each is a real recurrence, not a hypothetical:

- [`gate-failure-readability`](../../pitfalls/gate-failure-readability.md) — if
  this Task adds or changes a fail-closed check, its message must carry `why`
  and `remedy`.
- [`coverage-floor-tuning`](../../pitfalls/coverage-floor-tuning.md) — a red
  coverage gate is an instrument reading; raise real coverage, never lower a
  floor to go green.
- [`stress-tier-in-coverage-preset`](../../pitfalls/stress-tier-in-coverage-preset.md)
  — a new busy-spinning `stress` test must be excluded from the `coverage`
  preset in the same commit.
- [`acceptance-journey-truncation`](../../pitfalls/acceptance-journey-truncation.md)
  — map every specified transition to a far-side observable; do not shorten a
  journey to the last state the current implementation already reaches.
- [`synthetic-event-omits-platform-side-effects`](../../pitfalls/synthetic-event-omits-platform-side-effects.md)
  — where a test fires a synthetic event, stubs a device, or forces a state
  transition in place of something the platform does, enumerate the real
  thing's side effects and either reproduce all of them or record the
  unreproduced ones as an explicit gap beside the test. A `blur` dispatched
  into a page that owns an AudioContext is the worked example: the window
  event is the easy half, the context interruption is the half that hides
  defects. When a side effect needs a seam the packaged product must not
  carry, gate it in a component test and name that companion gate in a comment
  on the packaged journey.

---

## 3. Conventional Commit

Commit the changes following repository governance rules:

1. **Stage only declared task files**:
   ```bash
   git add <file1> <file2> ...
   ```
2. **Inspect whitespace & diff**:
   ```bash
   git diff --cached --check
   git diff --cached --stat
   ```
3. **Mandatory new-file ownership preflight after staging**:
   ```bash
   git add <file1> <file2> ...
   git diff --cached --diff-filter=A --name-only
   python3 tests/build/ci_change_scope_test.py
   ```
   Whenever `git diff --cached --diff-filter=A --name-only` lists any path, the
   ownership suite (or an equivalent gate that reads the staged index) is
   mandatory before commit.
   Confirm `test_every_tracked_path_has_explicit_ownership_or_full_rule` passes
   with no `unclassified tracked paths`. Task-specific tests do not substitute
   for this ownership check.

   A check that reads `git ls-files`, the index, or the commit graph is blind to
   an unstaged file, so a green run before `git add` proves nothing about a file
   the Task adds. A new tracked file needs a rule in
   `scripts/ci/scope_policy.json`; check whether an existing prefix rule covers
   the exact filename rather than assuming its directory is covered. See
   [`untracked-file-passes-ownership-gate`](../../pitfalls/untracked-file-passes-ownership-gate.md).

4. **Create Conventional Commit**:
   - Format: `<type>(<scope>): <short description> (fixes #<issue_id>)`
   - Example: `fix(core): handle provider timeout on empty buffer (fixes #142)`
   ```bash
   git commit -m "<type>(<scope>): <description>"
   ```

---

## 4. Push & Create Pull Request

Before any push, classify the final committed Task range:

```bash
git status --short
scripts/local-ci.sh --base-ref origin/main --list --json
```

Run this after the Conventional Commit against the clean final `HEAD`. Confirm
the JSON classifies the complete `origin/main...HEAD` range using the canonical
ownership rule in `scripts/ci/scope_policy.json`.

A changed path is safe to push when it matches `rules`, or when it matches
`full_rules` and the JSON selects `full` with every lane. A full-only path
may retain both an `unclassified path` diagnostic and its named `full rule`
reason; that diagnostic alone is not a push blocker. Stop before pushing
only when a path matches neither `rules` nor `full_rules`.

### Keep control-plane changes reviewable

Path classification remains useful for ownership and selecting local tests; it
does not require a complete CI run, a queue ticket, or chasing a moving main.
Split changes when they are independently reviewable or have a real producer /
consumer dependency, not merely because a control-plane path is present.
Preserve routing coverage when introducing new paths. A routing prerequisite
may land separately when the live baseline needs it; record that dependency
instead of applying a universal split rule.

The historical queue-specific limitation in
[`release-cut-bundles-control-plane`](../../pitfalls/release-cut-bundles-control-plane.md)
does not make ordinary PRs queue-dependent. Product Build allocation
still follows the canonical version policy and is not bundled with unrelated
feature work.

### Related-Issue vocabulary and the closing-directive check

GitHub reads `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`,
`resolves` and `resolved` immediately before an Issue reference as a closing
directive, and its parser has no notion of the sentence around them. "This
Pull Request does not close #466" closes #466 on merge. Four Issues lost their
open state that way; see
[`github-closing-keyword-negation`](../../pitfalls/github-closing-keyword-negation.md).

Choose exactly one form per Issue the Pull Request references:

- **Final delivery** — this Pull Request completes every acceptance item of the
  Issue: `Closes #<issue_id>`. Keep it; nothing here weakens it.
- **Partial delivery** — this Pull Request intentionally delivers only part of
  the Issue and the Issue must stay open: `Relates to #<number>`, the exact
  positive form. `Part of #<number>` and `Refs #<number>` are accepted
  synonyms for an umbrella reference.

Never write a closing keyword in front of an Issue reference in order to deny
it. Do not write "does not close #<number>", "will not fix #<number>", or any
other negated form: state what is still outstanding instead, in a sentence that
contains no closing keyword before a reference. Never pair `Relates to
#<number>` with `Closes #<number>` for the same Issue in one body — the closing
directive wins on merge and the retained relation is prose.

Write the body to a file and check it before `gh pr create`:

```bash
gh pr view <number> --json body -q .body > /tmp/pr-body.md   # or write the file directly
python3 tests/build/ci_pr_body_lint.py --body-file /tmp/pr-body.md
```

The lint is deterministic and fails closed, naming the violated invariant and
the exact safe replacement. Its regression coverage over the four real
recurrences is `tests/build/ci_pr_body_lint_test.py`. Run it again after any
later edit to the body, including an edit made in the GitHub web editor: the
lint reads the text you give it and cannot see a directive added afterwards.

1. **Push branch to origin**:
   ```bash
   BRANCH=$(git branch --show-current)
   git push -u origin "$BRANCH"
   ```

2. **Write and validate the Pull Request body before opening it**:
   Use the repository template and a unique temporary file outside the worktree.
   Record exact Task commands, results, unexercised acceptance legs, version and
   documentation impact, and pitfall disposition. Do not say full verification
   passed when only a local subset ran.
   ```bash
   python3 tests/build/ci_pr_body_lint.py --body-file <body-file>
   scripts/local-ci.sh --declaration-only --pr-body <body-file>
   gh pr create --base main --head "$BRANCH" \
     --title "<Conventional Commit Title>" --body-file <body-file>
   ```
   The declaration-only command executes no lanes. A not-applicable result is
   not a portal pass; run portal checks locally when the Task affects them.
   Validate a changed body again, without closing/reopening the PR merely to
   manufacture an old CI event.

   `Documentation impact` means **Architecture Portal pages**, not any file
   under `docs/`. Declare `required` when this change edits a page under
   `apps/docs-site/docs/`, and list routes on a line reading exactly
   `Affected portal pages:` with each entry starting with `/`. One case admits
   no `none` at all: a Product Build or Assembly change — `products/lmdj/`
   `version.json`, `assembly(.lock).json`, `CMakeLists.txt` or `src/` — must
   declare `required` and update the portal pages and snapshot obligation in
   the same Task, whether or not a portal page is in the diff.
   `check-doc-impact.mjs` enforces this independently of any page edit. Editing
   `docs/quality/`, `docs/governance/`, `docs/prd/`, `docs/design/`, `docs/plans/` or `docs/handoffs/` is
   `Documentation impact: none` with a reason. See
   [`documentation-impact-means-portal-pages`](../../pitfalls/documentation-impact-means-portal-pages.md),
   which repeated seven times because six of those Pull Requests were merged by
   hand while the gate that would have said so was queued or red.

---

## 5. Current-head review and authorized merge

1. **Check live state and authority**. Push and PR permission do not imply merge
   permission. Read the PR's current head SHA, open/draft state, conflicts,
   unresolved review threads and effective protection. Unknown mergeability is
   not proof of no conflict: reread with a bounded wait or report it.
2. **Inspect review evidence for that exact head**. Independent AI review is
   feedback, not a machine verdict granting merge permission. Use the trusted
   review publisher's head/run/attempt evidence and findings, not empty check
   lists, NEUTRAL checks, the model's own completion claim, or old-head reviews.
   Read and address substantive findings; dismissing or resolving a thread
   requires an actual disposition and applicable authority.
3. **Handle review failure visibly**. A missing credential, failed backend,
   timeout, malformed output or stale head is not a clean review. Seek an
   authorized human/agent takeover that actually inspects the current diff and
   records reviewer, exact head, findings/disposition, limitations and reason
   for takeover on the PR. Do not wait forever, forge green evidence or silently
   treat missing review as approval. A new push invalidates old-head evidence.
4. **Merge without the former queue/full-CI loop**. A non-conflicting PR need
   not update just because main advanced. Incremental or explicit full self-test failures,
   in-flight suites, coverage, sanitizer or portal batch results do not block
   an ordinary PR merge; they remain visible evidence and Issue follow-up.
   There is no `merge:queue` ticket or full-green prerequisite. Resolve real
   conflicts locally, rerun affected Task tests and review the changed head.
   If live protection requires retired gates or strict updates, stop and report
   configuration drift; do not bypass it or
   alter protection under shipping authority. Squash-merge only the head just inspected, using an atomic
   expected-head guard where supported, and recheck if it changed.
5. **Verify the result**. Read PR state, `mergedAt` and `mergeCommit`; report
   the actual merged SHA. A successful request or armed auto-merge is not a
   merged PR. Queries that fail or return no evidence must say so.
6. **Check conditional snapshot provenance**. If this Task allocated a Product
   Build or introduced a snapshot, verify provenance against the actual merged
   introducing SHA; retain the source object until that proof is complete.
   A missing squash witness must be generated with the official
   `scripts/docs-site.sh witness PRODUCT_BUILD [INTRODUCING_REVISION]`
   and shipped in a separate commit/PR within applicable authorization; never
   hand-edit frozen metadata. Report the gap until repaired. This obligation
   does not run the full portal for ordinary unrelated Tasks and grants no
   release-operation authority.
7. **Audit retained Issues read-only**. For each `Relates to #<number>`,
   inspect its live state. An unintended closure is a finding; reopening or
   commenting needs applicable Issue-mutation authority. Preserve the closing
   keyword pitfall and record a qualifying recurrence when authorized.

The main-only strategy batches the complete unprocessed commit interval,
using deterministic floor union authenticated review scope and eligible debt.
AI labels cannot shrink that scope; safe docs-none does not clear prior failures
or debt. Daily product tests and daily-missing alerts are retired. Lightweight
health ticks recover pending work without date-based product requests; shipping
a PR never authorizes automatic release.

The report runtime collects authenticated review-infrastructure and selected
batch failures into durable outboxes and stable Issue buckets;
these are not proven root-cause fingerprints, and one green batch does not
close an Issue automatically. Unknown business POST outcomes require an exact
positive receipt or explicit manual reconciliation, never a blind duplicate POST.
Report retries do not execute tests, and processed progress is not full health
or release evidence. Remote O1 acceptance and automatic activation remain separate.
It does not automatically release a version. Release preparation, publication,
deployment and Channel promotion follow their own exact-candidate evidence
and authorization boundaries.

## 6. Local worktree and branch cleanup

Cleanup is a separate authorized action, not a side effect of listing branches
or observing a merged PR. Use `issue-list` for the lifecycle audit when needed.

Before removing an exact worktree/branch, verify the PR is merged, all local
changes are retained on main (including squash equivalence), the worktree is
clean including untracked files, and it is neither locked nor in use by another
session. A merged PR does not prove that later local commits are retained.
Ancestry or `git cherry` alone can be inconclusive after squash.

Use the validated exact path with non-forced `git worktree remove`; run the
command from a different existing worktree without switching another session's
branch. Prefer `git branch -d`. If squash requires `-D`, first prove the whole
patch is retained and that deletion is within the cleanup authorization.
Protect dirty, divergent, ambiguous and active resources; report them instead.
Do not automatically delete remote branches, reset worktrees or run broad
cleanup loops. Report precisely what was removed and what was kept.
