# M1 — 64-Pad live Mute/Solo 的实时声音门控（DSP 实现）

状态：实施 Task 计划。本文件是
[producer/consumer 计划](2026-10-11-performance-live-control-producers.md)
M1 节的实施计划；M1 节是边界权威，本文件不扩大其 scope。

## Outcome and authority

在共享 engine 内为全部 64 Pad 增加 live Mute/Solo 声音门控：立即阻断对应 Pad
当前与后续输入，已进入共享 Delay/Reverb 的尾音自然衰减，其他 Pad 的效果继续。

**Authority:**

- [producer/consumer 计划 M1 节](2026-10-11-performance-live-control-producers.md)：
  declared files、defect oracles、版本与文档声明的完整边界。
- [已批准共享尾音规则](../prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md)：
  门控立即生效；共享 FX 总线内已存在的尾音不被清空、自然衰减。96-frame ramp 与
  cursor 保留是工程提案，不是 owner 批准的额外输入宽限；本 Task 以原生 PCM oracle
  证明实际应用边界满足已批准规则。
- D0 encoding 文档的 masks/queue/epoch 段：两组 uint64 mask 原子成对应用、
  复用有界 master-control queue、mask/status/reset 同属一个 producer。

## Facts this Task relies on

Checked on `02b7445ff035e48c43ea2a66c858f7c9282e6c79e`（本 worktree base）。

- engine 此前只有 `playback.muted`（持久 Pad 属性，realtime_engine.cpp 的
  trigger 与 mix 路径），没有 live mask；F1（`a61ab819`）与本 base 之间
  audio-runtime 源无变化，无 successor PR 交付该缺口。
- engine 内无 metronome 路径（metronome 在 engine 之外混音），"metronome 不改"
  由构造满足，不需要代码差异。
- 既有 ramp 常数 `kRealtimeRampFrames = 96`（realtime_engine.cpp）与有界
  master-control queue（容量 1024）可直接复用；render 内 fx queue 先于 trigger
  queue 排空，同一量子内 mask 先于 press 生效。
- audition 走保留 Bank sentinel voice，不占 64 个 project slot；mask 只寻址
  project slot，sentinel 不在值域内。

## Design

- **状态与队列**：`PadGatesState{muted_mask, solo_mask}` 作为
  `MasterFxControlKind::pad_gates` 事件的载荷进入既有有界 queue；
  `enqueue_pad_gates(muted, solo)` 只在 running 时接受，queue 满 fail-closed
  （不触碰 accepted shadow）。accepted shadow 与逐条 sequence 由 producer 侧
  原子维护；audio 侧在 render drain 中原子成对应用两组 mask，计数后向
  `ValueChannel<PadGatesAppliedState>` 发布带 `start_epoch_` 的 applied 快照。
  `pad_gates_status()` 是无锁 producer 侧读取（accepted shadow + channel）。
- **门控点**：mix loop 内每个非 audition voice 携带 `live_gate` 增益，朝目标
  （gated ? 0 : 1）以既有 `kRealtimeRampScale` 步进并 clamp；`live_gate != 1.0F`
  时才乘入，中性路径 bit-identical。门控只乘增益：voice cursor 继续前进，
  解除门控恢复的是当时位置的声音，不 retrigger、不冻结。trigger 处在既有
  `playback.muted` 之后追加同等拒绝：gated Pad 的 press 不起 voice，解除后不复活。
- **优先级**：Mute 优先于 Solo；Solo mask 非空时未被 Solo 的 Pad 视为 gated；
  多 Solo 合法。`playback.muted` 仍是独立的额外禁止，两者并存。
- **生命周期（producer 契约映射）**：`start()`/`stop()` 清空两半状态并按新
  epoch 发布中性 applied——reset/start/stop 的清理由 engine 保证；切换工程时
  清空是同一 producer（Host/Facade 生命周期）的职责，由 stop/start 边界自然覆盖。
  Bank/Pattern replacement 保留两组 mask（门控寻址 Pad slot，不寻址 Asset）。
