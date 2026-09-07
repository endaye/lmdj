# Cardputer Adv 能承载受限的 LMDJ 演奏终端，但不能原样承载当前完整产品

> 日期：2026-09-03
>
> 更新：2026-09-07 [ESP-IDF v6.1 工具链与 atomic 退化条件增补](./2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md) 记录 v6.1 版本落点、已声明 IDF 6 支持的 M5 库版本，以及本板无 PSRAM 对 atomic 路径的影响
>
> 评估对象：M5Stack Cardputer Adv（K132-ADV）与 LMDJ New Headless Core
>
> LMDJ 源码基线：`64ea7027e3162507e6bb10fba7aa0a278f4a5e98`
>
> 文档性质：技术可行性研究，不是已批准的产品范围、Contract、硬件选型、实施计划或排期承诺
>
> 证据边界：完成了源码与公开资料静态审查；未进行 ESP-IDF 交叉编译、真机烧录、I2S 输出、
> 端到端延迟、功耗或长时间稳定性测试

## 0. 结论先行

**未来可以运行，但只能是经过明确裁剪的 LMDJ Embedded Runtime，而不是把当前 Creator Web、
完整 Application Facade、Project IO、Provider 和全部 Audio Runtime 能力原样塞进设备。**

Cardputer Adv 的 56 键键盘、ES8311 codec、扬声器、3.5 mm 输出、microSD、LCD、电池和无线能力，
很适合做一台掌上 4×4 Pad 演奏器或 LMDJ 控制终端。决定性限制是它使用
`ESP32-S3FN8`：只有 512 KiB 片上 SRAM、8 MiB Flash，型号本身没有封装内 PSRAM；M5Stack
产品规格也没有提供板载 PSRAM。当前 LMDJ 的固定事件缓冲、样本表示和 Master FX 任一项都足以
突破这一级别的内存预算。

建议把“Cardputer Adv 支持”拆成三个互不混淆的目标：

| 目标 | 当前判断 | 说明 |
| --- | --- | --- |
| 远程控制终端 | **可行性高** | Cardputer 负责键盘、屏幕和 USB/Wi-Fi 控制，LMDJ 音频仍在电脑或 Web Host 上运行 |
| 本地受限演奏 Runtime | **有条件可行，推荐做 spike** | 需要 Embedded Runtime Profile、显著缩小容量、裁剪内存型 FX，并使用短样本或 SD 有界流式读取 |
| 完整 LMDJ / Creator 本地运行 | **在该硬件上不可行** | 512 KiB SRAM、无 PSRAM、无浏览器环境，无法承载当前内存模型与完整产品图 |

因此，本报告的推荐决策是：

1. 可以购买 Cardputer Adv 做交互和音频硬件 spike；
2. 不把它指定为“当前 Core 原样移植”的验收硬件；
3. 先验证一个不承诺功能等价的、受约束的 Embedded Runtime Profile；
4. 若产品要求 64 Pad 长样本、完整 Master FX 或设备端创作，应改用带至少 8 MiB PSRAM 的
   ESP32-S3 板卡，或重新评估更高内存平台。

## 1. 问题定义

“项目运行在 Cardputer Adv 上”至少可能表示四件事：

1. **控制器**：设备只发送 Pad、Transport、FX 等控制事件；声音由其他 Host 产生。
2. **本地播放器**：设备消费桌面/Web 端预先 Cook 好的运行时输入，在本机混音并输出声音。
3. **Standalone 乐器**：设备读取素材、保存 Project Truth、Cook、录 Sequence，并本地播放。
4. **完整产品**：还包括 Creator UI、完整 Facade 命令面、Provider、Bundle 导入导出等。

只有第 2 项可以合理称为“Core 的一部分运行在设备上”，也是本报告建议验证的范围。第 1 项是
近期低风险产品路线，但不是本地 Core 运行；第 3、4 项在 Cardputer Adv 上没有足够的资源余量。

