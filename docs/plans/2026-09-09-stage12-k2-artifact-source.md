# K2 owned Artifact byte execution and complete ABI migration

Relates to #1034, #467. Base: a81faad3. R1/C-Q1–C-Q5 and R2 are confirmed
in the two 2026-09-09 Stage 12 decision records. K1 merged in #1049.
Live open PR audit found only unrelated ESP32 documentation #1031; no SDK,
Facade or identity migration owner was active. Recheck shared main before shipping.

## Task K2a: implementation and coordinated identities

Replace Provider::run with an owning ProviderRunContext passed by value. Inputs
are frozen SDK copies of owner-returned buffers; source handles retain budget
leases. Explicit execution options inject owner and aggregate limits. There is
no v1 delegate or ambient source lookup. Source/sink callbacks own a shared
control block, reject wrong-thread/late calls, latch active errors, and close
before terminal processing. Consumer validators are registered per capability
output port and execute on private bytes before publication, including optional
outputs. Proof output validation is explicit. SDK never parses Slice or WAV.

Preserve singular Candidate and existing immutable terminal format. Persisted
terminal is visibility; publication/terminal I/O failure retains the reservation
as interruption evidence. No Project/Job/CandidateIndex API changes. Facade
passes explicit unavailable owner access until K5; unbound Proof remains usable.

Declared implementation files:
- packages/provider-sdk/include/lmdj/provider/{provider,attempt_store,registry}.hpp
- packages/provider-sdk/src/{provider,registry,attempt_store}.cpp and CMakeLists.txt
- providers/local-proof-{success,failure}/{src/provider.cpp,CMakeLists.txt,module.json}
- packages/application-facade/src/application.cpp
- tests/core/provider/{conformance,spec_regression,attempt_isolation,attempt_ledger_invariant,host_settings_invariant}_test.cpp
- tests/core/provider/{artifact_source,output_validation}_test.cpp, byte_fixture.hpp, byte_harness.hpp, CMakeLists.txt
- tests/core/provider/{execution_crash,callback_stress}_test.cpp;
  packages/provider-sdk/src/attempt_store_test_hooks.hpp (compile-only test seam)
  and CMakePresets.json (exclude new stress test from coverage).
- root CMakeLists.txt (register the new component executables in coverage union)
- tests/core/facade/assembly_loader_test.cpp and attempt-related Facade tests
  only where the explicit unavailable-owner refusal changes their expectation
- tests/core/facade/application_test.cpp and tests/build/version_test.py
  (exact ABI/dependency pins and bound-input refusal plus unbound Proof journey)
- apps/docs-site/test/repo-facts.test.mjs (exact coordinated Host identity pins)
- tests/conformance/{module_graph,version_lock}_test.py and
  apps/docs-site/docs/operations/testing-and-proof.mdx (current composition)
- this plan; current provider-sdk, application-facade, web-runtime-platform,
  local-proof, affected Host, Assembly and capability-map Portal pages;
  provider-sdk.architecture.json and its official generated HTML/SVG.

Identity files: provider-sdk, application-facade, web-runtime-platform and five
Host module.json files; products/lmdj/{version.json,assembly.json,assembly.lock.json,
src/compiled_assembly.cpp,generated/web-runtime-identity.json,
generated/web-runtime-identity.mjs}. Source-package identities regenerate from
CMake; Assembly/compiled identity via scripts/version.py lock, Runtime via its
existing generator. Amend exact test paths if a concrete migrated consumer
requires it; never skip an existing journey to preserve a green prefix.
Creator package identity: apps/creator-web/{package.json,package-lock.json}.
Official Host changelog projections:
apps/docs-site/docs/operations/{creator,runtime}-changelog.mdx.

## Verification and far-side evidence

- Configure/build dev; Provider and Facade tests with nonzero discovery.
- Source tests: validated declared bindings only, corrupt/missing/oversized input,
  aggregate overflow, original occurrence ordering, immutable ownership and
  retained handles, shared budget overlap, explicit empty owner refusal.
