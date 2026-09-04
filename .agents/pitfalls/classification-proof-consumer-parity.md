---
id: classification-proof-consumer-parity
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/600
    observed_by: grok-4.6-build
  - date: 2026-09-04
    occurrence: https://github.com/endaye/lmdj/pull/622
    observed_by: Codex (GPT-5)
  - date: 2026-09-04
    occurrence: https://github.com/endaye/lmdj/pull/628
    observed_by: Kimi Code Review
exit: gate:tests/build/ci_scope_policy_consumer_parity_test.py
---

# A producer-only classification proof is lost when downstream manifest consumers revalidate without the same independent authority.

## Why

The scope classifier proved that one policy edit preserved every merge-base
path, then kept that proof only in a local boolean. Its summary, Phase Gate,
PR Gate, and queue artifact parser all revalidated the focused manifest as if
the policy path still contributed the central-CI full rule. A full-labelled PR
hid the defect; the focused main push exposed it after merge.

## How to apply

Keep transient authority out of the manifest. Every consumer allowed to accept
a focused policy edit must independently recompute the proof from the
manifest's exact base/head revisions in a complete Git checkout. Consumers
must load both policies from those revisions and reject a policy used for lane
validation unless it exactly matches the policy stored at the head revision.
The differential never trusts a caller-supplied policy as revision evidence.
Consumers without repository authority, including queue and release readers,
must remain fail closed. The exit gate exercises every repository-backed
consumer against a preserving transition, a forged non-preserving transition,
and a caller attempt to replace the Git head policy.

The advisory local pre-flight is deliberately different: it classifies the
working tree, including uncommitted policy edits and untracked paths, and emits
no reusable authority. It must compare the working policy with the merge-base
policy through the pure classification differential. Calling the
revision-bound repository helper there makes every uncommitted policy edit
look non-preserving because the working policy cannot equal the committed HEAD
blob. Keep paired local tests: an uncommitted rule for a newly introduced path
stays focused, while an uncommitted change to an existing path's routing stays
full.
