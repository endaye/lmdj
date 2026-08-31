# LMDJ Stage 12 First Capability and ArtifactSource Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是
[#467](https://github.com/endaye/lmdj/issues/467) 的设计半部：选定首个正式
结构化字节消费方、锁定其 Capability Contract 文档形状，并设计 provider-sdk
的输入 `ArtifactSource` 与输出字节边界。实施计划与实施 Issue 拆分按 #467
验收另行落笔，不在本文。本文不实现任何 SDK API 或 Provider。

评审修正（2026-08-31）：原草案的旧三参 `run` 默认委托无法让输入消费方
获得字节，也错误地把不兼容执行 ABI 记为 MINOR；本文改为 provider-sdk
`2.0.0` 的显式 Provider v2 执行接口。输入由 Artifact owner 交给 SDK 私有
staging，校验后以不可变拥有型 handle 交给 Provider；结构化输出验证则在
Attempt 终态持久化前由执行路径调用消费方拥有的 validator。

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
| 2026-08-24 字节访问决策（#206） | 输入侧是与 `ArtifactSink` 对称的 `ArtifactSource`，随 Provider v2 执行上下文传入，仅能解析本次 `CapabilityRequest` 显式声明并经 SDK 校验的输入端口；输出侧字节口同落 provider-sdk，同一次评审；`ArtifactRef` 不加 Schema provenance，`lmdj.capability.v2` 不升级；选项 C（parameters 传路径）永久否决；analysis-bench 的 Host 注入桥接不得毕业。 |
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
| S12C-D4 | determinism = `deterministic`：同输入 Artifact + 同 parameters 必须字节一致输出。progress_events = `["analyzing"]`。errors 只引用现有公开 code：`["INVALID_ARGUMENT", "NOT_FOUND", "PROVIDER_FAILED", "UNSUPPORTED_AUDIO", "IO_ERROR"]`；稳定细因用 `details.reason = input_binding_invalid|input_artifact_unavailable|input_artifact_mismatch|input_artifact_too_large|source_audio_unsupported|output_contract_invalid|output_schema_invalid`。resources = cpu 级并声明 `memory_mib`。execution 声明 `timeout_ms`/`max_attempts`。policy 按既有词表声明本地执行、无网络权限。 | capability.v2 必备字段与当前封闭 Error Contract |
| S12C-D5 | provider-sdk `2.0.0` 定义版本化 `ProviderRunContextV2`，包含 `attempt_id`、只读 `CapabilityRequest`、`ArtifactSource` 与 `ArtifactSink`；`Provider::run(ProviderRunContextV2)` 取代旧三参接口，不提供忽略 source 的默认委托。`ArtifactSource(port, occurrence)` 返回 `Result<ArtifactInput>`；`ArtifactInput = {ArtifactRef ref, shared_ptr<const vector<byte>> bytes}`，不返回借用 `span`。`occurrence` 从 0 起。resolver 只在本次 `run` 可调用；已返回 handle 自拥有不可变 bytes，不产生悬空视图。 | 首个真实输入消费方要求；公开执行 ABI 必须诚实版本化 |
| S12C-D6 | 字节 custody 与 TOCTOU：provider-sdk v2 的 execution ingress 接受 owner 提供、仅在该次调用有效的 `ArtifactByteResolver(ArtifactRef) -> Result<shared_ptr<const vector<byte>>>`；AttemptStore 只能在 request/capability binding 校验后，以每个绑定的完整 ArtifactRef 调它，resolver 本身永不传给 Provider 或持久化。SDK 随即复制或冻结到 attempt 私有、不可变 staging，验证 sha256 + byte_length，再只为已声明且已绑定的 `(port, occurrence)` 构造 Provider-facing `ArtifactInput`。哈希只是身份与验证值，绝不用于猜测 Host 私有路径。Provider 无法取得 owner 路径、Workspace 根或可变 buffer。owner 无字节 → `NOT_FOUND` + `details.reason = input_artifact_unavailable`；哈希/长度不符 → `IO_ERROR` + `details.reason = input_artifact_mismatch`；`run` 均不调用。 | 决策点 1「AttemptStore 在调用前校验」与 artifact-port 权限模型 |
| S12C-D7 | 有界内存：v2 首版接受整段、拥有型 bytes；SDK staging 上限取 capability `resources.memory_mib`、Host manifest 输入字节上限与本次执行可用预算的最小者，分配前按声明长度 fail closed（不 OOM）。流式 chunk 读取是具名后续能力；若 `stem.split` 需要，必须以新的版本化执行上下文/API 评审，不能静默改变 `ArtifactInput` 语义。 | 长素材配额已有 D1 边界 |
| S12C-D8 | 输出侧确认既有 `ArtifactSink` 是正式输出字节口，但 sink 产出先进入 attempt 私有未发布 staging：它只接受本次 capability 声明的输出端口与 media_type，每端口计数不得超过 `max_count`，并可立即返回按 bytes 计算的暂定 ArtifactRef；`run` 成功返回时 required 端口必须齐全，否则 Attempt 失败；`run` 返回后 sink 失效。只有 S12C-D9 验证全通过，SDK 才原子发布 blobs，并把全部 outputs 同时记为 `minted_outputs` 与 `candidate_outputs`。 | 决策点 2；terminal-attempt-v2 成功态不变量 |
| S12C-D9 | Schema 校验归属：SDK 通用层只拥有端口、数量、media type 与哈希门禁；Artifact Schema validator 由消费方模块拥有并在 capability 注册时显式注入 AttemptStore execution。Provider 返回成功后、写 terminal Attempt 或 CandidateIndex 之前，执行路径对所有 required outputs 调 validator。任一非法输出使 Attempt 以 `PROVIDER_FAILED` + `details.reason = output_schema_invalid` 终结；未发布 staging 不 mint Artifact，terminal v2 的 `minted_outputs`/`candidate_outputs` 均为空，审计证据由 error、provider/request identity 承担。坏 bytes 不得成为 Candidate 或 Project 输入。 | 决策点 3；终态证据不能先于有效性判定 |
| S12C-D10 | 兼容与迁移：这是 provider-sdk `1.x → 2.0.0` 的 MAJOR。所有 Provider、Registry adapter、AttemptStore、proof Provider、Host 与 mocks 必须在同一实施序列迁移到 Provider v2；Registry 不注册 v1 Provider，产品路径没有双 ABI 自动回退。选项 B 内嵌字节的 proof Provider 可迁移为 v2 后暂时不调用 source，但这不构成正式 Provider 豁免。Product 身份整合与 #436 串行。 | 版本政策：公开 API/ABI 不兼容即 MAJOR |
| S12C-D11 | fail-closed 矩阵（全部类型化、零 Project 变更）：输入缺失/哈希不符/超长（S12C-D6/D7）；错端口/未声明端口/occurrence 越界（S12C-D5）；输出错端口/超计数/required 缺失（S12C-D8）；超时与资源超限走 execution 声明；重复 binding 在请求校验期拒绝。 | 规格 §18.1 |

## 4. Contract 影响

- 新增：`sample.slice.v1` capability 文档（`lmdj.capability.v2` 的实例，
  仓库首个）+ `lmdj.slice-points.v1` Artifact Schema。
- 不改：`lmdj.capability.v2` schema 本身、`ArtifactRef` 三元组、
  `lmdj.project.*`。
- provider-sdk：`2.0.0` MAJOR（Provider v2 执行接口 + `ArtifactSource` +
  AttemptStore staging/validator）；旧执行 ABI 不保留在产品路径。
- 不扩张 `lmdj.error.v1`：只用现有 code，新增稳定 lowercase
  `details.reason` 承载本文细因。

## 5. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. conformance：capability 文档与 `lmdj.slice-points.v1` fixture 过
   `tests/conformance/schema_contract_test.py`（合法 + 每条非法规则）。
2. `ArtifactSource`：声明端口可读且拥有型 bytes 与 binding 一致；多个
   occurrence 隔离；未声明端口/错 occurrence/run 后解析逐条 fail closed；
   已返回 handle 无悬空引用且不可变。
3. custody：ingress resolver 只收到已校验 binding 的完整 ArtifactRef，且
   永不泄漏给 Provider；owner unavailable、哈希/长度不符与超长输入使 `run`
   不被调用；测试证明 SDK 不从 hash 或 Host 私有布局重建路径。
4. sink 边界：错端口、超计数、required 缺失、run 后调用逐条失败。
5. 确定性：参考 Provider 对 #466 代表性 fixture 双跑字节一致。
6. MAJOR 迁移：全部 Provider/mock 只实现 Provider v2；v1 实现不能注册，
   不存在双 ABI 自动回退。
7. 归属与顺序：SDK 通用层放行的坏 JSON 由消费方 validator 拒绝；terminal
   Attempt 写入前已是 `Failed`，两组 outputs 均为空，CandidateIndex 与
   Artifact Store 从未发布该输出；成功态两组 outputs 完全相等。

## 6. Version Management

Version impact: none——本文只是设计文档。实施计划必须分配：provider-sdk
`2.0.0` MAJOR 与其全部依赖级联、两个新 Contract 的初始版本、参考 Provider 的
module 版本；Product Build / Assembly / Portal 快照整合与 Stage 10
Task 10/11（#436/#438）串行。

## 7. Documentation Impact

Documentation impact: none——本次只修订 retained 设计文档，不改变当前
manifest 派生的 Portal 真相。实施时 Provider SDK、Capability Contract、
Provider、Assembly 的 Portal 路由由实施计划按实际身份变更声明。

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

### 8.7 用旧三参 `run` 的默认实现兼容 Provider v2

拒绝。默认忽略 source 会让“迁移成功”的 Provider 在首个真实消费方处必然失败，
同时掩盖公开 ABI 的破坏性变化。执行接口以 provider-sdk `2.0.0` 一次迁移。

## 9. 实施入口（前置条件）

1. #466 的代表性成功/失败 fixture 就位（小型、可再分发、合成）。
2. 本文评审通过后落笔实施计划：SDK API、conformance、参考 Provider、
   注册/Assembly 逐项拆 Issue，逐 Task 声明 Version 与 Documentation
   impact。
3. 采纳语义（候选可见、预览、commit）在 #471 的设计内，本文止步于
   Provider 字节边界。
