# 已确认：BPM 旋钮即时变速保持音乐位置

- 日期：2026-10-10
- 来源：owner 对「BPM 旋钮转动时，声音立即变速应如何处理播放位置？」
  选择「保持当前小节／拍位置，继续播放」。停转 400 ms 保存／Undo 规则
  继续沿用，不重新决定。
- 解决的问题：后续计划 D2 与 #1822 的可听见 BPM preview 边界；仅有数值
  readback 不算交付。[实现计划](../../plans/2026-10-10-sequence-audible-tempo-preview.md)
  分开 Runtime、Facade/Web 与 Creator Tasks。

## 结论

1. Sequence 的 BPM 旋钮转动时立即改变实际播放速度，保持当前小节／拍的
   音乐位置继续播放，不重启 Pattern。节拍器跟随同一真实 tempo anchor，
   不能只改显示数字或另起一个与引擎不同步的 click clock。
2. 沿用[上下文旋钮决定](2026-10-09-contextual-encoders-and-monitor-volume.md)：
   preview 不写 Project Truth；最后一次转动后 400 ms 将最终值合并为一次
   authoring 保存／Undo，回到起始值不保存。
3. 离页、切 Pad／工程、打开 System、Esc、Undo／Redo 或失去目标所有权，
   取消尚未提交的 preview；恢复已提交 BPM 时仍保持当时的音乐位置继续播放。
   已发出的保存保留真实结果，不把已提交 Truth 当成可取消草稿。
4. 录音中 BPM 仍被拒绝。本决定不改变录制、重放或 Pattern 切换的时序权威。
5. 本决定仅修订 BPM **旋钮 preview** 的生效边界。
   [2026-10-02 直接调节决定](2026-10-02-creator-tempo-metronome.md) 中触屏
   slider 的 release／blur 提交、Esc／pointercancel 取消、步进与 Tap Tempo
   语义保持；不借此改成旋钮的 400 ms 提交或即时 playback preview。

## 原因

演奏中调速应延续正在进行的音乐位置；每格旋钮都重启 Pattern 会反复打断
乐句。400 ms 合并 authoring 保存，保留连续试听和一次撤销的已批准体验。

## 能力与实施边界

检查基线：`e9dae833d1c609bb203030a62053dee39b9d8b61`。
Creator `app.tsx` 仍只保留 `tempoPreview`，400 ms 后调用
`updateSequenceSettings`；Web Session、完整 Host operation 注册表及 handler
没有可逆的 tempo-preview 生命周期。Runtime 的同 BPM phase-preserving
publication 及其拒绝 changed BPM 的测试不能被放宽来冒充新能力。

#1936 已交付旋钮 consumer，#1985 和 #1990 已交付 Pattern switch 的 Web
入口及特定 generation fence 修复；它们没有实现本决定的即时 tempo preview。
#1984 仍开放，且与 Runtime 实施 Task 的源文件重叠。先交付该前置，再从其
实际 main revision 开始独立 tempo Tasks；每项仍需真实音频时序、取消、保存、
Undo 和 reopen 证据。此决策文档不宣称实现或人工听感已经验收。

## 影响

Version impact: none — 此 Task 只记录已批准产品行为与后续实施边界，不改
source、Contract、manifest 或 Product Build。实施的实际兼容性与版本债务
由各 Task 记录，在父计划 V1 结算。

Documentation impact: none — 此 Task 只改 PRD 和计划，未改变当前 Portal
页面、source facts 或 diagrams；Portal 更新随实际实现 Task 交付。
