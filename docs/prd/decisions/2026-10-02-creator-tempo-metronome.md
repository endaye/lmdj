# 已确认：Tempo/Swing 直接调节、Tap Tempo 与节拍器（#1672）

- 日期：2026-10-02
- 解决的问题：[#1672](https://github.com/endaye/lmdj/issues/1672) 实施前需要确定的产品问题：直接调节的手势模型与提交粒度、生效边界、录音中行为、Swing 语义、节拍器的状态归属与混音路由。#1672 本身由实施 Task 关闭。
- 依据：[Creator workflow baseline](2026-09-29-creator-user-workflow-baseline.md) 第 1、3 项；[Creator 用户操作流程](../../design/2026-09-29-creator-user-workflow-design.md) §6；[Sequence 录音语义](2026-08-23-sequence-recording-semantics.md) 第 3 项与 Quantize/Swing 录入烘焙决策；[长素材与 BPM Stretch 决策](2026-08-26-long-material-quota-and-bpm-stretch.md)（节拍器是 BPM 消费者）；Koala 业务流程调研 Q5、Q7（`docs/research/2026-07-28-koala-sampler-business-flows.md`）；[Undo/Redo 语义](2026-09-30-creator-undo-redo-semantics.md) §4。

## 结论

1. **手势模型：拖动只预览，结束才提交一次。** 沿用已交付的 Sample 参数推子手势（`parameter_slider.tsx`）：拖动只更新本地读数，不产生任何 Host 写入；松手（pointer up、任何能移动 range 的键抬起、blur）且值有变化时提交一次 `sequence.settings.update`；Escape 或 pointercancel 取消并还原。一次手势 = 一个 revision = 一条撤销记录；拖回原值不提交（Undo/Redo 语义 §4）。Sequence 设置不再有 Apply 按钮。
2. **步进与 Tap Tempo。** TEMPO 卡提供 −/+ 步进（±1 BPM，每次点击即一次提交）与 TAP：连续点击按最近若干次间隔（至多 4 个）的中位数换算 BPM，取整并夹取到 40–240 后立即提交；超过 2 秒未点击则重新起链。SWING 卡提供同样的拖动与 ±1 步进（50–75%）。这与 Koala 5.3 的拖动、tap、加减对齐。
3. **生效边界（文档化）。** 停止态改动立即生效。播放中改 BPM 沿用引擎现有行为：当前 Pattern 重新发布，从下一小节边界生效（响应已带 `pattern_publication.activation_frame`）。播放中改 Swing/Quantize 立即成为之后录入事件的烘焙参数。这满足 #1672「立即或在文档化边界可闻」的验收。
4. **Swing 语义不变。** 沿用 2026-08-23 决策：Swing 在录入时破坏性烘焙进之后的新事件，不改变已录事件的播放律动。Koala 的 Swing 是播放律动（调研 Q5），与既有决策不同，记为显式偏差；引入播放 Swing 需要 runtime-content Contract 与 audio-runtime 改动，不在本 Task。
5. **录音中：Tempo/Swing/Quantize 仍被拒绝，节拍器可用。** 沿用 Sequence 录音语义第 3 项与 `/product/workflows/` 已记录的行为（录制中 BPM、Quantize/Swing 被拒绝，control layer 返回 `HOST_STATE_INVALID`）：录音中这些控件保持禁用并说明原因。是否允许录音中改 BPM 需要动 Facade 的录音时序权威（`pattern_admission_controller`），留作后续问题。节拍器只是监听，不经过 Host，录音中可开可关、照常发声——这正是它的主要用途。
6. **节拍器开关是设备级监听偏好，不进 Project Truth。** 状态存设备级 IndexedDB（`lmdj.creator.host` 的 `settings` store，新增独立 key），重开恢复；默认关。依据 baseline 第 3 项：设备级状态不因放在界面里而属于 Project Truth；架构不变式同样要求监听偏好属于 Workspace/Host 设置。持久化沿用 `last_project.ts` 的 IndexedDB 语义（#1726 淘汰了 localStorage）。
7. **节拍器不进入任何录制。** click 由 Creator 侧 Web Audio 直接送 `AudioContext.destination`，绕过 Perform master tap（Perform 录音与「主输出」重采样的唯一采集点），因此任何录制都不会录到 click。这是 Koala 语义：节拍器是监听辅助，不属于作品。实施 Task 用 PCM 断言证明这一路由。
8. **节拍器对齐边界（文档化）。** 引擎渲染帧与 AudioContext 输出帧在同一音频时钟上 1:1 前进（每个回调 128 帧，门打开时无条件渲染）。Web Runtime Platform 增加一个纯 JS 的音频时钟采样（context 时间 + 回调心跳 + 引擎纪元起点心跳），Creator 据此把 transport 的 `originFrame` 映射到 context 时间轴，用 Web Audio 提前调度（lookahead）发声，逐拍无定时器抖动；小节起点由 `sequence.bar_boundary` 通知逐小节校正。常数误差 ≤ 约两个渲染量子（48 kHz 下 ≈5 ms），无逐拍漂移；每次音频中断/恢复（新引擎帧纪元）重新取锚。这一精度记为文档化边界；更高的对齐精度需要引擎侧 click，另议。
9. **UI 位置。** Tempo、Swing、TAP 与节拍器开关都在 Sequence 触控区现有设置行（Koala 的 Sequence 页一键开关，调研 Q7）。节拍器开关不受 transport 录制禁用的影响。
10. **不改 Contract，不改 Core C++。** Creator 之外的唯一改动是 Web Runtime Platform 的纯 JS 会话访问器与类型声明。

## 原因

- baseline 第 1 项要求交互未定时默认对齐 Koala：Koala 5.3 的 Tempo/Swing 是拖动、tap、加减直接调节，没有 Apply；节拍器是一键开关（Q7）。现状的数值 + Apply 是已记录的差距（设计 §6）。
- 提交粒度沿用已交付的 Sample 推子手势：一次拖动产生几十个 revision 和撤销记录不可用，而每次提交都是 durable、可撤销的 Project 命令（现状如此），所以必须手势结束才提交。
- 录音中拒绝沿用已记录行为与既有 fence，避免在本 Task 内动录音时序权威；先交付对录音最重要的部分——录音中可闻的节拍器。
- click 绕过 master tap 既满足「不录进作品」，又让节拍器在 Perform 录音与重采样时安全可用；不需要引擎侧改动。

## 影响

- **Creator。** Sequence 设置区改为直接调节（拖动/步进/TAP）加节拍器开关；新增节拍器调度模块、设备级偏好持久化与注入式 AudioContext 保留；`parameter_slider.tsx` 的手势机制抽取为通用数值滑杆。
- **Web Runtime Platform。** 纯 JS 的音频时钟采样访问器（无 C++ 改动）。
- **版本。** `creator-web` 与 `web-runtime-platform` 各欠一个 MINOR，并入下一次协调版本切点。无 Contract SemVer、Product Build 或 Assembly 变化。
- **门户。** 本条先在 `/product/workflows/` 记录已确认行为；`/hosts/creator-web/` 与 `/core/modules/web-runtime-platform/` 随实施 Task 更新。
