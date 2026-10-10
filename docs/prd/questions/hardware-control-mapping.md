# 各页剩余方向键与扩展控件怎样分配？

- 范围：Creator
- GitHub Issue: #1822
- 已确认：[2026-10-09 上下文旋钮和监听音量](../decisions/2026-10-09-contextual-encoders-and-monitor-volume.md) 分配了 Project、Sample、Sequence、Perform 和 System 的四个旋钮。ENC4 固定为设备监听输出音量；SHIFT + ENC1–3 细调；上屏持续显示当前功能和值。原来的「旋钮 1/2 管视图、3/4 管数值、SHIFT 粗调」提案已被该决定替代。
- Sequence 的 ENC1 横向小节滚动、↑/↓ 当前 Pad 导航，以及既有 ←/→ Pattern 导航已交付；跨 Bank 导航保留音符选择，不发声、不改 Project Truth。
- 已确认：[2026-10-10 BPM 旋钮即时变速](../decisions/2026-10-10-sequence-audible-tempo-preview.md) 保持当前音乐位置，沿用 400 ms 保存／Undo；[Sample Assign 与精确数值编辑](../decisions/2026-10-10-sample-assign-and-numeric-editing.md) 使用当前工程已有素材、明确 A01–D16 目标，以及试听后 Apply／Enter 一次保存。决定已记录，实施与验收仍待完成。
- 仍待决定：Project、Sample、Perform 页的普通方向键行为，以及 D04 MASTER、独立滤波类型／参数、Mute/Solo 和 meter 等扩展控制；新增 SHIFT 组合键也需单独确认。SHIFT + ←/→ 沿用全局撤销/重做，已批准旋钮细调不重新决定。
- 处理时点：在给这些剩余控件分配新行为前，由 owner 确认。不重复实现已确认的旋钮或 Sequence 导航。
