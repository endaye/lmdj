# 采集输入设备与静音门：设备选择器、输入身份可见、还是提交前电平门？

- 范围：Creator 前端（`apps/creator-web`），新内核（Playable Beat Instrument）
- 状态：待决
- 来源：2026-08-17 物理会话发现 F4（[补救计划](../../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md)「Findings out of scope」；[#214](https://github.com/endaye/lmdj/issues/214)）；决策行见 [2026-08-17-manual-verification-todo.md](../../quality/2026-08-17-manual-verification-todo.md)
- 为什么重要：`capture_controller.ts` 的 `getUserMedia` 不带 `deviceId`，采集永远跟随 OS 默认输入。当默认输入被静默切换（已观测案例：macOS Continuity 把输入改路由到附近的 iPhone）时，`getUserMedia` 成功、流携带数字静音，Creator 会把整整 5 秒静音提交到 Pad 上——无输入电平门、无静音检测、无任何提示。设备选择器的缺失是 `1.0.23.0` 在 portal `hosts/creator-web` 页上**已声明**的范围边界，所以补选择器属于扩范围决策，不是缺陷修复。F1/F2 修复（1.0.31.0）让电平表可见，缓解了「看不见」，但没有关上「静默提交」本身。
- 选项（可组合）：
  a) **提交前输入电平门**：整段 take 的峰值低于阈值时在提交前警告或拒绝。与设备无关地直接消灭「静音上 Pad」，是唯一直接关闭该缺口的选项；阈值取值需要物理数据支撑。
  b) **输入身份可见**：录制面板显示当前输入设备名（`track.label`），并监听 `devicechange` 在采集中途切换时给出提示。让 Continuity 切换可察觉，实现小，但只提示、不拦截。
  c) **完整设备选择器**：`enumerateDevices` + `deviceId` 约束。赋予操作者主动控制权，但引入权限/枚举/设备标签为空等一系列浏览器差异，且明确扩大已声明的版本边界。
  建议组合 a + b：电平门堵住提交、身份可见让切换可察觉，都不引入选择器的复杂度。
- 处理时点：F1–F3/F5 已随 1.0.31.0–1.0.33.0 落地后，这是 #214 剩余的两项之一；解决后需按
  [manual-verification-todo](../../quality/2026-08-17-manual-verification-todo.md)
  的触发表重跑「采集中途故意切换输入」的 M1 变体。
