# 已确认：D04 共用监听音量、独立滤波、实时 Mute/Solo 与作品电平

- 日期：2026-10-10
- 来源：owner 分别确认 D04 MASTER、独立滤波、Mute/Solo 和电平表四项问答。
- 结论：以下四项是批准的产品边界；产品实现、补充设计和验收仍待独立 Task。

## MASTER 共用 ENC4 的设备监听音量

D04 的 MASTER 与 ENC4 控制同一个设备监听音量，读回同一个值。
沿用[上下文旋钮与监听音量决定](2026-10-09-contextual-encoders-and-monitor-volume.md)：
本设备记住音量，重开恢复；不写入 Project Truth 或 authoring history，
不改变录音、重采样或导出电平。监听响度仍包含节拍器。
此决定不增加第二级总音量或新的工程 master gain。

## 真正独立的滤波类型、Cutoff 与 Resonance

D04 增加真正独立的 LP／HP／BP 类型、Cutoff 和 Resonance。
现有 Filter 单值同时控制 LP／HP 深度，不能充当这三个独立参数，
Sample Tone 也不能代替它们。

本条扩展上述 2026-10-09 决定中「使用现有单值 FX、不增加独立滤波参数」
的能力范围；历史决定保持原样。已批准的 Perform 停转／切参数组保持效果、
离页按已有 HOLD 规则释放仍有效。新滤波模型所需的扩展边界须显式设计，
不从该既有规则推导尚未批准的参数存储、默认值或完整录制模型。

## 全部 64 个 Pad 的实时 Mute/Solo

Mute／Solo 作用于全部 64 个 Pad（A01–D16）的实时演奏状态，
作为 Performance 事件录制和重放。不修改工程内 Pad 的 `playback.muted`
参数，不把实时状态当作 authoring 保存／Undo。

Solo 与 Mute 同时存在时的优先级、初始化／恢复状态、离页和 HOLD 扩展边界、
具体事件与重放 Contract 仍须补齐；此次回答没有批准这些细节。
不能将既有 Sample 的持久化 mute 操作当作该实时能力已经交付。

## Post-FX／Pre-ENC4 的立体声作品电平

D04 电平表显示效果处理后、ENC4 监听音量前的立体声 dBFS 峰值，
测量中排除节拍器。降低设备监听音量不会改变作品电平显示。
读数必须来自这个实际测量点，不能用触发次数、波形动画或录音期间的
PCM 批次假装常驻电平投影。

本条没有批准峰值测量窗口、峰值保持时长、显示衰减、静音读数下限或
不可用状态的具体表现；这些是后续设计内容，不在实现中静默选择。

## 当前来源与交付边界

Inspected revision: `314d1cadd8aab7504513b15a42cc96bb9c8742d8`。
该 revision 已包含 #1929 的 BPM／D03 决定记录，没有新增 D04 产品源码。

- 已有可复用监听 producer：`runtime_types.d.ts::MonitorOutputSession` 与
  `runtime_session.mjs` 提供 `monitorVolume`／`setMonitorVolume`；App ENC4
  已绑定它并通过 `monitor_volume_preference.ts` 记住本设备音量。
  MASTER 应复用此状态和节点；无需凭「缺少 Core master gain 操作」重建监听能力。
- 独立滤波仍缺：`MasterFxChain::process_filter` 接收一个 0…1000 值，500
  bypass，其余值联合决定 LP／HP、coefficient、damping 和混合深度；
  没有独立 type／cutoff／resonance 输入或 BP 输出选择。
- 实时 Mute／Solo 及其录制／重放仍缺：Domain `PerformanceEvent` 的完整
  variant、Web `PerformanceRawEvent` 和 Host FX validator 没有这些事件。
  完整 Web bridge 操作注册表与 handler 的正向控制包括
  `performance.fx.gesture`、`performance.record.event`、`sample.update_pad`；
  这些已有操作不能接受尚未定义的实时 Mute／Solo 或独立滤波 payload。
- 常驻作品电平仍缺：`PerformOverview` 明确未渲染无投影的 meter；
  `performance_master_tap_worklet.js` 只在 capture generation 开始后发送
  PCM batch，没有上述作品测量点的常驻立体声 dBFS 峰值 API。

先补齐尚未批准的产品／Contract 边界，再声明精确文件与最低层测试。
独立滤波、实时 Mute／Solo 的 producer／事件模型和 meter producer 与
Creator consumer 按实际依赖分 Task；MASTER consumer 复用已交付监听能力。
不更改已批准 ENC1–4 映射或现有触屏 slider release／blur 提交语义。
本决定部分解决 #1822；其他页方向键、新 SHIFT 组合键和上述设计细节仍未决定。

## Version Management

Version impact: none — 本记录不修改 source、Contract、manifest 或 Product Build。
实际新增 DSP／事件／投影能力的兼容性与版本结算由对应实现 Task 负责。

## Documentation Impact

Documentation impact: none — 本记录仅确认 PRD 与后续工作范围，不改变当前
Architecture Portal source facts、页面或图。实际实现保留各自 Portal 更新责任。
