# Creator Desktop Final：后续功能、缺陷修复与验收收尾

## Outcome and authority

逐项完成 Creator Desktop Final 后续范围：修复已确认缺陷，确认尚未决定的产品
行为并实现，验收四页交互，结算版本，再清理有完整保留证明的本地资源。
用户于 2026-10-09 授权执行本计划的 Goal，包括 Task 的 commit、push、PR、
当前 head 评审和 squash merge，以及证明安全后的相关本地工作区/分支清理。
本计划不授权 tag、Release、部署、Channel promotion、远端分支或云主机资源清理。

[原计划](2026-10-06-creator-desktop-final-ui.md) T1–T11（含 T1b、T5a）已完成。
用户明确确认以该计划为准完成原目标；本 Goal 不重做原任务。历史 Claude
会话的额度耗尽和 Goal 结束检查不构成产品未交付的证据。

产品决定优先于 Figma。Desktop Final 是桌面布局/视觉依据，不能凭图中的控件
推导运行时能力或持久化语义。Mobile/iPad 设计扩展不在本计划中；现有布局的
真实 Safari/iPad 输入与设备验收仍须保留适用证据。

## Facts and premise dispositions

初始调查绑定 `origin/main` = `0d7c178b2bc4d277ff34424bb5f42c78aee7ef9d`。
在每个 Task 开始、提交前和最终合并检查时刷新 main 及其相关继任交付。

| 前提 | 当前证据与处置 |
| --- | --- |
| 原 UI Task 未交付 | 已反证：相关实现 PR 全部 merged，最后 #1900 → `1f20e8f63`、#1901 → `0d7c178b2`；不重复实现。 |
| #1905 连续提交刷新丢失 | 已交付：#1907 → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`，Issue closed。旧代码从滞后 render ref 取刷新 revision，现由 grid/structure/colour 成功路径传入已提交 revision；回归测试检查最终画面，不重复修复。 |
| #1868 导入偶发停在 0 B | Issue open；尚未建立原因。R2 是条件调查，只有验收受阻时才启用，不把一次重跑通过当作修复。 |
| #1873 测试问题仍未修 | 已反证：Issue closed，相关修复已合并；本 Goal 不重做。 |
| #1822 其余控件映射已有决定 | 部分批准：I1a 的 Sequence 导航已交付；owner 进一步批准 I1b/I1c 的逐页 ENC1–3 与固定 ENC4 监听音量、SHIFT 细调。其他页方向键仍待决；Issue open。 |
| 400 ms 规则已正式确认 | 本计划初始调查时尚未确认；owner 现已批准立即预览、400 ms 合并 authoring 保存及明确的取消边界，见 I1b/I1c。 |
| D01/D03/D04 图示能力均可直接接线 | 部分反证：下文 C0 核实了可复用的复制与 Sample 编辑；MASTER、独立滤波参数、live Mute/Solo 及电平投影仍需 producer 工作。D01 自动保存/复制语义已有决定，不重新设计。 |
| 合并/自动化可代替人工验收 | 不成立。原验收台账保留真实输入、听感、辅助技术和生命周期缺口；A1/A2 分开记录。 |

开放 PR #1904 是 audition golden 计划；开始涉及 audition 的 Task 时重新核对其
交付与文件范围。原 Claude 主会话没有进行中的实现任务；监视器不取得新 Task
工作区所有权。新 Task 使用自己的隔离工作区，不共享旧构建目录。

## Progress and order

| ID | 工作 | 当前状态 | 依赖/完成条件 |
| --- | --- | --- | --- |
| P0 | 本后续计划 | 已合并 | #1906 → `cd5fbf9290fba820139bfdc9d41b9166a7fe333b`；独立接管评审及修订已验证。 |
| R1 | #1905 连续 authoring 提交刷新 | 已合并 | #1907 → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`；red/green、完整 Creator lane、Portal 与当前头独立评审通过；不代表 A2 人工验收。 |
| C0 | D2–D5 当前能力及决定边界调查 | 调查已记录 | 绑定下文 inspected revision；只更新本计划，不批准产品提案或实现 I Task。 |
| R2 | #1868 导入稳定性条件调查 | 待调查（条件项） | 若阻碍本计划验收，保留 trace 并定位请求/读取/提交边界；证实原因后独立修复。 |
| D1 | #1822 统一原则及逐页映射 | 全页旋钮已确认；其余方向键待决 | 执行 I1b/I1c；固定 ENC4 监听音量，ENC1–3 随页/组变化，SHIFT 细调。 |
| D2 | 400 ms 连续旋钮提交 | 已确认；待完成实现验收 | Sample/BPM 立即预览、停转 400 ms 合并一次保存/Undo，脱离目标或取消时丢弃未提交预览；Perform 保持效果并按 HOLD 离页释放。 |
| D3 | D01 Save / Save As / 未保存提示 | 已确认 DUPLICATE；现有入口符合 | owner 于 2026-10-10 选择 DUPLICATE；现有按钮复制新身份并打开副本，继续自动保存；整体 A1/A2 验收仍待完成。 |
| D4 | D03 audition/trim/browse/assign 与细调 | 能力已调查；待 owner 决策 | 区分已实现的导入/替换/trim 与新 Assign、参数细调入口；明确目标、单位/步长、Undo/Redo、取消/失败。 |
| D5 | D04 MASTER/滤波类型/Mute/Solo/电平 | 能力已调查；待 owner 决策 | 明确作用域、Truth 与 live 状态归属、真实投影及 DSP 能力；producer 与 consumer 分 Task。 |
| I1–I5 | D1–D5 的对应实现 | I1b 已合并；I1c 适配中；其他范围等决定 | 每项批准后追加精确 Task，再实施和合并；不得以此编号捆成一个大 PR。 |
| A1 | 四页自动化与视觉核对 | 待验收 | I1–I5 完成或 owner 明确取消相应范围；保留每个 journey 的 far-side assertion。 |
| A2 | 真实设备及人工验收 | 待验收 | 具体设备、来源、身份、步骤和结果；缺失 leg 保持未验收。 |
| V1 | 协调版本结算与 snapshot | 待实施 | 读取最终 manifests 和版本政策；独立 version Task、Portal snapshot 及合并后 provenance。 |
| C1 | 本地工作区/分支收尾 | 待调查 | 完整改动保留、干净（含 untracked）、未锁定且无人使用；逐个安全移除。 |

执行顺序为 P0 → R1，之后依次完成 D1/I1、D2/I2、D3/I3、D4/I4、D5/I5，
再 A1/A2、V1、C1；人工等待时可推进不依赖该结果的调查或实施。R2 仅在
适用条件出现时加入。每个产品问题一次给出少量选项、建议及影响，收到明确
回答后记录 decision。决定不做可以完成该范围的处置；暂缓仍是未完成，除非
owner 明确同意移出本 Goal。

2026-10-09 owner 已确认统一原则：旋钮 1/2 管视图位置，旋钮 3/4 管当前页
主要数值，方向键做导航，SHIFT 保留撤销/重做并支持粗调。此回答只确认
原则，具体页的参数、当前 Pad 与步长尚未批准；不以它推导完整映射。

