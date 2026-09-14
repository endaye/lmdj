# LMDJ Stage 12 Candidate Adoption and Lineage Design — 2026-08-31

日期：2026-08-31

2026-09-09 状态增补：C-Q1～C-Q5 确认不等于本 Candidate 草案整体批准。
候选 API 版本与 #467 K2 的边界、recipe 端点和生命周期待决项见
[R2 与 L1～L5 任务包](../plans/2026-09-09-stage12-decision-followups.md)。
本文 SDK 2.0.0 是历史提议，不能与 K2 各自重复分配同一版本。

状态：**草案，待评审**——本文是
[#471](https://github.com/endaye/lmdj/issues/471) 的设计半部：定义所有
Stage 12 智能结果共用的 Candidate → Preview → 用户选择 → Derived Asset
采纳路径与通用 Lineage 记录。实施计划按 #471 验收另行落笔，不在本文。
Lineage 的 Project 持久化位置已由 Stage 10 replay/lineage contract repair
确认：复用 `lmdj.project.v4` 的 `Asset.lineage`，见已解决的 S12L-Q1。

评审修正（2026-08-31）：Candidate 的可用性与 Job 重试关系改由独立
`JobRecord` / `CandidateIndex` 承担，terminal Attempt 保持不可变审计事实；
Discard 只写 tombstone，不删除 Attempt 证据。输出 Schema 校验移入 execution
并发生在 terminal 持久化前；采纳目标只保留明确 Pad，避免抢定仍开放的
Project Bin 模型；Lineage source 改为封闭 typed variant。

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
| S12L-Q1（已解决，2026-09-01） | Lineage 属于 Project Asset truth。Stage 10 在 `lmdj.project.v4` 增加唯一承载位 `Asset.lineage`，普通/迁移 Asset 写 `null`，resample 写首个封闭 typed variant；Stage 12 必须扩展并复用这个字段与同一 typed Lineage 模型，不得另建 Project 字段或 Workspace-only Lineage。 | #516 持久化；#431 首个写入方 |
| S12L-Q2 | Pattern 候选（`pattern.suggest`）的完整采纳细节（Merge 语义、替换当前编辑版的边界）在该 capability 的 Contract 设计内展开；本文只锁 §6.4 的四个出口与「不覆盖已录事件」。 | 后续 capability 设计 |

## 4. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S12L-D1 | CandidateSet 是成功 Attempt 输出经消费方验证后的只读视图，身份 = `{candidate_set_id, job_id, attempt_id, capability_id+version, source: {asset_id, artifact_sha256, project_revision}, candidates[]}`；每个候选携带 `CandidateId`。provider-sdk `2.0.0` 以 `AttemptResultV2.candidates: vector<Candidate>` 取代当前 singular `optional<Candidate>`，使多个候选成为显式执行结果；成功 terminal 的 `candidate_ids` 与聚合 outputs 据此产生。CandidateSet 由 Workspace 层独立 `CandidateIndex` 发布，**不写回 terminal Attempt，也永不进 Project Truth**。SDK 同时增加 `JobId` 与独立 `JobRecord {job_id, capability, ordered_attempt_ids, active_candidate_set_id?}`，明确 Attempt → Job 关系；同一 Job 的新 Attempt 成功只更新 JobRecord active pointer，并把旧 Set 在 CandidateIndex 标为 `superseded`，绝不把 terminal Attempt 改成 Superseded。 | §18；当前模型尚无 Job 关系且结果只有单 Candidate，必须显式补齐 |
| S12L-D2 | 候选两种形态：**字节候选**（候选即输出 Artifact，如 stem WAV）与 **recipe 候选**（候选是对源 Asset 的确定性派生配方，如 `lmdj.slice-points.v1` 的一个切片区间）。recipe 候选不物化字节，预览与采纳时由 Core 从源 Asset 确定性执行配方——切割真相在 Core，不在 Provider 输出。 | S12C-D2、存储成本 |
| S12L-D3 | 输出 Schema validator 由消费方模块拥有、在 capability 注册时注入 AttemptStore execution。Provider 返回后，执行路径先验证未发布 outputs，再决定并持久化 terminal Attempt，最后才允许 Artifact Store 与 CandidateIndex 发布；不存在“先成功落盘、采纳层稍后改成 Failed”的回写。成功的候选型 Attempt 必须满足 `candidate_outputs == minted_outputs`；非法输出以 `PROVIDER_FAILED` + `details.reason = output_schema_invalid` 终结，terminal v2 两组 outputs 均为空，未发布 bytes 不 mint Artifact，CandidateIndex 不产生记录。 | S12C-D9；terminal-attempt-v2 不变量 |
| S12L-D4 | Preview 是零变更操作：字节候选经普通 Runtime 试听路径播放；recipe 候选按配方对源 Asset 做只读区间试听（Stage 8 start/end 试听机制的复用）。Preview 不产生 revision、不写 Project、不触发准备以外的持久化。 | §5.2「Preview」 |
| S12L-D5 | 采纳是一个原子 Facade Command `AdoptCandidates`（带 `expected_revision`）：输入为显式清单 `[{candidate_id, target: {bank_id, pad_index}}]`。v1 只允许明确 Pad target，不提供“新 asset（不上 Pad）”；后者依赖仍开放的 Project Bin/未分配 Asset 持久化决策，本文不抢定。命令不自动选槽；多候选一次 revision 完成，按 `(bank_id, pad_index)` 稳定升序应用。配额按采纳后的每 Pad decoded float PCM bytes 预演所有受影响 Bank 与整个 generation ledger；相同 Artifact 到多个 Pad 分别计 residency，不能按 content hash 去重。任何变更前按既有 binding-constraint 规则判 `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED`——all-or-nothing，任一失败整体拒绝且零变更。源 Asset 与未采纳候选不受影响。 | §5.2「用户选择」、D1 配额与 2026-08-28 记账修正；Project Bin 问题仍开放 |
| S12L-D6 | 通用 Lineage 记录使用封闭 typed source variant：`source = {kind: asset_artifact, artifact_sha256, asset_id?, project_revision}` 或 `{kind: soundset, set_id, set_version, manifest_sha256, slot_index, artifact_sha256}`；`derivation = {kind, capability_id?, capability_version?, provider_id?, provider_version?, model_identity?, parameters_sha256?, job_id?, attempt_id?, range?, performance_id?}`。derivation `kind` v1：`capability_adoption`、`resample`、`trim`、`copy`、`soundset_install`。每个 variant 的必填字段由 Contract 条件约束，禁止只有自由文本 `kind`。#431 的字段映射到 `asset_artifact` source、`range`、`performance_id`；S11-D9 精确映射到 `soundset` source。记录不含挂钟时间戳。 | P10-D11 超集义务；Sound Set 与能力采纳只能有一个 Lineage Contract |
| S12L-D7 | 生命周期：Discard 是显式操作，只在 CandidateIndex 写 `discarded` tombstone；Supersede 同理只改变 index 可用性。两者都不得改写或删除 terminal Attempt、JobRecord 的 attempt 历史、minted/candidate output refs、provider/request/error 证据。Host 重启按 JobRecord + CandidateIndex 重建视图；若可用候选的 bytes 不可取，返回 `NOT_FOUND` + `details.reason = candidate_unavailable`，不损坏 Project、不半可见。Artifact bytes 的保留/GC 随 S8-D5 另行设计；Discard 本身绝不触发 GC。 | §18.1、S8-D5；审计事实与 UI 可用性分离 |
| S12L-D8 | 失败矩阵（全部零 Project 变更）：Provider 失败/超时（§18.1 原文）；源 Asset 已不存在 → `NOT_FOUND` + `details.reason = source_asset_missing`；`expected_revision` 不符 → `REVISION_CONFLICT`；候选已 superseded/discarded 或 bytes 不可取 → `NOT_FOUND` + `details.reason = candidate_unavailable`；配额超限 → `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED`；recipe 越界 → `INVALID_ARGUMENT` + `details.reason = candidate_recipe_invalid`。`details.reason` 是稳定 lowercase token；不新增公共 error code。 | §18.1 与当前封闭 Error Contract |
| S12L-D9 | Pattern 候选走同一 CandidateSet 身份与 Preview 语义，commit 出口是 §6.4 的四个（新 Pattern Slot / Merge / 替换当前编辑版 / Discard），经 Pattern 命令而非 Asset 命令；「不得覆盖用户已录入演奏事件”是命令级不变量。细节按 S12L-Q2 延后。 | §6.4 |

## 5. Contract 影响

- CandidateSet 仍不进 Project Truth；不改 `lmdj.capability.v2`。
- Lineage 必须复用 `lmdj.project.v4` 已有的 `Asset.lineage` 承载位与 typed
  model。若 Stage 12 新 source/derivation variants 需要扩展封闭 union，实施计划
  可分配后继 Project Contract 版本，但只能扩展该字段，不能增加第二个字段或
  第二套 Lineage model。
- 复用：`lmdj.error.v1` 现有 code；本文只新增稳定 lowercase
  `details.reason`：`candidate_unavailable`、`source_asset_missing`、
  `candidate_recipe_invalid`、`output_schema_invalid`。

## 6. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. 候选可见性：坏输出在 terminal 持久化前被 execution 中的消费方 validator
   拦下，Attempt 首次即以 `Failed` 写入，无 CandidateIndex 记录；成功路径
   断言 `candidate_outputs == minted_outputs`。
2. Preview 零变更：字节/recipe 两形态预览后 revision、Project、Asset
   逐项不变。
3. 采纳原子性：多候选按每 Pad prepared bytes 预演 Bank/generation ledger，
   重复 Artifact 多 Pad 分别计量；任一失败整体零变更；成功恰一次 revision、
   slot 升序、Lineage 逐字段齐全。
4. 永不自动：无显式 target 的采纳请求是 `INVALID_ARGUMENT`。
5. 生命周期：Job 多 Attempt 的 active pointer、Supersede/Discard tombstone、
   重启重建/bytes 缺失逐条；terminal Attempt 与 Job 历史逐 byte 不变。
6. 失败矩阵逐行（S12L-D8）。
7. Lineage 超集：`resample` kind 的记录与 #431 落地字段一一映射。

## 7. Version Management

Version impact: none——本文只是设计文档。实施计划必须分配：
`application-facade`（AdoptCandidates）与 provider-sdk（候选证据语义化）
的 SemVer（含 `JobId`/JobRecord/CandidateIndex，跟随 #467 的 provider-sdk
`2.0.0` 实施序列）、仅在扩展 `Asset.lineage` 封闭 variant union 时可能需要的
后继 Project Contract 版本；不得为 Lineage 分配新 Project 字段。Product 整合与 #436
串行，实现自身串行在 #431 与 #427 之后。

## 8. Documentation Impact

Documentation impact: none——本次只修订 retained 设计文档，不改变当前
Portal 真相。实施时 Facade、Provider SDK、Project Contract 的 Portal 路由
由实施计划按实际身份变更声明。

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

### 9.7 Discard 时删除 Candidate 或 Attempt 证据

拒绝。Discard 是用户可见性选择，不是审计擦除授权；它只写 CandidateIndex
tombstone。Artifact bytes 的长期保留由未来 GC policy 独立裁决。

### 9.8 v1 采纳为不上 Pad 的新 Asset

拒绝。该目标要求先回答 Project Bin/未分配 Asset 的权威持久化模型；开放问题
解决前，v1 只接受明确 Bank/Pad target。

## 10. 实施入口（前置条件）

1. #516 与 #431 合入，提供 `Asset.lineage` 持久化与首个 resample 写入方；
   S12L-Q1 已解决，不再等待位置决策。
2. #467 的 `sample.slice.v1` 与输出 Schema 定稿（recipe 候选的第一个
   生产方）。
3. 本文评审通过后落笔实施计划：候选存储语义化、AdoptCandidates、Lineage
   持久化、配额整合、Host/Creator 集成逐项拆 Issue，逐 Task 声明 Version
   与 Documentation impact；实现串行在 #427/#431 之后。
