# Creator developer diagnostics (#1514)

One Task adds a developer-only diagnostic surface without changing error
production, transport, recovery, or existing alert semantics.

Declared files: `apps/creator-web/src/app.tsx`,
`apps/creator-web/src/components/diagnostics_log.tsx`,
`apps/creator-web/src/styles.css`,
`apps/creator-web/test/diagnostics_log.test.tsx`,
`apps/creator-web/test/workspace_shell.test.tsx`,
`apps/docs-site/docs/hosts/creator-web.mdx`, and this plan.

Workspace owns an append-only in-memory tail of 100 records. Each record snapshots
UTC timestamp, a static operation/intent label, code, message and JSON details.
Only the error envelope is copied: no stack, request or additional Project data.
The surface is reachable in every mode; mode navigation does not reset it.
Existing shell error-code presentation sites share the same recorder, starting
with Sequence recovery and transport. No persistent storage or report upload.
Final end-user visibility remains deferred.

Verification: Creator Vitest record shape/privacy, mutation snapshot, fallback,
and 100-record retention tests; Workspace recovery refusal → full visible record
→ mode navigation → retained record with existing alert intact. Run the full
Creator unit suite and TypeScript check, `scripts/docs-site.sh check`, and staged
new-file ownership via `python3 tests/build/ci_change_scope_test.py`. No new e2e
journey or gate; this does not claim physical/browser acceptance.

## Version Management

Version impact: none — integration-only Creator presentation change, no public
Host API, Contract, Module, Provider, manifest or Product Build identity change.
No release or independently published Host package is allocated by this Task.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Describe the diagnostic surface, retention, session lifetime and developer scope.

## Pitfall Impact

Pitfall impact: none — loss of the error envelope is product presentation logic,
covered directly by unit regression tests.
