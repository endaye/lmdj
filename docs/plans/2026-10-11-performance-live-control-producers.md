# D04 Performance 实时控制：producer／consumer 实施计划

状态：D0 技术设计 review 完成；Root完整三文档审阅与独立复核已确认R1–R6设计处置。后续产品实施与运行验收未完成，尾音决定仍pending。
产品依据：[已批准 D04 决定](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)。
技术提案：[初始状态、顺序和确认边界](../prd/decisions/2026-10-11-performance-live-control-encoding.md)。
当前问题：[hardware-control-mapping](../prd/questions/hardware-control-mapping.md)。
本计划部分解决 #1822；不关闭其他方向键／SHIFT 问题。

## Task premises refresh（issue-done §0）

2026-10-11 已实际 `git fetch origin main`，integration base 与本隔离 worktree base 同为
`4a2b26f03a1e628882e907c92a9b9411b48e110d`。源审计绑定这个完整 SHA。根 checkout 最新只读观察也为
`4a2b26f03a1e628882e907c92a9b9411b48e110d`；本 Task 未执行根 checkout/merge/reset，
该根 SHA 变化不能归因给本 Task。以下 disposition 对应 4a2 的完整定义、reader／validator／
operation registration、dispatch、正向控制测试与相关 successor scope。

| Premise | Disposition 与具体证据 | Task 约束 |
| --- | --- | --- |
| D04 产品决定尚未完成 | Already delivered：#1994、#1999；后者实际 merge 4a2。2026-10-10 D04 decision 有初始值、生命周期、record-start 与 meter 规则 | 不重新问已批准选择 |
| 监听输出 producer 缺失 | Already delivered：#1910 merge `9119a7f90262e1c8ada92ac6b894f5014a5c0cab`；SDK MonitorOutputSession、runtime_session 与 App ENC4 真实绑定 | 不建立 Core master gain、不碰 MASTER owner |
| MASTER consumer 尚未集成 | PR #2000 OPEN，head `a5580f6b90d4f3d28b82a8dabab40b1be16713aa`，实际仅 7 文件监听 consumer/测试/Portal/计划 | C1/C2 开始前按实际 merged scope 刷新，不重复实现 |
| 独立 Filter 已有 producer | Still outstanding：MasterFxChain::process_filter 只有 0–1000 scalar／500 bypass；完整 Performance variant 与 Web validator 没有 type/cutoff/resonance；旧 LP/HP PCM 测试为正向控制 | F1 仅增加 independent branch，旧 Filter 保留 |
| 64-Pad live Mute/Solo 已有 producer | Still outstanding：RealtimeEngine voice mix 无 live masks，已有 playback.muted 为 Truth；Domain/Host 完整注册和 Replay sink 均无新事件 | M1 仅 live gate；不能用 Sample mute 充数 |
| 录制已有完整初始状态 | Still outstanding：Performance 闭合 6 键、Journal checkpoint 闭合 4 键，begin 后 Creator 才补 HOLD/open FX；新 header/typed events/ACK 尚无 | P0/P1 捕获 Core fence 起点，不从 UI 推断 |
| Core 竞态前置未合并 | Already delivered：#1984 merge `aa12f7f1a3a2b62f965a28e3d91e5a2e55d7e889` 的 Pattern reset/admission scope；#1992 merge a98 是播放中 Pattern 切换及显示 | 不重复其修复；本 Goal 的 fresh full+stress 验证由 Root 单独持有，不能在此声称通过 |
| Browser timeout 修复能顺便完成 D04 | Unrelated owner：PR #2001 OPEN，head `21f28e056f28540b09c453475c203716c38a3226`，实际 4 文件是历史导航保留与测试 | D0 不碰 Root App/history/Workspace 文件 |
| Mute 共享效果尾音已获批准 | Pending：实际 owner 回答未到；推荐 pre-shared-FX gate + 自然共享尾音，另一选项需 per-Pad FX 架构 | 不启动 M1 或依赖其声音语义的实现 |

D0 新建的 branch 为 `docs/performance-live-control-design`，worktree 为
`/Users/endaye/Projects/lmdj-wt-performance-live-control-design`。已逐项读取 live PR file lists
并查 Git/Orca worktrees 与 agent ownership；这三份文档无现有 owner 重叠。
使用 command-local `git -c core.symlinks=true worktree add`，Orca inventory 已识别其
独立 worktree；创建后 root main SHA 未变。没有修改 shared config、运行 setup hook、
开新 TUI 或清理其他 worktree。

