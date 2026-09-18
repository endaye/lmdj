---
name: lmdj-review-ci-triage
description: Use when an LMDJ PR review or CI job fails on GitHub.
---

# LMDJ PR Review / CI failure triage

Before rerunning a failed `PR Review` or `CI contract` job, read the failed job's own log and
classify the cause. Each class has a different remedy; rerunning the wrong way wastes 15+
minutes or masks a real defect.

Read logs per JOB, not per run: `gh run view <id> --json jobs` for job ids and conclusions,
then `gh api repos/<owner>/<repo>/actions/jobs/<job_id>/logs`. `gh run view <id> --log-failed`
can come back completely empty; an empty result is not "no failure detail", it means you asked
the wrong way.

## Which run carries the suite

The lane suite is invoked as a reusable workflow, so its jobs ride under `Self-test Report` /
`Incremental Completion` run names rather than only `Core CI` — `gh run list --workflow=ci.yml`
can look weeks stale while batches keep running it. Lane selection also leaves jobs `skipped`
on `main`, so "no recent failures for this lane" is not evidence the lane is green; check for a
run that actually executed the job before drawing any conclusion. And a job that fails inside
its test-running step exits before its post-test assertions: never cite those later checks as
passing for that run.

## Read the failure artifact before theorizing

The job log names only the downstream symptom (`why: no model reviewed this head`). The cause is
in the review artifact: `gh run download <run> -n pr-review-result-<head>-<run>-<attempt>` gives
`failure.json` (`status`, `error_class`), `t2-result.json` (`attempts[0].status`, `error_class`,
`error`, `usage`) and `t2-config-witness.json` (the engine identity the run actually used).
Classify from those. A non-zero `usage.num_ai_calls` disproves every "no backend / broken
install" class at once — the model was called and its output was rejected, which is a contract
question, not a host question. The installed adapter is the authority for that contract, not the
PR branch: `pr-review.yml` checks out `base.sha` scripts and runs the host-installed engine, so a
branch behind `main` keeps replaying old pipeline scripts no matter what it contains.

## Self-test bucket Issues (`self-test:*` labels)

A `self-test: <suite> test failure` Issue is filed from an authenticated batch journal, one
bucket per suite, and its observations are historical: the bucket stays open while the suite
is red, whether or not the lane has run since. Triage the *lane*, not the observation list.

1. Map suite to job: `gh run view <id> --json name,jobs --jq '.jobs[] | "\(.databaseId) \(.name) \(.conclusion)"'`
   on the run named in the newest observation, then read that job's own log
   (`gh api repos/<owner>/<repo>/actions/jobs/<job_id>/logs`). The failing CTest line names the
   test and assertion, and the run's `Label Time Summary` names the tier it lives in.
2. Check whether the lane has run at all since the last observation. Batch lanes are
   `skipped` whenever the incremental controller fails, so a week-old bucket can mean the
   suite never executed — not that it passed. `gh api
   repos/<owner>/<repo>/actions/runs/<id>/jobs --jq '.jobs[].name'` shows skipped lanes.
3. Reproduce the lane locally before theorising: `scripts/core.sh package` for the `package`
   suite, `scripts/core.sh test dev full` for `core_ubuntu`. It refuses to package a modified
   working tree, so commit first, then run it for a full PASS (ctest tiers + archive +
   detached `.sha256`).

Two lane facts that make a red look impossible to explain:

- `package` runs **only** in self-test/batch mode, never on a Pull Request. A defect that
  survives every PR lane (a Release-preset-only build error, for example:
  `CMAKE_BUILD_TYPE=Release` defines `NDEBUG`, so a test whose checks are `assert()` compiles
  them away and its assertion-only locals then fail `-Werror,-Wunused-variable`) is invisible
  until a batch runs that lane. `scripts/local-ci.sh --base-ref origin/main --list` shows
  whether the lane is even selected for a given diff — a suite absent from that list is not a
  suite your PR proved.
- A `package`/`core_ubuntu`-style red can be a *duplicate* of a fact another tier owns. Grep
  the failing assertion before fixing it: a hand-copied identity pin in a component-tier test
  fails the lane that does not own the fact, and files an extra bucket beside the one the
  owning tier already has. Deleting the duplicate beats re-binding it.

## Classification → remedy

