# LMDJ Agent Orchestration 设计

日期：2026-07-20

状态：已由
[LMDJ Playable Beat Instrument 与新内核设计](2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
取代（2026-07-30）

> 本文只保留为旧 `lmdj.patch.v1` 产品路线的历史设计记录。新产品不再以
> `Patchify → patch.json` 为核心，也不继承本文的旧契约、部署和模块边界。

首期范围：Idea → playable `Patch`

关联边界：`apps/api/`、`packages/orchestration/`、`workers/generation/`、`workers/audio/`、`packages/patchify/`

## 1. 背景

LMDJ 当前已经跑通上传歌曲路径：

```text
browser upload
  → apps/api
  → workers/audio
  → pipeline / pipeline_from_stems
  → packages/patchify
  → patch.json (lmdj.patch.v1)
  → apps/web Patch View
```

下一阶段需要支持自然语言 Idea 入口，并在未来承接 Patch 内 AI Talk、Scene Variation、Render 和 Remix。这里的核心问题不是增加一个聊天机器人，而是建立一层能够：

- 理解创作目标；
- 把目标转成受控的任务图；
- 调度 Generation、Audio、Patchify 和后续 Render 能力；
- 在长任务、GPU 任务和第三方 API 失败时安全恢复；
- 保留每一步产物、版本、成本和 lineage；
- 最终交付可播放、可编辑、可解释、可回退的 Patch。

本设计把这层能力称为 **LMDJ Agent Orchestration**。

## 2. 核心判断

LMDJ 不应把底层设计成多个 Agent 自由对话的 swarm。音频生成和处理任务成本高、耗时长，并且对幂等、恢复、质量门槛和产物 lineage 有明确要求。底层应采用：

> LLM 负责理解、规划、选择和解释；确定性工作流引擎负责执行、记录和恢复；Worker 负责真正的音频计算。

因此，系统分为两个不同控制层：

1. **Agent control plane**：Intent、Creative Brief、Planning、Routing、Evaluation、用户解释。
2. **Deterministic execution plane**：DAG 状态机、队列、Worker、Artifact、重试、幂等、审批和 promotion。

Agent 可以提出计划，但不能直接修改 WAV、MIDI 或 `patch.json`；所有写操作必须落为经过 Schema 和 Policy 校验的结构化命令。

## 3. 目标与非目标

### 3.1 目标

- 支持 Idea → 多候选音乐材料 → 选择 → Audio Pipeline → Patchify → Patch View。
- 复用现有 Audio Worker、separation、pipeline-from-stems 和 Patchify，不在 Agent 层重复音频能力。
- 每次执行都有冻结的计划、明确的任务依赖、可查询状态和可恢复 checkpoint。
- 同一输入、能力版本和参数能够安全重跑，不生成重复产品对象。
- 客观质量门槛由代码执行，LLM 语义评价只能作为补充信号。
- 为后续 AI Talk、Scene Variation、Render 和 Remix 复用同一个 orchestration kernel。
- 保持 `lmdj.patch.v1` 的契约纯度和单一真相地位。

### 3.2 首期非目标

- Agent 之间自由聊天或自发组队。
- Agent 自我修改 Prompt、代码、Capability 或运行权限。
- 跨用户的全局共享记忆。
- 多用户实时协同编辑。
- 自动发布或自动对外分享。
- 完整 Render / Community / Remix 总编排。
- LLM 直接读取或写入音频二进制文件。
- 用 Agent 框架的内存状态替代持久化工作流状态。

## 4. 架构概览

```text
User: Idea / Upload / AI Talk
  → App Backend
  → Orchestration Coordinator
      → Context Builder
      → Creative Director
      → Workflow Planner
      → Plan Validator + Policy Engine
      → Durable Workflow DAG
          → Generation Worker
          → Audio Worker
          → Patchify
          → Quality Evaluators
          → Render Worker (future)
  → Artifact Store + Postgres Event Log
  → promoted patch.json
  → Patch View
```

### 4.1 部署判断

首期不单独部署 Orchestrator 服务。推荐形态：

```text
apps/api
  + packages/orchestration
  + Postgres
  + Redis/RQ-compatible queue
  + existing workers
```

`packages/orchestration` 提供纯契约、计划校验、状态转移和调度决策；`apps/api` 负责持久化、API 和启动执行。规模扩大、需要更长时间暂停/恢复或跨区域 Worker 后，可以将 durable execution 迁移到 Temporal，但不改变业务契约。

LangGraph、CrewAI 或类似框架如果被采用，只能用于 Planner 内部推理；它们不是 Workflow、Task 或 Artifact 状态的唯一真相。

## 5. 组件职责

### 5.1 Context Builder

把用户输入和允许访问的产品上下文整理为 Planner 输入：

- 当前 Session / Project / Patch 引用；
- 用户 Idea、约束和 Assist Mode；
- 用户明确提供的 reference；
- 已获授权的历史偏好；
- 当前可用 Capability、预算、设备和模型；
- 当前 Patch 或 Project 的只读摘要。

Context Builder 必须执行权限裁剪。Planner 不得看到当前用户或当前项目无权访问的聊天、音频、Patch 或组织数据。

### 5.2 Creative Director

将自然语言 Idea 转成 `lmdj.creative-brief.v1`。它描述创作意图，不描述具体 Worker 命令。

示例：

```json
{
  "schema": "lmdj.creative-brief.v1",
  "intent": "late-night broken beat performance patch",
  "bpm": {"target": 92, "tolerance": 6},
  "duration_seconds": 45,
  "mood": ["dark", "dusty", "tense"],
  "structure": ["intro", "groove", "breakdown", "drop"],
  "required_roles": ["drums", "bass", "harmony"],
  "references": [],
  "constraints": {
    "instrumental": true,
    "playable_patch": true
  }
}
```

缺失的可选字段使用系统默认值；影响创作方向或成本的关键歧义由用户确认，不允许 Planner 静默假定。

### 5.3 Workflow Planner

把 Creative Brief 编译成 `lmdj.workflow-plan.v1`：

- 从 Capability Registry 中选择能力；
- 建立 Task 依赖；
- 选择串行、并行和候选数量；
- 声明输入、输出 Schema；
- 声明超时、重试和资源需求；
- 声明需要用户审批的节点；
- 估算成本区间。

Planner 只能引用已经注册的 Capability，不能生成任意 Shell、Python、URL 或未声明工具调用。

### 5.4 Plan Validator

Plan 在执行前必须通过：

1. JSON Schema 校验；
2. Capability 存在性和版本校验；
3. DAG 无环校验；
4. 输入输出类型兼容校验；
5. 权限和数据边界校验；
6. 预算、候选数量和 GPU 时间策略校验；
7. 终点必须能产生已知产品 Artifact；
8. 不允许 Agent 绕过 Patchify 直接写 `patch.json`。

校验失败时返回结构化错误给 Planner，允许在有限次数内重规划；超过上限后向用户报告，不无限自循环。

### 5.5 Orchestration Coordinator

Coordinator 是确定性状态机，负责：

- 找出所有 `ready` Task；
- 为 Task 计算 idempotency key；
- 将 Task 投递到对应队列；
- 接收 Worker 结果和 Artifact；
- 执行重试、跳过、取消和 promotion；
- 在审批点暂停；
- 在终态生成 Workflow Summary。

Coordinator 不做音频计算，也不使用 LLM 判断某个 Task 是否已经成功。成功条件来自 Worker 的结构化结果和 Output Schema 校验。

### 5.6 Capability Registry

每个可调度能力必须注册：

```json
{
  "id": "audio.separate",
  "version": "1.0.0",
  "input_schema": "lmdj.audio-ref.v1",
  "output_schema": "lmdj.canonical-stems.v1",
  "queue": "audio-gpu",
  "determinism": "versioned",
  "timeout_seconds": 1800,
  "retry_policy": {"max_attempts": 2, "backoff": "exponential"},
  "resource_class": "gpu-high-memory",
  "estimated_cost_class": "high"
}
```

首期 Capability 建议：

```text
idea.compile_brief
music.generate_candidate
audio.normalize
audio.analyze
audio.separate
audio.extract
patch.build
patch.validate
candidate.rank
artifact.promote
```

后续增加：

```text
patch.apply_operations
scene.generate_variation
render.audio
render.share_video
lineage.fork
```

### 5.7 Worker Adapters

Orchestration 通过 adapter 调用 Worker，不能依赖 Worker 内部目录结构：

- Generation Adapter：`CreativeBrief` → generated audio/stems candidates；
- Audio Adapter：audio ref → canonical stems / pipeline package；
- Patchify Adapter：validated package → `lmdj.patch.v1`；
- Evaluation Adapter：artifact refs → structured report；
- Render Adapter：Project/Patch refs → Render artifact。

现有 `workers/audio/process_job()` 可以保留为本地同步内核。首期 adapter 负责把上层 Task 转换为其调用参数，并把 `status.json` 转译为上层 Task Event。

## 6. 逻辑 Agent

第一版只定义四种逻辑角色，不为每个角色建立独立微服务。

### 6.1 Creative Director

负责 Idea → Creative Brief，以及向用户解释系统对创作目标的理解。

### 6.2 Workflow Planner

负责 Creative Brief → 受控 Workflow Plan，不执行任务。

### 6.3 Patch Director

负责输出结构化 `PatchPlan`：

- 哪些 Element 应进入 8-pad Focus View；
- 默认 Scene 和 Pattern 选择；
- 是否需要 Scene Variation；
- Fill、Drop、Mute、FX 的意图；
- 是否缺少某个音乐角色，需要补充候选。

Patch Director 不直接修改 Patch。Patch Plan 由确定性 Patchify 或 Patch Operation Executor 执行。

### 6.4 Quality Director

汇总客观指标与语义评价：

- 技术质量；
- separation benchmark 指标；
- BPM、结构和角色完整性；
- Pad/Pattern 可演奏性；
- Patch Schema；
- Creative Brief 符合度。

客观硬门槛优先于 LLM 评价。LLM 不能把 Schema 失败、缺失音频或硬门槛失败改判为通过。

## 7. 核心契约

### 7.1 Workflow Plan

```json
{
  "schema": "lmdj.workflow-plan.v1",
  "workflow_id": "wf_123",
  "kind": "idea_to_patch",
  "input_refs": ["brief_456"],
  "budget": {
    "max_generation_candidates": 3,
    "max_model_cost_usd": 2.0,
    "max_wall_seconds": 3600
  },
  "tasks": [
    {
      "task_id": "generate_a",
      "capability": "music.generate_candidate@1.0.0",
      "depends_on": [],
      "input_refs": ["brief_456"],
      "output_schema": "lmdj.generated-audio.v1",
      "timeout_seconds": 900,
      "retry_policy": {"max_attempts": 2},
      "approval_policy": "none"
    },
    {
      "task_id": "patchify",
      "capability": "patch.build@1.0.0",
      "depends_on": ["extract"],
      "output_schema": "lmdj.patch.v1",
      "approval_policy": "none"
    }
  ]
}
```

Workflow Plan 一旦开始执行即不可原地修改。重规划必须创建新的 plan revision，并记录旧 revision 为什么被替代。

### 7.2 Task Run

Task 定义和 Task Run 分离。一次 Task 可以有多个 attempt：

```json
{
  "task_run_id": "tr_123",
  "workflow_id": "wf_123",
  "task_id": "generate_a",
  "attempt": 1,
  "state": "running",
  "idempotency_key": "sha256:...",
  "worker_id": "generation-7",
  "started_at": "2026-07-20T10:00:00Z",
  "heartbeat_at": "2026-07-20T10:01:00Z",
  "output_artifact_ids": []
}
```

### 7.3 Artifact Manifest

所有 Task 通过 Artifact 交接：

```json
{
  "schema": "lmdj.artifact-manifest.v1",
  "artifact_id": "art_123",
  "type": "canonical_stems.v1",
  "content_hash": "sha256:...",
  "storage_uri": "s3://lmdj-artifacts/...",
  "producer_task_run_id": "tr_123",
  "parent_artifact_ids": ["art_input"],
  "metadata": {
    "duration_seconds": 45.2,
    "sample_rate": 44100
  }
}
```

原则：

- 大文件存 Object Storage；
- Postgres 存 Artifact metadata、关系和引用；
- Artifact 使用内容 Hash；
- Worker 不能通过共享临时目录形成隐式依赖；
- 只有通过验证的 Artifact 才能 promotion 为产品对象。

### 7.4 Evaluation Report

```json
{
  "schema": "lmdj.evaluation-report.v1",
  "artifact_id": "art_123",
  "hard_gates": {
    "schema_valid": true,
    "audio_decodable": true,
    "required_roles_present": true
  },
  "objective_scores": {},
  "semantic_scores": {
    "brief_alignment": 0.82
  },
  "decision": "eligible"
}
```

`decision` 的硬门槛部分必须由代码计算；LLM 只产生 semantic scores 和解释文本。

## 8. 状态模型

### 8.1 Workflow 状态

```text
draft
planning
awaiting_approval
queued
running
paused
completed
completed_with_warnings
failed
cancelled
```

### 8.2 Task 状态

```text
pending
ready
dispatched
running
succeeded
failed
retry_wait
skipped
cancelled
```

状态转移必须由 Coordinator 执行并写入数据库事务。Redis/RQ 只承担投递，不是真相源。

### 8.3 Event Log

每次有意义的状态变化写入 append-only event：

```text
WorkflowCreated
BriefCompiled
PlanCompiled
PlanRejected
WorkflowApproved
TaskReady
TaskDispatched
TaskStarted
TaskHeartbeat
ArtifactProduced
TaskSucceeded
TaskFailed
RetryScheduled
CandidatePromoted
PatchPublished
WorkflowCompleted
WorkflowCancelled
```

当前状态可以由数据库快照快速查询；Event Log 用于审计、恢复、调试和用户可读历史。

## 9. Idea → Patch 首期工作流

```text
Idea
  → compile creative brief
  → validate / optional user confirmation
  → generate 2–3 low-cost candidates in parallel
  → normalize + technical preflight
  → semantic/objective evaluation
  → auto-rank or user audition
  → promote one candidate
  → separation
  → pipeline_from_stems / extraction
  → Patchify
  → Patch schema + asset validation
  → create Patch version
  → open Patch View
```

关键成本策略：先对多个候选做低成本 preflight，只允许获选候选进入昂贵的 separation 和完整 Patchify。除非用户明确要求，不对所有候选执行完整 Audio Worker。

### 9.1 候选选择

默认规则：

- 硬门槛失败的候选直接淘汰；
- 剩余候选按 objective + semantic score 排序；
- Guided 模式可以自动选择明显领先者；
- 分数接近或 Creative Brief 高歧义时请求用户试听选择；
- 被淘汰候选仍保留 lineage 和有限时长的 Artifact，按存储策略回收。

### 9.2 Promotion

Worker 产物默认是临时 Artifact。只有 promotion 后才创建正式 Project/Patch 引用。Promotion 必须是幂等事务：

1. 验证 Artifact 和 Evaluation Report；
2. 使用内容派生标识检查是否已经 promotion；
3. 创建或复用 Patch record；
4. 记录 lineage；
5. 提交产品可见状态。

## 10. AI Talk 的后续复用方式

AI Talk 不另建一套自由执行系统，而是复用相同内核：

```text
voice/text command
  → intent parser
  → PatchOperation plan
  → impact + risk analysis
  → approval policy
  → apply operations to a new Patch/Scene version
  → validate
  → before/after audition
  → accept or undo
```

默认行为：

- Scene 级创作变化生成新 Scene；
- Patch 级变化生成新 Patch version；
- 不原地破坏当前可用版本；
- 每个 AI Action 保存 intent、operation、before/after refs 和撤销入口。

Assist Mode：

- `Manual`：所有产品变更先确认；
- `Guided`：低风险操作自动执行，高风险操作确认；
- `Flow`：允许连续生成有边界的变化，但必须版本化并支持撤销。

## 11. 幂等、重试与失败恢复

### 11.1 Idempotency Key

Task 的 idempotency key 至少包含：

```text
capability id + version
input artifact hashes
normalized parameters
model/checkpoint version
seed
relevant environment lock hash
```

同 key 的已完成 Task 默认复用 Artifact。带随机性的生成任务必须显式记录 seed；用户要求重新探索时创建新的 exploration nonce，而不是绕过幂等规则。

### 11.2 重试分类

| 错误类型 | 默认行为 |
|---|---|
| 网络超时、429、临时服务不可用 | 指数退避重试 |
| Worker 进程退出、心跳超时 | 在 lease 到期后重投递 |
| 输入 Schema 错误 | 不重试，回到 Plan/输入修正 |
| 模型不支持设备 | 不静默降级；重新规划或失败 |
| Artifact 校验失败 | 不 promotion；按 policy 重跑上游 |
| 预算耗尽 | 暂停并请求用户确认 |
| 用户取消 | 停止新 Task，向可取消 Worker 发取消请求 |

### 11.3 Worker Lease 与 Heartbeat

长任务使用 lease：

- Worker 获取 Task 后写入 lease expiry；
- 周期性 heartbeat 延长 lease；
- Coordinator 只在 lease 过期后判断 Worker 丢失；
- 重投递沿用同一个 idempotency key；
- 晚到的旧 Worker 结果可以登记为 attempt artifact，但不能覆盖已 promotion 的结果。

### 11.4 部分成功

`completed_with_warnings` 只用于产品结果可用、但有非关键能力失败的情况，例如预览 render 失败但 Patch 已经合法。Patch Schema、音频缺失或核心角色硬门槛失败不能降级为 warning。

## 12. 数据模型

建议在现有产品数据模型旁增加：

```text
creative_briefs
workflows
workflow_plan_revisions
workflow_tasks
task_runs
workflow_events
artifacts
artifact_edges
evaluation_reports
approval_requests
agent_actions
model_call_usage
```

职责边界：

- `workflows`：面向用户的一次目标执行；
- `workflow_plan_revisions`：不可变计划版本；
- `workflow_tasks`：计划节点；
- `task_runs`：每次实际 attempt；
- `workflow_events`：append-only 历史；
- `artifacts` / `artifact_edges`：产物和技术 lineage；
- `patches` / `lineage_edges`：产品对象和产品 lineage；
- `model_call_usage`：模型、token、延迟和成本，不保存不必要的隐藏推理文本。

技术 Artifact lineage 与产品 Remix/Sample lineage 相关但不相同，不应共用一张表。

## 13. API 草案

```http
POST /ideas
  → 创建 Creative Brief + Workflow

GET /workflows/{workflow_id}
  → 当前状态、进度、预算和可见 Task 摘要

GET /workflows/{workflow_id}/events
  → 用户可见事件历史

POST /workflows/{workflow_id}/approve
POST /workflows/{workflow_id}/cancel

GET /workflows/{workflow_id}/candidates
POST /workflows/{workflow_id}/candidate-selection

GET /artifacts/{artifact_id}
  → metadata；文件访问使用签名 URL
```

API 不暴露任意 Task 注入接口。内部运维重试需要单独权限，并记录审计事件。

首期继续 polling；Event Log 稳定后可增加 SSE。Web 不根据未知状态自行猜测阶段，应使用后端返回的 `display_stage` 和结构化 progress。

## 14. 权限、安全与成本控制

- 每个 Workflow 固定 `owner_id`、`project_id` 和权限快照。
- Artifact、Reference、Connector 在进入 Context Builder 前完成授权。
- Worker 使用短期签名 URL，不持有用户级长期凭据。
- Capability 默认最小权限，不允许任意网络、文件或 Shell 访问。
- 第三方生成服务接收的内容需在 UI 和策略中明确。
- Prompt injection 内容作为不可信数据，不得改变 Capability、预算或权限。
- Workflow 需要候选数、模型费用、GPU 时间和总 wall time 上限。
- 超预算只能暂停或降级到预先允许的能力，不能静默继续收费。

## 15. 可观测性

每个请求贯穿：

```text
workflow_id
plan_revision
task_id
task_run_id
artifact_id
worker_id
```

基础指标：

- Workflow 成功率、取消率、平均完成时间；
- 每 Capability 成功率、重试率、超时率；
- 队列等待时间和 Worker 执行时间；
- Artifact cache 命中率；
- 每 Patch 的模型成本和 GPU 时间；
- 候选 promotion 比率；
- Quality gate 失败分布；
- 用户在候选选择和最终 Patch 上的接受率。

面向用户的 Action History 与内部 trace 分开。用户看到“生成三个候选、选择 B、完成分轨、创建 Patch”；内部保留更细的 Task 和 attempt 信息。

## 16. 测试策略

### 16.1 Contract Tests

- Creative Brief、Workflow Plan、Task Run、Artifact、Evaluation Report Schema；
- Capability 输入输出兼容；
- `lmdj.patch.v1` 保持现有 single source of truth；
- Web/CLI/API 不读取 Agent 内部输出替代 `patch.json`。

### 16.2 State Machine Tests

- 合法和非法状态转移；
- DAG ready 判定；
- 并行节点汇合；
- retry_wait 和 backoff；
- cancel、pause、approval；
- lease expiry 和晚到结果；
- Coordinator 崩溃重启后的恢复。

### 16.3 Idempotency Tests

- 同输入重投递复用相同 Artifact；
- Worker 在写 Artifact 后、回报成功前崩溃；
- promotion 请求重复提交；
- 相同文件名但不同内容不发生缓存碰撞；
- capability/model/env 版本变化使 key 变化。

### 16.4 Planner Tests

- Planner 输出只能引用 Registry 能力；
- 循环 DAG、未知工具、超预算计划被拒绝；
- Prompt injection 不能扩权；
- Planner 重规划次数有上限；
- 使用固定输入集做 plan snapshot，而不是只验证自然语言文本。

### 16.5 End-to-End Tests

- 使用 Fake Generation Worker + 现有 golden fixture 跑 Idea → Patch；
- 单个候选失败不终止其他候选；
- 全部候选失败产生可读失败结果；
- 获选候选进入真实 Audio Worker/Patchify；
- 最终 Patch 通过 Schema，并能由 `apps/web::loadPatch` 打开；
- E2E 测试不要求下载生成模型或 Demucs。

### 16.6 真实验收

使用受控 Idea 集合跑真实 Generation + Audio Worker：

- 不同 BPM、风格和结构约束；
- 至少一个第三方 API 临时失败场景；
- 至少一次进程中断和恢复；
- 对生成候选、获选材料和最终 Patch 进行盲听/可演奏性检查；
- 记录成本、总耗时和各阶段失败率。

## 17. 推荐代码边界

```text
packages/orchestration/
  lmdj_orchestration/
    contracts/
    capability_registry.py
    plan_validator.py
    state_machine.py
    policies.py
    idempotency.py
  tests/

apps/api/
  lmdj_api/
    orchestration/
      routes.py
      service.py
      repository.py
      coordinator.py

workers/generation/
  lmdj_generation_worker/
    protocol.py
    providers/
    worker.py

workers/audio/
  # 继续保持现有音频能力和依赖隔离

workers/render/
  # 后续阶段
```

不要把 orchestration contract 加入 `packages/core-models`。`core-models` 继续作为产品对象和 `lmdj.patch.v1` 的契约中枢；workflow/task/artifact 属于执行基础设施，应有独立演进边界。

## 18. 分阶段落地

### Phase O0：Contracts + Simulator

- 建立 orchestration contracts 和 Capability Registry；
- 实现 DAG 校验、状态机和内存/Fake repository；
- 使用 Fake Workers 跑通 Idea → Patch fixture；
- 不接真实 LLM，不接队列。

退出条件：相同 Workflow Plan 可重复执行、恢复并得到同一最终 Artifact 引用。

### Phase O1：Generation MVP

- 建立 `workers/generation`；
- 接一个生成 provider；
- 实现 2–3 候选、preflight、排序/人工选择；
- 获选候选接现有 Audio Worker 和 Patchify；
- Web 能轮询并打开最终 Patch。

退出条件：Idea → playable Patch 在真实浏览器闭环，失败和取消均可恢复或明确终止。

### Phase O2：Durability + Production Queue

- Postgres repository；
- Redis/RQ 队列；
- lease、heartbeat、retry、cancel；
- Artifact 进入 Object Storage；
- 成本、trace、权限和限流。

退出条件：API、Coordinator 或 Worker 中断后，无重复产品对象并能继续执行或安全失败。

### Phase O3：AI Talk + Patch Operations

- `PatchOperation` contract；
- Assist Mode policy；
- 新 Scene / Patch version；
- before/after audition、Action History 和 undo。

退出条件：AI 变化可解释、可比较、可撤销，不原地破坏已发布 Patch。

### Phase O4：Render / Share / Lineage

- Render Worker；
- share artifact promotion；
- Remix / Sample / Fork orchestration；
- 产品 lineage 与 Artifact lineage 关联。

## 19. 首期成功标准

1. 用户输入 Idea 后，系统产出合法 `lmdj.creative-brief.v1` 和冻结的 Workflow Plan。
2. Planner 不能调用 Registry 外的能力，非法或超预算计划在执行前被拒绝。
3. 系统并行生成 2–3 个候选，只对获选候选执行昂贵的完整音频链路。
4. 获选候选通过现有 Audio Worker / Patchify，最终产出通过 Schema 的 `lmdj.patch.v1`。
5. `apps/web::loadPatch` 能打开最终 Patch；消费者不读取 Workflow 或 Agent 内部数据补齐 Patch。
6. 任一 Worker 重试、超时或进程退出不会产生重复 Patch、错误 promotion 或状态丢失。
7. 用户可以看到稳定的阶段进度、失败原因、候选选择和最终 Artifact。
8. 每个最终 Patch 可以追溯到 Idea、Brief、Plan、Task Runs、输入/中间 Artifacts 和模型/能力版本。
9. 单元与 E2E 测试不依赖重量模型；真实验收单独覆盖 Generation + Audio 全链路。

## 20. 已确认建议与评审点

### 20.1 本设计建议

- 使用 Agent control plane + deterministic execution plane。
- 首期采用 Postgres-backed 薄 DAG；未来保留迁移 Temporal 的边界。
- Agent 框架不拥有 durable state。
- 第一版只做四个逻辑 Agent，不建立 Agent swarm。
- `patch.json` 保持产品侧唯一真相。
- 先低成本生成/评估多个候选，再让单个获选候选进入完整 Audio Worker。
- Agent plan、trace 和模型记录独立于产品 Patch 契约。

### 20.2 需要产品/工程评审确认

1. 首个 Generation Provider 使用第三方 API 还是自建/本地模型。
2. 默认候选数是 2 还是 3，以及免费/付费层的预算差异。
3. Guided 模式下，候选明显领先时是否允许自动 promotion。
4. Phase O1 是否先沿用本地文件 Artifact，还是直接接 Object Storage。
5. 首期队列继续使用当前线程执行器过渡，还是在 O1 同时引入 Redis/RQ。
6. Creative Brief 哪些字段需要用户确认，哪些允许系统默认。
7. 生成内容、Reference 和第三方 Provider 的授权/隐私政策。