- Callback tests: wrong thread, retained callback and context, ignored failures,
  return/close ordering; stress tier executes the concurrent lifecycle scenarios.
- Output tests: count/aggregate bytes, missing validators, optional invalid output,
  approved domain error propagation versus SDK error spoofing, scratch reservation.
- Reserve -> input -> run -> staging -> validator -> publish -> terminal -> inspect
  -> new process inspect. Kill/fault at durable publication/terminal transitions;
  assert complete hash/length identity or no visible success, immutable old ledger,
  retained interrupted reservation and rejected ID reuse. Existing durability
  failure tests remain strict; direct execution is not a hard timeout claim.
- version/module graph/lock/dependency checks, staged ownership, docs-site check.
  Complete snapshot proof belongs to K2b, not a release or full-CI merge gate.

## Version Management

Version impact: required. Allocate SDK 2.0.0 (api_version 3) and Proof Providers
2.0.0 (api_version 3) for the new execution/registration ABI. Facade exposes
ProviderRegistration factories: 4.0.0; web-runtime-platform exposes its config:
5.0.0. Their public C++ API revisions advance; unchanged Host transport contracts
retain api_version and receive dependency-only PATCH bumps (native Hosts 3.2.1,
Web Hosts/Creator 4.1.1). No new Slice Provider or Contract allocation.
Recheck this fresh allocation against main at shipping. Current Product 1.0.45.0
advances BUILD to 1.0.46.0 for the coordinated dependency integration, canary
snapshot. No tags, release, deployment or Channel promotion.

## Task K2b: immutable documentation snapshot

After K2a is verified and committed, run scripts/docs-site.sh version with the
allocated Build and canary on clean source. Commit only the exact generator
output inventory under docs/site/versions and current versions metadata as a
second Task in the same PR. Validate snapshot and post-squash provenance; publish
a supported witness if required. Never merge K2a without its matching snapshot.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/provider-sdk/ /core/modules/application-facade/ /core/modules/web-runtime-platform/ /providers/local-proof/ /hosts/core-cli/ /hosts/core-mcp/ /hosts/native-host/ /hosts/web-runtime/ /hosts/creator-web/ /assembly/lmdj/ /product/capability-map/ /operations/testing-and-proof/ /operations/creator-changelog/ /operations/runtime-changelog/
Keep generated identities derived and distinguish SDK byte execution from the
not-yet-integrated Slice Provider and Host owner wiring. No new required gate.

K2a portal validation uses `npm --prefix apps/docs-site run check:current` on
the source change. The full `scripts/docs-site.sh check` was also run before
commit and correctly reports only the absent new Build snapshot. K2b requires
clean committed source to generate it; rerun the full check before its commit
and before pushing this PR. This is an ordered snapshot dependency, not a waived
verification gate. Pitfall impact: none; byte/lifecycle defects have regression
tests and the snapshot ordering follows the existing official workflow.

## Verification results before source commit

- Dev configure/build passed; Provider/Facade: 45/45, including 13 Provider
  registrations and the component callback/byte/crash tests.
- Explicit full stress selection: 13/13; callback stress runs 300 run/return races.
- Module graph, version lock, Product version, active tree, schema conformance,
  dependency audit and coverage-union tests passed.
- Current Portal: 112 tests, typecheck, diagrams, build and built-route checks
  passed. Full Portal snapshot gate is completed by K2b as described above.
- SIGKILL acceptance covers reserve, validated inputs, staged outputs, validated
  outputs, published bytes and persisted terminal. Separate restarted processes
  assert invisibility or complete nonempty Artifact hash/length and immutable
  prior terminal; publication and terminal obstruction tests retain reservations.
- No ASan/TSan, Web packaging, physical hearing, deployment or release claim.

Shared-file audit refreshed at main 9e2077d5: #1072 changes Sound Set audition
behavior/docs; #1074 changes Capture memory plus Native docs/CMake; #1031 is
ESP32 documentation. None changes the SDK ABI or allocated Product/Module
identities. Preserve their independent documentation if a real conflict arises;
no strict update gate or automatic release is introduced.
