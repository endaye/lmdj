---
id: core-job-name-elastic-registration
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/587
    observed_by: claude-code/opus-5
exit: gate:tests/build/ci_benchmark_workflow_test.py
---

# A `ci-core` job whose name is absent from `core_job_names` classifies as non-core, so the elastic controller keeps admitting load under timing-sensitive Core work.

## Why

`scripts/ci/elastic_runner.py` suppresses scale-out while a `ci-core` service is
running Core work. It identifies that work by reading the listener's journal and
prefix-matching the job name against `core_job_names`, and the classifier fails
closed only on an *unreadable* name: `_current_job_is_core` returns `None` when
it cannot parse one, and the caller treats `core_job is not False` as core. A
name it parses cleanly but does not recognise returns `False` — an explicit
"not core" — so suppression is skipped.

Nothing enforces that the list stays complete. `load_config` rejects only an
empty `core_job_names` on a host with `ci-core` services, which passes forever
after the first entry. The list was written with the four formal `ci.yml` lanes
and never revisited, so `core-stress` and `core-tsan-self-hosted-probe` in
`core-nightly.yml` were unregistered from the day they were added. `core-stress`
is the nightly Release stress lane, 20 consecutive stress repetitions and the
most timing-sensitive workload in the repository; elastic services were free to
scale out beneath it. The failure is silent in both directions — the controller
logs a normal scale-out, and the affected job reports only a timing-sensitive
test that missed its budget, which reads as a flake.

This is the same host-capacity truth as
[`shared-host-runner-capacity`](shared-host-runner-capacity.md), reached through
a different mechanism: that entry covers jobs contending inside the
`lmdj-native-heavy` queue, this one covers load the controller admits from
outside it.

## How to apply

- Adding a job that names the `ci-core` role means registering a prefix of its
  GitHub display name in `core_job_names` of
  `scripts/ci/elastic-runner/contabo.json`, in the same commit. The display name
  is the job's `name:` when present and the job id otherwise, so a `name:` that
  interpolates an input must be registered by its literal prefix.
- `tests/build/ci_benchmark_workflow_test.py` enumerates every job in
  `.github/workflows` whose `runs-on` names `ci-core` and requires each to be
  registered, so this now fails the CI contract lane rather than degrading a
  host silently. Do not narrow that scan to one workflow; the trap belongs to
  the role, not to any single job.
- Do not treat a widened test budget as the remedy for a timing-sensitive Core
  job that missed its deadline on the shared host. Check first whether the job
  was admitted alongside elastic scale-out.