| Log signature | Cause | Remedy |
| --- | --- | --- |
| `403 primary-rate-limit remaining=0` | GitHub API quota | Rerun once after the reset window (`reset=` epoch in the log). |
| `connection reset by peer`, transient socket errors | Network blip | Rerun once. |
| `changed Git inventory exceeds the file limit` / `MAX_FILES` | Diff > 50 files (`pr_agent_review.py MAX_FILES = 50`) | Never rerun. Split the branch or get a manual merge. |
| `Artifact not found for name: ...-attempt-N` after a failed-job-only rerun | Artifact names embed the attempt number; a failed-job rerun is a NEW attempt and cannot see the model step's artifact from the old attempt | Rerun ALL jobs: `gh run rerun <id>` WITHOUT `--failed`, so the model step re-executes in the same attempt. |
| `failure.json` shows `error_class: invalid_output` with a `why:` naming the repair verdict ("new findings require human review before automatic resolution", "repair verdict is missing or malformed", "repair verdict inventory differs from requests") | The installed host overlay is older than merged `main`. The engine's own verdict validation voids the WHOLE head review, so a stale adapter costs a fully validated review (`#1347` narrowed it to the rechecks; `#1346` reports refusals per finding). The `settings/.secrets.toml` WARNING under a `releases/cutover.*` path is benign noise — green runs print it too, it is NOT an install-breakage signature. | Not a diff defect and not rerunnable. Download the review artifact, read `failure.json` / `t2-result.json`, confirm the run's `t2-config-witness.json` adapter hash differs from `main`, then reinstall the overlay from current `main`: stage root-owned 0700 `pr_agent_review.py`, `runtime.toml`, `run-engine.sh` and `sudo -n bash STAGE/install.sh STAGE`. Verify `current` switched, `previous` retained, the ledger hash unchanged, then prove it with a real review (the manual dispatch entry) rather than trusting the witness alone. |
| `run-engine.sh` itself prints `why: no PR-Agent release is installed at .../current` or `release is incomplete` within seconds | Genuinely missing or half-finished install | Not rerunnable. Ask the owner to run `scripts/ci/pr-agent/install.sh` on the review host. |
| `CI contract` fails with `subprocess.TimeoutExpired: ... --integration-child ... timed out after 120 seconds` | Runner contention, not the host and not the diff. The instrument is right; that host was ~5x slow. | Compare the same job's own `Ran N tests in Xs` line: green ≈ 185s, red ≈ 900s+. Rerun. Never widen the 120s timeout — thresholds are instruments, not targets. |
| `why: all configured review backends are unavailable` + `error_class: budget_exhausted`, `num_ai_calls: 0` in `t2-result.json` | Every enabled review-host provider is out of budget (2026-09-17: kimi disabled earlier, deepseek was the last one enabled and its budget ran out). Not a diff defect; rerunning cannot fix it. | Owner-side: restore a provider budget on the review host, or record an authorized current-head owner review/waiver per `issue-done` §5.3, then merge with the expected-head guard. Classify by downloading `pr-review-result-<head>-<run>-<attempt>` and reading `failure.json` / `t2-result.json` / `t2-config-witness.json` (witness `providers` shows which backends are enabled). |
| `no model reviewed this head (status=not-reviewed)` | Downstream of any of the above model-step failures | Fix the upstream class first; then rerun. |

## Proving "not my diff"

Stash the working changes (`git stash -u`), rerun the failing test or wait for a clean-main
run, compare, then `git stash pop`. A red test that fails identically on clean main encodes a
superseded contract from a freshly merged stack — update the test to the new contract in your
Task instead of 'fixing' it backward.

## Review findings

Bot review findings on a pushed head are usually legitimate (unbound decoded values,
unused imports, wrong failure-mode expectations). Fix them in a follow-up commit on the same
branch; rerun only the affected local tests.

When the finding targets a budget-ledger accounting rule, read every path that writes the
record before conceding or fixing: a settlement/refund rule keyed on record STATUS alone
silently covers paths where provider-side over-consumption was observed and flagged
(`envelope_breach`), releasing budget against spend that really happened. Key the refund on
the observation flag, not the status, and pin the carve-out with an admission on a DIFFERENT
provider envelope so the denial comes from the still-committed reservation, not the envelope
hold (the hold only fences the same provider/model/price envelope).

## Red proofs must hinge on the changed rule

When acceptance demands a deterministic test that is red before the fix, compute what the OLD
code does with the fixture before trusting a green run: records that already settle to their
actual (reconciled) behave identically under both accountings, so the discriminating record
must be the one the rule changes — put a dead (`uncertain`) reservation in the committed basis
before the far-side admission. Stash only the fix and rerun the named tests; a suite green
under both rules proves nothing. For budget fixtures, reservation = context×input_price +
output_cap×output_price (+ fixed charge): pick caps so the denial leg, the recovery leg, and
any still-denied leg each have headroom, and verify the arithmetic by hand first — a cap two
reservations cannot fit fails the fixture, not the rule.

