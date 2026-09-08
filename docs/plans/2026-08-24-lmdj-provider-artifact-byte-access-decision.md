# LMDJ Provider Artifact Byte Access Decision Plan

**Goal:** 记录 Issue [#206](https://github.com/endaye/lmdj/issues/206)（machine-task
清单 D3）的架构决策：Provider SDK 的 Artifact 字节访问（输入 resolver 与输出
访问口）落在哪一层、什么形状、什么时点。本 Task 只产出决策记录，不实现任何
接口。

**Why now.** 两个独立消费方已撞上同一面墙：首个需要解析结构化 Artifact bytes
的正式 Capability（问题文件预定的触发时点），以及确定性 Attempt 重放 Provider
（[`2026-08-19-lmdj-attempt-replay-provider.md`](2026-08-19-lmdj-attempt-replay-provider.md)
Task 0，其剩余 19 步全部阻塞在此）。Issue #206 已给出分析结论：方向是选项 A
（SDK 内 capability 门控的 `ArtifactSource`），但刻意不在首个真实消费方出现前
支付 API 变更级联；选项 C 应明确否决；选项 B 仅作重放 Provider 的临时方案。本
Task 把这一结论写入 `docs/prd/decisions/`，使问题闭环、重放计划解除阻塞。

**Architecture:** `docs/prd/`、`docs/quality/` 与相关计划文档。无 Core Module、
Facade、Contract、Provider、Host 或 Product Assembly 变更。

---

## Task 1 — 写入决策文件并删除问题文件

- [x] 新建
  `docs/prd/decisions/2026-08-24-provider-artifact-byte-access.md`，按
  `docs/prd/decisions/README.md` 模板记录：
  1. 输入侧正式接口是 provider-sdk 内与 `ArtifactSink` 对称的
     `ArtifactSource` 读取回调，仅解析本次请求显式声明的输入端口；Provider
     不获得 ambient 文件系统权限；
  2. 输出侧字节访问口同样落在 provider-sdk 层，与输入 resolver 同一次设计、
     同一次 Contract Review 落地；analysis-bench 原型的 Host 注入桥接不毕业
     （重申 decision-log 2026-08-16 条目）；
  3. Schema 验证边界不变：`ArtifactRef` 不增加 Schema provenance 字段，
     `lmdj.capability.v2` 不升级；字节级 Schema 校验属消费方与获批验证器，
     与 resolver 设计同期评审；
  4. 时序：首个必须解析结构化 Artifact bytes 的正式 Capability 实现前，以
     独立 Task 落地；provider-sdk MINOR 及依赖级联在那时支付；
  5. 永久否决选项 C（parameters 传 fixture 根路径）；
  6. 选项 B（fixture 字节嵌入 `src/provider.cpp`）获准作为重放 Provider 的
     临时方案，仅限小型 proof fixture。
- [x] 在同一个 commit 里删除
  `docs/prd/questions/provider-artifact-byte-access.md`，并在决策条目里注明
  它解决的问题（`docs/prd/decisions/README.md` 与
  `docs/prd/open-questions.md` 的约定）。

## Task 2 — 同步引用该问题的工作清单与计划

- [x] `docs/quality/2026-08-17-machine-task-todo.md`：D3 行标记决策已记录并
  链接决策文件；实现工作保持 deferred 至触发时点。
- [x] `docs/quality/2026-08-17-manual-verification-todo.md`：Decisions 表的
  D3 行标记已决并链接决策文件。
- [x] `docs/plans/2026-08-19-lmdj-attempt-replay-provider.md`
  Task 0：记录裁定结果（重放轨道按选项 B 继续 Tasks 1–4），勾掉「问题裁定后
  由裁定 Task 写决策文件并删问题文件」一项，更新指向已删除问题文件的引用。
- [x] 修复两处将成为死链的引用：
  `docs/research/2026-08-19-deepseek-harness-plugin-architecture-and-lmdj-relevance.md`
  与 `docs/plans/2026-08-19-lmdj-dsh-derived-hardening.md`。
- [x] 不改 `2026-08-20-lmdj-migrate-prd-questions-to-issues.md`：问题已闭环，
  该问题的迁移步骤自然失效，由迁移 Task 执行时按当时状态处理。

**Verification:** `scripts/architecture-portal.sh check`；全仓 grep 确认无指向
已删除问题文件的残留链接。

---

## Global Constraints

- 本 Task 只记录决策，不实现 `ArtifactSource`、不改 Contract、不改任何版本
  身份。实现是触发时点后的独立 Task。
- 不在本 Task 内顺带裁定任何其他开放问题。

## Version Management

**Version impact: none.** 仅文档变更：新增决策文件与计划、删除问题文件、更新
工作清单与引用。无 Core Module、Contract、Provider、Host、Product Assembly 或
lock 内容变更，无 `module.json` 版本移动。

## Documentation impact

**Documentation impact: none.** 变更全部在 `docs/prd/`、`docs/quality/`、
`docs/design/` 与 `docs/plans/` 与 `docs/research/` 内，不涉及 architecture-portal 路由，
也不改变任何 manifest 派生事实（先例：问题迁移计划同样声明 none）。

## Out of scope

- `ArtifactSource` 的 API 形状、校验边界与实现——属于触发时点后的独立
  Contract Review 与 Task。
- 重放 Provider 的 Tasks 1–4——属于
  [`2026-08-19-lmdj-attempt-replay-provider.md`](2026-08-19-lmdj-attempt-replay-provider.md)。
- 关闭 Issue #206：按 `docs/governance/github-work-management.md`，question
  Issue 在权威决策记录合并并链接后关闭；本 Task 的 commit message 携带
  `Closes #206`，合并即闭环。
