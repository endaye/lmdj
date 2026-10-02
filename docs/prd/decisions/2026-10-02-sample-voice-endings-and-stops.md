# 已确认：带滤波的 voice 在 EQ 之后再做一次结尾 declick；只有 release 事件走 Pad 的 release，其余停止只用 declick

- 日期：2026-10-02
- 修订：[2026-09-30 Pad 回放与音色对齐决策](2026-09-30-sample-playback-and-tone-parity.md)的第 4 条（DSP 顺序）与第 5 条（包络与触发模式）；其余条目不变。
- 关联：#1667 的 Core 实现 [#1780](https://github.com/endaye/lmdj/pull/1780)。两轮独立审查对它的输出做了实测，Owner 在会话中确认了本文件的规则。
- 结论：
  1. **带滤波 voice 的结尾 declick 在 EQ 之后再做一次（修订第 4 条）。**
     - 问题：包络在滤波器之前，包络归零时 tone 与 EQ 仍在响。voice 若在这一帧直接关闭，输出会从约 −2 dB 跳到 0，实时与导出相同。
     - 规则：开了 tone 或 EQ 的 voice，最后 96 帧的结尾 declick（release 尾音与非循环 voice 的结尾）在 EQ 之后对输出再乘一次。voice 仍在原来那一帧结束。
     - 不变的部分：第 4 条的其余顺序不变；不开滤波的 voice 不受影响，输出逐位不变。
     - 代价：共鸣很强的 EQ 尾巴会在最后 2 ms 被淡出截断。
  2. **只有 release 事件走 Pad 的 release（澄清第 5 条）。**
     - 走 Pad release 的事件：gate / loop_gate 松开、`loop_toggle` 再次按下、Pattern 与 Performance Replay 的 note-off，以及将来的 choke。
     - 只用 2 ms declick 的停止：`stop_all`、`stop_slot`、Pattern 切换与 transport 停止、audition 停止。
     - 依据：Owner 要求"和 Koala 一致"。Koala 手册与仓库里的 Koala 调研都没有写明停止时的行为，最接近的官方说明是"要停止一个很长的 one-shot，可以双击播放键停止 sequencer"，即停止表示立即静音。
  3. **Release 从 attack 当时的电平开始（落实第 5 条）。**
     - 在长于 2 ms 的用户 attack 进行中开始的 release，从 attack 当时的电平线性淡出，release 长度不变，不会在松开后继续变响。
     - 起始电平为 0 时 voice 立即结束，不让无声尾音占用声部；这发生在按下与松开落在同一个音频回调时。
     - 不超过 2 ms 的 attack 按第 5 条等同 declick，release 开始后 declick 仍会走完，最多 2 ms 的上升。
  4. **one_shot 的 release 解析为 0（落实第 5 条）。** 第 5 条已规定 one_shot 忽略 release，所以只设置了 release 的 one_shot 仍是中性的，Cardputer 不会因此拒绝它。
- 原因：
  - 结尾 declick 的作用是防止阶跃。阶跃发生在 voice 的最终输出上，所以它对带滤波 voice 的输出也必须成立。
  - Release 表示演奏者松手，停止表示立即静音。一次停止若让尾音再响 4 秒，就和"停止"的含义相冲突。
- 影响：
  - 中性 Pad 在所有停止路径上的输出与此前逐位相同。
  - 内核 voice 的行为见 Portal `/core/modules/audio-runtime`。
  - 不改 Contract、Module 版本或 Product Build。
