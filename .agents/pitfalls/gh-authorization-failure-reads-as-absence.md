---
id: gh-authorization-failure-reads-as-absence
area: ci-release
status: open
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/pull/748
    observed_by: claude-opus-5
exit: none
---

# `gh` reports an authorization failure as `HTTP 404: Not Found` on a run and `Could not resolve to a Repository` on a Pull Request, so losing access reads as the run or the repository having been deleted.

## Why

GitHub does not distinguish "this exists and you may not see it" from "this does
not exist"; hiding the difference is deliberate, so an unauthorized read of a
private resource is a 404. `gh` passes that through verbatim. Observed while
watching a queued Pull Request:

```
$ gh run view 34082734098 --json status
failed to get run: HTTP 404: Not Found (https://api.github.com/repos/endaye/lmdj/actions/runs/34082734098?exclude_pull_requests=true)

$ gh pr view 748 --json state
GraphQL: Could not resolve to a Repository with the name 'endaye/lmdj'. (repository)
```

Both were authorization failures. The run existed, the repository existed, and
`git fetch origin` in the same shell seconds later succeeded — because `git`
authenticates over SSH with a key while `gh` uses its own stored OAuth token, so
one can lose access while the other keeps working. That combination is what
makes the symptom misleading: the natural reading of "404 on the run I was
watching, and `git` is fine" is that the run was deleted or the validation was
wiped, which is a far more alarming conclusion than the truth and sends you
looking in the wrong place.

Neither message names authorization, neither suggests checking the account, and
`gh`'s exit status is the same as for a genuinely missing resource. Nothing in
the product code expresses any of this.

The trigger on a machine with more than one authenticated account is the active
account changing under a long-lived session — here it reverted to an account
whose token cannot see this repository, and it did so repeatedly across
concurrent sessions on the same day. But the mapping is worth knowing on a
single-account machine too: a revoked token, an expired token, an
organization-level access change or a missing scope produce the same 404 for the
same reason.

## How to apply

- When `gh` reports `HTTP 404: Not Found` on a resource you were just reading
  successfully, or `Could not resolve to a Repository`, check the account before
  concluding anything was deleted:
  ```bash
  gh auth status
  ```
  A different `Active account: true` than the one you need is the explanation.
  If the account is already correct, it is a transient API failure with the same
  wording — retry once before concluding anything. Both were observed minutes
  apart on the same Pull Request, so the message alone does not tell you which
  you have; only `gh auth status` separates them, and neither means the resource
  is gone.
- Re-assert the account **immediately before** any authorizing or mutating call
  — labelling, merging, commenting, approving — in the same command, rather than
  relying on a switch made earlier in the same shell:
  ```bash
  gh auth switch --user <account> && gh pr edit <n> --add-label "merge:queue"
  ```
  A flip between a read and the write that depends on it is worse than a failed
  write: the write can succeed against a value you read as a different identity.
- In any poll loop or monitor, give the query failure its own branch and say so.
  A loop that treats an errored query as "nothing to report" converts lost
  access into silence, and silence is indistinguishable from steady state. See
  [[pr-checks-omits-merge-ref-lanes]] for the same shape in a different query.

`exit: none`: no mechanism is eligible yet. The invariant is settled and
violation is decidable, but the check would have to run inside every agent's ad
hoc `gh` invocation, which no repository gate reaches; a wrapper that re-asserts
the account before each call is the plausible mechanism and does not exist.

## Same defect, other areas

A clean result from an instrument that could not have reported otherwise. The
same shape is recorded under three `area:` labels, none of which reaches the
others through the contract's `area:*` prior-art search:

- [`blind-search-reads-as-absence`](blind-search-reads-as-absence.md) — `core`.
  Searches, test filters, parsers, test harnesses and review tooling.
- [`audit-axis-cannot-fire`](audit-axis-cannot-fire.md) — `ci-release`. An
  audit axis pointed at a path that does not exist.
- [`gh-authorization-failure-reads-as-absence`](gh-authorization-failure-reads-as-absence.md)
  — `ci-release`. A failed authorization returning an empty list.

Whether these should be one entry is [#983](https://github.com/endaye/lmdj/issues/983).
