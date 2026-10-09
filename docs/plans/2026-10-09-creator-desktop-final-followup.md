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
| #1822 其余控件映射已有决定 | 部分批准：owner 已批准下文 I1a 的 Sequence ENC1/↑/↓；原 T6 的 ENC2–4/左右键已交付。其余页与粗调步长仍待决定；Issue open。 |
| 400 ms 规则已正式确认 | 原计划 T6 仍记录为待 owner 确认的提案。D2 需正式决定，不把实现存在当作产品批准。 |
| D01/D03/D04 图示能力均可直接接线 | 部分反证：下文 C0 核实了可复用的复制与 Sample 编辑；MASTER、独立滤波参数、live Mute/Solo 及电平投影仍需 producer 工作。D01 自动保存/复制语义已有决定，不重新设计。 |
| 合并/自动化可代替人工验收 | 不成立。原验收台账保留真实输入、听感、辅助技术和生命周期缺口；A1/A2 分开记录。 |

开放 PR #1904 是 audition golden 计划；开始涉及 audition 的 Task 时重新核对其
交付与文件范围。原 Claude 主会话没有进行中的实现任务；监视器不取得新 Task
工作区所有权。新 Task 使用自己的隔离工作区，不共享旧构建目录。

## Progress and order

| ID | 工作 | 初始状态 | 依赖/完成条件 |
| --- | --- | --- | --- |
| P0 | 本后续计划 | 已合并 | #1906 → `cd5fbf9290fba820139bfdc9d41b9166a7fe333b`；独立接管评审及修订已验证。 |
| R1 | #1905 连续 authoring 提交刷新 | 已合并 | #1907 → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`；red/green、完整 Creator lane、Portal 与当前头独立评审通过；不代表 A2 人工验收。 |
| C0 | D2–D5 当前能力及决定边界调查 | 调查已记录 | 绑定下文 inspected revision；只更新本计划，不批准产品提案或实现 I Task。 |
| R2 | #1868 导入稳定性条件调查 | 待调查（条件项） | 若阻碍本计划验收，保留 trace 并定位请求/读取/提交边界；证实原因后独立修复。 |
| D1 | #1822 统一原则及逐页映射 | 原则与 Sequence 已确认；其余页待决 | owner 已选统一原则；再逐页确定具体参数、当前 Pad、边界/播放/录音/SHIFT 行为。 |
| D2 | 400 ms 连续旋钮提交 | 待 owner 决策 | 确认预览、提交、取消、离页、锁定、Undo 语义。 |
| D3 | D01 Save / Save As / 未保存提示 | 语义已有决定；界面待确认 | 保留自动保存、复制新身份并打开副本的已交付流程；确认 D01 命名/入口，不能引入虚构的未保存状态。 |
| D4 | D03 audition/trim/browse/assign 与细调 | 能力已调查；待 owner 决策 | 区分已实现的导入/替换/trim 与新 Assign、参数细调入口；明确目标、单位/步长、Undo/Redo、取消/失败。 |
| D5 | D04 MASTER/滤波类型/Mute/Solo/电平 | 能力已调查；待 owner 决策 | 明确作用域、Truth 与 live 状态归属、真实投影及 DSP 能力；producer 与 consumer 分 Task。 |
| I1–I5 | D1–D5 的对应实现 | 等待相应决定 | 每项批准后追加精确 Task，再实施和合并；不得以此编号捆成一个大 PR。 |
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
