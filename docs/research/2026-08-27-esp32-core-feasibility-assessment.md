# LMDJ New Headless Core 在 ESP32 上的可行性评估

> 日期：2026-08-27
>
> 更新：2026-09-01 增补第 9 节目标芯片选型
>
> 评估对象：当前 New Headless Core 主线源码与 ESP-IDF 平台能力
>
> 文档性质：静态可行性研究，不是已批准的产品范围、实施计划、排期承诺或硬件选型
>
> 证据边界：尚未执行 ESP-IDF 交叉编译、固件烧录、I2S 真机输出或长时间压力测试

## 0. 结论先行

把当前完整 Core 原样迁移到 ESP32，难度高，估计为 **8/10**，不建议作为第一目标。

把 ESP32 定位为只消费运行时状态的实时播放设备，保留必要的 Application Facade、
Audio Runtime 和平台 Host，难度中等，估计为 **5/10**，具备明确可行性。

建议把目标分成三个不同问题：

| 目标 | 可行性 | 主要困难 | 一名熟悉 ESP-IDF 与实时音频的 C++ 工程师粗估 |
| --- | --- | --- | --- |
| Pad 触发、有限复音、I2S 输出 | 高 | 原子语义、容量裁剪、I2S Host | 4–8 周 |
| 加载 Project、Cook WAV、基础持久化 | 中 | 峰值内存、Storage Platform、掉电语义 | 8–16 周 |
| 完整 Facade、Project IO、Provider 全量迁移 | 低，且收益存疑 | 内存、文件系统、Provider 与构建图 | 3–6 个月以上 |

这些工期是风险分档，不是交付承诺。最终估算必须由真实硬件 spike 提供的固件尺寸、
峰值内存、callback 时间和 underrun 数据校准。

目标芯片见第 9 节：spike 选 ESP32-S3，ESP32-P4 记为升级路径，其余型号被初筛淘汰。

## 1. 评估范围

“Core 跑在 ESP32 上”至少有三种含义，不能混为同一个移植任务。

### 1.1 Runtime-only 设备

设备接收已经准备好的运行时输入，负责：

- Pad 输入与 Trigger 排队；
- Sample Bank 发布；
- Voice 生命周期；
- 48 kHz 双声道混音；
- I2S DMA 输出；
- 有界运行时 telemetry。

这是最推荐的范围。

### 1.2 Standalone 播放设备

除实时播放外，设备还读取 Project Truth、解析 Project Bundle、解码 WAV、执行 Cooker、
管理本地项目和恢复持久化状态。

这个范围技术上可能实现，但需要显著改造内存和存储路径。

### 1.3 完整 Headless Core

完整范围还包含 Provider SDK、Attempt Store、Product Assembly 中的 Provider、完整 Facade
命令与查询面、Bundle 导入导出和离线渲染等能力。它们不是一个采样播放设备的必要条件，
直接迁移会把平台工作放大为产品边界重构。

## 2. 当前 Core 中有利于 ESP32 的部分

### 2.1 实时线程纪律已经正确

`RealtimeEngine::render` 是唯一 Audio Thread 入口，现有契约明确规定它不得分配、释放、
加锁、阻塞或抛异常。这是 MCU 音频最重要的基础之一：

- [RealtimeEngine 线程契约](../../packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp)
- [固定容量 SPSC Queue](../../packages/audio-runtime/include/lmdj/audio/detail/fixed_spsc_queue.hpp)
- [实时混音循环](../../packages/audio-runtime/src/realtime_engine.cpp)

因此，核心混音行为不需要推倒重写；主要工作是让现有契约在 ESP32 的原子、内存和设备
模型上继续成立。

### 2.2 Core Module 边界适合增加平台实现

Audio Runtime 已经把通用 `RealtimeEngine` 与 Apple CoreAudio、Web AudioWorklet 分开。
Project IO 也公开了 `ProjectStoragePlatform` 抽象。这意味着可以增加 ESP32 I2S Host 和
ESP32 Storage Platform，而不应把 ESP-IDF API 写进产品中立模块的业务逻辑。

### 2.3 C++20 不是首要障碍