- **共享尾音**：gate 在 shared-FX 输入之前乘在 voice 上；已进入共享
  Delay/Reverb 总线的字节不归任何 Pad 所有，自然衰减，不清空总线。每 Pad 历史
  尾音隔离明确不在本 Task（M1 节禁止靠清空总线实现）。

## Declared files（完整边界）

- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `tests/core/audio/master_fx_allocation_guard_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `docs/plans/2026-10-12-live-pad-mute-solo-dsp.md`（new，本文件；日期按实际
  实施日命名，覆盖 M1 节原文的 10-11 文件名）
- `apps/docs-site/diagrams/audio-runtime.architecture.json`
- `apps/docs-site/static/diagrams/audio-runtime.html`
- `apps/docs-site/static/diagrams/audio-runtime.svg`

## Lowest-tier verification / defect oracles

- `audio.realtime_engine`（unit tier）：
  - mask 寻址 slot 0 与 63；多 Solo 合法、Mute 优先于 Solo；accepted/applied
    status 与 sequence/epoch 一致；Bank replacement 保留两组 mask；gated Pad
    的 press 不起 voice 且解除后不复活。
  - 原生 PCM oracle：两条持续 Pad 信号。无 FX engine 证明 ramp 形状——常值
    内容下 mix 在恰好 96 帧内单调降到精确目标值且之后逐帧相等，解除时单调
    升回，`started_voices` 不变（无 retrigger）。Delay engine（单 voice）
    证明共享尾音规则——门控关闭后先出现一整个 Delay period 的精确静音
    （closed gate 零泄漏），随后两代 echo 峰值按 0.35 反馈严格衰减（尾音
    自然衰减、无再注入）。
  - cursor 保留：sweep 内容跨 loop wrap 门控后，恢复帧读取的是推进后的
    cursor（由帧数精确计算），不是冻结副本。
  - audition sentinel 不被门控（gated ≠ deactivated：`active_voices` 不变）。
  - queue 满 fail-closed 且 rejected pair 不污染 accepted shadow；
    not-running 拒绝；stop/restart 清空并以新 epoch 发布中性对。
- `audio.realtime_engine_stress`（stress tier）：并发 producer/consumer——
  render 线程逐帧 render，producer 线程高频翻转两组 mask enqueue 5 万次；
  断言不崩且 applied 按 FIFO 收敛到最终 accepted 对（内容与 sequence）。
- `audio.master_fx_allocation_guard`（unit tier）：`enqueue_pad_gates` 与
  applied drain 纳入零分配/无锁覆盖；enqueue/status 的 noexcept 静态断言；
  无 prepared Master FX 时门控仍然 admit（voice 级，非 FX stage）。
- `scripts/docs-site.sh check`（portal 页与源图同 Task 更新）。
- mutation 证明：去掉 `live_gate != 1.0F` 守卫或令 `pad_live_gated` 忽略 Solo，
  重建 artifact 后 RED 必须落在上述命名断言行；恢复后 GREEN。

## Version Management

Version impact: audio-runtime ABI MAJOR debt — `RealtimeEngine` 公共布局与
`MasterFxControlEvent` 增长，记入既有 audio-runtime ABI debt，V1 结算。无
Project Contract、RuntimeSnapshot 或 Product Build allocation；不新增持久化
PadPlayback 变更（live mask 是 Attempt/session 态，不进 Project Truth）。
F1/M1 共享 engine 文件，按序 landing。

## Documentation impact

Documentation impact: required — `/core/modules/audio-runtime/`；
`audio-runtime.architecture.json` 源图与生成 HTML/SVG 在同一 Task 更新。

## Pitfall Impact

预计无新 pitfall：本 Task 的陷阱（Mask 只寻址 project slot、门控不碰 audition
sentinel、尾音属总线属主）已由既有测试名固化。shipping 前按 issue-done 评估
`area:audio` 既有条目是否需要 bump。
