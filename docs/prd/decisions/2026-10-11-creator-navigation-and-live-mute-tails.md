# Creator 其余页面导航与 live Mute/Solo 共享尾音

- 日期：2026-10-11
- 状态：owner 已批准；导航和声音 producer 的实施、验证与验收待独立 Task。
- 来源：owner 分别采用「采用这套映射」和「保留已产生的尾音自然衰减」。
  导航问答的完整结尾包括 SHIFT + ←/→ 撤销／重做、SHIFT + ENC1–3 细调、
  SHIFT + ↑/↓ 暂不分配；不以回答界面的截断文本缩小批准范围。
- 初始 inspected revision：`5d31f21bb7b5f91014881c05b0ef7f4708c03b29`；
  本 Task 保留七文件草稿后，快进整合并复查实际 main
  `1e9a90c1055c8fc5c5df3fa878dda416b1d00a20`。
- 关联：[#1822](https://github.com/endaye/lmdj/issues/1822)、
  [上下文旋钮与监听](2026-10-09-contextual-encoders-and-monitor-volume.md)、
  [D04 实时控制](2026-10-10-mixer-live-controls-and-meter.md)、
  [后续计划](../../plans/2026-10-09-creator-desktop-final-followup.md)。

## 已批准的导航

| 页面 | ← / → | ↑ / ↓ |
| --- | --- | --- |
| Project | 选择左右相邻工程 | 在三列列表中上下移一行 |
| Sample | 切 Trim、Playback、Tone/EQ、Pad 子页 | 与 Sequence 一样选择上一／下一 Pad |
| Perform | 切 PRIMARY、FILTER、MORE 效果组，保持效果声音 | 与 Sequence 一样选择上一／下一 Pad |

Project 只改变选择，明确按 OPEN 才打开。Sample／Perform 的 Pad 导航沿用
Sequence 的 A01–D16 顺序与边界，不触发 Pad、不写 Project Truth；切编辑
上下文按已批准规则取消未提交的 400 ms 预览，已发出的提交保留真实结果。
Perform 切组保持声音，离页继续按已有 HOLD 规则释放。

SHIFT + ←/→ 继续全局 Undo／Redo，不同时执行普通方向导航。
SHIFT + ENC1–3 继续细调；SHIFT + ↑/↓ 暂不分配新功能。
本次不批准 SHIFT 的瞬时／粘滞方式、SHIFT + Pad、SHIFT + Play 或
SHIFT + Record 提案。四排键盘映射沿用其[独立决定](2026-10-11-creator-keyboard-spatial-mapping.md)，
与这四个方向控件的导航分开实施。

## 已批准的 live Mute/Solo 尾音

立即阻断对应 Pad 当前和后续的声音输入。已经进入共享 Delay／Reverb 的
尾音自然衰减；其他 Pad 的效果继续。不扩大为每 Pad 独立效果发送或尾音隔离，
不能静音或清空整条共享总线来冒充对应 Pad 的门控。

既有 D04 约束保持：全部 64 Pad、多个 Solo、Mute 优先；不修改 Pad muted
Truth；切 Bank／Pattern 保持，离 Perform／切工程清空；Performance 记录
起点状态和后续变更并在重放恢复。ENC4、独立滤波默认值、HOLD 和 meter
规则不变。

该批准解决共享尾音的产品选择，不批准具体 ramp 长度或额外输入宽限。
编码提案中的 96-frame ramp、cursor／解除门控实现仍属工程设计；M1 必须
证明它满足立即阻断当前／后续输入及自然共享尾音的已批准要求，不能把
96 帧当作 owner 批准的 grace period。

## 当前能力与实施边界

当前 App 仅给 Sequence 接入普通方向导航；Project 的选择、Sample 的
四个子页和 Perform 的 PRIMARY／MORE 切组可复用，但不构成新增三页方向
接线。Perform 的 FILTER 组还依赖真实独立滤波 producer／consumer；不渲染
假参数组来声称已完成。现有 DSP 也尚无 live Mute/Solo mask producer。

刷新 main 已包含 #2000 的 MASTER consumer（`116280f9209245b4757a814fcf3155002b025269`），
直接复用该交付；其完整 committed-head Creator 仍 pending，不借 merge 当作
验收通过。#2005 的 S0／S1 版本治理也已合入，Deploy Contract 实际失败仍
保持未完成。本 Task 不分配身份／Build，不属于 allocation cut，不适用
S0 的特殊 source checkpoint；仍须完成本 Task 的原完整 Portal 校验。

K2 在 K1 与有关 App／Sample／Perform Task 的实际 main 集成后声明精确
文件和最低层测试。M1 依赖 F1 实际合并，并与 F1／BPM 等 engine owner 顺序
集成；它只解除本次尾音问答卡点，不借前置 Task 的测试结果。后续边界见
[producer 计划](../../plans/2026-10-11-performance-live-control-producers.md)。

旧记录中「其他页方向键未决定」「共享尾音 pending」是其当时状态，本决定
只替代这两项未决前提，不重写历史提案、R1–R6 技术审阅或工程证据。
#1822 仍有未批准的其他 SHIFT 提案；本记录不关闭 Issue、不宣称实现、
A1/A2、V1、设备听音或整个 Goal 完成。

## Version Management

Version impact: none — 仅记录批准，不改产品源码、Contract、active manifest、
ABI 或 Build；未来实现的实际版本债务由各 Task 记录并在 V1 结算。

## Documentation Impact

Documentation impact: required
Affected portal pages: `/platform/input/`、`/hosts/creator-interactions/`。
只同步已批准／实现待完成的状态和决定链接，不把未来能力写成已交付。