本评估继承并收窄仓库已有的
[ESP32 Core 通用可行性评估](2026-08-27-esp32-core-feasibility-assessment.md)。通用评估建议首个
ESP32-S3 spike 使用至少 8 MiB PSRAM；Cardputer Adv 恰好不满足这一关键条件，因此必须单独
评估，不能把“ESP32-S3 可行”直接外推为“Cardputer Adv 可行”。

## 2. Cardputer Adv 硬件与 LMDJ 的适配度

### 2.1 已确认硬件事实

| 维度 | Cardputer Adv | 对 LMDJ 的意义 |
| --- | --- | --- |
| SoC | ESP32-S3FN8，双核 Xtensa LX7，最高 240 MHz，单精度 FPU | 有运行实时浮点混音的基础，但必须真机量 callback deadline |
| 内存 | 512 KiB 片上 SRAM；该 FN8 型号无封装内 PSRAM | **主要阻断项**；可用 heap 还要扣除系统、任务栈、驱动、DMA 和 UI |
| Flash | 8 MiB | 足以放固件和少量固定资源，不能替代低延迟可写 RAM |
| 音频 | ES8311、NS4150B、1 W 扬声器、3.5 mm 输出、MEMS 麦克风 | 本地播放硬件完整；首期只验证输出，采集另立范围 |
| 音频总线 | I2S：BCLK G41、LRCK G43、DAC data G42、ADC data G46 | 与 ESP-IDF 标准 I2S/DMA 路径匹配 |
| 输入 | 56 键，TCA8418 通过 I2C G8/G9，INT G11 | 足以映射 16 Pad、Bank、Transport 和模式键；需测按键到声音延迟 |
| 屏幕 | 240×135 ST7789V2 | 适合状态、Pad、Pattern 与浏览 UI，不适合复用 Creator Web 布局 |
| 存储 | microSD，SPI：CS G12、MOSI G14、CLK G40、MISO G39 | 适合 runtime package 和流式样本实验，不自动满足 Project IO 持久化语义 |
| 连接 | Wi-Fi、Bluetooth LE、USB | 适合传输与遥控；无线开启时必须重测音频抖动 |
| 电源 | 1750 mAh 电池 | 形态合适；持续混音、背光、扬声器与 Wi-Fi 下续航仍是未测项 |

