# LMDJ New Headless Core 全量代码审查报告

- **日期**：2026-08-01
- **审查对象**：`main` 分支（HEAD `2cd0cf7b`，工作树 clean）
- **审查范围**：Core 的全部 11 个组成部分——7 个 Core Module（`packages/`）、2 个 Core Host（`apps/`）、Provider 实现（`providers/`）、Product Assembly（`products/lmdj`）、跨语言 Contract（`contracts/`）
- **方法**：每个部分由独立审查通道逐文件通读源码与对应测试，对照 `CLAUDE.md` 架构不变量与 `docs/governance/version-management.md` 版本政策交叉验证；关键疑点辅以实际构建（dev + asan/ubsan preset）、测试复跑、Python 数值交叉验证与哈希人工复核
- **基线验证**：全量 ctest **32/32 通过**；`verify-core-dependencies.sh`、`test_active_tree.sh`、`version_test.py`、`version_lock_test.py`、`version.py verify`（1.0.6.0）全部 PASS

---

## 总体结论

**整体质量：良好偏优。** 架构不变量在每个模块都得到严格遵守并普遍有直接测试背书；无 CRITICAL 级问题；共发现 **2 个高严重度、约 9 个中严重度** 问题，全部可在常规迭代内修复。

### 各部分评级一览

| # | 部分 | 评级 | 最高严重度发现 |
|---|---|---|---|
| 1 | packages/foundation | 优 | 中（`Result<T>` 缺 `[[nodiscard]]`） |
| 2 | packages/authoring-domain | 优 | 中（4 条错误分支零测试覆盖） |
| 3 | packages/audio-runtime | 良 | 低 |
| 4 | packages/project-io | 良 | 中（JSON 读路径符号链接 TOCTOU） |
| 5 | packages/project-cooker | 良 | 低 |
| 6 | packages/application-facade | 良 | **高**（JSON 深度栈溢出 DoS） |
| 7 | packages/provider-sdk | 良 | **高**（多端口校验只看 `.front()`） |
| 8 | apps/core-cli | 良 | 中（`valid_utf8` 双份实现） |
| 9 | apps/core-mcp | 优 | 低 |
| 10 | providers/（proof 对） | 优 | 低 |
| 11 | products/lmdj | 优 | 低 |
| 12 | contracts/ | 良 | 中（error contract 无生产者等 3 项） |

### 架构不变量核查（全仓库交叉验证）

- ✅ **Hosts 只用 Application Facade**：CLI 的 include 白名单有源码级测试断言（`tests/host/cli_test.py:726-746`）；MCP 经 `ast` 强制标准库-only import；product wiring 由 `products/lmdj/CMakeLists.txt` 单向注入，Host 自身不知道 product 存在。
- ✅ **Project Truth / Runtime Snapshot 分离**：cooker 单向派生（`const ProjectState&` → `shared_ptr<const RuntimeSnapshot>`），无回写路径；facade 的 `render_offline` 用 `path_is_inside_bundle` 阻止派生产物写入 `.lmdj` bundle。
- ✅ **Pattern 事件只引用 Pad Slot**：domain、cooker、facade、project schema 四层一致；`lmdj.project.v1` 的 `pattern_event` 直接不含 `asset_id`，并有 schema 测试显式断言。
- ✅ **Provider 隔离**：`Provider::run()` 签名层面杜绝可变 Project/bundle path；`attempt_isolation_test.cpp` 做字节级前后比对；失败落 Attempt 状态且经 `redact_provider_error` 脱敏。
- ✅ **退役 contract**：对活动树全量 grep `lmdj.patch.v1` / `lmdj.materials.v1`，唯一命中是 `test_active_tree.sh:33` 的守卫断言本身——无违规。
- ✅ **版本治理**：Product `1.0.6.0` 符合 `MILESTONE.MINOR.BUILD.PATCH`；11 个 `module.json` SemVer 无漂移；`assembly.lock.json` 哈希实测一致。

### 需优先处理的问题（按优先级）

