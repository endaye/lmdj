# 已确认：Performance 回放期间允许编辑，回放按开始时的状态播放，不被编辑打扰

- 日期：2026-10-02
- 相关问题：[#1789](https://github.com/endaye/lmdj/issues/1789)。
- 依据：
  - [2026-08-28 Performance 对象决策](2026-08-28-perform-performance-object-v4.md)第 5、6 条；
  - Perform 设计（`docs/design/2026-08-28-lmdj-stage10-perform-design.md`）验收第 16 条。

## 结论

1. **编辑照常准入。** Performance 回放进行时，Project 编辑照常准入并写入 Project Truth，包括：
   - Sequence 网格的 `pattern.events.edit`；
   - Pad 的 Sample 与播放设置；
   - BPM、Swing 等 Sequence 设置。

   不因回放而拒绝，也不自动停止回放。
2. **本次回放听到的内容不变。** 回放按 begin 时固定的 resolved revision 播放（设计验收第 16 条：中途 Project 变更不改变本次 resolved revision）。回放期间的编辑不改变这次回放的 Pattern、Pad 声音与速度。
3. **Runtime 不覆盖回放。** 回放期间，编辑提交后不能把选中 Pattern 的视图或新的 Bank 发布进引擎、覆盖回放正在使用的 Runtime 状态。回放结束（停止、播完或中止）后，Runtime 按当前 Truth 恢复选中 Pattern。
4. **不变的部分：**
   - 录音中的准入规则（`sequence_session_active`、`performance_session_active`）不变；
   - 回放按当前 Project 回放、不做指纹门控的既有决策不变：换过的采样在下一次回放里出新声音。

## 原因

- **Koala 没有可以照搬的行为。** Koala 没有事件级的演奏录制与回放；它的 Record a Song（手册 §6.2）只产出音频（2026-08-28 决策第 6 条）。最接近的 Koala 体验是一边播放录好的歌一边改 Sequence：歌的声音不随编辑变化。本条按此对位，依据 [2026-09-29 Creator 用户流程决策](2026-09-29-creator-user-workflow-baseline.md)第 1 条“先对齐 Koala”。
- **既有设计已经这样设想。** 设计验收第 16 条已经把 resolved revision 固定在 begin 时，即回放期间的 Project 变更本来就被设想为允许的，只是 Host 的发布路径（#1789 所述）会覆盖回放的视图。
- **owner 于 2026-10-02 选择了本方案**，没有选择以下两种备选，它们的问题是：
  - 回放期间拒绝编辑，会打断“边听边改”；
  - 编辑时自动停止回放，会让用户意外丢失正在听的演奏。

## 影响

- **实现 Task**，排在 #1792 之后：
  - Web Runtime Platform 在回放进行时，不让编辑提交后的 Pattern 视图与 Bank 发布覆盖回放的 Runtime 状态，并在回放结束时按 Truth 恢复；
  - Facade 准入不变；
  - 回归测试覆盖网格编辑、Pad 编辑与 BPM 修改各一种；
  - 门户 `/hosts/creator-web/` 与 Web Runtime Platform 模块页随实现更新；
  - 版本按实现时的实际改动支付。
- **不涉及 Contract 改动。**
- 本决策关闭 #1789 的产品问题部分，实现仍在该 Issue 下跟踪。
