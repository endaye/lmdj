---
id: runner-account-check-misses-service-mounts
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-11
    occurrence: https://github.com/endaye/lmdj/actions/runs/34628173677
    observed_by: codex
exit: gate:tests/build/ci_pr_agent_install_test.py
---

# A runner-account smoke check does not exercise the service mount namespace

## Why

The PR-Agent installer checked ACLs and imported the engine using `sudo -u`.
The actual runner inherited `ProtectSystem=strict` without a writable ledger
mount. Host-shell checks succeeded while CI failed with EROFS before any model
call; the wrapped admission error looked like exhausted monetary budget.

## How to apply

Separate DAC/ACL permission from service mount policy. Reproduce the relevant
unit properties in real systemd tests, assert state writes and protected-path
refusals, and verify the live service namespace after an idle restart. Do not
treat `sudo -u`, `test -w`, a witness, or daemon-reload alone as that proof.
The installer Linux-root tests cover this boundary without provider calls;
ordinary non-root fixture runs do not claim systemd acceptance.
