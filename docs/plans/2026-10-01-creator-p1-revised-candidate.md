# P1: revised test candidate after complete-proof findings

Retain the frozen first candidate byte-for-byte. Allocate the next unused BUILD
from the current candidate manifest and a Creator PATCH from its Host manifest
for the Pad reservation/recording fixes and retained concurrent main changes.
No other component version or dependency pin changes. Generate Assembly lock,
compiled Assembly and Runtime identities using their stable tooling.

## Declared files

`apps/creator-web/{module.json,package.json,package-lock.json}`;
`products/lmdj/{version.json,assembly.json,assembly.lock.json,src/compiled_assembly.cpp}`;
`products/lmdj/generated/web-runtime-identity.{json,mjs}`;
`tests/build/version_test.py`, `apps/docs-site/test/repo-facts.test.mjs`,
current generated Creator changelog, this plan and the existing integration plan.
A separate immutable snapshot Task follows the clean source commit.

## Verification

Manifest verification, generated identity freshness, version suite and
change-scope tests; portal source facts, routes and diagrams. Freeze from the
retained clean source and verify the new snapshot without modifying the older
snapshot. Complete packaged Creator and Runtime Host proofs and Linux Core,
ASan and coverage run against the committed new candidate. Earlier candidate
results are retained negative/partial evidence, not new-candidate lane passes.

## Version Management

Version impact: new Product Build and Creator Host PATCH. Numbers are derived
from retained live manifests and checked against remote tags and release intents.
No release, tag, Creator deployment or Channel promotion is authorized.

Documentation impact: required
Affected portal pages: /hosts/creator-web/, /operations/creator-changelog/ and
generated component/version routes.
Reason: changed Host and Assembly identities require current projections and a
new immutable test-candidate snapshot.

The pre-freeze portal check confirms current source tests, then refuses the
missing new snapshot at `check:release-docs`. The snapshot command requires a
clean retained source commit: settle source first, generate the immutable new
snapshot immediately afterwards, and rerun the complete portal gate. Retain
this intermediate refusal and do not report complete portal passage before
the post-freeze check succeeds.
