---
id: queue-evidence-enforcement-sites
area: ci-release
status: open
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/437
    observed_by: Claude Code (Opus 5)
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: Codex (GPT-5)
exit: none
---

# The Integration Queue's evidence contract is enforced at eight independent points across three modules, so changing it in one place leaves a silent majority still enforcing the old rule.

## Why

"Queue validation requires full" read like one rule. Implementing
[`2026-08-29-focused-merge-evidence`](../../docs/prd/decisions/2026-08-29-focused-merge-evidence.md)
found it written seven times, in three modules, in four different shapes:

1. `change_scope.classify` — the `merge:queue` label added a full reason;
2. `change_scope.classify` — an empty `workflow_dispatch` added another, which
   the controller's own dispatch inherited;
3. `change_scope.queue_validation_document` — mode had to be `None` or `full`;
4. `change_scope.validate_manifest` — a queue manifest had to be full;
5. `merge_queue._validation_contract_error` — `manifest_mode != "full"`;
6. `merge_queue._validation_contract_error` — every required check had to be
   `success`, which a focused run cannot satisfy because it skips Core;
7. `github_queue_api.parse_scope_manifest_zip` — a synchronized scope had to
   be full;
8. `github_queue_api.parse_queue_validation_json` — a dispatched validation
   artifact still admitted only `None` or `full` after focused evidence shipped.

Points 1, 3, 4, 5 and 7 were found by reading. Point 6 was found by reasoning
about what a focused run publishes. **Point 2 was found only because a test
failed**, and it would have silently defeated the whole change: the controller
dispatches `ci.yml` with an empty `lanes` input, so the queue path inherited
the rule meant for an operator asking for release evidence. Five of seven
lifted and the queue would still have run full on its most common path, with
every test green.

Nothing in the code links the seven. They are not named consistently, three of
them do not mention the queue at all, and the two that share a module sit in
different functions.

## How to apply

Before changing what the queue accepts as evidence, enumerate all eight sites
above and state what each becomes; do not stop at the ones a grep for `full`
finds, because points 1, 2 and 6 do not read that way. Points 5 and 7 now share
`change_scope.MERGE_EVIDENCE_MODES`; #446 binds point 8 to the same set. The
other five remain independent.

`exit: none`: no check can decide whether seven differently-shaped conditions
express one intent, so this is not gate-eligible under
[`docs/governance/pitfall-ledger.md`](../../docs/governance/pitfall-ledger.md).
The reduction that would retire this entry is structural -- routing every
enforcement point through one predicate -- not a test. The second occurrence
opened [#447](https://github.com/endaye/lmdj/issues/447) to perform that
consolidation; keep this entry open until that Task installs the deterministic
gate and records it as the exit.