提交和最终 premerge 前再 fetch/刷新 relevant successor scope；若新 producer 已交付，
删掉重复工作并保留 delivering merge 证据。Issue 状态、标题、空搜索不是 delivery 证明。

## 最小实现边界与依赖

D0先review optional header、新profile无coalescing、Core input_sequence、Core fence／Web
capture两个ACK、七FX binding/adoption、bounded durable receipt与Journal faults/exact
retry、lost-owner recovery-only closure/seal、epoch/reset ACK和legacy Filter ownership。方案细节在上述
技术提案，不把 Task 交给实现者再自行决定产品 Contract/concurrency。

`D0 → P0` 与 `D0 → F1` 可并行；`F1 合并 + owner 尾音实际回答 → M1`；
`P0 + F1 + M1 → P1 → W1 → C1 → C2`。
P0 与 F1 的 source 文件互不重叠，可在 D0 接口 review 后并行；F1/M1 共用 engine
和 Audio Portal，必须顺序合并。M1 还等待实际尾音回答。P1 在 P0/F1/M1 都交付后闭合
admission、record/replay、begin/reset；不能只接 UI 假 projection。C1/C2 共用 Perform/
样式/Portal，顺序合并，并吸收 MASTER #2000 的实际 main source。未选的 meter producer、
Numeric、BPM、键盘 #1960、其他方向键、V1、release 不混入以下实现提交。
尾音pending只约束M1和真正依赖其声音语义的Task，不作为D0、P0或F1的shipping前置；
这些独立Task仍须各自满足技术review、最低验证和正常shipping保护，不默认任何尾音选择。

每个 implementation Task 一个 Conventional Commit，只 stage 本节的 exact files。
新文件标 new；既有路径均已在 4a2 用 git cat-file 确认存在。实现若需要额外文件，先
调整该 Task 声明与最低层验证，再编辑；不能用此计划授权跨 Task 的 shared source。
本计划不新增 CMake/test registry 条目，沿用已有有意义的 suite，而非复制实现的微测试。

最低层验证先检查直接 owning unit/component/contract；异步/queue 变更还必须执行原 stress
selector 和预算，不能用默认 `test dev` 冒充 stress。可通过 `build/core/dev` 的 exact
CTest regex 选已有 suite；stable configure/build/test entrypoint、tier 与本地平台边界
沿用 [Core test policy](../quality/core-test-policy.md)。各实现 Task 的 selected batch-only
lane 另按 committed head 收集 pass key；focused oracle 不等于整个 lane 或发布验证。

## D0 — 锁定 D04 live-control 的耐久与重放设计

依赖：none。状态：R1–R6已获设计处置；Root已通读完整709/13/474行修订及实际recovery源，独立最终复核findings=[]，仅表示设计层闭合。

D0以完整三文件设计及实际轻量检查完成原子shipping，仍须正常current-head review、
冲突及conversation保护；不依赖尾音答复。尾音保持pending，M1不启动。完整评审保留
原R1–R6反例与未实施边界，不把文档交付当DSP、录制、恢复或浏览器验收。
本文没有授权release或cleanup。
最低验证：三文件 diff/check、所有实际相对链接与 declared path、new-path ownership、
Documentation-impact body。设计review逐条覆盖技术提案九个反例与R1–R6，缺失reply不默认批准。
没有产品源码修改，不运行 Core/native/browser/Portal suites。

Declared files（完整边界）：

- `docs/prd/decisions/2026-10-11-performance-live-control-encoding.md (new)`
- `docs/prd/questions/hardware-control-mapping.md`
- `docs/plans/2026-10-11-performance-live-control-producers.md (new)`

Lowest-tier meaningful verification / defect oracles：

- 确认新文档内部链接、旧决定与本设计的替代范围；独立设计 review 逐条确认兼容、起点 fence、排序、失败/重试；无实现测试可替代设计 review

Version impact: none: technical design only; no manifest/schema/source changes

Documentation impact: none — D0 仅未实施 PRD/计划，不改变当前 Portal source facts。

## P0 — 耐久 Performance 初始状态与控制变更格式

依赖：D0。状态：未实施；须先完成前置。

