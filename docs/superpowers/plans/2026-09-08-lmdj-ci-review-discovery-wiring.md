# Manual PR Review discovery entry

## Task and declared files

Add `report-discovery` to the existing short-lock report step. This isolated
Task owns only `.github/workflows/self-test-report.yml`,
`tests/build/ci_review_discovery_workflow_test.py`,
`tests/build/ci_batch_runtime_workflow_test.py`, and this plan. Its branch is
`feat/ci-review-discovery-wiring`. Shipping depends on the actual discovery
runtime and fixed shared-storage loader being merged; source is not copied
from another worktree to manufacture integration success. Before final testing,
the branch safely fast-forwarded to merged dependency revision
`6d50bf922f143d2d4a4f134cc2d3f368b269b0aa`, preserving its own four-file change.

## Interface and safety

The existing manual controller requires main and first attempt. The new closed
branch calls `review_discovery_runtime.py --root PATH --summary PATH --limit N`,
optionally with paired `--run-id` and `--attempt`. These use the existing
`report_limit`, `review_run_id`, and `review_attempt` inputs. It rejects supplied
report/journal configuration, batch/probe requests and legacy reporter inputs.
Fixed storage is resolved by the authenticated runtime, not caller paths.

The branch exits after the one CLI invocation, including nonzero/incomplete
results. It cannot fall through to the legacy report mapping. It produces no
scheduler action/request/executor output or controller artifact, and does not
run a product test. Existing `report-*` exclusions and the same writer lock
continue to apply. No job, permission, source-registry path, automatic trigger,
initialization protocol or long-held product lock is added.

Initialization of the fixed discovery journal remains a separate authorized
use of the existing initializer. Discovery only queues authenticated reports;
business delivery/recovery remains a separate outbox operation. Actual remote
historical scanning, queueing and draining are not certified by local tests.

## Verification

Execute actual inline workflow Python with strict subprocess assertions. Cover
bounded scan, paired exact-attempt input, malformed/mixed inputs before CLI,
nonzero/incomplete status preservation, no fallthrough and no execution output.
After dependencies land, drive the actual CLI parser/summary boundary with its
runtime port injected. Run existing report workflow contracts, CI discovery,
actionlint, staged ownership and final nonempty docs_static. Portal check must
report missing dependencies honestly, not claim unexecuted stages passed.

## Version Management

Version impact: none
Reason: internal manual CI reporting entry; no product version allocation.

## Documentation Impact

Documentation impact: none
Reason: inactive automatic discovery and isolated manual acceptance tooling;
current product/Portal routes and automatic trigger policy remain unchanged.

Pitfall impact: none — retain exact CLI and actual-platform boundaries; local
command wiring cannot prove remote discovery/delivery or automatic cutover.

## Results

The actual CLI integration test initially failed because its runtime was not
yet on main. After the real dependencies merged, all five new workflow tests
passed, including the actual CLI parser, summary and incomplete exit behavior.
The 19 existing runtime workflow tests passed. Staged ownership passed 66 tests;
actionlint 1.7.12 passed with only the existing unsupported concurrency `queue`
key exemption. Portal check ran 57 tests: 54 passed, three failed due to missing
`glob`, `gray-matter` and `cheerio`; subsequent Portal stages did not run.

Complete CI Python discovery passed 1,641 tests with no skips. The final
nonempty committed range is classified and docs_static verified before shipping.
No remote exercise, initialization, release, deployment or cleanup is part of
this Task; local command-boundary tests do not claim discovery/delivery O1.
