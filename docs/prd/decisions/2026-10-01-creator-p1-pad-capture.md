# 已确认：空 Pad 按下即录音，录音所有者互斥

- 日期：2026-10-01
- 结论：空 Pad 的真实指针或键盘按下立即录入记忆的麦克风或内部 post-FX master 音源，松手封口并提交。没有长按延迟。首次麦克风授权只准备设备，下一次按下才录音；MIDI Note 不发起麦克风授权。
- 原因：P1 首次使用应沿用演奏动作完成素材采集，同时避免授权等待后出现意外录音。
- 影响：Capture、Pattern Record、Perform Record 互斥；Sequence 播放可继续。取消、失焦、导航和 60 秒上限只封口，释放资源并保留显式 Save/Discard 素材。仅裁去开头严格数字零，静音拒绝提交。冲突保留原素材，显式重试仅允许原 Project 中仍为空的 Pad。使用已有 Facade 素材导入路径及 Undo，不向 Project Truth 写入音源偏好或浏览器权限。
- 替代：Perform 手动帧区间 resample UI 由空 Pad 的内部回放录音替代，保存后的 Performance replay 保留。此前 [Stage 8B Capture 设计](../../design/2026-08-15-lmdj-stage8b-pad-capture-design.md) 的传统 Sample Capture 编辑流程继续可用，但遵守上述录音所有者互斥规则。