只实现新 profile 的耐久数据边界：header／新 events／序号、strict shape、旧 reader
fingerprint、begin/flush/stop/save/reopen、Journal checkpoint/recovery及新增bounded
admission ledger／complete metadata record和cooked projection。
不在此 Task 实现实时 DSP、Facade readiness 或 Creator 控件。
Domain 验证要接受初始 engaged/frozen/HOLD seed，旧 no-header validator 原样；durable
PadHit 用 press sequence，预约 Pattern 用原请求 sequence，high-water 不等于 canonical
列表最后的序号。Project Store 的 receipt lookup 先于新 profile 选择。
新增ledger只有1pending+最近1completed，expected_recording_sequence由Core发出；
receipt含requestID/rawrequestSHA256、冻结tick/input_sequence、阶段/result/event序号列表。
prepared与admission_complete是不同Journal record，后者不重新分配音乐序号。
new-profile discriminator和内部Journal grammar在本Task实际review迁移；旧v1分支不改。
对unknown-write的持久化fixture明确恢复present/absent，不静默降成known failure。
lost-owner收尾经原exclusive writer/reconcile，验证完整prefix和原identity后允许metadata-only
logical closure/seal，原prepared ledger保持unknown；不伪造complete、改变原结果或补声。
复用tail/checkpoint/sealed snapshot，不加无必要record kind；terminal旧pending不占新session窗口。

Declared files（完整边界）：

- `contracts/project/lmdj.project.v5.schema.json`
- `packages/authoring-domain/include/lmdj/domain/project.hpp`
- `packages/authoring-domain/src/project.cpp`
- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/src/project_store.cpp`
- `packages/project-io/include/lmdj/project_io/sequence_journal.hpp`
- `packages/project-io/src/sequence_journal.cpp`
- `packages/project-cooker/include/lmdj/cooker/performance_replay.hpp`
- `packages/project-cooker/src/performance_replay.cpp`
- `tests/conformance/schema_contract_test.py`
- `tests/fixtures/contracts/project-v5-live-controls-valid.json (new)`
- `tests/fixtures/contracts/project-v5-live-controls-invalid.json (new)`
- `tests/core/domain/performance_test.cpp`
- `tests/core/project_io/performance_journal_test.cpp`
- `tests/core/project_io/performance_lifecycle_test.cpp`
- `tests/core/cooker/performance_replay_projection_test.cpp`
- `apps/docs-site/docs/contracts/project.mdx`
- `apps/docs-site/docs/core/modules/authoring-domain.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/core/modules/project-cooker.mdx`
- `docs/plans/2026-10-11-performance-live-control-data.md (new)`
- `apps/docs-site/diagrams/authoring-domain.architecture.json`
- `apps/docs-site/static/diagrams/authoring-domain.html`
- `apps/docs-site/static/diagrams/authoring-domain.svg`
- `apps/docs-site/diagrams/project-io.architecture.json`
- `apps/docs-site/static/diagrams/project-io.html`
- `apps/docs-site/static/diagrams/project-io.svg`
- `apps/docs-site/diagrams/project-cooker.architecture.json`
- `apps/docs-site/static/diagrams/project-cooker.html`
- `apps/docs-site/static/diagrams/project-cooker.svg`

Lowest-tier meaningful verification / defect oracles：

- schema conformance: old valid v5 remains valid; malformed type/ranges/masks/order rejected
- domain.performance: all initial fields and changes round-trip; duplicate/out-of-range slot rejected; ordinals 0–6 and old canonical ordering unchanged
- project_io.performance_journal + performance_lifecycle: begin/flush/stop/save/reopen保留header、logical open-FX checkpoint与ledger；prepared/complete各自unknown present/absent、torn/checksum拒绝；no-op/release/未来Pattern都保持原request绑定，metadata complete不消耗音乐sequence
- Journal recovery owning oracle: C1 expected0→C2 expected1→reattach时C2exact返回seq、同identity变payload碰撞、C1原wire明确retry_expired零重新enqueue；pending/completed各≤1，flush/recovery不丢窗口；无legacy receipt自动升级
- owner-loss recovery oracle: prepared后publish前/后、complete前崩溃→validated exclusive reconcile→logical closure/seal/terminal→原pending仍unknown；closure/seal各present/absent/unknown同identity有界metadata恢复，旧retry零enqueue且新Performance空ledger可独立begin；legacy recovery保持
- cooker.performance_replay: initial state survives even zero events; explicit initial state is independent of first event tick, fixed revision/material identity unchanged
- scripts/docs-site.sh check; ownership admission for new fixtures

Version impact: Project Contract additive MINOR candidate only if every old valid v5 remains valid and old semantics unchanged. Public Performance variant/struct and ProjectState layout imply authoring-domain ABI MAJOR; changed public I/O request/checkpoint/projection layout implies dependent Module MAJOR debt. Exact versions and lock settlement belong V1; schema metadata/conformance expectation must advance together in this Task, never ship unversioned new persisted syntax. 新内部Journal profile/complete-record迁移须明确登记review，现有源码v1 ID不被误当成已支持新ledger。

Documentation impact: required — `/contracts/project/`, `/core/modules/authoring-domain/`, `/core/modules/project-io/`, `/core/modules/project-cooker/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## F1 — 独立 LP/HP/BP、Cutoff、Resonance 的实时 DSP

