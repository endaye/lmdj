# Creator P2.7：Tempo/Swing 直接调节、Tap Tempo 与节拍器（#1672）

## Outcome and authority

对齐 Koala 5.3 与调研 Q7：

- Tempo 与 Swing 直接调节——拖动、±步进、Tap Tempo，没有 Apply 按钮；
- 节拍器一键开关，播放与录音中可闻，永不进入任何录制；
- 改动立即生效，或在文档化边界生效（播放中 BPM 下一小节；Swing 烘焙进之后录入的事件；录音中拒绝）。

产品决策记录在 [`2026-10-02-creator-tempo-metronome.md`](../prd/decisions/2026-10-02-creator-tempo-metronome.md)。其他依据：

- 2026-09-29 workflow baseline 第 1、3 项与设计 §6；
- 2026-08-23 Sequence 录音语义（Swing 录入烘焙；录音中拒绝）；
- 2026-08-26 BPM 决策（节拍器是 BPM 消费者）；
- 2026-09-30 Undo/Redo 语义 §4（拖回原位不产生记录）。

工作分为四个 Task。每个 Task 是一个 Conventional Commit；T1 独立一个 Pull Request，T2+T3+T4 一个 Pull Request（T3 依赖 T2 的访问器，T4 记录 T1–T3 的交付）。每个 Pull Request 完成验证、推送、current-head review 与 squash merge。没有 Task 做发布、分配 Product Build 或清理 worktree。

## Facts this plan relies on

Checked on `e4e17e7f`.

- **写入路径已存在。** `sequence_touch_workspace.tsx` 的 `onSettingsChange` → `app.tsx:1587-1624` `updateSequenceSettings`（经 `sequenceAuthoringTail` 串行化）→ `session.updateSequenceSettings`（`runtime_session.mjs:3586-3650`，JS 侧先校验 bpm 40–240、swing 50–75）→ Host `sequence.settings.update`（`control_runtime.cpp:4447-4524`）。成功响应已带 `pattern_publication.activation_frame`（bpm 非空时），app 目前忽略它。
- **生效边界。** 播放中改 BPM：当前 Pattern 重新发布，`activation_frame` = 旧 tempo 的下一小节边界（`realtime_engine.cpp:1237-1256`；证明测试 `control_runtime_test.cpp:2280-2368`）。停止态：发布在帧 0 生效（`realtime_engine.cpp:1264-1265`）。
- **录音中拒绝是两层。** UI 预拒绝（`app.tsx:1597-1603`）加 control layer `HOST_STATE_INVALID`（`control_runtime.cpp:4467-4472`）。本计划不改变它。
- **Swing 不进播放调度。** `packages/audio-runtime` 与 `lmdj.runtime-content.v1` 没有任何 swing 概念；swing 只在录入 admission 时由 `domain::quantize_onset_tick` 烘焙（`pattern_admission_controller.cpp:759`）。直接 Swing 控件的验收只能断言 Project Truth 与之后录入的事件。
- **每次提交都是一个 revision。** `UpdateSequenceSettings` 是普通可撤销 Authoring Command：一次提交 = 一个 Project revision = 一条历史记录。所以拖动必须在手势结束时才提交一次。
- **手势模型已有先例。** `parameter_slider.tsx`（176 行）：拖动预览、松手/键抬起/blur 提交一次、Escape/pointercancel 取消、音频挂起强制取消；但它硬绑定 `PadPlayback` 的 `field` 联合类型。
- **引擎帧与 context 帧 1:1。** worklet 每个回调处理 128 帧（`realtime_audio_worklet.cpp:37-38,104`），门打开时无条件 `engine.render`（141），`rendered_frames_` 在每个 render 调用前进（`realtime_engine.cpp:1951-1957`）。`engine.start()` 把帧计数归零（1655，`control_runtime.cpp:4108` 的 `audio.activate`），所以**每个音频纪元一个锚**，纪元切换对 app 可见（audio phase 变化）。门只在中断/挂起路径关闭，且总是伴随 `engine.stop()`。
- **JS 今天拿不到任何音频时间。** `packages/web-runtime-platform` 中 `currentTime|currentFrame|getOutputTimestamp|outputLatency` 零匹配；但回调心跳已桥接（`web-runtime-pre.js:146-148`，`runtime_session.mjs:2698-2711` 自用于激活等待），且会话支持注入 `createAudioContext`（`runtime_session.mjs:1302-1304`；Creator 今天在 `main.tsx:77-113` 没注入）。
- **引擎帧↔context 时间的锚可行（纯 JS）。** 激活顺序是：建 context → 挂起 → 建 worklet → resume → `audio.activate`（门开、帧归零）→ running（`runtime_session.mjs:2783-2921`）。`audio.activate` 返回后立即同读（心跳, context.currentTime）即得锚，误差 ≤ 门开后到读取之间的回调数（≤ 约两个量子 ≈5 ms），纪元内 1:1 无漂移。
- **小节通知存在但 app 未订阅。** `subscribeSequenceBarBoundary`（`runtime_session.mjs:3005-3009`；Creator 类型 `runtime_types.ts:392-396`）携带 `{runtime_frame, generation, pattern_id}`。
- **master tap 是唯一采集点。** Perform 录音与「主输出」重采样都采集 `performance_master_capture.mjs:235-260` 的 tap 节点（引擎 → tap → destination）。直连 `context.destination` 的声音不被采集。
- **没有节拍器。** 产品代码（`packages/`、`contracts/`、`apps/`）无任何 metronome/click 实现；设计 §6 盘点也未发现。
- **设备级持久化先例。** `last_project.ts`：IndexedDB `lmdj.creator.host` 的 `settings` store，串行写、失败降级；文件头注释记录为什么不用 localStorage（#1726）。localStorage 已实质退役。
- **要替换的旧 journey。** `creator_web_hardware_layout.spec.mjs:162-200`「keeps Project Truth across an unapplied draft and a reload」断言了「不点 Apply 不提交」的旧语义，直接调节后必须重写。
- **UI 测试现状。** `sequence_surface.test.tsx:104-108` 只测了「拖 Swing 推子 → 点 Apply Swing → onSettingsChange」；`sequence_state.test.ts` 覆盖 `failed` 置 `errorCode`。