1. **【高】application-facade：JSON 嵌套深度无限制 → 栈溢出 DoS**（`c_api.cpp:206-208, 254-256`、`assembly_loader.cpp:52`）。只有字节数上限，`nlohmann::json::parse` 递归无深度上限，几十 KB 的深嵌套输入即可打崩宿主进程；这是所有跨语言宿主（含未来 `workers/`）的公共 C ABI 边界，且无回归测试。
2. **【高】provider-sdk：多端口 Artifact 数量校验只检查第一个端口**（`attempt_store.cpp:624-632, 1484-1491`）。多端口 Capability 的 required/max_count 静默失效；当前测试全部单端口所以未暴露。进入多端口阶段前必须修复并补测。
3. **【中】project-io：JSON 读路径缺少与 `read_artifact()` 对称的 `O_NOFOLLOW` 防护**（`project_store.cpp:161-266, 524-566`），存在文件级符号链接 TOCTOU 窗口。
4. **【中】contracts：`lmdj.error.v1` 必填 `contract` 字段无任何生产者满足**；`lmdj.project.manifest.v1` 与 `lmdj.build-manifest.v1` 已被代码持久化/消费却无 schema——打 contract tag 前必须解决。
5. **【中】facade：`dispatch()` 隐式兜底路由（`application.cpp:927-983`）+ `Application` 线程安全契约未声明**；**provider-sdk：崩溃遗留 attempt 目录无恢复路径、`ArtifactSink` 线程约束未声明、空输出端口注册/执行校验不一致**。
6. **【中】测试与工具性补齐**：authoring-domain 的 `duplicate_id`/`missing_asset` 四分支补测；foundation 的 `Result<T>` 加 `[[nodiscard]]`；`valid_utf8` 下沉 foundation 消除 CLI/C ABI 双份实现。

### 横向观察

- **重复实现是最常见的系统性问题**：手写 SHA-256（cooker vs foundation 的 picosha2）、`valid_utf8`（CLI vs c_api）、bars/slot 校验（domain vs cooker）、journal 首行解析（project_store 两处）。建议统一下沉到 foundation/domain。
- **"防御性代码写了但测不到"反复出现**：多端口分支、bpm 防御分支、duplicate_id 错误分支、I/O 失败路径——本次两个高严重度问题正藏身于此类零覆盖分支，值得作为测试策略专项。
- **工程亮点**：project-io 的 fault-injection 崩溃点穷举矩阵、audio-runtime 的 Golden Audio 独立 Python 参考实现比对、facade 的 ABI 导出符号集钉死（`nm`/`dlsym`）、provider 的 source-package 身份哈希锁——质量明显高于同类代码库平均水平。

---

## 分部分详细报告

### 1. packages/foundation — 优

**概述**：最底层公共模块——强类型 ID（`StrongId<Tag>`）、统一 `Result<T>`/`Error` 错误原语、内容寻址 `ArtifactRef`、`canonical_json` 工具，被其余所有 Core Module 依赖。dev 与 asan/ubsan 两套 preset 实测构建运行全绿，`-Wall -Wextra -Wpedantic -Werror` 无告警。

**优点**
- `describe_artifact` 64KB 分块流式哈希（picosha2），显式防御 `byte_length` 无符号溢出，`error_code` 重载区分 `not_found`/`io_error`；无裸 `new/delete`、无 UB。
- `StrongId<Tag>` 幽灵类型正确阻止不同 ID 类型互相隐式转换。
- 模块边界干净：不涉及任何领域逻辑，无退役 contract 字样；`0.1.0` 与全部下游依赖声明一致，无版本漂移。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| 中 | `include/lmdj/foundation/error.hpp:66-112` | `Result<T>`/`Result<void>` 及工厂函数缺 `[[nodiscard]]`，错误可被静默丢弃；当前所有调用点均正确接收，尚无实际故障，但应尽早补上 |
| 低 | `src/json.cpp:6-28` | `canonical_json` 递归重建依赖 nlohmann 默认 map 排序的隐藏假设；若调用方改用 `ordered_json` 会静默产出非规范化顺序 |
| 低 | `src/artifact.cpp:21-25`、`ids.hpp:36-38` | ADL `from_json` 失败抛异常而非返回 `Result`（nlohmann 固有限制），下游均有 try/catch，但头文件未文档化该行为 |

**测试覆盖**：成功路径、not_found、io_error（符号链接自环）、round-trip、强类型隔离均覆盖。缺口：`Result<T>` 失败态直接单测、`canonical_json` 顶层数组/标量/Unicode、读取中途失败分支——均低优先级。

---

### 2. packages/authoring-domain — 优

**概述**：纯值语义 Authoring Domain——`ProjectState`（Project Truth）+ 无副作用 `apply(state, command, receipts)` 命令处理器（ImportAsset / AssignPad / CreatePattern / RecordTake）。ASan/UBSan 下全部 3 个测试（含 256 种子 × 64 命令生成式矩阵）全绿。

