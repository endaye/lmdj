# Stage 12 K3 reference Slice results

Relates to #1035, #467, #472. This is an unregistered deterministic reference,
not a production-selection or Host support claim.

The real Registry/AttemptStore test emitted predictions from unchanged B1 corpus
bytes. B2 consumed those predictions without changing labels or tolerances.
Manifest SHA-256: `33d06cfe36df2d840aae168908c59be6747753d2c7e3b6fac56b4c6f1f13f5a5`.

| Fixture | Actual frames | TP / FP / FN | Result |
| --- | --- | --- | --- |
| basic_three_onsets | 2400, 7200, 12000 | 3 / 0 / 0 | precision/recall/F1 = 1 |
| close_overlapping_tails | 480 | 1 / 0 / 1 | precision 1, recall 0.5, F1 2/3 |
| silence | none | 0 / 0 / 0 | silence correct; F1 not applicable |

Micro precision is 1, recall 0.8, F1 8/9. The overlapping tail never falls below
the threshold before its second labeled onset; the approved rising-edge rule
therefore misses that onset. No quality threshold or production selection is
inferred. Malformed/unsupported and unavailable-source corpus cases exercise
terminal errors, not quality scoring.

Reproduce from the repository root after a dev build:

```bash
build/core/dev/bin/lmdj_provider_sample_slice_tests /tmp/lmdj-k3-predictions.json
python3 tools/provider-benchmark/score_slice.py \
  --manifest tests/fixtures/provider-benchmark/sample-slice/manifest.json \
  --predictions /tmp/lmdj-k3-predictions.json
```

The executable also tests unseen integer pulses, both supported sample rates,
mono/stereo including the right channel and -32768, threshold equality,
refractory suppression without delayed emission, silence and onset overflow.
It checks every K1 JSON vector against the reusable consumer validator.

Acceptance evidence follows the complete K3 journey: owned input bytes enter
Registry execution; the algorithm writes through the sink; independent validation
rejects wrong source/rate/EOF/order/schema and missing required output; terminal
receipts preserve the exact error or output; reopening the store confirms status
and output bindings; actual files match digest and byte length; a second execution
produces identical bytes. Source files and the inaccessible Project sentinel
remain unchanged. Omitted and explicit default parameters produce equal output
but distinct actual-parameter provenance hashes.

No concurrency implementation changed. No physical Host, RSS enforcement,
hard timeout, production integration, release, or deployment was exercised.
