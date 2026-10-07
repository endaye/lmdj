# Local audio output diagnostics (#1730)

## Task

Record the macOS default output at the start and end of the Creator and Web
Runtime Host proofs, including direct invocations and `scripts/local-ci.sh`.
Print lane, wrapper PID, UTC observation time, device name and transport beside
the command's exit status. Flag Bluetooth at either endpoint and different
endpoint routes with a wired/built-in rerun suggestion. Preserve failed tests,
their exit status and real audio output; a warning does not establish a cause.
Unavailable diagnostics remain visible and advisory. Other platforms execute
the original proof without a macOS probe. Cached local passes are historical
input evidence and do not execute or claim a new device observation.

Declared files:

- `scripts/local-audio-output.py`
- `scripts/creator-web.sh`
- `scripts/web-runtime-host.sh`
- `scripts/ci/scope_policy.json` (add ownership only for the new helper)
- `tests/build/ci_local_audio_output_test.py`
- `.agents/pitfalls/local-audio-proof-inherits-output-device.md`
- this plan

## Verification

Lowest tier: Python tooling tests with captured profiler JSON and real child
processes. Each test fixes one fact: output rather than input/system selection,
Bluetooth warning, changed endpoint warning, unavailable probe, retained exit
status, non-macOS passthrough, or public proof-entry wiring. These deterministic
tests defend diagnostic reporting, not the physical audio path. No new required
CI check or changed timeout/threshold is introduced.

- `python3 tests/build/ci_local_audio_output_test.py`
- `python3 tests/build/ci_local_preflight_test.py`
- `python3 tests/build/ci_change_scope_test.py` after staging new files
- `bash -n scripts/creator-web.sh scripts/web-runtime-host.sh`
- Capture the actual Mac output with the helper around a bounded command.
- On the clean committed head, run both selected batch-only proof lanes through
  `scripts/local-ci.sh --lanes creator,web_runtime_host --no-cache` and retain
  their printed input-bound evidence. Run sequentially in this worktree.

Sampling is at the endpoints: a switch away and back between observations can
escape detection. Captured Bluetooth/switch fixtures test the diagnosis; they
do not claim a physical Bluetooth-switch or device-latency acceptance.

## Version Management

Version impact: none
Reason: local verification tooling only; no Product, Module, Provider, Host or
Contract artifact identity changes or Product Build allocation.

## Documentation Impact

Documentation impact: none
Reason: no Architecture Portal pages, projected identities, diagrams or product
source facts change. The plan and pitfall document the local diagnostics.

## Pitfall Impact

Absorb `local-audio-proof-inherits-output-device` into the deterministic tooling
test and automatic endpoint diagnostics. Retain the historical recurrences and
the guidance to read traces before attributing an audio failure.
