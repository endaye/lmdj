# 真实入口接线：14 步 carrier 与 managed adapter

日期：2026-09-16

状态：待实现。本 Task 只声明范围与验证，不改动产品代码。

跟踪任务：[一键发版与部署 #1301](https://github.com/endaye/lmdj/issues/1301)。
上位计划：[`2026-09-14-release-convergence.md`](2026-09-14-release-convergence.md) 的 M1。

## 已核实的前置事实

- 14 步定义在 `tools/release/orchestration.py` 的 `STEPS`；每步的执行载体或受管 adapter 模块都已合入
  （candidate #1343、verification #1344、intent #1350、changelog #1374、prepared #1376、tag #1380、
  draft #1382、publication+promotion #1384、changelog_site+final #1392）。
- 真实入口两处都未接线：`tools/release/cli.py:426` 构造 `ReleaseDriver(...)` 时没有传
  `candidate=` / `publication_pr=` / `dispatches=`，且 `release_carriers()`（`cli.py:209`）返回 `()`。
  由于 `backend.missing(STEPS)` 先行拒绝，`scripts/release.sh run` 目前对任何范围都拒绝执行，
  因此接线前不存在半驱动风险。
- 各步 spec 的取值只有前序步骤跑完才存在，故 carrier 必须在自己的步骤运行时惰性恢复 spec：
  candidate 步把 `product_build` / `snapshot_sha256` / `head_sha` / `tree_sha` 持久化在
  `<candidate root>/candidate-transition.json` 的 `scope.cut_spec`；`plan_sha256` / `tag_object_id`
  来自 prepare 输出；`changelog_sha256` / `notes_sha256` 来自 intent 与 changelog 步；`target_revision`
  / `channel` / `disposition` 来自 `context.ledger` 的 intent 行；`release_id` 由发布记录与 GitHub
  Release 两侧交叉确认。`mode` 为 `new` 时 candidate 步之前不存在 tag。
- backend 契约需要 `.step`、`.observe`、`.execute`（写操作由该步驱动时另需 `.advance`）。
  包装层若无条件定义 `advance`，`orchestration_driver._backend_advance` 会让 driver 对每一步都走
  advanced 路径，绕过 managed 分支——因此只有真正驱动写操作的步骤可以暴露 `advance`。

## 范围

一个 Task 一次可审查提交，按依赖分组拆分；每组独立可审、可回滚，且 `release_carriers()` 只在其
全部步骤就绪后才不再拒绝：

1. **恢复层 + 包装**：`tools/release/carriers.py` 新增「按 state 恢复 spec 并委托」的载体包装
   （恢复不到报 `pending`，不伪造 `absent`/`verified`），复用 `ChangelogCarrier._recovered_spec()`
   的既有模式。
2. **只读步骤**：`changelog_site`、`final` 接线（复用 #1392 的载体与既有 site fetch）。
3. **可驱动步骤**：`intent`、`changelog`、`draft`、`promotion`（`prepared` 与 `tag` 的 spec 绑定其
   自身产出，写入前不可冻结，曾在 [#1404](https://github.com/endaye/lmdj/issues/1404) 待裁决；
   已由 [`2026-09-17-prepared-tag-spec-freezing.md`](../prd/decisions/2026-09-17-prepared-tag-spec-freezing.md)
   裁决为结果绑定、在 advance 内两阶段冻结，两步各自作为独立实现 Task 登记）。
4. **受管 adapter**：`candidate`（`CandidateTransition`）、`publication` / `runtime` / `creator`
   （每步一个 `DispatchTransition`）、`published_record`（`EvidencePrTransition`）。
5. **verification**：接入既有 `BatchVerification`。

声明文件：`tools/release/carriers.py`（新增）、`tools/release/cli.py`、
`tests/build/release_entry_enrollment_test.py`（新增）、必要时为上述测试补 `CMakeLists.txt` 注册；
实现完成时同 Task 更新 `apps/docs-site/docs/operations/version-and-release.mdx`。

### 组装载体之外还缺受信组装层（实现时核实）

登记工作开始时假定只需把已有载体接到入口，核实后发现入口还缺一层从未写过的**受信组装**：
`candidate_transition.py` 是生产代码里唯一构造 PR 对象的地方，而 `authorize` / `review` /
`verify_merged` / `observe_main` 都由外部传入，当前只有测试提供过它们；`rehearsal.py` 是
tag/draft 演练，不提供这组回调。构件本身在生产路径上存在，应当复用而不是重写：

- 完整评审输入：`review_inventory.py` 已由 `github_api.py` 在生产路径收集，并提供
  `bind_eligibility` 绑定合格性；
- batch 证据与引用：`batch_evidence.py` 的 `BatchEvidenceConsumer`、`batch_reference.parse_reference`
  与 `scripts.ci.batch_runtime.decode_reference`（唯一解码入口）；
- PR/见证机制：`witness_pr.py`、`evidence_pr.py`、`candidate_pr_sequence.py` 及其 `review` /
  `verify_merged` 挂钩；
- 身份与签名：`prepare.py` 的 `create_local_tag`、`tag_signer_fingerprint`。

因此第 4/5 组的范围包含「实现并测试这层组装」，而不只是「把载体接上」；它的每一部分都必须是
可判定的、fail-closed 的，且不得放宽既有 verifier 的校验。此层与 `prepared` / `tag` 的 spec
冻结问题（[#1404](https://github.com/endaye/lmdj/issues/1404)）相互独立。

不做的：不改驱动语义、journal 格式、policy、保护规则；不新增 required gate；不预先创建 M2 凭据、
workflow 或保护配置；不合并或重写既有 verifier。

## 最低层验证与完成标准

- 新增 `tests/build/release_entry_enrollment_test.py`：证明各步在 spec 可恢复前报 `pending`、
  恢复后委托到真实载体；证明只有驱动写操作的步骤暴露 `advance`；证明某一工具步缺失时
  `run` 仍然拒绝而不是半驱动。
- 既有假体模板复用为接线证据：`tests/build/release_cli_orchestration_test.py`（真实入口驱动全部
  step）、`tests/build/release_candidate_portal_journey.py`（candidate）、
  `tests/build/release_managed_dispatch_test.py`（dispatches）。
- 交付可复制命令：`scripts/release.sh run --authority <ref>` 在测试假体下走完整 14 步，并在中断后
  `resume` 不重复外部写（沿用既有断点测试断言）。
- 完成标准对齐上位计划 M1：真实入口连到同一总控；中断恢复不重分配、不重签覆盖、不重复外部写。
  完成前不得报告 M1 达成。

## Version Management

Version impact: none

Reason: release 工具与测试接线，不改变 Product、Assembly、Module、Host、Provider、Contract 或
模型身份，不分配版本与快照。

## Documentation Impact

Documentation impact: none

Reason: 本 Task 仅声明范围，不改变当前命令、workflow、配置或 Portal 源码事实；实现 Task 必须声明
`Documentation impact: required` 并同步 `/operations/version-and-release`，因为该页当前记录的
「`release_carriers` 的全量登记仍未接通」将被改变。
