# LMDJ Playable Beat Instrument 与新内核设计

日期：2026-07-30

状态：用户已逐节确认；设计完成，尚未实现

修订：2026-07-30 评审后补充 §6.5 Raw Take 持久化边界、§6.6 Pattern 引用
语义、§13 `apps/` 目录边界说明、§22 Proof 范围说明、§23 交付顺序（第 0 步
旧产品处置、Web 实时音频 Spike、首个用户价值里程碑）；素材 BPM 与
Project BPM 的关系（Time-stretch）记入
[open-questions.md](../prd/open-questions.md)

勘误（2026-08-23 Sequence 录音语义决策，
[决策文件](../prd/decisions/2026-08-23-sequence-recording-semantics.md)）：
§6.2 / §6.5 由该决策取代——Project Truth 不含 Raw Take / Take 对象，录音
只写 tick-native Pattern 事件；Quantize / Swing 在录入时破坏性写入之后的
新事件，不保留隐藏原始 timing。§6.4、§8、§10.1、§12.1、§18.1 的 Take 措辞
一并按该决策更正。

勘误（2026-08-26 长素材配额与 BPM/Time-stretch 决策，
[决策文件](../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md)）：
首部记入 open-questions 的「素材 BPM 与 Project BPM 的关系（Time-stretch）」
已由该决策解决——sample 无 BPM 属性，全局 BPM 只驱动 Sequencer，
Time-stretch 立为后续逐 Pad opt-in 的离线烘焙能力；prepared-PCM 资源模型
定为 Bank 共享配额、数值由 Host manifest 注入。

优先级：本设计在冲突处取代旧 Stage 1 Creator、`lmdj.patch.v1`、
`lmdj.materials.v1` 与 Agent Orchestration 产品假设

## 1. 结论

LMDJ 重新定位为一个更容易上手的 **Playable Beat Instrument**：

> 把任何声音或完整歌曲快速变成可演奏素材，由用户亲手录制 Beat，并用于现场
> 表演、重组和 Resample。

新产品采用全新的、完全不兼容的内核。旧产品已经下线，不等待新产品完成；旧代码
和文档可以留在 Git 历史中作为研究与迁移素材，但不再约束新设计。

新系统采用以下总原则：

- 一个权威的 Authoring Domain；
- 一个由 Project Cook 得到的派生 Audio Runtime；
- UI、CLI、MCP 与测试 Host 都通过同一 Application Facade 使用内核；
- 每项智能或计算能力通过 Capability Contract 接入；
- Provider 可以是本地模型、原生库、WASM、云服务、远程 GPU 或 Multi-Agent；
- 所有正式源码永久保存在同一个 Monorepo；
- 模块可以独立开发、测试、打包和发布，但不能拆分 Source of Truth；
- 失败属于某次 Attempt，不属于用户 Project。

## 2. 状态边界

| 项目 | 当前状态 |
| --- | --- |
| 产品与内核设计 | 已确认 |
| 新 Project / Runtime / Capability Contract | 已设计，未编码 |
| 新 64-Pad Headless Core | 未实现 |
| Creator 新 UI | 已设计，未实现 |
| CLI / MCP Host | 已设计，未实现 |
| 新 Provider SDK | 已设计，未实现 |
| 旧产品服务 | 已停止，服务器文件和历史代码仍保留 |

本文授权的是后续规划，不代表任何模块已经实现、发布、合并或部署。

## 3. 产品定位

### 3.1 目标用户

目标用户接近 Koala Sampler 的用户，但比现有 Koala 用户更偏新手：

- 有节奏感、品味或表演欲；
- 想快速把自己的声音变成 Beat；
- 不想先学习完整 DAW；
- 愿意亲手演奏，而不是让 AI 代替创作。

### 3.2 核心承诺

用户应能在约三分钟内完成：

```text
任意声音 / 完整歌曲
  → 分析、分轨、切片或裁剪
  → 得到可演奏 Pads
  → 用户亲手录制第一个 Beat
```

AI 的角色是辅助材料处理和 Sequence 候选，不是替用户完成 Beat。

### 3.3 首版非目标