依赖：D0。状态：未实施；须先完成前置。

只增加 audio-runtime 的 typed independent Filter、单一 stage ownership 和 bounded
master-control reservation/ACK 所需 Filter 状态。Core DSP types 与 Domain persisted types
保持 explicit boundary translation，不借此把 Host 的 Hz 换成 Sample Tone。
建议 TPT/Q/ramp 细节见技术提案，独立 review 后落实；旧 scalar path 与 golden 固定。
把 accepted/enqueued 与 coherent applied state/epoch/token 分开；不新增 render mutex、
allocation、unbounded retry 或额外 master output gain。mask 命令的声音作用留 M1。

Declared files（完整边界）：

- `packages/audio-runtime/include/lmdj/audio/master_fx.hpp`
- `packages/audio-runtime/src/master_fx.cpp`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/master_fx_test.cpp`
- `tests/core/audio/master_fx_determinism_test.cpp`
- `tests/core/audio/master_fx_allocation_guard_test.cpp`
- `tests/core/audio/master_fx_stress_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `docs/plans/2026-10-11-independent-live-filter-dsp.md (new)`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

Lowest-tier meaningful verification / defect oracles：

- audio.master_fx: default OFF is bit-identical bypass; LP/HP/BP frequency response has independent oracles; changing each parameter preserves the others; 20 Hz/20 kHz and 0/100% finite/stable
- audio.master_fx_determinism: same explicit integer control stream produces same output across real engine and shared DSP; independent golden/reference analytic values, not only two copies agreeing
- audio.master_fx_allocation_guard: all new parameter changes, HOLD/release/neutral stay zero-allocation/no render lock
- audio.master_fx_stress: original full stress selectors/timeouts unchanged; add parameter churn + queue rejection/epoch tests, not lowered budget
- scripts/docs-site.sh check

Version impact: audio-runtime ABI MAJOR debt because public Fx/RealtimeEngine layouts grow; legacy Filter branch and its original golden vectors unchanged. No Project Contract or Product Build allocation in this DSP Task.

Documentation impact: required — `/core/modules/audio-runtime/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## M1 — 64-Pad live Mute/Solo 的实时声音门控

依赖：F1 实际合并 + owner 尾音实际回答（F1 本身依赖 D0）。状态：未实施；M1 等待 owner 回答。

**Blocked pending owner tail answer；本计划当前不授权启动。**
若批准推荐：在工程 Pad voices 的 shared-FX 输入前增加 96-frame gate gain，cursor
继续、解除恢复当时声音；共享 Delay/Reverb 尾音自然衰减。复用有界 master-control
queue，atomic 同时设置两组 uint64 mask，mask/status/reset 是一个 producer。
若要求每 Pad 历史尾音隔离：本 Task 需先被新的 architecture/CPU/memory/resample
计划替代，不能靠清空总线实现，也不能沿用本节文件声明直接扩 scope。

Declared files（完整边界）：

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `tests/core/audio/master_fx_allocation_guard_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `docs/plans/2026-10-11-live-pad-mute-solo-dsp.md (new)`
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

Lowest-tier meaningful verification / defect oracles：

- audio.realtime_engine: masks address slots 0 and 63; multiple Solo and Mute priority; persistent Pad muted remains an additional prohibition; Bank/Pattern replacement preserves masks
- native PCM oracle with two distinct sustained Pad signals: mute/solo affects both existing and newly played Pad voices; timeline and tail policy match reviewed design; clear restores intended sound without retrigger
- audition is not Pad A01: sentinel audition bank excluded from Pad mask, real Pattern/replay/live Pad voices included; metronome path not modified
- queue-full and stale epoch fail-closed; reset, start/stop and project replacement leave no old mask
- existing allocation guard and audio.realtime_spsc_stress original tier/budget, with actual concurrent producer/consumer stress for new queue state
- scripts/docs-site.sh check

