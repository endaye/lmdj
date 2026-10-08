# LMDJ `2.0.87.0` Canary Release Intent

This record binds one releasable Product intent for the verified P1 integration candidate delivered by [PR #1848](https://github.com/endaye/lmdj/pull/1848). The release target remains its exact protected-main squash. It carries the existing immutable Build 2.0.87.0 Portal snapshot; this Task does not allocate a Build or change that snapshot.

| Field | Value |
| --- | --- |
| Tag | `lmdj-v2.0.87.0` |
| Kind / identity | `product` / `2.0.87.0` |
| Publication Channel / profile | `canary` / `web-hosts` |
| Target revision | `5abc52106728f463768210eb4186777a0b44ad7f` |
| Immutable snapshot | `2.0.87.0` |
| Full candidate executor | [37676506324](https://github.com/endaye/lmdj/actions/runs/37676506324) |
| Executor control revision | `f095c098ffee24ee141bc7c0c8310aa43d14824e` |
| Executor event / attempt | `schedule` / `1` |
| Candidate request | `p1-release-build87-5abc-20261007-r2` |
| Current policy SHA-256 | `85143e3cb4a1592927a87a35261b4212712990435a9744d2629bc431ea2bfc08` |
| Origin run / attempt | `37673669694` / `1` |
| Durable admission run / attempt | `37676506324` / `1` |
| Canonical batch reference SHA-256 | `61351e67c0490a679a1638d399a264beb4ea20b7618b64fa29c84aad4bdb17eb` |
| Full evidence SHA-256 | `a2b6cea511384e922a900cd06aab26da610e1c4241b864c1520433f6b4d669ad` |
| Frozen changelog SHA-256 | `72afc0fd481ba45add6af33940b190bcd852313d62c0891447b77be91c8b21be` |
| Rendered notes SHA-256 | `f5e990dadfe081926cd5b3abf9580f2e933322182ecb6096bff04d6b8e630fd5` |

## Exact candidate verification

The canonical batch consumer independently authenticated the original origin and durable-admission controller artifacts, the complete verdict/execution/needs bundle, actual API jobs, main ancestry, distinct control and target revisions, and current/frozen/executor policy agreement. All 16 selected suites passed with no verification debt:

`chameleon_lab`, `ci_contract`, `core_asan`, `core_coverage`, `core_macos`, `core_release_stress`, `core_tsan_stress`, `core_ubuntu`, `creator`, `deploy_contract`, `docs_static`, `package`, `portal`, `web_runtime_host`, `web_runtime_lab`, `web_toolchain`.

The origin was a manual `workflow_dispatch`; the actual admitted executor event was `schedule`. The reference records that authenticated executor event, without deriving it from the candidate request kind. Its original origin and admission record digests are `17f8ac711c2d4256eb7f4ae73661bf1c5b9318acf711aa446e4c907ab293d76a` and `cc87d3605c8d6dcd1b8c8a12ce60c7174ad74baed63a1210f4e1f7f8b104b034`.

## Historical verification and recovery

The original R1 source [37576667995/1](https://github.com/endaye/lmdj/actions/runs/37576667995) passed all 16 suites under policy `3f9acee824ea61b858eaae7ed2e487d4991d9b6be2a052324127f805f061b16b`, with control `1eda56d365a7ace574c169351e6afd16e846d8be`, event `workflow_dispatch`, canonical reference SHA-256 `2d1594b9d9ddeefc5971c8b8f74469a6a04f21ea051740534ac01064b7ff0405`, and evidence SHA-256 `38f466b5d776290246e92754b65d718c411f73ce048fc38826bc3e3820e740ab`. It remains a historical pass. After PR #1858 changed the prospective policy, a fresh audit refused that older reference for new release qualification; it is not mixed into R2's current-policy source.

[#1864](https://github.com/endaye/lmdj/issues/1864) retains the negative admission evidence and authenticated fixed-journal recovery. [PR #1867](https://github.com/endaye/lmdj/pull/1867) added bounded, secret-safe diagnostics; [PR #1872](https://github.com/endaye/lmdj/pull/1872) recovered independently confirmed transient REST GET failures within the unchanged shared wait budget. Supported same-ID reconciliation then queued and admitted R2. Those repairs changed neither this Product candidate nor the suite/signature/publication gates.

The earlier scheduler recovery run [37576127506](https://github.com/endaye/lmdj/actions/runs/37576127506) only removed the audited stranded pending intent. It did not run product tests. The initial refused dispatch [37575134715](https://github.com/endaye/lmdj/actions/runs/37575134715) remains negative admission evidence. Neither is used as a passing candidate source.

The failed local macOS Creator and Runtime proofs remain failed, with the Owner's retained-distribution release exception recorded in [#1860](https://github.com/endaye/lmdj/issues/1860) and [#1861](https://github.com/endaye/lmdj/issues/1861). The passing current-policy candidate source does not relabel those local failures. Canonical artifact, signing, protected publication, and deployment verification remain required.

## Approved publication scope and editorial

The Owner authorized release and deployment after the concrete current notes were supplied. The approved changelog accounts for all 137 commits since the independently audited published baseline `lmdj-v1.0.66.0`, with 24 entries and 79 explicit exclusions. Its rendered payload is retained in [lmdj-v2.0.87.0-canary-changelog.md](lmdj-v2.0.87.0-canary-changelog.md).

Publication uses the six signed `web-hosts` assets, followed by separate Creator and Runtime Cloudflare deployments and dev Channel promotion. This intent records no completed tag, Draft, public Release, deployment or promotion.

## Deferred manual acceptance

The Owner deferred the remaining physical browser/device/hearing acceptance into [#1851](https://github.com/endaye/lmdj/issues/1851), [#1852](https://github.com/endaye/lmdj/issues/1852), [#1853](https://github.com/endaye/lmdj/issues/1853) and [#1854](https://github.com/endaye/lmdj/issues/1854). Automated and retained partial native evidence does not prove those complete journeys. No physical acceptance or stable promotion is claimed.

## Version Management

Version impact: none. The already allocated Product Build 2.0.87.0, release target and immutable snapshot are retained. This Task adds release evidence only.

Documentation impact: required

Affected portal pages: /releases/; /releases/2.0.87.0/; /versions/2.0.87.0/. The approved notes are bound here; the observed publication and normal Git-triggered website projection follow in their own evidence Task.