**优点**
- 核心不变量有直接测试背书：`PatternEvent`/`RawTakeEvent` 只持有 `PadSlotId`；Pad 重新分配后 Pattern 保持 slot 引用，有专门用例与生成式矩阵覆盖。
- `ProjectState` 无 provider 状态或运行时派生字段。
- 命令原子性设计清晰：UUID 校验 → 重放回执 → `expected_revision` → 具体校验；失败路径有字节级"状态不变"断言。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| 中 | `src/command_handler.cpp:138-144, 161-168, 182-188, 207-214` | 四条 `duplicate_id`/`missing_asset` 错误分支零测试覆盖（生成式测试永远生成新 UUID、只选已存在 asset）；分支内回归 CI 无法发现 |
| 低 | `src/command_handler.cpp:207-214` | RecordTake 的 take/pattern id 冲突返回同一条笼统消息，无法区分 |
| 低 | `src/command_handler.cpp:232-236` | 重放命中不校验 receipt 的 `committed_revision` 与传入 `state.revision` 一致；建议文档化前提或加断言 |

**测试覆盖**：修订冲突、幂等重放、参数边界（BPM 40/240 等）、原子提交、slot 身份保持均到位；唯一短板即四条错误分支。

---

### 3. packages/audio-runtime — 良

**概述**：纯离线 Offline Renderer——输入不可变 `RuntimeSnapshot`，定点 velocity 缩放与饱和混音，输出 PCM16 立体声 WAV 并回填 `ArtifactRef`。dev + asan 实测全绿；定时算法经独立 Python 数值验证。

**优点**
- Snapshot 不可变性严格（`shared_ptr<const>` 全程只读 + 专门回归测试）；事件经 `PadSlotId` 引用。
- 溢出防护完备：所有尺寸计算走 `checked_multiply`/`checked_add`，越界访问点前有边界检查。
- `mix_math.hpp` 用 `int64_t` 中间量 + `constexpr` + 编译期 `static_assert`。
- Golden Audio：独立 Python 参考实现（`tests/fixtures/golden/reference_render.py`）与 C++ 输出 SHA256 比对。
- 已排除误报：非整除 BPM 下 step→frame 映射经穷举验证（40–240 BPM × {1,2,4,8} 小节）误差恒 <1 帧、不累积、不丢事件。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| 低 | `src/offline_renderer.cpp:127-145` | 逐事件 PCM 格式/velocity 校验在缓冲区分配之后，与 "rejects before allocating" 测试意图不一致（最坏分配约 4.6MB，非 DoS） |
| 低 | `src/wav_writer.cpp:85-116` | 写入中途失败不删除残留的半成品 WAV，调用方可能误用损坏文件 |
| 低 | `src/offline_renderer.cpp:191-208` | 写完 WAV 后 `describe_artifact` 重新读盘算哈希，双倍 I/O，可在写入时同步累积 |

**测试覆盖**：数学性质、WAV 精确定位、饱和/顺序敏感、端到端链路、最大合法尺寸均覆盖。缺口：逐事件校验失败路径、`wav_writer` I/O 失败分支无单测。

---

### 4. packages/project-io — 良

**概述**：体量最大模块（约 3.7k 行），负责 Project Truth 持久化：checkpoint + append-only 事务日志 + manifest 的 `.lmdj` bundle，另有 `TakeJournal` 提供录音 crash-safe 恢复（`recovery/active` → `recovery/sealed`）。

**优点**
- 崩溃一致性工程扎实：所有持久化写入遵循 `write-temp → fsync → rename → fsync(dir)`；`fault_matrix_test.cpp` 用声明式 `FaultPoint` 矩阵对每个持久化边界做崩溃点穷举并断言每个故障点恰好触发一次。
- 白名单反序列化严格：闭合键集、拒绝浮点/负数、sha256/UUID/slot/step 逐字段校验，贴合 `lmdj.project.v1`。
- 写盘后用同一解析器反解比对（`parse_project(project_json(state)) == state`），确保写出的 checkpoint 一定能读回。
- 命令幂等重放完整（同 command_id 不同语义检测、身份校验后返回缓存结果）。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| **中** | `src/project_store.cpp:161-266, 524-566` | TOCTOU：JSON 读路径（manifest/checkpoint/事务文件）用会跟随符号链接的普通 `ifstream`，只在开始扫描一次；而 `read_artifact()` 已用 `openat(O_NOFOLLOW)` 逐级防护——同一威胁模型未一致应用 |
| 低 | `src/project_store.cpp:1719-1757` | `matching_active_journal` 手写解析 journal 首行，与 `TakeJournal::read_active_journal` 重复且校验粒度不一致 |
| 低 | `src/project_store.cpp:1842-1858` | RecordTake 因 `duplicate_id` 失败时匹配的 active journal 不 seal 也不清理，成为 `list_recoverable()` 发现不了的死档案 |
| 低 | `include/lmdj/project_io/take_journal.hpp:1-9` | 头文件依赖传递包含，非自包含 |
| 低 | `project_store.cpp:469-507` vs `take_journal.cpp:489-541` | 两处 `write_new_file` 对失败临时文件清理策略不一致 |

