# 渲染路径振幅斜坡策略：斜坡长度、循环接缝、过零吸附如何取舍？

- 范围：Core（`packages/audio-runtime`），新内核（Playable Beat Instrument）
- 状态：待决
- 来源：2026-08-17 物理会话发现 F6（M2 第 1 检：修剪后触发在修剪边界产生可闻咔哒声；[补救计划](../../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md)「Findings out of scope」；[#214](https://github.com/endaye/lmdj/issues/214)）；决策行见 [2026-08-17-manual-verification-todo.md](../../quality/2026-08-17-manual-verification-todo.md)
- 为什么重要：`realtime_engine.cpp` 渲染循环（:710-737）逐帧输出 `voice.samples[voice.cursor] * voice.gain`；到达 `end_frame` 时，循环模式直接把 `cursor` 重置回 `start_frame`（硬接缝），非循环模式立即 `active = false`（硬停止）；`stop_voice`（:195）同样立即停声。全程无 attack 斜坡、无 release 斜坡、无修剪边界淡出、无循环接缝 crossfade、无过零吸附。修剪边落在非零采样上就是阶跃不连续——这正是咔哒声的定义。同一缺失还预示循环接缝（M2 第 5 检）与按住释放两处咔哒，均未实测。这是 Core/DSP 决策，不能在某个前端 Task 里顺带定掉。
- 实时安全约束（评审必须回答的）：渲染路径 `noexcept`、无分配、无锁，任何斜坡状态必须是 `Voice` 结构体内的纯数据字段（预分配、POD），每帧至多几次乘加；`stop_voice` 的 release 斜坡意味着 voice 在淡出期间保持 active（新增 "releasing" 态），这会改变 voice 生命周期、容量/抢占（voice stealing 路径 :602-623 也走 `stop_voice`）与 `publish_voice_state` 的上报语义，必须显式评审；斜坡实现需避免次正规数（denormal）拖累。
- 选项（可组合）：
  a) **attack + release 短斜坡**（1–5 ms，48 kHz 下 48–240 帧）：覆盖修剪边界与 voice 释放两处咔哒，每 voice 只需一个当前增益系数 + 逐帧增量，实现最小。
  b) **循环接缝 crossfade**：接缝两侧各取短窗交叉淡化，需要额外的接缝区状态；解决 M2 第 5 检。
  c) **过零吸附**：在 authoring 侧把修剪边吸附到最近过零点，不改渲染路径，但改变修剪语义与精度。
  建议先 a，用 M2 听测验证后再评估 b；c 与渲染路径解耦，可独立决定。
- 处理时点：这是解锁 M2 剩余检查（第 1、5 检今天构造性失败）的前置；也是 #214 剩余的两项之一。落地后按触发表重跑 M2 第 1、5 检。
