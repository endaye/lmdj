# Needle 端侧小模型工具调用可行性验证

> 日期：2026-09-01
>
> 文档状态：技术验证报告，不是已批准设计、实现计划或发布证明
>
> Needle 基线：`cactus-needle` PyPI `2.0.11`，原生引擎 `2.0.3`，源码提交 `ee221ce7c13579d9809209b979a9b7a50936614c`（`cactus-compute/needle`，Apache-2.0）；权重 `huggingface.co/Cactus-Compute/needle2`
>
> LMDJ 基线：`5a551a0a69be304edbefe982979c5c381fcff4c3`（Product Build `1.0.40.0`）
>
> 配套代码：[`tools/needle-spike/`](../../tools/needle-spike/README.md)。该目录是与产品平行的技术验证，不接入 `scripts/core.sh`，不链接任何 Core Module，不声明 Capability，不改动 Project Truth。
>
> 测量环境：WSL2（Linux 5.15）、20 核、31 GiB、纯 CPU（未使用本机 RTX 4060 Ti；`cactus-needle` 运行时不依赖 GPU）

## 1. 结论先行

### 1.1 总体判断

一个 45M 参数、14 MB、峰值 71 MB 内存的端侧模型，**能在 LMDJ 的真实 MCP 契约上产出 100% schema 有效的调用载荷**，但**不能独立决定要执行哪条命令**。

> 它的可用位置是「意图候选生成器」，不是「命令执行者」。让它填参数是成立的；让它选动作并自动派发，在本次测量下会改写 Project Truth。

三条支撑：

1. **参数层已经成立。** 把 Host 持有的字段（`project_path`、`command_id`、`expected_revision`、会话句柄、全部 UUID 实体引用）从模型面前拿掉之后，模型只填「人真的会说出口的字段」，合成后的载荷在 `apps/core-mcp` **同一个** `validates` 下 25/25 全部通过，三次重复完全一致。

2. **动作选择层不成立。** 路由准确率 24/30（80%），且错误不是均匀噪声——它把只读提问变成破坏性命令：`"am I still recording?"` 路由到 `stop_recording`，`"tell me what's loaded on pad 9"` 路由到 `reset_pad`。

3. **模型自报的 confidence 不能当安全闸。** 在本意图集上它与正确性**反相关**：错误调用中位数 0.995，正确调用只有 0.79–0.86。按阈值放行恰好会放行最危险的那批。且该分数在多次运行间并不稳定，而路由决策本身是稳定的。

### 1.2 建议等级

| 建议 | 等级 | 依据 |
| --- | --- | --- |
| 以 `query`/`command` 面作为派发闸，`command` 一律需确认 | **建议采纳** | §4.3；MCP 工具表已自带该标签，本次两条危险误路由全部被它拦下 |
| 模型面使用动词别名，而非 MCP 线名 | **建议采纳** | §4.1；13–22 个百分点，成本是一张映射表 |
| Host 持有字段与 UUID 引用不进模型面 | **建议采纳** | §3；同时是正确性与上下文预算的必要条件 |
| 以 confidence 阈值决定是否自动派发 | **建议否决** | §4.2；本次测量下反相关 |
| 让模型直接面对 `lmdj.sample.update_pad` 原始 schema | **建议否决** | §4.4；绝对状态 schema 迫使模型为未提及字段编值 |
| 现在就把端侧 NL 控制列入产品路线 | **建议暂缓** | §5；名称解析缺口未解，且本报告不构成产品决定 |

### 1.3 本报告不承诺的事项

- 不构成把自然语言控制纳入 LMDJ 产品范围的决定；
- 不构成 Provider、Capability 或 Contract 的新增或变更提案；
- 不代表已评估 Needle 在移动端、WASM 或 ESP32 目标上的表现；
- 不代表微调路径（`cactus-needle[train]`、JAX）已验证。

### 1.4 本报告刻意未决的产品问题

验证过程中浮出四个产品级问题。它们不在实施 Task 内决定，已按
[open-questions](../prd/open-questions.md) 的约定各自建档：

