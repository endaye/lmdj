# 已确认：渲染路径加 2 ms attack/release 线性斜坡，循环接缝 crossfade 暂缓

- 日期：2026-08-24
- 结论：F6 采用选项 a——在 `packages/audio-runtime` 渲染路径引入
  attack + release 短斜坡，斜坡长度 **96 帧**（48 kHz 下 2 ms），线性
  插值。2 ms 足以消除阶跃不连续产生的咔哒，又不会可闻地软化打击乐
  瞬态（本产品是节奏乐器）。循环接缝 crossfade（选项 b）**暂不实施**，
  待 M2 听测验证 a 之后再评估；过零吸附（选项 c）**不采纳**——它改变
  修剪语义与精度，且对循环接缝无效。
- 斜坡语义：
  - **attack**：voice 触发时增益从 0 线性升至 1。循环 voice 只在首次
    触发应用一次，接缝回卷不重复——因此 attack 使用每 voice 的剩余帧
    计数状态，而非 cursor 位置的纯函数。
  - **release（边界淡出）**：非循环 voice 到达 `end_frame` 前的最后
    96 帧按 cursor 位置淡出，无额外状态；循环 voice 无边界淡出。
  - **release（stop_voice）**：`stop_voice` 不再立即停声，voice 进入
    releasing 态，继续渲染 96 帧尾音后停用。`RuntimeVoiceState::stopped`
    的发布时机不变（stop 发起时发布），尾音只是防咔哒，不改变 voice
    的逻辑生命周期；抢占（stealing）路径可以立即停用一个 releasing
    voice。
- 实时安全（评审结论随决策记录）：斜坡状态为 `Voice` 结构体内的 POD
  字段（attack 剩余帧、release 剩余帧/标志），无分配、无锁、每帧至多
  两次额外乘法与计数递减；release 结束增益精确到 0 并立即停用 voice，
  无 denormal 残留；`noexcept` 契约不变。
- 原因：2026-08-17 物理会话（F6，M2 第 1 检）：修剪边落在非零采样
  即阶跃不连续，产生可闻咔哒；渲染路径全程无任何斜坡/淡化/吸附。
- 影响：关闭 #214 的 F6 行；解决开放问题
  `docs/prd/questions/render-path-amplitude-ramp.md`（同 Task 删除该
  文件）。`audio-runtime` 按 SemVer patch  bump 并承担既有级联（module
  manifests、Assembly、portal、新 Product Build）；改动无锁/实时代码，
  验证必须包含 stress tier；落地后按触发表重跑 M2 第 1、5 检（第 5 检
  接缝咔哒在选项 b 实施前预期仍存在，记录而不掩盖）。
- 确认：项目负责人口头确认（"都按建议来"），代理记录。
