# Stage 6 Formal Web Runtime Host Review — 2026-08-11

- **审查对象**：Stage 6 设计文档
  `docs/superpowers/specs/2026-08-03-lmdj-formal-web-runtime-host-design.md`
  及其在当前 `main` 上的实现（含 Stage 7 抽取到
  `packages/web-runtime-platform` 之后的形态，以及 2026-08-08
  公开部署设计落地的 deploy 链路）。
- **审查基线**：`main` revision `86b52d4`（含 PR #103–#112）。
- **方法**：两轮。第一轮（`38a8c13`）通读设计全文并逐条核对
  OPFS 存储层、Host 协议、状态机、Wasm AudioWorklet、RealtimeEngine
  outcome 路径、输入适配器、Proof 服务器与工具链锁定；第二轮补齐
  第一轮略读的 manifest gate、bridge/Control Runtime deadline 与
  publication claim 机制、终局释放通道、部署 headers 与 orchestrator，
  并复核第一轮发现在 `86b52d4` 上是否仍然成立（全部成立）。
- **性质**：这是评审记录，不是实施计划。代码问题 F1–F4 的修复已由
  已合并的
  [`docs/superpowers/plans/2026-08-11-lmdj-web-runtime-hardening.md`](../superpowers/plans/2026-08-11-lmdj-web-runtime-hardening.md)
  （PR #105）排期，本文档不重复其 Task 与版本决策。

## 一、总体结论

设计文档质量高，实现与设计的核心不变量高度一致，两轮均未发现高危缺陷。
问题集中在两类：**文档漂移**（实现正确演进、Stage 6 spec 未回写，3 项）
与**防御纵深缺口**（失败路径可再收紧、无一构成当下可利用漏洞，4 项）。
这与 Core Review 积压整理的历史结论同型：实现质量持续很高，
围绕实现的证明与文档层在掉队。

| 严重度 | 数量 | 处置 |
| --- | ---: | --- |
| 高 | 0 | — |
| 中 | 3 | D1、D2 未排期；F1 已排期（PR #105 计划 Task 1） |
| 低 | 4 | F2–F4 已排期（Task 2–4）；D3 未排期 |
| 编辑/清理 | 4 | F5、F6 与两个编辑项未排期 |

## 二、设计文档评审

### 值得保持的实践

- **B1–B6 六个阻塞假设的锁定决议**是全文最强的部分：每个假设都有明确
  的架构层答案而不是推给实施计划。§6.3 的语义存储义务四分类
  （`native / equivalent / vacuous / absent`）从机制上禁止了
  "POSIX 按名映射 OPFS"这类常见错误；`absent`（目录持久性屏障）
  附带完整的 intent 重放恢复论证，并要求实施计划逐步翻译成命名测试。
- §9.2 把 **enqueue admission、runtime outcome、物理可闻发声**拆成
  三个不同事实（B5），§16.3 要求 Browser Proof 按 Core 常量推导边界
  而不是调参到通过。
- §17 物理验收行的 `deferred / unverified` 边界诚实，automation
  无权标记通过。

### 文档漂移（实现演进未回写 spec）

| ID | 严重度 | 内容 |
| --- | --- | --- |
| D1 | 中 | **`restart-required` 终态未回写。** §11 声明终态只有 `failed` 与 `closed`，§12.1 说 `HOST_RESTART_REQUIRED` 时 Host "remains `failed`"（`terminal_state` 只是 details 字段）。实现（`packages/web-runtime-platform/web/state_machine.mjs:10,16`）把 `restart-required` 做成独立的第一类终态，三处终态判断均为三元集合。§11 状态表已不描述真实状态机。 |
| D2 | 中 | **实际存储拓扑与 §6.3/§7.1 描述不符。** 实现中 WasmFS 只用于探测挂载可用性（`packages/project-io/src/web/storage_platform.cpp:325-332`），全部真实 I/O 走自研 JS library `library_opfs_storage.js` 的 `lmdj_opfs_*` 导入 + Asyncify，绕开 WasmFS 文件 API。该选择本身合理（语义义务确实无法用 WasmFS 表达），但 §6.3 架构图与 §7.1 conformance 第 4 条（"WasmFS OPFS synchronous file access"）描述的是另一个拓扑。 |
| D3 | 低 | **终局强杀宽限常量漂移。** §12.1 写 "100 ms force-termination fallback"，实现为 `TERMINAL_OWNER_RELEASE_GRACE_MS = 5_000`（`packages/web-runtime-platform/src/web-runtime-pre.js:197`），由 PR #98（slow-runner proof 预算加固）引入，未回写。 |

编辑性：§12.1 错误码列表 "…and `HOST_RESTART_REQUIRED`, and
`HOST_PROTOCOL_MISMATCH`" 双 and；实际链接 flags 含
`-sPROXY_TO_PTHREAD`、`-sASYNCIFY=1`，超出 §7.1 "minimum" 集合
（允许，但真实契约在 `tools/web-runtime/emscripten.lock.json`，
spec 宜注明指针）。

