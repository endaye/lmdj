# 已确认：D04 共用监听音量、独立滤波、实时 Mute/Solo 与作品电平

- 日期：2026-10-10
- 来源：owner 于 2026-10-10 分别确认 D04 MASTER、独立滤波、Mute/Solo 和
  电平表四项问答；2026-10-11 又明确确认滤波旋钮分组、完整参数录制与
  多个 Solo／Mute 优先。此前七项决定已通过 #1994 合并；同日后续问答再批准
  滤波初始值与范围、Mute/Solo 生命周期及录制起点状态、电平表显示边界。
- 结论：以下产品行为已批准；具体 Contract 设计、产品实现和验收仍待独立 Task。

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
的能力范围；历史决定保持原样。owner 明确批准以下映射：

| Perform 参数组 | ENC1 | ENC2 | ENC3 | ENC4 |
| --- | --- | --- | --- | --- |
| 主效果 | Cutoff | Delay | Reverb | 同一个设备监听音量 |
| FILTER（新增） | LP／HP／BP 类型 | Cutoff | Resonance | 同一个设备监听音量 |

已有「更多效果」组、SHIFT + ENC1–3 细调与其他页映射保持。
主效果与 FILTER 的 Cutoff 读写同一个参数，不各存一份滤波值。

独立滤波停转和切参数组保持效果，离开 Perform 时按已有 HOLD 规则释放。
类型、Cutoff、Resonance 完整随 Performance 录制和重放，不写入 Pad／工程
音色参数。不能只录制旧单值 Filter，或只重放其中一个新参数。

2026-10-11 后续批准：独立滤波初始为 OFF；默认类型 LP、Cutoff 20 kHz、
Resonance 0%。Cutoff 范围为 20 Hz–20 kHz，按对数调节；Resonance 为
0–100%。进入 FILTER 参数组本身不改变声音，不自动启用滤波。
具体事件编码和兼容策略仍须由对应 Contract／实现 Task 显式设计。

## 全部 64 个 Pad 的实时 Mute/Solo

Mute／Solo 作用于全部 64 个 Pad（A01–D16）的实时演奏状态，
作为 Performance 事件录制和重放。不修改工程内 Pad 的 `playback.muted`
参数，不把实时状态当作 authoring 保存／Undo。

允许多个 Pad 同时 Solo。只要有任一 Solo，仅放行被 Solo 的 Pad；
Mute 优先，Mute 与 Solo 同时开启的 Pad 仍静音。

2026-10-11 后续批准：切换 Bank 或 Pattern 时保持实时 Mute/Solo 状态；
离开 Perform 或切换工程时清空。Performance 同时捕获录制起点的状态及
其后的变更，重放恢复这些状态；不能只录制起点之后的按钮事件而丢失起始状态。
具体事件与重放 Contract、兼容策略仍须由对应实现 Task 明确。
不能将既有 Sample 的持久化 mute 操作当作该实时能力已经交付。

## Post-FX／Pre-ENC4 的立体声作品电平

D04 电平表显示效果处理后、ENC4 监听音量前的立体声 dBFS 峰值，
测量中排除节拍器。降低设备监听音量不会改变作品电平显示。
读数必须来自这个实际测量点，不能用触发次数、波形动画或录音期间的
PCM 批次假装常驻电平投影。

2026-10-11 后续批准：L／R 分别显示，峰值保持 1 秒；显示范围为
−60…0 dBFS，静音显示 −∞。真实读数不可用时明确显示 unavailable，
不以 0 dBFS、静音或装饰动画代替不可用状态。
峰值测量窗口、显示衰减及测量投影接口仍由对应 producer／consumer Task
明确；本次批准不指定这些细节。

## 当前来源与交付边界

最初 inspected revision: `314d1cadd8aab7504513b15a42cc96bb9c8742d8`。
2026-10-11 追加决定复查 revision：`a98ae01c4f033c78221fc961f6207c7fe5cabfd7`。
#1994 已合并决定记录；#1992 的实际 scope 是播放中 Pattern 切换及其显示，
没有交付上述 D04 producer。下列能力边界在复查 revision 仍成立。

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

本次补充已完成上述产品问答；后续声明精确文件与最低层测试，并明确 Contract
兼容设计，不能将决定记录当作实现或音频验收。
独立滤波、实时 Mute／Solo 的 producer／事件模型和 meter producer 与
Creator consumer 按实际依赖分 Task；MASTER consumer 复用已交付监听能力。
仅以上述 owner 批准的主效果＋FILTER 表扩展 Perform ENC1–3，ENC4 固定监听；
不改变其他已批准映射或现有触屏 slider release／blur 提交语义。
本决定部分解决 #1822；其他页方向键与新 SHIFT 组合键仍未决定。

## Version Management

Version impact: none — 本记录不修改 source、Contract、manifest 或 Product Build。
实际新增 DSP／事件／投影能力的兼容性与版本结算由对应实现 Task 负责。

## Documentation Impact

Documentation impact: none — 本记录仅确认 PRD 与后续工作范围，不改变当前
Architecture Portal source facts、页面或图。实际实现保留各自 Portal 更新责任。
