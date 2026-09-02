# Needle 2 类端侧结构化指令小模型与 LMDJ 适配研究

> 日期：2026-09-01
>
> 关联 Issue：[#528](https://github.com/endaye/lmdj/issues/528)
>
> LMDJ 代码基线：`dec5d7b566ba5c29745800ff82eddab836bbf17c`
>
> 文档性质：静态技术研究与受控 Spike 建议，不是产品立项、模型选型批准、
> Capability/Provider/Contract 设计或自然语言控制功能承诺
>
> 证据边界：本文核对了公开模型卡、论文、源码说明和当前 LMDJ 源码；没有下载
> 或运行任何模型，没有产生 LMDJ 语料实测准确率、延迟、峰值内存或真机结论

## 0. 结论先行

Needle 2 不是一个“纯 MLP”，也不是音频模型。它是一个面向端侧工具调用与结构化
抽取的 45M 参数语言模型，使用 Simple Attention Network：GQA Attention、Hadamard
MLP、Engram key-value memory 与多通道 residual 共同组成网络。它接收文本和工具
Schema，输出受语法约束的结构化调用。

这类模型对 LMDJ 最合理的用途只有一条：

```text
自然语言或语音转写
  → 受限的 LMDJ Intent Draft
    → Schema / 风险 / 权限 / 当前状态校验
      → 用户预览与确认
        → Host 补齐权威字段
          → Application Facade / MCP
```

它不适合、也不能替代：

- 音频分轨、节拍或调性分析；
- 波形理解、切片点检测和声音分类；
- Pattern 音乐内容生成本身；
- Realtime Audio Thread 上的任何判断；
- Project Truth、Provider Attempt 或 Candidate 的权威写入路径。

本文建议把 **Needle 2 作为第一候选做只读、永不执行工具的本地 Spike**；同时用
FunctionGemma 270M、LFM2.5-230M 和一个非生成式 intent classifier/MLP 作为对照。
在 LMDJ 自有中英文命令语料、拒答样本和真实 MCP Schema 上完成测量之前，不批准任何
模型进入 Product Assembly，也不新增产品自然语言入口。

## 1. 研究问题与范围

本文只回答五个问题：

1. Needle 2 到底是什么模型，所谓 MLP 在其架构中承担什么角色？
2. Needle 2 类端侧小模型能为 LMDJ 完成哪些文本任务？
3. 当前 LMDJ MCP / Application Facade 边界是否能直接承接其输出？
4. 哪些相近模型值得作为对照，纯 MLP 又适合放在哪里？
5. 一个不改变产品架构、不执行命令的 Spike 应如何判定 go/no-go？

本文不研究音频神经网络、Stem Separator、生成音频模型、大语言模型聊天助手、云端
Agent、Speech-to-Text 模型或通用 RAG。语音只是可能的上游输入；若未来使用语音，转写
准确率和隐私必须由独立研究负责。

## 2. Needle 2 的真实模型形态

### 2.1 不是纯 MLP

[Needle 2 官方模型卡](https://huggingface.co/Cactus-Compute/needle2)将它描述为
45M 参数的工具调用、设备控制与结构化抽取模型。其 Simple Attention Network 包含：

- GQA Attention；
- 代替传统 FFN 的 Hadamard MLP；
- hashed n-gram Engram key-value memory；
- multi-lane hyper-connections；
- RMS normalization、gating 与受 Schema 约束的 byte-level decoding。

因此，“Needle 2 是 MLP 小模型”只说对了一部分：Hadamard MLP 是一个组件，但整个模型
仍然包含 Attention、Embedding、Memory、Tokenizer 和自回归解码。其研究基础是
[A Controlled Study of Attention-Only Transformers](https://arxiv.org/abs/2607.18363)，
论文研究的是在受控预算下移除传统 FFN/MLP 后 Attention-only 模型的能力与缺口；
Needle 2 的工程配方并不等于一个普通前馈分类器。

### 2.2 它擅长的任务

官方公开能力集中在三个窄任务：

1. 从工具目录中选择函数；
2. 从用户文本抽取参数并生成结构化调用；
3. 在给定 Schema 下提取结构化数据。

模型卡还声明：

- 45M 参数，CQ2-bit 压缩；
- 模型与 engine 合并为一个约 14 MB binary；
- 官方自报完整 session 峰值约 28 MB RAM；
- 支持 ARM64、x86-64、ARMv7、RISC-V 与 WebAssembly 等目标；
- 256-token sliding window，工具作为固定 KV sinks；
- 超过五个工具时由内置 retrieval head 只选择前五个进入上下文；
- 结构化调用由从 Schema 编译出的 byte-level grammar 约束；
- 输出带 confidence，但该 confidence 必须在具体产品语料上重新校准。

以上尺寸、速度和内存数字来自上游模型卡，不是 LMDJ 测量。不同平台 binary、静态库、
页面装载、WASM memory、模型初始化和一次完整产品 session 的成本必须分别测量，不能把
“14 MB 模型 binary”直接写成“LMDJ 只增加 14 MB”。

### 2.3 它不具备的能力

Needle 2 的输入是文本 Token，不是 PCM、频谱或 MIDI event。仅靠该模型不能回答：

- 音频的 BPM、Key、Chord 或乐器角色是什么；
- 哪些 frame 是合适的 slice points；
- 哪段声音适合 Kick、Snare、Bass 或 Melody Pad；
- 一条 Pattern 是否更有 Groove；
- 两段音频在听感上是否匹配；
- 哪个 Stem Separator 的质量更好。

它最多可以在其他权威模块已经产生上述结构化事实后，把“把 BPM 改成 96”“新建一个
四小节 Pattern”之类语言转成命令草案。

## 3. 候选模型与非模型基线

### 3.1 Shortlist

| 候选 | 规模与定位 | 结构化调用特点 | LMDJ 价值 | 主要风险 |
| --- | --- | --- | --- | --- |
| Needle 2 | 45M，端侧工具调用与抽取 | byte-level grammar、工具检索、confidence head | 最小尺寸；输出契约最贴近 MCP JSON Schema | 上游性能数字未在 LMDJ 复现；中文与复杂参数能力未知；专用 engine 集成成本未知 |
| FunctionGemma 270M | 270M，函数调用专用基础模型 | Google 明确建议按具体函数调用任务微调 | 成熟 Transformers 生态；适合验证“专用微调是否超过极小模型” | 比 Needle 大；Gemma 使用条款；未经 LMDJ 微调不能当成成品 |
| LFM2.5-230M | 230M，端侧通用文本与 agentic task | 支持 tool use、抽取；中英等十种语言 | 可作为中文与通用能力对照；提供 GGUF/ONNX/MLX | 自身没有 Needle 同等的强制 grammar 契约；自定义 LFM license；部署体积显著更高 |
| Intent classifier / MLP | 参数量可低于 1M，固定类别分类 | 只输出 intent/risk/tool shortlist；参数需另用规则解析 | 极低成本、可解释、适合作为 query/command/refuse gate | 不是语言生成模型；不能独立填充开放字符串、UUID 或复杂嵌套参数 |

[FunctionGemma 官方模型卡](https://huggingface.co/google/functiongemma-270m-it)
明确说它不是直接对话模型，而是为特定 function-calling task 微调的基础。官方 Tiny
Garden 示例把自然语言游戏指令映射到应用函数，与 LMDJ 的窄命令草案场景相近。

[LFM2.5-230M 官方模型卡](https://huggingface.co/LiquidAI/LFM2.5-230M)
将其定位为端侧数据抽取和轻量 agentic pipeline，声明 230M 参数、32K context、十种语言
以及 GGUF、ONNX、MLX 等发布形式。其 function calling 默认生成特殊标记包围的 Pythonic
call，也可以提示为 JSON；LMDJ 仍需独立语法和 Schema 校验，不能把“支持 tool use”理解成
“输出必然符合 LMDJ Contract”。

### 3.2 为什么保留纯 MLP 基线

如果 LMDJ 只开放十几个固定高层 intent，一个小型 MLP 可以处理：

- `query | command | refuse` 风险分类；
- `inspect_project | inspect_pad | set_tempo | create_pattern | ...` intent 分类；
- 在候选工具目录中做 top-k ranking；
- 判断输入是否落在训练分布内。

它的输入可以是固定词袋、字符 n-gram 或冻结 encoder 产出的 embedding；输出是固定类别。
但这只是路由器。`96 BPM`、`Bank B Pad 3`、自然语言文件名和多步引用仍需要确定性解析器、
实体解析器或生成模型。把纯 MLP 与参数解析链组合后，系统更可解释，但不再是“一只模型
完成全部工作”。

因此 Spike 必须保留一个非生成式基线，避免因为 Needle 2 新颖就跳过更简单方案。若规则
或 MLP 已在目标语料上达到同等准确率和更低风险，应优先选择简单方案。

### 3.3 暂不进入 Shortlist 的模型

OpenELM、SmolLM、TinyLlama 等通用小语言模型可以生成文本，但没有比前三者更直接的
LMDJ function-calling 证据。本文不把“参数少”当作唯一入选条件。模型必须至少具备明确
的端侧部署路线和结构化调用定位，否则只会扩大 benchmark，而不会回答产品问题。

## 4. 当前 LMDJ 表面对小模型意味着什么

### 4.1 真实 MCP 表面不是自然语言 UX Contract

基线提交中的 `apps/core-mcp/lmdj_core_mcp/server.py` 注册了 30 个工具：

- 9 个 query；
- 21 个 command。

这些工具是自动化 Host 表面，不是专门给自然语言用户设计的高层意图目录。它同时包含：

- `project.inspect`、`sample.inspect` 等相对适合语言查询的操作；
- `sequence.settings.update`、`pattern.create` 等可能映射用户意图的命令；
- `sample.import.begin/chunk/commit/abort` 等传输协议步骤；
- `sequence.record.event` 等实时会话内部动作；
- `sequence.recovery.discard`、`provider.select/run` 等需要更强权限边界的命令。

把完整 30-tool 表直接交给模型，会把产品不应暴露的内部步骤和高风险命令一起变成候选。
Needle 的 top-five retrieval 只能减少上下文工具数量，不能替 LMDJ 判断权限和产品语义。

### 4.2 用户字段与 Host 权威字段必须分开

当前 MCP Schema 中大量必填字段不应由模型生成：

| 字段类别 | 示例 | 权威来源 |
| --- | --- | --- |
| Workspace 定位 | `project_path` | Host 当前 Workspace |
| 幂等身份 | `command_id`、`import_token`、`session_id` | Host / Facade session owner |
| 并发控制 | `expected_revision` | 当前 Project Truth revision |
| 实体身份 | `asset_id`、`pattern_id` | Project Truth 查询与显式解析 |
| 运行时锚点 | `runtime_frame`、`input_sequence` | Runtime / input sequencer |
| 内容副本证明 | `byte_length`、SHA-256、sidecar | Artifact owner / import path |

用户可能说出的字段只有 BPM、Bars、Bank/Pad、Swing、Quantize、Trigger Mode 等少数值。
因此不能要求小模型直接生成完整 MCP arguments；它应只生成一个较小的 Intent Draft，
Host 在确认后按当前权威状态补齐剩余字段。

### 4.3 Application Facade 边界保持不变

LMDJ 当前不变量要求所有 Host 只通过 Application Facade 使用 Core，不能解析 Project
Bundle 或绕过 Command Handler。增加模型不会创造新的特权路径：

- 模型不是 Facade；
- 模型不是 Command Handler；
- 模型输出不是 Project Truth；
- 模型 confidence 不是权限；
- grammar-valid JSON 不等于语义合法；
- 工具选择正确不等于用户已经确认写入。

如果未来实施，模型只应存在于 Host 输入适配层或一个明确的外部建议组件中。本文不批准
新的 Provider 或 Capability；究竟由 Host 本地组件还是 Provider 承载，需要在 Spike 后
根据可替换性、模型身份、执行平台和产品入口另行设计。

## 5. 推荐的数据流

### 5.1 第一阶段：只生成，不执行

```text
用户文本
  → 输入清洗与 locale
  → model-facing 高层工具投影
  → Needle / 对照模型
  → IntentDraft
  → 独立 Validator
  → 记录建议、正确答案和失败类型
  ✕ 不调用任何 MCP tool
```

第一阶段只回答模型是否能理解 LMDJ 语言，不产生 Project mutation，不下载用户音频，不访问
Project Bundle，也不执行 query。即使模型 SDK 提供自动执行的 `run()`，Spike 也只调用返回
原始建议的低层接口或等价机制。

### 5.2 可能的后续产品流

只有 Spike 通过且产品另行批准后，才讨论：

```text
用户文本 / 已批准的语音转写
  → IntentDraft {intent, user_arguments, evidence_spans, risk_class}
  → Schema + range + enum 校验
  → 实体解析（只查 Project Truth）
  → 显示预览、影响范围和缺失字段
  → 用户确认 command；query 可按独立策略处理
  → Host mint command_id / 读取 expected_revision / 注入 project_path
  → Application Facade 或现有 MCP Host
  → Typed Result
```

`IntentDraft` 只是研究中的概念名，不是已批准 Contract。若后续需要跨语言或跨进程持久化，
必须另立 Contract 评审；不能把本文示意直接实现成公共 `lmdj.intent.v1`。

### 5.3 风险分级

Spike 至少区分三类：

| 风险类 | 示例 | Spike 行为 | 未来最低门禁 |
| --- | --- | --- | --- |
| Query | “看看 Bank A 第三个 Pad” | 只记录建议 | 仍需 Project 与实体解析；是否自动执行另评审 |
| Command | “把速度改到 96” | 只记录建议 | 必须显示结构化预览并确认 |
| Refuse / unsupported | “删除所有项目”“把这首歌变好听” | 应拒绝或标记无工具 | 不得降级到相近 command |

模型把 Query 错分成 Command 是比普通 intent 错误更严重的风险。评估报告必须单独列出
cross-risk confusion，不能只给一个总体准确率。

## 6. LMDJ 适合与不适合的用例

### 6.1 适合进入 Spike

| 用户表达 | 目标 Intent Draft | 为什么适合 |
| --- | --- | --- |
| “把速度调到 96” | `sequence.settings.update {bpm: 96}` | 数字与范围清晰，Facade 已有对应操作 |
| “打开摇摆，设成 58%” | `{swing_percent: 58}` | 参数是有界整数，可受 grammar/range 限制 |
| “建一个四小节 Pattern” | `pattern.create {bars: 4}` | Bars 是固定枚举；ID 由 Host 生成 |
| “看看 B 组第 3 个 Pad” | `sample.inspect {bank: 1, pad: 2}` | 适合测试自然语言到零基索引映射，但必须明确 UI 与技术索引 |
| “现在有哪些 Provider？” | `provider.list {}` | 只读查询，适合验证工具路由 |
| “把这个 Pad 改成 Gate” | `sample.update_pad {trigger_mode: gate}` | 枚举明确，但目标 Pad 必须由 UI selection 提供而非模型猜测 |

### 6.2 不应交给模型

- 自动生成 `command_id`、UUID 或 revision；
- 从模糊称呼猜测 `asset_id` 或 `pattern_id`；
- 直接执行 import chunk、record event 等协议内部步骤；
- 未经确认 discard recovery、覆盖 Pattern 或选择 Provider；
- 把“更有 Groove”“更好听”硬映射到任意命令；
- 在 Audio Thread 或实时演奏路径逐 Token 推理；
- 用模型自由文本替代 Typed Error；
- 在同一次 Attempt 失败后静默切换模型或 Provider。

### 6.3 与 Composition Assist 的关系

Composition Assist 可以由规则、概率模型、传统模型或 AI Provider 实现，但 Needle 2 类模型
不负责创作候选 Pattern。它只能把“给我一个稀疏一点的鼓 Pattern”解析成未来某个已批准
Capability 的参数草案。真正候选必须进入 Candidate 流程，用户试听并采纳；模型输入入口
不能获得覆盖用户演奏的额外权限。

## 7. 受控 Spike 设计

### 7.1 固定比较对象

第一轮建议：

1. 确定性规则 parser；
2. 小型 intent classifier/MLP；
3. Needle 2 原始权重；
4. FunctionGemma 270M 原始权重；
5. LFM2.5-230M 原始权重。

第一轮不微调。先判断原始模型、工具投影和 Schema 是否值得进一步投资。若某模型只有微调后
才有合理表现，第二轮必须冻结训练集、验证集、测试集、adapter hash 和训练参数。

### 7.2 模型面对的工具表

不要一次暴露全部 30 个 MCP 工具。至少做两个受控条件：

- `raw-mcp`：只用于证明原始表面的困难，仍删除所有 Host-owned 字段；
- `high-level-6`：六个高层 intent，使用面向用户的描述和最小参数。

两组都只输出建议。A/B 的目标是判断问题来自模型能力还是工具表设计，不是借简化工具名
掩盖错误。

### 7.3 语料矩阵

建议至少 240 条冻结 utterance，按语义模板切分，不能把同一句近义改写分到训练和测试两边：

| 类别 | 最低数量 | 覆盖 |
| --- | ---: | --- |
| 明确 Query | 40 | Project、Pad、Provider、Attempt |
| 明确 Command | 80 | BPM、Swing、Quantize、Pattern、Pad playback |
| 缺失参数 | 30 | 未指明 Pad、Bars、目标值 |
| 歧义表达 | 30 | “快一点”“第三个”“当前这个” |
| Unsupported / refuse | 40 | 音频分析、删除全部、开放聊天、越权 |
| 对抗与 Schema 注入 | 20 | 要求忽略工具表、输出任意 JSON、伪造 ID |

每类同时覆盖简体中文、英文和中英混合。LFM2.5 明确声明中文；Needle 2 与 FunctionGemma
是否满足中文必须由本语料实测，不能从通用模型家族宣传推断。

### 7.4 指标必须分开

| 指标 | 定义 |
| --- | --- |
| Tool routing exact match | 选中的 intent/tool 是否准确 |
| Risk-class accuracy | `query/command/refuse` 是否准确 |
| Cross-risk confusion | Query→Command、Refuse→Command 等高风险错分数量 |
| Schema validity | 输出是否符合 model-facing Schema |
| Argument exact match | 用户字段是否逐项正确，包括 UI/零基索引 |
| Evidence grounding | 每个参数是否能指回输入文本或明确 UI context |
| Hallucinated authority fields | 是否生成未提供的 ID、路径、revision、runtime frame |
| Refusal precision/recall | 无工具输入是否可靠拒绝，正常输入是否被误拒 |
| Determinism | 同一输入、模型、runtime、seed 的字节结果是否一致 |
| Cold/warm latency | 初始化和连续调用的 p50/p95/p99 |
| Peak RSS / package bytes | 每个平台独立测量，不使用 vendor 宣传替代 |
| Offline behavior | 预置完整产物后是否确实零网络依赖 |

总体准确率不能掩盖风险错分。grammar-valid 也不能掩盖错误工具、错误数值或错误实体。

### 7.5 初始 Stop Conditions

以下任一成立，第一轮即不进入产品设计：

- 任一模型要求直接执行工具才能完成评估；
- 不能在模型表面移除 Host-owned 字段；
- 出现 Refuse→Command 的稳定错误且无确定性外部门禁可消除；
- 中文核心命令明显落后且需要超出项目收益的专用语料；
- Web/WASM 或目标 Native Host 的实际包体、峰值内存、冷启动不可接受；
- License、模型权重再分发或 telemetry 行为无法满足发布要求；
- 简单规则/MLP 基线已达到相同效果，生成模型没有可证明的产品收益。

达到门槛只允许进入“产品入口与 Contract 是否值得设计”的下一轮评审，不自动批准集成。

## 8. 模型身份、许可证与供应链

### 8.1 Model Identity

若任何模型进入 Provider 或正式产品路径，必须按
[Version Management](../governance/version-management.md)记录：

- model id 与版本；
- 精确权重或 binary artifact SHA-256；
- tokenizer / grammar / runtime 版本；
- 量化格式和参数；
- fine-tune adapter 与训练配置身份；
- Provider SemVer、Capability Contract、输入/输出 Artifact hash。

不能记录 `latest`、模型家族名或下载 URL来替代精确身份。Needle 把模型烘进 engine binary
并不会消除 Model Identity；相反，engine 与权重组合 Artifact 的 hash 更重要。

### 8.2 许可证不是同一档

| 候选 | 当前公开许可 | 研究要求 |
| --- | --- | --- |
| Needle 2 | Apache-2.0 | 核对 engine、weights、Python package 与训练数据声明是否一致；保留 notices |
| FunctionGemma 270M | Gemma Terms | 在再分发、微调和产品发布前单独法律/许可审核 |
| LFM2.5-230M | LFM Open License v1.0 | 在再分发、量化、微调和商业产品使用前单独审核 |
| 自有规则/MLP | 由代码、语料、encoder 分别决定 | 不能因分类头自有就忽略上游 embedding/训练语料许可 |

本文只记录模型卡当前展示的许可标签，不作法律意见。

### 8.3 网络与 telemetry

“推理离线”不等于“安装、首次初始化、模型下载、错误报告和 telemetry 全部离线”。Spike
必须在一次准备完整产物后断网运行，并记录：

- 哪些包在安装时联网；
- 模型/engine 首次加载是否下载；
- 是否存在 telemetry 环境开关及默认值；
- 禁用网络后功能、错误和启动时间；
- Web 版本是否请求 CDN、WASM 或 worker 资源。

正式产品不得依赖运行时自动下载一个漂移的“latest”模型。

## 9. 推荐路线

### Phase 0：文档与语料

- 冻结高层六工具投影；
- 明确 model-owned 与 Host-owned 字段；
- 建立 240 条中英文语料和 risk labels；
- 写确定性规则 parser 作为第一个 baseline。

### Phase 1：只读本地 Benchmark

- 三个生成模型 + MLP/规则基线；
- 永不执行 MCP；
- 报告 routing、risk、arguments、refusal 和资源测量；
- 固定模型与 runtime artifact hash。

### Phase 2：Shadow Mode

只有 Phase 1 通过后，在开发 Host 中旁路记录建议；真实操作继续由现有 UI/CLI/MCP 发起。
模型建议不进入 Project、Attempt 或 Candidate。

### Phase 3：单独产品决策

只有 Shadow Mode 证明存在真实用户价值后，才决定：

- 是否增加自然语言或语音入口；
- 是否需要新的 Intent Draft Contract；
- 模型属于 Host 组件还是 Provider；
- Query 与 Command 的确认策略；
- Web、Native 与离线分发范围；
- Product Build、Module、Provider、Contract 与 Portal 影响。

## 10. 最终建议

Needle 2 值得研究，不是因为它“能做音乐”，而是因为它把一个窄而有价值的问题压到端侧：
把语言可靠地映射成受 Schema 约束的工具草案。

对 LMDJ，最优先验证的不是聊天体验，而是三件事：

1. 六个高层音乐操作在中英文下能否稳定路由和抽取参数；
2. 模型是否能可靠拒绝越权、缺参和不支持的请求；
3. 其体积、延迟和准确率是否明显优于规则 parser 或小型 MLP。

当前推荐顺序：

1. **Needle 2：第一 Spike 候选**，因为尺寸、强约束 JSON 和工具检索与问题最匹配；
2. **FunctionGemma 270M：专用微调上限对照**，不是默认成品；
3. **LFM2.5-230M：中文和通用 agentic 能力对照**；
4. **规则 + MLP：必须保留的简单基线**。

在实测之前，唯一可以批准的是研究。不能批准模型执行命令，不能把 vendor benchmark 写成
LMDJ 事实，也不能因为 JSON 合法就把模型放进 Project mutation path。

## 11. 研究边界、版本与文档影响

- 资料检索日期：2026-09-01。模型卡、权重、runtime 和许可可能变化；任何 Spike 必须锁定
  精确 revision 与 Artifact hash。
- 本文中的 Needle 2 尺寸、内存与速度均为上游自报，未由 LMDJ 当前机器或目标 Host 验证。
- 本文没有创建或批准 Intent Contract、Capability、Provider、Host、Module、Assembly 或
  Product Build，也没有把自然语言控制加入产品路线图。
- Version impact: none。本文只增加研究文档，不改变 Product、Module、Provider、Contract、
  Model Identity、Assembly 或运行时行为。
- Documentation impact: none。本文不改变 Architecture Portal 当前事实或源图；后续若批准
  产品入口、Provider 或 Product Assembly 变更，必须在同一实施 Task 更新对应 Portal 路由。

## 12. 主要来源

### Needle 2

- [Needle 2 model card](https://huggingface.co/Cactus-Compute/needle2)
- [Needle source, APIs, fine-tuning and export](https://github.com/cactus-compute/needle)
- [A Controlled Study of Attention-Only Transformers](https://arxiv.org/abs/2607.18363)

### 对照模型

- [FunctionGemma 270M model card](https://huggingface.co/google/functiongemma-270m-it)
- [LFM2.5-230M model card](https://huggingface.co/LiquidAI/LFM2.5-230M)
- [LFM2 Technical Report](https://arxiv.org/abs/2511.23404)

### LMDJ 当前权威

- [Playable Beat Instrument Core Redesign](../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
- [Version Management](../governance/version-management.md)
- [`apps/core-mcp` production tool table](../../apps/core-mcp/lmdj_core_mcp/server.py)
