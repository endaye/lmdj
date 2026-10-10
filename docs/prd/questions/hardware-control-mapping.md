# 各页剩余方向键与扩展控件怎样分配？

- 范围：Creator
- GitHub Issue: #1822
- 已确认：[2026-10-09 上下文旋钮和监听音量](../decisions/2026-10-09-contextual-encoders-and-monitor-volume.md) 分配了 Project、Sample、Sequence、Perform 和 System 的四个旋钮。ENC4 固定为设备监听输出音量；SHIFT + ENC1–3 细调；上屏持续显示当前功能和值。原来的「旋钮 1/2 管视图、3/4 管数值、SHIFT 粗调」提案已被该决定替代。
- Sequence 的 ENC1 横向小节滚动、↑/↓ 当前 Pad 导航，以及既有 ←/→ Pattern 导航已交付；跨 Bank 导航保留音符选择，不发声、不改 Project Truth。
- 仍待决定：Project、Sample、Perform 页的普通方向键行为，以及 Assign、独立滤波类型/细调、Mute/Solo 等扩展控制。SHIFT + ←/→ 沿用全局撤销/重做。
- 处理时点：在给这些剩余控件分配新行为前，由 owner 确认。不重复实现已确认的旋钮或 Sequence 导航。
