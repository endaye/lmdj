---
id: shared-temporary-staging-ownership
area: ci-release
status: open
recurrences:
  - date: 2026-10-11
    occurrence: https://github.com/endaye/lmdj/issues/1958
    observed_by: Codex coordinator and Orca Codex worker ctx_c0982cb189dc
exit: none
---

# An isolated Git worktree can still share an unwritable OS temporary staging directory with another owner.

## Why

During the S4 implementation for the linked Pattern-switch decision, the
unchanged `authoring_history` fixture placed its bundle directly under `/tmp`.
Sample import stages under the bundle parent's `.lmdj-host/sample-staging`.
That existing directory belonged to UID 0 with mode 0755; the worker ran as
UID 1000. The ordered diagnostic exposed `storage directory could not be
created` with `Permission denied`, rather than a Pattern-switch defect.

The original test binary failed again in the shared directory and passed in a
fresh worker-owned temporary parent. Source, binary and linked-library hashes
were unchanged. The complete official Ubuntu lane then passed under that
child environment. Initial Ubuntu and ASAN failures remain part of the S4
verification record; a reduced diagnostic never replaces the owning lane.

## How to apply

When a filesystem assertion fails, expose the exact returned error and inspect
the actual fixture parent, staging path, owner, permissions and symlink state.
Compare the original binary and library identities before and after the
diagnostic. Distinguish an external ownership failure from a product defect.

If those facts establish shared-directory interference, give the owned proof
process a fresh private temporary parent through child-only `TMPDIR`, `TMP`
and `TEMP`. Keep the original failure evidence and rerun the complete original
lane with unchanged selection, thresholds and timeouts. Do not chmod, remove
or take over another owner's shared directory; do not use a changed temporary
path as a generic substitute for causal diagnosis.

This first recurrence remains open with `exit: none`: a product regression
cannot determine a particular operator host's external staging ownership, and
no dedicated ownership workflow or gate has been introduced. A second
recurrence requires the mechanism or escalation specified by the pitfall
policy.
