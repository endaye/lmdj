# LMDJ Stage 12 First Capability and ArtifactSource Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是
[#467](https://github.com/endaye/lmdj/issues/467) 的设计半部：选定首个正式
结构化字节消费方、锁定其 Capability Contract 文档形状，并设计 provider-sdk
的输入 `ArtifactSource` 与输出字节边界。实施计划与实施 Issue 拆分按 #467
验收另行落笔，不在本文。本文不实现任何 SDK API 或 Provider。

关联 Issue：[#472](https://github.com/endaye/lmdj/issues/472)（umbrella）、
[#467](https://github.com/endaye/lmdj/issues/467)、
[#466](https://github.com/endaye/lmdj/issues/466)（代表性 fixture 来源）、
[#471](https://github.com/endaye/lmdj/issues/471)（采纳边界，本文不越界）、
[#206](https://github.com/endaye/lmdj/issues/206)（已裁决的字节访问决策）。

## 1. 结论

首个正式结构化字节消费方选定为 **`sample.slice.v1`**：Provider 读取一个
PCM16 WAV 输入 Artifact，输出一份结构化切片点 JSON。它以最小的模型与权利
负担逼真地要求 2026-08-24 决策预留的全部机制——Provider 必须读输入字节
（`ArtifactSource` 的第一个真实消费方）、必须写结构化输出（输出边界与
消费方 Schema 校验归属的第一个真实检验），同时保持 deterministic 类别，
使 conformance 可以做字节级断言。

`stem.split` 不做首个消费方：checkpoint 选型、权利与资源问题（#466 语料、
`docs/prd/questions/production-separator-checkpoint.md`）会把 Contract
评审拖进模型评测；它成为第二个消费方，直接复用本文的机制。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 2026-08-24 字节访问决策（#206） | 输入侧是与 `ArtifactSink` 对称的 `ArtifactSource` 回调，随 `Provider::run` 传入，仅能解析本次 `CapabilityRequest` 显式声明并经 AttemptStore 校验的输入端口；输出侧字节口同落 provider-sdk，同一次评审；`ArtifactRef` 不加 Schema provenance，`lmdj.capability.v2` 不升级；选项 C（parameters 传路径）永久否决；analysis-bench 的 Host 注入桥接不得毕业。 |
| `lmdj.capability.v2` | capability 文档必备字段：ports（name/media_types/schema_id/schema_version/required/max_count）、determinism、progress_events、errors、resources、execution、policy；`capability_id` 形如 `sample.slice.v1`；port 名 `^[a-z][a-z0-9_]*$`。 |
| provider-sdk 现状 | `ArtifactSink = function<Result<ArtifactRef>(port, span<const byte>, media_type)>`；`Provider::run(attempt_id, request, sink)`；AttemptStore 已做端口/数量/media type 门禁、输入 binding（port+sha256）校验、attempt 证据（`minted_outputs`/`candidate_outputs`/`parameters_sha256`）。 |
| 2026-08-01 多端口决策 | 端口身份由显式端口声明承担；SDK 不做字节级 Schema 校验。 |
| 规格 §16/§18 | 禁止同一 Attempt 内静默回退；Attempt 是最小失败单元；Provider 失败属 Attempt 状态，永不改 Project。 |
| CLAUDE.md 不变量 | Provider 收到 Artifact 输入与 Artifact 输出 sink，永不收到可变 Project 或 bundle 路径。 |

## 3. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S12C-D1 | 首个正式消费方 = `sample.slice.v1`（§1 理由）。`stem.split.v1` 是第二个消费方，其 Contract 文档在 checkpoint 决策后按本文机制照抄成文。 | #466 语料边界 |
| S12C-D2 | `sample.slice.v1` Capability 文档：输入端口 `source_audio`（`audio/wav`，S8-D6 约束，required，max_count 1）；输出端口 `slice_points`（`application/json`，schema `lmdj.slice-points.v1`，required，max_count 1）。Provider 不输出切好的音频：切片点是结构化建议，实际切割由 Core 在采纳路径按 §5.2 确定性执行（#471 的 recipe 候选）。 | 输出小、确定性可断言、切割逻辑单一真相 |
| S12C-D3 | `lmdj.slice-points.v1` 是新的 Artifact Schema（Capability I/O Contract 层，独立 SemVer）：`{contract, source_sha256, frame_rate, points: [{frame, confidence?, label?}]}`，frame 为输入 WAV 的整数帧索引、严格递增、越界非法。`source_sha256` 必须等于绑定输入的哈希，使输出自证其对象。 | §17.3 |
| S12C-D4 | determinism = `deterministic`：同输入 Artifact + 同 parameters 必须字节一致输出。progress_events = `["analyzing"]`。errors = `["PROVIDER_FAILED", "SOURCE_AUDIO_UNSUPPORTED"]`。resources = cpu 级并声明 `memory_mib`。execution 声明 `timeout_ms`/`max_attempts`。policy 按既有词表声明本地执行、无网络权限。 | capability.v2 必备字段 |
| S12C-D5 | 输入 API：`using ArtifactSource = std::function<foundation::Result<std::span<const std::byte>>(std::string port, std::uint32_t occurrence)>;` 与 `ArtifactSink` 同构（一次调用、整段字节）。`occurrence` 服务 `max_count > 1` 的端口，从 0 起。解析未声明端口、未绑定 occurrence、或在 `run` 返回后调用 → 类型化失败，Attempt fail closed。 | 决策点 1 的「对称」字面义 |
| S12C-D6 | 完整性与 TOCTOU：AttemptStore 在调用 `run` 前把每个输入 binding 的字节暂存进 attempt 私有区并验证 sha256 + byte_length；`ArtifactSource` 只从已验证暂存读。验证失败 → Attempt 以 `INPUT_ARTIFACT_MISMATCH` 类错误终结，`run` 不被调用。Provider 拿到的 span 生命周期 = 本次 `run` 调用。 | 决策点 1「AttemptStore 在调用前校验」 |
| S12C-D7 | 有界内存：v1 接受全驻留 span，上限 = capability 文档 `resources.memory_mib` 与 Host manifest 资源上限的较小者；超限输入在暂存阶段 fail closed（不 OOM）。流式 chunk 读取立为具名后续能力（stem.split 若需要长素材再支付），API 预留不改签名的演进空间（新增回调类型，不改 `ArtifactSource`）。 | 长素材配额已有 D1 边界 |
| S12C-D8 | 输出侧确认既有 `ArtifactSink` 就是正式输出字节口，本次评审补齐其边界语义：sink 只接受本次 capability 声明的输出端口与 media_type；每端口计数不得超过 `max_count`；`run` 成功返回时 required 端口必须已产出，否则 Attempt 失败；`run` 返回后 sink 失效。sink 产出即 content-address（现状），AttemptStore 记 `minted_outputs`/`candidate_outputs`。 | 决策点 2 |
| S12C-D9 | Schema 校验归属：SDK 只做端口/数量/media type/哈希门禁（现状不变）；`slice_points` 的字节级 Schema 校验由消费方所有——采纳层（#471）在候选可见前按 `lmdj.slice-points.v1` 验证，非法输出把 Attempt 判为 `Failed`（类型化），永不把坏 JSON 暴露给用户或 Project。conformance 套件同时测两层，防止归属混淆。 | 决策点 3 |
| S12C-D10 | 兼容与迁移：`Provider` 增加新虚函数 `run(attempt_id, request, ArtifactSource, ArtifactSink)`，默认实现委托旧三参 `run`（忽略 source）——既有 proof Provider（选项 B 内嵌字节）与全部 mock 不改一行即编译通过，按各自节奏迁移。provider-sdk 支付 MINOR；依赖级联（proof providers、依赖 SDK 的 Host/测试）在实施计划逐项列出，Product 身份整合与 #436 串行。 | 决策点 4 的 MINOR 承诺 |
| S12C-D11 | fail-closed 矩阵（全部类型化、零 Project 变更）：输入缺失/哈希不符/超长（S12C-D6/D7）；错端口/未声明端口/occurrence 越界（S12C-D5）；输出错端口/超计数/required 缺失（S12C-D8）；超时与资源超限走 execution 声明；重复 binding 在请求校验期拒绝。 | 规格 §18.1 |

## 4. Contract 影响

- 新增：`sample.slice.v1` capability 文档（`lmdj.capability.v2` 的实例，
  仓库首个）+ `lmdj.slice-points.v1` Artifact Schema。
- 不改：`lmdj.capability.v2` schema 本身、`ArtifactRef` 三元组、
  `lmdj.project.*`。
- provider-sdk：MINOR（新 run 重载 + `ArtifactSource` 类型 + AttemptStore
  暂存校验），无破坏性变更。

## 5. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. conformance：capability 文档与 `lmdj.slice-points.v1` fixture 过
   `tests/conformance/schema_contract_test.py`（合法 + 每条非法规则）。
2. `ArtifactSource`：声明端口可读且字节与 binding 一致；未声明端口/错
   occurrence/run 后调用逐条 fail closed。
3. 暂存校验：哈希不符与超长输入使 `run` 不被调用且 Attempt 类型化失败。
4. sink 边界：错端口、超计数、required 缺失、run 后调用逐条失败。
5. 确定性：参考 Provider 对 #466 代表性 fixture 双跑字节一致。
6. 迁移：既有 proof Provider 与 mock 不修改即通过全部既有套件。
7. 归属：SDK 放行的坏 JSON 在消费方校验被拒且 Attempt 记 `Failed`。

## 6. Version Management

Version impact: none——本文只是设计文档。实施计划必须分配：provider-sdk
MINOR 与其全部依赖级联、两个新 Contract 的初始版本、参考 Provider 的
module 版本；Product Build / Assembly / Portal 快照整合与 Stage 10
Task 10/11（#436/#438）串行。

## 7. Documentation Impact

Documentation impact: required——本文自身是新增 retained 设计文档；实施时
Provider SDK、Capability Contract、Provider、Assembly 的 Portal 路由由
实施计划声明。本文不改当前 manifest 派生的 Portal 真相。

## 8. 拒绝的替代

### 8.1 parameters 携带路径或 fixture 根（选项 C）

已被 2026-08-24 决策永久否决，不再评审。

### 8.2 给 Provider ambient 文件系统或 Project/bundle 访问

拒绝。正是 artifact-port 模型要消除的东西（CLAUDE.md 不变量）。

### 8.3 `ArtifactRef` 增加 Schema provenance / 升级 capability.v2

拒绝（决策点 3）。端口声明已承载 Schema 身份；本文没有发现需要推翻的新证据。

### 8.4 首个消费方选 stem.split

拒绝（§1）。把机制评审耦合进 checkpoint 选型与权利问题。

### 8.5 Provider 直接输出切好的 WAV

拒绝 v1（S12C-D2）。输出体积与切割真相双重问题：切割语义属于 Core 的
确定性派生路径，Provider 只交建议。

### 8.6 v1 就做流式读取 API

拒绝（S12C-D7）。首个消费方不需要；无消费者检验的流式 API 会冻结进 SDK，
与 2026-08-24 决策反对的「提前落地」同病。

## 9. 实施入口（前置条件）

1. #466 的代表性成功/失败 fixture 就位（小型、可再分发、合成）。
2. 本文评审通过后落笔实施计划：SDK API、conformance、参考 Provider、
   注册/Assembly 逐项拆 Issue，逐 Task 声明 Version 与 Documentation
   impact。
3. 采纳语义（候选可见、预览、commit）在 #471 的设计内，本文止步于
   Provider 字节边界。
