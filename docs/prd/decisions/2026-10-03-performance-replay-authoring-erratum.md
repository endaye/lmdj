# 已确认（勘误）：回放期间只暂缓 Pattern 视图，Bank 照常发布；编辑 Pad 只停现场声音

- 日期：2026-10-03
- 替代：[2026-10-02 回放期间编辑决策](2026-10-02-performance-replay-authoring.md)第 3 条中“新的 Bank”的部分。其余各条不变，原文件不回改。
- 相关问题：[#1789](https://github.com/endaye/lmdj/issues/1789)。

## 结论

1. **Bank 照常发布。** 回放期间，编辑提交后照常发布新的 Bank；只暂缓 Pattern 视图的发布。
   - 回放的 Pad 击打与 Pattern 声音都带着自己的采样数据，不读引擎 Bank，所以新 Bank 不改变回放听到的声音。
   - 现场按 Pad 与试听立即听到 Truth。
2. **编辑 Pad 只停现场声音。** 回放期间编辑或删除 Pad 时，只停止该 Pad 的现场声音；回放发出的击打与回放启动的 Pattern 声音继续发声。
   - 引擎为此新增 `stop_slot_live` 停止命令，只作用于来源为现场输入、且不是 Pattern 声音的 voice。
   - 不在回放时，Pad 编辑的停止行为不变。
3. **恢复时机。** 回放结束（停止、播完或中止）后，Runtime 按当前 Truth 恢复选中的 Pattern：
   - transport 播放中，在下一小节恢复，与切换 Pattern 的时机相同；
   - 否则立即恢复。
4. **不在本决策范围。** 回放期间的 Pattern transport 命令（Play/Stop、Record）仍会作用于或替换回放的 Pattern 视图，由 [#1801](https://github.com/endaye/lmdj/issues/1801) 跟踪，等 owner 决定。

## 原因

- 实施 #1789 时核对代码发现两点：
  - 回放的声音从不读取引擎 Bank，原决策“不发布新的 Bank”对回放没有保护作用，反而会让现场按 Pad 在回放期间听不到新采样，并需要在回放结束后再发布一次 Bank、等待音频确认。
  - Pad 编辑原本发出的 `stop_slot` 会停掉该 Pad 上所有非试听声音，包括回放的击打，违反“回放不受影响”和回放设计 RLC-D6。
- owner 于 2026-10-03 确认：
  - Bank 照常发布；
  - 编辑 Pad 只停现场声音，不动回放的声音；
  - 回放期间的 transport 命令另开 Issue（#1801）。

## 影响

- **Audio Runtime：** 新增 `stop_slot_live`，属新增能力（MINOR）。
- **Web Runtime Platform：**
  - 跟踪本 Host 开始的回放；
  - 回放期间暂缓 Pattern 视图发布，并以 `stop_slot_live` 停止 Pad；
  - 回放结束后在 service 节拍里恢复选中的 Pattern。
- **门户：** Audio Runtime、Web Runtime Platform 模块页与 `/hosts/creator-web/` 随实施更新。
- **不涉及 Contract 改动。**