- 不做首次登录新手引导；
- 不做 YouTube 教学弹窗；
- 不做完整 DAW；
- 不自动生成一个成品 Beat 取代用户演奏；
- 不做 Sound Set Marketplace、购买和创作者上传；
- 不做多人实时协作；
- 不兼容旧 Patch / Materials Project。

### 3.4 首发平台与输入

首发产品面向 Desktop / Tablet Web/PWA，同时支持：

- Touch；
- Mouse；
- Keyboard；
- Web MIDI。

Native Host 是内核验证与后续产品形态，不是首版 Creator UI 的前置条件。

## 4. 工作台信息架构

工作台始终保持上、中、下三部分：

### 4.1 顶部

- Project 名称和保存状态；
- BPM、Key 和全局音乐状态；
- Transport：播放、停止、录制、节拍器、Loop、Bar/Beat；
- `Sample / Sequence / Perform` 三个主模式；
- 当前 Provider、执行位置和任务状态的必要提示。

### 4.2 中部 Surface

中部是多功能 Surface，根据模式和当前对象切换：

- Sample：波形、裁剪、Slice、Stem、候选预览；
- Sequence：录制状态、Pattern Grid、Quantize、Swing、Pattern Assist；
- Perform：Pattern Launch、Momentary FX、录制和 Resample；
- Sound Set：预览、下载、安装目标 Bank；
- Job：进度、Provider、错误和恢复动作。

Pad 旁不保留永久 Inspector。`Edit / AI / More` 只是二级入口，具体操作在中部
Surface 展开。

### 4.3 底部

底部始终是可演奏 Pad 平面：

- 一次显示一个 4×4 Bank；
- 总计四个 Bank：A、B、C、D；
- 一共 64 个 Pad；
- Bank 位置和 Pad 位置稳定；
- 编辑时仍保留演奏入口。

## 5. Pad、Asset 与 Lineage

### 5.1 单一 Pad 模型

Pad 是一个可演奏 Slot，引用一个 Sound Asset。Pad 不因为来源不同而变成互不兼容
的类型。

Asset 来源包括：

- Captured：用户录音；
- Imported：用户导入的音频；
- Derived：裁剪、复制、Slice、Stem、Resample 得到的素材；
- Sound Set：下载的预设音色包。

用户可以先把一段录音、一个 Loop 或一首完整歌曲放进单个 Pad，再选择只裁出一段，
或使用 Slice / Stem 能力把它拆成多个 Candidate Assets。

### 5.2 派生规则

所有自动分析遵循：

```text
Source Asset
  → Analyze / Trim / Slice / Stem
  → Candidate Assets
  → Preview
  → 用户选择结果
  → 用户选择目标 Pad
  → 创建独立 Derived Asset
```

系统不得在分析完成后自动覆盖 Bank。原始素材必须保留，派生结果记录 Lineage。

### 5.3 复制与独立编辑

用户可以把当前 Pad 的 Asset 复制到其他 Pad。复制后可以独立裁剪、调参或再次
派生，不反向改变原始 Pad。

### 5.4 Sound Set

Sound Set 是可预览和下载的 16-Pad Bank Package：

- 支持整套与单个音色试听；
- 带角色、BPM、Key、License 和 Version；
- 安装时由用户选择目标 Bank；
- 原始 Set 不可变；
- 用户修改后产生 Derived Asset；
- 首版只做 Catalog，不做 Marketplace。

将 Sound Set 应用到已有 Pattern 时，优先使用确定性的角色、BPM、Key 和音域
映射。AI 可以成为未来 Provider，但不是首版依赖。

## 6. Sequence

### 6.1 用户演奏是真相

Beat 必须由用户亲手演奏。系统保存：

- 触发的 Pad 和 Bank；
- 实际 Timing；
- Velocity；
- Pitch 或 Playback 参数；
- Overdub 和编辑历史。

### 6.2 Pattern 录音（2026-08-23 决策勘误）

- 录音直接往当前 Pattern 槽写入 tick-native 打击事件（PPQ 960）；没有
  Raw Take / Take 对象，也没有录音会话的音频 bounce；