当前根构建要求 C++20。ESP-IDF 支持现代 C++，也支持大部分 `std::filesystem`，异常和
RTTI 则按配置启用。语言版本本身不是本次评估中的主要不可行因素；真正的风险是实时原子
语义、动态内存规模、构建图和平台能力。

来源：[ESP-IDF C++ Support](https://docs.espressif.com/projects/esp-idf/en/v5.4/esp32/api-guides/cplusplus.html)

## 3. 首要阻断：64 位原子不满足当前实时契约

当前 Audio Runtime 在编译期要求：

```cpp
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
```

同时，Audio Thread 会更新多个 64 位 telemetry 和 frame counter：

- `rendered_frames_`；
- `callback_count_`；
- Voice、Capture、Outcome 和 Bank 统计；
- 64 位 `availability_mask_`。

ESP-IDF 源码表明，在目标没有硬件 64 位原子时，64 位 atomic 由一个全局
`portMUX_TYPE` 自旋锁模拟。对 ESP32/ESP32-S3 这样的 32 位目标，这与当前
`is_always_lock_free` 要求不兼容；即使绕开静态断言，让 Audio Thread 进入全局自旋锁也
会破坏“不锁、不阻塞”的实时契约。

来源：
[ESP-IDF `stdatomic.c`](https://github.com/espressif/esp-idf/blob/master/components/esp_libc/src/stdatomic.c)

建议的技术方向是：

- Audio Thread 独占的累计 frame 使用普通 64 位值，只由 Audio Thread 写；
- 并发 telemetry 改成 32 位 lock-free counter，或只在 quiescence 后精确读取；
- 如必须并发读取 64 位值，使用两个 32 位 word 加序列戳，而不是平台模拟的 64 位 atomic；
- 64 Pad availability mask 拆成两个 32 位 atomic mask；
- SPSC Queue 的 producer/consumer index 保持原生 32 位 lock-free。

这是小范围架构调整，但属于必须完成的第一道门槛。它也无法通过选型规避：
整个 ESP32 家族都是 32 位架构，没有任何一颗芯片具备硬件 64 位原子，详见 9.3 节。

## 4. 内存评估

### 4.1 固定事件环已接近或超过内部 RAM 预算

当前默认容量包括：

| 结构 | 容量 |
| --- | ---: |
| Trigger / Control Queue | 1,024 |
| Capture Ring | 4,096 |
| Trigger Outcome Ring | 4,096 |
| Voice State Ring | 10,240 |
| Voice | 128 |
| Sample Bank Slot | 4 |

根据当前字段布局，以常见 32 位 ABI 的结构大小估算，仅事件 payload 就约
**0.4–0.5 MiB**，尚未计入原子对齐、Voice 数组、Sample Bank 元数据、任务栈、I2S DMA、
Wi-Fi/BLE 和 ESP-IDF 自身内存。

这不适合作为 ESP32 默认配置。容量应成为平台 profile，而不是修改所有平台共用的语义
常量。一个用于 spike 的起点可以是：

| 项目 | Spike 建议值 |
| --- | ---: |
| Voice | 16 或 32 |
| Trigger Queue | 128 或 256 |
| Capture Ring | 512 |
| Trigger Outcome Ring | 256 或 512 |
| Voice State Ring | 512 或 1,024 |
| Sample Bank Slot | 2 |

这些数值只是测量起点，不能在没有产品输入密度和 Capture 需求的情况下变成正式 Contract。

### 4.2 Float Sample Bank 是最大的动态内存消费者

当前 `PreparedSampleBank` 为 64 个 Pad 分别保存 `std::vector<float>`，固定 48 kHz 单声道。
由此可直接得到：

| 内容 | PCM 内存 |
| --- | ---: |
| 1 秒、单 Pad、float mono | 187.5 KiB |
| 5 秒、单 Pad、float mono | 937.5 KiB |
| 8 个五秒 Pad | 约 7.3 MiB |
| 64 个五秒 Pad | 约 58.6 MiB |

当前 Web 运行时测试使用的限制是单 Artifact 1 MiB、单 Pad 240,000 frames、单 Bank
64 MiB、活动 Bank 128 MiB。这些限制是 Web/桌面量级，不能直接复用为 ESP32 产品配置。

ESP32-S3 能映射外部 PSRAM，但实际模组容量远小于当前 64/128 MiB 上限。官方文档还指出：

- 大于约 32 KiB 的连续访问会超出缓存能力，性能退化；
- Flash cache 被禁用时，外部 RAM 也不可访问；
- DMA descriptor 不能放入 PSRAM；
- DMA 与 CPU 同时访问外部 RAM 时带宽受限。

来源：
[ESP32-S3 External RAM](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/external-ram.html)

因此，“所有 float PCM 放 PSRAM”只能作为实验起点，不能直接视为生产解法。尤其要验证
播放期间的 Flash/NVS 写入行为。

候选优化包括：

- PCM16 常驻，在混音时转换为 float，可将 Sample Bank 内存减半；
- 短样本常驻，长样本从 SD 卡或 Flash 经过有界 read-ahead buffer 流式读取；
- 由非实时任务提前解码，Audio Thread 只读取连续、不可变的块；
- I2S DMA buffer 和 descriptor 保留在内部 DMA-capable RAM；
- Bank publication 的最大同时存活字节数采用 ESP32 专用硬限制。

### 4.3 Cooker 的峰值内存也需要重做

当前 Cooker 路径会同时经历：

1. 完整 Artifact 字节；
2. 解码后的 PCM16 `PcmSample`；
3. 采样率转换后的 PCM16；
4. `PreparedSampleBank` 中的 float mono；
5. Bank 发布期间的新旧 Bank 重叠。

相关实现：

- [WAV 完整内存解码](../../packages/project-cooker/src/wav_reader.cpp)
- [Cooker decoded artifact cache](../../packages/project-cooker/src/project_cooker.cpp)
- [Float Sample Bank 准备](../../packages/audio-runtime/src/prepared_sample_bank.cpp)

所以 Standalone 范围不能只降低最终 Bank 限制，还必须降低解码期间的峰值和碎片化风险。

## 5. CPU 与实时音频评估

当前混音循环按 active voice × callback frames 执行。128 Voice、48 kHz 的理论上限是每秒
约 614 万次 voice-frame 混合，尚未加入事件扫描、ramp、状态发布、I2S 格式转换和系统任务。

对 ESP32-S3，这不是显然不可行的数量级，但必须用真实 callback deadline 判断，而不能用
平均 CPU 占用判断。建议首个目标限制为 16/32 Voice，并测量：

- callback 最大执行时间和 p99.9；
- I2S DMA underrun；
- Sample 数据位于 internal RAM 与 PSRAM 的差异；
- Wi-Fi/BLE 开启时的抖动；
- SD 读取和 Flash/NVS 写入时的行为；
- 连续运行至少数小时后的碎片化与稳定性。

ESP-IDF 提供标准 I2S 通道和 DMA 驱动，增加 I2S Host 本身不是最大风险。

来源：[ESP-IDF I2S Driver](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/i2s.html)

## 6. 构建系统与平台 Host

当前根 `CMakeLists.txt` 会无条件加入全部 Core Modules、Provider、测试、Web Host、CLI、
Native Host 和 Product Assembly，并查找 Bash 与 Python。这不是可直接嵌入 ESP-IDF
component graph 的构建入口。

ESP32 支持需要：

- 独立的 ESP-IDF component 或受控的 embedded build profile；
- 只链接目标需要的 Core Modules；
- 排除 Apple、Web、CLI、MCP、测试和 proof Provider；
- 保留现有桌面/Web CMake 行为；
- 在 CI 中增加 ESP-IDF 交叉编译和固件尺寸门槛。

这里的“ESP-IDF 交叉编译”是指在开发机上使用 Espressif 的 Xtensa/RISC-V 工具链，为目标
ESP32 生成固件。它能发现：

- C++/标准库与目标 ABI 是否兼容；
- 64 位 atomic 静态断言是否失败；
- POSIX API 和链接符号是否缺失；
- `.text`、`.rodata`、`.data`、`.bss` 和 IRAM 占用；
- 固件是否超过 Flash partition 或内部 RAM 预算。

交叉编译通过只证明“能生成固件”，不证明实时音频可用。之后仍必须烧录开发板并执行
I2S、延迟、underrun、压力与长时间运行测试。

## 7. Project IO 与持久化

`ProjectStoragePlatform` 已提供一个适合增加 ESP32 backend 的边界，但接口要求的不只是普通
文件读写，还包括：

- Writer lease；
- immutable create；
- complete replace；
- durable append；
- directory listing；
- tree validation；
- publish-directory-if-absent 的原子发布语义。

现有 native backend 使用 `openat`、`flock`、descriptor-relative traversal 等 POSIX 能力，
不能直接视为 ESP-IDF VFS 上等价可用。SPIFFS 还是平面命名，且垃圾回收可能令一次写操作
延迟数秒，不适合直接承载与实时播放并行的完整 Project IO 语义。

来源：

- [ESP-IDF Virtual Filesystem](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/storage/vfs.html)
- [ESP-IDF SPIFFS 限制](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/storage/spiffs.html)

如果产品要求 Standalone Project Truth，较合理的候选是 SD/FAT 或经过掉电测试的 LittleFS
方案，但每个 durable/atomic 条件都必须通过 fault-injection 和断电测试证明，不能只靠 API
名称推断。

另外，Foundation 的 artifact hash 路径当前在栈上创建 64 KiB buffer。ESP-IDF Task stack
通常远小于此值，这类桌面栈假设必须改为小块 buffer 或显式分配。

## 8. 推荐架构边界

建议增加一个正式的 **Embedded Runtime Profile**，而不是让 ESP32 Host 绕开 Facade 直接
调用内部模块。

推荐关系为：

```text
Desktop / Web authoring
        |
        | Project Truth -> cook / prepare
        v
Application Facade embedded runtime surface
        |
        | immutable transient Runtime Snapshot / runtime Artifact
        v
ESP32 Host -> RealtimeEngine -> I2S DMA -> DAC
```

它应保持现有架构不变量：

- Host 只使用 Application Facade；
- Host 不解析 Project Bundle；
- Project Truth 仍是权威创作状态；
- Runtime Snapshot 是不可变派生状态，不作为 Project Truth 持久化；
- Pattern event 仍引用 Pad Slot；
- Provider 选择属于 Host/Workspace 设置；
- 产品专用 ESP32 wiring 只进入 Product Assembly。

是否定义新的 runtime Artifact/传输 Contract、是否允许设备本地 Cook、以及断网时设备保存
何种状态，都是产品级 Contract 问题。本研究不替产品静默决定这些问题。

## 9. 目标芯片选型

ESP32 是一个芯片系列，不是一颗芯片。选型直接决定第 3 节的原子改造范围、第 4 节的内存
预算和第 5 节的 CPU 余量，因此必须在 spike 开始前收敛，否则测量对象无法固定。

### 9.1 家族全景

| 芯片 | 架构 / 核数 | 主频 | SRAM | PSRAM | FPU | I2S | 无线 |
| --- | --- | ---: | ---: | --- | :-: | :-: | --- |
| ESP32（经典） | Xtensa LX6 ×2 | 240 MHz | 520 KB | 支持 | 有 | 2 | WiFi 4 + BT Classic + BLE 4.2 |
| ESP32-S2 | Xtensa LX7 ×1 | 240 MHz | 320 KB | 支持 | 无 | 1 | 仅 WiFi 4 |
| ESP32-S3 | Xtensa LX7 ×2 | 240 MHz | 512 KB | 支持，Octal，模组常见 8 MB | 有，含向量指令 | 2 | WiFi 4 + BLE 5 |
| ESP32-P4 | RISC-V ×2 + LP 核 | 400 MHz | 768 KB + 8 KB TCM | 支持，最高 32 MB 封装内 | 有 | 3 | 无 |
| ESP32-S31 | RISC-V ×2，128-bit SIMD | 320 MHz | 512 KB | 支持，DDR PSRAM | 官方页面未声明 | 2 | WiFi 6 + BT Classic + BLE 5.4 + 802.15.4 + GbE MAC |
| ESP32-C2 | RISC-V ×1 | 120 MHz | 272 KB | 不支持 | 无 | 无 | WiFi 4 + BLE 5 |
| ESP32-C3 | RISC-V ×1 | 160 MHz | 400 KB | 不支持 | 无 | 1 | WiFi 4 + BLE 5 |
| ESP32-C5 | RISC-V ×1 | 240 MHz | 384 KB | 支持 | 无 | 1 | 双频 WiFi 6 + BLE 5 + 802.15.4 |
| ESP32-C6 | RISC-V ×1 | 160 MHz | 512 KB | 不支持 | 无 | 1 | WiFi 6 + BLE 5.3 + Thread/Zigbee |
| ESP32-C61 | RISC-V ×1 | 160 MHz | 320 KB | 支持 | 无 | 1 | WiFi 6 + BLE |
| ESP32-H2 | RISC-V ×1 | 96 MHz | 320 KB | 不支持 | 无 | 1 | 无 WiFi，BLE 5 + Thread/Zigbee |
| ESP32-H4 | RISC-V ×2 | 96 MHz | 384 KB | 未核对 | 有 | 1 | 无 WiFi，BLE 5.4 + 802.15.4 |

数据边界：上表用于选型初筛，取自 2026-09-01 检索到的乐鑫官方产品页、数据手册与开发者
门户。被初筛淘汰分档的外设数量仅作参考；进入 spike 的候选必须以锁定版本的数据手册复核。

来源：

- [Espressif Product Selector](https://products.espressif.com/)
- [Floating-Point Units on Espressif SoCs](https://developer.espressif.com/blog/2025/10/cores_with_fpu/)

### 9.2 初筛条件

本 Core 的实时播放路径给出四条硬性条件：

1. **必须有硬件 FPU。** `PreparedSampleBank` 保存 float，混音循环也按 float 执行；软件
   浮点无法满足 Audio Thread 的 callback deadline。乐鑫现有 FPU 均为单精度，`double`
   仍走软件实现，因此实时路径同样不应引入 `double`。
2. **必须支持外部 PSRAM。** 见 4.2 节：单个五秒 float Pad 约 937 KiB，任何一颗芯片的
   内部 SRAM 都装不下目标 Sample Set。
3. **必须有 I2S。** 产品需外接 I2S DAC 或 codec。经典 ESP32 与 ESP32-S2 上的内建 DAC
   为 8 位，不满足乐器产品的输出质量要求。
4. **属于算力档而非连接档。** 见第 5 节：混音循环规模需要双核与 240 MHz 以上主频。

仅条件 1 即可淘汰 ESP32-S2、C2、C3、C5、C6、C61、H2。其中 ESP32-C6 虽有 512 KB SRAM，
但无 FPU 且不支持 PSRAM，对本用途无价值。ESP32-H2 与 H4 属低功耗无线档，不满足条件 4。
经典 ESP32 满足条件 1 至 3，但内存与 PSRAM 地址空间比 ESP32-S3 更紧，9.4 节的结论不变。

### 9.3 换芯片解决不了 64 位原子

需要明确记录一条否定结论：**整个 ESP32 家族没有任何一颗芯片具备硬件 64 位原子。**
Xtensa LX6/LX7 与乐鑫全部 RISC-V 核心都是 32 位架构。32 位原子在 Xtensa 上由 `S32C1I`
条件存储提供，在 RISC-V 上由标准 `A` 扩展提供，两者都满足需求；但 64 位原子在两种架构
上都只能由 ESP-IDF 用全局自旋锁模拟。

因此第 3 节的阻断项是架构层面的事实，不是选型问题。无论最终选 ESP32-S3、ESP32-P4 还是
后续任何一颗乐鑫芯片，Audio Thread 上消除 64 位原子的改造都必须完成。

### 9.4 候选对比与建议

通过初筛的算力档候选为 ESP32-S3 与 ESP32-P4。

| 维度 | ESP32-S3 | ESP32-P4 |
| --- | --- | --- |
| 算力 | 双核 Xtensa LX7 240 MHz | 双核 RISC-V 400 MHz |
| 内部 SRAM | 512 KB | 768 KB + 8 KB TCM |
| PSRAM 上限 | 模组常见 8 MB | 最高 32 MB |
| I2S | 2 | 3 |
| 无线 | 自带 WiFi + BLE | 无，需外挂 ESP32-C6/C61 |
| 发布时间 | 2020-12 发布 | 2023-01 发布，2024 起供货 |
| 音频方向生态成熟度 | 高 | 低 |

建议维持 10.1 节的 ESP32-S3 起点，理由是变量隔离：spike 的目的是量出本 Core 自身的行为，
而 S3 的 ESP-IDF 支持、I2S codec 驱动与 PSRAM 调优经验最成熟，能把未知集中在我们的代码
上，而不是同时叠加平台本身的未知。

同时把 ESP32-P4 记为明确的升级路径。若第 11 节的产品问题最终指向 Standalone 范围、更多
Pad、更长 Sample 或设备端 Cook，S3 的 8 MB PSRAM 与 240 MHz 会先于架构成为约束，届时应
重新评估 P4；代价是增加一颗协处理无线芯片与相应的板级复杂度。这仍是选型问题，不改变
第 3、4、7 节的任何阻断项。

### 9.5 ESP32-S31 列为观察项，不进入本轮 spike

ESP32-S31 于 2026-07-27 宣布量产。它不适合作为本轮 spike 的目标：

- 官方零售渠道为乐鑫 AliExpress 店铺，首批开发板数量极少且很快售罄；
- 模组与开发板料号、flash/PSRAM 配置组合尚未公开文档化；
- ESP-IDF 支持刚起步，音频方向参考设计为零；
- 官方页面强调 128-bit SIMD，未声明传统 FPU，9.2 节条件 1 无法确认；
- SRAM 仍为 512 KB，主频 320 MHz；相对 S3 的提升集中在无线与影像/显示，不在本 Core 的
  瓶颈方向。

若产品后续需要 LE Audio 或以太网，应在其 FPU 情况、模组料号与 ESP-IDF 支持稳定后重新
评估，而不是在本轮 spike 中引入。

来源：
[ESP32-S31 Now in Mass Production](https://www.espressif.com/en/news/ESP32_S31_Mass_Production)

### 9.6 Xtensa 与 RISC-V 的长期取向

ESP32-C3 之后乐鑫发布的每一颗新芯片都是 RISC-V，ESP32-S3 是目前最后一颗 Xtensa 算力型
芯片。这不影响 S3 的短期可用性，但对长期投入有两点影响：

- **工具链**：Xtensa 依赖乐鑫维护的 GCC/LLVM 分叉，上游支持较晚且有限；RISC-V 是上游
  GCC/LLVM 的一等目标。C++20 特性、标准库更新与静态分析工具在 RISC-V 目标上跟进更快。
- **SIMD 不可移植**：若将来为混音内核编写 SIMD，Xtensa PIE 与 RISC-V 向量/DSP 扩展互不
  兼容，需分别实现。这应作为 Embedded Runtime Profile 的可选优化，不进入产品中立模块。

除此之外，ESP-IDF 已抹平两种架构在应用层的绝大部分差异，本 Core 是可移植 C++，架构本身
不应成为选型的主要理由；决定性因素仍是 9.4 节的内存、算力与生态成熟度。

## 10. 推荐的可行性 Spike

建议先做一个 1–2 周、有明确停止条件的真实硬件 spike。

### 10.1 建议硬件起点

- ESP32-S3；
- 至少 8 MiB PSRAM；
- 外置 I2S DAC 或 codec；
- 可选 SD 卡，用于测试流式 Sample；
- 固定开发板和 ESP-IDF 版本，避免测量对象漂移。

经典 ESP32 不建议作为第一个目标。它的内存和 PSRAM 地址空间更紧，会同时放大容量、缓存
和工具链风险。

选择 ESP32-S3 而非 ESP32-P4 或 ESP32-S31 的完整理由见 9.4 与 9.5 节；简言之，本轮 spike
要量的是本 Core 自身的行为，应把平台未知降到最低。购买开发板时须确认模组带 PSRAM，
即料号含 `R` 后缀（如 `ESP32-S3-WROOM-1-N8R8` 为 8 MB flash 加 8 MB PSRAM）；
不带该后缀的模组只有片上 512 KB SRAM，无法完成 9.2 节条件 2。

### 10.2 Spike 必须完成的证据

1. ESP-IDF 交叉编译选定 Core 子集；
2. 报告完整 linker map 和 `idf.py size`；
3. 解决 64 位 atomic 阻断，但不削弱 Audio Thread 实时契约；
4. 从 PSRAM 加载至少一个真实 Sample；
5. 48 kHz stereo I2S 连续输出；
6. 16 Voice 重叠播放；
7. 记录 callback 最大时间、p99.9 和 DMA underrun；
8. 分别在 Wi-Fi、SD 读取、Flash/NVS 写入下复测；
9. 运行至少两小时，不出现 crash、corruption 或不可解释的 heap 下降；
10. 输出下一阶段内存预算与明确 go/no-go 结论。

### 10.3 Stop conditions

出现以下任一结果时，不应直接扩大实现范围：

- Audio Thread 仍依赖模拟 64 位 atomic 或全局锁；
- 16 Voice 已无法稳定满足 callback deadline；
- 目标 Sample Set 无法在规定 PSRAM 内完成单/双 Bank publication；
- Flash 写入与 PSRAM Sample 播放无法形成安全生命周期；
- Storage Platform 无法满足批准范围内的掉电恢复语义；
- 为适配 ESP32 必须改变未批准的 Project/Runtime Contract。

## 11. 待产品确认的问题

在正式实施计划前至少需要回答：

1. “跑在 ESP32”指 Runtime-only、Standalone，还是完整 Core？
2. 目标芯片是经典 ESP32、ESP32-S3，还是其他系列？
3. 最大 Pad 数、单 Sample 时长和同时 Voice 数是多少？
4. 是否允许 PCM16、ADPCM 或流式 Sample，而不是 float 全量驻留？
5. 播放期间是否必须写 Project/Take/配置到 Flash？
6. 是否需要 Wi-Fi/BLE 与音频同时工作？
7. Project Truth 是否必须在设备上独立存在和编辑？
8. Runtime 输入通过 USB、Wi-Fi、BLE、SD 卡还是预装 Flash 到达设备？

这些答案会使任务规模相差数倍。

## 12. 结论与建议

推荐决策不是“移植整个 Core”，而是先验证一个受约束的 Embedded Runtime Profile：

- 选 ESP32-S3 与至少 8 MiB PSRAM；
- 保留 Facade 边界；
- 先支持有限 Pad、16/32 Voice 和 I2S；
- 参数化固定队列容量；
- 消除 Audio Thread 上的 64 位 atomic；
- 用 PCM16 或有界 streaming 控制 Sample 内存；
- 把完整 Project IO 和 Provider 留在后续独立决策中。

如果 spike 通过，ESP32 Runtime-only Host 是合理的产品方向。若产品要求设备同时承担完整
创作、Cook、持久化和 Provider，ESP32 会从平台移植演变为一次新的产品架构项目，应单独
立项，而不是被描述为普通 Host port。

## 13. 研究边界、版本与文档影响

- 资料检索日期：第 1 至 8 节为 2026-08-27，第 9 节为 2026-09-01。ESP-IDF latest/stable
  文档可能随版本更新，正式 spike 必须锁定精确 ESP-IDF 版本、工具链和开发板。
- 第 9 节的芯片参数取自乐鑫公开产品页、数据手册与开发者门户，未经实物核对；正式选型
  必须以锁定版本的数据手册和供货确认为准，被初筛淘汰型号的外设数量尤其只作参考。
- 本文的内存数字来自源码常量和字段布局估算，不替代目标 ABI 的 `sizeof`、linker map、
  heap trace 或真机测量。
- 本文没有批准新的 Contract、Embedded Host、Product Assembly 或硬件 SKU。第 9 节是选型
  建议与初筛依据，不是已批准的硬件决策。
- Version impact: none。本文只增加研究资料，不改变 Product Build、Core Module、Host、
  Provider、Contract、Assembly 或运行时行为。
- Documentation impact: none。本文不改变 Architecture Portal 的当前架构事实、页面或源图；
  若后续批准 Embedded Host 或 Product Assembly 变更，必须在同一实施 Task 更新对应 Portal
  路由并按版本政策处理身份。
