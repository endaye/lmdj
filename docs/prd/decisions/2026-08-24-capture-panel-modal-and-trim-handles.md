# 已确认：Capture 面板改为视口锚定的模态会话，Trim 手柄改为可见握把 + 中点划界的指针模型

- 日期：2026-08-24
- 结论：落地 Creator 补救计划
  [`2026-08-17-lmdj-creator-capture-ui-remediation.md`](../../plans/2026-08-17-lmdj-creator-capture-ui-remediation.md)
  Task 1 的设计门（P2）。四条子决策：P2-D1 Capture 面板从 Sample 面板
  末尾的流式元素改为视口锚定的模态对话框，固定几何，进入 `recording`
  不改变外框；P2-D2 焦点随各阶段主操作走，关闭时恢复既有
  `returnFocus` 契约；P2-D3 Trim 手柄废弃两个叠放的隐形全宽
  `input[type=range]` 指针路径，改为「可见握把即命中区、两柄中点划界、
  拖动保留抓取偏移、波形中段对 trim 惰性」的指针模型；P2-D4
  `DUPLICATE_ID` 从 fatal 呈现改为可恢复呈现并给出 `Open local
  Project` 恢复控件。
- 原因：2026-08-17 物理会话证明（F1/F2/F3/F5，见计划原文）：面板无
  样式、开在首屏之下且随 recording 向下增长；Trim 手柄的命中带与视觉
  指示错位且误触具有破坏性。Koala Sampler 对同一问题的成熟解法是直接
  参照：录制是全屏模态会话（一次只做一件事，大波形 + 主操作固定在
  底部），采样编辑屏的 trim 手柄是宽大的可见竖条、所见即所抓，波形
  主体从不因点击而移动 trim 点。
- 影响：解锁补救计划 Task 2–4（F1、F2、F3、F5），即
  `docs/quality/2026-08-17-machine-task-todo.md` 中 "blocked on P2"
  的全部条目；`docs/quality/2026-08-17-manual-verification-todo.md`
  的 P2 决策行就此关闭。F4（设备选择 / 输入可见性 / 提交前输入电平
  门）与 F6（渲染路径振幅斜坡，需 realtime-safety 评审）不在本条决策
  内，仍为待人工决策项。本条由项目负责人口头确认，代理记录——与
  P2 行注明的 "a person decides, the agent records" 一致。

## P2-D1 Capture 面板呈现：视口锚定模态对话框

- 面板以原生 `<dialog>` + `showModal()` 呈现，复用
  `ConfirmationDialog` 已验证的机制：背景 `inert` + `aria-hidden`、
  遮罩、`returnFocus`。录制在 Koala 中是一个模态会话；在 Creator
  桌面 Web 上同理——录制中操作者唯一的工作是看电平与按 Stop，模态
  使面板及其主操作**构造上**必然在视口内，不再依赖 Pad grid 的高度，
  也不需要 scroll-into-view 机制。
- 固定几何：宽度 `min(44rem, calc(100vw - 2rem))`，最大高度
  `calc(100dvh - 2rem)`，内部滚动。内部三个固定区域：
  1. Header——标题 + `Close`（所有阶段均在）；
  2. 波形/电平区——固定高度；`idle` 显示就绪占位，`recording` 显示
     实时增长的波形与电平表，`trimming` 显示完整波形与选区；
  3. 操作行——固定底部：`idle` 为 `Record into Pad N`，`recording`
     为同一位置的 `Stop`，`trimming` 为 `Crop to selection` /
     `Commit` / `Discard`。
- 进入 `recording` 时各区域只换内容、不改外框尺寸，因此 `Stop` 相对
  操作者的位置与 `Record into Pad N` 一致——无任何东西会中途跌出
  首屏（F1/F2 的直接根因）。
- 否决的备选：流内面板 + scroll-into-view（位置仍依赖 grid 高度，且
  把「面板在哪」变成需要滚动管理的状态）；Sample 面板常驻固定区域
  （为偶发任务永久占位）。