- Pattern 是可循环、可编辑的结构；
- 首版提供 16 个 Pattern Slot；
- 录制长度支持 1、2、4、8 Bars；
- 支持 Overdub、Undo/Redo、Clear、Duplicate；
- Quantize 和 Swing 在录入时破坏性写入之后的新事件：Quantize 开则原始
  时间丢弃、不保留第二份未吸格档案，Swing 只烘焙进之后新写入事件的
  onset；
- 首版使用简化 Step Grid，不做完整 Piano Roll。

### 6.3 Pattern 切换

Pattern 可以在 Beat、Bar 或 Pattern End 切换，默认在下一 Bar 生效。

### 6.4 Composition Assist

Sequence 阶段可以生成候选：

- Drum Groove；
- Bass / Melody；
- Fill / Variation；
- Sparse / Dense 版本。

候选基于 Pad Role、BPM、Key、Range 和当前素材。它可以由规则、概率模型、传统
模型或 AI Provider 实现。

候选只能：

- 保存到新 Pattern Slot；
- Merge；
- 替换当前编辑版本；
- Discard。

它不得覆盖用户已录入 Pattern 的演奏事件。

### 6.5 录音持久化边界（2026-08-23 决策勘误）

用户演奏不可再现，其丢失成本与可重跑的 AI Job 不对称，因此录音不走
Candidate → Commit 流程：

- Journal 只服务录音会话；录音在 flush 边界（停录、停 Play、切 Sample、
  切槽）以幂等 Command 原子写入 Pattern，不创建 Take 对象；
- 录音进行中，演奏事件必须尽早写入本地 Journal，不允许只存在内存；
- 录音中断按 §18.1 封存为恢复件，下次打开 Project 时提示恢复；恢复写回
  由目标 Pattern 的 canonical fingerprint 门控，新鲜 revision 不单独构成
  写回理由；
- Workspace Cache 的清理策略不得清除尚未恢复的中断录音；
- 录音进行中的并发 Command 按分类处理（选择性 rebase 白名单、Sample 类
  失败但录音继续、未知 Command fail closed），完整语义见
  [2026-08-23 决策](../prd/decisions/2026-08-23-sequence-recording-semantics.md)
  与其引用的设计文档。

### 6.6 Pattern 引用语义

Pattern 事件引用 Pad Slot（Bank + Pad 位置），不直接引用 Asset：

- 更换 Pad 音色后，既有 Pattern 以新音色回放（Sampler 惯例）；
- 需要冻结当前声音时，使用 Resample 产生新 Asset；
- Lineage 记录 Asset 派生关系，不记录 Pattern 与音色的历史组合。

## 7. Perform

Perform 提供：

- Pad 演奏；
- Pattern 切换；
- Bank 切换；
- Momentary FX；
- Performance Events 录制；
- Stereo WAV 录制；
- Replay、命名、导出和 Resample。

Stage 10 的 Pattern Launch 表面不是 Host 私有列表。Project Truth 持久化恰好
16 个有序 nullable Pattern 槽；占用槽引用同一 Project 中唯一存在的 Pattern。
槽 assign/clear/move 是 Authoring Command。Performance 只记录 slot index，Replay
在开始时固定的当前 Project revision 上解析该槽；空槽产生静默 gap。精确 schema、
录制 draft 生命周期、Core 时间/边界/合并权威与 Facade 操作面见
[2026-08-31 Contract 修复决策](../prd/decisions/2026-08-31-stage10-performance-contract-repair.md)。

首版 Momentary FX 包括（2026-08-29 Stage 10 设计评审勘误：Roll 更名为
Cutter，八项逐一对位 Koala 官方手册 §9.1 的 perform FX 定义；Delay 取
节拍同步语义，见
[Stage 10 Perform 设计](2026-08-28-lmdj-stage10-perform-design.md)）：

- Filter；
- Delay；
- Reverb；
- Stutter；
- Gate；
- Reverse；
- Crush；
- Cutter。

`Hold` 必须是显式状态。用户可以把完整演出或选中片段 Resample 成新的 Asset，
再写入目标 Pad，形成：

```text
Sound → Pad → Pattern → Performance → New Sound
```

## 8. 用户看到的 Project

