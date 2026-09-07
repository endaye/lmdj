# LMDJ 主干增量批次自测实施计划

日期：2026-09-08
原始计划交付时状态：仅设计交付，当时下列实施 Task 均未执行。
这不是当前完成度清单；后续实现与真实演练见各 Task 记录。本文后续澄清仍不代表
T5 自动触发切换已完成，不能据此跳过 O1 前置验收。

依据：[同次提交的 spec](../specs/2026-09-08-lmdj-ci-incremental-batches.md)。
源码检查基线：`5eb314f52ea71c879a8a4e00f749135791c16879`，各 Task 开始前重新读取 main。
旧计划作为历史保留，不按未勾选框重复已完成的 O2 或修改保护规则。

## 1. 交付与拆分

一次有效 AI 审查产出范围 → main 更新唤醒 → 固定目标、累计变化合批
→ focused／full／none 真实结论与 issue → 跑完接续最新 main。
取消每日自动产品测试，保留显式全量、手动发布和普通 PR 乐观合入。

每 Task 在独立 worktree 创建一个 reviewable Conventional Commit。下面是文件所有权
边界；新增／改名的辅助文件须在该 Task 开始时逐项声明并验证 ownership。
T1 定义接口后，T2 和 T3 可并行，禁止共同改同一个 workflow；T4 集成，T5 最后切换。

## 2. 实施 Tasks

### T1 — 范围 schema、标签与最低规则

文件：新增 `scripts/ci/test_scope.py`、`scripts/ci/test_scope_policy.json`、
`tests/build/ci_test_scope_test.py`；既有 scope／self-test policy 和 classifier parity tests。

- 版本化提交绑定 record；有限 suite 词表，规则与 AI 并集，full 支配，none 显式允许。
- 审计文件消费者、传递依赖和文档例外，完整展开 16-suite，不能遗漏 stress。
- 真实临时 Git 测试 first-parent、squash／merge、rename、delete、revert、策略变化。
- 比较旧／新策略最低范围；输入不完整不能推断 none。

验证：新增 scope suite、`ci_change_scope_test.py`、consumer parity、`ci_self_test_test.py`；
变异用例证明删除关键高风险／消费者规则会失败。
Documentation impact: none — 未启用内部协议；Version impact: none。

### T2 — 单次有效审查、回退与可信范围 publisher

依赖 T1，可与 T3 分开开发。
文件：`.github/workflows/pr-review.yml`、现有 review backend／publisher scripts 和
对应 `tests/build/ci_*review*_test.py`；新增文件在 Task 开始时逐项声明。

- GLM → Kimi → Grok 有界回退；有效结果即停，真实代码 findings 不触发换模型。
- 同次审查输出范围；独立 publisher 校验、保存记录、贴标签，模型不获得写权限。
- 固定记录保存介质、认证与过期恢复，不能只存可变标签；新 head／旧晚到／重复发布安全。
- 三后端全失败去重开 issue，保留真实状态与接管，不增加 merge required checks。

验证：后端故障矩阵、预算、非法输出、发现不回退、head race、标签不能降级、
同 head 并集、publisher 最小权限、合入后不再次调用 AI。
Documentation impact: none — 暂不启用新调度；Version impact: none。

### T3 — 可恢复调度与验证债务

依赖 T1，与 T2 使用相同固定 schema fixtures，不改 review workflow。
文件：新增 `scripts/ci/incremental_batch.py`、`tests/build/ci_incremental_batch_test.py`，
以及开始 Task 时声明的持久化 adapter／tests。

- 首先确定一个持久化后端并写决策：认证写者、条件更新／单写者锁、请求日志、
  保留期、恢复权限。用原型证明后才接 workflow；这是实施前置，不是已完成能力。
  不把每轮进度写回 main，不创建长寿命 Git 分支，不建设常驻队列服务。
- 实现 spec 的 generation、进度、在途／pending、请求启动、结果与债务状态。
- 请求先写、响应丢失先查、执行 claim 防双跑；none 记账、bootstrap full、终态接续。
- 处理进度与健康分离；有界重试／暂停债务／显式恢复，候选不被持续合入饿死。

验证：spec 所有状态／恢复行，走完“写请求→启动→结果→进度→重新读 main”；
持久化 adapter 故障注入、并发与过期／状态丢失，不能只验证 happy path。
Documentation impact: none — 未启用内部控制逻辑；Version impact: none。

### T4 — focused 执行、报告与完整候选隔离

依赖 T1–T3；缺失 review record 仍须规则兜底。
文件：`.github/workflows/ci.yml`、`.github/workflows/self-test-report.yml`、
`scripts/ci/self_test.py`、`scripts/ci/self_test_report.py`、相关 tests；
必要的 `tools/release/ci_evidence.py` 和候选证据拒绝回归。

- 复用既有 suite job，固定 target／control／policy，不复制完整矩阵。
- 批次 selection kind 为 none／focused／full；suite 单独记录 selected／not-selected
  及实际结果／blocked，focused 不能冒充 complete。
- reporter 支持局部失败，issue 幂等／独立恢复，不让报告重试重新运行产品测试。
- full 新来源须严格认证，拒绝 focused／none／跨 SHA 拼接／过期证据。
- 保持手动精确 full，本 Task 仅手动／隔离入口，不启用第二条自动测试路径。

验证：scope／self-test／reporter／candidate tests、workflow 合约及支持版本 actionlint；
full 仍严格枚举全部 16-suite。候选入口审计按适用 release 技能，不执行发布。
Documentation impact: none — 内部兼容扩展未切换；Version impact: none。

### O1 — 受控端到端演练

依赖 T2–T4；操作不是空 commit，故障注入和远端写入遵循适用授权。

