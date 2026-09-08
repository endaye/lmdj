# LMDJ Contract Schema Validator Implementation Plan

**Goal:** Make the versioned Contracts executable, so a Schema that disagrees
with the code implementing it fails a gate instead of drifting silently.

**Architecture:** The repository keeps the Python side free of third-party
dependencies, so this adds a minimal JSON Schema 2020-12 validator covering
exactly the keyword subset `contracts/**/*.schema.json` uses. The validator
refuses to run against a Schema using a keyword it does not implement, because
silently ignoring one would make a Contract look enforced when it is not. No
Contract document, Module API, or Product identity changes.

Origin: `docs/quality/2026-08-03-review-backlog.md` unit B, item B1, from
`2026-08-03-build-1.0.8.0-review.md` finding 2.

## Tasks

- [x] Add `tests/conformance/json_schema.py` covering the 20 keywords the
  Contracts actually use, with an explicit unsupported-keyword failure.
- [x] Add `tests/conformance/json_schema_test.py` and register it as the
  `contract.schema_validator` unit test.
- [x] Execute the Contracts in `schema_contract_test.py`: validate both
  fixtures, every `module.json`, `assembly.json`, and `version.json`.
- [x] Replace the bundled invalid fixture's implicit coverage with 11 named
  negative cases, each asserting which rule fired.
- [x] Cover the two rules the Schema cannot express with C++ tests and record
  why they live in code.
- [x] Prove the new tests fail without the rules they claim to protect.

## What the executor found

The backlog estimated 10 keywords. The Contracts actually use 20: the estimate
missed `items`, `contains`, `minContains`, `maxContains`, `minLength`,
`maximum`, `maxItems`, `if`, `then`, `allOf`, `oneOf`, and `propertyNames`.

Running the Schemas for the first time also showed that
`tests/fixtures/contracts/capability-v2-invalid.json` documents four
violations but only three are Schema-expressible. Its empty `candidate.outputs`
is not a Schema rule at all: whether a Candidate satisfies the required output
ports depends on the Descriptor, which the candidate Schema cannot see. That
rule is enforced only by `valid_output_bindings()` in
`packages/provider-sdk/src/attempt_store.cpp`.

Unique port names is the same shape. `uniqueItems` rejects only identical port
objects, so two ports sharing a name but differing elsewhere satisfy the
Schema. Its only enforcer is `valid_ports()` in
`packages/provider-sdk/src/registry.cpp:145`, whose branch had no test. This
plan adds `test_v2_registry_rejects_duplicate_port_names` and
`test_v2_registry_rejects_non_lowercase_port_names`, and both were verified by
mutation: deleting the rule from `registry.cpp` fails `provider.conformance`.

Both cross-document rules are now asserted in `schema_contract_test.py` as
deliberate Schema gaps, so a future reader cannot mistake them for covered.

## Non-goals

- Unifying the port-name rule across the Host boundaries is backlog item B2.
  It changes runnable Product behavior and carries a version cascade, so it is
  a separate Task.
- No Contract document is edited. Making a Schema stricter is a Contract
  change and needs its own version decision.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

**Version impact: none.**

- Product Build: unchanged. Nothing under `packages/`, `apps/`, `providers/`,
  or `products/` changes; the only non-test edit is a CTest registration.
- Core Modules: unchanged. `packages/provider-sdk/src/registry.cpp` was
  mutated only during verification and restored; `git diff` confirms no
  residual change.
- Contracts: unchanged. Every Schema document is byte-identical. This plan
  starts enforcing the existing Contracts; it does not alter them.
- Providers and Models: unchanged.
- No tag, Release, Channel promotion, or deployment is authorized.