## I1a — Sequence view and current-Pad navigation (#1822)

Owner 于 2026-10-09 回复「采用」，批准：ENC1 每格横向滚动一小节；↑/↓
按 A01–D16 选择当前 Pad，跨 Bank 同步 Bank 与上屏，在首尾停止；只高亮，
不发声、不改变音符选择或 Project Truth。其余页映射与粗调步长仍待决定。

**Premise disposition before implementation:** Task base 与 freshly fetched
`origin/main` 均为 `d4eb51161e8b97d33f2cb8cc7f4184696576caef`。Live #1822
open、无评论；当前 `PhysicalControls` 禁用 ENC1/↑/↓，App 只有 ENC2–4 与
左右 Pattern 绑定，Grid 仅有原生滚动，故本次批准的连接仍缺失。原 T6 已交付
ENC2–4/左右键，不重做。继任 #1907 只修复 authoring refresh，#1908 只更新
能力调查；唯一开放 PR #1904 是不重叠的 audition 计划。App 现有 Bank effect
清空音符选择；↑/↓ 必须绕开该清空，保留显式 Bank 键原有的清空语义。

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/sequence_grid.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/sequence_grid_edit.test.tsx`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/prd/decisions/2026-10-09-sequence-view-and-pad-navigation.md`
- 本计划。

**Lowest-tier verification and journey:** App component red/green 验证每格实际
小节宽度及横向两端；当前 Pad 首尾、跨 Bank 与上屏可见性；跨 Bank 后返回
仍保留所选音符，Truth/revision/trigger 调用保持原值；显式 Bank 键仍清空选择。
Packaged Chromium 从 EDIT 的真实滚动容器读取几何，验证滚动与 overview frame；
从音符框选经过 Pad 跨 Bank、边界及返回，逐段检查高亮、Bank、音符选择、
完整 Truth 与 history 不变；SETUP/离页禁用 ENC1，不积存隐藏的滚动命令。
完整 Creator lane 保留既有 ENC2–4、Pattern、SHIFT history 与 accessibility
到首个 Pad 的 journey。Portal check；新增文件 stage 后 scope Python suite；
clean committed head 的所有实际 batch-only lanes 与当前 head 独立评审。
真实 Safari/iPad/物理旋钮及听感未执行仍归 A2，不以自动化替代。

**Precommit evidence:** 再次 fetch main 后仍为上述 `d4eb51161`；继任记录与
源行为无变化。新增控件在未实现树上 2 red；CSS scale 0.5 的独立回归先显示
192 px 而非 384 px，再由 layout-pixel 修复通过。最终 App component 14/14、
TypeScript、Portal check（50 routes）通过。完整 Creator/batch lane、当前 head
独立评审与合并状态由本 Task PR 的验证记录承载；本记录不预先宣称这些已通过。

**Independent review follow-up:** #1909 初始头 `108c3d9b` 的独立评审在真实
Chromium 复现禁用旋钮仍累计 wheel 余量。已补 red（SETUP 半格 + EDIT 半格
误滚一小节）并修复：禁用时拒绝 wheel/pointer 起点，可用状态/参数切换清空
wheel/drag；同时保留启用后两次半格组成整格的正常行为。Packaged journey
使用原生 wheel 并等待事件送达后再断言，不能以 disabled 属性代替该边界。
初始完整 lane 为修改而主动中止，exit 143，保持未通过；新头重新验证。

**Packaged fixture pacing:** 第二次 lane 的新场景在首个音符前失败。保留的
trace 显示 resize 已写 Truth，但 EDIT 刚挂载时仍是 1-bar 投影且
`data-editing-disabled=true`；测试当时量取旧几何并点击被正确锁定的网格。
新场景改为先等待上屏实际呈现 4 bars 且投影允许编辑，再量取/点击；原有完整
Truth、history、trigger、选择保留与边界断言均保留，不增加 sleep 或超时。
此为测试前置条件修正，产品实现未改变；失败 trace 留存后，新场景使用
`eaaf6759` 已打包产品单独完整通过（1 test，15.3 s）。该诊断不替代最终
committed head 的完整 Creator lane；最终头仍重新执行该 lane。

**Version Management:** Creator 新交互积累 MINOR debt，留待本计划 V1 协调
结算；本 Task 不分配 Product Build。**Documentation impact: required** —
`/hosts/creator-web/`、`/platform/input/`，同时记录新的产品决定。

## I1b — Web monitoring output producer

Owner 已批准 [三个页面旋钮与固定监听音量](../prd/decisions/2026-10-09-contextual-encoders-and-monitor-volume.md)，
并分别确认 400 ms 取消边界、本设备音量记忆和 Perform 效果保持。
该决定替代 D1 原则中上排统一视图/SHIFT 粗调；D2 的产品语义已确认，
实现与验收尚未完成。其他页方向键、D3/D4/D5 其余问题不从此推导。

**Premise dispositions before implementation:** fresh main 与 Task base 为
`502932e345b621abc5533431e61adf0d0253a189`。#1909 已交付 Sequence 导航，
不重做；#1822 open，唯一开放 PR #1904 为 audition 计划。检查 Runtime Session
的实际 bootstrap、capture factory 与 processor-failure 分支：正常路径直达
AudioContext destination，失败恢复调用固定直连 destination 的 bridge；同一
注册表中 `registerAudioNode`/`startAudioWorklet` 已接入 tap，为正向控制。
Session 完整公开返回对象无监听音量/目标接口；Creator metronome 同样直达
destination。故监听 gain producer 仍缺失，须同步保持恢复路径和 capture 边界。

**Behaviour:** Session 提供 0–100 的监听音量（默认 100）、读取值与 Host
监听目标。可在 activation 前设置，AudioContext 创建时先应用，再连接任何
发声路径；运行中短 ramp 平滑调节。master capture 位于 gain 前，tap 故障
恢复也进入同一 gain；跨 context/无效目的地拒绝，重复恢复不叠加连接。
关闭后拒绝修改并断开 gain。设备记忆、metronome 路由与旋钮 UI 属于 I1c。

**Declared files:**