- 隔离状态、显式目标：docs-none、双 host、Contract-full、审查失败规则兜底。
- 真实观察 B 在跑→C/D/E 合入→B 终态→唯一 E 批次→进度追平。
- 完成边界合入、启动响应丢失、控制器重启、取消后债务、report replay 去重。
- focused 候选拒绝与精确 full 接受，不执行 tag、发布或部署。
- 逐行映射 spec §6，每腿保留 SHA／run／状态证据，标明模拟与真实平台部分。

退出：确定性场景通过，平台相关场景有真实证据；关键不漏测／恢复路径存在缺口时
不能启用新自动入口，mock 不冒充远端验证。

### T5 + O2 — 触发切换与现行文档

依赖 O1；记录切换窗口、旧在途批次、初始进度及回退责任。
文件：`.github/workflows/ci.yml`、既有 `.github/workflows/self-test-report.yml`、
workflow inventory tests、AGENTS／CLAUDE、相关 issue-done／issue-list skills、
测试／Git／GitHub 工作管理／门户与相关证据治理、门户 testing／release 页面和源图。

- 同一切换移除每日产品 cron 及每日未启动告警，启用 main 轻量唤醒与完成接续。
- 旧批次完成或明确取消，结果保留；状态未知 bootstrap full，不把历史失败当全绿。
- 复用 `self-test-report.yml` 作为唯一调度控制器和 reusable 执行调用者，不另建
  dispatcher workflow 或迁移 workflow ID。保留现有固定 writer／controller 身份；
  main push、整次执行完成通知、手动恢复都进入同一短写锁，重型子任务不持有该锁。
- 独立 `schedule` 的轻量控制面健康巡检为有界完成链提供恢复入口：读取已有请求、
  未处理 main 变化和报告状态，不依赖前一条 `workflow_run` 继续触发。它不是每日
  产品测试，不因日期变化运行产品测试；无未处理变化、待执行请求或显式恢复时
  不启动重型任务。
- 完成通知只唤醒应结算或接续的工作；纯报告／idle 运行完成不能无条件制造新的
  同类运行。GitHub 的 `workflow_run` 最多链接三层，不能承诺无限即时接续；巡检
  的频率与最坏接续延迟须在接线 Task 中声明，Actions 全局不可用时保留人工入口。
- 保留 PR／冲突／对话和非 strict 状态，本计划不授权修改远端保护。
- 回退停 admission，保留进度、在途结果和手动 full，不自动恢复日测或旧队列。

验证：相关完整 CI 合约回归、staged ownership、portal check；线上确认 cron 已去掉、
main 唤醒与完成接续真实发生、无变化不启动重型 run、没有发布动作。
O2 还必须保留真实“完成通知链达到平台上限 → 独立健康巡检恢复已有尾部工作 →
进度追平”的逐腿证据，以及无变化巡检不启动重型任务的证据；本地模拟不能替代
该平台恢复验收。此要求不取消前述 O1 前置条件。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/
Reason: 触发、范围和结果语义改变，current 页面与治理必须同步。
Version impact: none — CI 与文档调整不分配 Product Build。

## 3. 本次文档 Task

声明文件：新 spec、本计划、旧 spec 与旧计划顶部替代说明，共四个 Markdown。
验证：相对文件链接、spec 场景与任务依赖复核、`git diff --check`、staged 新文件
ownership suite、`scripts/architecture-portal.sh check` 和完整 staged diff。
按 issue-done 创建本地 Conventional Commit；shipping 遵循适用授权。
本 Task 不切换触发器、不改保护、不发布；文档验证不能宣称 T1–O2 已完成。

Pitfall impact: none — 已检索 CI／治理 ledger，采用现有并发、证据和验收约束；
本次无新故障发生，不将设计预防措施计作历史事故 recurrence。

## Documentation Impact

Documentation impact: none

Reason: 当前 Task 仅设计、计划与历史指针，不修改 Portal 页面、行为或身份。
切换时的 required 页面义务列在 T5，不提前声称新调度已启用。

## Version Management

Version impact: none

Reason: 不改变产品、模块、Host、Provider 或产品 Contract 版本。
内部 CI schema 在实施 Task 中版本化，不据此自动分配 Product Build 或发布。

## 4. 后续设计澄清：复用控制器与有界接续

本次澄清检查基线为 `c2932ab2fcf43f6643bbd78a160a8ec1b4eb9eaf`。既有 runtime
已固定 `self-test-report.yml` 的可信 workflow 身份、controller job 和执行源码
闭集，因此撤销原计划“新增唯一 dispatcher workflow”的文件选择，采用上面的
复用方案。这只确定后续 T5 实现边界，不重写历史 Task 为全部未执行或全部完成；
真实 O1 尚须逐项验证，当前每日入口也未因本次文档修改退役。

平台依据：[GitHub workflow_run 事件说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)。
独立巡检是对完成链深度上限的恢复机制，不是绕过有界重试、暂停债务或状态认证。

本次 Task 仅声明本计划文件；不改 workflow、runtime、权限、Portal 页面或远端
状态。按 issue-done 执行 staged ownership、缓存区 whitespace 检查及最终提交范围
docs-static；Portal check 在提交前实际执行并如实记录缺失依赖，不声称构建通过。
本地单 commit 后 HOLD shipping，等当前 none 演练窗口结束再另行授权。
本地检查：staged ownership 66 项通过、缓存区 whitespace 通过；Portal check
54 项通过、3 项因隔离 worktree 未安装依赖失败，下游校验和构建未运行。

Documentation impact: none — 本次只是实施边界澄清；现行 Portal 不提前宣布切换，
T5 的 required 页面义务保持不变。
Version impact: none — 不分配任何产品身份或发布版本。