用户只看到一个 `Beat Project`：

- 名称；
- BPM / Key；
- 64 Pads / 4 Banks；
- Patterns；
- 16 个有序 Pattern Launch 槽；
- Performances；
- Save / Load / Duplicate / Export。

导出入口使用用户语言：

- Sample；
- Pattern；
- Performance；
- Stems；
- Full Beat；
- Project Backup。

Asset Path、Hash、Lineage、Checkpoint、Attempt、Schema、Cache 和 Migration 等
内部信息默认隐藏。

## 9. `.lmdj` Project 与存储

`.lmdj` 是可移植的 Project Bundle，不是某个 Storage Provider 的数据库备份。

逻辑内容包括：

```text
manifest.json
project.*
assets/<content-hash>
history/*
```

Project Bundle 保存：

- 用户 Authoring State；
- 已采用的原始或派生 Artifact；
- Lineage；
- 必要的 Command / Checkpoint；
- 已采用 Provider 结果的标准化溯源。

标准化溯源可以包含：

- `capability_id`；
- Provider / Model Version；
- Parameters Hash；
- Input / Output Artifact Hash；
- 时间、License 和必要 Region 信息。

Project Bundle 不保存：

- API Key 或登录凭证；
- Provider 私有数据库；
- 模型 Cache；
- Multi-Agent 内部对话或推理；
- 完整执行日志；
- 队列状态；
- 未采用 Candidate；
- 失败任务的临时产物。

这些运行数据属于独立的 Job Store / Workspace Cache。Authoring Session 可以持有
当前 Job / Candidate Handle，但 Candidate 只有在用户采用后，其结果和最小溯源
才持久化进入 Project Bundle。

物理存储通过 Storage Provider 实现：

- Native：Filesystem / SQLite 等；
- Web：OPFS / IndexedDB 等；
- Cloud：Object Store / Database 等。

Application Facade 是唯一访问入口。UI、CLI 和 MCP 不直接解析 Bundle 内部文件。

## 10. Engine 与 Editor 分离

新内核参考 Godot 的 Engine / Editor 分离，但不复制 SceneTree。

### 10.1 Headless Engine

Headless Core 可以在没有 UI 的情况下：

- 创建、加载和检查 Project；
- 导入或录入 Artifact；
- 分配和编辑 Pad；
- 创建 Pattern / Performance（含 Sequence 录音会话）；
- Cook Runtime Snapshot；
- Offline Render；
- 调用 Capability；
- 查询、等待、取消和重试 Job；
- 切换 Provider；
- 输出结构化诊断。

### 10.2 Editor / Host

Creator Editor 没有内部特权。Web UI、Native UI、CLI、MCP 和测试 Host 都调用相同
Application Facade。

CLI 不解析 UI 文案，MCP 不绕过 Command Handler，REST 也不是内核本体。

## 11. 一个权威 Domain，一个派生 Runtime

系统不是两个平级 Core，而是：

```text
Authoring Project
  → Validate / Cook
  → Immutable Runtime Snapshot
  → Audio Runtime
```

### 11.1 Authoring Domain

Authoring Domain 持有：

- Project Truth；
- Pad / Asset / Pattern / Performance；
- Lineage；
- Command、Undo/Redo 和 Checkpoint；
- Save / Load / Migration；
- Job 与 Candidate 的产品级引用。

### 11.2 Audio Runtime

Runtime 只持有播放必须的临时状态：

- 当前 Snapshot；
- Transport Position；
- Voice Pool；
- DSP Buffer；
- Asset Cache；
- Event Queue；
- Capture Ring；
- Telemetry Counters。

这些状态可丢弃、可重建，不回写成 Project Truth。

### 11.3 Snapshot 发布

- Snapshot 在非 Audio Thread 准备；
- 完整验证后，在安全音频边界原子发布；
- 发布失败继续使用上一 Snapshot；
- 旧 Voice 可以按策略自然结束；
- 退役资源在安全时机回收。

### 11.4 录音路径

```text
Audio Thread
  → lock-free Capture Ring
  → Background Writer
  → Immutable Audio Artifact
  → Authoring Command
  → Project Revision
  → New Runtime Snapshot
```

