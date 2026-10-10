# Preserve Candidate saved-byte evidence without numeric-array IPC

## Objective and premise disposition

The complete Creator proof at b07e178dfd1c73c654697317aae71cd0f31ade42
failed the full Slice preview/adopt/reopen journey at its original 30-second
budget. Its retained trace shows multiple full saved-file reads consuming
0.86–2.62 seconds each; the final reopen exhausts the total budget. A permanently
missing Slice source is unproven. The unchanged journey passed isolated in
20.3 seconds, which does not erase the complete-run failure.

The refreshed main base is 414268d654adeae32dfb500f62c000f06e4f2b47. The
Candidate spec's files helper is byte-identical to b07e178d. Current open PRs
#1929, #1936, #1937, #1939 and #1941 do not change that helper. New main #1938
and #1940 modify Sequence/Sound Set navigation, not this saved-byte boundary.
The goal's pending BPM, direction-key, Assign and Perform decisions are unrelated.

A paired profile using the exact retained distribution and Candidate fixture,
with the same real imported WAV, found all 10 paths and 232,344 bytes identical.
Returning numeric arrays took 834–922 ms; returning Uint8Array and expanding
in Node took 31–76 ms. OPFS reads inside the browser took 18–48 ms. A second
paired input profile preserved the complete 96,044-byte WAV digest/length while
reducing numeric-array transfer from 832–1,149 ms to typed-array transfer in
5–12 ms. The locked
Playwright 1.62.1 serializer supports typed arrays directly. Thus numeric-array
serialization is a verified material cost; broader load/audio failures remain
unresolved.

## T1 — Transfer unchanged bytes through the typed-array serializer

Declared files:

- tests/platform/web/creator/creator_web_candidate.spec.mjs
- docs/plans/2026-10-10-creator-candidate-byte-evidence.md
- .agents/pitfalls/playwright-byte-transfer-overhead.md

Keep OPFS files and WAV input as Uint8Array while crossing Playwright, then
expand saved files into the existing path-to-numeric-array result in Node.
Use an explicit view copy for incoming WAV/source-restoration bytes, preserving
the exact byte range rather than exporting a Buffer backing slab. Preserve every file path,
byte, deletion fault, source restoration, digest, length, lineage, Truth and
reopen assertion. Retain the original test deadlines and every journey leg.
No product source, API, fixture or test selection changes.

Precommit lowest-tier verification: node --check of the changed spec; all eight
existing Chromium Candidate cases against an owned packaged server and the
retained exact fixtures, including missing-source restoration. Use the retained
failing distribution as controlled helper evidence; it is not current-main
product acceptance. Run staged new-file ownership before committing. After
commit, build/package the final clean head and execute those same cases on that
distribution. Run committed-head canonical lane classification; complete every
selected batch-only obligation before merge. Record all terminal results outside
the worktree. This ordering lets the clean-head product proof bind to the actual
Task commit; no verification requirement or journey leg is removed.

## Version Management

Version impact: none
Reason: test transport optimization only; no product source, manifest, API or
Contract changes or version debt.

## Documentation Impact

Documentation impact: none
Reason: acceptance harness transport only; no Portal facts, routes or source
identities change.

## Pitfall Impact

Pitfall impact: new playwright-byte-transfer-overhead
Reason: the measured serialization cost belongs to the locked tool boundary,
not product logic or per-sample matcher starvation. Preserve the paired evidence
and strict byte identity without adding a universal timing gate.

## Acceptance status

Measured cost and byte equivalence are verified. An initial output-only
optimization ran all eight cases against the exact retained distribution:
six passed; the full journey still exhausted 30 seconds at its final Discard
leg, and zero-onset import visibility failed at its original 5-second guard
before the byte helper. Actual saved-file calls fell to 18–65 ms. Those failures
remain; the subsequent profiled input-byte optimization must run the complete
group again. The complete bidirectional group then ended with 3 passed / 5
failed (2.9 minutes): three failures occur at initial Project import before the
changed helpers, one full-journey total-budget expiry and one Host timeout.
Both terminal logs and traces are retained; no commit or shipping pass is
claimed. The pitfall ledger initially rejected a local-ahead-of-UTC recurrence
date; using the actual UTC observation date restored all 15 ledger tests.
Canonical Creator lane and independent current-head review remain
pending. No whole-product or real-device acceptance is claimed.

The diagnostic copy then passed all eight cases (2.5 minutes), retaining request
metadata across reopens without capturing any expired deadline. This diagnoses
neither the previous Host timeout nor the earlier import failures. Removing all
diagnostic instrumentation and running the original complete eight-case group
against the same exact retained inputs passed in 2.3 minutes. This is a controlled
helper-semantic pass, with the original 5-second assertions, 30-second journeys,
full saved bytes and missing-source restoration unchanged. Earlier failures stay
retained and unresolved. Final-head package/Creator verification remains pending.
