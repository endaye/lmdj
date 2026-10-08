# Validate triage evidence before accepting a premise

## Task and declared files

Deliver #980's missing skill mechanism. At base
`1b8691b652afa8d9cd5501394b7cf9c038b8ed2c`, the Issue is open, the pitfall has
three recorded recurrences and `exit: none`, and `issue-list` moves from inventory
to classification without checking the report's factual premises.

- `.agents/skills/issue-list/SKILL.md`
- `.agents/pitfalls/blind-search-reads-as-absence.md`
- `docs/plans/2026-10-08-triage-evidence-validation.md`

No product, Creator, release, version, CI control-plane or other concurrent Task
files change. #983's possible ledger consolidation remains a separate decision.

## Mechanism

Place evidence validation before classification and workstream assignment.
Bind every premise to its inspected revision. Check each reported Host operation
through its actual dispatch, handler, accepted payload and state/result path;
include alternative/nested `exact_keys`, sidecar/value constraints and filesystem
mapping where relevant. Handle generated/table registrations rather than using
one textual dispatch spelling as an existence oracle.

An absence requires both a known-present control that the same instrument can
detect and a bounded inspection of all authoritative implementation sites for
the claim. Preserve aliases, generated chains, tables and positional wiring.
Record verified, contradicted and unverified claims separately; missing coverage
requests concrete evidence instead of producing a Ready Machine defect Task.
The completion criterion covers every named operation and asserted absence.

Absorb the pitfall into this skill, preserve all three historical recurrence
records and related-entry links, and add no occurrence for administrative
absorption. No generic CI gate or mirror text test is added: prose acceptance
and search coverage require review judgment.

## Walkthrough and review

Use current source at the base revision to check the mechanism independently:

| Reported premise | Discriminating inspection and disposition |
| --- | --- |
| `project.import.chunk` succeeds | Inspect complete Host dispatch, with known-present begin/index/entry/commit handlers as controls. Chunk is absent from that bounded surface; index/entry carry real chunked payloads. Record the report mismatch. |
| `project.inspect` addresses a Project ID | Its actual handler requires `exact_keys(payload, {})`, a retained session and no sidecar. Contrast `project.open`'s project/pattern ID key sets. Reject the ID-addressed inspect premise. |
| Creator lacks Project Bundle import UI | Follow `app.tsx`'s `onImport` callback through `importProject` to `importProjectJourney` in `runtime/project_actions.ts`. This positive wiring refutes the absence despite a mismatched name grep. |
| Host omits Sound Set limits because a member grep finds no assignment | Map the trailing `ApplicationConfig` field to `soundset_limits`; follow generated identity, CMake resource-limit extraction and compile defines into that initializer. Positional wiring proves presence. |

These are source/mechanism walkthroughs, not execution of a historical packaged
Host/browser journey, new product regression tests or proof about all deployments.
An independent reviewer checks the complete three-file diff and these mappings.

## Verification

Run existing pitfall-ledger tests for the absorbed skill exit and recurrence
contract. Compare recurrence frontmatter with the base byte for byte. Stage all
three files before the existing change-scope tests so new-plan ownership is
visible. Inspect the staged diff and whitespace, then classify the committed
range, run the applicable docs-static check, validate the PR body's declarations
and satisfy any actual batch-only obligation on that head. Obtain authenticated
current-head review and inspect all review conversations before coordinator merge.

## Version Management

Version impact: none
Reason: Agent triage guidance allocates no Product Build and changes no Product,
Module, Host, Provider, Contract or Channel identity.

## Documentation Impact

Documentation impact: none
Reason: This agent triage procedure changes no Architecture Portal pages,
product behavior, public API, projected identity or product operating procedure.

## Pitfall Impact

Pitfall impact: recurrence blind-search-reads-as-absence
Reason: Absorb the existing escalation into issue-list; retain the three recorded
incidents and add no occurrence for this mechanism delivery.
