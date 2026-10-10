# Monitor energy observation on paired rendering frames

## Premises

Base: `d5554ed55f7ebc2d800285715cef79dcfed57c9a` (main, including #1948).
The #1948 Creator visual change does not alter the audio test or its producer.
The monitor attenuation journey still reads two independent AnalyserNodes in
sequence, although its comment claims that both readings contain the same
frames. The intervening JavaScript reduction can span an audio render quantum.
No current merged successor replaces this observation method.

The complete Web Runtime Host proof at `6ec71050e02cad41bac85e0c852ab80b1fd0b6e7`
failed the original precision-five comparison: expected 0.25, actual
0.2497655493043446. In a separate real-Wasm diagnostic, a deliberate 4 ms gap
between the original readings produced 34 mismatches in 42 observations;
each mismatch coincided with an advancing audio clock. A two-input observer
measuring the same rendering frames produced zero mismatches in 420
comparisons. This demonstrates the invalid atomic-read premise; it does not
establish the exact frame timing of the historical failure or close unrelated
activation, transport, storage, or device issues.

## Task M1

Replace only the attenuation measurement with a real two-input AudioWorklet
observer. After the real trigger proof, collect the first complete 2048-frame
window after the gain change, with contiguous rendering frames and matching
channel lengths. Sum both inputs in that same processing callback. Pull the
observer through an output of zeros, so it adds no unattenuated audible route.
Serve only the observer module from the owned origin under the unchanged CSP;
do not intercept production operations or replace the engine, voice, or gain.
Disconnect the observer before the original recovery journey.

Declared files:

- `tests/platform/web/audio/paired_energy_probe.mjs`
- `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- `docs/plans/2026-10-10-monitor-energy-frame-alignment.md`

Keep the original levels (1, 0.5, 0), nonzero master assertion, precision five,
and 30-second test deadline. Await one rendering window; do not poll for a
desired ratio or nonzero signal. Keep every later assertion: cross-context
refusal, disconnected-tap direct recovery, repeated connection idempotence,
refusal of an unattenuated reroute, running context, exactly one direct
connection, engine-positive/output-zero mute, and nonzero output after unmute.
The last assertion is an energy observation, not a physical hearing result.

Lowest-tier verification: the real Chromium attenuation journey using freshly
built Wasm, plus all 29 original AudioWorklet/failure cases, JavaScript syntax,
and `tests/build/ci_change_scope_test.py`. A wrong gain must fail the original
ratio assertion, and an aligned observation must retain the complete recovery
journey. No additional gate is introduced. Complete selected batch-only lanes
remain obligations on the committed head and cannot be inferred from focused
or diagnostic runs.

## Verification

The first fresh main-based Wasm build passed in 188.11 seconds. All 29 original
Chromium audio cases ran: 28 passed and the attenuation journey failed while
loading the new observer module, before any energy assertion. Its trace and
error context are retained. The chosen page request interception did not serve
the Worklet fetch; this is a test-module delivery defect, not a product gain
failure. Replace that delivery with a unique temporary static module under the
existing owned proof server root. Delete only its newly created directory after
module loading. CSP, product requests, renderer inputs and test bounds remain
unchanged. The freshly built product Wasm remains byte-identical; a new browser
worker must load the corrected interpreted observer and rerun all 29 cases,
the wrong-gain mutation and the restored complete recovery journey before commit.

Retained historical and diagnostic evidence lives outside the source tree in
the local Creator follow-up evidence directory. Initial runs using an older
retained distribution are diagnostics, not rebuilt current-head proof.

The corrected static delivery passes every original Chromium audio case:
29/29 in 45.78 seconds, with original case bounds. The 77-case staged ownership
suite and module syntax checks pass. The first mutation selector selected no
case and is retained as invalid evidence. After listing and confirming exactly
one original journey, a fresh worker executing gain fixed at 1 failed the
original precision-five assertion (expected 0.25, received 1) in 8.99 seconds.
Restoring the source with a fresh mtime and another fresh worker passed the
complete original monitor/recovery journey in 2.71 seconds. Both executions
load the interpreted observer afresh against the same freshly rebuilt product
Wasm, whose bytes are unchanged. No signal, gain implementation, deadline,
precision, CSP, activation or recovery leg was weakened. Committed-head batch
lanes, independent review and merge are still required. This is automated
energy evidence, not physical hearing or closure of other Host failures.

## Version Management

Version impact: none — this changes test observation only, without a product,
module, provider, contract, Host API, or manifest change.

## Documentation Impact

Documentation impact: none — no portal source fact, product behavior, identity,
or assembly changes. This plan records the test defect and bounded repair.

## Pitfall disposition

The open free-running audio-driver entry concerns frame-dependent assertions
around blocking native dispatch; this test defect is an independent pair of
browser observations. Output-device diagnostics remain advisory and are not
used as causal proof. The repair expresses the necessary frame alignment in
the owning test rather than introducing another process gate or ledger entry.