## 12. Application Facade

内核公开四类结构化接口：

### 12.1 Command

改变 Authoring State，例如：

- CreateProject；
- ImportAsset；
- AssignPad；
- TrimAsset；
- CommitCandidate；
- Sequence 录音会话的 flush（把本批事件写入 Pattern）；
- Pattern 槽 assign / clear / move；
- Performance draft begin / flush / save / discard / recover / bind；
- SavePattern；
- ResamplePerformance。

Command 必须原子执行，并带 Expected Project Revision。

### 12.2 Query

读取 Project、Pad、Pattern、Capability、Provider、Job 和 Runtime 状态，不产生
写入副作用。

### 12.3 Job

表示长任务：

- Stem Split；
- Smart Slice；
- Pattern Suggest；
- Render；
- Export；
- Remote Processing。

### 12.4 Event

向 Host 通知：

- Project revision changed；
- Snapshot published / rejected；
- Job progress / terminal state；
- Device state；
- Runtime warning；
- Capture recovered。

Audio Runtime 只暴露窄 C ABI。上层结构化 API 不把实现语言 ABI 泄露给 Host。

## 13. 模块边界

第一阶段建议在 Monorepo 中建立以下独立构建与测试单元：

```text
contracts/

packages/
  foundation/
  authoring-domain/
  project-cooker/
  audio-runtime/
  provider-sdk/
  project-io/

providers/
  local-*/
  cloud-*/

apps/
  core-cli/
  core-mcp/
  native-test-host/
  web-runtime-lab/
  creator-web/

workers/
  provider-host/

products/
  lmdj/
    assembly.*

tests/
  conformance/
  fixtures/
```

`packages/`、`providers/` 和 Host-neutral Contract 必须保持产品无关，不能依赖
LMDJ Creator UI。LMDJ 只是通过 `products/lmdj/` 组合这些能力；未来其他产品可以
在同一 Monorepo 中建立自己的 Product Assembly 并复用相同模块。

`apps/` 不整体承担产品无关约束：`core-cli`、`core-mcp`、`native-test-host` 和
`web-runtime-lab` 是内核 Host，必须保持产品中立；`creator-web` 是 LMDJ 产品
UI，允许依赖 `products/lmdj/` 的 Assembly，但同样不得绕过 Application Facade。

目录名称可以在实施计划中做机械调整，但依赖方向不能改变：

```text
foundation
  ← authoring-domain
  ← project-cooker
  ← audio-runtime

provider-sdk
  ← provider implementations

Application Facade
  ← UI / CLI / MCP / Test Hosts
```

模块不得读取兄弟模块内部文件、私有数据库或未公开类型。

## 14. 永久 Monorepo 开发模式

所有正式源码永远保存在当前 Monorepo。未来可以发布独立 Package、SDK、Binary、
Container 或 WASM，但不拆分正式源代码仓库。

### 14.1 并行开发

每台机器或 Agent：

- 拉取同一个 Repo；
- 认领一个清晰模块目录；
- 使用短分支和独立 Worktree；
- 只修改自己的 Ownership Scope；
- 提交 Module Manifest、实现、测试和产物说明；
- 通过 PR 和 CI 合并。

### 14.2 Contract First

跨模块变更顺序：

1. 先提交 Contract / ADR；
2. 通过 Schema 与兼容性检查；
3. 各模块并行实现；
4. 各 Provider 跑 Conformance Suite；
5. 主 Agent 组装产品；
6. 跑组合、平台和真机验证。

### 14.3 主 Agent

主 Agent 是 Integration Owner：

- 维护契约和依赖方向；
- 维护 Assembly Manifest；
- 接收并审查模块 PR；
- 运行组合测试；
- 定位跨模块故障；
- 把模块缺陷派回对应 Owner；
- 负责仅属于装配层的修复；
- 执行 Release Gate。

主 Agent 也不能直接修改 protected `main`。它在专用 Worktree / 分支中组装和调试，
再通过 CI、Review 和 PR 合并。

## 15. Module Manifest 与 Product Assembly

每个模块声明：

