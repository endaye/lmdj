# 已确认：实体 ● 键在各页都只录 Pattern 事件，按 Koala 增加 count-in

- 日期：2026-10-10
- 解决的问题：[#1959](https://github.com/endaye/lmdj/issues/1959)（实体 ● 键是否按页面决定录什么，以及录音前的 count-in）。#1959 没有对应的 `questions/` 文件。
- 来源：owner 对 #1959 的回复「行为跟着 Koala 走」。
- 依据：
  - [Koala 手册](https://manual.koalasampler.com/one-page/)，2026-10-10 访问：
    - §2.1、§3.1：SAMPLE 页没有录音键，按住空 Pad 开始录音，松开停止；
    - §2.2、§5.2：SEQUENCE 页的录音键录 Sequence，再按切回回放，叠录在已有内容上；
    - §6.2、§7.4：歌曲录音从菜单进入录制模式，按 PLAY 开始，不使用 Sequence 的录音键；
    - [§8.1 General Settings](https://manual.koalasampler.com/mobile/8-settings/)："Count in: number of bars counted in with metronome before recording starts"。
  - [#1230](https://github.com/endaye/lmdj/issues/1230) 的六状态转换表，以及其中「restart/resume/count-in 需要明确处置」的要求。
  - [节拍器决定](2026-10-02-creator-tempo-metronome.md) 第 6、7、8 项。

## 结论

1. **实体 ● 键在每一页都只录 Pattern 事件。**
   - 这就是 Koala SEQUENCE 页录音键的行为。#1230 的六状态转换表不变。
   - #1959 原先提出的「按页面语义」：Sample 页 ● 录采样、Perform 页 ● 录演奏，不是 Koala 行为，不采用。等功能对齐 Koala 之后，如有需要另行提出。
   - 采样继续用按住空 Pad（Koala §2.1）和 Sample 页的 Record Sample；演奏录音继续用 Perform 页自己的入口（对应 Koala 的歌曲录音）。
2. **新增 count-in 设置，单位是小节。**
   - 档位：Off、1 小节、2 小节。
   - 默认 Off：按下 ● 立即开始，与现状相同。
   - Koala 手册没有写可选档位和默认值。这两项是 LMDJ 的取舍，owner 可以改，不需要改动本文件以外的其他决定。
3. **count-in 只在停止状态按 ● 时生效。**
   - 节拍器先数设置的小节数，期间 Pattern 不播放，也不录音。
   - 数完后，Pattern 从开头开始播放并录音，与现在停止状态按 ● 的结果相同，只是推迟了 N 小节。
   - 已经在播放时按 ●，直接叠录，不数拍；Koala §5.2 的叠录就是在回放中切到录音。
   - 按住空 Pad 采样、Record Sample、演奏录音都不使用 count-in。
4. **count-in 期间的节拍器和操作。**
   - count-in 一定发出节拍声，不受节拍器开关影响，这就是 Koala 说的 "counted in with metronome"。数完之后，节拍器按它自己的开关决定是否继续响。
   - 节拍声走节拍器决定第 7 项的路由，不进入任何录音。
   - count-in 期间再按 ● 或 Play/Stop，取消这次录音，回到停止状态，不写入任何内容。
   - count-in 期间可以照常打 Pad 发声，但这些按压不录入 Pattern。Koala 手册没有写这一点，这里按「数完才开始录」处理。
5. **界面反馈。**
   - 上屏主状态行显示 COUNT-IN 和剩余拍数。
   - count-in 期间 Record 灯闪烁，开始录音后常亮。
6. **count-in 是本设备的设置，不进 Project Truth。**
   - Koala 把它放在通用设置里，不在工程里。LMDJ 与节拍器开关、SEQ SNAP 一样存设备级设置，重开恢复。
   - 设置放在 Sequence 触摸区 SETUP 层，与节拍器开关相邻。

## 原因

- owner 要求按 Koala 来。Koala 用三个不同的入口完成三种录音，录音键只管 Sequence；LMDJ 现在的分工与之一致，不需要改。
- Koala 在通用设置里提供 count-in，用节拍器数小节。LMDJ 现在停止状态按 ● 立即开录，没有预备拍，第一拍容易打晚。
- 默认 Off 保持现有手感，也不改变 #1230 已验收的「停止状态按 ● 立即播放并录音」；需要预备拍的用户自己打开。

## 影响

- **#1230。** 本决定是 #1230 要求的 count-in 处置。count-in 为 Off 时，六状态转换表完全不变；为 1 或 2 小节时，「停止 → 按 ●」的结果推迟到 count-in 结束，中途取消回到停止。
- **Core / Facade 与 Web Runtime。** 录音开始必须精确落在 count-in 结束的那一帧。实施计划需要决定由 transport 接受预定的开始帧，还是由其他机制保证对齐，并写明最低层测试。count-in 期间不得打开录音 Journal。
- **Creator。** SETUP 层增加 count-in 设置；节拍器调度在 count-in 期间无条件发声；上屏和 Record 灯的 count-in 状态；设备级偏好持久化。
- **版本与门户。** 本决定本身没有版本影响，也不改 Contract。实施 Task 更新 `/hosts/creator-web/` 与 `creator-interactions` 页面中 Record 的描述。