| 问题 | 档案 |
| --- | --- |
| 自然语言控制属于哪个用户、哪个 Stage？ | [nl-control-target-user-and-stage](../prd/questions/nl-control-target-user-and-stage.md) |
| 离线可用是硬需求还是可选便利？ | [offline-operation-requirement](../prd/questions/offline-operation-requirement.md) |
| 模型产出的 Pattern 候选是否越过产品定位边界？ | [model-generated-pattern-candidates](../prd/questions/model-generated-pattern-candidates.md) |
| AI 提议的状态变更：确认在前还是撤销在后？ | [ai-change-confirm-or-undo](../prd/questions/ai-change-confirm-or-undo.md) |

其中「离线是否硬需求」是决定性的一条：若答案为否，则云端一个模型即可覆盖全部
讨论过的任务，端侧模型没有存在理由，本报告的价值只剩 §4.4 与 §4.1 两条关于
LMDJ 自身的结论——它们与是否采用 Needle 无关。

## 2. 研究范围与证据口径

### 2.1 本次回答的问题

1. Needle 是什么，能否在本地跑起来，代价多少。
2. LMDJ 现有的 MCP 工具表能否直接作为它的工具面。
3. 它产出的调用能否通过 LMDJ 生产 schema 校验。
4. 哪些工程选择实际影响准确率。
5. 若要接入，安全边界应画在哪。

### 2.2 证据标签

- **[实测]**：在本机运行 `tools/needle-spike/` 得出，附具体数字，可用同一命令复现。
- **[源码]**：直接读取 `cactus-needle 2.0.11` 已安装包或 LMDJ `5a551a0` 源文件得出，含文件路径。
- **[宣称]**：上游 README 表述，本报告单独核查。

### 2.3 可复现性

同一机器上**路由决策稳定**：连续四次全新运行，路由/schema/参数三组比值与那 6 条失败语句的具体集合每次完全相同。**[实测]**

但 `confidence` 标量**不稳定**：同一条语句路由结果不变的情况下，该分数在多次运行间会变（正确组中位数在 0.787–0.857 之间移动，错误组稳定在 0.995）。这是 §4.2 判定该分数不可用的第二条理由——它连自身可复现性都不具备。**[实测]**

## 3. Needle 是什么

### 3.1 形态与代价 **[实测]**

| 项 | 值 |
| --- | --- |
| 参数量 | 45M **[宣称]** |
| 分发物 | `libneedle.so` 单文件 14.3 MB，权重已编入 |
| 安装 | `pip install cactus-needle`；基础包不含 jax/numpy，仅 `huggingface_hub` 等 |
| 首次拉取 | 从 HF 取平台 wheel 解出 `.so`，本机 13.8 s，缓存于 `~/.cache/cactus-needle/2.0.3/` |
| Agent 初始化 | 15 工具面下约 1.1 s |
| 单轮延迟 | p50 508 ms，p95 3.4 s |
| 峰值 RSS | 71 MB |
| 吞吐 | prefill 约 500–1050 tps，decode 约 78–545 tps |

关键校正一条：上游把权重编进原生二进制，**推理不需要单独下载权重**。HF 仓库里 90 MB 的 `checkpoints/needle2.pkl` 是 JAX 微调 checkpoint，与推理路径无关。**[源码]** `needle/agent/fetch.py`

### 3.2 接口 **[源码]**

`needle/__init__.py` 通过 `ctypes` 绑定四个 C 函数：`needle_init(system, tools_json, tool_index_path)`、`needle_complete(text, max_new_tokens, buf, buflen)`、`needle_reset()`、`needle_load(blob, len)`。工具面允许直接传 JSON dict 列表，格式为 `{name, description, parameters}`——因此 LMDJ 的 MCP schema 可以原样喂进去，无需翻译层。

返回信封含 `type`、`function_calls`、`confidence`、`error_code`、`peak_ram_mb`、`decode_tps`。本验证一律调 `complete` 而非 `run`：只观察它「打算调什么」，不执行任何工具体，因此不产生任何状态变更。

### 3.3 遥测 **[源码]**

`needle/_telemetry.py` 在每次 `complete`/`run`/`extract` 时向一个 Supabase endpoint 发送匿名计数（事件名、版本、OS/arch、随机安装 id），后台守护线程 fire-and-forget。不含 prompt 或输出。可用 `NEEDLE_TELEMETRY=0`、`DO_NOT_TRACK` 或 `CI` 关闭。

`tools/needle-spike/` 的每个入口在 import 之前设置 `NEEDLE_TELEMETRY=0`，因此跑验证不会外发。

## 4. 实测结果

