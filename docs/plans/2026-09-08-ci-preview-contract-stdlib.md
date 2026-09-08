# Preview workflow contracts without ambient Python dependencies

## Task and declared files

One test-only Task, one Conventional Commit:

- `tests/build/ci_cloudflare_preview_workflow_test.py`
- `docs/plans/2026-09-08-ci-preview-contract-stdlib.md`

No workflow, permissions, product code, deployment, or release state changes.
The existing `ci_self_test_report_workflow_test` block/field/scalar helpers
remain unchanged; this Task introduces no YAML library or general YAML parser.

## Defect and implementation

The preview contract test added an undeclared PyYAML import. The `ci_contract`
lane does not install that package. An ambient system package concealed the
defect locally: at base `75e1484f34f3d3da024a6cad12eb259056dc2de1`,
`python3 -S tests/build/ci_cloudflare_preview_workflow_test.py` failed before
running tests with `ModuleNotFoundError: No module named 'yaml'`.

Use the existing structured, exact-indentation workflow helpers and a bounded
step-list splitter. Reject duplicate keys and non-explicit security mappings.
These contracts intentionally require the repository's explicit YAML layout;
unsupported formatting fails rather than being silently treated as safe.
Comment-only prose is not a security directive.

Retain all six original contracts:

1. Build accepts only PR events with the exact opt-in branch/repository guards.
2. Untrusted build uses the hosted runner, read-only permissions, no protected
   environment, and no deployment secret.
3. Both checkouts disable persisted credentials; source checkout is exact PR SHA.
4. Upload identity binds PR SHA and run attempt, with required ZIP/error policy.
5. Publisher accepts only workflow completion and checks out trusted workflow SHA.
6. Deployment secret enters only the trusted publish step, never tool install;
   protected environment and non-cancelling concurrency remain required.

Mutation regressions exercise the same real contract methods with a wrong write
permission, wrong checkout ref, and secret injected into tool installation.
A current-diff review found that ignoring unsupported mapping keys could miss
a quoted job `environment` and an inline secret map on another step. Both
mutations first reproduced escaping the original replacement (zero failures
instead of one), then passed after direct keys became fail-closed and every
step environment used explicit scalar-mapping validation. Quoted/merge keys
and nonempty inline mapping prefixes are rejected, not silently ignored.
A subprocess runs all six original contracts under `python -I -S`; a missing
ambient dependency cannot again be masked by local site-packages. This adds no
required workflow check and does not reduce an existing security assertion.

## Verification and review

- Baseline isolation command: failed at the undeclared `yaml` import as above.
- Updated isolation suite: 12 tests passed, including all six original contracts,
  five rejected mutations, and the isolated six-contract subprocess.
- Actionlint 1.7.12 with explicit ShellCheck 0.9.0 passed. The only ignored
  diagnostic is `unexpected key "queue" for "concurrency" section`.
- Staged ownership: 66 tests passed. Staged whitespace/docs-static check passed.
- Declaration-only preflight selected `ci_contract` and `docs_static`; the
  portal declaration check was not applicable, not a portal acceptance pass.
- Full CI contracts with `LMDJ_ACTIONLINT` explicitly set: 1,795 tests,
  exactly one pre-existing pitfall-ledger
  failure (retired `apps/architecture-portal/test/changed-files.test.mjs` path),
  no skips. That unrelated defect is repaired separately in PR #943; this Task
  neither bundles its repair nor treats a failed complete suite as green.
  An earlier invocation without that variable also skipped the existing
  Actionlint-dependent parser test; the explicit invocation removed that skip.
- Root's independent `python3 -I -S` run passed all 12 tests. Current-diff
  review confirmed both syntax findings resolved with no remaining code finding.
- Local tests are not a hosted rerun or deployment acceptance result. No remote
  rerun, publish, dispatch, permission change, or product repair is authorized by
  this Task.

Pitfall review: `optional-linter-dependency-silently-absent` motivates explicitly
including ShellCheck in lint verification; `gate-matches-its-own-prose` requires
comment-only lines not to satisfy or violate directive scans. This Python
dependency defect is caught directly by the new isolated subprocess regression;
no separate pitfall-ledger file is added to this two-file Task.

## Version Management

Version impact: none — test dependency isolation does not change product,
module, host, provider, contract, or release identity.

## Documentation Impact

Documentation impact: none — only test implementation and this evidence plan
change; no current portal page, diagram, product identity, or documented
workflow behavior changes.
