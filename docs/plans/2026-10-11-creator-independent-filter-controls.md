# C1 — Creator 独立滤波参数组与旋钮/触摸 consumer

状态：实施 Task 计划。本文件是
[producer/consumer 计划](2026-10-11-performance-live-control-producers.md)
C1 节的实施计划；C1 节是边界权威，本文件不扩大其 scope。

## Outcome and authority

Creator Perform 消费 W1 落地的真实 typed producer：主组 ENC1 Cutoff /
ENC2 Delay / ENC3 Reverb，FILTER 组 ENC1 type（LP/HP/BP）/ ENC2 同 Cutoff /
ENC3 Resonance；七个既有 FX 全部改走 typed generation route；录制经
headered begin 消费 Core mapping；读回只认 Core 状态。

**Authority:**

- [C1 节](2026-10-11-performance-live-control-producers.md)：declared files
  与逐条 oracle。
- [D04 决定](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)：
  LP/HP/BP + Cutoff 20 Hz–20 kHz 对数 + Resonance 0–100%；初始
  OFF/LP/20 kHz/0%；进 FILTER 组不改声；停转/切组保持；主组与 FILTER 组
  共用 Cutoff；ENC4/MASTER 复用 #2000 同一监听。
- [D0 编码](../prd/decisions/2026-10-11-performance-live-control-encoding.md)
  的 wire/绑定/双 ready 规则。
- W1（`f11746f8`）落地的 SDK：`applyPerformanceLiveControl` /
  `queryPerformanceLiveStatus` / headered `beginPerformanceRecording` /
  有界 FIFO / capture started ACK。

## Facts this Task relies on

Checked on `f11746f8`（本 worktree base，含 W1 merge head）。

- `CreatorPerformanceRuntimeSession` 继承 `PerformanceRuntimeSession`，
  W1 typed 方法直接可用。
- 现状：ENC 主组为 [filter(legacy 0–1000), delay, reverb]，MORE 组为
  [crush, stutter, gate]；`turnFx` 线性 ±10/±1；record() 在 begin 后把
  已开 gesture 以 synthetic fx_engage 补写进 Journal；FX 状态是 Host 本地
  镜像（`state.fx`）。
- W1 已知点：`performance.live.status` 的 `reset_pending` 恒 false
  （reset 归 replay sink）——UI 不依赖它。
- 两个 hosts portal 路由不嵌图；本 Task declared set 无图文件。

## Design

### perform_state.ts（typed controller）

- `PerformState` 新增 `filter: FilterControlState`（type/cutoffHz/
  resonanceMilli/engaged/frozen + provenance: core/pending/unavailable）与
  `liveControl: {available, epoch}`；初值来自 `queryPerformanceLiveStatus`
  的真实读回，不可用明确显示 unavailable，不从旧 percentage 反推 Hz。
- 全部八 FX 的 engage/move/release 改走 `applyPerformanceLiveControl` 的
  fx_parameter/fx_release typed route；runtime generation 来自 Core
  receipt；stale/错 generation 由 Core 拒绝（far-side），Host 不伪造。
- Cutoff 对数映射：position 0..1000 ↔ 20·1000^(p/1000) Hz；粗调 ±10
  position/detent，SHIFT 细调 ±1；端点精确 20/20000。
- 首次实际参数变化 engage（Core 派生完整 tuple），此后 move；停转/切组/
  rest 不 release；touch pointer-up/cancel/blur 保持既有 release 语义；
  HOLD 下 release 由 Core 冻结。
- headered record()：`queryPerformanceLiveStatus` 取 epoch →
  `beginPerformanceRecording({controlEpoch})`（fence 轮询在 SDK 内完成）
  → 消费 `fxBindings` mapping 注册 logical/runtime 双绑定并把
  mapping 覆盖的 FX 收养为已开 gesture，**不再 synthetic engage 补起点**；
  随后显式 `startPerformanceMasterCapture(queue)`，其 start promise 本身
  以真实 started ACK 为门（D0 R1 同一 fence → capture 顺序、同一双 ready
  事实）。实施修订：Host 在 capture start 前保留 begin receipt，确保
  capture 失败后仍有 committedRevision 可补偿；stop 持有实际 capture
  handle。Host 自行组合两个门，首 Pad 由
  controller 相位（recording 才放 recordPerformanceEvent）gate 在 ACK
  之后。录制中的 move/release 携带 binding 对。status 不可用
  （headless/旧 Core）→ legacy begin + 旧 seed 分支原样。
- FILTER 组进入是纯 UI 状态，零 producer 调用。
- 实施修订（兼容）：主组首推子在 typed 模式下保留 `Filter` 可访问名
  （`creator_web_touch_fit.spec.mjs` 等既有 journey 按该名定位，该文件
  不在 declared set）；typed 变化体现在读数（Hz）与行为，面板内滑杆
  名为 Cutoff/Resonance。

### Components