工具面取 `apps/core-mcp` 30 个工具中 15 个具备自然语言表述的子集（字节级导入分片、recovery 管道、原始 provider 派发没有口语形式，只出现在 `--surface full`）。意图集 30 条，其中 3 条是「不应触发任何工具」的对照项。

基线（动词别名 + 参数切分）：**[实测]**

```
routing           24/30 (80%)
  tool expected   22/27 (81%)
  silence wanted  2/3  (67%)
schema valid      25/25 (100%)
arguments correct 11/15 (73%)
latency ms        p50 508  p95 3418
peak rss mb       71.0
```

### 4.1 命名比工具数量重要得多 **[实测]**

| 工具面 | MCP 线名 | 动词别名 |
| --- | --- | --- |
| 15 工具 | 63% | **76%** |
| 8 工具 | 59% | **81%** |

把 `lmdj.sequence.settings.update` 换成 `set_tempo_and_groove` 值 13–22 个百分点；把工具面从 15 砍到 8 几乎不值钱。MCP 线名是点分命名空间，读起来是路径而不是动作，而该模型只能靠措辞路由。

结论：适配层必须自带一张模型面命名表。线名仍是权威，别名在派发前映射回去。

### 4.2 confidence 不能当闸 **[实测]**

| | n | 中位数（四次运行） | 极值 |
| --- | --- | --- | --- |
| 路由正确 | 24 | 0.787–0.857 | min 0.000 |
| 路由错误 | 6 | 0.995 | max 1.000 |

错误调用比正确调用更自信。多条完全正确的调用（`inspect_pad`、`set_pad_playback`、`set_tempo_and_groove`）confidence 为 0.000，而 `"am I still recording?" → stop_recording` 是 1.000。

叠加 §2.3 的观察：路由结果稳定而该分数会漂动，说明它不是「模型对该次判断的把握」的可靠读数。

上游文档说微调不更新 confidence head，因此该分数在微调权重下更不可用；**[源码]** `needle/__init__.py` 对此显式告警。但本次是**基础权重**，反相关不能归因于微调。合理解释是该 head 在训练分布（智能家居、可穿戴）之外未标定。

### 4.3 有效的闸是 `query`/`command` **[实测]**

LMDJ 的 `tool_table()` 已给每个工具标了 `surface: "query" | "command"`。**[源码]** `apps/core-mcp/lmdj_core_mcp/server.py:527`

以此为闸（`command` 一律需玩家确认，`query` 可自动执行）：

| | 动词别名 | MCP 线名 |
| --- | --- | --- |
| 误路由总数 | 6 | 10 |
| 其中作为 `command` 被拦下 | 2 | 7 |
| 误派发但只读、无状态变更 | 1 | 2 |

两条危险误路由（`reset_pad`、`stop_recording`）100% 被拦。剩下唯一逃出的误派发是 `"who wrote this software?" → list_providers`——读到一份无关列表，不改任何状态。

这条闸的性质值得强调：它不依赖模型自评，只依赖 LMDJ 自己早已声明的操作语义。

### 4.4 绝对状态 schema 迫使模型编值 **[实测]**

`lmdj.sample.update_pad` 的 `playback` 要求 5 个字段全部提供（`trim_start_frame`、`trim_end_frame`、`trigger_mode`、`gain_millidb`、`muted`）。**[源码]**

于是 `"set the tempo to 96"` 得到 `{bpm: 96, quantize_enabled: false, swing_percent: 75}`——bpm 对了，另两个是为满足 required 编出来的。

更能说明问题的是 `"mute pad 3"`。模型路由正确、`muted: true` 正确、`slot` 正确，schema 校验通过，但它同时给出 `gain_millidb: -60000`——那是该字段的下限。也就是说，一句「把 pad 3 静音」如果直接派发，除了静音还会把这个 pad 的增益推到底；等玩家取消静音时，pad 已经哑了。schema 校验完全看不出这个问题，因为每个值都合法。

命令面是绝对状态而非增量，这对 Project Truth 的确定性是正确设计。但它意味着自然语言适配层不能直连原始 schema：必须 read-modify-write（先 `inspect`，改动被提及的字段，再提交），否则每句「把 pad 3 调响一点」都会顺手重置该 pad 的其余参数。

### 4.5 上下文预算 **[实测]**

引擎有固定上下文预算，超出时返回 `error_code: "truncated"`、`error: "tool call truncated: token budget exhausted"`，`function_calls` 为空。抬 Python 侧 `max_new_tokens`（256→1024）**无效**——该预算是引擎内部的。

