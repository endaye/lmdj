---
id: shared-host-runner-capacity
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: codex-gpt-5
  - date: 2026-09-04
    occurrence: https://github.com/endaye/lmdj/pull/624
    observed_by: claude-code/opus-5
exit: gate:tests/build/ci_nightly_workflow_test.py
---


<!-- exit names one gate, per the ledger's entry contract. The absorbed
mechanism is split across two files because each pins a different workflow:
`tests/build/ci_nightly_workflow_test.py` covers `core-nightly.yml` and is the
gate that repairs this entry after the 2026-09-04 recurrence, so it is the
recorded exit; `tests/build/ci_build_acceleration_test.py` continues to pin the
five admitted `ci.yml` lanes. Neither file can cover the other's workflow. -->
# Separate self-hosted runner services on one physical host do not provide independent CPU capacity.

## Why

The Contabo host exposes two baseline runner services with the same `ci-core`
role. A job-level role selector can therefore place coverage on one service and
an ordinary Core proof or package build on the sibling service. Those jobs look
independent to GitHub but compete for the same host CPU budget: main run
33290370946 timed out two unchanged 30-second coverage tests while PR #444's
Core proof occupied the sibling service. PR #444 run 33320085818 later proved
that the Architecture Portal is also a material host consumer: Portal occupied
the sibling service while ordinary Core timed out unchanged Project Store and
Sequence Journal tests at their exact 30-second budgets.

The 2026-09-04 recurrence is the same shape one workflow over. `core-nightly.yml`
placed `core-stress` and `core-tsan-self-hosted-probe` on the `ci-core` role and
in no capacity queue, so a dispatched probe started in the same second as the
release stress suite -- 04:58:05Z on `contabo-lmdj-linux` and
`contabo-lmdj-linux-02` in run 33838737018 -- and both failed. `core-stress`
carried a comment stating the literal role "queues behind other native lanes",
which described an intent the configuration did not implement. Naming a role
answers where a job runs and says nothing about what runs beside it.

That recurrence also showed the exit was narrower than `absorbed` implied.
`tests/build/ci_build_acceleration_test.py` reads `ci.yml` alone and asserts the
queue has exactly five members there, so it could never observe a workflow
outside that file. The entry was absorbed for `ci.yml` and unguarded everywhere
else, which is why a second workflow could carry the defect for as long as it
did. **A gate's file scope is the true scope of the pitfall it absorbs.**

Two failures that look like this one are not: PR #611 moved `queue-item` off
hosted runners because a job that only waits should not be billed by the
minute, which is cost rather than contention; and PR #632 fixed a golden fixture
drift whose root cause was an LFS rehydration path covering
`tests/fixtures/audio` instead of `tests/fixtures`. The shared host decided
which service showed that one first, but the defect was the narrow path. Reach
for this entry when two jobs run beside each other, not whenever two services
are involved.

## How to apply

Put every material job eligible for the shared Contabo host in the same
repository-wide capacity queue, including Architecture Portal, ordinary Core
proof and package jobs, ASan, and coverage. Retain every waiter with
`queue: max`, keep `cancel-in-progress: false`, and gate the complete admitted
job set. Do not widen product test budgets to absorb sibling-runner contention.

Every workflow, not only `ci.yml`. `core-nightly.yml` is in scope and its two
native jobs are pinned by
`tests/build/ci_nightly_workflow_test.py::test_both_native_jobs_share_the_repository_capacity_queue`.
A new workflow placing a material job on `ci-core` needs the queue block and a
gate that can see it; the `ci.yml` counter cannot.
