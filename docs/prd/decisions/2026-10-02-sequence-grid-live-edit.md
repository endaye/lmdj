# 已确认（勘误）：播放中编辑网格立即原地生效，不跳回 Pattern 开头

- 日期：2026-10-02
- 替代：[2026-10-02 Sequence 网格编辑决策](2026-10-02-sequence-grid-editing.md)第 4 项"播放中允许编辑，从下一小节生效"的生效方式。该决策的其余各项不变，原文件不回改。
- 相关问题：[#1671](https://github.com/endaye/lmdj/issues/1671)。

## 结论

1. **只播放、未录音时，编辑正在播放的 Pattern：** 提交后立即在原位替换它的 Runtime 视图。
   - 播放位置不变，不会重新从第 1 小节开始。
   - 正在发声的音不被打断。
   - 播放头之后、本圈尚未播放的新音符，本圈就能听到。
2. **停止时编辑当前 Pattern：** 提交后立即替换，不等到小节边界。下一次 Play 不会因为有待生效的发布而被拒绝。
3. **编辑不是 Runtime 当前 Pattern 的 Pattern：** 只改 Project Truth。那个 Pattern 在被选中时，按 Truth 准备视图。
4. **不变的部分：**
   - 录音中拒绝编辑；
   - Pattern transport 命令进行中（含待结算的发布）时，提交前拒绝，可以重试。待结算的发布包括播放中修改 BPM、Sequence 切换和 reload 排到下一小节的替换；
   - 撤销与重做仍需先 Stop。
5. **引擎 Pattern 槽位已满时，照常提交，空出后自动补上替换。**
   - 原位替换时，旧视图要等它的音响完才释放槽位。播放中对长音色快速连续编辑，4 个槽位可能都被这样的旧视图占住。
   - 这时编辑照常写入 Project Truth，替换延后（`publication: "deferred"`）。
   - Runtime 在槽位空出后，按 Truth 自动原位替换，播放位置仍不变。之后的编辑或任何其他 Pattern 发布都会取代这次延后。
   - 代价：这次改动最多晚一个长音的时长才能听到。
   - owner 于 2026-10-02 在"照常提交并自动补上""提交前拒绝、可以重试""维持现状交给 T3"三者中选择了第一种，理由是与 Koala 一致：播放中编辑从不被拒绝。

## 原因

- 原决策的推荐理由是"沿用播放中修改 BPM 的发布方式"。实施时核对引擎（`packages/audio-runtime/src/realtime_engine.cpp` 的 `apply_published_pattern`）发现，这条路径在下一小节切换时，会停止 Pattern 的发声，并把 Pattern 原点重置到切换帧。
- 结果是：在多小节 Pattern 的中途编辑，播放会在下一小节跳回第 1 小节。这与原决策"新内容从下一小节开始播放"的本意不符，也破坏了"边循环边改"。
- 引擎已有保相位替换 `publish_pattern_view_preserving_phase`。它要求 Project、Pattern、BPM、PPQ 与循环长度相同；事件编辑恰好只改变事件。它保留原点，保留持续中的 Voice，并把事件游标定位到当前相位后第一个尚未调度的事件。
- owner 于 2026-10-02 在三种方案中选择"立即生效，播放位置不变"：
  - 维持下一小节切换并接受跳回开头；
  - 立即生效，播放位置不变；
  - 为引擎新增"按小节调度且保留相位"。

## 影响

- **Web Runtime Platform。** `pattern.events.edit` 播放中走保相位替换，停止时走立即替换。两者都只发布 Pattern 视图，不重做 Bank。槽位已满时延后替换，由 transport service 节拍在槽位空出后重试。响应以 `publication`（`none`、`published`、`live`、`deferred`、`failed`）与 `pattern_publication` 表示结果。
- **不涉及 Contract 与 Audio Runtime 的代码改动。**
- **门户 `/product/workflows/`** 中网格编辑的已确认说明随实施 Task 更新。
