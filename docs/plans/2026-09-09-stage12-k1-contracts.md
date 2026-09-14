# Stage 12 K1: Slice Contracts and conformance

Relates to #1033; authority is the confirmed R1 decision in
[Stage 12 decisions](../prd/decisions/2026-09-09-stage12-contract-candidate.md).
K1 implements the approved current file inventory in
[review delivery](2026-09-09-stage12-review-delivery.md).

## Declared files

Create contracts/capability/sample.slice.v1.json,
contracts/slice-points/lmdj.slice-points.v1.schema.json,
contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md;
tests/fixtures/contracts/slice-points/{valid,invalid}.json;
apps/docs-site/docs/contracts/{artifact-audio,slice-points}.mdx; this plan.
Modify tests/conformance/schema_contract_test.py and
apps/docs-site/docs/contracts/capability.mdx.

Schema validation fixes payload shape. Independently named byte/context vectors
fix JSON syntax, source binding, ordering and UTF-8 encoded length. Generated
boundary cases cover large point counts without storing thousands of repeated
fixture lines. Their layer assertions prevent attributing context rules to JSON
Schema. The canonical reference serializer checks compact sorted UTF-8 bytes
and round-trip stability; production C++ validation and replay remain K2/K3.
No generic Schema keyword extension or new required CI gate is needed.

## Verification

```bash
python3 tests/conformance/schema_contract_test.py
python3 tests/conformance/json_schema_test.py
python3 tests/core/provider/stage12_fixture_corpus_test.py
python3 tests/build/ci_change_scope_test.py
scripts/docs-site.sh check
```

Stage new files before ownership checks; inspect staged diff and whitespace.
Check that vector discovery is nonzero and failures name the individual vector
and its expected validation layer. No SDK lifetime, Provider audio processing,
performance measurement or Host adoption journey is claimed by this Task.

## Version Management

Version impact: new consumer instance, binary profile and output Schema at the
confirmed initial 1.0.0. The capability.v2 envelope remains unchanged.
No Module/Provider ABI or Product Build allocation. Product registration and
Assembly lock integration are K4; adding these Contract definitions does not
make a Provider available. No tag, Release, deploy or Channel operation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /contracts/capability/ /contracts/artifact-audio/ /contracts/slice-points/
Current pages distinguish formal Contract/conformance from absent execution.
New consumer/profile/output identities stay in their source files until K4
registers them; they are not declared as integrated Assembly identities or
imported from live JSON into future frozen pages. No handwritten Portal version
strings. No source diagram
changes: this Task adds definitions, not a new module or execution boundary.
Pitfall impact: none; no governance mechanism change.
