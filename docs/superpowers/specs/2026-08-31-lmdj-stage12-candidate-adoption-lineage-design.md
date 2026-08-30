# LMDJ Stage 12 Candidate Adoption and Lineage Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是
[#471](https://github.com/endaye/lmdj/issues/471) 的设计半部：定义所有
Stage 12 智能结果共用的 Candidate → Preview → 用户选择 → Derived Asset
采纳路径与通用 Lineage 记录。实施计划按 #471 验收另行落笔，不在本文。
Lineage 的 Project 持久化位置与 Stage 10 Task 5（#431）对齐，见 S12L-Q1。

关联 Issue：[#472](https://github.com/endaye/lmdj/issues/472)（umbrella）、
[#471](https://github.com/endaye/lmdj/issues/471)、
[#467](https://github.com/endaye/lmdj/issues/467)（候选的生产方）、
[#431](https://github.com/endaye/lmdj/issues/431)（首个 Lineage 实例）、
[#341](https://github.com/endaye/lmdj/issues/341)（配额）。

## 1. 结论

规格 §18 的事务管线（Command Validation → Job/Attempt → Candidate
Artifact → Preview → User Commit → Atomic Project Revision）是本文的
唯一框架：Stage 12 只是给这条已定管线补上「Candidate 长什么样、住在哪、
怎么预览、怎么一次性 commit、Lineage 记什么」的缺失定义。不存在第二条
智能结果进入 Pad 的路径。

成功命题：

> 任何分析结果都不能在没有显式用户选择结果、显式用户选择目标的情况下
> 触碰任何 Pad；源 Asset 永远原样保留；采纳恰好是一次原子 revision；
> 每个 Derived Asset 都能从 Lineage 无歧义地回答「从哪来、被谁、以何
> 参数派生」。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 规格 §5.2 | 派生规则全文：Candidate → Preview → 用户选择结果 → 用户选择目标 Pad → 独立 Derived Asset；不得自动覆盖 Bank；原始素材保留；记录 Lineage。 |
| 规格 §6.4 | Composition Assist 候选只能存新 Pattern Slot / Merge / 替换当前编辑版 / Discard，不得覆盖用户已录入的演奏事件。 |
| 规格 §18 / §18.1 | Attempt 状态机（含 `Superseded`）与隔离行为：Provider 超时/失败零 Project 变更。 |
| provider-sdk 现状 | AttemptStore 已区分 `minted_outputs` 与 `candidate_outputs`，已有 `CandidateId` 与 attempt 证据（provider/model 身份、`parameters_sha256`、输入 bindings）。候选证据在 Workspace 层已存在，缺的是采纳语义。 |
| P10-D11（#431） | Resample 的 Lineage 记源哈希 + 范围 + Performance 身份 + 录音 revision，经 D1 选区 commit 路径。这是第一个落地的 Lineage 实例，本文的通用记录必须是其超集。 |
| 2026-08-26 D1 + 2026-08-28 记账修正案 | 配额判定与 `BANK_QUOTA_EXHAUSTED` 零变更语义；选区/导入/capture commit 同路径。 |
| S8-D5 | 旧 Asset 不立即删除，Artifact GC 延后设计——候选与被替换素材的 GC 同样延后。 |
| CLAUDE.md 不变量 | Runtime Snapshot 永不持久化为 Project Truth；Provider 失败属 Attempt 状态。 |

## 3. 开放问题绑定

| ID | 问题 | 归属 |
| --- | --- | --- |
| S12L-Q1 | Lineage 记录的 Project 持久化位置：随 #431 落地形态对齐——若 Task 5 把 resample Lineage 记在 Project Truth 之外（Workspace 证据），通用记录先同址，Project 内字段（需要 v4 之后的 Project Contract 版本）作为具名后续；若记在 Project 内，本文直接复用其承载位。本文只锁记录形状（S12L-D6），不与未合入的 #431 抢定位置。 | #431 合入后回填 |
| S12L-Q2 | Pattern 候选（`pattern.suggest`）的完整采纳细节（Merge 语义、替换当前编辑版的边界）在该 capability 的 Contract 设计内展开；本文只锁 §6.4 的四个出口与「不覆盖已录事件」。 | 后续 capability 设计 |

## 4. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S12L-D1 | CandidateSet 是 Attempt 成功后的只读视图，身份 = `{job_id, attempt_id, capability_id+version, source: {asset_id, artifact_sha256, project_revision}, candidates[]}`；每个候选携带 `CandidateId`。CandidateSet 住在 Workspace 层 attempt 证据（AttemptStore 现有 `candidate_outputs` 的语义化），**永不进 Project Truth**。同一 Job 的新 Attempt 成功即把旧 CandidateSet 判 `Superseded`。 | §18、SDK 现状 |
| S12L-D2 | 候选两种形态：**字节候选**（候选即输出 Artifact，如 stem WAV）与 **recipe 候选**（候选是对源 Asset 的确定性派生配方，如 `lmdj.slice-points.v1` 的一个切片区间）。recipe 候选不物化字节，预览与采纳时由 Core 从源 Asset 确定性执行配方——切割真相在 Core，不在 Provider 输出。 | S12C-D2、存储成本 |
| S12L-D3 | 候选可见前，采纳层按该 capability 声明的输出 Schema 做字节级校验（S12C-D9 的消费方归属）：非法输出把 Attempt 判 `Failed`，用户永远看不到坏候选。 | 决策点 3 归属 |
| S12L-D4 | Preview 是零变更操作：字节候选经普通 Runtime 试听路径播放；recipe 候选按配方对源 Asset 做只读区间试听（Stage 8 start/end 试听机制的复用）。Preview 不产生 revision、不写 Project、不触发准备以外的持久化。 | §5.2「Preview」 |
| S12L-D5 | 采纳是一个原子 Facade Command `AdoptCandidates`（带 `expected_revision`）：输入为显式清单 `[{candidate_id, target: pad slot 或 新 asset（不上 Pad）}]`，目标永远用户显式给出，命令不做任何自动选槽。多候选一次 revision 完成，内部按 target slot index 升序应用；配额按全清单字节和在任何变更前判定——all-or-nothing，`BANK_QUOTA_EXHAUSTED` 或任何一项校验失败即整体拒绝且零变更。源 Asset 与未采纳候选不受影响。 | §5.2「用户选择」、D1 配额 |
| S12L-D6 | 通用 Lineage 记录（#431 记录的超集）：`{derived_asset_id, source: {artifact_sha256, asset_id?, project_revision}, derivation: {kind, capability_id?, capability_version?, provider_id?, provider_version?, model_identity?, parameters_sha256?, attempt_id?, range?, performance_id?}, }`。`kind` 词表 v1：`capability_adoption`、`resample`（#431 实例）、`trim`、`copy`、`soundset_install`（S11-D9）。#431 的四个字段分别映射到 `source.artifact_sha256`、`range`、`performance_id`、`source.project_revision`。记录不含挂钟时间戳（确定性；时间在 Attempt 证据里已有）。 | P10-D11 超集义务 |
| S12L-D7 | 生命周期：Discard 是显式操作，只删 Workspace 候选证据；`Superseded` 由新 Attempt 触发（S12L-D1）；Host 重启后 CandidateSet 从 AttemptStore 证据重建，重建不出来则该 Set 以 `CANDIDATE_UNAVAILABLE` 类型化不可用——永不损坏 Project、永不半可见。候选证据的磁盘 GC 随 S8-D5 的 Artifact GC 一并延后设计。 | §18.1、S8-D5 |
| S12L-D8 | 失败矩阵（全部零 Project 变更）：Provider 失败/超时（§18.1 原文）；采纳时源 Asset 已被删（`SOURCE_ASSET_MISSING`）；采纳时 `expected_revision` 不符（标准 revision 冲突）；候选已 `Superseded`/已 Discard（`CANDIDATE_UNAVAILABLE`）；配额超限（`BANK_QUOTA_EXHAUSTED`）；recipe 越界（源被裁剪后配方失效，类型化拒绝）。 | §18.1 |
| S12L-D9 | Pattern 候选走同一 CandidateSet 身份与 Preview 语义，commit 出口是 §6.4 的四个（新 Pattern Slot / Merge / 替换当前编辑版 / Discard），经 Pattern 命令而非 Asset 命令；「不得覆盖用户已录入演奏事件”是命令级不变量。细节按 S12L-Q2 延后。 | §6.4 |

## 5. Contract 影响

- 不改：`lmdj.project.v4`（CandidateSet 不进 Project Truth）、
  `lmdj.capability.v2`。
- Lineage 的 Project 内承载位若成立（S12L-Q1），走 v4 之后的 Project
  Contract 版本，属实施计划的 Version Management。
- 复用：`lmdj.error.v1` 惯例；新增错误 token：`CANDIDATE_UNAVAILABLE`、
  `SOURCE_ASSET_MISSING`。

## 6. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. 候选可见性：坏输出被消费方校验拦下，Attempt `Failed`，无候选可见。
2. Preview 零变更：字节/recipe 两形态预览后 revision、Project、Asset
   逐项不变。
3. 采纳原子性：多候选全清单配额预判；任一失败整体零变更；成功恰一次
   revision、slot 升序、Lineage 逐字段齐全。
4. 永不自动：无显式 target 的采纳请求是 `INVALID_ARGUMENT`。
5. 生命周期：Supersede/Discard/重启重建/重建失败逐条；源 Asset 全程不变。
6. 失败矩阵逐行（S12L-D8）。
7. Lineage 超集：`resample` kind 的记录与 #431 落地字段一一映射。

## 7. Version Management

Version impact: none——本文只是设计文档。实施计划必须分配：
`application-facade`（AdoptCandidates）与 provider-sdk（候选证据语义化）
的 SemVer、可能的 Project Contract 版本（S12L-Q1）；Product 整合与 #436
串行，实现自身串行在 #431 与 #427 之后。

## 8. Documentation Impact

Documentation impact: required——本文自身是新增 retained 设计文档；实施
时 Facade、Provider SDK、Project Contract 的 Portal 路由由实施计划声明。
本文不改当前 Portal 真相。

## 9. 拒绝的替代

### 9.1 候选进 Project Truth

拒绝。候选是可丢弃派生物；进真相会把 Provider 输出变成用户创作意图，
且使 `Superseded`/Discard 需要 revision。

### 9.2 自动把切片/分离结果铺满 Bank

拒绝。规格 §5.2 明令禁止自动覆盖；目标永远显式。

### 9.3 每个候选一次 revision 的逐个采纳

拒绝作为默认。一次分离产生 4 个 stem 的采纳要么全成要么全不成；逐个
可见的中间态使配额与撤销语义不可归因。单候选采纳是清单长度为 1 的特例。

### 9.4 第二套 Lineage 模型（与 resample 并行）

拒绝。#431 是第一个实例，本文是其泛化；两套记录会让「从哪来」有两个答案。

### 9.5 Provider 直接执行采纳（省去用户选择）

拒绝。规格 §24.4 已否决 Agent 直改 Project；写入必须经结构化 Command。

### 9.6 Lineage 记挂钟时间

拒绝。破坏 Project 确定性；时间属于 Attempt 证据。

## 10. 实施入口（前置条件）

1. #431 合入，S12L-Q1 回填持久化位置，本文按需勘误。
2. #467 的 `sample.slice.v1` 与输出 Schema 定稿（recipe 候选的第一个
   生产方）。
3. 本文评审通过后落笔实施计划：候选存储语义化、AdoptCandidates、Lineage
   持久化、配额整合、Host/Creator 集成逐项拆 Issue，逐 Task 声明 Version
   与 Documentation impact；实现串行在 #427/#431 之后。