- `fx_slider_bank.tsx`：主组首 fader 变为 Cutoff（Hz 读回，对数滑杆）；
  FILTER 按钮切换 FILTER 面板（type 三段 LP/HP/BP + Cutoff + Resonance）；
  `onGroupChange` 升级为组枚举；既有 touch release/blur/cancel 语义不动；
  MASTER/ENC4 复用同一 monitorVolume。
- `perform_surface.tsx`：encoder 组枚举 main/more/filter；FILTER 组 ENC1
  循环 type、ENC2 cutoff、ENC3 resonance；组切换/rest 不 release。
- `styles.css`：FILTER 面板样式沿用既有 perform-* 类命名。

### 不做

不新增 save/Undo/400ms 工程提交；不改 `playback.muted`；不新增第二级
master gain；旧 legacy 录音重放路径不动。

## Declared files（完整边界，10 个）

- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/perform_surface.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-11-creator-independent-filter-controls.md`（new，本文件）

## Lowest-tier verification / defect oracles

- component/controller：主组/FILTER 组映射；OFF LP/20kHz/0% 初值来自
  Core 读回；对数端点与 SHIFT 细调；rest/组切换保持；touch 生命周期不变。
- typed controller 初始 state 来自 Core mapping 实际 read/ACK；七 FX 起点
  engaged/frozen、首 move/release、begin 异步积压、late generation/epoch
  far-side 断言；new profile 无 fake engage；legacy seed 旧分支保留；
  三个独立参数各一次录制。
- failure oracle：Core-ready 而 capture 未 started 时首 Pad gated；ACK 后
  FIFO 恢复；积压超限明确失败、matching release/cleanup 完成。
- `creator_web_perform.spec.mjs` 的 packaged journey 写全
  （Control→PCM、HOLD/离页、Record/Stop/Save/reopen/Replay 每侧），
  takeover 后在最终 committed head 运行完整 packaged proof。
- `npx tsc --noEmit`（apps/creator-web）、ownership/scope、
  `scripts/docs-site.sh check`、`tests/build/ci_change_scope_test.py`。

## Version Management

Version impact: Creator compatible new public interaction MINOR debt；无
Project authoring 参数、无 400ms save 语义变化、无第二 master gain。
无 Product Build allocation。

## Documentation impact

Documentation impact: required——`/hosts/creator-web/` 与
`/hosts/creator-interactions/`；两路由不嵌图，无图源更新。

## Pitfall Impact

本 Task 的读回、epoch、bounded FIFO 与 gesture lifetime 缺陷均可从产品
逻辑推导，并由组件/浏览器回归直接表达；按 issue-done 不新增流程 pitfall。
rest/组切换不 release 是 D04 批准语义，不得退回旧 release-on-rest。

## 2026-10-13 takeover amendment

Kimi stopped after rebase head `22f178f34a1f6f32f6f49ad108ca9dd500bd1a5d`
and a full packaged proof with six Chromium failures (92 passes, one skip).
Codex retained that failure and the four uncommitted legacy-route pinning files.
Refreshed integration base: `613e23c26bb0ae54dccd75003b8858ac484b0faf`.
C1 remains outstanding on this base; W1 and silent Pad navigation are delivered,
not repeated. Project/Sound Set/rail changes remain intact after rebase.

- A legacy Filter gesture opened before the first status answer must keep its
  original route and controls until release. Retain the component regression.
- Add `creator_web_hardware_layout.spec.mjs` to the declared set to update the
  held-control navigation journey to typed Cutoff: wait for Core readiness,
  turn down one logarithmic detent, assert position 990 across all Pad steps,
  and inspect the actual typed producer. This is an existing journey's semantic
  update, not a navigation redesign.
- Core status incorrectly counts the legacy container during headered recording.
  Separate prerequisite #2124 fixes that source defect. Keep the browser
  gesture-count assertions; do not replace them with weaker presence checks.
- Replay neutral release retains the independent Filter tuple by design
  (`MasterFxChain::derive_filter_state`); assert the retained value plus OFF,
  not an invented reset to 20 kHz.
- Scope the 20.0 kHz locator to the touch workspace; the overview EQ displays
  the same text and is not the control under test.

The original committed-head full packaged proof remains required after focused
fix validation; physical audio/hearing acceptance remains unverified.

Takeover source corrections preserve the original C1 acceptance boundary:

- An ACK no longer promotes a Host tuple to Core provenance. Bounded status
  polling reads the applied tuple; stale reads and old-epoch receipts cannot
  overwrite a newer control. Type-only gestures also release on page exit.
- One shared bounded FIFO resolves Core generations / begin mappings at dequeue
  time. It admits at most two ordinary controls, explicitly rejects overflow,
  and reserves matching gesture releases. Inputs submitted during begin wait
  for both the Core mapping and the real capture-start ACK; stop drains its
  admitted interval before later controls resume on the sessionless route.
- A mapped legacy scalar Filter stays on `fx_move/fx_release`; an independent
  Filter uses its separate parameter binding. A pinned early legacy gesture
  also blocks the alternate FILTER rotary controls until release.
- The consumer is temporarily stacked on prerequisite commit
  `5ba8b2a3963d7e27ccc6a53783ac63dfe82f31da` (PR #2126). This is local source
  composition, not evidence that the prerequisite has merged.

### Precommit verification

- Inherited C1 source rebuilt by Vitest: all seven new regression oracles FAIL
  (ACK versus applied tuple, stale status, stale epoch, Type-only cleanup,
  overflow with release, begin-time FIFO mapping, and legacy Filter mapping).
  Source restored with fresh mtime; the complete controller suite PASS 97/97.
- Creator TypeScript: PASS. Portal `scripts/docs-site.sh check`: PASS.
- Full committed-head packaged proof remains outstanding at this checkpoint;
  earlier failed proof evidence is retained.
- Wider Creator UI run: 1459/1464 PASS, five failures retained. The one C1
  legacy call-order regression is fixed (the targeted App/Perform selection
  now PASS 30/30); four retired Open-local queries reproduce 4/22 on identical
  main Creator source and are tracked independently as #2129. C1's full proof
  requires that lifecycle-test prerequisite; the failed broad run is not green.

## 2026-10-13 second verification pass

Refreshed integration base: `edb05dbb14c0f6ed28abeeeceab742fc3e282080`.
Prerequisites are now merged: #2126 (`692d2ac1`, headered gesture counts),
#2130 (`88fd1616`, current Project action lifecycle tests), and #2134
(`edb05dbb`, observed SDK recording sequence after Pattern ACK). Current main
also includes #2123's renamed Project navigation assertion; do not repeat it.

The first takeover full proof at `110e43bc0b3be559488d644441befa95097120fe`
returned exit 1. Both clean distributions were reproducible and all 1464 UI
cases passed. Main Chromium: 93 PASS / 6 FAIL / 1 skip; subsequent browser
groups completed. Original logs and failure traces remain retained.

The six failures are addressed without deleting journey legs or changing
budgets: guard all control readbacks (including recording status) against
newer HOLD/FX input; retain Core's zero neutral scalar FX values in assertions;
integrate the observed-sequence fix and existing Project selector fix; assert
Core release/HOLD admission before the next ordinary typed input. The real
transport observer kept original requests and responses and proved the SDK
cursor defect separately from the intended bounded-window refusal.

Additional component RED/GREEN proofs cover all seven scalar FX preserving
Core generations when move receipts return no new binding; 64 Pad reservations
retained until release completion; explicit cancellation of not-yet-admitted
ordinary controls on Stop while matching releases complete; and old recording
status not overwriting newer HOLD. Refused ordinary input does not fabricate
local gesture ownership. Seven FX are also checked at engaged and frozen
recording start, including the first bound move/engage and matching release.
The complete Perform component selection now passes 122/122; TypeScript passes.
The next committed-head packaged proof remains required before shipping C1.

Second prepackage checks: all 75 Creator UI files / 1504 tests PASS; the final
Perform touch-provenance correction then passed TypeScript and 122/122 targeted
tests. `scripts/docs-site.sh check` PASS (50 routes and internal links).
These checks prepare a clean build checkpoint; packaged acceptance is still
pending and no PR/merge is inferred from them.

Focused packaged journeys at source `353dce3c` initially returned 4 PASS /
2 FAIL. The real request observer proved the missing cutoff move had been
refused by the bounded input window while the previous Pad release was still
settling; the captured second strike was therefore dry. The two journeys now
assert Pad release, Filter applied provenance/value and HOLD admission before
the next dependent control. Both pass against that same source distribution;
all PCM thresholds, time budgets and journey legs remain unchanged. These
assertions add far-side evidence, not extra queue capacity or retries. The
final clean-head complete proof is still the shipping prerequisite.

Full packaged proof at `acf8e919b41863b85aa1f08a56fc63b7fc9b7cb8`
returned exit 0: reproducible clean distributions, 1504 UI cases and all eight
browser groups (141 passes, 11 configured capability/project skips).
Independent current-head review had two findings; seven external diagnostic
probes disproved stuck navigation after refused touch and false Core provenance
during the pending release interval. Both received recorded dispositions.

The premerge refresh then found SDK #2138 at
`7d27e33d209d4b0644339085d27c038d41e2393a`. It adds an optional owned capture
handle to capture-sink begin and keeps the headered no-sink path exact. C1
retains the latter path so its existing compensation can observe the committed
begin revision even when the subsequent capture start fails. The previous
claim that the SDK cannot return a handle is removed. This is a premise
refresh, not a new capture lifecycle: the same two readiness gates and held
input semantics remain. Rebased integration verification is required before
shipping this updated head; the earlier complete receipt remains historical.