**测试覆盖**：三个测试文件共 2446 行，round-trip、契约 shape 拒绝、孤儿临时文件精确清理、advisory lock、断尾截断修复、故障矩阵穷举。缺口：文件级符号链接竞态、整数边界值、JSON 重复键/深嵌套、duplicate_id 孤儿 journal。

---

### 5. packages/project-cooker — 良

**概述**：Project Truth → 不可变 Runtime Snapshot 单向派生：`cook()` 校验、经 Pad Slot 解析 Asset、`ArtifactResolver` 取字节并 sha256/长度双重校验、手写 WAV(PCM16/48kHz) 解码生成 `PcmSample`。纯函数、只读输入、无回写。

**优点**
- 不变量合规：`const ProjectState&` 入、`shared_ptr<const>` 出；事件始终经 `PadSlotId`。
- 完整性双重校验（长度 + 重算 sha256）+ 按 sha256 内容寻址去重。
- 测试质量高：256 种子确定性矩阵（两次 cook 逐字段比对、解析调用计数断言、失败不发布部分快照）；测试硬编码 SHA-256 常量经 Python 交叉复算确认。
- WAV 解析逐行验证无越界读、无除零。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| 低 | `src/project_cooker.cpp:17-145` | 手写约 130 行 SHA-256，与 foundation 的 picosha2 重复；建议 foundation 增加 `hash_sha256(span<const byte>)` 公共 API |
| 低 | `include/lmdj/cooker/project_cooker.hpp:17-20` | `ArtifactResolver`/`PatternId` 按值传参，每次 `cook()` 拷贝闭包状态，建议 const 引用 |
| 低 | `src/project_cooker.cpp:5` | 未使用的 `<limits>` include |
| 低 | `src/project_cooker.cpp:160-174` | bars/slot/step 校验与 `command_handler.cpp` 重复维护，建议下沉 domain 公共函数 |
| 低 | 测试缺口 | `cook()` 入口 bpm 防御分支不可达且无测试；矩阵 `bars` 恒为 1，未覆盖 {2,4,8} 的 step_limit 及非法 velocity/step 直接拒绝 |

---

### 6. packages/application-facade — 良

**概述**：Host 唯一入口——`Application`（`command`/`query`）、`assembly_loader`（Assembly 校验与 Provider 编目）、`c_api`（跨语言 C ABI 与句柄生命周期）。围绕 Project Truth 与 Attempt 状态两条独立数据线组织。

**优点**
- 不变量严格：`provider.*` 全部落在以 `workspace_root` 为作用域的 `AttemptStore`，从不触碰 `project_path`；Provider 只收 `ArtifactRef`。
- `render_offline` TOCTOU 防护严谨：openat 链式 `O_NOFOLLOW`、私有 scratch 渲染、二次校验、`linkat` 原子发布、阻止写入 `.lmdj` bundle。
- C ABI 每引擎串行锁 + `tombstone_shells` 防句柄 ABA/UAF，有 32 引擎并发、万次创建销毁 stress 测试；`dynamic_load_test` 用 `nm`/`dlsym` 钉死导出符号集。
- facade 不硬编码产品身份，product 数据经 `CompiledAssemblyCatalog` 注入。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| **高** | `src/c_api.cpp:206-208, 254-256`、`src/assembly_loader.cpp:52` | JSON 嵌套深度无限制 → 栈溢出 DoS。仅有字节上限（16MB/64KB），几十 KB 深嵌套 `[[[...]]]` 即可耗尽线程栈打崩宿主；公共 C ABI 边界、无回归测试 |
| 中 | `src/application.cpp:927-983` | `dispatch()` 末尾无条件兜底到 `attempt_inspect`；`operations()` map 与 if-链需手工同步，新增 operation 忘加分支会被静默错误路由 |
| 中 | `include/lmdj/facade/application.hpp:30-31` | `Application` 自身无并发保护（唯一保护在 c_api 层），头文件未声明调用方序列化契约；C++ 直连多线程 Host 会数据竞争 |
| 低 | `src/assembly_loader.cpp:25-26, 413-419` | catalog 安装为一次性单例，重复调用抛未捕获 `logic_error`，契约未文档化 |
| 低 | `src/c_api.cpp:71-72, 308-313` | `tombstone_shells` 永久泄漏防 ABA 是刻意取舍但无注释，后人可能误"修复"重新引入 UAF |
| 低 | `src/assembly_loader.cpp:93-98, 282-296` | 同 capability id 不同 version 声明两次被静默覆盖而非拒绝 |