Version impact: audio-runtime ABI MAJOR debt; no persisted PadPlayback, RuntimeSnapshot or Project authoring mutation added. F1/M1 share engine files and must land sequentially.

Documentation impact: required — `/core/modules/audio-runtime/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## P1 — Facade 一次 admission、录制起点和重放/neutral 闭合

依赖：P0, F1, M1。状态：未实施；须先完成前置。

闭合 Core 一次 admission kernel、record start fence 和 actual applied state、Header
Replay-before-Pad、recording/live exact retry、stale epoch 与所有 neutral 终态。
Begin校验applied header和engaged binding generation同epoch才core_control_ready；
Facade不启动Webtap，也不宣称host_capture_ready。它不是等待任意enqueue counter增长。
既有 legacy request/fingerprint 走原分支；新请求携带 Core-issued epoch，不接受 Host
header/tick/frame/sequence。known failure/unknown fault/publish/ACK 的事实分别返回。
Core首Pad gate只证明control-ready，SDK另等待真实capture-start ACK；reset queue-full
保持pending。为七已有FX及Filter跟踪Core runtime generation，begin只为engaged分配
持久logical recording gesture并返回mapping，frozen-only无open gesture；不执行fakeengage
或reset DSP。move/release验证logical/runtime双绑定，begin期间FIFO dequeue取mapping。
新profile禁全部FX move coalescing，完整接受的改变各保留tick/sequence；旧128tick不改。
Pattern序号从当前ACK分配改成new-profile成功请求reservation时冻结，ACK复用；自动
FX/HOLD关闭逐事件分配唯一Core sequence。新增recording expected窗口与durable
prepared→publish→complete闭合，metadata unknown不重新enqueue。原runtime丢失后的
new-profile reattach只查询/显式finalize，不自动复活producer或恢复录制输入。
普通pending guard不阻止已证明producer丢失/旧epochquiescent的recovery-only收尾；exclusive
writer/完整prefix/原identity证明缺失或仅ACK超时均不能进入例外。P0 closure/seal未知结果
保持unknown直到canonical终态确认，Facade不伪造completion/appliedACK或重投声音。
现有 resample/capture receipt 的原 Wav 仍 authoritative；event Replay 不宣称重建其 PCM。

Declared files（完整边界）：

- `packages/application-facade/include/lmdj/facade/performance_ports.hpp`
- `packages/application-facade/include/lmdj/facade/performance_replay.hpp`
- `packages/application-facade/include/lmdj/facade/performance_engine_adapter.hpp`
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/src/application.cpp`
- `packages/application-facade/src/performance_replay.cpp`
- `packages/application-facade/src/performance_runtime.cpp`
- `packages/application-facade/src/performance_engine_adapter.cpp`
- `tests/core/facade/performance_operation_contract_test.cpp`
- `tests/core/facade/performance_gesture_admission_test.cpp`
- `tests/core/facade/performance_session_test.cpp`
- `tests/core/facade/performance_replay_test.cpp`
- `tests/core/facade/performance_engine_adapter_test.cpp`
- `tests/core/facade/performance_runtime_bridge_test.cpp`
- `tests/core/facade/resample_performance_test.cpp`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `docs/plans/2026-10-11-performance-live-control-admission.md (new)`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`

Lowest-tier meaningful verification / defect oracles：

- facade.performance_operation_contract: exact typed request/response keys; Core-owned time/sequence, target identity; no Host supplied tick/frame/order
- facade.performance_gesture_admission: 同recording identity/payload exact retry一次；prepared absent/present与complete unknown分别故障注入，tick/sequence不二次分配，publish后metadata重试零重复apply；C2exact/collision、C1expired和staleepoch均有far-side zero-enqueue断言
- facade recovery/finalize oracle: producer真实丢失后的prepared unknown可经recovery-only closure/seal到terminal，sealed旧retry只查unknown且零enqueue；ACK超时/仍有效lease拒绝例外，latecallback不能复活，下一Performance新ledger不被旧terminal pending堵住
- existing FX owning oracle: pre-begin engaged Delay500 + HOLD frozen Reverb700；Core mapping只含Delay，首move600/release配对、group保持、leave/HOLD按生命周期；旧g/late callback无法冒充new generation，begin不假engage、不重置既有DSPbuffer
- owning recording/replay oracle: Delay Move500@(16,10)→Pad@(32,11)→Move900@(64,12)跨实际render quantum均保留，新profilePad32前状态500；同tick两个次序与原request序号futurePattern；旧profile128tick/ordinal/fingerprint固定
- begin fence deterministic interleaving: change pre-begin/while asynchronous begin/post-begin, then first same-tick Pad; header matches authoritative initial state and every later accepted change appears once
- journal faults before write/unknown after write: preserve irreversible audio effect and explicit recovery/unknown state; no optimistic rollback claim or automatic replay under new event ID
- facade.performance_replay + engine_adapter: initial header applied before any Pad/Pattern including zero-event Performance; type/Cutoff/Resonance + mask changes actually reach same DSP; complete/Stop/owner loss/reset queue pressure waits for new states neutralized
- recording stop alone retains live performance state (old FX independent-toggle rule); leaving Perform clears masks even HOLD=true but filter follows HOLD; project change clears both through engine lifecycle
- resample_performance: confirmed live capture PCM identity/length remains authoritative, never re-render invented audio
- scripts/docs-site.sh check

Version impact: application-facade ABI MAJOR debt if public ports/config/adapter layouts grow; C ABI envelope need not change unless design chooses otherwise. No silent api_version bump or guessed Module/Product identity.

Documentation impact: required — `/core/modules/application-facade/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## W1 — Web Host 和 typed SDK producer 接口