- `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/web-runtime-pre.js`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`
- `docs/prd/decisions/2026-10-09-contextual-encoders-and-monitor-volume.md`
- 本计划。

**Lowest-tier tests and journeys:** Node Session tests bind pre-activation volume,
normal graph, tap initialization/processor failure, repeat connections, invalid
input and terminal cleanup to actual producer calls; master-tap controller tests
assert gain is downstream and batch bytes unchanged. Real rebuilt AudioWorklet
conformance exercises alternate same-context monitor destination, zero/half/full
output energy, rejection of cross-context nodes, idempotent fallback and audible
continuation. Existing activation/recovery/capture journeys remain intact. Run
Portal check and exact clean-head selected batch-only lanes under issue-done;
record platform-not-runnable and unperformed physical hearing honestly.

**Version Management:** additive Web Session capability and Web Audio routing
accumulate Web Platform/Audio Runtime MINOR debt for V1; no Product Build or
persisted Contract change. **Documentation impact: required** — `/platform/web-runtime/`,
`/core/modules/web-runtime-platform/`; update the source diagram in the same Task.

**Source-shell fixture correction:** the full Web Host proof reaches the existing
source-shell activation journey, whose injected AudioContext predates monitoring
and has no `createGain`, destination or node registration. This fails activation
at the newly required browser capability, before any lifecycle assertion. Keep
the failed trace and update only that fake's Web Audio surface; preserve every
activation, interruption, recovery and cleanup leg and the existing deadlines.

## I1c — Creator contextual encoders (dependent on I1b)

Deliver the approved per-page table, touch parameter groups and visible readback,
SHIFT fine steps, device-local ENC4 memory, and metronome monitoring routing.
Sample/BPM follow the approved 400 ms cancel/commit lifecycle; Perform uses owned
live gestures retained through rest and group switches and released on page exit
under HOLD. Consumer development base is `deebae1c3c99de1081e71647689bfebff7b83afc`, the
implemented I1b producer, while fresh main remains
`502932e345b621abc5533431e61adf0d0253a189`. I1b is independently source-reviewed
but not merged yet: this dependent branch must be based on its actual squash
before shipping. Inspection confirms the existing Sample preview/update and
Perform live/journal operations are reusable; current bindings only serve
Sequence, ENC4 is Swing, Project selection and FX groups are touch-only, and
metronome bypasses capture directly to destination. This Task adds consumers;
it does not reimplement those producer operations or the merged I1a navigation.

**Steps and state boundaries:** trim Start/End use 10 ms per detent (SHIFT one
source frame), Pitch 1 st (SHIFT 0.1 st), gain 1 dB (SHIFT 0.1 dB), Pan/Tone
10 units (SHIFT 1), FX 10/1000 (SHIFT 1/1000). BPM remains integer 1 BPM;
view/list navigation retains one bar/row/item. ENC4 is always one percentage
point. Bounds reuse Core-valid playback/loop limits; no new units or DSP.
Sample turns across parameters of the same Pad merge into one 400 ms update;
no-change turns save nothing. Touch slider commit semantics remain intact.
Target loss, System, Esc, history and recording/mutation locks cancel rotary
work before it can submit; sent authoring results retain normal acknowledgement
and refresh semantics. The current BPM consumer previews readback then uses existing publication on
save; this is an unfinished acceptance item until the audible preview producer
and consumer in PR #1929 are implemented. Perform rotary ownership persists through group/rest, shares the existing
FX gesture when touch and rotary target the same FX, and releases before leave
through existing HOLD semantics. Host preference restore precedes enabling
ENC4; later turns win, storage refusal cannot stop monitoring. Metronome enters
monitor downstream of capture. No alternate ENC4 or undeclared direction keys.

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/runtime/metronome_click.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/state/encoder_input.ts`
- `apps/creator-web/src/state/sample_encoder.ts` (new)
- `apps/creator-web/src/state/monitor_volume_preference.ts` (new)
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/components/authoring_history.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/hardware_console.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/sequence_grid_edit.test.tsx`
- `apps/creator-web/test/sample_encoder.test.ts` (new)
- `apps/creator-web/test/monitor_volume_preference.test.ts` (new)
- `apps/creator-web/test/metronome_click.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/authoring_history.test.tsx`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/prd/questions/hardware-control-mapping.md`
- 本计划。

**Lowest-tier verification:** typed helper tests pin per-parameter bounds,
fine steps, loop fitting, one merged save, no-change/cancel and stale target
refusal; IndexedDB tests pin default/corruption, serialized writes and bounded
restore. Component/controller tests exercise real registration, Project
selection-only/scroll, Sample cancel boundaries, all six FX/group persistence,
HOLD-aware leave, SHIFT events, monitor independence and history cancellation.
Metronome tests assert its actual downstream destination. Packaged browser
journeys use the real current bindings, explicit OPEN, Sample far-side Truth/
Undo and cancellation, and monitor preference reload; preserve all existing
journey legs including SETUP Swing. Check readback/8-row fit at console sizes.
Recording also covers rotary-to-touch takeover of one FX and verifies Core's
open-FX count returns to zero before the stopped recording is saved/reopened.
Run TypeScript, ownership on the staged new files, Portal and the exact clean
head selected batch lanes; independent full-diff/current-head review remains
required before squash. Physical knobs/hearing and Safari/iPad remain A2.

**Precommit refresh (2026-10-09):** fresh `origin/main` remains
`502932e345b621abc5533431e61adf0d0253a189`; no successor delivered the remaining
I1c bindings. New staged-file ownership tests pass (77), TypeScript passes,
and the independent new App/Perform group passes (15). The reverse FX handoff
regression fails before the fix at the second engagement, then passes with
one matching gesture; the prior grouped Project-selection timing failure is
retained and corrected by waiting for its actual enabled encoder. Portal passes its 175 tests and 50-route build. All 69 Creator test files / 1,164 tests and TypeScript pass. The clean build/package pass. Packaged Chromium passes the new hardware, Sequence binding, Sample merge/cancel/Undo/preference-reopen and rotary-to-touch Perform recording journeys. The status containment regression passes against the real rendered console and packaged CSS. Earlier browser failures are retained: report export entered System and correctly cancelled a pending turn; default seed Pad targets were unavailable; Truth acknowledgement preceded the history input unlock; zero playback fields are omitted by Core. Tests now observe the actual target, committed Truth, restored full playback and input availability without removing journey legs. Perform save also waits for its WAV binding before inspecting the artifact. The complete exact-head Creator lane is still pending; targeted passes do not replace that shipping obligation.

**Open acceptance finding (independent review, 2026-10-09):** the implemented
BPM preview updates readback only; playback tempo and metronome follow committed
Truth after 400 ms. The approved decision did not limit immediate preview to
readback. D2 is therefore not fully accepted: retain this finding until the
approved audible runtime tempo preview/clear producer is implemented and
consumed. The owner's pending playback-position choice is recorded in the
supplemental plan in PR #1929; it does not narrow the immediate-preview decision. No passing UI test proves
pre-commit audible tempo preview. The remaining contextual bindings and
monitoring work continue independently; this finding is not silently excluded.

**Version Management:** Creator MINOR debt and monitoring preference are Host
state, deferred to V1; no persisted Contract or Product Build allocation.
**Documentation impact: required** — `/hosts/creator-web/`,
`/hosts/creator-interactions/`, `/platform/input/`.
No corresponding Creator/input source diagram exists; update their current
control tables and retain I1b's shared audio graph. Other product questions
remain in #1822 and D3–D5.

2026-10-10 consumer integration refresh: monitoring producer #1910 is merged
as `9119a7f90262e1c8ada92ac6b894f5014a5c0cab`; strict fixture #1915 is merged
as `864c0f061033a7f0c3488f1908a8817516cd3b62`. Rebase the single consumer Task
onto that actual main, retaining the newly merged MPC Pad arrangement and
touch-panel layout. The only textual conflict is in the Creator Portal page:
retain main's Pad-order paragraph and the consumer's metronome gain routing.
The refreshed source passes all 69 Vitest files / 1,169 tests and TypeScript.
Full packaged/browser and physical acceptance remains outstanding. The BPM
readback still does not preview engine timing; the audible-tempo supplement
PR #1929 and the owner's playback-position choice remain required.

