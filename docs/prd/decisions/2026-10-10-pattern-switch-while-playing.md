# 已确认：播放中和录音中随时切换 Pattern，按 Koala 的 SEQ SNAP 在边界生效

- 日期：2026-10-10
- 解决的问题：[#1958](https://github.com/endaye/lmdj/issues/1958)（播放中能否切换 Pattern、何时生效）。#1958 没有对应的 `questions/` 文件。
- 来源：owner 对 #1958 的回复「根据 Koala 的设置来」。
- 依据：
  - [Koala 手册](https://manual.koalasampler.com/one-page/)，2026-10-10 访问：
    - §5.1：播放中点另一个 Sequence 槽就切换；
    - §5.2：录音中点另一个 Sequence 可以继续无缝录音；
    - §5.3 SEQ SNAP：控制从当前 Sequence 切到新选 Sequence 的快慢。1 BEAT、1 BAR、SEQ END 等到对应时间步结束，新 Sequence 总是从开头开始。OFF 立即切换；
    - §2.3、§3.3、§6.1：Perform 页按 Play 后点槽切换，不需要先开演奏录音。
  - Koala 业务流程调研 Q6、Q16、Q18 与 §4.5（`docs/research/2026-07-28-koala-sampler-business-flows.md`）。
  - 已有机制：[Sequence 录音语义](../../design/2026-08-22-sequence-recording-semantics-design.md) SR-D11 / SR-D23（切槽是 selection request，commit 旧槽、Journal 改目标、Runtime 改播放在同一边界发生）；[Stage 10 Perform 设计](../../design/2026-08-28-lmdj-stage10-perform-design.md) P10-D2、P10-D22（Launch 默认下一 Bar；未认领的请求以最新为准，已认领的后来请求顺延）；[switch 后重锚](2026-09-16-pattern-transport-switch-retarget.md)。

## 结论

1. **播放中可以切换 Pattern。**
   - Sequence 页的 `←` `→` 与触摸区 `‹ GROOVE / NN ›`、Perform 页的 Pattern Launch 槽，在播放中都可用。
   - 按下只提交切换请求。旧 Pattern 继续播放，直到 SEQ SNAP 规定的边界才换成新 Pattern。
   - 停止状态下按下立即换当前 Pattern，与现状相同。
2. **录音中也可以切换，录音不中断。**
   - 沿用 SR-D11 / SR-D23：在生效边界上，旧 Pattern 的录入内容结算提交，Journal 改指向新 Pattern，Runtime 改播放新 Pattern，三件事同一时刻发生。
   - 边界之前录入的事件仍写进旧 Pattern；边界之后的进新 Pattern。
   - Record 灯保持亮，用户不需要重新按 ●。这就是 Koala §5.2 的「继续无缝录音」。
3. **SEQ SNAP 有 Koala 的四档，默认 1 BAR。**

   | 档位 | 何时切换 | 新 Pattern 从哪里开始 |
   | --- | --- | --- |
   | OFF | 立即 | 匹配当前播放位置，可能从中间开始 |
   | 1 BEAT | 当前拍结束 | 开头 |
   | 1 BAR | 当前小节结束 | 开头 |
   | SEQ END | 当前 Pattern 播完一遍 | 开头 |

   - 默认 1 BAR：Koala 手册没有写默认值，沿用 LMDJ 已有的下一 Bar 默认（SR-D11、P10-D2）。
   - 设置放在 Sequence 触摸区 SETUP 层，靠近 Tempo、Swing 和 Quantize，对应 Koala 把它放在 Tempo 菜单。
   - Sequence 页与 Perform 页使用同一个 SEQ SNAP。
4. **排队规则沿用 P10-D22。**
   - 边界之前再按另一个 Pattern，以最新一次为准。
   - 再按当前正在播放的 Pattern，等于取消待切换。
   - 音频线程已经认领、即将生效的请求不再被覆盖，之后的请求顺延到下一个边界。
   - 失败、取消或停止播放时，待切换请求作废，不留下半切换状态。
5. **Perform 的 Pattern Launch 不再要求开着演奏录音。**
   - 只要 Pattern 在播放，Launch 槽就按第 1、3、4 条工作；停止时按下槽就选中它，之后按 Play 从它开始。
   - 开着演奏录音时，Launch 照常作为演奏事件记录（P10-D8、P10-D22 不变）。
6. **界面反馈。**
   - 待切换的目标在 Perform 槽上显示 QUEUED，在 Sequence 标题行显示目标序号，直到生效后变为当前 Pattern。
   - 上屏继续显示真正在播的 Pattern，生效前不提前换成目标。
   - `←` `→` 的灯按「还有上一个、下一个 Pattern」点亮，不再因为播放而熄灭。
7. **SEQ SNAP 是本设备的演奏偏好，不进 Project Truth。**
   - 与节拍器开关一样存设备级设置，重开恢复。#1230 已规定 transport 偏好不作为 Project Truth 持久化。
   - Koala 是否把 SEQ SNAP 存在工程里，手册没有写。这里按 LMDJ 的架构不变式处理，记为 LMDJ 差异。
8. **本决定不改变的内容。**
   - 播放中改 Tempo、Swing、Quantize，以及改 BARS、DOUBLE UP、COPY：Koala 手册没有写能否在播放中调整，沿用 [Tempo 决定](2026-10-02-creator-tempo-metronome.md) 第 3、5 项与 [Pattern 长度决定](2026-10-08-pattern-length-and-copy.md) 第 5 项。
   - 录音前的 count-in 与实体 ● 键按页面的语义，归 [#1959](https://github.com/endaye/lmdj/issues/1959)。

## 原因

- owner 要求按 Koala 来。Koala 允许播放中、录音中随时点槽切换，由 SEQ SNAP 决定生效边界；现在的 Creator 要求先停止，演奏会断拍。
- LMDJ 的内核早已按这条路设计：SR-D11 / SR-D23 定义了边界切换和录音改目标，引擎在 Bar 边界发布切换，2026-09-16 的重锚决定处理了切换后再录音。缺口在 Creator 的界面限制和 Launch 只走演奏录音路径。
- Stage 10 当时只开放 Bar 一档，并写明「Koala 有四档，首版收缩」。本决定把剩下三档补齐。
- 排队、覆盖、顺延已有 P10-D22 的规则，不另造一套。

## 影响

- **替代的旧结论。**
  - [Sequence 硬件界面修订](2026-10-04-sequence-hardware-ui-revision.md) 第 5 项「播放中不能切换」与第 7 项「播放中不可切换」由本决定替代；该文件其余结论不变。
  - Stage 10 P10-D2「首版仅暴露 Bar 边界」由第 3 条扩展为四档。
- **Core / Facade。**
  - 需要一个不依赖演奏录音会话的 Pattern 切换请求，复用 Launch 的边界预约、认领与确认机制；当前 Web Runtime 只有 `performance.record.launch-request`。
  - 1 BEAT、SEQ END 需要按对应边界计算生效帧；OFF 需要新 Pattern 从匹配的播放位置开始。
  - 录音中跨 Pattern 的结算走既有 switch 结清路径（2026-09-16 决定第 3 项）。
- **Creator。** 解除 `←` `→`、`‹ ›`、Launch 槽的播放中禁用；SETUP 层加 SEQ SNAP；排队显示；设备级偏好持久化。
- **实施顺序建议。** 先交付 1 BAR 档的播放中与录音中切换，以及 Perform Launch 脱离演奏录音；再补 1 BEAT、SEQ END、OFF。实施计划需写明文件、最低层测试与版本影响。
- **版本与门户。** 本决定本身没有版本影响，也不改 Contract。实施 Task 更新 `/hosts/creator-web/` 与 `creator-interactions` 页面中「playing／recording 时不能切 Pattern」「Launch 仅 recording／flushing 可用」的描述。
