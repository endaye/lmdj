# Creator 交互手册与设计状态复核

日期：2026-10-12。范围：更新当前操作手册、关联门户说明与本地 HTML 阅读版，
核对开发和修复后的交互及设计差距。此 Task 不修改产品行为或替 owner 批准新设计。

## Source and scope

- 核对 main：`7df1af16df5e6d864ca7968626d63f84a5d9cb63`。
- 比较起点：手册按页面整理的 #1980，`e14084f602448ee2046a9cd64e7dd3bf3bd2e7ea`。
- 分支：`docs/creator-interactions-audit-20261012`，隔离 worktree。
- 声明文件：
  - `apps/docs-site/docs/hosts/creator-interactions.mdx`
  - `apps/docs-site/docs/hosts/creator-web.mdx`
  - `apps/docs-site/docs/platform/input.mdx`
  - 本计划。
- 本地阅读版由本次门户构建导出到原有 ignored 路径
  `.local/creator-interactions/creator-interactions.html`；它是阅读副本，门户为正式源码。

## Premise dispositions before editing

| 前提 | 当前证据与处置 |
| --- | --- |
| 手册仍完整反映当前 Pad 与 Bank | **过时，更新。** #1989 合并 `ea657b3e6f6346fcafe0c4fbeb7667518f073244`；`selectCurrentPad`、`selectBank`、`stepSequencePad`、input controller 及 workspace tests 表明 Sample 与 Sequence 共用一个当前 Pad，Bank 不重定向编辑对象。保留 armed Capture 的固定目标例外。 |
| 页面旋钮和监听仍待实现 | **已交付，不重复实现。** #1936 合并 `9b4d80c9e5ed965f5776c0321cf166d9d1f289ce`，#2000 合并 `116280f9209245b4757a814fcf3155002b025269`；App 的 encoder bindings、监听偏好、Perform MASTER 使用同一状态。补足恢复监听音量前的可见等待条件。 |
| 播放中只能下一小节切换 | **过时，更新。** #1992 `a98ae01c4f033c78221fc961f6207c7fe5cabfd7` 与 #2015 `e220c98ca1b0f4a3c08646bfeb328ffa186a263d`；SETUP 的三档 SEQ SNAP、设备偏好及实际 request 参数均已接线。OFF、全局 Pattern 录音中切换、count-in 仍未交付。 |
| 任一入口点当前 Pattern 都取消排队 | **不一致，记录剩余实施缺口。** `PatternSelector` 对当前项只关闭弹窗，不调用 onSelect；←/→ 和未录 Performance 的 Launch 走 `selectSequencePattern` 请求路径。已批准的统一取消语义尚未贯穿 GROOVE。正文明确当前操作；不以设计替代事实。 |
| 停止 Performance 后 Launch 一直不可用 | **过时，更新。** #1998 `c4287b454fab09c733f7b7d4e025b905cf1fe779` 的实际 `transportLaunchOpen` 允许 idle/stopped，阻断 starting/stopping/saving/discarding/failed；对应 deferred setup/stop 测试证实转换完成前不得走 fallback。Stop 完成后跟随全局 transport。 |
| 换页必须重新等待 Undo | **修复已交付。** #2001 `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`；ready 且权威不变的普通换页保留历史。blocked/unknown、报告失败、Slice/Sound Sets 路径及 focus/authority 变化仍重新核对。 |
| 可听 BPM 的位置语义仍待决定 | **已批准、未实现。** #1929 `314d1cadd8aab7504513b15a42cc96bb9c8742d8` 已确定保持音乐位置。App `tempoPreview` 只改读数，400 ms 后保存；不得写成已经能即时变速。 |
| Assign、精确输入、四排键盘、D04 仍全是设计问答 | **已批准、交付不完整。** 读取 2026-10-10 Sample/BPM/D04、2026-10-11 keyboard/navigation 产品决定，并区分 encoding 技术提案的工程边界；四排键盘、Sample 入口和三页普通方向导航未挂载。 |
| 独立滤波与实时 Mute/Solo 底层完全不存在 | **过时，纠正能力层级。** F1 #2014 `a61ab819686ad896a3192e4a4bce1541ae55676d` 有 typed Filter controls，M1 #2037 `7df1af16df5e6d864ca7968626d63f84a5d9cb63` 有 64-Pad gate masks。当前 Perform 仍使用旧单值 FX，尚无独立 FILTER、live Mute/Solo 或作品 meter 的完整界面与录放流程。 |
| 上屏仍可见选区数量／力度摘要 | **当前显示不同，更新。** `OverviewDisplay` 传 `hideContext`，`SequenceOverview` 将旧 context 放入 visually-hidden；正常上屏显示旋钮读数及八行轨道。不能以 DOM 文本存在当作视觉可见。 |