## P2-D2 焦点行为

- 打开：焦点移到当前阶段主操作（`idle` 时为 `Record into Pad N`）。
- 阶段切换：若焦点所在的控件随阶段切换被卸载（如点击 Record 后进入
  `recording`），焦点转移到新阶段的主操作（`recording` → `Stop`，
  `trimming` → `Commit`），不回落到 `<body>`；焦点不在被卸载控件上
  时不主动移动。
- 关闭：任何阶段（含 `recording`）都可用 `Close` / `Escape` 关闭；
  关闭前停止进行中的录制（沿用 `capture_panel.tsx` 现有
  `handleClose` 语义与单所有者生命周期，不改 blur/hidden 停止语义）。
  关闭后恢复既有 `returnFocus` 契约：回到发起按钮，失效时回退到
  遮罩外第一个可聚焦元素（`restoreConfirmationFocus` 的现有行为）。

## P2-D3 Trim 指针模型：可见握把 + 中点划界

- **可见即所抓**：每条 handle 线渲染为可见握把——加宽竖条（视觉
  ≥12px）加顶端/底端 grip 指示（Koala 编辑屏式样）。命中区以 handle
  线为中心、总宽 ≥24px，覆盖握把两侧的触控余量。只有握把上才显示
  `ew-resize` 光标与 hover 态，可预测、可学习。
- **命中区不重叠**：两柄命中区以两条 handle 线的中点为界划分，各自
  不越过中点。两值相邻时各区缩为间距的一半——恒非零且由中点规则唯
  一消歧，因此任意缩放级别下两柄都独立可达；放大即恢复完整命中区。
- **按下与拖动**：握把内按下即抓住该柄；拖动保留按下瞬间的抓取偏
  移（handle 跟随指针增量，绝不跳到指针位置）。`pointercancel` /
  `Escape` 取消手势并还原原值（沿用现有 `cancelGesture` 语义）。
- **中段惰性**：波形主体（两柄命中区之外）按下不移动任何 trim 点。
  这替代了原来「中段是死区」与「误触跳变」两个互为表里的缺陷：现在
  中段什么都不做，而握把永远做你指着的那件事。中段未来可留给
  pan/scrub，本 Task 不实现。
- **禁止跳变**：任何按下都不得把 trim 点跳到点击的轨道位置——原生
  range input 的 jump-to-click 行为随指针路径一起废弃。
- **无障碍与键盘路径原样保留**：两个 `input[type=range]` 继续作为
  键盘 / 辅助技术通道，带实时秒值的 accessible name、方向键微调、
  Shift 粗调、`Escape` 取消全部不变；它们移出指针路径
  （`pointer-events: none` 并视觉隐藏），指针交互由单一 overlay 层
  按中点规则映射到最近 handle，驱动与现有代码相同的
  begin/preview/commit 手势函数。数值输入框路径同样不变。

## P2-D4 `DUPLICATE_ID` 可恢复呈现

- 不再归入 fatal 的 `Creator unavailable` 标题。标题命名真实情形
  （本地已存在该 Project 且本地副本更新），正文说明无数据丢失、导入
  被拒绝是因为本地 Project 已分叉。
- 给出恢复控件 `Open local Project`，走与现有 `Open local` 相同的
  路径打开分叉后的本地 Project，无需 reload。
- 其他错误码的呈现不变（计划 Task 4 的验证要求保持不变）。

## 参照

- Koala Sampler（elf audio）：录制屏为全屏模态会话，主操作（大红色
  Record/Stop）固定于底部；采样编辑屏 trim 手柄为贯穿波形全高的
  宽大可见竖条，命中目标与视觉指示合一，点击波形主体从不移动 trim
  点。本条决策是这两个模式向 Creator 桌面 Web 形态的映射，而非像素
  级复刻。
