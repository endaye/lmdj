# Stage 12 R1/R2 review delivery and implementation handoff

Date: 2026-09-09. Relates to #467 and #471.
Status: complete proposal for review; product decisions remain unapproved.
Authority: [review packet](../design/2026-09-09-stage12-contract-candidate-review.md).

## This Task

Declared files, one documentation commit:

- Create docs/design/2026-09-09-stage12-contract-candidate-review.md.
- Create this plan.
- Update docs/plans/2026-09-09-stage12-decision-followups.md with review links
  and the proposed L1 owner/cardinality correction.

Verification: parse the embedded descriptor and validate it against the existing
capability.v2 schema with tests/conformance/json_schema.py; inspect required
field parity with capability.hpp and policy consumers in attempt_store.cpp;
check local relative Markdown targets; run scripts/docs-site.sh check for the
documented source facts; stage then run ci_change_scope_test.py and whitespace
checks. No new tests or gates: these checks validate the proposal and existing
path ownership, not implementation or runtime acceptance.

## K1 current exact file inventory after R1 approval

This inventory replaces the historical architecture-portal paths in K1's older
plan. K1 is #1033; R1 must be explicitly accepted before activating these files.

Create:

- contracts/capability/sample.slice.v1.json
- contracts/slice-points/lmdj.slice-points.v1.schema.json
- contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md
- tests/fixtures/contracts/slice-points/valid.json
- tests/fixtures/contracts/slice-points/invalid.json
- apps/docs-site/docs/contracts/artifact-audio.mdx
- apps/docs-site/docs/contracts/slice-points.mdx

Modify:

- tests/conformance/schema_contract_test.py
- apps/docs-site/docs/contracts/capability.mdx

The corpus retains source context beside payloads. K1 owns independent Python
shape/context examples; K3 owns production validators. K1 must not claim Python
fixtures prove execution-time C++ validation. If the approved schema uses a
keyword unsupported by the minimal validator, declare json_schema.py and its
regression suite before editing; do not silently ignore that keyword. New paths
must pass staged ownership; only add routing changes if the current ownership
test demonstrates a gap, then amend the declared files before committing.

Lowest-tier verification:

```bash
python3 tests/conformance/schema_contract_test.py
python3 tests/conformance/json_schema_test.py
python3 tests/core/provider/stage12_fixture_corpus_test.py
python3 tests/build/ci_change_scope_test.py
scripts/docs-site.sh check
```

Acceptance remains the K1 positive/negative matrix in the original Capability
implementation plan, including malformed JSON and contextual checks. No Provider,
SDK ABI, Assembly or Build allocation belongs to this Contract-only Task.
Proposed new consumer/profile/output versions are all 1.0.0; the capability.v2
envelope remains unchanged. These are proposed allocations until R1 is accepted.
Documentation impact for K1: required; routes /contracts/capability/,
/contracts/artifact-audio/, /contracts/slice-points/.

## L1–L5 plan changes to make after R2 approval

- L1 (#1038): own JobRecord/CandidateIndex in the Facade's Workspace state,
  consume K2 terminal evidence, preserve singular SDK Candidate. Remove the
  plural-result migration requirement. Exact storage/locking API and files are
  an implementation plan prerequisite; include cross-process exclusion and
  restart publication tests in L1, not only L4.
- L3 (#1040): extend the one existing lineage carrier with the closed Slice
  capability derivation and its explicit field authority. Allocate the successor
  Project Contract plus old resample/soundset round-trip compatibility before
  implementation. Do not introduce unused trim/copy variants.
- L2 (#1039): implement one-revision adoption with explicit target uniqueness,
  unchanged source binding checks and reuse rules from R2. Include candidate
  eligibility versus lifecycle races and all-target quota/preparation refusals.
- L4 (#1041): extend L1 durability to discard/supersede/cancel; no TTL or GC.
- L5 (#1042): preview/stop/adopt/save/reopen journey, including no-onset UI and
  unknown commit response inspection. Native/Web support is evidenced separately.

Each L Task must publish exact files, current version/dependency closure and
named lowest-tier tests after the relevant decision is accepted. This Task
provides product choices; it does not pretend that the old high-level L table
is an executable file inventory. Avoid reserving another SDK 2.0.0 for this work.

## Review and completion boundary

Request one explicit confirmation of R1 and R2-A–F as written in the linked
packet; collect amendments by ID. Approval creates a new dated decision record,
updates current readiness in the parent/child Issues, and refreshes exact
implementation plans. Keep #467/#471 open until their approved-design and
implementation-plan acceptance is actually satisfied. This proposal PR uses
only Relates to references, not closing directives.

## Version Management

Version impact: none for this Task; retained review material only. No Product,
Module, Host, Provider, Contract, Channel or revision identity is allocated.

## Documentation Impact

Documentation impact: none for this Task; no current Portal pages or facts change.
The checks above validate references to existing source, not new availability.
Pitfall impact: none; no process mechanism is changed.