**测试覆盖**：golden path、幂等重放、异形请求、TOCTOU/符号链接、ABI 生命周期与并发覆盖极佳。缺口正对应上述问题：深嵌套 JSON、绕过 c_api 直接并发压测 `Application`、重复安装、重复 capability id。

---

### 7. packages/provider-sdk — 良

**概述**：Capability-based Provider 抽象——`Registry`（注册校验）+ `AttemptStore`（在 Host Workspace 下以文件级原子操作执行、隔离、持久化 Attempt）。`Provider::run()` 只收 `AttemptId`、`CapabilityRequest`、`ArtifactSink`，接口层面杜绝可变 Project。

**优点**
- 不变量严格执行：`prepare_workspace` 显式拒绝 `.lmdj` 路径；attempt isolation 字节级前后比对。
- 零信任校验 Provider 返回值：candidate/error 二选一、attempt_id 一致性、outputs 与 sink 实际写入比对、异常统一转 `provider_failed`。
- 秘密不落盘：参数只存 sha256，错误经 `redact_provider_error` 脱敏，均有专门测试。
- 原子文件 I/O 模式（temp + rename/hardlink、`mkdir` 互斥点）正确且有并发测试。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| **高** | `src/attempt_store.cpp:624-632, 1484-1491` | 多端口 Artifact 数量校验只看 `.front()`，其余端口 required/max_count 静默失效。例：声明 `audio: required` + `thumbnail: optional` 时，返回 3 个 audio、0 个 thumbnail 也通过。当前测试与 proof Provider 全部单端口，未暴露 |
| 中 | `src/attempt_store.cpp:1486-1491` | 空输出端口 Capability 可合法注册但执行期永远被判 `invalid_provider_outcome`——注册期与执行期校验不一致 |
| 中 | `src/attempt_store.cpp:223-267, 1264-1320` | `mkdir` 成功后、terminal json 写入前崩溃 → attempt_id 被永久占用且返回与"正常完成"无法区分的 `duplicate_id`，无恢复机制 |
| 中 | `src/attempt_store.cpp:1330-1459` | `ArtifactSink` 回调引用捕获 `minted` 无互斥，接口未声明单线程串行约束；多线程 Provider 会数据竞争 |
| 低 | `src/attempt_store.cpp:595-604` | `selected_capability()` 对 `find_if` 结果不检查 `end()` 直接解引用 |
| 低 | `src/attempt_store.cpp:606-675` | 用 `Error{internal_error, ""}` 魔法值兼职"校验通过"哨兵 |
| 低 | `src/attempt_store.cpp:34, 962` | `host_settings_mutex` 进程级全局锁，不同 workspace 互相排队 |

**测试覆盖**：单端口场景极扎实（政策门禁、畸形结果、脱敏、并发预留、canonical JSON 防篡改）；多端口零覆盖、空输出端口、崩溃遗留目录、Registry 负向校验缺失。超时/取消按计划推迟属预期范围（建议在 `capability.hpp` 注明字段暂未强制执行）。

---

### 8. apps/core-cli — 良

**概述**：单文件 C++ Host，仅 include facade 两个公共头；命令行解析、UTF-8/大小/JSON 形态校验、路径规范化后交由 `lmdj::facade::Application`，统一 JSON envelope 输出与退出码映射。

