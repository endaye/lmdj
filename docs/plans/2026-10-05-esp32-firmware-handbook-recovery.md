# Recover the ESP32 firmware handbook

Base: `0050db4a4`. The user authorized processing all eight audited branches
on 2026-10-05, including shipping this retained document. The earlier
2026-09-09 plan's commit/push-only boundary describes that historical run.

## Declared files

- `docs/README.md`
- `docs/deploy/esp32-firmware.md`
- `docs/plans/2026-09-09-esp32-firmware-handbook.md` (unchanged historical plan)
- This plan.

## Scope

Recover the Chinese EIM/build/evidence/flash-recovery/audio-comparison handbook.
Retain dated research as historical evidence, verify all relative file links,
and distinguish independent experiment steps from the current stable
`scripts/cardputer-host.sh build` entrypoint and its exact SDK gate. Do not
change firmware, tooling, device state, acceptance records or release identities.
The README adds only the focused handbook entry, preserving current main.

## Verification

Verify every relative link against tracked current files and parse shell
examples with `bash -n` without executing them. Compare SDK revision and
entrypoint descriptions with the current stable script. Run staged path
ownership, diff check and `scripts/docs-site.sh check` for documented source
facts. No new tests or gates are introduced for this documentation-only change.
Before merge classify the committed range, validate the PR declarations and
selected batch-only evidence, and require current-head independent review.

## Version Management

Version impact: none — an operational handbook and index; no Product Build,
Module, Host, Contract, SDK, Assembly or release identity is allocated or changed.

## Documentation Impact

Documentation impact: none
Reason: an independent-experiment runbook under docs/deploy and its index; no
portal page, support promise, product behavior or acceptance rule is changed.

Pitfall impact: none — existing relevant documentation pitfalls were read;
this recovery observed no new process defect or recurrence.
