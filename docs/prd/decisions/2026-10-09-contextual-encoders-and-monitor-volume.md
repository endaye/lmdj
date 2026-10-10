# 已确认：三个页面旋钮与固定监听音量

- 日期：2026-10-09
- 来源：owner 对推荐表回复「行，按你的设计来！」，随后分别确认 400 ms、
  本设备音量记忆和 Perform 效果保持。
- 结论：ENC1–3 随当前页面/参数组变化，右下 ENC4 始终控制监听输出音量。

| 页面/参数组 | ENC1 | ENC2 | ENC3 | ENC4 |
| --- | --- | --- | --- | --- |
| Project | 选择项目 | 滚动项目列表 | 未分配 | 输出音量 |
| Sample / 剪辑 | 播放起点 | 播放终点 | 音高 | 输出音量 |
| Sample / 音色 | 当前 Pad 音量 | 声像 | Tone | 输出音量 |
| Sequence | 横向滚动小节 | 上屏滚动 Pad 行 | BPM | 输出音量 |
| Perform / 主效果 | Filter | Delay | Reverb | 输出音量 |
| Perform / 更多效果 | Crush | Stutter | Gate | 输出音量 |
| System | 未分配 | 未分配 | 未分配 | 输出音量 |

- Sample 与 Perform 参数组通过触屏切换；上屏始终显示当前旋钮名称与值。
  Project 的旋钮只选择项目，OPEN 仍是打开动作。Sequence 的 Swing 保留在
  SETUP 触屏；已交付的横向/行滚动、当前 Pad 与 Pattern 导航保持。
- SHIFT + ENC1–3 细调，SHIFT + ←/→ 继续 Undo/Redo；ENC4 不获得第二功能。
  本决定替代之前「上排统一视图」「SHIFT 粗调」的原则，并修改
  [Sequence 硬件决定](2026-10-04-sequence-hardware-ui-revision.md) 的 ENC4。
  [Sequence 当前 Pad 决定](2026-10-09-sequence-view-and-pad-navigation.md)
  中已交付的导航边界继续有效。
- 工程参数（Sample、BPM）每格立即预览，最后一次转动后 400 ms 合并为
  一次 authoring 保存/Undo；回到起点不保存。离页、切 Pad/Project、打开
  System、Esc 或 Undo/Redo 前，取消未提交预览；已发出的请求保留真实结果，
  不把已提交 Truth 当成可取消的本地草稿。
- Perform 停转和切参数组保持效果；离开 Perform 时按已有 HOLD 规则释放。
  使用现有单值 FX，不由本决定增加独立 cutoff/resonance 或滤波类型。
- ENC4 只改变最终监听响度，包括节拍器；不改变录音/重采样/导出的 PCM，
  不写入 Project Truth 或 authoring history。在本设备记住音量，重开恢复；
  正常图与录音 tap 失败后的恢复图都必须经过同一监听音量节点。
- 影响：部分解决 #1822 与后续计划 D2。其他页方向键、D03 Assign、D04
  独立滤波/Mute/Solo/meter 仍是未完成范围；不从本次批准推导它们的语义。
  先交付 Web 监听输出 producer，再交付 Creator 控件 consumer。
