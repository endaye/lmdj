# Wait for actual terminal publication in packaged COUNT-IN proofs

Relates to #2112 and #2233. Task2 follows the unpublished Creator consumer
Task1 (`d962bf10afc1c673e225818d391f3ac2fd42e0b6`) on the same isolated
`fix/count-in-recording-selection` branch. Refreshed main remains
`fa6998234de0560b09ba4720f6f49f8e8af8ba4e`.

## Premise dispositions

The complete existing COUNT-IN/metronome selection runs20 tests. An initial
owned external server omitted the official `--test-audio-observer-file` flag:
all9 failures are worklet-module load errors (11 PASS, exit1/178.236s). A live
HTTP positive control proves the production worklet200 and the observer404.
Preserve that run; use the official flag and byte-equal HTTP200 preflight.

With the official observer, the unchanged selection gives6 FAIL/14 PASS,
exit1/242.964s. Every Native failure reaches `finishCountIn`'s final consume;
all6 retained traces show its immediately preceding ordinary wire result with
`phase:idle`, `recording:false`, but `publication_pending:true`. The same
instrument also records false values (2–6 per case). The helper's old condition
accepts that pending state because it checks only the retained legacy decoder.
Current Host consumption explicitly requires `!engagement.publish_pending`.
Host, SDK and this spec are byte-identical to refreshed main. This is a stale
test readiness premise, not evidence to remove the Native consumption gate.

Keep the legacy-decoder compatibility assertions and add the actual wire
publication flag to the existing5s readiness predicate. Require literal false,
so a missing field cannot masquerade as readiness. Preserve the final genuine
consume ACK, receipt equality, PCM planes/clock/capture, silent held duration,
real release, exact whole Truth/Assets and reload/reopen legs. This does not
assert that these six historical failures explain any other candidate failure.

## Declared files

1. This plan.
2. `tests/platform/web/creator/creator_web_count_in.spec.mjs`.

No product source, protocol, timing, tolerance, budget, fixture or release path
changes. Task1's10 declared files stay separate from this atomic test Task.

## Verification

The complete20-case ordinary-artifact run above supplies the actual RED at the
consume assertion; retain all failures and traces. After the change, run Node26
syntax and the same complete20 cases on the same official Task1 artifact with
the existing official PCM observer route. Bind the modified spec/plan hashes,
all10 distribution files and both fixture hashes. The producer remains Task1;
Task2's entire delta is plan/spec and does not require rebuilding product code.
Run staged and committed new-file ownership, whitespace, PR body declaration
and lint, and exact final-head independent review before guarded merge.

The four complete Task1 recording-switch journeys already pass4/4 at this same
artifact (130.518s): ordinary/COUNT-IN and terminalA/B,32 successful JSON
attachments read back byte-for-byte, exact whole Truth/revision77/Assets and
actual Stop/reopen. They are not a complete Creator/candidate or physical pass.

## Version Management

Version impact: none
Reason: Task2 corrects test readiness only; Task1's Creator Host MINOR debt
remains tracked in #2237. No manifest, identity, Build or snapshot allocation.

## Documentation Impact

Documentation impact: none
Reason: this Task changes only the existing packaged proof and its plan;
Task1 owns the three current Portal fact corrections.