依赖：P1。状态：未实施；须先完成前置。

在严格Host registration/validator、typed SDK serializer/status和Runtime action FIFO
暴露new profile、expected-recording窗口、Core FX binding与begin mapping。真实capture
controller/worklet新增started应用ACK，闭合generation+epoch/session/begin binding；
RuntimeSession在await前占有pending start，避免active=null期间并发start。
Core-ready和Host-capture-ready为不同producer，SDK等两端匹配同target/begin后才
放行recorded input。close/replacement/processor fail/错ACK取消并走bounded stop清理；
不能证明tap停下则unavailable至quiescent replacement，不能复用lateACK。
SDK原FIFO改为最多1inflight+1普通waiting、最多64openPad各保留1release slot及1cleanup
token；超额明确拒绝，不合并已接收控制值、不丢matching release；cleanup取消未admitted
promise须明确reject。old Project callback不得落新epoch，动态unavailable不伪造值。
所有64slot数组与 uint64 opaque序号显式校验，无 JS 32-bit mask或unsafe Number。
node protocol/session及capture-controller/worklet是最小serializer/FIFO/actual-start oracle；native bridge 是真正 Facade registration
oracle，不靠一份 mock SDK 验证真实 C++边界。

Declared files（完整边界）：

- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/performance_master_tap_worklet.js`
- `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-11-web-live-performance-controls.md (new)`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`

Lowest-tier meaningful verification / defect oracles：

- host.web_performance_bridge: exact registrations/validators for live/status/recording initial/new events; native boundary rejects unknown/extra fields, invalid units, 64-bit lossy masks
- control_runtime: live command bound to actual retained Project + engine epoch; late old-target commands cannot affect replacement Project; Bank/Pattern changes preserve state
- Node performance_protocol/runtime_session: camelCase↔wire conversion exact; sorted unique 0..63 slots round-trip; Runtime action FIFO, original same-identity failure retry and closed/replaced Session guards
- Node capture controller/worklet owning oracle: start promise在实际started ACK前pending；错generation/epoch/binding、close、processorfailure、timeout无firstPad放行或lateACK继承；正常ACK后首跨quantumPCM被capture；原batch sequence/stop严格断言保持
- runtime_session owning oracle: Core fence已ready而worklet start延迟时SDK仍pending且零Pad/Pattern投递；两个ready后才原FIFO放行；await前pending owner拒绝第二start，closed target不能复用ACK
- Node producer statuses分别显示Core accepted/applied、capture armed receipt与reset；bounded backlog压力固定inflight/waiting/release上限，超额明确失败且已接收release/cleanup最终完成；不可用不伪造neutral
- scripts/docs-site.sh check; TypeScript consumers compile

Version impact: web-runtime-platform MINOR if typed/JSON additions remain compatible; ABI MAJOR if any public C++ layout or dependent ABI changes. 真实capture worklet/controller protocol新增started与begin binding，部署必须配套同SDK/worklet，旧cached工作流不得假成功。Exact Module/Host settlement in V1; Product Assembly changes not hidden here.

