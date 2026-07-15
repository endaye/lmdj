# 决策记录

这里记录已经确认的产品和技术决策。没有确认的内容不要写进这里，先放到 [open-questions.md](open-questions.md)。

## 2026-07-02

### 已确认：当前处于脑暴和 PRD 快速迭代阶段

- 结论：当前仓库先服务于素材整理、工作版 PRD、开放问题和决策记录。
- 原因：已有输入包括高嘉丰 PRD 素材和 demo 工具，但它们都不是最终版本。
- 影响：文档中需要明确区分“素材”“假设”“待决”“已确认”。

### 已确认：`lmdj-song-pipeline` 是高嘉丰 demo 工具

- 结论：`lmdj-song-pipeline` 是后续可参考、可复用的 demo 工具，不是 LMDJ 最终系统架构定稿。
- 原因：该工具能证明音频到 playable patch 包的技术链路，但产品系统仍在脑暴。
- 影响：后续 PRD 可以参考它的 package contract 和运行方式，但不默认继承全部设计。

## 2026-07-06

### 已确认：`lmdj-song-pipeline` 是参考项目，不是最终代码边界

- 结论：`lmdj-song-pipeline` 是高嘉丰提供的个人参考项目和可复用技术素材库；LMDJ 可以吸收其中的功能和代码，但最终云端系统、产品对象、服务边界和 package contract 需要按 LMDJ 自己的架构定义。
- 原因：当前产品方向已经从 demo pipeline 扩展为 AI-native sampler workstation，核心对象是 `Patch / Pad / Scene / Element`，不应被参考项目的目录结构、API、CLI 或状态模型锁死。
- 影响：后续技术方案需要区分“复用 pipeline 能力”和“继承系统架构”。`Patchify` 应作为参考 pipeline 输出到 LMDJ 产品对象之间的 adapter layer；正式实现不写入 `lmdj-song-pipeline`。

## 2026-07-07

### 已确认：Patchify 进入正式源码边界重新编写

- 结论：`references/demos/lmdj-song-pipeline/` 和 `references/demos/ascii-matrix-camera/` 都只作为参考 demo；Patchify 需要作为 LMDJ-owned code 在正式目录中重新编写，第一落点是 `packages/patchify/`。
- 原因：Patchify 是产品核心能力，需要服务 Web、CLI、Audio Worker、云端 API 和后续 community/lineage，不应被参考 demo 的 CLI、API、状态模型或目录结构锁定。
- 影响：新实现计划采用 Path B：先建立 `apps/`、`packages/`、`workers/` 边界，再实现独立 `packages/patchify`，只消费参考 pipeline 可能产出的 `samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`。

### 已确认：`patch.json` v1 携带 normalized patterns

- 结论：`patch.json` 增加 `patterns[]`，scene 通过 `pattern_ids` 引用；notes 为 `{element_id, lane, pitch, step, velocity}`；pattern 携带 `length_steps = beats × 4`（`beats` 取自 `lanes.json` 顶层，不用 `bpm × loop_seconds` 反推，也不用可能出现半小节小数的 `bars`）；v1 不带 note duration；`chart.mid` 保留为 pattern 的 source artifact，不进 `renders`。
- 原因：`patch.json` 是 Web/CLI/Worker/API 四方共同契约，不携带 notes 则消费方必须各自解析 MIDI，"可演奏"闭不了环。demo 的 duration 数据无音乐语义（鼓硬编码 0.1s 占位、长样本为样本文件全长，见 `sequencer.py`），velocity 恒为 100（写入 schema 文档注明）。
- 影响：Patchify loader 需解析 `chart.mid` 为 normalized note events；后续接非量化输入时再加 `start_beats`/`duration_beats`，避免 v1 复杂化。

### 已确认：`packages/core-models/` 即刻成立，patchify 为纯 adapter

- 结论：`Patch / Pattern / Pad / Scene / Element` 等产品对象 dataclass 与 `lmdj.patch.v1` 的 JSON Schema 文件都落在 `packages/core-models/`；`packages/patchify/` 只含 loader、mapper、orchestrator、CLI，依赖 core-models。
- 原因：schema 是四方契约，应放在产品对象包而非某个 adapter 里；云架构对 Patchify 的定位本就是 adapter layer。
- 影响：Path B 计划改为两个 package；TS 前端未来从 JSON Schema codegen 类型。

### 已确认：Patchify 输入契约以 demo 真实输出为准 + golden fixture 方法论

