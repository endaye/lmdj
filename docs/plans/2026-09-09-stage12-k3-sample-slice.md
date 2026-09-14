# K3 deterministic, unregistered Slice reference Provider

Relates to #1035, #467, #472. Base: 692ac483. R1/C-Q1–C-Q5 are confirmed;
K1 and K2 are merged. The live PR audit found only unrelated ESP32 docs #1031.

## Task and declared files

Implement local.sample.slice with the approved integer amplitude rising-edge
detector. Decode bounded RIFF PCM16 views without resampling or copying sample
buffers. The independent reusable consumer validator checks syntax, shape and
source context before Attempt publication. Use streaming JSON validation rather
than building a second output DOM. Provider receives only owned SDK source/sink.

- providers/local-sample-slice/{CMakeLists.txt,module.json}
- providers/local-sample-slice/include/lmdj/providers/local_sample_slice/{factory,validation}.hpp
- providers/local-sample-slice/src/{provider,validation}.cpp
- root CMakeLists.txt and tests/core/provider/{CMakeLists.txt,sample_slice_test.cpp}
- tests/build/version_test.py and tests/conformance/module_graph_test.py: retain
  the exact Assembly inventory and name only this unregistered source exception
- apps/docs-site/docs/providers/{local-sample-slice,overview}.mdx and sidebars.ts
- apps/docs-site/scripts/lib/snapshot-provenance.mjs and its existing test:
  current completeness pin becomes 44; historical validation must use the
  recorded source revision's exact inventory, not today's page count
- .agents/pitfalls/snapshot-page-pin-only-fires-at-freeze.md: record historical-pin recurrence
- this plan; docs/quality/2026-09-09-stage12-k3-reference-results.md
- scripts/ci/scope_policy.json only if staged ownership reveals a missing rule

The new source-package identity covers both public headers, both source files
and module.json, sorted and hashed by CMake. No fixture IDs/hashes in code.
No Product Assembly registration or Host platform claim: descriptor uses test.

## Verification

Configure/build dev. Run provider.sample_slice, artifact_source,
output_validation and conformance with nonzero discovery. Real Registry /
AttemptStore execution: input custody -> integer detector -> sink -> independent
validator -> durable terminal -> inspect -> reopened store and identical bytes.
Unseen pulse/silence/stereo/refractory/threshold/overlap cases; malformed WAV
chunks/padding/fmt/geometry; strict parameter failures; >4096 onset refusal;
required output count, same-source/rate/EOF/order and unchanged Project/source.
Replay the unchanged six-case smoke corpus, export actual predictions to B2 and
record its scores honestly without a production-selection threshold.
Cross-check reusable validator against every K1 JSON conformance vector.
Run corpus, module graph/version lock/version, dependency, staged ownership and
full current Portal checks. No concurrency change, full-CI or physical claim.

## Version Management

Version impact: required. New Provider local.sample.slice 1.0.0, api_version 3,
depending on provider-sdk 2.0.0; no existing identities change. Product Build
remains 1.0.46.0, its existing snapshot immutable. No new Contract, Assembly,
snapshot, release, deployment or promotion. K4 owns later registration and its
fresh integration identities. Historical snapshot validation retains complete
source-path/hash/length equality against its recorded revision.

## Documentation Impact

Documentation impact: required
Affected portal pages: /providers/local-sample-slice/ /providers/overview/
The source-only page must not masquerade as an Assembly identity. It links the
active manifest and describes the reference implementation and measured limits.