## Resolving review threads: repair, never hand-resolve

A bot finding is a live defect claim, so hand-resolving it to unblock merge defeats the gate it
runs on. The path that both clears the thread and satisfies `required_conversation_resolution`:
fix the defect on the branch, push, and the `synchronize` review automatically repair-rechecks
the original finding against the new head — a `resolved` verdict resolves the thread for you and
publishes the evidence reply. Do not push a partial fix: the recheck reads the current source and
returns `unresolved` with the exact lines that still contradict the claim, which tells you what
remains. Hand-resolve ONLY findings that are genuinely wrong or superseded (e.g. the reported
trigger no longer exists at the current head), and say why in the resolve comment.

## Auto-merge and docs-only lanes

Auto-merge is opt-in per PR — `gh pr merge --auto --squash`. Nothing merges by itself even with
all checks green; `mergeStateStatus: BLOCKED` with zero required approvals usually just means
nobody enabled it yet. Attempting it on an already-merged PR errors with "already merged" —
check `state` first.

The Documentation-impact gate cross-checks the PR body against the actual changed-file list in
both directions: `required` demands the listed portal page really changed in the diff; `none`
fails if any `apps/docs-site/docs/**.mdx` changed. Editing the body after the fact does nothing
— the check reads the event payload, so re-trigger with close/reopen or a new push. A small
evidence-only PR (witness, ledger provenance file) should declare `none` with a Reason line,
not `required` with pages it does not touch. The declaration must be a BARE line —
`Documentation impact: none` with nothing else on it, justification on its own `Reason:`
line; prose, bold, or a trailing period on the same line defeats the parser and fails
`scripts/local-ci.sh --declaration-only --pr-body`. Run that plus
`python3 tests/build/ci_pr_body_lint.py --body-file` before `gh pr create`.

## RealHandlerIntegrationTests red on every PR = stale host overlay

`RealHandlerIntegrationTests` runs only on the review host (skip-locally; needs
`PR_AGENT_RUN_INTEGRATION=1` plus the installed bundle) and tests the INSTALLED engine, not the
branch. When a merged `pr_agent_review.py` change reaches `main` but the host overlay is not
reinstalled, every PR's `CI contract` fails inside that suite with assertion mismatches against
the old engine — regardless of the PR's contents. Diagnose by comparing the overlay install
timestamp (operations doc's install log) against the merge time of the last `pr_agent_review.py`
commit on main. Remedy: reinstall the overlay from current `main`, and record the missed
reinstall as a pitfall in the operations doc — the budget section already carries this
precondition; it applies to ANY adapter change, not just budget changes.

## Model-variance invalid_output: rerun before diagnosing

`not-reviewed` with `invalid_output` (e.g. `native finding locations are duplicated`,
`native finding anchor is not a changed RIGHT-side line`, `native PR-Agent output is malformed
line=.. bytes=..`) plus `num_ai_calls: 1` means the model ran and its YAML variant was rejected
by the strict duplicate/anchor validation. When fresh attempts of the same head show DIFFERENT
malformed-output details each time, it is model variance — a whole-run rerun (`gh run rerun <id>`,
no `--failed`) is the designed recovery and usually passes within a few attempts (observed:
pass on attempt 7 after 6 rejected variants). Escalate to an engine-strictness issue only when
the identical detail repeats across 3+ fresh attempts. `t2-config-witness.json` tells you which
provider/engine actually ran.

## Transient review-lane failure: retry before diagnosing

A Review fallback failure whose only log signature is "why: review pipeline operation failed"
with no model call, no invalid_output, and no host error is usually transient host jitter. Push
(or close/reopen) to get a fresh run before downloading artifacts or reinstalling anything —
the next run re-reviews the same head and normally goes green. Diagnose only when the same
signature repeats on a fresh head.

## Unrelated red tests: prove pre-existence before absorbing

Before absorbing a red test into your Task, run the SAME suite in a clean checkout of `origin/main`
(`git worktree add /tmp/main-check origin/main` in the REPO worktree, never inside a stack worktree
— a stack worktree carries another branch's WIP and a `git stash pop` there lands on the wrong
branch). Identical failure on clean main = pre-existing/environmental; note it and move on. A red
test that fails identically on clean main encodes a superseded contract or an environment gap, not
your regression. And never `git stash pop` inside a shared worktree whose branch you do not own —
stashes are repo-global and will land on whatever HEAD is checked out there.

## Polling

`gh pr checks --watch` effectively caps around 10 minutes. For longer runs, poll
`gh run view <id> --json status,conclusion` on an interval instead.
