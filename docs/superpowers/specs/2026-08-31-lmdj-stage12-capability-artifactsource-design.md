# LMDJ Stage 12 First Capability and ArtifactSource Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是
[#467](https://github.com/endaye/lmdj/issues/467) 的设计半部：选定首个正式
结构化字节消费方、锁定其 Capability Contract 文档形状，并设计 provider-sdk
的输入 `ArtifactSource` 与输出字节边界。2026-09-08 的待评审实施计划与本地 Issue 草稿见
[`2026-09-08-lmdj-stage12-capability-implementation.md`](../plans/2026-09-08-lmdj-stage12-capability-implementation.md)。
本文及该计划均未获批准；§10 列出实现前必须裁决的缺口。本文不实现任何 SDK API 或 Provider。

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


## 10. 2026-09-08 源码评审与待确认修订

状态：**提议，未批准**。下述文字纠正旧草案对现状与可执行性的描述；
不授予新 Contract 或并发语义的实现权。遇到与 §3 冲突的提议，先完成本节
具名决策，再按确认后的单一规则实施，不由工程 Task 任选一个版本。

### 10.1 当前实现证据与版本口径

基线为 `5eb314f52ea71c879a8a4e00f749135791c16879`。SDK manifest 为
`1.1.4`，其 `api_version: 2` **不代表** ProviderRunContextV2 已实现。
`provider.hpp` 仍为三参纯虚 `run`；`execute` 无 owner resolver 参数；
`ArtifactSink` 捕获 execute 的栈引用。终态协议已校验成功态
`candidate_outputs == minted_outputs`，失败态两者为空；输出先落私有
staging，之后 publish，再写 terminal。不能将这三步描述为一个已经存在的
跨文件原子事务。

当前 `validate_request` 对整个 request 的重复 sha256 拒绝，不只是同端口
重复；不同端口同 hash 也拒绝。此轮保留已有规则，放宽需要单独 Contract
评审。`occurrence` 应按原始 request 中同端口的出现次序绑定，不能按之后
用于审计序列化的排序重编号。

当前 Provider 返回的失败只接受 `PROVIDER_FAILED`；因此 §3 所列的
`UNSUPPORTED_AUDIO` 不能仅加进 descriptor 就自动贯通执行路径。当前
Registry 也没有消费方输出 validator 的注册位置。两者必须纳入迁移测试。

替换纯虚 `run` 是破坏性 C++ API/ABI 变化，按既定版本政策必须 MAJOR。
本草案继续提议 `provider-sdk 2.0.0`；Issue #467 / umbrella #472 的
“MINOR”是待修正的旧文字，不是两种可以任选的版本策略。此文不分配或
发布版本；计划的 fresh allocation gate 要重新核对所有依赖和占用情况。

### 10.2 Capability 和输出 Schema 的逐字段评审表

| 字段／规则 | 已有依据与待确认内容 |
| --- | --- |
| Capability 身份 | 提议 `sample.slice.v1`, `contract_version: 1.0.0`；外壳仍为 `lmdj.capability.v2`，其 Schema 不变 |
| 输入 | `source_audio`, `audio/wav`, required=true, max_count=1；PCM16 WAV 按 S8-D6；必填 `schema_id/schema_version` 尚无正式 WAV Artifact Schema，见 C-Q1，不能借用 Proof 的占位身份 |
| 输出 | `slice_points`, `application/json`, required=true, max_count=1；提议 `lmdj.slice-points.v1` / `1.0.0` |
| 输出对象 | 必需且仅有 `contract`, `source_sha256`, `frame_rate`, `points`；每 point 必需 `frame`，可选 `confidence`, `label`；所有对象拒绝额外字段 |
| 整数和绑定 | 提议整数为非负安全整数，`frame_rate` 为正且等于已解码输入采样率；hash 为 64 位小写十六进制且等于绑定源；frame 严格递增且 `0 <= frame < frame_count` |
| 空输出与端点 | 提议静音允许 `points: []`；points 表示检测到的 onset，不强制添加 0 或 EOF。recipe 如何补边界仍归 #471，见 C-Q2 |
| 可选字段 | 提议 confidence 为有限数且在 [0,1]，label 为非空 UTF-8 字符串；长度和点数上限纳入 C-Q2/C-Q3；JSON 重复键、NaN/Infinity、坏 UTF-8 拒绝 |
| 确定性 | 同输入字节和参数，输出 JSON 字节相同；需锁定 UTF-8、键顺序、空白、数值编码。参考 Provider 建议不输出可选 confidence/label，避免未经定义的浮点序列化 |
| 参数 | `CapabilityRequest.parameters` 当前只是 object；首版精确参数和默认值尚未定义，见 C-Q2。未知 key 拒绝，不传路径或权限 |
| 平台与政策 | 提议本地、无网络；`platforms` 是 C++ descriptor 字段，不是 capability.v2 JSON 的字段；分类／region／权限精确 token 和支持平台见 C-Q3，不能通过增补额外 JSON 字段绕过现有 Schema |
| resources/execution | class=cpu，memory_mib、timeout_ms、max_attempts 必须在 C-Q3 锁数值；direct in-process 只报告 elapsed，不能宣称 hard timeout 或总 RSS 门禁 |
| progress/errors | `analyzing`；公开 code 保持封闭集合。SDK 的 policy/selection 拒绝和 Provider 的领域失败分别验证，见下表，不伪称所有失败都来自 Provider |

### 10.3 输入、输出、存储与失败矩阵

| 时点／故障 | 提议结果和验收观测 |
| --- | --- |
| 请求绑定的未声明端口、超计数、错误 media type、重复 hash | `INVALID_ARGUMENT` / `input_binding_invalid`；不向 owner 请求未授权输入，不调用 run |
| run 中 source 的未绑定端口／错误 occurrence | `INVALID_ARGUMENT` / `input_binding_invalid`；run 已开始，拒绝该次访问并 latch 失败，不额外调用 owner |
| owner 不可取 | `NOT_FOUND` / `input_artifact_unavailable`；不调用 run |
| declared length/hash 与 bytes 不符 | `IO_ERROR` / `input_artifact_mismatch`；不调用 run |
| 声明长度超过本次输入预算或求和溢出 | `INVALID_ARGUMENT` / `input_artifact_too_large`；在 resolver/SDK staging 分配前拒绝 |
| WAV 截断、坏头、非 S8-D6 | 消费方输入 validator 或参考 Provider 返回 `UNSUPPORTED_AUDIO` / `source_audio_unsupported`；SDK 必须保留此已声明失败，而不是一概改为坏 Provider outcome |
| 输出端口／数量／media type／required 缺失、伪造 ArtifactRef | `PROVIDER_FAILED` / `output_contract_invalid`；失败 terminal 的两组 outputs 为空，无可见 Candidate |
| JSON／源 hash／rate／frame／可选字段非法 | 消费方 validator 返回失败，SDK terminal 为 `PROVIDER_FAILED` / `output_schema_invalid`；不发布输出 |
| Provider 抛异常 | `PROVIDER_FAILED`，无同 Attempt 静默 fallback；私有输出清理后终结 |
| 输出 publication 或 terminal 持久化 I/O 故障 | 返回外层 I/O 失败，不能谎称耐久 terminal 已写入；恢复与可见性必须按 C-Q5 验证 |

上述新增 reason/code 配对也是提议，须随 C-Q4 批准。Owner resolver 只接收
校验过的完整 ArtifactRef，不能获得端口外查找入口。SDK 将 bytes 复制到
attempt 私有拥有型缓冲；仅有 `shared_ptr<const vector<byte>>` 不足以证明
owner 没有 mutable alias，不能把 const 视图误当 freeze。验证后 Provider
拿到稳定 handle；保留 handle 可延长内存寿命，其额度计费必须纳入 C-Q3。

预算覆盖**聚合**输入 staging、输出 staging 和转换 scratch，使用溢出安全
算术。仅比较单个 declared byte_length 不足以限制多个输入、两次拷贝或
未释放 handle；Owner 预有内存和 Provider 自行分配的内存不能由 SDK
宣称受其硬约束。需要整进程资源门禁时使用 benchmark sandbox 另行验证。

输出 validator 由消费方拥有，注册时显式注入，收到 request 的已验证输入
元数据及私有输出 bytes；不得把 Project/Workspace 路径带给 Provider。
必须验证所有存在的结构化 outputs，不能因端口 optional 就跳过其 bytes。
无 validator 的结构化注册 fail closed；Proof 的不透明端口须显式声明其
验证策略，不把“没有 validator”解释成“任意 JSON 合格”。

### 10.4 待用户／设计评审裁决（实施阻塞项）

| ID | 推荐方案 | 阻塞范围 |
| --- | --- | --- |
| C-Q1 WAV 输入契约 | 新建可复用的 PCM16 WAV Artifact profile，精确引用 S8-D6 支持范围；评审命名、初始版本和验证所有者，不用 Proof 占位 Schema | K1 Contract；K2 输入验证；K3 Provider |
| C-Q2 onset/parameters | 首版采用 onset-only、静音空列表；确认参数及默认值、confidence/label 上限和 canonical bytes；参考算法使用确定性整数运算。recipe 端点补全不在此决定 | K1 输出契约与 K3 算法；benchmark 工具使用独立预测帧接口可先做 |
| C-Q3 资源／平台／权限 | 显式宿主预算注入，聚合 staging 配额；锁定数值、保留 handle 的预算归属、执行平台与权限 token；无网络、无静默重试，direct 模式 timeout 仅观测 | K1/K2/K3 生产执行；K5 Host 集成 |
| C-Q4 回调线程与领域失败 | 首版 source/sink 仅同步 run 线程调用，run 返回后关闭共享生命周期状态；保存的 callback 拒绝而非悬空；拒绝跨线程调用，推荐 context 持有共享状态而非栈引用。允许 descriptor 声明且经 SDK 白名单验证的领域失败；禁止 Provider 伪造 SDK owner/权限错误 | K2 是并发/API 决策，不能在实现里暗定；竞态与 late-call 测试为必需 |
| C-Q5 crash 可见性 | 以已验证的耐久 terminal 作为外部可见性提交标志；private blobs 可以先落盘，缺少 terminal 的残留不得被 inspect/未来 CandidateIndex 消费。评审并锁定恢复/孤儿清理策略，不承诺多路径 rename 原子性 | K2 持久化 conformance；#471 只消费确认后的规则 |

这些缺口意味着 #467 尚不是“已批准／可直接实现”。本轮交付使评审材料、
迁移清单、Task 文件范围和验收可以逐项审阅；设计确认与版本分配审计是
明确的下一道门，不以计划完备代替批准。

### 10.5 可直接评审的推荐方案（仍未批准）

以下是供 C-Q1–C-Q5 选择的具体候选，**不是现有 manifest 身份或默认产品
限制**。只有确认后才能写入 active source；若被否决，先修订计划。

- **C-Q1**：提议 profile ID `lmdj.audio.pcm16-wav.v1`、初始版本 `1.0.0`，
  retained profile 文档路径
  `contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md`。它是二进制 WAV
  profile，不伪装成验证 WAV bytes 的 JSON Schema。限定 RIFF/WAVE PCM16、
  mono/stereo、44.1/48 kHz（既定 S8-D6），拒绝截断及非法 chunk 长度；
  按 RIFF chunk 遍历及 padding 读取，不能假设永远是 44-byte header。
  消费方拥有 profile/输出 validator，建议放在新 reference Provider 的
  `validation.hpp` / `validation.cpp` 中，可由 Registry 显式注入。
  SDK 不依赖 WAV 或 slice Schema。输入结构错误由 Provider 前置解码返回
  approved domain error；输入 custody 的 hash/length 校验仍先于 run。
- **C-Q2**：首版参数对象只接受可选 `threshold_pcm16`（1..32767，默认
  4096）、`refractory_frames`（1..采样率，默认 240）；未知键、bool 与
  非整数拒绝。参考 detector 每帧取各声道绝对幅度最大值，以 widened
  integer 处理 -32768。由低于 threshold 转为达到 threshold 的帧是候选，
  距上次已采纳 onset 至少 refractory_frames 才输出。输入前的幅度视为 0；
  保持输入原始采样率／帧索引，不先 resample。该简单算法用于检验机制，
  不宣称真实音乐切片品质已合格。points 最多 4096；label 最多 128 UTF-8
  bytes；参考实现不输出 confidence/label。JSON 输出按 UTF-8、key 字典序、
  紧凑分隔符、无 BOM、无尾换行固定；只输出整数 frame/rate，确保参考实现
  不受浮点打印差异影响。其他 Provider 使用可选数值字段时必须证明双跑
  字节一致，不把模型输出美化成参考结果。
- **C-Q3**：参考候选建议 memory_mib=64、单次聚合输入 staging 上限
  16 MiB、聚合输出上限 256 KiB、timeout_ms=1000、max_attempts=1；这些
  是待测起点，不能证明性能门禁通过。execution ingress 显式传入
  `{maximum_input_bytes, maximum_output_bytes, staging_budget_bytes}`，不能
  默读 Host 文件；实效预算取 capability/Host/执行剩余预算最小值。SDK
  输入复制、输出 staging、validator scratch 的预留总量必须计入预算。
  返回 handle 共享预算 lease，最后 handle 释放才归还；活跃调用结束不
  等于内存回收。Owner 缓冲另计，SDK 不能宣称限制 owner 总 RSS。
  原始候选支持平台提议为 `test`（现有测试 token）、`linux`、`macos`，
  region=`local`，分类=`public|private`，permission=`sample.slice.execute`；
  新 token 均需评审，未确认／未实测的平台不加入 descriptor。无网络权限，
  本地执行并不自动替用户授予权限；Host granted_permissions 必须显式允许。
- **C-Q4**：context 持有共享控制块，source/sink 通过它检查 active 标志和
  调用线程身份；callback 只保存控制块，不捕获 execute 栈引用。run 返回
  先在控制块内原子关闭，后续 invocation 返回类型错误且不访问已释放对象。
  callback 的任一违规调用在 active 期间设置 first-error latch；Provider
  忽略失败返回也不能使 Attempt 成功。迟到调用在关闭后不得改写已持久化
  terminal；应返回 `INVALID_ARGUMENT` / `input_binding_invalid`（source）或
  `INVALID_ARGUMENT` / `output_contract_invalid`（sink）。active 期间 output
  latch 在终态转换为 `PROVIDER_FAILED` / `output_contract_invalid`。自建线程调用即使碰巧在 run 期间也拒绝；同步首次执行线程是
  v2 首版明确限制，不是默许的 data race。request/context 元数据也使用
  拥有型或共享不可变存储；不让保存的 context 引用栈上 request。
- **C-Q5**：继续利用已存在的 attempt reservation/私有 staging 和耐久
  terminal 文件；读取方只经校验 terminal 获得 outputs，不能扫描 blob
  目录发现 Candidate。无 terminal 的 reservation 保留为不可见、不可复用
  的中断证据，启动时不自动删除仍可能在其他进程执行的目录；自动 GC 与
  abandoned-attempt 恢复另行设计。新 Attempt 使用新 ID；旧 terminal 永不
  回写。正常失败仍清理该次私有输出并写失败终态；如果持久化失败，返回
  外层 I/O 错误并保留原始失败证据，不伪造 terminal。须通过在每个 publish/
  terminal 交界杀死独立测试进程再重启 inspect 的试验证明不可见性。

推荐 error 白名单：Provider 仅可返回 descriptor 声明的
`PROVIDER_FAILED`、`UNSUPPORTED_AUDIO` 或 `INVALID_ARGUMENT`（仅已确认参数
验证细因）；SDK 自己处理 owner I/O、绑定和 policy。输入不可取、输入不匹配
等 SDK reason 不允许 Provider 伪造。输出违规一律转换为 SDK 拥有的输出
错误。policy 拒绝沿用现有 `PERMISSION_DENIED`，selection 沿用现有
`PROVIDER_NOT_FOUND`；不是扩张 Capability 的领域错误集合。