剥离 Host 字段与 UUID 引用把 15 工具面从 6585 压到 4861 字节（−26%）。即便如此，15 工具面仍处于预算边缘：本次仍有 3 条（quantize on/off、swing）落入截断，且 system prompt 长度会改变哪几条被截断。

因此工具面规模在这个模型上是**硬约束**，不是调参项。

机制来自上游架构：并行进行的案头研究
[Needle-class 端侧命令模型评估](2026-09-01-needle-class-on-device-command-models-for-lmdj.md)（PR #532）
记录 Needle 2 使用 **256-token 滑动窗口，工具作为固定 KV sinks**。这与本节实测
吻合，并解释了为何抬 `max_new_tokens` 无效——预算不是输出长度，而是被工具 sinks
占据之后剩下的那点总上下文。它也意味着「压缩 schema」的收益有上限：省下的每个
字节都直接兑换成可容纳的工具数，但窗口本身不会变大。

## 5. 与 LMDJ 的关系

### 5.1 可复用的既有资产

本验证没有为接入写任何新契约，全部复用现有物：

- `apps/core-mcp` 的 `tool_table()` 提供 30 个工具的 schema 与 `query`/`command` 语义；
- 同模块的 `validates()` 提供校验，因此测的是生产契约本身；
- `apps/core-mcp` 已是 Python 且已有 `c_api.Engine` ctypes 边界，若将来要端到端派发，路径已存在。

这也说明一件事：LMDJ 的 MCP 表面**已经**是一个可被小模型消费的工具面，不需要为它再造一层。

### 5.2 未解的最大缺口：名称解析

模型面拿掉了全部 UUID 引用，`HostContext` 里用固定桩值顶替。真实场景里「把那段 drum loop 放到 pad 5」需要把「那段 drum loop」解析成 `asset_id`——这是对当前 Project Truth 的检索问题，本验证完全没有触碰。

它比路由准确率更关键：路由 80% 可以靠确认闸兜住，名称解析错了则会把对的命令作用在错的对象上，而 schema 校验完全看不出来。

### 5.3 架构不变量的对照

若将来真要接入，本验证的形状与现有不变量一致：

- 模型不接收可变 Project，只接收工具 schema，输出候选调用——与「Provider 收 Artifact 输入与 Artifact 输出汇」的方向一致；
- 生成的载荷经 Application Facade 的既有命令面进入，Host 不解析 Project bundle；
- 模型身份（包 2.0.11 / 引擎 2.0.3 / 权重仓库）是必须记录的 Model Identity，`docs/governance/version-management.md` 已有该要求；
- 失败（截断、误路由、低置信）属于尝试状态，不进 Project Truth。

未对齐处：本验证以 `NEEDLE_TELEMETRY=0` 关闭外发，但若真接入产品，「推理默认离线、无任何外发」需要成为可验证的构建期属性，而不是一个环境变量约定。

## 6. 下一步（若继续）

按价值排序，均为独立可停止的实验：

1. **read-modify-write 适配**（§4.4）。让 `inspect → patch → submit` 成为 `update_pad` 类命令的唯一路径，消掉编值问题。成本小，收益直接。
2. **名称解析**（§5.2）。用当前 Project Truth 做候选集，模型只在候选里选，不生成标识符。这是最大缺口。
3. **微调**（`cactus-needle[train]` + 90 MB checkpoint + LMDJ 意图集）。最可能抬动 73% 参数准确率与 80% 路由准确率的一项，也是唯一需要 GPU 的一项。注意微调会使 confidence 恒为 `None`，但 §4.2 已判定该分数不可用，故不构成损失。
4. **移动/WASM 目标实测**。上游提供 16 个平台的预编译物，含 `wasm` 与 `android-arm64`；LMDJ 已有 Web Runtime，值得单独测一次浏览器内可行性。

## 7. 方法与可复核性

全部数字由 `tools/needle-spike/` 产出，命令见其 README。校验路径为：模型输出 → 剥离 Host 字段 → 合入 Host 半边 → `apps/core-mcp` 的 `validates` → 报告。测试分两层：`tests/tool_surface_test.py` 不需要引擎（纯切分与合成性质），`tests/router_smoke_test.py` 需要引擎且在缺失时 SKIP 而非 FAIL，因此干净检出不会因此引入网络依赖。