- Module ID 和 Version；
- Owner / Claim Scope；
- Public Contract Version；
- Dependencies；
- Supported Platforms；
- Build / Test Commands；
- Produced Artifacts；
- Required Permissions；
- Resource Class；
- Conformance Suite。

`products/lmdj/assembly.*` 锁定：

- 精确模块版本；
- Provider Selection Policy；
- Platform Drivers；
- Region / Privacy / Permission Policy；
- Required Test Gates。

“最终在一个地方组装”指可复现 Assembly Pipeline，而不是某台开发机器上的手工粘合。
同一清单应能在本地、CI 或云环境中生成可追踪的产品产物。

需要胶水时，胶水必须成为具名、版本化、可测试的 Adapter / Transformer Module。

## 16. Capability 与 Provider

Capability 定义产品需要什么，不定义由谁实现。

示例：

```text
stem.split
sample.slice
sample.analyze
pattern.suggest
render.audio
export.project
```

Capability Contract 至少包含：

- `capability_id`；
- `contract_version`；
- Input / Output Artifact Schema；
- Determinism Class；
- Progress Event；
- Typed Error；
- Resource Requirements；
- Timeout / Retry Policy；
- Privacy / Region Constraints。

Provider 可以是：

- 本地原生模型；
- Python Worker；
- WASM；
- 云 API；
- 远程 GPU；
- 传统算法；
- Multi-Agent Workflow。

Provider 内部架构对 Product 不透明。Multi-Agent 也只是一个 Provider 实现；它不能
让多个 Agent 直接修改 Project。

系统根据 Platform、Capability、性能、网络、成本、Region 和用户策略选择 Provider。
执行前应显示 Provider、位置和能力等级。

禁止在同一 Attempt 内静默回退。重试、换 Provider 或换参数都创建新的 Attempt。

## 17. 契约分层

新内核不使用一份万能 JSON 同时服务所有层，而是四个独立边界：

### 17.1 Project Contract

持久化用户创作意图，是唯一 Project Truth。

### 17.2 Runtime Snapshot Contract

由 Project Cooker 生成，只读、可丢弃，不回写 Project。

### 17.3 Capability I/O Contract

每项 Capability 独立版本，不由某个 Provider 定义。

### 17.4 Assembly Contract

描述 LMDJ 产品由哪些模块、Provider、Driver 和 Policy 组成。

四种契约独立版本。跨边界只传不可变 Artifact Ref：

- Content Hash；
- Media Type；
- Schema / Contract Version；
- Minimal Metadata。

只为新架构自己的未来版本提供前向 Migration。新内核不读取、不迁移、不提供
`lmdj.patch.v1` 或 `lmdj.materials.v1` Compatibility Adapter。

## 18. Job、Attempt 与失败恢复

采用 Strict Transactional Recovery：

```text
Command Validation
  → Job / Attempt
  → Candidate Artifact
  → Preview
  → User Commit
  → Atomic Project Revision
```

Attempt 是最小失败和追踪单元，状态包括：

- Queued；
- Running；
- Succeeded；
- Partial；
- Failed；
- Cancelled；
- Superseded。

Attempt 记录：

- Job / Attempt / Capability Identity；
- Module、Provider 和 Model Version；
- Input Artifact、Project Revision 和 Parameters Hash；
- Region、Device、时间和进度；
- Output Artifact 或 Typed Error；
- 质量信号；
- 脱敏诊断。

### 18.1 隔离行为

- Provider 超时：当前 Attempt 失败，Project 不变；
- Snapshot 构建失败：继续使用上一有效 Snapshot；
- Audio Device 丢失：安全挂起 I/O，不修改工程；
- 录音中断：尽可能封存为恢复件，确认写回由指纹门控（§6.5）；
- Asset 丢失：Pad 标记 Offline，保留引用，不自动换音色；
- Storage Full：原子写失败并保留旧 Project；
- Multi-Agent 冲突：Provider 内部解决，对外只产生一个终态结果；
- Export 失败：只影响 Export Job，可从相同 Revision 重跑。

UI、CLI 和 MCP 使用相同 Typed Error，例如：