## T1 — 直接 Tempo/Swing/步进/Tap 控件（Creator）

**Behaviour.**

- **通用手势滑杆。** 从 `parameter_slider.tsx` 抽出与手势机制逐行为等价、面向裸数值的滑杆组件（min/max/step、拖动预览、松手/键抬起/blur 提交一次、Escape/pointercancel 取消、disabled、音频挂起强制取消）；`parameter_slider.tsx` 变成保留现有 API 的薄包装，现有 Sample 测试不改语义地通过。抽取而不是复制，避免两份手势代码各自漂移（pitfall `parity-check-between-agreeing-copies`）。
- **TEMPO 卡。** 滑杆（40–240，step 1）+ −/+ 步进（±1，每次点击一次提交）+ TAP 按钮。TAP 逻辑是纯函数模块：≥2 次点击后按最近至多 4 个间隔的中位数换算，取整夹取到 40–240；间隔超过 2 秒重新起链；每次换算立即提交。
- **SWING 卡。** 滑杆（50–75，step 1）+ −/+ 步进。两个 Apply 按钮与 `<form>` 删除；读数显示本地预览值（手势中）或已提交值。
- **提交路径不变。** 提交仍走 `updateSequenceSettings`（串行化、revision 调和、失败进 `SequenceState.errorCode`）。手势期间不做任何 Host 写入——没有 sequence 设置的 preview 操作，也不新增。
- **录音中。** 三个控件沿用 `disabled`（busy 或 recording），卡片说明原因；Quantize 行为不变。
- **撤销交互不变。** 一次手势/步进/TAP = 一条历史记录；拖回原值不提交。

**Declared files.**

