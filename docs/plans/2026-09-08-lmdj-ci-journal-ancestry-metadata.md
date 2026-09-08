# Read only ancestry metadata when authenticating journal writers

## Task and declared files

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- `docs/plans/2026-09-08-lmdj-ci-journal-ancestry-metadata.md`

Change only the writer's compare GET to `?per_page=1&page=2`. Preserve the
existing status, base-commit and merge-base checks and all other authentication,
cache and failure boundaries. This response is not a commit/path inventory and
must never replace scope collection or first-parent enumeration.

GitHub's [compare API documentation](https://docs.github.com/en/rest/commits/commits#compare-two-commits)
states that changed files appear only on the first page. Independent GET-only
evidence is retained in `/tmp/lmdj-ancestry-compare-pages.zP1AdM`: the ordinary
and second-page responses have equal complete status/base_commit/merge_base_commit
fields for [020774 to e981](https://github.com/endaye/lmdj/compare/020774746c27bcd55fb488eb42276d9e3dcb04ba...e981b01da7973960fa0849d53457f0137c9ea3f7)
and [4eb6 to e981](https://github.com/endaye/lmdj/compare/4eb6a13958543af377437658ad6ba788ec279880...e981b01da7973960fa0849d53457f0137c9ea3f7); observed payload bytes were
330935 versus 21558 and 502309 versus 13686 respectively. One-commit ahead has
empty second-page commits but valid identity metadata; behind remains rejected.
These are individual payload observations, not a stable latency or capacity ratio.

## Verification

Baseline: 45 journal tests pass. First add an exact-path regression which fails
against the old GET. Verify ahead and identical (including empty commits),
behind/diverged/unknown/missing status, missing or mismatched ancestry identities,
and a failed GET followed by fresh authentication without cache poisoning or
writes. Run the focused suite, all CI contracts with explicit actionlint 1.7.12
and ShellCheck 0.9.0, staged ownership, and docs_static. Local fixtures and read
payload checks do not prove O2 or end-to-end scheduling capacity.

Completed local verification on base `e981b01da7973960fa0849d53457f0137c9ea3f7`:

- `python3 tests/build/ci_batch_github_journal_test.py`: 49 passed,
  `/tmp/lmdj-ancestry-target.log`; original exact-path regression failed before
  the production edit (`/tmp/lmdj-ancestry-red.log`, baseline 45 passed).
- `PATH=/tmp/lmdj-shellcheck-lint.cxa20X/extracted/usr/bin:$PATH LMDJ_ACTIONLINT=/tmp/lmdj-t2-shipping.MTX7q1/actionlint python3 -m unittest discover -s tests/build -p 'ci_*test.py'`:
  1764 passed in 40.747 seconds, zero skips, `/tmp/lmdj-ancestry-ci.log`.
  Executables are actionlint 1.7.12 and ShellCheck 0.9.0.
- After staging all three declared files,
  `python3 tests/build/ci_change_scope_test.py`: 66 passed,
  `/tmp/lmdj-ancestry-ownership.log`; `git diff --cached --check` passed.
- `scripts/local-ci.sh --base-ref origin/main --lanes docs_static --no-cache --json`:
  docs_static passed without cache, `/tmp/lmdj-ancestry-docs.json`.

Current schedule and callback runs also show a generic failure before their
source witness, with root cause still unknown. This payload optimization does
not claim to repair that failure or prove live callback recovery.

## Version Management

Version impact: none — internal metadata retrieval changes no Product, Module,
Contract, Assembly, snapshot or release identity.

## Documentation Impact

Documentation impact: none — the internal GET changes no operator workflow,
test scope, identity policy, Portal page, diagram or projected source fact.
No Portal build is required or claimed.

## Pitfall disposition

Pitfall impact: none — this is a bounded retrieval optimization using documented
API semantics, not a new failure of an existing process invariant. All eleven
open ci-release entries were read. Exact-path fixtures and real response checks
preserve API fidelity; explicit tools preserve lint coverage. No latency ratio,
new gate, retry, permission or cache bypass is introduced.
