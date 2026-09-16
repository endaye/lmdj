---
id: negative-mutation-matches-fixture-value
area: ci-release
status: open
recurrences:
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/pull/1364
    observed_by: Kimi Code CLI
exit: none
---

# A negative test that mutates an input to a fixed value silently becomes a no-op when a shared fixture's own value drifts into it

## Why

`tests/build/release_dispatch_evidence_test.py` verifies that the dispatch
receipt verifier rejects a receipt whose `tag` differs from the request: it
mutates `document["inputs"]["tag"]` to `"lmdj-v1.0.57.0"` and expects a
refusal. #1364 legitimately moved the shared receipt fixture's own tag to
`lmdj-v1.0.57.0` (that Build became real). From then on the mutation wrote
the value the fixture already held, the payload still matched the expectation,
and the "refusal" case passed without the verifier rejecting anything. The
suite stayed green while the negative leg proved nothing — the same coverage
illusion as an unregistered test file
([`unregistered-test-file-reads-as-coverage`](unregistered-test-file-reads-as-coverage.md)),
but produced by fixture-value drift rather than registration.

What made it invisible: the mutation target is a string literal far from the
fixture that defines the baseline value, and nothing asserts the mutation
actually changes anything. The verifier under test was not broken; the proof
was.

## How to apply

- When a negative test mutates a shared fixture to a fixed literal, assert the
  mutation is non-vacuous (`assertNotEqual(original[key], value)`) inside the
  same case, so a future fixture drift fails the test instead of gutting it.
- Prefer a clearly foreign sentinel (e.g. `lmdj-v9.9.99.0`) over a plausible
  next value: a value that looks like a real future identity invites exactly
  this collision when that identity becomes real.
- When a suite in your Task's lane fails on a value assertion, check for a
  vacuous mutation before touching the verifier: compare the mutation target
  against the fixture's current baseline first.

`exit: none` because the mechanism is per-test hygiene; no gate can decide
whether a mutation was intended to change a value. If a second recurrence
appears, look for a lint that flags `assertRaises` cases whose mutated input
equals the fixture baseline.
