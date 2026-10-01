# 已确认：Sequence 网格编辑的首版范围、布局与播放中编辑

- 日期：2026-10-02
- 解决的问题：[#1671](https://github.com/endaye/lmdj/issues/1671) 实施前需要确定的产品问题（布局、首版范围、播放中能否编辑）。#1671 本身由实施 Task 关闭。
- 依据：[Creator workflow baseline](2026-09-29-creator-user-workflow-baseline.md) 第 1、8 项；[Creator 用户操作流程](../../design/2026-09-29-creator-user-workflow-design.md) §6；[Undo/Redo 语义](2026-09-30-creator-undo-redo-semantics.md) §3、§4；[Sequence 录音语义](2026-08-23-sequence-recording-semantics.md) 第 3 项；Koala 业务流程调研 Q19–Q25（`docs/research/2026-07-28-koala-sampler-business-flows.md`）。

## 结论

1. **网格位置与布局。** 网格放在 Sequence 模式的触控区，不是上屏。
   - 行是当前 Bank 的 16 个 Pad，用现有 Bank 键切换。
   - 横轴是整个 Pattern（1、2、4 或 8 小节），可横向滚动。
   - 吸附默认 1/16，可选 1/4、1/8、1/16、1/32 和关。
2. **上屏仍然只读，改为整个 Pattern 的总览。** 内容包括：
   - 4 个 Bank 共 64 行的缩略图；
   - 实时播放头；
   - 标出触控区当前显示范围（Bank 与时间）的框；
   - 保留现有的 Quantize、Swing、小节数与状态；
   - 增加选中信息：选中音符数、吸附精度、力度。
3. **首版编辑。**
   - 用笔点增加或删除音符。
   - 拖动改变位置与长度。
   - 调整力度。
   - 框选后批量删除或移动。
   - 一次手势，或一次批量操作，是一条撤销记录；拖回原位不产生记录（Undo/Redo 语义 §4）。
4. **播放中允许编辑，从下一小节生效。**
   - 只播放、未录音时，编辑照常提交。若被编辑的是正在播放的 Pattern，新内容从下一小节开始播放，沿用播放中修改 BPM 的发布方式。
   - 录音中编辑被拒绝，沿用 Sequence 录音语义第 3 项。
   - 撤销与重做仍需先 Stop，沿用 Undo/Redo 语义的现有规则，本决策不改变它。
5. **不改 Contract。**
   - `lmdj.project.v5` 的 Pattern 事件已经有 `duration_tick`，现有的事件键 `(bank, pad, onset_tick)`、"后写覆盖"与不跨循环接缝的规则保持不变。
   - 增删、移动、改长度、改力度都能在 v5 内表达。
   - 需要新增的只是内部 Authoring Command 与 Host 操作。
6. **不在首版。**
   - DICE 概率：需要改 Contract。
   - Legato、Reverse、Stretch、Repeat、Double Up。
   - 复制与粘贴。
   - 超出 Pad 行的音高 piano roll。
   - 这些各由后续 Task 处理。

## 原因

- 基线决策第 8 项把网格编辑列为 Sequence 的高优先级缺口，第 1 项要求先对齐 Koala。
- Koala 的 Piano Roll 支持笔点增删、拖动、力度、吸附与框选批量编辑。边循环边改是它的主要工作方式，所以播放中应当允许编辑。
- 触控区一次只放得下一个 Bank 的 16 行，用上屏补上全局视野。这样也兑现了上屏原有的"事件网格只读投影"预留，上屏仍不承担编辑。
- 首版限定在不需要改 Contract 的编辑，减小风险；其余批量操作随后续 Task 增量交付。

## 影响

- **Core。** Authoring Domain 与 Project I/O 新增一个原子的事件编辑命令（按键删除加按键放入，一次提交），自动进入会话历史。Application Facade 与 Web Runtime Platform 新增对应 Host 操作；播放中编辑正在播放的 Pattern 时，在下一小节发布。
- **Creator。** 项目视图保留 Pattern 事件；新增触控区网格与上屏总览；每次手势结束时提交一次编辑。
- **版本。** 上述模块都欠一个 MINOR，并入下一次协调版本切点（在 #1741 计划的 2.0.71.0 之后）。不涉及 Contract SemVer。
- **门户。** 受影响的模块页与 `/hosts/creator-web/` 随各实施 Task 更新。