以上 PR 的 merged 状态和完整 merge SHA 已经 GitHub API 回读；闭合的问答
#1958/#1959 只说明决定已完成，不证明剩余实施已交付。113 条非 `ci:storage`
开放 Issue 的清单低于 Search 上限；它用于交叉核对，不替代源码。

## Coverage and method

逐一检查四区的全局操作及 Project、Sample 四子页、Sequence EDIT/SETUP、
Perform Live/Slots/Takes/Replay、Sound Sets、Slice、System 和跨页恢复。
读取比较区间内 Creator 的 25 个变动源文件；原手册其余入口的 owning source
在比较区间没有变动时，保留原说明并以当前组件套件复核。没有把历史设计图、
关闭的 Issue、单个注册 operation 或未合并分支当作当前完整流程。

| 交互范围 | 当前权威与自动化索引 |
| --- | --- |
| 页面、Bank、当前 Pad、旋钮、监听恢复、history | `app.tsx`、`creator_state.ts`、`input_controller.ts`、`authoring_history.tsx`；workspace_shell、hardware_console、authoring_history、encoder_input、monitor_volume_preference |
| Project、Sample 子页／录音／精确范围／取消 | project_surface、sample_surface、sample_controls、waveform_editor、sample_encoder、capture_panel、long_source_editor；对应组件与 action tests |
| Sequence、排队、取消、上屏、SEQ SNAP | sequence_touch_workspace、touch_kit、sequence_overview、pattern_transport_actions、seq_snap_preference；sequence_surface、workspace_shell、pattern_transport_actions、seq_snap_preference tests |
| Perform、MASTER、Launch 转换门槛、FX、Replay | perform_surface、fx_slider_bank、pattern_launch_strip、perform_overview、perform_state；perform_surface、perform_overview、workspace_shell tests |
| Sound Sets、Slice、System、异常和恢复 | soundset_surface、candidate_surface、system_surface、recovery_prompt、takeover_panel、error_panel；对应组件与 workspace tests |
| 新底层能力与尚缺 Creator 接线 | audio-runtime 的 FilterParameters/FilterGesture 与 PadGatesState API、实际 render 消费；App 的实际挂载、Perform FX 枚举/控制和 Sample 控件完整范围 |

缺失入口的正向对照是同一挂载链中存在的 MASTER、旧 Filter、Sample Delete
和 Start/End input；逐项读完整 consumer，确认没有 Assign flow、六参数 Apply
输入、独立 FILTER、Mute/Solo/meter、count-in 和 OFF 控件。底层 API 的存在
单独记录，不能从名称搜索为空或图示缺少得出全栈不存在。

## Design reconciliation

### 应随已实现行为同步的设计说明

- Bank 表示当前演奏组，当前 Pad 表示编辑对象。选 A03 后切 Bank B，编辑对象
  仍为 A03；Sequence ↑/↓ 从 A03 继续。图稿和操作图须体现两者可以暂时不同。
- 所有页 ENC4 与 Perform MASTER 共用监听值；作品电平、录音输出与监听响度
  保持各自语义。恢复记忆音量的等待状态必须可见。
- 播放中的“当前／排队目标”分别显示；SEQ SNAP 为设备偏好，与网格 Snap、
  录音 Quantize 不同。三档当前能力与未来 OFF／录音切换分开。
