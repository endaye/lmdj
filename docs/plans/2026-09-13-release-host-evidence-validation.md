# Reuse Host deployment evidence validation without mutation

Status: delivery integration of original `15cb865d`, based on local passive-Git
Task `758d1bca`. Source/test files match the original prerequisite before import.

## Scope

Declared files:

- `apps/web-runtime-host/tools/deploy_orchestrator.py`
- `apps/creator-web/tools/deploy_orchestrator.py`
- `apps/web-runtime-host/test/deploy_orchestrator_test.py`
- `apps/creator-web/test/deploy_orchestrator_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-host-evidence-validation.md`

Expose each existing evidence writer's exact schema validation as a pure function
and read-only CLI. The writer must use that same validator. This is the required
interface for later deployment-effect integration, not the integrated effect.
It validates internal consistency, not authentic origin or current Site state.

## Verification

Run both real orchestrator suites. Success and recovery fixtures pass function
and actual CLI subprocess; CLI bytes equal writer bytes and no file appears in
an empty working directory. Mutate production URL, published deploy ID, Site,
immutable index, browser Build, prior deploy ID and prior manifest separately;
both entrypoints must refuse without success output or evidence files. Run
related workflow and isolated command suites, staged ownership, Portal, and an
independent complete six-file review. No real release or deployment is executed.

The unchanged-source API-availability regression failed with two AttributeError
subcases (one test, 0.000s, exit 1); this does not claim an existing schema bypass.
Original-stack results do not prove this delivery tree.

Current actual orchestrator suites passed Runtime 20/20 (1.005s), Creator 20/20
(5.246s); workflow contracts passed 16/16 each (0.033s/0.032s), all exit 0.
Independent complete six-file review found no actionable finding and reran
both orchestrator suites 20/20 (0.779s/0.811s). The actual isolated Runtime
command suite discovered and executed 54/54, including two serial signal tests,
in 196.564s, exit 0; `/tmp/lmdj-host-evidence-runtime-command-v1.log`.
Creator command-suite verification also completed: 53/53 discovered/executed,
including its separate serial signal phase, exit 0. Output is retained at
`/tmp/lmdj-host-evidence-creator-command-v1.log`.

Staged ownership passed 74/74 (6.186s). Locked npm ci and Portal check under
Node 22.22.2 exited 0, including 144 tests and 47 routes/internal links. Logs:
`/tmp/lmdj-host-evidence-delivery-scope-v1.log` and
`/tmp/lmdj-host-evidence-delivery-docs-v1.log`. No actual deployment occurred.

## Version Management

Version impact: none

Reason: internal deployment tooling only; no Host API, manifest, Product Build
or Assembly identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document passive schema verification and its authentication boundary.

## Acceptance boundaries

Run/artifact authentication, frozen candidate/Site binding, live HTTP/browser
verification, production driver composition and full request-to-promotion
acceptance remain required. Schema consistency is not deployment acceptance.
Pitfall disposition: executable interface behavior, no process-ledger entry.