D1–D3 的共同修复形态是给 Stage 6 spec 增加一个勘误/演进段，或在文首
指向 Portal current truth。该 docs Task 已在 PR #105 计划中显式声明为
范围外待办，仍**未排期**。

## 三、实现符合性矩阵（逐项核对通过）

| 设计要求 | 核对结果与位置 |
| --- | --- |
| §14 CSP / COOP / COEP | `tools/web-runtime/serve_distribution.py:22-35` 与 spec 逐字一致 |
| §7.1 emsdk 三层身份 pin | `tools/web-runtime/emscripten.lock.json` 与 spec 一致；512 MiB 固定堆、禁增长；manifest gate 再次硬校验同一组身份（`manifest_gate.cpp:185-193`） |
| §13.1 preflight 8 项能力 | `preflight.mjs` 列表与顺序逐项一致 |
| §12.1 协议严格性 | 未知字段拒绝、fatal UTF-8、重复 `request_id` 拒绝、64 KiB envelope、1 MiB sidecar 长度+SHA-256 双验证、1s/30s/10s deadline 分类（`protocol.mjs`） |
| §12.1 单一 cutoff 与 claim 语义 | `bridge.cpp:986` 在同步 marshal 入口一次性打点 `steady_clock::now()`，随 RequestSlot 传递；`control_runtime.cpp:1042` 用同一 `submitted_at` 推 cutoff；publication 以 `open→cancelled` 对 `open→publish_claimed` CAS 竞争，claimed 先手不可再转 `HOST_TIMEOUT`（`bridge.cpp:302-338`） |
| §12.1 settlement watchdog | `PUBLICATION_SETTLEMENT_WATCHDOG_MS = 1_000`（`web-runtime-pre.js:3`）；`HOST_RESTART_REQUIRED` 携带 `terminal_state`/`mutation_outcome: "unknown"` |
| §12.1 终局通道防伪造 | BroadcastChannel `lmdj.web-runtime-host.terminal.v1` 消息携带 `crypto.randomUUID()` token，native completion 原子单次消费；伪造/重放事件不能制造完成 |
| §12 manifest gate | canonical JSON 回验、exact keys、SHA-256、宿主身份白名单、asset 路径安全检查、恰好一个 `runtime_script` 与一个 `runtime_wasm`（`manifest_gate.cpp`） |
| §11 状态表 | 除 D1 所述终态集合漂移外，其余转移逐行匹配（含 `audio-suspended→recovering` 需 recovery epoch、interrupted/终态 seal Take、`audio.suspend` 幂等）；`state_machine.mjs` |
| §11.2 恢复探针 | 恢复 epoch 单调、探针窗口单次预留、跨 epoch outcome 不能完成当前 epoch、`RECOVERY_OUTCOME_DEADLINE_MS = 1_000`（`runtime_session.mjs`） |
| §6.4/§6.5 音频回调纪律 | 48 kHz / 128 帧硬校验并 latch fatal；回调只做 render + 原子操作；shape 校验、重入检测（`realtime_audio_worklet.cpp:62-153`） |
| §9.2 outcome 恰好一次 | 每个 dequeued Trigger 恰好一个 `voice_started`/`voice_capacity`，ring 满计 `runtime_outcome_drops`（`realtime_engine.cpp:414-451`） |
| §6.3 存储义务 | 排序迭代（unsigned UTF-8 byte order）、`lmdj.storage.intent.v1` 完整实现、恢复规则（absent→清除部分文件并重验；existing 不匹配→fail closed 保留证据，`library_opfs_storage.js:653-666`）、`create_immutable` 写循环+长度+hash 回读+flush、`append_durable` truncate+append+恰好一次 flush、超长 prefix 无变更拒绝 |
| §6.3 Journal 串行化 | `take_journal.cpp:112-133` per-platform mutex；已确认 append 不会被 stale prefix 回退 |
| §8.2 writer lease | 独占 SyncAccessHandle + `platformIdentity` 区分实例 → `PROJECT_BUSY`；按 path 引用计数重进入；不等待/不偷锁/不删锁文件（重取仅在 size==0 时写身份字节） |
| §10 输入适配 | pointer `isPrimary`+`button 0`、keyboard `event.code`+repeat 忽略+可编辑控件禁用、MIDI `sysex:false`、status 正确掩码 `0xf0`、velocity 0 = Note Off 不触发（`input_adapters.mjs`） |
| §16 门禁 | toolchain conformance 在 `tests/platform/web/toolchain/` 且入 CI；Host 源码边界有 `web_host_source_boundary_test.py`；`docs/quality/2026-08-03-formal-web-runtime-host-acceptance.md` 诚实区分自动化与物理证据 |
| 部署缓存策略（2026-08-08 部署设计 §9.2） | tracked `_headers` 仅保底 security/no-store；orchestrator 按已验证 manifest 生成九条精确 `public, max-age=31536000, immutable` 规则（`deploy_orchestrator.py:300-335`），未知路径保持 no-store。与 Stage 6 §7.4 "no-store 仅限 index/manifest" 的意图经由部署设计正确衔接，非违规 |

