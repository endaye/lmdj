# Recheck the frozen preflight Site before publication

## Scope

Delivery base: `678c911b95ccb9aa30d2d1e26833fa738dba0c47`. Reapply the
independently bounded deployment publication guard from
`a0fdf277bdb72a542ad1992904af954272e8d9e7`, preserving the newer evidence,
dispatch and live-verification prerequisites. Neither Host currently rereads
the preflight pointer after candidate validation and before its public write.

Declared files:

- `scripts/web-runtime-deploy.sh`
- `scripts/creator-web-deploy.sh`
- `apps/web-runtime-host/test/deploy_command_test.py`
- `apps/creator-web/test/deploy_command_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-deploy-prior-publication-guard.md`

Freeze the canonical full Site projection returned by existing preflight.
After immutable candidate HTTP/browser validation, reread Site using the
existing bounded API command (30 seconds), then compare the full projection
before setting publication_attempted. Mismatch or unreadability must not
publish, enter publication recovery, restore prior, or disable another
operator's Site. Preserve post-publication recovery and retain any created
unpublished draft. New refusals give an explicit why and remedy.

This last observation is not an expected-prior atomic write primitive: a
subsequent change may still race publication. Original request-level prior
binding and global same-Site writer coordination remain separate required
work. No real Site, authorization, protection, credential or deployment changes.

## Verification

Use the actual deploy scripts and orchestrators with existing isolated API,
browser, Git and signer fixtures. First reproduce a successful old-script
publication after a competing pointer is installed at draft creation.

Each Host adds five cases: unchanged-pointer read ordering; pointer change;
first-publication concurrent pointer; disabled Site; unreadable Site. Refusals
assert no publish/restore/disable calls and no success/recovery evidence; changed
pointer and disabled state are inspected on the far side. The successful
fixture now requires the sixth authenticated API request, not fewer checks.

Run both complete command populations, including their serial signal recovery
cases, plus both workflow contracts, shell syntax, staged path ownership and
Portal checks. Independently review the full six-file diff. No timeout,
population, assertion strictness, coverage floor or gate is relaxed.

## Version Management

Version impact: none

Reason: internal deployment ordering only; no Product, Assembly or public API.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Document no-recovery refusal, retained drafts and the remaining post-read race
and original-request binding boundaries, without claiming unattended readiness.

## Evidence

Current delivery red on unchanged scripts: the pointer-change case failed on
both Hosts because deployment returned exit 0 rather than refusing. Runtime:
1/1 failed, 9.223 seconds; Creator: 1/1 failed, 8.997 seconds; both test commands
exit 1. Logs: `/tmp/lmdj-prior-publication-delivery-runtime-red-v1.log` and
`/tmp/lmdj-prior-publication-delivery-creator-red-v1.log`.

Original-stack fixture corrections remain historical evidence at the original
commit; do not count their old logs as current verification.

Completed current delivery checks, each exit 0:

- Complete Runtime deploy command: 59/59 discovered and executed, 348.969
  seconds; four shards of 15/14/14/14 plus both serial signal cases.
  `/tmp/lmdj-prior-publication-delivery-runtime-full-v1.log`.
- Complete Creator deploy command: 58/58 discovered and executed, 349.481
  seconds; four shards of 14 plus both serial signal cases.
  `/tmp/lmdj-prior-publication-delivery-creator-full-v1.log`.
- Both complete populations report no failed worker or omitted case. These
  counts already include the five new cases per Host; do not double count.
- `bash -n scripts/web-runtime-deploy.sh scripts/creator-web-deploy.sh`.
- Runtime workflow 16/16, 0.039 seconds; Creator workflow 16/16, 0.033 seconds:
  `/tmp/lmdj-prior-publication-delivery-runtime-workflow-v1.log` and
  `/tmp/lmdj-prior-publication-delivery-creator-workflow-v1.log`.
- Staged path ownership/admission 74/74, 11.385 seconds:
  `/tmp/lmdj-prior-publication-delivery-scope-v1.log`.
- Fresh locked npm ci and Portal check under Node 22.22.2: 144/144 tests and
  47 routes/internal links (`/tmp/lmdj-prior-publication-delivery-deps-v1.log`,
  `/tmp/lmdj-prior-publication-delivery-docs-v1.log`).
- Independent `release_journal_review` inspected the complete six-file diff
  and actual Bash failure/recovery path; clean. It ran shell syntax and diff
  checks, not the concurrently running complete command populations.

The initial workflow invocations incorrectly named nonexistent
`apps/*/test/deploy_workflow_test.py` files and exited 2 without executing
tests. Repository discovery located the actual two `tests/build/*` commands
above; only their executed results are counted.

Pitfall disposition: directly testable deployment ordering invariant, not a
new process-ledger entry. Fixtures do not prove production credentials,
browser acceptance, real deployment or the complete release journey.