```text
INVALID_PROJECT
MISSING_ASSET
CAPABILITY_UNAVAILABLE
PROVIDER_FAILED
DEVICE_LOST
STORAGE_FULL
TIMEOUT
CANCELLED
PARTIAL_RESULT
SNAPSHOT_REJECTED
DECODE_FAILED
EXPORT_FAILED
```

UI 可以把错误解释成人话，但不能改变错误语义。

## 19. 权限、Region 与执行隔离

采用 Capability Permission Manifest + Policy Engine + Execution Zones。

### 19.1 Realtime Trusted Zone

Audio Runtime 和审核过的 DSP Extension 可以进程内运行，但：

- 只能访问 Audio Buffer、Transport 和 DSP Params；
- 不能访问网络、Project Write、Secret 和普通日志；
- Audio Thread 禁止 Lock、Allocation、File I/O、Network 和 Logging。

### 19.2 Local Isolated Provider Zone

本地模型、分析器、导出器和 Multi-Agent Host 默认在独立进程或 Sandbox：

- 只读取 Scope 内 Artifact；
- 只写临时 Workspace 和 Output Artifact；
- GPU、Filesystem、Subprocess 和 Network 必须声明；
- 结果只能是不可变 Artifact 或 Typed Error。

### 19.3 Remote / Cloud Zone

远程 Provider 必须满足 Region、Privacy 和 Retention Policy：

- 使用临时上传或短期 Signed Artifact Access；
- 记录 Provider、Model、Region 和 Attempt；
- 支持时记录 Retention 与删除回执。

### 19.4 Policy

Capability Request 声明：

- Input Artifact；
- Data Classification；
- Capability；
- Platform；
- Region；
- Latency / Cost Preference；
- Required Permissions。

Policy Engine 只允许匹配的 Provider。没有合法 Provider 时 Fail Closed，不能偷偷
上传、换区或扩权。

Secret 由 Host Secret Store 注入短期凭证，永不写入 `.lmdj`、Assembly Manifest
或日志。Provider 只接收当前 Capability 所需素材，不接收整个 Project Bundle。

## 20. 技术实现原则

### 20.1 Audio Runtime

实时 Sampler、Sequencer、Mixer、Capture 和基础 DSP 优先使用 C++20：

- 编译为 Static / Shared Library；
- 提供稳定窄 C ABI；
- 支持 Native；
- 支持 WASM。

### 20.2 其他实现

- Python 可用于本地或云端 ML Provider；
- TypeScript / React 可用于 Web Editor 和 Host Orchestration；
- Provider 语言不进入 Domain Contract；
- 具体库、模型或云平台不是内核固定依赖。

## 21. 验证策略

### 21.1 Domain

- 相同 Command Log 重放得到相同 Project State；
- Command 原子性；
- Revision Conflict；
- Undo / Redo；
- Lineage；
- Project Bundle Round Trip。

### 21.2 Runtime

- 同平台 Offline Render 可重复；
- 跨平台使用 Golden Audio 容差；
- Snapshot 原子发布；
- 旧 Voice 与资源回收；
- Audio Thread 无 Lock、Allocation、File I/O、Network 和 Log。

### 21.3 Provider

- 所有实现运行同一 Capability Conformance Suite；
- Input / Output Schema；
- Typed Error；
- Cancellation；
- Timeout；
- Partial Result；
- Permission / Region Denial；
- Provenance。

### 21.4 Host

- CLI、MCP、Web 和 Native Test Host 共享行为 Fixture；
- Host 不直接读取 Project Bundle；
- Provider Quality 可以不同，但 Version、Params 和 Artifact 必须可追踪。

### 21.5 Assembly

```text
Module Unit Tests
  → Contract Conformance
  → Dependency Graph Validation
  → Product Assembly E2E
  → Platform Matrix
  → Real Device Gates
```

真实 MIDI、触控、浏览器音频生命周期、延迟、Audio Device、可访问性和音质不能由
Headless Test 代替。

## 22. 第一个内核 Proof Project

首个目标是：

> Headless 64-Pad Beat Project + Sampler + Pattern Playback + Offline WAV Render
> + Golden Audio + CLI / MCP。

它必须在没有 UI 的情况下完成：