**优点**
- Facade 边界严格：无内部头；`cli_test.py` 对 include 白名单和禁用字符串做源码级断言（独立 grep 复核确认）。
- Product wiring 正确隔离：CLI 只链接 `lmdj::application`，assembly 由 product 侧单向注入。
- 请求文件 `O_RDONLY|O_NONBLOCK` + `fstat` + fd 全程操作，防 FIFO 阻塞与 TOCTOU；`OwnedDescriptor` RAII；写失败/异常双层兜底。

**问题**

| 严重程度 | 位置 | 说明 |
|---|---|---|
| 中 | `src/main.cpp:75-117` vs facade `c_api.cpp:74-116` | `valid_utf8()`（约 43 行）与 `kMaximumRequestBytes` 在 CLI 与 C ABI 两处逐字节重复，无单一事实来源；只修一处会导致两个 Host 校验不一致。建议下沉 foundation |
| 低 | `src/main.cpp:283-291` | `valid_workspace` 同时被用于校验 `--assembly` 路径，命名与用途不符 |
| 低 | `src/main.cpp:220` | 栈上 64KB 缓冲区，受限环境偏大 |

**测试覆盖**：参数形态、路径拒绝、请求文件边界（REQUEST_LIMIT±1、FIFO/符号链接/目录）、退出码映射、SIGPIPE、完整创作+崩溃恢复+golden WAV 逐字节比对、构建期链接库/头白名单自省——非常全面。小缺口：UTF-8 畸形分支未逐条覆盖。

---

### 9. apps/core-mcp — 优

**概述**：纯标准库 Python 的 MCP 2025-11-25 stdio JSON-RPC Host。`c_api.py` 经 `ctypes` 严格封装 `lmdj_core_c` C ABI；`server.py` 为协议状态机 + Schema 校验 + 工具路由。

**优点**
- 零第三方依赖且有 `ast` 级 import 白名单测试强制；只经 C ABI 交互，不解析任何 Project 内部结构。
- `c_api.py` 对 C ABI 所有失败路径（native 异常、指针契约不一致、非法 UTF-8/Unicode 响应、create 部分失败）显式清理并转 `CApiError`，`close()` 幂等——防御性极强的 ctypes 封装。
- `bounded_lines()` 流式限制单行缓冲，缓解无界内存 DoS；`additionalProperties: false` 阻止经 `arguments` 注入 `operation` 的路由劫持（有专门测试）。
- 畸形输入防护实测：非法字节、深嵌套 RecursionError、超限行、孤立代理对、批量请求拒绝且无副作用、BrokenPipe 静默处理。

**问题**：仅 2 处低——同一请求重复 `canonical_json` 序列化两次（性能）；跨语言重复的路径校验属有意边界防御，建议文档标注。

**测试覆盖**：启动期校验、生命周期状态机全部非法转移、Schema 逐字段比对、`FakeLibrary` 故障注入、CLI 与 MCP 双向互操作并逐字节比对 manifest/golden WAV——很难找到明显缺口。

---

### 10. providers/（local-proof-success / local-proof-failure）— 优

**概述**：一对对称的 proof Provider，精确对应 `AttemptStatus::succeeded`/`failed` 两条终态路径。本机实测 conformance 与 attempt isolation 测试均 PASS。

**优点**
- `run()` 只收 `AttemptId`、const `CapabilityRequest`、`ArtifactSink`，未触碰任何 Project/bundle 类型；有字节级 bundle 不变性回归测试。
- 失败经 `ErrorCode::provider_failed` 落 Attempt 状态而非 Project Truth。
- `module.json` 遵循 `lmdj.module.v1`，独立 SemVer `0.1.0` 与 `assembly.lock.json`、source-package sha256 机制完全对齐；`#error` 守卫防止遗漏 `SOURCE_PACKAGE_SHA256` 时静默产生错误身份。
- 结构完全对称，易维护、易审计。

**问题**：仅 2 处低——`local-proof-success/src/provider.cpp:47` 成功分支可与失败分支一致地 `std::move(attempt_id)`；两个 `factory.hpp` 缺说明性注释。

**测试覆盖**：conformance、attempt isolation、version lock 三层齐备，duplicate attempt id、policy 拒绝、provenance 确定性等边界均覆盖，无缺口。

---

### 11. products/lmdj（Product Assembly）— 优

**概述**：审查 `version.json`、`assembly.json`、`assembly.lock.json`、`CMakeLists.txt`、`src/compiled_assembly.cpp`，对照 `lmdj.assembly.v2` 与 `lmdj.product-version.v1`。实际执行版本校验、lock conformance、完整构建及全量 ctest（33/33），哈希人工复核一致。

