# Align stale module-version test fixtures

This is a test-only repair discovered by the exact current-tree Core `full`
run. It restores the source and manifest consistency checks after the already
merged application-facade/audio-runtime version cascade; it does not alter
product behavior or Cardputer wiring.

## Scope

- `tests/core/facade/application_test.cpp`
- `tests/host/native_host_source_boundary_test.py`
- this plan

Both tests asserted the retired application-facade `5.3.0` and audio-runtime
`4.0.3` dependency pair, while the active manifests consistently declare
application-facade `6.0.0` and audio-runtime `5.0.0`. The assertions remain
exact; only their expected current values are repaired.

## Verification

Run the complete Core `full` tier and retain the prior red run showing the two
stale assertions. No threshold, timeout, test selection, or failure handling is
changed.

## Version Management

Version impact: none. This change consumes existing manifest identities and
does not allocate or modify a Module, Contract, Assembly, Product Build, or
release identity.

## Documentation Impact

Documentation impact: none — test expectations only; no documented product
fact, portal route, diagram, or user-facing behavior changes.