1. 创建 Project；
2. 导入固定音频 Fixture；
3. 分配 64 Pad 中的若干 Pad；
4. 创建一个用户演奏 Pattern；
5. Cook Snapshot；
6. Offline Render WAV；
7. 对比 Golden Audio；
8. 通过 CLI 和 MCP 查询相同 Project State；
9. 切换一个测试 Provider；
10. 验证失败 Attempt 不改变 Project。

第一 Proof 不包含：

- Creator UI；
- Stem Model；
- Sound Set Catalog；
- Live Device Audio；
- Marketplace；
- 云部署。

第一 Proof 验证的是确定性与事务边界，不覆盖实时演奏延迟。实时延迟由 §23 中
提前启动的 Web 实时音频 Spike 单独验证，两者互不替代。

## 23. 交付顺序

0. 旧产品处置与仓库指南重写：确定旧 `apps/` / `packages/` / `workers/` 代码
   的去向（删除或移入 `references/`），并重写 CLAUDE.md / AGENTS.md，使其
   描述新内核而非旧 `lmdj.patch.v1` 链路——否则后续每个开发 Agent 都会被
   过时指令误导；
1. Foundation、Contract 和 Build Lab；
2. Headless Project / Runtime / Offline Render；
3. CLI + MCP；
4. Provider SDK 与 Provider Conformance Lab；
5. Native Realtime Host（先 macOS / CoreAudio）；
6. Web WASM + AudioWorklet + OPFS；
7. Creator Editor；
8. Sample；
9. Sequence；
10. Perform；
11. Sound Set；
12. Stem / Slice / Pattern Intelligence Providers。

与第 1 步同期启动 **Web 实时音频 Spike**：最小化验证
AudioWorklet + WASM 线程、SharedArrayBuffer 所需的 Cross-Origin Isolation、
iPad Safari 音频生命周期，并实测 Touch-to-Sound 延迟。它不依赖 Facade 和
Provider SDK，是"Web/PWA 首发"决定的最早验证点；若延迟不可接受，必须回到
设计评审重议首发平台，而不是在实施中静默降级体验。

第 9 步完成即构成**首个用户价值里程碑**：真实用户可以导入声音、手动裁剪、
分配 Pad 并亲手录出 Beat（不含 Stem / Slice 智能）。三分钟核心承诺的
"亲手演奏"部分在此验证，不等待第 12 步的 Intelligence Providers。

UI 与内核可以独立开发，但 Creator Editor 只能依赖已经通过 Facade 和 Conformance
验证的能力。

## 24. 被拒绝的方向

### 24.1 继续扩展旧 Patch / Materials

拒绝。它们的生命周期和消费者边界已经与新产品不匹配。

### 24.2 两个平级 Core

拒绝。Authoring Domain 是唯一真相，Runtime 是派生状态。

### 24.3 一个万能 Contract

拒绝。Project、Runtime、Capability 和 Assembly 必须独立演进。

### 24.4 自由 Agent Swarm 直接修改 Project

拒绝。Agent 可以规划或作为 Provider 内部实现，但写入必须经过结构化 Command、
Policy 和事务边界。

### 24.5 Provider 静默回退

拒绝。会破坏可追踪性、质量解释和数据策略。

### 24.6 Polyrepo

永久拒绝。可以独立发布产物，但不拆 Source of Truth。

### 24.7 Editor 拥有内部特权

拒绝。UI、CLI、MCP 与测试 Host 必须使用同一 Facade。

## 25. 实施计划前仍可机械确定的事项

以下内容不改变本设计，可以在实施计划中确定：

- C++ Build System；
- Project Contract 的具体编码格式；
- `.lmdj` Bundle 的压缩与索引实现；
- Native Storage 数据库选型；
- WASM Toolchain；
- C ABI 函数命名；
- Module Manifest 的 YAML / TOML / JSON 语法；
- Golden Audio 的精确数值容差；
- 第一批 Fixture；
- macOS Audio Host 的具体 Driver Library。

如果某项选择改变 Domain Ownership、公开 Contract、Provider 权限、Monorepo 原则或
用户演奏优先级，则必须回到设计评审，而不能作为实施细节直接决定。
