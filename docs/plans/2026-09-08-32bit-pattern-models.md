# Reproducible Pattern claim and reclamation models

## Scope

Preserve two pending design arguments as independently runnable SC experiments:
claim CAS interference with/without admission, and audio-owned cancellation
versus activation/reclamation. No Core implementation or new concurrency policy.

Declared files: this plan, `demos/README.md`, and
`demos/32bit-pattern-mailbox/{model.py,README.md}`.

## Verification

- Enumerate bounded interleavings; assert both race winners and safe reuse are
  reachable. Reject the deliberately broken early-reclamation implementation.
- Compare admission/no-admission under identical control replacement attempts.
- Run demo index consumer and active-tree checks; stage exact files and run
  tracked-path ownership validation. No new required gate or CI lane.

## Version Management

Version impact: none
Reason: standalone models, not product source, API, ABI or manifests.

## Documentation Impact

Documentation impact: none
Reason: research-only demo and index; no changed current product support claims
or documentation-site pages.

## Completion boundary

This closes reproducibility of these bounded experiments only. Full mailbox
composition, authority/timing, C++/target progress and original ESP32 A→B1
probe evidence remain unproven. Preserve the existing draft and failure logs.