Documentation impact: required — `/core/modules/web-runtime-platform/`, `/platform/web-runtime/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

W1开始前须刷新meter owner实际合并scope；若meter已改tap/controller/session，以实际
source协调该4文件并保持capture-start owning oracle，不能借meter省略本producer缺口。

## C1 — Creator 独立滤波参数组与旋钮/触摸 consumer

依赖：W1, MASTER PR #2000 integration。状态：未实施；须先完成前置。

消费真实 typed producer：主组 Cutoff/Delay/Reverb，FILTER type/同Cutoff/Resonance。
进 FILTER 不调用 enable；rotary rest/group 不 release；touch/blur/cancel 保持旧 release。
读回 OFF、frozen、applied/pending/unavailable，不能从旧 percentage猜 Hz。ENC4/MASTER
复用#2000同一个monitor，不新增save/Undo或400ms工程提交。七已有FX也走新typed
generation route；new begin消费Core mapping，不沿旧synthetic engage补起点；legacy
begin的原seed保留旧分支。FIFO dequeue取mapping/expected、callbacks验证epoch/token，
真实capture ACK未到不放行首Pad，bounded pending/Pad release规则同W1。
real packaged Perform journey 在 committed head 证明 Control→PCM、HOLD/离页、Record/
Stop/Save/reopen/Replay 的每一侧；不可用 audio/device/hearing 分别标 unknown，不能冒充验收。

Declared files（完整边界）：

- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-11-creator-independent-filter-controls.md (new)`

Lowest-tier meaningful verification / defect oracles：

- component/controller: primary ENC1 Cutoff, ENC2 Delay, ENC3 Reverb; FILTER ENC1 LP/HP/BP, ENC2 same Cutoff, ENC3 Resonance; More preserved, ENC4 always monitor
- component: OFF LP/20kHz/0%; enter FILTER no producer call and no audible enable; logarithmic Cutoff endpoints and SHIFT fine steps; rest/group changes preserve rotary state; release/blur/cancel semantics for touch preserved
- typed controller初始state与Core mapping实际read/ACK，非percentage推导；七FX起点engaged/frozen、首move/release、begin异步积压、late generation/epoch均far-side验证；new profile无fakeengage，legacy seed仍走旧分支；三独立参数各一次录制
- component/SDK failure oracle: Core-ready而capture未started时firstPad被gate；完整ACK后原FIFO恢复，积压超限明确失败但matching release/cleanup完成；SHIFT/触摸生命周期不缩减
- current committed-head packaged Perform native/browser journey asserts actual PCM/type/ranges/rest/switch/exit/HOLD/replay/reopen; original budgets and all legs retained; full selected batch-only lanes collected separately
- TypeScript + ownership + scripts/docs-site.sh check

Version impact: Creator compatible new public interaction MINOR debt; no Project authoring parameter/400 ms save semantics or second master gain.

Documentation impact: required — `/hosts/creator-web/`, `/hosts/creator-interactions/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## C2 — Creator 当前 Pad Mute/Solo 与 64-Pad 状态 consumer

依赖：W1, C1 integration。状态：未实施；须先完成前置。

消费 Core 64slot mask：针对明确 current Pad 的两个独立状态，Bank转换不丢视图，
multiSolo/Mutepriority的 active/silenced 表现和实际 producer一致；late callbacks受epoch保护。
录制起点已有 mask、后续变化、离页/换工程 ACK全闭合；不修改 Truth muted、Undo或localStorage。
不重复 #1960键盘映射，也不借 Pad visual state重写 MIDI/SHIFT或导航。

Declared files（完整边界）：

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-11-creator-live-pad-mute-solo.md (new)`

Lowest-tier meaningful verification / defect oracles：

- component: explicit current Pad address, two independent aria-pressed states, multi Solo and Mute precedence; Bank change reveals same 64-state, persistent playback.muted not changed
- real App: current Pad/Bank identity and late callback guards; navigation/project replacement clears producer and UI, HOLD cannot retain Mute/Solo; recording start preexisting mask+later events retained
- native/browser: distinguishable two-Pad PCM, A01/D16 identity, Bank and Pattern switching, multiple Solo+Mute, actual leave/reset, Record/Stop/Save/reopen/Replay initial and subsequent states
- old keyboard mapping and SHIFT/MIDI semantics not changed by this Task; do not duplicate #1960
- TypeScript + ownership + scripts/docs-site.sh check

