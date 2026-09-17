# 一键发版入口接线：handoff

Living document。本文件记录 2026-09-16 至 2026-09-17 一次连续实施的实际状态，
供下一个接管者直接继续。日期为 Asia/Shanghai。动作前请对着 live GitHub / 本地
仓库复核本文的每个状态声明；本文只记录写入当时为真的事实。

## 接管概述

- 跟踪任务：[#1301 收敛一键发版与部署](https://github.com/endaye/lmdj/issues/1301)；上位计划
  [`docs/plans/2026-09-14-release-convergence.md`](../plans/2026-09-14-release-convergence.md) 的 M1；
  本次实施计划 [`docs/plans/2026-09-16-release-entry-enrollment.md`](../plans/2026-09-16-release-entry-enrollment.md)。
- 接管范围：把 14 步 carrier 接到真实入口（`tools/release/cli.py` 的 `release_carriers()` 与
  `ReleaseDriver(...)` 构造）。
- **停止原因**：Kimi Code 7 天配额耗尽（provider 403），子 agent 无法再启动；本次在一个
  **未提交** 的本地 worktree 中途停止。恢复前先读完「未提交 WIP」一节。
- 语料状态：main 上 12/14 步已登记并合并；`release_carriers()` 在 main 上**仍返回 `()`**，
  因此 `release.sh run` / `resume` 依旧 fail-closed 拒绝任何范围（这是设计，不是缺陷）。

## 本次已合并（11 个 PR，均 squash 到 main）

| PR | 合并提交 | 切片 |
| --- | --- | --- |
| [#1414](https://github.com/endaye/lmdj/pull/1414) | `c50701cb` | `final` 步登记（observe-only） |
| [#1419](https://github.com/endaye/lmdj/pull/1419) | `9053a0be` | `intent` 步登记（自驱动写入）+ 修复 `intent.py` 批次引用与 PR 序列两处真实缺陷 |
| [#1420](https://github.com/endaye/lmdj/pull/1420) | `394394bc` | 身份一致化：intent 行为 `target_revision`/`channel`/`disposition` 的权威来源（witness merge，非 cut squash） |
| [#1421](https://github.com/endaye/lmdj/pull/1421) | `217dac24` | `changelog` 步登记（自驱动写入） |
| [#1428](https://github.com/endaye/lmdj/pull/1428) | `38b6e468` | 前置修复：Product Build 1.0.58.0 squash witness 缺失（阻塞所有新树） |
| [#1431](https://github.com/endaye/lmdj/pull/1431) | `60dcef1d` | `promotion` 步登记 + 补齐 #1384 只交付了一半的 promotion carrier |
| [#1439](https://github.com/endaye/lmdj/pull/1439) | `07a1db0c` | `candidate` 受管 adapter + **首次写出受信组装层** `tools/release/entry_gates.py` |
| [#1443](https://github.com/endaye/lmdj/pull/1443) | `b7e32313` | `publication` dispatch adapter（`RecoveredDispatch`）+ 修复 `release_dispatch_evidence_test.py` 的空洞突变 |
| [#1445](https://github.com/endaye/lmdj/pull/1445) | `4ef8f0d4` | `runtime` + `creator` deployment dispatch adapter |
| [#1447](https://github.com/endaye/lmdj/pull/1447) | `7be77e15` | `published_record`（`EvidencePrTransition`）登记 |
| [#1449](https://github.com/endaye/lmdj/pull/1449) | `637fec3f` | `verification` 步登记（observe-only，`BatchVerification`） |

新增/变更的 pitfall：`.agents/pitfalls/negative-mutation-matches-fixture-value.md`（新条目，
#1364 复发）；`squash-witness-provenance` 复发计数在 #1428 内已更新。

## main 上的当前状态

- 已登记步骤（12）：`candidate`、`verification`、`intent`、`changelog`、`draft`、
  `publication`、`published_record`、`changelog_site`、`runtime`、`creator`、`promotion`、`final`。
- 未登记步骤（2）：`prepared`、`tag` —— 被 [#1404](https://github.com/endaye/lmdj/issues/1404)
  的 spec 冻结问题阻塞，**不得在实现里自行拍板**。
- 因此 `backend.missing(STEPS)` 仍先拒绝一切 `run`/`resume`；12 个登记目前只由测试驱动。
- 撤销保护不变：`stable`、Channel、签名身份、reviewed intent 绑定、conversation/closing-relation
  保护均未放宽（#1439 的 review gate 还新增了未解决线程与 closing relation 的 conflict 判定）。

## 未提交 WIP（接管第一优先级）

- Worktree：`/Users/endaye/Projects/lmdj/.worktrees/release-entry-wiring`
- 分支：`feat/release-entry-wiring`，base `f703f9b2`（**落后当前 main，需 rebase**）
- 未推送、未提交；`git log origin/main..HEAD` 为空（本切片尚无提交）。
- 文件（`git status`）：
  - 新增未跟踪：`tools/release/entry_composition.py`（734 行，受信组装层主体）
  - 修改：`tools/release/carriers.py`、`tools/release/cli.py`、`tools/release/entry_gates.py`
  - 修改：`tests/build/release_cli_orchestration_test.py`、`tests/build/release_entry_enrollment_test.py`、
    `tests/build/release_entry_gates_test.py`
  - 未提交 diffstat：约 +323/−35（不含新文件的 734 行）
- 已实现的形状：
  - `cli.release_carriers(context, policy, request)` 改为委托 `entry_composition.compose_carriers`；
    签名从 `(context, policy)` 变为三参。
  - `compose_carriers` 组装 12 个惰性 request-bound wrapper；组装本身不驱动任何步骤、不读 batch/site。
  - `entry_gates._GATE_KINDS` 扩为 `("candidate","witness","intent","changelog","promotion","published_record")`；
    `dispatch_authority` 放宽了 `control_revision` 比对（**需复核这是否与 reviewed intent 绑定一致，
    不要无声放宽**）。
  - 两个 fail-closed seam 仍未定义（非缺陷，见下）。
- **测试状态（实测）**：
  - `python3 tests/build/release_entry_enrollment_test.py` → **107 OK**
  - `python3 tests/build/release_cli_orchestration_test.py` → **14/15，1 error**：
    `entry_composition.py:118 resolve_repository_id` 收到的是 function 而非 reader 对象
    （`'function' object has no attribute 'get'`），调用链
    `cli.py:220 release_carriers → entry_composition.py:436 compose_carriers`。
    这正是停止点：reader 注入 seam 尚未在组装层（或其测试）对齐。
- 结论：这是**接近完成但未验证**的一片，不要重写，也不要丢弃。

## 两个已知 fail-closed seam（无生产通道，非本次范围）

`entry_composition.py` 模块文档已记录，两者当前是具名拒绝而非发明：

1. reviewed changelog editorial input（`changelog_binding` 的生产来源）；
2. 只读 frozen deployment projection 组装（Host 站点身份在 GitHub Environment secrets，本地读不到）。

它们缺席时对应步骤如实 `pending`；通道落地后接线无需改动。

## 下一步（按序）

1. 在 `.worktrees/release-entry-wiring` 修掉上述 reader 注入 seam，让
   `release_cli_orchestration_test.py` 全绿（该文件新增 148 行就是本切片的真实入口驱动证据）。
2. 补「`prepared`/`tag` 未登记 → `run` 拒绝而不是半驱动」的断言；确认
   `scripts/release.sh run` 在假体下的行为与本计划「完成标准」一致（本轮未能实测该命令）。
3. rebase 到当前 main，跑 `python3 tests/build/release_entry_enrollment_test.py`、
   `release_cli_orchestration_test.py`、`ci_change_scope_test.py` 与 `scripts/docs-site.sh check`，
   按 `.agents/skills/issue-done/SKILL.md` 提交一个 Conventional Commit 并走完 PR/评审/squash。
   `entry_composition.py` 是新文件，需要 ownership/scope 预检（`ci_change_scope_test.py`）。
4. #1404 裁决后开两个实现 Task：先 `prepared` 后 `tag`；两者登记完成后
   `backend.missing(STEPS)` 才不再拒绝，`run` 才可能走完 14 步。
5. 之后才是上位计划 M2（真实执行载体、工具链、凭据/保护、冷启动非交互双角色签名）与
   M3（一次真实候选测试、签名发布、双站部署、doc-site changelog 与 dev 晋级）。

## 已知基础设施问题（会重复遇到）

- **PR Review publish job 的 GitHub REST primary rate limit**：`--failed` 重跑无法恢复
  （attempt-N 的 producer job 被跳过，永不产出 artifact），**只有整轮 rerun 有效**。#1421、#1428 各中一次。
- **squash witness 漂移**：为新树分配 Product Build 后若不同时生成 witness，portal provenance
  gate 会对所有更新的树 fail-closed（`squash-witness-provenance`，已复发多次）；用
  `scripts/architecture-portal.sh witness <BUILD> <cut>` 生成并 `verify-witness` 复核。
- PR body 的 `Documentation impact:` 声明由 `scripts/local-ci.sh --pr-body` 毫秒级校验；
  provenance-only 产物会被判 `required` 不成立 —— 照实写 `none` 并给理由。

## 复核命令

```bash
# 登记的 12 步与未提交 WIP
git -C /Users/endaye/Projects/lmdj log --oneline -12 origin/main
git -C /Users/endaye/Projects/lmdj/.worktrees/release-entry-wiring status --short

# 本切片测试（在 WIP worktree 内）
python3 tests/build/release_entry_enrollment_test.py
python3 tests/build/release_cli_orchestration_test.py

# 主仓库
git -C /Users/endaye/Projects/lmdj status
gh issue view 1301
gh issue view 1404
```

## Version Management

Version impact: none

Reason: 本文件是交接记录，不改变 Product、Assembly、Module、Host、Provider、Contract 身份，
不分配版本或快照。

## Documentation Impact

Documentation impact: none

Reason: `docs/handoffs/` 不是 Portal 页面，不改变当前命令、workflow、配置或 Portal 源码事实。