硬件信息来自 [M5Stack Cardputer Adv 官方文档](https://docs.m5stack.com/en/core/Cardputer-Adv)
与 [ESP32-S3 Datasheet v2.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)。
数据手册的型号对比表明确列出 `ESP32-S3FN8` 为 8 MiB Quad SPI Flash、无封装内 PSRAM；
同一数据手册给出 512 KiB 片上 SRAM、双核 240 MHz 和单精度 FPU。

### 2.2 有利条件

- Cardputer Adv 已把 codec、功放、扬声器、耳机口、键盘、屏幕、SD 和电池集成在一个可购买
  设备中，能显著降低板级 bring-up 工作。
- ESP32-S3 有两个 I2S 外设与 DMA。ESP-IDF 5.5.1 还提供 ES8311 官方 I2S 示例，说明 codec
  类型与平台驱动路径本身不是未知领域。
- M5Stack 官方 [M5Cardputer 库](https://github.com/m5stack/M5Cardputer)明确支持 Cardputer 与
  Cardputer Adv；官方 User Demo 也提供专用 `CardputerADV` 分支。
- 56 键比典型开发板更接近乐器控制面。一个自然映射是 4×4 当前 Bank Pad，加 Bank、Pattern、
  Play/Stop/Record、FX 和菜单键。
- 有线 3.5 mm 输出比仅有小扬声器更适合延迟和音质测量；插入耳机时板载扬声器功放会被硬件静音。

### 2.3 不利条件

- 无 PSRAM，使它低于仓库通用 ESP32 评估所建议的最低 spike 配置。
- 240×135 屏幕无法承载现有 Creator Web 工作区，需要新的小屏 Host UI。
- 键盘、codec 和 IMU 共用 I2C 控制总线。它们不应进入音频热路径，且需要验证按键中断、批量读取
  与 codec 控制不会相互造成可感知抖动。
- microSD 是素材容量方案，不是 RAM。随机多 Voice、低延迟 seek、卡顿、拔卡和坏卡都需要独立
  设计与故障测试。

## 3. 当前源码为什么不能原样运行

### 3.1 固定事件缓冲已经接近整机 SRAM

当前 [`RealtimeEngine`](../../packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp) 的
默认容量包括：

| 结构 | 当前容量 |
| --- | ---: |
| Pad control queue | 1,024 |
| Capture ring | 4,096 |
| Trigger outcome ring | 4,096 |
| Voice state ring | 10,240 |
| Voice | 128 |
| Sample Bank slot | 4 |
| Pattern slot | 4 |

仓库现有 ESP32 评估按 32 位 ABI 对事件 payload 的静态估算约为 **0.4–0.5 MiB**，尚未计入
对齐、Voice、Pattern、Master FX、FreeRTOS、任务栈、I2S DMA、显示、SD、Wi-Fi/BLE 和 heap。
Cardputer Adv 全部片上 SRAM 也只有 0.5 MiB，因此默认 `RealtimeEngine` 形状即不可接受。

这不是链接脚本调优可以解决的问题。容量必须成为经 Contract/产品批准的平台 profile，并通过
输入密度和溢出行为重新验收。

### 3.2 当前 Master FX 的最低历史缓冲也远大于整机 SRAM

[`MasterFxChain::prepare`](../../packages/audio-runtime/src/master_fx.cpp) 按一个 4/4 小节为 delay、
stutter 和 reverse 预分配多个双声道 `float` 历史缓冲。由源码可直接得到：

```text
bar_frames = sample_rate * 240 / bpm
history_float_count = 10 * bar_frames + 2 * (sample_rate / 20)
history_bytes = history_float_count * 4
```

在固定 48 kHz 下，仅这些 vector 的元素就需要：

| BPM | 仅 Master FX 历史缓冲 |
| ---: | ---: |
| 40 | 11,539,200 bytes，约 11.00 MiB |
| 120 | 3,859,200 bytes，约 3.68 MiB |
| 240 | 1,939,200 bytes，约 1.85 MiB |

[Native Host](../../apps/native-host/src/main.cpp) 在准备 Runtime 时会调用 `prepare_master_fx`。
即使 BPM 取允许范围上限、还没有加载任何 Sample，当前 Master FX 也需要约为 Cardputer Adv
总 SRAM 的 3.7 倍。这是“完整当前 Runtime 原样运行”最直接的确定性否定证据。

首期 Embedded Profile 若要成立，必须排除或重新设计需要整小节历史的 delay、stutter、reverse
等 FX。Filter、gate、crush、cutter 这类低状态量效果更适合作为第一阶段候选，但具体能力集合是
产品决策，不能由移植任务静默改变。

### 3.3 Sample 在当前播放路径中存在多份表示

当前 Runtime Snapshot 持有 48 kHz PCM16；
[`PreparedSampleBank::from_snapshot`](../../packages/audio-runtime/src/prepared_sample_bank.cpp) 又为
实时 Pad 触发生成单声道 `float` 副本。每秒 Sample 的基础 resident 成本为：

| 来源形状 | Runtime Snapshot PCM16 | Prepared mono float | 合计，不含发布重叠 |
| --- | ---: | ---: | ---: |
| mono | 96,000 B/s | 192,000 B/s | 288,000 B/s |
| stereo | 192,000 B/s | 192,000 B/s | 384,000 B/s |

Bank publication 还允许新旧不可变 Bank 在 Voice 结束前重叠。即便删除 Master FX 和大事件环，
一个一秒样本也会消耗 Cardputer 总 SRAM 的大部分，更不用说 16 或 64 Pad。

可行方向只有两类：

- 让 Embedded Runtime 直接消费有界 PCM16 material，避免同时常驻 PCM16 与 float Bank；
- 短样本分层缓存，长样本由 SD 经过固定大小 read-ahead buffer 流式供给。

两者都会改变当前 preparation/publication 形状，需要保持不可变样本所有权、Voice 生命周期和
实时线程不分配/不阻塞的契约，不能只把 `vector<float>` 换成文件指针。

### 3.4 64 位原子与当前实时契约冲突

[`realtime_engine.cpp`](../../packages/audio-runtime/src/realtime_engine.cpp) 明确要求
`std::atomic<std::uint64_t>::is_always_lock_free`，并在音频线程访问大量 64 位 frame、generation
和 telemetry 原子。ESP-IDF 的官方
[`stdatomic.c`](https://github.com/espressif/esp-idf/blob/master/components/esp_libc/src/stdatomic.c)
说明没有硬件 64 位原子时使用单一全局 `portMUX_TYPE` 自旋锁模拟；ESP32-S3 是 32 位目标。

因此当前代码预期首先会在静态断言处失败。删除断言并链接成功不是正确修复，因为会把全局锁带入
音频热路径。需要把热路径并发计数改为原生 32 位原子、音频线程独占 64 位值，或采用两个 32 位
word 加序列戳的可证明读取方案。

### 3.5 构建图与完整 Facade 依赖不适合 MCU

根 [`CMakeLists.txt`](../../CMakeLists.txt) 无条件加入全部 Module、proof Provider、测试、
Web Runtime、CLI、Native Host 和 Product Assembly，并依赖桌面 Bash/Python 工具。当前树中没有
Cardputer、ESP-IDF component 或 embedded build profile。

同时，Application Facade 当前公开库会链接 Authoring Domain、Project IO、Project Cooker、
Audio Runtime 和 Provider SDK。架构规定 Host 只能使用 Facade，因此正确方向不是让 Cardputer
Host 绕过 Facade 直连 `RealtimeEngine`，而是先批准一个窄的 embedded runtime Facade surface，
再让独立 ESP-IDF component 只链接需要的模块。

### 3.6 Project IO 不能等同于“有一张 SD 卡”

Project IO 的 Storage Platform 要求 writer lease、immutable create、complete replace、durable
append、目录验证和原子发布等语义。当前 native backend 使用 POSIX `openat`、`flock`、
descriptor-relative traversal 等能力，不能直接移植到 FAT/microSD 后宣称语义等价。

推荐的首期设备只消费预先生成的 runtime package，不在设备上维护权威 Project Truth。若未来
需要本地录 Sequence、断电恢复或 Project 编辑，必须为 SD/FAT 或其他存储实现故障注入、掉电和
拔卡测试；这应是独立 Standalone 里程碑。

### 3.7 I2S 驱动可用，但 Host 调度方式必须不同

ESP-IDF 的 [I2S 文档](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/i2s.html)
确认 ESP32-S3 支持标准双声道 I2S、DMA、异步事件 callback 和 ES8311 示例。文档也明确警告：
I2S 中断 callback 不应执行复杂逻辑、浮点运算或不可重入调用，而 LMDJ 的混音和 FX 是浮点逻辑。

因此 Cardputer Host 应让一个固定核、高优先级 FreeRTOS audio task 调用
`RealtimeEngine::render`，再完成 float 到 I2S PCM 的有界转换/写入；ISR 只做最小通知。显示、
键盘、SD、网络和日志放在控制任务，不进入 ISR 或 render 路径。

## 4. 推荐的产品与架构边界

建议的本地运行关系如下：

```text
Desktop / Creator Web
  Project Truth -> Cook / prepare
       |
       | versioned embedded runtime package（尚需产品/Contract 决策）
       v
Cardputer Adv Host
  ├─ Input/UI task: TCA8418 + LCD + Bank/Pattern controls
  ├─ Transfer/storage task: USB/Wi-Fi/microSD，非实时
  └─ Application Facade embedded runtime surface
       └─ RealtimeEngine embedded profile
            └─ high-priority audio task -> PCM conversion -> I2S DMA -> ES8311
```

这个方向必须保留现有架构不变量：

- Host 使用 Application Facade，不解析 Project Bundle；
- Project Truth 仍由 Creator/桌面端管理；
- 设备消费的 Runtime Snapshot/package 是不可变派生状态，不持久化为 Project Truth；
- Pattern event 仍引用 Pad Slot，不直接引用 Asset；
- Provider 选择与失败不进入 Project Truth；
- Cardputer 的引脚、codec 和任务 wiring 只进入新 Host/Product Assembly，不污染产品中立模块。

需要产品先批准而不能由 spike 静默决定的问题包括：

1. 是否允许一个能力少于桌面/Web Runtime 的 Embedded Profile；
2. runtime package 的 Contract、版本、完整性和传输方式；
3. 64 个逻辑 Pad 是否都必须随时本地可发声，还是只要求当前 16-Pad Bank 驻留；
4. 哪些 FX 必须存在，是否允许省略长历史 FX；
5. 最大 Sample 时长、同时 Voice 数和 SD streaming 行为；
6. 设备是否需要本地 Sequence 录制、麦克风采样与 Project Truth；
7. Wi-Fi/BLE 是否必须与演奏同时开启。

## 5. 建议的首期能力包络

为了让第一次真机验证回答“Core 能不能稳定发声”，而不是一次承担完整产品，建议采用以下
**测量起点**。这些数字不是正式 Contract：

| 能力 | Spike 起点 | 暂不进入首期 |
| --- | --- | --- |
| Pad | 4 个真实短样本；随后验证 16 个当前 Bank 输入 | 64 个长样本同时驻留 |
| Voice | 4 Voice 起步，逐级测到 8/16 | 直接承诺当前 128 Voice |
| Sample | 48 kHz PCM16，100–250 ms one-shot 起步 | 完整 float Bank、任意长样本 |
| Trigger mode | One Shot；稳定后加 Gate/Loop | 未测的长循环与多流随机 seek |
| FX | 先关闭；随后只评估低内存 FX | 当前完整 Master FX history |
| Sequence | 先只播放预生成 Pattern | 本地 durable 录制、恢复与编辑 |
| 存储 | 只读、有 hash 的 runtime package | 设备端 Project Bundle/Truth mutation |
| 网络 | 第一轮关闭，稳定后分别开启 Wi-Fi/BLE | 默认宣称无线共存无影响 |
| 麦克风 | 不进入第一轮 | 录音、裁剪、提交与回放全链 |

若产品不能接受这个能力包络，Cardputer Adv 不应进入本地 Runtime 实施；可以退回远程控制终端
路线，或选择带 PSRAM 的硬件。

## 6. 推荐 spike 与验收证据

### 6.1 Phase A：纯硬件 bring-up

1. 锁定 Cardputer Adv 硬件 revision、M5 库/示例 commit 和精确 ESP-IDF 版本；
2. 48 kHz、双声道、16-bit I2S 连续输出到 ES8311；
3. 同时驱动 LCD、TCA8418 和 microSD，记录 I2C/SPI 错误；
4. 输出 linker map、IRAM/DRAM/Flash 占用、最小 free heap、最大连续块和各 Task stack high-water
   mark；
5. 在扬声器与 3.5 mm 有线输出上完成听感与录音证据。

### 6.2 Phase B：最小 Core 集成

1. 新建 ESP-IDF component，只交叉编译获批的 Facade/runtime 子集；
2. 解决 64 位 atomic 阻断，证明 render 路径仍无锁、无分配、无阻塞；
3. 参数化固定容量并生成实际 `sizeof`、`.bss`、heap 和 stack 报告；
4. 播放 4 个短真实样本，验证 4、8、16 Voice 阶梯；
5. 记录每个 DMA 周期的 render 最大值、p99、p99.9、deadline overrun 和 underrun；
6. 依次叠加 LCD 刷新、键盘 burst、SD 读取、Wi-Fi 与 Flash/NVS 写入，不能把平均 CPU 当作
   实时证据。

48 kHz 下，128-frame DMA 周期约为 2.67 ms，256-frame 周期约为 5.33 ms。测量必须以所选
DMA 周期的 deadline 为准，并为 PCM 转换和 driver 写入保留余量。

### 6.3 Phase C：端到端产品证据

仓库已有 Web 物理输入基线是：500 次触发中零漏发、零重复；Touch-to-Sound p95 不高于
50 ms、p99 不高于 80 ms；前台 10 分钟零 underrun。Cardputer spike 可以复用它作为对照门槛，
但这不能替代仍待产品确认的
[Hardware Proof 阈值问题](../prd/questions/hardware-proof-thresholds.md)，也不能把 Web 决策静默
扩展为 Embedded Contract。

Cardputer 专用证据至少还应包括：

- 按键物理动作与有线音频起音的同一时间基准测量；
- 最少两小时连续演奏/Pattern 运行；
- SD 卡慢卡、拔卡、损坏 package 和 hash 不匹配的 fail-closed 行为；
- Wi-Fi/BLE 开启与关闭的独立结果；
- 电池供电、USB 供电、扬声器和耳机输出的独立结果；
- 过温、低电量和音频 route 变化时的明确状态与恢复行为。

### 6.4 Stop conditions

出现以下任一项时，应停止扩大范围并回到架构或硬件选择：

- 默认或裁剪后的最小引擎无法为系统、DMA 和控制任务留下可证明的 SRAM 余量；
- 音频热路径仍使用 ESP-IDF 模拟的 64 位 atomic/global spinlock；
- 4 Voice 已不能稳定满足 DMA deadline；
- SD 读取必须在 render/ISR 中阻塞才能避免断音；
- 设备端持久化无法满足获批的掉电/拔卡恢复语义；
- 为适配设备必须绕过 Application Facade、持久化 Runtime Snapshot，或使用已退休 Contract；
- 产品仍要求当前完整 Master FX、完整 Creator 或完整 Project/Provider 能力等价。

## 7. 风险登记

| 风险 | 概率 | 影响 | 当前处理建议 |
| --- | --- | --- | --- |
| 512 KiB SRAM 无法容纳有意义的本地样本集 | 高 | 致命 | PCM16 单表示、平台容量 profile、短样本或固定 read-ahead streaming |
| Master FX 历史缓冲超预算 | 确定 | 致命 | 首期禁用长历史 FX；另立低内存 FX 设计 |
| 64 位 atomic 破坏实时契约 | 确定 | 致命 | 32 位 lock-free/单写者重构并保留并发证明 |
| 多 Voice + PCM 转换超过 DMA deadline | 中 | 高 | 阶梯压测，先 4/8 Voice，再决定 16 Voice |
| SD 随机延迟造成 underrun | 中高 | 高 | 非实时预取、固定缓冲、读失败 fail closed、慢卡矩阵 |
| LCD/键盘/Wi-Fi 抢占音频任务 | 中 | 高 | 核绑定、优先级隔离、IRAM/DMA 配置、逐项共存测试 |
| 小屏 UI 不适合现有工作流 | 高 | 中 | 设计专用 Performance UI，不移植 Creator Web |
| 电池续航与扬声器热/功耗不达预期 | 未知 | 中 | 真机功耗曲线，不从额定容量推算产品续航 |
| ESP-IDF/M5 版本漂移或 codec 回归 | 中 | 中 | 锁定版本和 commit，保留最小 codec/I2S 回归固件 |

## 8. 最终建议

### 8.1 Go：把 Cardputer Adv 定位为验证平台

适合验证：

- 4×4 Pad 和 Bank/Pattern 键盘交互；
- Embedded Host 与 Facade 边界；
- 48 kHz I2S/ES8311 输出；
- 小容量实时引擎 profile；
- runtime package 传输、只读加载和 SD streaming 原型；
- 有线输出下的触发延迟与稳定性。

### 8.2 No-go：不要承诺当前产品等价运行

在 Cardputer Adv 上不应承诺：

- 当前 Creator Web 或 Web Runtime 直接运行；
- 当前默认 64 Pad/128 Voice/多 Bank 内存模型；
- 当前完整 Master FX；
- 设备端完整 Project Truth、Cook、Provider 与恢复语义；
- 不经真机证据即可继承桌面/Web 的音频质量与延迟结论。

### 8.3 一句话决策

**Cardputer Adv 值得作为 LMDJ 掌上演奏形态的硬件原型，但它验证的是一个新的、受约束的
Embedded Runtime Profile；如果目标是当前完整 Runtime 的功能等价，硬件必须升级到带 PSRAM
的平台。**

## 9. 资料来源与可复现性

### 9.1 LMDJ 仓库证据

- [通用 ESP32 可行性评估](2026-08-27-esp32-core-feasibility-assessment.md)
- [Audio Runtime 实时契约与容量](../../packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp)
- [Sample Bank 表示](../../packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp)
- [Sample Bank 准备实现](../../packages/audio-runtime/src/prepared_sample_bank.cpp)
- [Master FX 缓冲实现](../../packages/audio-runtime/src/master_fx.cpp)
- [Native Host Runtime 准备路径](../../apps/native-host/src/main.cpp)
- [Application Facade 构建依赖](../../packages/application-facade/CMakeLists.txt)
- [Project Storage Platform](../../packages/project-io/include/lmdj/project_io/storage_platform.hpp)
- [Web 物理输入验收阈值](../prd/decision-log.md)

### 9.2 外部一手资料

- [M5Stack Cardputer Adv 官方文档与 PinMap](https://docs.m5stack.com/en/core/Cardputer-Adv)
- [M5Stack Cardputer Adv 官方商店规格](https://shop.m5stack.com/products/m5stack-cardputer-adv-version-esp32-s3)
- [Espressif ESP32-S3 Datasheet v2.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)
- [ESP-IDF 5.5.1 C++ Support](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-guides/cplusplus.html)
- [ESP-IDF 5.5.1 I2S Driver](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/peripherals/i2s.html)
- [ESP-IDF 64-bit atomic 实现](https://github.com/espressif/esp-idf/blob/master/components/esp_libc/src/stdatomic.c)
- [M5Stack 官方 M5Cardputer 库](https://github.com/m5stack/M5Cardputer)
- [M5Stack 官方 Cardputer User Demo](https://github.com/m5stack/M5Cardputer-UserDemo)
- [M5Stack 官方 M5Unified 音频实现](https://github.com/m5stack/M5Unified/blob/master/src/M5Unified.cpp)

外部资料检索日期为 2026-09-03。正式 spike 必须把硬件 revision、ESP-IDF、M5 库和所有外部
依赖锁到精确版本/commit，不能以 `latest` 或 `master` 作为可复现证据。

## 10. Version Management 与 Documentation Impact

- Version impact: none。本文只增加研究资料，不改变 Product Build、Core Module、Host、Provider、
  Contract、Product Assembly 或运行时行为。
- Documentation impact: none。本文记录候选硬件与未来方案，不改变 Architecture Portal 的当前
  产品事实、能力状态、公开边界或源图。若后续批准 Embedded Host、embedded runtime Contract、
  Module profile 或 Product Assembly 变更，必须在同一实施 Task 更新受影响 Portal 路由、源图与
  版本身份。