Version impact: Creator compatible public interaction MINOR debt; no Truth Pad mute mutation, localStorage mask, authoring Undo or recording/output-level change.

Documentation impact: required — `/hosts/creator-web/`, `/hosts/creator-interactions/`；上列源图与生成 HTML/SVG 同 Task 更新，不能只改计划。

## Version Management

Version impact: none — 当前 D0 只改三份设计文档，无 source/Contract/Module/Host/Build 更动。
实现影响按每 Task 上述具体边界负责，不以“暂不改 manifest”掩盖 ABI debt。

| 当前 active manifest / schema | 4a2 的真实 identity | 后续影响 |
| --- | --- | --- |
| Project Contract | lmdj.project.v5 / 5.3.0 | P0 optional header/new-profile 是 MINOR 候选；schema/conformance 同提交，旧输入/含义必须保留 |
| authoring-domain | 4.4.0 / api 1 | Public Performance variant/ProjectState layout 增长需 ABI MAJOR |
| project-io | 7.1.0 / api 1 | Begin request/checkpoint 与下游 public ABI 检查，MAJOR debt |
| project-cooker | 2.1.0 / api 1 | ReplayProjection layout 和 Domain ABI，MAJOR debt |
| audio-runtime | 5.2.0 / api 2 | RealtimeEngine/Fx layout/新 port，MAJOR debt |
| application-facade | 6.7.0 / api 3 | virtual port/config/adapter ABI，MAJOR debt；C envelope 不变不代表无影响 |
| web-runtime-platform | 5.8.0 / api 2 | strict additive SDK 可 MINOR，若 public ABI/依赖 ABI 变则需 MAJOR 结算 |
| creator-web | 6.0.0 / api 2 | 新兼容交互 MINOR debt；依赖/Host identity 按实际源变更结算 |

这些版本由实际 manifest 读取，仅表示 inspected base，不是拟分配的新 identity。
V1 另立原子 identity/Assembly-lock/Build Task，逐项检查 ABI 与依赖闭包；未结算期间
各 Task 必须显式登记真实 debt，禁止声称二进制向后兼容或发布可用。Contract新语法
本身不等 V1 才版本化。新 Product Build/Assembly 必须 Documentation impact: required
和 immutable portal snapshot；local build/PR preview 不产生 snapshot，更不授权 release。

## Documentation Impact

Documentation impact: none — 此 D0 只新增待 review 技术提案、计划和修正开放问题范围，
未改变实现、source facts或 identities。实现 Task 的 required routes/source graphs 已按
owner 分列，D0 不修改其共享 Portal，也不运行 Portal build。

## D0 的具体设计 review 与轻量证据

Review必须直接比对完整三文件draft及base/source证据，不以本文勾选自我认证：

- legacy no-header输入、0–6排序/语义/fingerprint和旧Filter PCM保留；新语法写入须版本化。
- header实际applied状态冻结于fence，capture/firstPad须等两端ready；两个sameTick反例解释
  全事件input_sequence的最小必要范围，durable sequence与audio applied token明确分离。
- prepared/complete两阶段Journal、1pending+最近1completed与超窗拒绝、reservation/epoch/resetACK；C1→C2→reattach、sameidentity exact/collision及capacity边界。
- lost-owner recovery-only例外与普通pending guard分开；closure/seal present/absent/unknown保留原identity及未知事实，不假complete/ACK或补声；terminal旧ledger不阻塞新Performance。
- 七FXCore binding/逻辑mapping、engaged/frozen/stale callbacks、无fakeengage；new profile无coalescing的跨Pad/Pattern反例；真实worklet started ACK及4个W1声明文件。
- all64 slot、multiSolo、Mutepriority、audition/metronome排除、HOLD与离页两类清理。
- owner尾音答复仍pending；Q曲线/ramp属于技术提案待review，不冒充已批准听感。
- D0/P0/F1不依赖尾音答复，M1及声音语义依赖Task仍blocked；正常review/light验证/shipping保护不省略。

具体命令/argv、exit、三文件hash、local links/new-path owner/body verdict保存在该Task
外部证据目录；正式receipt应记录实际结果，不预填pass。产品测试与heavyPortal未执行，
本D0不提供DSP听感、浏览器、设备、full/stress、complete-self-test或release证据。
