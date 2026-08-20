# Serialized Integration Queue rollout acceptance

Date: 2026-08-21

## Scope

This documentation-only change is the first authorized end-to-end acceptance
probe for the repository-owned Integration Queue. It changes no Product Build,
Module, Provider, Host, Contract, runtime behavior, release state, or queue/CI
control-plane file.

## Completed preflight

The default-branch `Merge Queue` workflow returned a numeric
`workflow_run_id` for all three no-mutation dispatches:

| Run | Queue item start (UTC) | Queue item completion (UTC) | Result |
| --- | --- | --- | --- |
| `32429732791` | `2026-08-20T23:42:15Z` | `2026-08-20T23:43:49Z` | success |
| `32429734894` | `2026-08-20T23:43:52Z` | `2026-08-20T23:45:27Z` | success |
| `32429736955` | `2026-08-20T23:45:30Z` | `2026-08-20T23:47:06Z` | success |

The first item ran while the other two remained pending. Each successor began
only after its predecessor completed, so the live repository retained both
pending runs and honored the platform FIFO start order under `queue: max`.

The enabled authorization label is exactly:

- name: `merge:queue`
- color: `0E8A16`
- description: `Authorized for serialized full-CI squash merge`

## End-to-end acceptance condition

This exact file may reach `main` only after the probe Pull Request uses the
ordinary review and required-check path, receives an explicit `merge:queue`
label, and the controller then:

1. binds the PR, actor, current base SHA, synchronized head SHA, and numeric
   validation run ID;
2. obtains a closed full manifest and successful same-run `PR Gate`;
3. squash-merges the exact validated head without bypassing branch protection;
4. removes the authorization label and leaves the resulting `main` push run
   observable.

The Pull Request, queue run, validation run, runner assignments, merge SHA, and
resulting main run are live GitHub evidence. They cannot truthfully be embedded
in this pre-merge payload and must be reported separately after reconciliation.

## Evidence boundaries

Passing this probe enables daily queue use only. It does not establish
exact-main full release evidence and authorizes no tag, Release, deployment,
publication, Channel promotion, branch-protection change, or Product Build
snapshot.
