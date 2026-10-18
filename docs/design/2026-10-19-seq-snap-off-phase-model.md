# SEQ SNAP OFF: actual frame and current-loop phase

Authority: #2112 / #2234 and the approved
[Pattern switch decision](../prd/decisions/2026-10-10-pattern-switch-while-playing.md).
This refines S5 in the [original plan](../plans/2026-10-10-pattern-switch-and-count-in.md).
P1 is the [phase arithmetic Task](../plans/2026-10-19-seq-snap-off-phase-anchor.md);
it does not enable OFF in the product.

## Settled position rule

Use the actual audio application frame S and its coherent source position N.
The existing musical denominator is D = 2,880,000 at 48 kHz / PPQ 960.
For nonzero source and target loop lengths Ls/Lt in ticks:

```text
source_local_N = N % (Ls * D)
target_local_N = source_local_N % (Lt * D)
target_anchor = {runtime_frame: S, tick_numerator: target_local_N, bpm: target_bpm}
```

The source reduction is essential: old one-bar Pattern, second loop, beat 2
has cumulative tick 4800 but source-local tick 960. Switching to two bars must
land on tick 960, not tick 4800. A shorter target wraps that local position;
a source-loop boundary maps to zero. Preserve the fractional numerator rather
than rounding to a whole tick or frame. Reject zero/overflowing geometry or
unsupported BPM; do not manufacture a plausible fallback.

S is a real engine frame, not `S - phase_in_frames`. At real frame 36,000,
source 240 BPM position tick 2880 maps to target 40 BPM with the same tick
position. A synthetic origin would be -180,000 and underflow unsigned frame
arithmetic. The actual anchor is `{36000, 8294400000, 40}`; target tick 2881 is
due at frame 36,075. Existing exact boundary projection can consume this anchor.
Changing target BPM changes only the subsequent tick rate, not matched position.

## Native publication and ownership work still required

P1's pure helper does not observe audio, allocate a publication, authorize a
switch or retain a receipt. Its future caller must provide N from the actual
coherent source clock at actual S. Request-time estimates, delayed inspect time
and current Pattern after a later switch cannot establish historical position.

The Native follow-up must add a distinct cross-Pattern mode and retain actual
`(S, N, BPM/geometry)` for each pinned publication until its own acknowledgment.
Do not relax the same-Pattern phase-edit contract, borrow an unrelated
predecessor's anchor, overwrite an audio-owned predecessor or expose a predicted
frame as Applied. Check old generation/Pattern/frame authority, supersession,
cancel and Stop under their original budgets and complete concurrency tests.
Audit the precise OFF eligibility behind a claimed predecessor and subsequent
quantized boundary rules against the approved queue semantics before declaring
that follow-up's files. Any remaining product concurrency ambiguity is a gate
for the affected implementation, not permission to choose silently.

Voice behavior is also a separate unresolved product question: when the target
has a note whose onset precedes matched position but whose duration crosses it,
the decision does not yet say whether to chase that note. An owner question is
pending. Do not infer an answer from the default selection or from this pure
position helper. Preserve live/manual input ownership and existing declick and
gated-release rules in whichever reviewed Native behavior is later selected.

## Recording producer before consumer

S3 C3/C4 already carry actual switch S and partition source input before S from
target input at/after S. Their quantized target profile starts at zero. OFF must
carry the actual nonzero anchor before releasing parked target candidates;
keeping S while substituting N=0 would silently record into the wrong ticks.
Retain original recording operation/runtime/start epoch and COUNT-IN S0/e1/e2;
OFF does not open a second Journal or rewrite those original identities.

At the inspected stack parent, `PatternAdmissionOwner::continue_segment` and
the private I/O `segment` request pass BPM plus zero position. Extend that
producer and exact retry identity rather than converting with the latest
transport clock. Existing `SequenceAdmissionTimingProfile` already persists
runtime_frame, tick_numerator and BPM with Pattern/generation/watermark/revision;
its grammar can carry a nonzero anchor. Reuse it without adding keys or relaxing
strict decoding merely to support OFF. Refresh the complete durable validator,
restart/retry/abort and late physical-release journeys in that Task.

## Host, SDK and Creator follow-ups

Expose `snap: off` only after Native publication and recording producers can
deliver their real applied anchors. Audit the existing clock APIs before
choosing an additive companion; legacy physical `origin_frame` alone cannot
represent a fractional nonzero start. Keep strict legacy response shapes and
unavailable behavior; never fill a missing anchor with zero.

Then add OFF to the one shared device preference and existing ordinary
Sequence/Perform/global-recording selection path. Preference save/reopen is
device state, not Project Truth. Metronome, playhead and recording must consume
the same actual clock. Performance-record Launch retains its separate existing
event semantics. Keep all COUNT-IN locks and original pre/post-start barriers.

Before each follow-up, refresh main, Issues, actual successors and the stack
parent, and declare its exact files, lowest owning tests and acceptance legs.
The sequence is Native publication/retention, Facade/recording plus Host/SDK,
then Creator and packaged combination. These are remaining work boundaries,
not preauthorized wildcard file lists or completed Tasks.

## Timing debt and evidence

#1973 remains the canonical fractional quantized-boundary debt. P1 performs no
boundary scheduling and does not resolve it. The Native follow-up must audit
the exact path reached from OFF into Beat/Bar/End and live edits; fix any
acceptance-blocking defect in its owning scope under #1973, without widening
timeouts, reducing journeys or reporting the rounded legacy path as exact.
Do not duplicate that debt or turn unrelated UI work into a global gate.

Independent literal absolute tick/frame oracles must distinguish common-mode
producer/consumer errors. Later acceptance covers unequal loops/BPM, loop edge,
audio-owned predecessor, later snap, refusal/cancel/Stop, retained B after C,
recording segment durability/restart and real packaged current/queued/audio/
persistence. P1's component proof covers only position arithmetic. Full
candidate, version settlement, device and human acceptance remain separate.

## Version Management

P1 adds a function only: Audio Runtime additive API MINOR debt in #2237, no
existing layout or persisted grammar change. Native retention may enlarge the
public concrete `RealtimeEngine`; private fields still affect its C++ ABI and
require MAJOR classification. Deduplicate compatible pending debt only after
examining actual final domains. No guessed identity or Build allocation.

## Documentation Impact

Documentation impact: required for P1 on `/core/modules/audio-runtime/`.
Current Portal/diagram state must describe the pure helper separately from
OFF product wiring. Later Host/Creator Tasks declare their own affected routes.
The owner's main freeze applies to this entire linear Draft stack; no merge,
release, deployment, promotion or cleanup until applicable authorization.