- `apps/creator-web/src/components/value_slider.tsx`（新）、`parameter_slider.tsx`（薄包装）、`sequence_touch_workspace.tsx`、`styles.css`。
- `apps/creator-web/src/runtime/tap_tempo.ts`（新）及其测试。
- 测试：`value_slider.test.tsx`、`tap_tempo.test.ts`、`sequence_surface.test.tsx`（重写 tempo/swing 腿）、`parameter_slider` 现有测试保持。
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`（重写 unapplied-draft 腿）、`creator_web_sequence.spec.mjs`（新腿）。

**Lowest-tier tests.**

- 滑杆：拖动只预览不提交；松手提交一次且仅在值变化时；Home/End/PageUp/PageDown/方向键抬起提交；Escape 与 pointercancel 取消并还原；blur 提交；disabled 无手势。
- 包装等价：`parameter_slider` 现有测试原样通过。
- TAP：单次点击不提交；两次得间隔 BPM；中位数与夹取；>2 秒重新起链。
- 组件：提交调用 `onSettingsChange` 一次且参数精确；录音中禁用；失败显示 errorCode 且读数回到已提交值。
- Packaged journey（每条腿一个 far-side 断言）：
  1. 拖动松手提交，`project.inspect` Truth 的 bpm 精确等于新值，revision +1；
  2. 步进与 TAP 各提交一次（TAP 用合成间隔）；
  3. 播放中提交，响应的 `activation_frame` 是下一小节边界（far-side：transport inspect + activation frame 比较）；
  4. Escape 取消：无提交、无 revision 变化、读数还原；
  5. 录音中拒绝：控件禁用，直接发 session 调用得 `HOST_STATE_INVALID`，Truth 不变；
  6. 失败：注入失败（session 包装层）后界面显示错误码，Truth 与读数不变；
  7. 重开：reload 后 Truth 与界面显示已提交值，未提交的预览消失。

**Gate defect caught.** 任何「预览被当成提交」「一次手势多个 revision」「取消/失败/重开后界面与 Truth 不一致」的回归。

## T2 — 会话音频时钟采样（Web Runtime Platform，纯 JS）

**Behaviour.**

- 会话新增 `sampleAudioClock()`：同步返回 `{contextTimeSeconds, callbackHeartbeat, engineEpochHeartbeat}`。`engineEpochHeartbeat` 在 `audio.activate` 解决后立即采样并随新纪元更新；暂停/中断恢复路径重取。JS 侧无新 C++。
- Creator 在 `main.tsx` 注入 `createAudioContext` 工厂，把 context 保留进新模块 `audio_clock.ts`；该模块按音频纪元缓存锚并换算 engineFrame ↔ context 秒。纪元切换（audio phase 离开/回到 running）时锚失效重取。
- 语义文档化：同一纪元内引擎帧与 context 帧 1:1；锚有 ≤ 约两个量子的常数误差。

**Declared files.**

- `packages/web-runtime-platform/web/runtime_session.mjs`、`runtime_types.d.ts`、`test/runtime_session.test.mjs`（与心跳夹具）。
- `apps/creator-web/src/main.tsx`、`src/runtime/audio_clock.ts`（新）、`src/runtime/runtime_types.ts`（会话类型）、`test/audio_clock.test.ts`。

**Lowest-tier tests.**

- 会话：激活后可采样；字段类型与单调性；激活前拒绝或明确空态（按会话现有惯例选一并钉死）。
- Creator 锚：同一纪元换算恒等；纪元切换重取；注入工厂被调用且 context 被保留。

**Gate defect caught.** 锚跨纪元复用或心跳/context 时间不配对的换算漂移。

## T3 — 节拍器（Creator）

**Behaviour.**

- **调度器（纯模块）。** 输入：锚（T2）、transport 状态（playing/recording、originFrame、当前 Pattern bars）、已提交 bpm、待生效的 `activation_frame`。输出：未来拍点 `{contextTime, beat, accent}` 序列。4/4：拍 = 四分音符，每小节首拍重音。BPM 或 Pattern 在播放中变化时，从新网格的 `activation_frame`/bar 边界起算，旧网格未发声的拍点作废。
- **发声。** Web Audio 提前调度（lookahead ≈120 ms，定时器只负责补充队列，不参与计时）：短 click（重音更高音高），直连 `context.destination`，**不经过 master tap**。transport 停止或开关关闭即停，已排队未发声的 click 取消。
- **开关。** Sequence 设置行的 METRONOME 按钮，`aria-pressed`；不受 transport 录制禁用影响；默认关。
- **持久化。** 设备级 IndexedDB `lmdj.creator.host`/`settings` 新 key `metronome.v1`（遵循 `last_project.ts` 的串行写与失败降级语义，新模块而不是改它）；启动时读回，切换时写入。
- **可观测缝。** 每个实际调度的 click 派发 `lmdj:metronome-click` CustomEvent（`{contextTime, beat, accent}`）。这是 journey 与诊断的 far-side 读数，在计划里明示而不是隐式测试钩子。
- **录音中。** 开关可用、click 可闻；PCM 证明它不进入 Perform 录音与重采样。

**Declared files.**

- `apps/creator-web/src/runtime/metronome_scheduler.ts`（纯）、`src/runtime/metronome_click.ts`（发声与队列）、`src/state/metronome_preference.ts`、`app.tsx`（transport/audio effect 接线）、`sequence_touch_workspace.tsx`、`styles.css`。
- 测试：`metronome_scheduler.test.ts`、`metronome_click.test.ts`（fake AudioContext）、`metronome_preference.test.ts`、`sequence_surface.test.tsx`（开关腿）。
- `tests/platform/web/creator/creator_web_metronome.spec.mjs`（新）；`creator_web_perform.spec.mjs` 复用其 PCM helper。

**Lowest-tier tests.**

- 调度器：拍点间隔精确（60/bpm）；重音图案；originFrame 映射；bpm 变化在 activation_frame 切网格；停止清空队列；bars 变化。
- 发声：click 路由直连 destination 且不触达 tap；toggle-off 取消未发声队列。
- 偏好：写入可读回；损坏值降级为默认关。
- Packaged journey（每条腿一个 far-side 断言）：
  1. 正常：播放中开节拍器，`lmdj:metronome-click` 事件的间隔 = 60/bpm（容差内）、首拍重音；停止播放即无新事件；
  2. 录音中：节拍器照常发声（事件仍在），且 Record-off 后 Pattern 事件不受任何影响；
  3. 不进录制：节拍器开、无任何 Pad 触发时录 Perform，导出的 WAV 是全数字静音；同 session witness sample 腿证明采集链本身有信号（对照）；
  4. 取消：播放中关掉开关，事件停止且已排队 click 被 cancel；
  5. 重开：reload 后开关状态恢复（IndexedDB far-side），默认工程为关。

**Gate defect caught.** click 被录进作品、拍点 cadence 错、开关/停止后仍发声、偏好丢失。

## T4 — 门户与验收台账

- 更新 `/hosts/creator-web/`（直接调节、TAP、节拍器与生效边界；删除 Apply 描述）与 `/core/modules/web-runtime-platform/`（音频时钟采样）；`/product/workflows/` 把「已确认，尚未实现」改为交付状态。
- 新增 `docs/quality/2026-10-02-creator-tempo-metronome-acceptance.md`，沿用 sample-playback-parity 台账格式：参数真值表、五路径自动化表（normal/refused/failed/cancelled/reopened，每行 far-side 断言与归属）、信号级事实表、聆听矩阵（真人聆听行全部记 not run，自动化不替代）、未覆盖项。
- 同步设计 §6 的现状列（内部版文档的当前状态重审属于 umbrella 验收，本 Task 只改本行）。

**Gate defect caught.** 门户或台账描述与交付行为不一致。

## Verification

- 每个 Task 先跑其 lowest-tier 测试，再跑相关套件：Creator 的 Vitest 与 `tsc --noEmit`，Web Runtime Platform 的 `node --test`，相关 journey 经 `scripts/creator-web.sh proof` 的浏览器门。
- T1/T3 改动门户页时跑 `scripts/docs-site.sh check`。
- 变更选中的每个 batch-only lane 在已提交 head 上本地跑过，`pass key=` 进 Pull Request。
- 每个 Pull Request 跑 `scripts/local-ci.sh --list --json` 分类与 PR body lint。
- revert/mutation 证明都在重建产物上做。
- 不放宽任何 timeout、coverage floor、已有 lane 或 journey 腿。

自动化不能推断的：真人聆听（click 与 Pattern 的对齐听感、click 音色）、iPad/触屏实机拖动手感、真实 Safari。这些在台账里保持独立的 not-run 行。

## Version Management

Version impact: none in this plan Pull Request（决策与计划文档，外加 `/product/workflows/` 的状态记录）。

实施 Task 在下一次协调版本切点欠 MINOR：

- T1、T3：`creator-web`；
- T2：`web-runtime-platform`（纯 JS 会话 API）。

无 Contract SemVer 变化（`lmdj.project.v5` 已携带 bpm/swing；节拍器不进 Truth）；无 Product Build 或 Assembly 变化。

## Documentation Impact

Documentation impact: required for this plan Pull Request，`/product/workflows/`。沿用 #1695/#1753 先例，把已确认行为记录在那里，与当前未实现状态分开。各实施 Task 自己的声明：

- T1：required，`/hosts/creator-web/`（或随 T4 合并声明，见下）；
- T2：required，`/core/modules/web-runtime-platform/`；
- T3+T4 同 PR：required，`/hosts/creator-web/`、`/core/modules/web-runtime-platform/`、`/product/workflows/`。

T1 的 Pull Request 若不带门户页，则在该 PR 声明 required 并由 T4 在同一工作流内补齐页面——不允许最终以 none 收尾。Host → Facade → Store/Cooker 依赖拓扑不变。

## Pitfall Impact

Pitfall impact: 实施时应用以下既有条目；预期不产生新条目，每个 Task 发货前按 `area:creator`、`area:web-host` 复查开放条目。

- `parity-check-between-agreeing-copies`：手势机制抽取共享，不复制；
- `local-audio-proof-inherits-output-device`：本地音频 lane 在内建输出上跑，留意 Bluetooth；
- `acceptance-journey-truncation`：五路径每条腿都有 far-side 断言，未走的腿记为显式缺口；
- `synthetic-event-omits-platform-side-effects`：合成 TAP/手势事件时枚举真实事件的平台副作用，未复现的记为缺口；
- `untracked-file-passes-ownership-gate`：新增文件先入 `scope_policy.json` 覆盖再提交。