- 普通换页保留 ready history；需要重新核对的失败／恢复情形仍显示真实等待。
- 独立滤波和 live Mute/Solo 已有 DSP，剩余录制数据、Facade/Web 和 Creator
  接线按已批准设计继续；不再为这些已经确定的产品语义重复发起问答。

### 仍需处理的体验缺口

| 优先级 | 观察 | 下一步与批准边界 |
| --- | --- | --- |
| 高 | GROOVE 点当前项与 ←/→、Launch 的取消排队行为不一致 | 已批准的取消语义尚未完整实现；后续修复应覆盖“排队 → 点当前 → 队列清空且旧 Pattern 继续”。本 Task 只记录现状。 |
| 中 | Bank 与当前 Pad 分离后，当前编辑对象可能在可见 Bank 外；Sequence 的 context 摘要已隐藏 | **建议，待设计确认：** 保留可见的当前编辑地址，检查它与四个旋钮读数的空间分配；保持 Bank 不改编辑对象的现有语义。选区数量与力度摘要也需要重新评估可发现性。 |
| 中 | Record Sample 停止后可裁剪／保存，但无法先试听录下的选段 | **建议，待设计确认：** 增加“裁剪 ↔ 试听 → 保存”闭环，明确试听与 discard、切页及其他录音的互斥。 |
| 中 | 三类录音、保存失败与已保存但音频未就绪有不同入口和文字 | **建议，待设计确认：** 统一显示录制对象、目标、保存状态及下一步；保留三类录音职责与持久化/音频准备的真实区别。 |
| 低 | NOTE 轻点已有音符直接删除，VEL 轻点不编辑 | **建议，待用户验证：** 比较当前快速开关与选择后删除的误触率/操作成本；此处不批准替换手势。 |

历史决定保留原文；本报告链接新的批准，不改写当时的证据或把以上建议记成
owner 已批准。设计稿资产本身没有在此 Task 中修改。

## Verification

- Baseline: `npm test --prefix apps/creator-web -- --run`，74 files / 1305 tests
  PASS；覆盖上述页面、控制器、参数取消、排队、history 与恢复的组件/单元事实。
- 文档编辑后 `scripts/docs-site.sh check` PASS（exit 0）：52 页元数据、10 个源图、
  20 个图输出、类型、生产构建及 50 条路由／内部链接检查通过。
- Stage 新计划后 `python3 tests/build/ci_change_scope_test.py` PASS：77 tests，
  包括全部 tracked paths 的显式 ownership 检查，无未分类新路径。
- 最终 committed head 分类，并运行 Task 的 `docs_static` lane；正文声明由 PR body lint
  与 `scripts/local-ci.sh --declaration-only --pr-body …` 验证。
- 本地 HTML 从已检查门户导出；MDX AST 的全部 33 张 Markdown 表格、281 条数据行、
  897 个单元格与门户及 HTML 逐一相等，所有本地章节锚点存在。
  Chromium 实页检查 PASS：搜索 SEQ SNAP 显示 5/281 条且每条匹配，清除恢复 281 条，
  Sequence 章节跳转成功；1440×1000 与 390×844 无页面横向溢出，章节标题均在固定工具栏下方，
  窄屏表格在各自容器中横向滚动。保留两种视口截图。
- 完整 Creator native/WASM/package/browser proof、DSP Core 全套、真实键盘／MIDI、
  Safari/触控/麦克风及听感、线上部署均未由此文档 Task 重跑或验收。
  历史失败和候选完整验证债务保持原状态；本次组件 PASS 不清除它们。

## Version Management

Version impact: none — 只修正文档事实与设计交付状态；不改 Product、Module、Host、
Provider、Contract 或 manifest，不分配 Build，不生成版本快照。

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-interactions/ /hosts/creator-web/ /platform/input/
Reason: 当前 Pad、Pattern 切换、监听/history 状态及已批准待交付行为需要同步说明。
控制台布局和架构边界不变，现有源图无需变更。

## Pitfall Impact

Pitfall impact: none — 本次修正文档与可从源码/测试读取的交互事实，没有新增
非产品代码可推导的过程缺陷或新 gate；不增加重复的 ledger 条目。