## 四、代码发现

| ID | 严重度 | 位置 | 内容 | 处置 |
| --- | --- | --- | --- | --- |
| F1 | 中 | `packages/audio-runtime/src/web/realtime_audio_worklet.cpp:415-426` | `await_quiescent` 超时 latch fatal 后进入 `while (in_flight)` 的无限 futex 等待；Worklet 线程 render 中途死亡时 Control Worker 永久阻塞。浏览器主线程有 deadline + 强杀兜底，Host 整体不挂死，但违反 §13.2 "must not hang indefinitely" 的精神 | 已排期：PR #105 计划 Task 1 |
| F2 | 低 | `packages/project-io/src/web/storage_platform.cpp:42-56` | JS 层区分 `QuotaExceededError`(-6)/`InvalidStateError`(-5)/`NoModificationAllowedError`(-7)，`web_error` 仅为 -3/-4/-8 附 `storage_condition`，quota 失败折叠成无细节 `io_error`。类型仍满足 §13.2，诊断信息丢失 | 已排期：Task 2 |
| F3 | 低 | `packages/project-io/src/web/library_opfs_storage.js:802-827` | `appendDurable` 不经 `activeLease` 即打开文件；`replaceComplete`/`createImmutable` 均经 `createIntent→activeLease` 强制持锁。common code 总在持锁下调用且有 mutex，不构成漏洞，但三个变更原语义务不对称 | 已排期：Task 3 |
| F4 | 低 | `packages/web-runtime-platform/web/protocol.mjs:423-425` | transport `receive` 对未知/重复 `request_id` 的 response 静默 `return false`。same-build 私有传输上这是协议违规，§11.2 对 outcome 同类情况要求 `HOST_PROTOCOL_MISMATCH` fail-closed | 已排期：Task 4 |
| F5 | 清理 | `tools/web-runtime/emscripten.lock.json` | `ASYNCIFY_IMPORTS` 显式列 3 个 `lmdj_opfs_*` 导入，而 library 中约 15 个均用 `Asyncify.handleAsync`（Emscripten 自动标记，能工作）；3 个显式条目冗余且误导读者以为只有它们会挂起 | 未排期 |
| F6 | 风格 | `packages/project-io/src/web/storage_platform.cpp:129-138` | `lmdj_opfs_byte_length` 用 double 复用返回值传 size 与负错误码，混叠脆弱 | 未排期 |

## 五、第二轮补充观察

- **manifest gate 是本轮新读到的最强一环**：canonical 序列化回验杜绝
  同 hash 异构 JSON，宿主/兼容宿主白名单、资产 hash 标记唯一性、
  `runtime_script`/`runtime_wasm` 恰好各一，失败一律
  `protocol_mismatch` 且 gate 单向进入 `rejected`。未发现问题。
- **deadline/publication claim 机制与 §12.1 完全一致**，包括 spec 中
  最容易实现错的两条：单一绝对 cutoff 跨 marshal/队列传递、
  claimed 先手后越线不得改判 `HOST_TIMEOUT`。
- **部署链路（#103–#112）**：`_headers` 全量 no-store 初看与 §7.4
  矛盾，实为部署设计的分层方案（tracked 保底 + orchestrator 按
  manifest 生成精确 immutable 规则），核对通过。#109–#112 是烟测
  验收对真实 Netlify 行为的逐例放宽（冗余 noindex、JS MIME 变体、
  紧凑 cache 指令、traversal 拒绝形态），每次放宽都有独立提交与
  理由，模式健康；建议在部署验收文档中维持"放宽清单"以防漂移
  成默许。**本条目的审计基线止于 #112**：其后部署烟测又发现
  Netlify 发布时间戳格式与禁用站点仍保留 current 指针两项问题
  （PR #114 处理中），因此本节不能作为当前部署链路的完整审计引用。

## 六、建议

1. **回写 Stage 6 spec**（D1–D3 + 编辑项）：一个 docs Task 即可
   完成,优先级应高于新功能——该 spec 是 Stage 7/8 的引用基线,
   漂移会传导。
2. F1–F4 按已合并的 hardening 计划执行；F5、F6 可并入该分支顺手
   清理，或明确记入积压。
3. 五行物理验收自 Stage 6 起一路 `deferred`，Stage 8 仍在向上叠
   功能；建议在 Stage 8 收尾前安排一次真机 pass，避免平台性风险
   积到更深的栈上。

## 七、审查环境

| 项 | 值 |
| --- | --- |
| 审查日期 | 2026-08-11（两轮） |
| 第一轮基线 | `38a8c13` |
| 第二轮基线 | `86b52d4`（第一轮全部发现复核仍成立） |
| Product Build | `1.0.16.5 · canary` |
| 相关计划 | `2026-08-11-lmdj-web-runtime-hardening.md`（PR #105，已合并；实现未开始） |
