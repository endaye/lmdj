# Bind managed deployment to the original Site snapshot

## Scope

Delivery base: `45385d3b62ac634f4d5997ed827f56665d688973`.
Reapply the bounded Task from `c6d493bc51afaaaa5f6a4b3c289abff714312363`,
retaining the newer ZIP limits, live retention checks and parent guards. Carry a frozen canonical Site digest through
durable dispatch inputs, authentic workflow receipts and the actual Host
preflight. Refuse drift before draft creation; retain the final prepublication
recheck. Legacy manual dispatch without a request ID remains supported.
Managed deployments require the digest; old correlated receipts cannot satisfy
the new closed input contract and need explicit reconciliation, not redispatch.

Declared files:

- tools/release/dispatch_receipt.py
- tools/release/live_host.py
- tools/release/deployment_effect.py
- .github/workflows/deploy-web-runtime-host.yml
- .github/workflows/deploy-creator-web.yml
- scripts/web-runtime-deploy.sh
- scripts/creator-web-deploy.sh
- tests/build/release_dispatch_receipt_test.py
- tests/build/release_dispatch_evidence_test.py
- tests/build/release_managed_dispatch_test.py
- tests/build/release_deployment_effect_test.py
- tests/build/release_live_host_test.py
- tests/build/web_runtime_deploy_workflow_test.py
- tests/build/creator_web_deploy_workflow_test.py
- apps/web-runtime-host/test/deploy_command_test.py
- apps/creator-web/test/deploy_command_test.py
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-deploy-request-prior-binding.md

The digest covers the canonical full Site projection, including an absent or
zero-file prior pointer, not an inferred healthy-prior identity. Read-only
snapshot acquisition checks configured Host/Site identity and two equal reads.
The parent must own and durably bind that snapshot before dispatch; supplied
JSON is not authority. Workflow preflight still proves prior content/browser
health. No atomic Netlify CAS or global Site writer lock is claimed.

## Verification

Actual Host commands with isolated API/Git/browser fixtures: identical frozen
snapshot succeeds; changed prior before invocation, absent prior becoming
published, missing/malformed managed digest refuse before any Site mutation.
Retain legacy manual baseline and both full command populations including
signal recovery. Exercise real receipt CLI/consumer, durable parent dispatch,
recorded/live effect and read-only Site snapshot transport. Check workflow
contracts, staged ownership, Portal and independent current-diff review.

## Version Management

Version impact: none

Reason: release control-plane input binding, no Product/Assembly version change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

No real credentials, signing, CI dispatch, release, deployment or promotion is
executed. Full unattended service composition and real rehearsal remain open.

## Evidence

Original-stack logs remain historical and are not current-head proof. Both
actual-command negative tests first ran against unchanged scripts with a
different well-formed frozen digest and an otherwise healthy Site. Both wrongly
returned success: Runtime 1/1 failed in 9.748 seconds; Creator 1/1 failed in
9.584 seconds, each test command exit 1. Logs:
`/tmp/lmdj-request-prior-delivery-runtime-red-v1.log` and
`/tmp/lmdj-request-prior-delivery-creator-red-v1.log`. Prior smoke did not mask
this missing-binding red.

Initial current receipt 14/14 (0.248 seconds), consumer 34/34 (7.643 seconds),
managed dispatch 20/20 (10.617 seconds), both workflow 16/16 (0.050 / 0.055
seconds), shell syntax and staged ownership 74/74 (10.871 seconds) passed.
Consumer, managed and ownership logs use the
`/tmp/lmdj-request-prior-delivery-` prefix with `consumer-v1.log`,
`managed-v1.log` and `scope-v1.log`. Complete Host and registered integration
results were pending at that checkpoint and are recorded below.

Independent full 18-file static review initially found no functional defect.
A subsequent root diagnostic check found the inherited receipt failure remedy
advised a new dispatch, contradicting this Task's reconciliation-only handling
of old receipts. The independent reviewer confirmed the finding. A direct
exception-output regression failed on that advice (1/1, 0.000 seconds, exit 1).
The corrected message preserves every validator condition and explicitly
forbids redispatch to repair missing or invalid evidence. The new regression
is added to, not substituted for, the original receipt population.

Final complete Host command populations passed, each exit 0:

- Runtime 67/67 discovered and executed, 382.892 seconds: four shards of
  17/16/16/16 plus both serial signal cases.
  `/tmp/lmdj-request-prior-delivery-runtime-full-v1.log`.
- Creator 66/66 discovered and executed, 384.565 seconds: four shards of 16
  plus both serial signal cases.
  `/tmp/lmdj-request-prior-delivery-creator-full-v1.log`.

No failed worker or missing case; each count includes its eight new cases.
Final receipt suite passed 15/15, 0.312 seconds, exit 0
(`/tmp/lmdj-request-prior-delivery-receipt-v2.log`). The independent reviewer
also reran the diagnostic case 1/1 and confirmed the correction without
rerunning heavy suites.

Final registered CTest verification passed 6/6, exit 0, total 157.81 seconds:

- live Host 42/42, including both actual freezer-to-command bridges (62.02s);
- deployment effect 48/48, retaining the new bounded-ZIP regressions (73.25s);
- managed dispatch 20/20 (10.20s), durable dispatch 19/19 (4.56s);
- dispatch consumer 34/34 (7.37s), receipt 15/15 (0.36s).

No failed or skipped population. Existing per-suite budgets were unchanged.
Evidence: `/tmp/lmdj-request-prior-delivery-ctest-v1.log` and
`build/core/dev/Testing/Temporary/LastTest.log`; configuration selected Python
3.14.7 (`/tmp/lmdj-request-prior-delivery-configure-v1.log`).

Fresh locked npm ci under Node 22.22.2 and both Portal checks passed, each
144/144 tests plus 47 routes/internal links. The final v2 rerun covers the
clarification that prior freezing's parent composition is still missing.
Logs: `/tmp/lmdj-request-prior-delivery-deps-v1.log`,
`/tmp/lmdj-request-prior-delivery-docs-v1.log`,
`/tmp/lmdj-request-prior-delivery-docs-v2.log`.
The parent service and real release journey remain incomplete.

Pitfall disposition: directly testable control-plane binding invariant; no new
process-only ledger entry. No production, public TLS, browser, signer or full
release acceptance is claimed by these fixtures.
