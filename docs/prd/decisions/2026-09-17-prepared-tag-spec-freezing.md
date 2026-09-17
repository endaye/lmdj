# 已确认：`prepared` / `tag` 的 spec 是结果绑定，在 advance 内两阶段冻结

- 日期：2026-09-17。
- 关联：GitHub issue [#1404](https://github.com/endaye/lmdj/issues/1404)（本条裁决它）；
  跟踪任务 [#1301](https://github.com/endaye/lmdj/issues/1301) 的 M1；上位计划
  [`2026-09-14-release-convergence.md`](../../plans/2026-09-14-release-convergence.md)；
  登记计划 [`2026-09-16-release-entry-enrollment.md`](../../plans/2026-09-16-release-entry-enrollment.md)。
- 本条解决并删除开放问题 `docs/prd/questions/prepared-step-spec-freezing.md`。

## 结论

1. `prepared` 与 `tag` 的 closed spec 形状**保持现状**：
   [`prepared_step.validate_spec`](../../../tools/release/prepared_step.py) 与
   [`tag_step.validate_spec`](../../../tools/release/tag_step.py) 的字段集与校验一字不改。
   正式确认这两步的 spec 是**结果绑定**的：`plan_sha256` 与 `tag_object_id` 是
   `prepare()` 的产出，不是写入前的输入。
2. reviewed intent 绑定的是**输入**，不是这两个派生值。intent 账本行绑定 `tag`、
   `target_revision`、`channel`、`profile`、`snapshot`、`merged_main_run_id`、
   `evidence_paths`，加上驱动 `changelog` 步冻结进同一行的 reviewed changelog。
   `plan_sha256` / `tag_object_id` 是这些输入加上签名 tag 对象的**确定性派生见证**，
   由 journal 记录、由后续步骤按恢复绑定，不需要、也不会新增 ledger 字段。
3. `prepared` 步按「授权 spec → 驱动一次 → 结果 spec → read-back」两阶段冻结。
   `enroll_prepared` 先从 reviewed intent 行恢复写入前即可知的授权字段
   （`operation_id`、`request_sha256`、`repository_id`、`actor_id`、`tag`、
   `target_revision`），以此授权在 driver 的 `before_write` 守卫下调用一次
   `prepare(tag)`；返回后从它自己的产出读出 `plan_sha256` 与 `tag_object_id`，
   补全为完整 spec，再用现有 `prepared_step.read_back` 做读回校验。授权字段恢复不到
   就如实 `pending`，`prepare()` 抛错一律报 `unknown`，绝不重试写入。
4. `tag` 步**不需要任何新契约**。它排在 `prepared` 之后
   （[`orchestration.py:22`](../../../tools/release/orchestration.py) 的 `STEPS`），
   spec 的每个字段在它自己的步骤运行时都已存在：本地签名 tag 给出 `tag_object_id` 与
   `signer_fingerprint`，prepared 产出给出 `plan_sha256`。`enroll_tag` 直接复用既有
   `RecoveredStep` 恢复模式，与 [`enroll_draft`](../../../tools/release/carriers.py) 同构；
   恢复不到就 `pending`。
5. `scripts/release.sh run` **承诺覆盖 prepare 与 push-tag 的写入**。未 prepare 的请求
   不再永久停在 `pending`：`run` 走到 `prepared` 时自己驱动。既有
   `scripts/release.sh prepare` / `push-tag` 保留为独立可用的手动入口与恢复入口，
   语义不变——`prepare()` 自带的 reconcile 路径正是让二者可以共存的前提。
6. 不放宽任何既有校验。`prepare()` 自身的 intent 授权、`releasable` disposition、
   目标 main 祖先性、远端 tag 冲突拒绝、product proof、asset 校验、changelog 同源校验，
   以及 `tag_step` 的本地/远端一致性与签名者一致性，全部原样保留；不改
   `lmdj.release-plan.v1`。

## 原因

### 候选 1（驱动内只做验证，写入仍由手工命令承担）不满足 M1 的验收

收敛计划给 M1 写的验收是「临时 Git / fake API / 测试 signer **从真实入口走完整交付链**，
各腿验证实际产物」。若 `prepared` / `tag` 永不驱动，14 步链在假体下也走不完，M1 的
「可运行完整入口」按其自身文字不成立。这不是一键语义好不好看的问题，是验收判定问题。

### 候选 2（收窄 spec、写入前投影计划摘要）在结构上不可能

[`prepare.py:295`](../../../tools/release/prepare.py) 的 `_plan_document` 把
`"tag_object": plan.tag_object` 写进计划文档，而
[`prepare.py:164`](../../../tools/release/prepare.py) 的
`plan_sha256 = sha256(canonical_json(document))` 覆盖整份文档。`tag_object` 是
[`git_repository.py:114`](../../../tools/release/git_repository.py) 的
`git tag --sign` 产出的注解 tag 对象 id，其内容含 tagger 时间戳与 OpenPGP 签名，
**不可预先计算**。所以「干跑投影出预期计划摘要」只有先把 `tag_object` 从
`lmdj.release-plan.v1` 里拿掉才成立。

那是在削弱计划文档与签名 tag 的绑定，而 `plan_sha256` 是一路带到
`publish-release.yml` 输入的身份脊梁。为让 spec 形状「看起来是写入前冻结的」而拆掉这条
绑定，缩小的正是校验强度，不是校验数量——minimization 原则明确禁止。

### 候选 3 是仓库已经在用的模式，不是新增让步

[`carriers.py:292`](../../../tools/release/carriers.py) 的 `enroll_draft` 已经在做完全
同一件事：`draft` 的 spec 绑定 `plan_sha256`，靠
[`read_prepared_plan`](../../../tools/release/carriers.py)（`carriers.py:250`）从 prepared
产出恢复，恢复不到就 `pending`。`RecoveredStep`（`carriers.py:42`）的整个设计前提就是
「spec 的取值只有前序步骤跑完才存在」。承认 `prepared` / `tag` 的 spec 结果绑定，是把
已经生效的架构事实写明，而不是为这两步破例。

`prepared` 与 `draft` 的唯一差别是：`draft` 的前序产出由别人写，`prepared` 的前序产出
由它自己写。这正是它需要两阶段、而 `tag` 不需要的原因。

### reviewed intent 究竟绑定了什么，必须说清

`docs/release-evidence/release-intents.json` 的 42 行里没有任何计划摘要字段。这不是缺口。
`_plan_document` 的每一个输入——repository、tag、target_revision、kind、identity、profile、
channel/make_latest、snapshot、CI run 投影、changelog、assets——要么来自 policy，要么来自
这一行 reviewed intent（`intent` 与 `changelog` 两步都排在 `prepared` 之前，冻结先于消费），
要么来自对该 exact target 的构建并经 `_verify_profile_assets` 校验。唯一不由 reviewed 输入
决定的就是 `tag_object`，而它由双角色签名与 `tag_step` 的本地/远端一致性独立守卫。

因此 reviewed 授权落在**输入与签名身份**上；`plan_sha256` 是这些输入的函数，不是一个需要
被单独评审的独立事实。[`carriers.py:261`](../../../tools/release/carriers.py) 留下的
「哪个 *reviewed* 摘要授权该计划仍然开放」由本条回答：没有，也不需要有。实现 Task 同步
改写该 docstring，不把已裁决的问题留成注释。

## 影响

- 按序开两个实现 Task，`prepared` 在前、`tag` 在后；两者都登记后
  `entry_composition.ENROLLED_STEPS`（`entry_composition.py:74`）等于
  `orchestration.STEPS`，`backend.missing(STEPS)` 不再拒绝，`run` 才第一次可能走完
  14 步。这就是 M1「可运行完整入口」的判定点。
- `prepared` Task 声明文件：`tools/release/carriers.py`（新增 `enroll_prepared`，改写
  `read_prepared_plan` 的 #1404 docstring）、`tools/release/prepared_step.py`（写入前
  授权字段的校验入口）、`tools/release/entry_composition.py`、
  `tests/build/release_entry_enrollment_test.py`、
  `tests/build/release_cli_orchestration_test.py`。
- `tag` Task 声明文件：`tools/release/carriers.py`（新增 `enroll_tag`）、
  `tools/release/entry_composition.py`、同上两个测试文件。
- 最低层验证，每条钉一个事实：授权字段不可恢复（账本无该 tag 的 `releasable` intent）时
  `prepared` 报 `pending`；可恢复时在守卫下驱动一次 `prepare()` 并经 read-back 校验；
  `prepare()` 抛错时报 `unknown` 且不重试；prepared 产出缺席时 `tag` 报 `pending`；
  两步登记后假体从真实入口走完 14 步，中断后 `resume` 不重复外部写。
- 不新增 required gate；不改 driver 语义、journal 格式、orchestration policy、分支保护，
  不改 `lmdj.release-plan.v1`，不新增 ledger 字段。
- 同 Task 删除 `docs/prd/questions/prepared-step-spec-freezing.md` 并关闭 #1404。
