---
id: release-intent-target-reachability
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/pull/328
    observed_by: claude-code/fable-5
  - date: 2026-08-26
    occurrence: https://github.com/endaye/lmdj/issues/331
    observed_by: claude-code/fable-5
  - date: 2026-08-29
    occurrence: https://github.com/endaye/lmdj/pull/400
    observed_by: codex/gpt-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/issues/332
    observed_by: claude-code/opus-5
exit: gate:tests/build/release_hydrate_test.py
---

# Allocated release intents can target commits no branch or tag reaches, and long-lived runner workspaces mask it

## Why

An allocated intent in `docs/release-evidence/release-intents.json` may record
a pre-squash `target_revision` whose branch was deleted after merge, so no
advertised ref reaches it. A fresh full clone (`fetch-depth: 0`) therefore
lacks the object, and the repository-local release audit correctly reports the
intent unverifiable — but only on machines without workspace residue.
Long-lived runner `_work` checkouts accumulate objects across runs, so the
Deploy contract lane passed for weeks on established runners and failed the
first time an elastic runner with a fresh workspace picked it up (PR #328,
`lmdj-v1.0.25.0`, target `349a834f`). The failure signature depends on which
machine takes the job, not on the change under test, and the same trap awaits
any operator running `scripts/release.sh audit` from a fresh clone.

Reachability is a property of the remote, so it cannot be asserted
repo-statically and never becomes a gate of its own. What the recurrences
actually cost was ownership: hydration had no home, so every consuming workflow
copied the same inline `git fetch --no-tags origin <sha>` step and each copy
could drift. The recurrence-2 escalation
[#332](https://github.com/endaye/lmdj/issues/332) settled that question, and the
gate below asserts the settled shape rather than the remote property.

## How to apply

Hydration is `scripts/release.sh hydrate` — the stable interface's only
object-store write. Run it before `scripts/release.sh audit` on any fresh
clone; it is idempotent and prints `all release intent targets were already
present` when nothing is missing, so running it unconditionally is safe. The
audit stays read-only and never fetches on miss: an absent target is reported
as `unverifiable` with the remedy in the message.

Never re-add an inline hydrate copy to a workflow, a script, or a runbook, and
never make the audit self-heal. `tests/build/release_hydrate_test.py` fails
closed on both, and on an audit remedy naming a subcommand `release.sh` does
not accept. Rationale and the two rejected alternatives:
[`docs/prd/decisions/2026-09-06-release-intent-hydrate-subcommand.md`](../../docs/prd/decisions/2026-09-06-release-intent-hydrate-subcommand.md).