- 结论：`lanes.json` 每条 lane 的 wav 路径 key 是 `sample`（loader 兼容读 `path`，`sample` 优先；内部模型与输出统一为 `source_path`）；`song_id` 取自 `report.json`（`lanes.json` 里没有）。测试 happy path 必须使用真实 demo 输出提交为 golden fixture；错误路径 fixture 从 golden 复制后破坏单个字段，不得从零合成。
- 原因：原计划 fixture 凭想象使用 `path`/`song_id` 字段，与 `sequencer.py` 真实输出不符——TDD 全绿但真实数据直接 KeyError。
- 影响：通用规则——凡消费外部产物的 loader，happy-path fixture 必须取自真实产物。

### 已确认：pad 采用 trigger_group 语义，mapper 走 profile 检测

- 结论：element 槽位 pad 携带 `behavior.element_ids`（全组）+ `element_id`（primary）；组内多 element 时 action 为 `trigger_group`，单 element 为 `trigger_element`。mapper 入口先 `detect_profile()`，v1 只支持 standard profile，ABC/DEF（`loop_*`）包显式报 unsupported 而非静默产出空 pads。melody 第二候选 fallback 到 Lead/Vocal 槽位。未上 pad 的 elements 记入 `metadata.unmapped_element_ids`。占位 action（`scene_fill`/`scene_drop`/`mute_group`/`ai_variation`）进完整 enum 并标 reserved；消费方遇到 unknown/reserved action 必须渲染为禁用态/no-op，不得报错。
- 原因：snare/hat 等素材不可成为不可达孤儿；固定语义槽位不可名不副实；前向兼容规则让 v1 前端天然兼容后续 action 扩展，v2 启用时零迁移。
- 影响：schema 的 action 词表一次到位。

### 已确认：patch_id 内容派生，全局身份归平台层

- 结论：`patch_id = {song_id}-{sha256(lanes.json + chart.mid)[:8]}`；schema 文档注明其为内容派生的局部标识，全局唯一 ID 由 App Backend 入库时分配。
- 原因：deterministic mapping 约束与 worker 重试幂等都要求同输入产生同身份；随机 uuid 出局；单用 song_id 与云架构"一歌多 patch"方向冲突。
- 影响：任何一方不得以 patch_id 作数据库主键。

### 已确认：pitch/sample truth 三段式模型

- 结论：v1 内 `lanes.json`/`chart.mid` 是 Patchify 的输入 truth（demo 契约，已冻结）；`patch.json` 生成之后即产品侧唯一 truth，下游不得回读 lanes/chart；`workers/audio/` 正式实现时直接产出 LMDJ 中间格式，demo 契约 loader 转入维护模式。
- 原因：原架构原则"`lanes.json` 仍然是 pitch/sample truth"无限期锚定 demo 格式，与产品自主性冲突；patterns 决策已使下游无需回读。
- 影响：infra spec 关键架构原则同步改写；jobs 幂等（同输入 → 同 storage key，覆盖写安全）与 Postgres v1 收缩（不单独建 pads/scenes 表）一并修订进 infra spec。

## 2026-07-15

### 已确认：PipelineFromStemsRunner 独立 venv，DSP 栈不进 workers/audio 主包

- 结论：从参考 demo 迁移的 pipeline 阶段 3–6（beat/loop/slicer/sequencer/validation）代码落在 `workers/audio/lmdj_audio_worker/pipeline_from_stems/`，但运行在自己的专用 venv 中、以子进程调用；`workers/audio` 主包 `dependencies` 保持为空，只保留协议层。该 venv 的 `librosa`/`numpy`/`scikit-learn`/`soundfile`/`pretty_midi` 锁定为与 demo venv 相同版本，lock 文件入库。
- 原因：DSP 栈（librosa 含 numba、numpy<2）若进主包，会经 `apps/api` 的 path dep 传染进 API venv，破坏既有重依赖隔离决策；同版本锁定又是新旧 pipeline parity 数值容差（1e-4/1e-5）成立的前提。
- 影响：与现有 `DemoPipelineRunner`、separator runner 统一为"子进程 + 独立 venv"模式；parity 只做同平台比较；详见多分轨 benchmark spec §3.1/§3.2（2026-07-15）。

### 已确认：Phase 2A 后生产链路统一走新链，DemoPipelineRunner 退役

- 结论：separator 生产接入（Phase 2A）后，产品 job 统一走 `separator runner 子进程 → PipelineFromStemsRunner 子进程 → Patchify`，包括选 Demucs 时也不再经过 demo 的 `song-pipeline` 整链；`DemoPipelineRunner` 保留到 Phase 2C 端到端验证通过后退役。
- 原因：双链路并存意味着 Demucs 与其他模型走不同代码路径，benchmark 结论对生产不成立；parity 门槛的存在正是为了让新链安全替换旧链。
- 影响：demo 从此只剩 fixture 与 parity 基线角色；CLAUDE.md/AGENTS.md 中"audio → demo pipeline subprocess"的链路描述在 Phase 2C 后需同步改写。
