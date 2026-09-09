# Runtime-only 紧凑存储设计

日期：2026-09-10。状态：提案，待当前提交独立评审；不是容量 PASS。

Parent: [#1104](https://github.com/endaye/lmdj/issues/1104)。设计工作项：
[#1124](https://github.com/endaye/lmdj/issues/1124)。本设计继承
[Cardputer 已批准范围](2026-09-10-cardputer-runtime-host.md)，不改变产品或并发语义。
[实施计划](../plans/2026-09-10-runtime-compact-storage.md) 分开存储修复与正向复测。

## 1. 缺陷与证据边界

R1 [PR #1127](https://github.com/endaye/lmdj/pull/1127) 的目标 ABI 证据绑定
`bd28364a6a95fd8b7a11a74184bcf917b410f1a6`，不是本设计提交的实际 heap 测量。
4 Pad、合计 48000 mono frames、32 events 的 fixed payload 为 261860 bytes；
PCM16 为 96000 bytes，另有 per-Pad float 192000 bytes。
常驻 payload 下界 549860 bytes，完整准备模型 763071 bytes；尚不能启动目标验收。
R1 的失败、无效初版 allocator 测量及修正后数据均留在原报告，不能以优化预测覆盖。

目标 ELF 的 Engine member offset 分解中，控制队列到下一 member 的 extent 为
65728 bytes，trigger outcome ring 为 98496 bytes；两者合计 164224 bytes。
这些 extent 包含 padding，不是独立 allocation，也不能再加到 Engine sizeof 上。
Engine sizeof 为 201024 bytes，独立 receipt-bounded Voice-state storage 为
52416 bytes；Facade 与 Impl 合计 8420 bytes。固定合计仍为 261860 bytes。

源码复核基线 `de78b1e35767a172bb27a2b6df1c89c07052e444`：窄 Facade 已限制
pending command 数量，但 Engine 控制/结果存储没有随之收敛；load 仍逐 Pad
转 float 并复制进 Bank。基线之间 authoring 代码有变化，不能宣称全部五个包未变。

## 2. 不变项

- 桌面默认 128 Voice、1024 控制、1024 FX、4096 trigger outcome、10240
  Voice-state 的容量及 Capture 能力不变；既有 float Bank 入口不改变。
- 一个串行 control producer、一个 audio consumer；原 SPSC acquire/release
  顺序、callback admission、quiescent stop/reclaim 与 full-width 身份不变。
- 4 Pad、1 秒素材、32 events、四声部、reserve、原始 PCM/event 保真和全部
  stop/unload/reload/reset/retry 验收腿不缩减。不修改 Runtime Content wire。
- 不新增 Host 私有 Runtime；Host 只调用 Facade，不解析 Project 或自己维护 Voice。

## 3. M1：按回执额度一次配置存储

扩展现有显式 receipt-bounded 构造，使其接受 `N`（1..1024）；未传 N 的旧显式
调用保留原容量。默认构造仍用完整桌面配置。Facade 使用已经验证的
`maximum_pending_commands`；无运行中切换、resize 或自动扩容。

| 存储 | 默认 Engine | 显式 N 配置 |
| --- | --- | --- |
| Pad control | 1024 | N |
| Trigger outcome | 4096 | N |
| Voice-state | 10240 | 2N + 128 |
| FX control | 1024 | 1024，保持不动 |
| Voice | 128 | 128，保持不动 |

兼容旧显式无参数构造时，必须保留其原控制 1024、结果 4096、状态 2176 的组合，
不能把旧调用静默改成较小结果队列。新 N 配置是独立显式选择。

采用构造时申请、之后地址与容量不变的固定容量 SPSC storage；在 control 侧
为每个队列申请 `capacity + 1` 个 cell。沿用原索引原子宽度、自然对齐 cell、
缓存行隔离、满/空判断与内存序。构造失败由 RAII 回收已申请块，Facade 返回
allocation_failed 并保持 empty。callback 不分配、释放、引用计数或选择新存储。
析构只能在原 quiescence 边界后执行。原 FixedSpscQueue 及无关使用方不改。

上界证明：每个 accepted 命令从准入直到回执取走一直占用一个 N 名额；音频
消费不归还额度。每个命令至多一个 trigger outcome，故未读 outcome 至多 N。
每条命令至多两个 Voice-state，加上开始本轮时至多 128 个旧 Voice 的 terminal，
得 `2N + 128`。Pattern/replay/audition 不发布到这条 Voice-state 流。
control 必须先 acquire 消费位置，drain outcomes 和 Voice states，最后才归还回执
额度；空 span 和部分 poll 也保持顺序。违反前置条件仍由既有 corrupted/fail-closed
机制处理，不能覆盖、截断或把状态丢弃伪装为正常成功。

字节模型必须使用实际 cell sizeof、`capacity + 1`、wrapper sizeof 与 alignment，
共享 overflow-checked storage 计算给构造和预算使用。移到堆上不等于释放成本；
所有独立块继续进入 fixed_bytes。至少测试 N=1、128、1024 和非法边界。

## 4. M2：Bank 复用只读 PCM16

Engine 的 Pattern Voice 已使用 `PreparedSampleMaterialView` 和
`prepared_material_sample` 读取 PCM16。为 PreparedSampleBank 添加只读 PCM
样本入口和 ownership；live Pad 使用同一转换函数，不再先生成完整 float 副本。
既有 float `set_sample/from_snapshot` 入口保留，不能改变桌面配额与诊断。

每个 Bank Pad 保留 `shared_ptr<const PcmSample>` owner 和已验证 playback；
同一 decoded sample 的多个 Pad 共享 payload。新入口明确不可变前置条件：发布后
不得经其他 mutable alias 改写 sample。窄 Facade 的 decoder 产生内部拥有的 PCM，
不向 Host 暴露 alias，因此该路径可建立此条件；任意公共调用者仍须遵守。
Bank 成为不可变 publication 后，只在 control 回收；audio Voice 持有 raw view
并沿用 Bank generation/claim 生命周期，不在 callback 复制 shared_ptr。
Pattern 保留自身原有 sample ownership，不能仅删除 Facade snapshot 就宣称省掉 PCM。

slot 只选择一种表示；重复 set 必须原子地替换 control-local 数据并更新 availability、
sample count、字节账本。校验 PCM channel/frame、播放范围和空值，失败不半更新。
sample frame 数、preview 校验、Voice material/data 选择需统一处理两种表示。
释放尾音、旧 Bank Voice、audition、Pattern、mute、loop 与 Bank 替换均保留现有语义。

mono/stereo PCM16 在每帧使用与原预转换相同的函数；对同一内容的 native render
要求逐 sample 比较，不以 RMS 接近代替保真。负值、边界值、stereo downmix、
trim/loop/ramp、同素材多 Pad 各自 playback 都需覆盖。

仅窄 load 的 `prepared_float_bytes` 成为 0；codec footprint 仍可报告其他消费者
的 float 需求。metadata 计入新增 owner table；workspace 删除实际消失的
largest-float 临时项，保留 Pattern 准备、Bank/View 对象与解码临时重叠。
必须用包含 aligned new 的 allocator positive controls 和失败注入验证模型，
allocator/control-block rounding 仍属于显式 reserve，不得漏算已知 payload。

## 5. 准入与恢复

M1/M2 都需要独立当前 head 评审后合并；设计 Closed、修复合并、native PASS
均不解除 H1/B1 的容量阻塞。R2 在两项修复后的 exact source 重跑同一 A/B 数据、
严格 EIM 目标构建和预算，达到原 D1 容量/运行测量门槛后才可记录正向准入。
若仍超限或 deadline 失败，保留负结果，另拆已定位原因；不更换素材缩小目标。
target heap、最大连续块、栈高水位、DMA 时限及真实延迟只能由实际目标运行证明。
H1 完整 Host I/O 成本、B1 Build、物理听感和耐久运行仍分别验收。

## Version Management

Version impact: none — 本 Task 只提交设计与计划。实现预计改变公开 C++ 对象布局，
Audio Runtime 必须按 MAJOR 不兼容处理、所有消费者一致重编；不是事件字段 ABI
未变就可忽略 Engine/Bank ABI。具体 staged 分配与后续 B1 见实施计划。

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /core/modules/audio-runtime/
Reason: 说明待评审优化和仍然阻塞的设备容量，不宣布新实现或设备支持。