**优点**
- 产品接线严格集中：唯一 Provider 静态链接在 `products/lmdj/CMakeLists.txt:6-11`；`apps/` 与 facade 生产代码无硬编码 Provider ID。
- `1.0.6.0` 符合 `MILESTONE.MINOR.BUILD.PATCH`，与治理文档 M1 PR6 吻合。
- 三方一致 + 双重校验：`assembly.json` / 各 `module.json` / `compiled_assembly.cpp` 版本一致；lock 哈希实测匹配；运行时 `load_assembly()` 将 Provider 工厂产出与声明逐字段比对。
- 无退役 contract 引用。

**问题**：仅 2 处低——facade 自身单测直接链接两个 proof Provider（不泄漏进产品运行时，但建议换 stub/mock）；`assembly_loader.hpp:31` 的 `assembly_schema_sha256` 字段名易与 `assembly_sha256` 混淆。

---

### 12. contracts/ — 良

**概述**：7 个 schema（assembly v1/v2、capability、error、module、project、version），全部通过 Draft 2020-12 元校验；统一 `$id`、`x-lmdj-contract-version`、`additionalProperties: false`、`contract` 判别字段；Contract ID `vN` 与 SemVer Major 全部匹配；实例验证通过。

**各子目录要点**
- **assembly**：v2 因新增必填 `provider_policy` 按 breaking change 升 Major 并保留 v1，与政策记载一致；代码只接受 v2。
- **capability**：最完整的 contract，`errors` 枚举 13 个 code 与 error contract 完全一致且有测试断言。无实质问题。
- **error**：`ErrorCode` 枚举一一对应，但见 C1。
- **module**：与政策示例逐字段一致，11 个 `module.json` 全部声明，依赖强制精确版本。无实质问题。
- **project**：16 组 contains 规则强制 4 banks × 16 pads 各恰好一次；`pattern_event` 不含 `asset_id`——schema 层直接落实 Pad Slot 不变量并有测试断言。
- **version**：四个独立整数字段正确体现"非 SemVer"，`build == 0 ⇒ patch == 0` 有条件规则。无实质问题。

**交叉一致性问题**

| 编号 | 严重程度 | 说明 |
|---|---|---|
| C1 | 中 | `lmdj.error.v1` 必填 `contract` 判别字段，但运行时所有错误输出只有 `{code, message, details}` 且 host 测试断言键集恰为这三个——当前无任何生产者能产出合法实例 |
| C2 | 中 | 代码读写并强校验 `lmdj.project.manifest.v1`（`project_store.cpp:1268,1609`），但 `contracts/` 下无对应 schema——持久化格式恰是跨版本兼容最敏感的数据 |
| C3 | 中 | Build Manifest 输出 `lmdj.build-manifest.v1` 并被 conformance 测试断言，同样无 schema、政策未提及该 ID |
| C4 | 低 | assembly 与 capability 的 `$defs.id` 语法漂移（前者允许段以数字开头） |
| C5 | 低 | `product_version` pattern 允许后三段前导零 |
| C6 | 低 | `uniqueItems` 无法阻止同一 id 不同 version 重复出现 |

**Retired-contract 检查**：活动树全量 grep 唯一命中为 `test_active_tree.sh:33` 的守卫断言——无违规。

**文档质量**：7 个 schema 共 0 个 `description` 字段；schema 旁无正/反例 fixture（政策要求打 contract tag 前配套，属打 tag 前需补齐事项）。

---

## 附录：验证记录

| 验证项 | 结果 |
|---|---|
| `scripts/core.sh configure/build/test dev` | 构建成功，ctest 32/32 PASS |
| `bash scripts/verify-core-dependencies.sh` | PASS |
| `bash tests/build/test_active_tree.sh` | PASS |
| `python3 tests/build/version_test.py` | PASS |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | PASS (1.0.6.0) |
| `python3 tests/conformance/version_lock_test.py` | PASS |
| ASan/UBSan（foundation、authoring-domain、audio-runtime 等重点复跑） | 无报警 |
| `sha256(assembly.json)` vs `assembly.lock.json` | 一致 |
| 退役 contract 全树 grep | 无违规 |

> 说明：本次审查环境未安装 `clang-tidy`/`cppcheck`，静态分析以人工逐行走读 + sanitizer 实测 + 数值交叉验证代替。
