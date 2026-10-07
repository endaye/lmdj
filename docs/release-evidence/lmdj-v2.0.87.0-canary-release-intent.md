# LMDJ `2.0.87.0` Canary Release Intent

This record proposes one releasable Product intent for the verified P1 integration candidate delivered by [PR #1848](https://github.com/endaye/lmdj/pull/1848). The release target is its exact protected-main squash. It carries the existing immutable Build 2.0.87.0 Portal snapshot; this Task does not allocate a Build or change that snapshot.

| Field | Value |
| --- | --- |
| Tag | `lmdj-v2.0.87.0` |
| Kind / identity | `product` / `2.0.87.0` |
| Publication Channel / profile | `canary` / `web-hosts` |
| Target revision | `5abc52106728f463768210eb4186777a0b44ad7f` |
| Immutable snapshot | `2.0.87.0` |
| Full candidate executor | [37576667995](https://github.com/endaye/lmdj/actions/runs/37576667995) |
| Executor control revision | `1eda56d365a7ace574c169351e6afd16e846d8be` |
| Executor event / attempt | `workflow_dispatch` / `1` |
| Candidate request | `p1-release-build87-5abc-20261007-r1` |
| Origin run / attempt | `37576667995` / `1` |
| Canonical batch reference SHA-256 | `2d1594b9d9ddeefc5971c8b8f74469a6a04f21ea051740534ac01064b7ff0405` |
| Full evidence SHA-256 | `38f466b5d776290246e92754b65d718c411f73ce048fc38826bc3e3820e740ab` |
| Frozen changelog SHA-256 | `72afc0fd481ba45add6af33940b190bcd852313d62c0891447b77be91c8b21be` |
| Rendered notes SHA-256 | `f5e990dadfe081926cd5b3abf9580f2e933322182ecb6096bff04d6b8e630fd5` |

## Exact candidate verification

The canonical batch consumer independently authenticated the original origin and durable-admission controller artifacts, the complete verdict/execution/needs bundle, actual API jobs, main ancestry, distinct control and target revisions, and current/frozen/executor policy agreement. All 16 selected suites passed with no verification debt:

`chameleon_lab`, `ci_contract`, `core_asan`, `core_coverage`, `core_macos`, `core_release_stress`, `core_tsan_stress`, `core_ubuntu`, `creator`, `deploy_contract`, `docs_static`, `package`, `portal`, `web_runtime_host`, `web_runtime_lab`, `web_toolchain`.

The scheduler recovery run [37576127506](https://github.com/endaye/lmdj/actions/runs/37576127506) only removed the audited stranded pending intent. It did not run product tests. The initial refused dispatch [37575134715](https://github.com/endaye/lmdj/actions/runs/37575134715) remains negative admission evidence. Neither is used as a passing candidate source.

## Approved publication scope and editorial

The Owner authorized release and deployment after the concrete current notes were supplied. The approved changelog accounts for all 137 commits since the independently audited published baseline `lmdj-v1.0.66.0`, with 24 entries and 79 explicit exclusions. Its rendered payload is retained in [lmdj-v2.0.87.0-canary-changelog.md](lmdj-v2.0.87.0-canary-changelog.md).

Publication uses the six signed `web-hosts` assets, followed by separate Creator and Runtime Cloudflare deployments and dev Channel promotion. This intent records no completed tag, Draft, public Release, deployment or promotion.

## Deferred manual acceptance

The Owner deferred the remaining physical browser/device/hearing acceptance into [#1851](https://github.com/endaye/lmdj/issues/1851), [#1852](https://github.com/endaye/lmdj/issues/1852), [#1853](https://github.com/endaye/lmdj/issues/1853) and [#1854](https://github.com/endaye/lmdj/issues/1854). Automated and retained partial native evidence does not prove those complete journeys. No physical acceptance or stable promotion is claimed.

## Version Management

Version impact: none. The already allocated Product Build 2.0.87.0, release target and immutable snapshot are retained. This Task adds release evidence only.

Documentation impact: required

Affected portal pages: /releases/; /releases/2.0.87.0/; /versions/2.0.87.0/. The approved notes are bound here; the observed publication and normal Git-triggered website projection follow in their own evidence Task.