2026-10-10 Sample integration: rebase onto `1992e258b066152e7d08cf5382bf94d21f1d95d1`,
including the Sample contextual pages in #1930 and the owner's DUPLICATE decision
in #1932. Keep all four touch pages and Pad colour management; retain the approved
independent Trim / Pitch and Pad Sound encoder groups. Touch parameter takeover
cancels the rotary draft before the touch edit. Switching Sample subpages cancels
the pending rotary timer and its owned runtime preview before showing the new
page. A component regression first fails because the old timer saves Pitch after
leaving Trim; it must pass with no update and restored playback after the full
400 ms interval. This integration does not implement Assign, new numeric editing,
or the outstanding audible BPM preview. The integrated tree passes all 69
Creator test files / 1,174 tests, TypeScript, and the 50-route Portal check.
The expanded packaged journey retains the original commit, Pad cancellation,
Undo and device-volume reopen legs and adds the Sample subpage cancellation leg;
its browser execution and the complete selected Creator lane remain pending.
A later main refresh is `46df56797265942f760afb253c3e4ad2b3a13c80` (#1934),
a documentation-only interaction map; it does not implement contextual encoders
or the remaining audible BPM preview.

## D3 — record the approved DUPLICATE name

Owner 于 2026-10-10 选择「DUPLICATE（推荐，明确表示复制工程）」，保留
自动保存、复制新身份并打开副本的已有语义。决定见
[D01 DUPLICATE](../prd/decisions/2026-10-10-creator-project-duplicate-label.md)。

**Refreshed premise:** Task base 与 inspected main 均为
`864c0f061033a7f0c3488f1908a8817516cd3b62`。D01 的
`project_surface.tsx` 已显示 DUPLICATE，并用 `onDuplicate` 调用 App 的
`duplicateProject`：经现有 journey 复制，再打开副本；复制/打开失败保留
真实结果与可重试入口。9 月 29 日 workflow baseline 已批准自动保存与复制。
因此没有新的产品实现缺口，不重复修改按钮、存储或失败处理。
该判断不声称完成整体四页、真机或听感验收。

**Declared files:** 本计划；
`docs/prd/decisions/2026-10-10-creator-project-duplicate-label.md`。
**Lowest-tier verification:** 相对链接、源码/回调链与已有决定核对；stage 后
77-case ownership suite；staged diff check；committed-head docs_static；
PR body lint、declaration-only 与无 batch lane 的 evidence check。
**Version Management:** Version impact: none — 产品行为已存在，只记录命名决定。
**Documentation impact: none** — 只新增产品决策并更新计划，Portal 页面与事实不变。

2026-10-10 Perform integration: refresh onto `08c216647138ef9e1f7824a4a2624f82eef86cce`,
which includes #1935's Live / Slots / Takes / Replay pages and #1931's Host proof
result slots. Preserve page state, native pointer capture, navigation refusal
while a touch FX gesture is open, and recording/replay continuity. Keep the
approved three main FX and three more encoder mappings, HOLD semantics and
rotary/touch ownership. Extend the existing touch geometry journey to all
three main faders without removing any page, hit-area or first-screen assertion.
The previous complete lane on 4d558259 was stopped for this integration after
two failures (old-generation window listener retained; final project.inspect
request timeout in the full Perform capture journey). Logs and traces are
retained outside the worktree; no full pass or cause of the latter is claimed.
The encoder cancellation listener must be owned by the Runtime session and
rebound on replacement, verified by the unchanged packaged recovery journey.
The resolved integration passes 69 Creator test files / 1,179 tests, including
FX value retention through Live / Slots / Takes / Replay, TypeScript build,
77 staged ownership tests, and the 50-route Portal check. The three primary
faders share one row, preserving their original 44 px hit areas and 80 px
vertical travel. Packaged geometry, recovery and the complete lane remain
pending; these component passes do not settle those obligations or audible BPM.

2026-10-10 overview integration: refresh the single consumer Task onto actual
main `ec15f9adf3ca7c3fd09c06d61b53e0bcdf189fe6`, including #1938 Sequence
touch controls, #1940 Sound Set navigation and #1942 mode-specific overview.
Resolve the overview conflict by retaining the opened Project / selected Sample /
selected Sequence identity, qualified Perform feedback and the System details
boundary from main, alongside the four approved encoder function/value readbacks.
Keep the SYSTEM title while its overlay is open and the opened Project identity
available to assistive technology. Do not restore the removed generic Project
facts or build metadata to the editor screen. Every existing navigation, history,
capture and refusal journey remains in the consumer range. The original b07
complete Creator failure and its 14-view static/Figma comparison remain retained
outside this worktree; neither is a pass on this integration. This refresh does
not settle the audible BPM playback-position question, Assign, fine numeric
editing or the other pending product decisions. Exact integrated verification
and the original complete Creator lane remain required. The conflict-resolved
integration passes TypeScript, all 71 Creator component/helper files / 1,209
tests (173.96 s), and the staged 77-case ownership suite. Portal and the
committed-head complete Creator obligations still require their own results;
these component passes do not replace them.

2026-10-10 touch-preview integration: later main
`4281d5f54dd01ad73c18e876c2119a35b0229e0b` adds #1946's synchronous shared
touch drafts and rejected-gesture cleanup. Preserve its Project/Pattern/mode
and recording-lock boundaries, the Sample editor's controlled preview-active
signal and both sets of existing lifecycle regressions. Keep ENC4 assigned to
monitoring; do not restore the superseded Swing encoder. Extend the existing
touch timing journey in the declared `sequence_grid_edit.test.tsx` to verify
that ENC3's displayed value follows the same touch draft and cancellation as
the upper screen, without a Truth write. The Sample encoder cancellation
fixture publishes the running Host state after Project open, rather than only
changing diagnostics, and asserts that an audible preview actually begins
before each existing cancellation boundary. Keep the inactive-audio visual
preview and rejected-preview journeys from main unchanged. This refresh does not provide the
still-missing audible BPM producer. Retain the preceding ec15 integration
results as dated evidence; new source verification remains required.

2026-10-10 status/recovery integration: refreshed main
`42d86bfdf3c74785810ebaa0c5fe3e0e11e6e19f` includes #1947. Preserve its compact
default-sound recovery, recording ownership notice across modes/System, and
return-to-Takes Save/Discard workflow alongside I1c's contextual encoders and
FX gesture ownership. Both sets of existing Perform regressions and both CSS
blocks remain. Integrate in a separate short-lived worktree while the original
`bbd4433` complete proof retains its frozen source. That proof is evidence only
for its original head, and neither #1947's pass nor a clean merge substitutes
for fresh integrated-head verification. BPM audible preview and outstanding
product choices remain pending.

2026-10-10 Graphite/font integration: refreshed main
`d5554ed55f7ebc2d800285715cef79dcfed57c9a` includes #1948. Apply the prepared
#1947 integration in another isolated worktree, preserving its original frozen
verification inputs. Resolve the one overlapping CSS append by retaining both
#1948's compact action/font rules and I1c's encoder readbacks/group controls.
Keep main's neutral encoder icon, locked Space Grotesk dependency, stage clip,
font/geometry assertions and late-recovery layout observation unchanged. Preserve
#1947's recovery/recording workflows and all contextual encoder regressions.
The original 37-file declaration still bounds this Task; no mapping, DSP,
deadline, tolerance or unresolved product choice changes. TypeScript, complete
components at their original timeout, ownership, portal and fresh committed
Creator evidence remain required on this integrated input. Earlier runs on
`bbd4433` or `42d86bf` do not establish verification of this tree.
The integrated source now passes all 72 Creator test files / 1,230 tests at the
original 20-second case bounds (132.87 seconds), TypeScript, 77 staged ownership
tests, and the complete 50-route Portal check (82.27 seconds). The product and
test sources remain identical to those verified inputs; this paragraph records
terminal results only. Commit and replace the owned draft PR head with an exact
expected-head lease, retaining the earlier frozen branches and evidence. Fresh
committed-head browser proof and review, audible BPM preview and the outstanding
product choices remain incomplete; none of these component/Portal results is
complete Creator or device acceptance.

2026-10-10 producer integration: refreshed main
`a2a43cc088ab35e40297e80eecb7ef048923a154` includes the landed-overlay cutoff
(#1941), Candidate typed-byte proof (#1943), retained transport replay (#1950)
and matched-frame monitoring proof (#1949). Live PR metadata confirms each
merged source and introducing SHA. Carry I1c's same 36-file diff into another
isolated worktree; it applies without conflicts. Preserve all four producer
deliveries, #1947 recovery/recording and #1948 font/geometry behavior. The
Foundation immediate-depth-refusal repair remains a separate PR (#1956).
The earlier e74 Creator entry failed before tests because this owned checkout
lacked its locked Web test npm dependencies; retain that failed attempt and
provision each required package from its lockfile before fresh verification.
No mapping, product decision, deadline or assertion changes. Frozen earlier
results remain evidence for their own inputs. Verify this integrated source
before replacing the owned Draft PR head; audible BPM and the unanswered
product decisions remain pending.

This integrated input passed TypeScript, all 77 staged ownership checks, all
72 Creator test files / 1,230 cases at their original case bounds (159.87
seconds), and the complete 50-route Portal check (79.35 seconds). The source
and tests remain identical to the frozen verified inputs; only this results
paragraph was appended afterward. Commit the same 36 declared files and update
the owned Draft PR with an expected-head lease. Original complete Creator
browser proof, audible BPM preview, current-head review and the unanswered
product choices remain incomplete.

2026-10-10 stopped-Pattern producer integration: refreshed main is
`e14084f602448ee2046a9cd64e7dd3bf3bd2e7ea`, containing #1978's native
stopped-Pattern transport authority repair, #1956's Foundation depth refusal,
#1966's executable Creator proof build and #1977's VEL-tap regression. Merge
that actual main into the existing I1c consumer branch without conflicts;
retain all three shared touch/ENC3 BPM assertions alongside the new VEL test.
No contextual mapping, commit/cancellation boundary, HOLD rule, bound or
journey leg changes. The previous complete Creator result on `65b237cd`
was 112 passed, two failed and 11 skipped; retain its hardware-profile timing
failure and stopped-Record reconciliation trace as failed evidence. The
frontend reconciliation repair in #1970 remains an independent unmerged Task,
so this integration alone does not close that browser failure. Run the
unchanged complete consumer verification on the new input after coordinating
the browser/Portal build schedule. Audible BPM preview, physical acceptance,
current-head review and pending product decisions remain unfinished.
The newly refreshed interaction manual in main still describes ENC4 as Swing,
other pages' encoders as unassigned and rotary drafts as surviving page exit.
Add that existing Portal page to I1c's declaration and correct those current
source facts in this Task; retain the open audible-BPM finding and the existing
direction-key decisions. #1980 reorganizes the same handbook by page; retain its
new layout and anchors while updating the relevant control cards and appendix.
The earlier 03a integration and both successful Portal checks are retained as
dated evidence; fresh handbook verification is required. This adds one
documentation path, no product scope.

The integrated product/test inputs pass all 72 Creator files / 1,231 cases at
the original 20-second bounds (58.09 s) and TypeScript (1.54 s); all 32 owning
input hashes remain unchanged through the later handbook-only refresh.
Staged ownership passes 77 tests (6.03 s), official document validation passes,
and the final page-organized handbook passes the complete 50-route Portal check
(51.26 s). Its ConsoleDiagram and 39 anchors remain identical to #1980.
The final diff contains 37 of 38 declared paths. Record these results and push
the existing Draft PR; fresh committed-head Creator and independent review are
still pending. The separate frontend reconciliation repair must be integrated
before the consumer's complete browser acceptance; its predecessor's passing
Creator lane is not evidence for this consumer head. Audible BPM and the other
open product and physical acceptance obligations remain unfinished.

### 2026-10-10 — integrate the merged current-command repair

Fresh protected main is `4dde8e5e6b511c3ae2bd9c310f607f7d6148d2dc`, the actual
#1970 squash at 09:08:21 UTC. Its authenticated review and complete Creator
receipt belong to the repair's `46f6877b` input. They are not a pass key for
this contextual consumer. The preceding #1970-unmerged note is historical.

Merge that main normally into the clean pushed consumer `f2593fd...`; retain
its live Runtime/Project/session/command guards and all three mounted-App
late-error/current-error regressions alongside the approved ENC1–3 bindings,
global ENC4, Sample 400 ms cancellation and Perform HOLD/gesture ownership.
The merge has no conflicts; it imports the existing repair rather than
reimplementing it. Main's #1980 page-organized handbook, SVG, anchors and the
approved contextual-control corrections remain unchanged.

**Integration Task declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/pattern_transport_actions.ts`
- `apps/creator-web/test/pattern_transport_actions.test.ts`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `docs/plans/2026-10-10-creator-transport-current-observation.md` (exact main)
- This plan.

The three additional imported-main paths are already #1970's declared and
merged files; the consumer diff relative to actual main retains I1c's own
38-file declaration. Verify the combined full component set at its original
20-second bounds, TypeScript, exact staged ownership and committed docs_static.
Current Portal pages, diagrams, projected identities and source-facing facts
are byte-identical to the completed `f2593fd` Portal inputs; this internal
current-command repair restores existing semantics, so it adds no new Portal
fact or fresh full Portal build obligation. Record that comparison explicitly.
The I1c documentation-impact declaration remains required.

**Version impact:** no new identity allocation; retain the existing Creator
compatible MINOR debt, absorbing #1970's PATCH repair at Goal V1.
**Acceptance:** preserve the 65b complete failed run and original bounds.
After the Conventional integration commit and normal push of the same Draft
PR, run this consumer's own complete Creator lane when the parent's heavy-run
window is available. Audible BPM preview, open product choices, current-head
review, A1 visual comparison and A2 physical/hearing acceptance stay unfinished.

The combined staged source passed all 72 component files / 1,248 tests
(`npm --prefix apps/creator-web test -- --run`, 61.50 seconds including the
wrapper, 60.33 seconds reported by Vitest). TypeScript passed in 3.82 seconds;
the staged scope passed 77 ownership checks in 9.61 seconds. Source and test
hashes are retained with the staged-tree receipt in
`encoder-consumer-main-4dde8e5e` outside the worktree. The final plan-only
results update leaves those tested product inputs unchanged. Committed-head
docs_static and this consumer's complete Creator proof remain separate
verification boundaries; the earlier repair's receipt does not satisfy them.

### 2026-10-10 — expose device-volume restore readiness

**Premises:** PR #1936's authenticated exact-head review of
`367a14daa980e7106789d346023cdfb31837f0e9` found that musical controls can look
available while device-volume restoration is pending. Fresh main is
`785d36db27dc44fde7cceb4f6cb6da0956a795e1`; its changes after #1970 are
documentation reconciliation, not this consumer repair. The old session's
restore is already fenced by effect cleanup, but the current session's
`activateAudio` returns false until its preference arrives. Pad and transport
reachability omit that prerequisite and show no visible pending reason. This
remaining refusal is confirmed from the actual consumer source. Preserve the
original 367 complete Creator PASS and its seven browser groups as dated
evidence; it is not evidence for this subsequent repair.

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- This plan.

**State boundaries:** show a visible and accessible `Restoring output volume…`
status. Pad, Play/Record and keyboard/pointer input share the current Runtime
session's monitor-readiness prerequisite. Temporarily disable musical Pad
input; other page and authoring controls retain their existing reachability.
Keep the Runtime's actual phase, restore-before-first-audio, bounded storage
fallback, remembered zero volume and stale-session cleanup. Do not queue or
replay a gesture after its browser activation window has expired.

**Lowest-tier verification:** a mounted App regression delays actual
IndexedDB read-success delivery after storing a device preference. While its
Runtime/Project are ready, pending status and musical disabled state must be
observable and a keyboard gesture must not activate or trigger audio. Release
the same session's read, verify restored zero, restored input reachability and
a positive musical input through the existing running-audio component seam.
A replacement-session case releases the old read first and verifies that it
cannot set the replacement's volume or clear its pending state. Record an
actual RED failure on unchanged product source before the fix, then GREEN;
keep the original case bounds. Run affected components, TypeScript, staged
ownership, Portal and fresh committed-head selected Creator evidence when the
coordinated resource window allows them. No old pass key satisfies the new
head's verification or authenticated review.

**Version Management:** compatible Creator PATCH repair absorbed by the
existing I1c MINOR debt at V1; no manifest or Product Build allocation.
**Documentation impact: required** — `/hosts/creator-web/`; document the
visible restoration/input boundary. The existing input diagram does not
describe this Host preference read, so no new diagram is required. Audible
BPM, D03/D04, S1 and A1/A2/V1 remain incomplete.

The mounted deferred-IndexedDB regressions first fail on the unchanged 367
product: the first case reports `disabled` false instead of true at
`workspace_shell.test.tsx:4317`, and the replacement case cannot find the
restore status. The first fixed-source attempt passes replacement but fails
the other case's mistaken `Play` locator; retain that fixture failure. Correct
the name to the existing `Play/Stop`, restore only the two owned old product
blobs, and rerun the corrected test: actual RED exit 1 (1.96 s). Restore the
fixed source with fresh mtimes; the identical corrected test then passes both
cases (1.98 s). The other 124 cases are unselected by this reduced command,
not a full component result. Receipts, source/test hashes and all logs remain
in `consumer-monitor-readiness-repair` outside the worktree. The deferred
events belong to actual stored `monitor-volume.v1` read requests, not a mock
preference function. The positive musical admission uses the existing running
component seam; it does not establish browser-trusted activation or hearing.
TypeScript first reports TS2683 for the new IndexedDB spy's untyped `this`.
Add only the erased `this: IDBObjectStore` annotation; TypeScript then passes
(1.73 s), and both reduced regressions pass again (2.40 s). Keep the original
type failure and the final test hash alongside the earlier RED/GREEN receipts.
The repaired input passes all 72 Creator component/helper files and 1,250
cases (53.56 s wrapper / 53.18 s Vitest) at the original 20-second case bounds.
All five declared input hashes remain unchanged during that run. Portal also
passes all 176 checks, current page/diagram validation and the 50-route build
with internal links (52.33 s); its source guards remain unchanged. The final
I1c declaration contains 39 unique paths, of which 38 change in the actual PR
merge-base range. This five-file repair preserves the earlier 367 complete
Creator result as dated evidence and allocates no identity. The final
results-only plan update does not change tested product, test or Portal page
inputs. Staged ownership, committed docs_static, this repair's fresh complete
Creator and authenticated current-head review remain separate boundaries.

## P0 — ship this bounded plan

**Declared files:** only `docs/plans/2026-10-09-creator-desktop-final-followup.md`。

**Lowest-tier verification:** 检查相对链接与 declared files；新增文件 stage 后运行
`python3 tests/build/ci_change_scope_test.py`；运行实际选择的 docs_static；
PR body lint 与 declaration-only 检查。本 Task 不改变产品事实或 Portal 页面，
不新增产品测试或 required gate。

## R1 — latest projection after consecutive authoring commits (#1905)

**Behaviour:** 连续 authoring 操作按 tail 顺序提交，后一次投影不能被 render ref
滞后丢弃。每次请求仍使用正确 expectedRevision，Project 切换后的旧结果仍被
拒绝；不放宽 reducer 的跨 Project/Pattern/token 身份保护。成功提交后的
刷新失败沿用现有 error/current 清空策略，authoring tail 保留已提交 revision，
不能重发已提交操作；本 Task 不改变失败投影的契约。

**Declared files:**

- `apps/creator-web/src/app.tsx`；
- `apps/creator-web/test/workspace_shell.test.tsx`；
- 若 reducer 复现需要，`apps/creator-web/test/creator_state.test.ts`，不预先改 reducer；
- `apps/docs-site/docs/hosts/creator-web.mdx`；
- 本计划（更新 R1 状态及验证证据）。

**Lowest-tier verification:** App component 测试先显示 red：两个同步进入 tail 的
颜色操作都已提交后，Pad 呈现第二个颜色；另外两种不同操作（例如 grid edit
和 Pad colour）连续执行后同时呈现最新事件和颜色。保留当前 stale token/
Project 切换拒绝测试。断言分别检查请求 revision、fixture Truth 和最终 UI，
不能只检查两个请求都成功。修复后这些检查通过，revert/mutation 证明失败
确实落在新显示断言。再执行 Creator unit/typecheck、Portal check，以及最终
committed head 实际选择的 batch-only creator lane。

**Documentation:** `/hosts/creator-web/` 描述成功 authoring 后投影刷新的一致性。
**Version:** Creator 修复至少欠 PATCH，纳入 V1；不在修复 Task 猜测身份。
**Pitfall:** 产品逻辑的回归测试是其出口；不为该逻辑错误新增流程 pitfall。

2026-10-09 R1 进度：两个同步颜色请求以 revision 3 → 4 → 5 成功提交，旧代码
仍画第一色（预期 `3`，实际 `2`）；颜色紧接 grid edit 的 fixture 使用真实
snake_case Project event 字段，旧代码同样在最终 UI 缺少音符的断言处失败。
恢复修复后，完整 Creator Vitest 67 files / 1,135 tests 与 `tsc --noEmit`
通过，现有 stale Project/Runtime 和失败清空投影测试继续通过；
`scripts/docs-site.sh check` 通过（50 routes）。修复仅让 grid、structure、
colour 三条成功路径先 dispatch 已提交 revision，再以该 revision 刷新；
settings 的现有显式 revision 刷新不变，reducer 不改。以上不代替最终提交头的
batch-only lane、当前头评审、实际 merge 或 A2 的人工验收。

2026-10-09 R1 完成证据：最终提交头
`3827b4614b50c20119d3438c2c511c5e3341d285` 的选中 Creator/docs_static lane
完整通过；Creator proof 包括两次干净产物一致性、1,135 单测及全部选中浏览器
分组，batch key 为
`efa97940870ca51b5be878429bf8588c96591008b15d43cd481ad790832acbcc`。
该 key 只证明 R1 当时的输入，不供后续 Creator 改动复用。自动评审
`37869819612/1` 因 service_error 未完成；独立会话审完完整四文件 diff 与验证，
无遗留 finding，owner 接管记录见
[#1907 comment](https://github.com/endaye/lmdj/pull/1907#issuecomment-6072499529)，
`review_wait.py` 确认有效后按 expected head squash merge，#1905 已关闭。
真实输入、听感和物理设备验收仍属于 A2。

## C0 — capability audit before product decisions

**Declared files:** only this plan.
**Lowest-tier verification:** 相对文件链接/声明范围核对、`git diff --check`、
实际选择的 docs_static、PR body lint 与 declaration-only；不新增产品测试或 gate。
**Version impact: none** — 只记录调查，未改变实现、Contract 或身份。
**Documentation impact: none** — 记录既有源码与决定供后续 Task 使用，不修改
Portal 或产品行为。以下建议均未获本次 owner 批准；不作为 I Task 实施授权。

Inspected revision: `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`。
检查 Web Host 的完整 `bridge.cpp::supported_operation` 注册表，再读
`control_runtime.cpp` 实际 handler；以 `project.duplicate`、`sample.update_pad`、
`performance.fx.gesture` 这些已注册并实际分发的操作为正向控制。
同时检查 Runtime Session 方法、Creator consumer 和现有测试。
以下“无操作/投影”限定为本 revision 的 Web Host/Creator 公开路径，不表示所有
Core 内部均无相关算法。进入 I Task 前仍须刷新相关源码与继任交付。

### D2 — 400 ms 的已实现部分与未决定边界

- `apps/creator-web/src/state/encoder_input.ts::createEncoderTurn` 每格立即预览，
  最后一次输入后 400 ms 提交一次；回到起始值不提交；范围 clamp；前一请求
  尚未完成时从 requested value 继续。`cancel` 丢弃未提交 turn，`forget`
  在失败后忘记 requested value；两者不能撤回已经提交的 Truth。
- `app.tsx` 的 Tempo/Swing 范围分别为 40–240 BPM、50–75%。目前取消 effect
  绑定 `transportBusy || recording`；settings error 触发 `forget`。
  `selectMode`、`openSystem`、rail Undo/Redo 没有调用这两个 turn 的 `cancel`，
  encoder helper 也没有 Esc 监听。不能把 Sample slider 的取消机制当作 encoder
  已覆盖这些转移的证据。
- `test/encoder_input.test.ts` 七个案例覆盖合并、no-op、范围、取消、Truth 与
  in-flight 起点和失败回退；该 harness 手动触发 timer，不证明真实 400 ms
  边界，也不证明离页、Project 切换、Esc 或 Undo 集成行为。
- 待选择：是否保留 400 ms；离页/System/切 Project/失去所有权/卸载时对未提交
  preview 取消还是先提交；Undo/Redo 前先取消还是提交后再撤销；Esc 作用域。
  建议保留 400 ms，并对脱离目标的未提交 preview 取消；此建议尚未批准。
  已发出的请求仍须保留准确身份与真实结果，不得当作可取消的本地 preview。

### D3 — 已决定的 autosave / Duplicate，剩余是 D01 表达

[已确认的 workflow decision](../prd/decisions/2026-09-29-creator-user-workflow-baseline.md)
第 4 项已明确“全部自动保存，另存为即复制工程”，来自 #1652 →
`2abbb3fdaf718f1433b640ff954ce23d9664b31e`。#1684 已由 #1714 →
`206fcd571f60a0608fa3cded0e744b1e7ae1a84c` 交付；此处保留已有决定，不把
原 Desktop Final 的未渲染项解释为必须重新增加手动保存机制。

- Runtime `duplicateProject({sourceProjectId, projectId})` 经串行 Project action
  发送 `project.duplicate`，payload 严格为 `source_project_id, project_id`，
  无 sidecar；返回新身份、revision 0 的 summary。
- Host handler 调用 Facade `duplicate_project`；running、active Sequence 或
  Sample import 阻止复制；busy/unfinished-recording/identity/storage 拒绝由真实
  错误呈现。Host 只复制，不替换当前 Project、writer lease 或 Runtime。
  Creator `duplicateProjectJourney` 及 `app.tsx::duplicateProject` 随后单独打开
  副本并更新 remembered Project；打开失败仍保留、列出已复制的 Project。
- `project_overview.tsx` 已显示自动保存；`project_surface.tsx` 已有 Duplicate
  入口，D01 `hideSummary` 布局也渲染该入口。`project_create.test.tsx` 包含新身份、
  记住副本、拒绝、复制已存但 summary 无效、打开失败、旧 Runtime 拒绝等案例。
  Web Host 完整注册表没有独立 `project.save` / `project.save_as`；不能用
  `performance.save`（另一对象的操作）代替。
- 待确认仅是 D01 是否保持 Duplicate 名称/位置，或把相同已交付动作标作 Save As。
  若 owner 想引入手动保存、改名或导出，须明确改变既有语义并独立设计所需接口；
  不凭图添加“未保存”提示。现有自动保存/复制无需重复实现。

### D4 — Sample 的可复用编辑与新 Assign 的界线

- `sample_surface.tsx::runImportJourney` 统一文件/录音字节采用流程；已有 Pad
  替换确认、mutation 前 stop、expected revision、AbortSignal 和最终刷新。
  Slice/Candidate 的片段与明确目标选择是既有独立路径，不能据此推导一个
  未设计的新 Assign 按钮的对象与目标。
- Runtime `updatePad` → `sample.update_pad`，payload 为
  `command_id, expected_revision, slot, playback`，无 sidecar；Host 要求可用
  session，处理 mutation controls，Facade 检查 authoring admission、已分配
  Asset、音频边界与 expected revision，再执行持久化 `UpdatePadPlayback`。
  Preview 是 `sample.preview.set {slot, playback}`，清除是
  `sample.preview.clear {slot}`；两者不是 Truth 保存。
- `SampleControls` 已有 Volume −60…+6 dB / 0.1 dB、Pitch −24…+24 st / 0.1 st、
  Pan −100…100 / 1，以及 Attack、Release、Tone、EQ 等。Volume/Pitch/Pan 用
  `ParameterSlider` → `ValueSlider`；后者只有 range 与 output，没有通用数字
  输入框。它在 release/blur 提交，Esc/pointercancel 取消，不能静默改成 400 ms。
  `WaveformEditor` 已有 Start/End 秒数输入，步长 1/source sample rate，转换为
  frame；因此“细调编辑器完全缺失”不成立，须指定哪些参数、精度与入口仍缺。
- Host 已注册 `pad.assign`，严格 payload 为
  `command_id, expected_revision, slot, asset_id`（asset_id 可为 null），无
  sidecar；调用 Facade 并更新 Project revision。仅有此低层操作不等于 Creator
  已有素材浏览/选择/采用/Runtime 重建的完整 Assign journey。
- 待决定：Assign 是导入新文件、采用候选，还是将已保留 Asset 指向另一个 Pad；
  指定目标、替换确认与取消语义。细调需分别确定 Volume/Pitch/Pan 等是否可点数值
  输入、常规/SHIFT 步长；保留既有单位、边界、单次 commit、失败与 Undo 行为。
  audition golden PR #1904 当前仅是一文件计划，尚未合并；不重复其测试设计，
  也不把它视为已执行的音频验收。

### D5 — live controls 需要的 producer 工作

- `FxSliderBank` 已渲染 Filter/Delay，其他六种 FX 在 FX / MORE。
  Runtime type、Host validator、Facade handler 都使用八种 FX 的单一整数
  `value`（0…1000）；`performance.fx.gesture` payload 只有 `event`，无 sidecar。
  engage/move 是 `kind, fx, value`，release 是 `kind, fx`，hold 只有 `kind`。
  Facade 将其交给实际 master-bus gesture sink；无 sink 时失败。live gesture
  不写 journal，录音另经 `performance.record.event` 记录。
- `audio-runtime/src/master_fx.cpp::process_filter` 用同一 value 控制 LP/HP
  深度（500 bypass，小于 500 LP，大于 500 HP），coefficient/damping 从该值
  派生；没有独立的 type/cutoff/resonance 输入或 BP 输出选择。
  此算法不等价于 D04 的独立 LP/HP/BP + resonance 控件。
- 完整 Web Host 注册表、FX event validator 与 `runtime_types.d.ts` 不提供
  master gain、独立 filter 参数、live Pad Mute/Solo 操作。Sample 的 persisted
  `playback.muted` 已存在，但不等于 Perform live Mute/Solo 的状态与录制语义。
- `control_runtime.cpp::status` 提供 Project/Runtime/control generation、limits、
  audio/capture state 和 Pattern transport，没有输出 level 投影。
  `performance_master_tap_worklet.js` 的 PCM batch 只在 capture generation
  启动后发送给录音 sink，不能当作常驻电平接口；`PerformOverview` 没有电平读数。
  这些实际 producer 证明 Creator 尚无可直接绑定的输出 meter。
- 待决定：MASTER 作用于监听、录音、重采样的哪一段及是否持久化；滤波采用
  现有双向单值还是新增独立 type/cutoff/resonance；Mute/Solo 针对哪些 Pad，
  属于 Truth 还是 live session，是否进入录制/重放；meter 的测量点、单位和峰值
  保持。新增能力先做 Contract/Facade/audio/Web producer Task，再做 Creator
  consumer Task；不能用 Sample gain/mute 或合成电平代替这些决定。

## Decision and implementation Task contract (D1–D5 / I1–I5)

每个 D Task 在决定前核实真实源码与 dispatch/handler/payload/state 前提，
记录 inspected revision、已有能力、仍需实现和未确认部分。既有能力的正向
控制与实际 authoritative registration 必须先检查，再报告缺失。

Decision Task 声明自己的 `docs/prd/decisions/` 文件、decision-log/open-questions
更新、本计划，以及适用 Portal 页面；路径在该 Task 开始前锁定。决定之后，
在本计划追加实现 addendum，列出精确文件、最低层测试、每个状态/转移的
验收与影响。Core/Contract/Host producer 与 Creator consumer 有实际依赖时
分开 Task；未决定或未声明文件的 I Task 不进入实施。

## Acceptance (A1/A2)

**Declared evidence file:** `docs/quality/2026-10-09-creator-desktop-followup-acceptance.md`，
另加本计划；自动化发现的产品/测试问题使用独立修复 Task 声明文件。

四页分别覆盖正常、拒绝、失败、取消、Undo/Redo、reload/reopen。核对字体、
布局、缩放命中、键盘、控件状态与 Figma/decision；Figma fidelity 是实际
比较结果，不从功能测试推断。现有 journey 不删 leg、放宽阈值或伪造输入。
真实 Safari/iPad 输入、听感、辅助技术和生命周期分别记录；需要 owner 操作
时给出可执行步骤与预期结果，收到实际证据前保持未验收。

验收记录包含源码/Build/Host 身份（来自 manifests 或 report）、来源、设备、
浏览器、操作人/日期、逐 leg 观测和 report digest。未分配 Build 的源码验证
明确写源码 revision，不用旧 Build 证明新功能。V1 的 snapshot 不能倒推
此前人工验收绑定到新 Build；必要时在 V1 后复验身份敏感的验收。

## Version Management

Version impact: none — P0 仅建立计划，不修改 active manifest、Build 或 Contract。

实现 Task 各自记录 PATCH/MINOR/Contract 兼容性，V1 按最终实际影响协调结算。
原计划已记载 Creator 及相关 Core/Web 模块的版本债务；读取现行 manifest 和
继任版本提交后再确定剩余债务，不手填旧版本或预分配号码。

V1 在执行前声明确切 manifests、消费者、测试、Build/Channel 与 snapshot 文件。
Product Build/Assembly 改动同步更新当前 Portal、生成不可变 snapshot，合并后
验证实际 introducing SHA 的 provenance；必要 witness 走官方 generator 的
独立后续 Task。此过程不启动 Release 或部署。

## Documentation Impact

Documentation impact: none
Reason: P0 只记录计划与进度，不修改 Architecture Portal 或宣称新产品事实。
R1 和各实现 Task 按实际影响更新 Portal；Build/Assembly Task 必须 required。

## Verification and completion

每个 Task 先证实原因和当前前提，再跑最低层测试。stage 仅声明文件，确认非
main、ownership、cached diff check，创建 Conventional Commit；在 clean committed
head 分类，执行所有实际选择的 batch-only lane，PR 记录 pass key。评审、修复、
最终 main/governance 刷新、完整 conversation/closing relation 和 expected-head
保护均按 issue-done。失败后端/旧 head/过期证据不是独立评审。

本 Goal 的每项范围均完成决定、实现、验证、合并和适用验收，或者经 owner
明确取消/移出后，才可结束。保留最终 PR/SHA、验证/人工证据、版本/snapshot
状态、清理结果与范围处置；等待、额度、PR 创建或一段 green journey 不表示完成。

## Pitfall Impact

Pitfall impact: none — P0 规划不引入新流程知识。执行中按 Task area 查阅 pitfall，
特别保留共享构建目录、环境相关性归因及真实输入完成证据的既有要求。
