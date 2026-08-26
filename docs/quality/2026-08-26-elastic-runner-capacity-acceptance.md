# Elastic Runner Capacity Acceptance (issue #327)

Date: 2026-08-26. Operator: Claude Code (Fable 5), authorized by the Owner.
Scope: resource-guarded elastic capacity on the two trusted Linux hosts.
No workflow dispatch, push, Pull Request, merge, release, or deployment was
coupled to any provisioning step.

## Delivered topology

GitHub runner inventory after provisioning (`gh api
repos/endaye/lmdj/actions/runners`):

| Host | Runner | Kind | State | Roles |
| --- | --- | --- | --- | --- |
| netcup | netcup-lmdj-linux (01) | baseline | online | ci-general, ci-web-heavy |
| netcup | netcup-lmdj-linux-02 | baseline | online | ci-general, ci-web-heavy |
| netcup | netcup-lmdj-linux-03 | baseline | online | ci-general, ci-web-heavy |
| netcup | netcup-lmdj-linux-04..08 | elastic | registered, offline | ci-general, ci-web-heavy, elastic |
| Contabo | contabo-lmdj-linux (01) | baseline | online | ci-general, ci-core |
| Contabo | contabo-lmdj-linux-02 | baseline | online | ci-general, ci-core |
| Contabo | contabo-lmdj-linux-03..06 | elastic | registered, offline | ci-general, elastic |

The pre-existing runners keep their unsuffixed/`-02` names; the issue's
"runners 01-03" numbering maps onto them without deregistering a healthy
runner. Every runner has its own `lmdj-runner-NN` nologin user, its own
`/opt/actions-runner[-NN]` workspace, its own hardened unit inside
`lmdj-ci.slice`, and its own GitHub identity. No Contabo elastic runner
carries `ci-core`, `deploy`, `release`, `production`, sudo membership, or
Docker group membership; `elastic_runner.py` additionally refuses any config
that puts `ci-core` on an elastic service.

Slices are unchanged and remain the hard host boundary: netcup
`CPUQuota=1400%`, `MemoryMax=48G`; Contabo `CPUQuota=600%`, `MemoryMax=16G`.
Baseline units carry `CPUWeight=300` (drop-in plus live `set-property`),
elastic units `CPUWeight=100`, so baseline — including Contabo's ci-core —
outranks elastic under contention.

## Controller

`scripts/ci/elastic_runner.py` is installed on both hosts at
`/usr/local/lib/lmdj/elastic_runner.py` with host config at
`/etc/lmdj/elastic-runner.json` (from `scripts/ci/elastic-runner/netcup.json`
and `contabo.json`), driven by `lmdj-elastic-runner.timer` every 60 s. The
decision core is pure; `tests/build/ci_elastic_runner_test.py` (39 tests)
covers scale-out, resource refusal, cooldown, hard ceiling, idle scale-in,
busy-worker protection, malformed input, reboot baseline, ci-core-busy
suppression, projected next-job memory refusal including the no-swap netcup
profile, scale-in grace-window recheck, and heartbeat scheduling.

Contabo's operational ceiling is 4: runners 05-06 stay registered and outside
capacity consideration (the ceiling excludes them; the heartbeat still covers
them), until queueing evidence from operation at 4 supports the approved 6.

## Remote verification evidence

`scripts/ci/elastic-runner/verify.sh` on both hosts (2026-08-26, after
provisioning) showed every service with the expected user, workspace, slice,
`NoNewPrivileges=yes`, enablement (baseline `enabled`/`active`, elastic
`disabled`/`inactive`), and CPU weights 300/100 as above.

- **Manual elastic start/stop**: `netcup-lmdj-linux-08` started manually,
  reached `active` and GitHub `online`, stopped manually back to
  `inactive`/`disabled`. Return to baseline confirmed by the final inventory:
  only baseline services active on both hosts.
- **Controller dry-run**: `--dry-run` on both hosts printed a valid decision
  JSON without mutating state.
- **Heartbeat**: all nine stopped elastic services were heartbeated by the
  live controller (one per tick), each reaching listener-ready
  ("heartbeat ok ... authenticated and reached listener-ready") and recording
  `last_online_ts`; all returned to stopped. Interval is 7 days against
  GitHub's 14-day offline auto-removal.
- **Simulated registration loss**: a scratch config naming a nonexistent
  service produced `LMDJ-ELASTIC-REGISTRATION-LOSS service=... why=...
  remedy=...`, flagged the service in controller state, and the next tick
  took no retry ("no action required"). Real state files contain no losses.
- **Fail closed, observed live**: the first netcup deployment failed
  observation (slice cgroup path) and the controller preserved capacity with
  a why/remedy log line instead of acting; fixed by resolving the cgroup path
  via `systemctl show -p ControlGroup` (a dashed slice name nests under its
  parent slice).

## Defects found and fixed during acceptance

1. **Slice cgroup path**: `lmdj-ci.slice` lives at
   `/sys/fs/cgroup/lmdj.slice/lmdj-ci.slice`; the controller now resolves
   `ControlGroup` instead of assembling the path from the name.
2. **Shared cache group**: the shared caches are `root:lmdj-ci-cache` mode
   2770; freshly provisioned users were outside the group and every cache
   write their units promise would have failed. All new users were added to
   `lmdj-ci-cache` on both hosts (running `netcup-lmdj-linux-03` restarted
   while idle to pick it up), and `provision-runner.sh` now adds the group
   when it exists.
3. **ci-core suppression semantics**: suppression keyed on a bare
   `Runner.Worker` would deadlock Contabo scale-out (baselines carry both
   ci-general and ci-core, and the all-busy trigger requires them busy). The
   controller classifies the running job from the listener journal against
   declared core job names, treating an unclassifiable job as core. Issue
   #327's design section was updated accordingly.

## Accepted residual risks

- Scale-in retains the window where a job accepted between the grace recheck
  and `systemctl stop` fails with "runner lost communication" instead of
  re-queueing; the grace window plus journal recheck makes it narrow.
- Ramp latency: with no PAT the controller cannot see queue depth, so a burst
  ramps one service per cooldown (300 s), by design.
- Exit-node latency may degrade during full elastic load; both hosts remain
  Tailscale exit nodes as a documented co-tenant workload.

## Operational rollback

`systemctl disable --now lmdj-elastic-runner.timer`, then stop any active
elastic service (`systemctl stop actions.runner.endaye-lmdj.<name>.service`).
Baseline services stay enabled; nothing is deregistered. Reboot alone also
restores baseline because elastic units are disabled.
