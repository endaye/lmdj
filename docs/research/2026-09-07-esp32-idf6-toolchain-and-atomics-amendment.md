# ESP32 研究增补：ESP-IDF v6.1 工具链落点与 Xtensa atomic 的实际退化条件

> 研究日期：2026-09-07
>
> 用途：为 [2026-08-27 可行性评估](./2026-08-27-esp32-core-feasibility-assessment.md)
> 与 [2026-09-03 Cardputer Adv 分析](./2026-09-03-cardputer-adv-feasibility-analysis.md)
> 补两件在原文写作时无法核实的事实：本地 spike 的 ESP-IDF 版本落点，以及 Xtensa 上
> atomic 退化的精确触发条件。不回改原文正文，只在原文抬头加指针。
>
> 状态：已按上游发布 tag 逐字核对源码与 Kconfig。不是 spike 授权、Embedded Host 批准、
> Product Assembly 变更或硬件 SKU 决策。
>
> 证据边界：版本与 atomic 结论来自上游固定 tag 的源码核对；第 1.1、1.3 与 2.5 节另有
> Cardputer Adv 真机烧录与串口读回的证据。**未执行**任何时间测量、I2S 音频输出、
> linker map 归因或长时间压力测试，原文 10.2 节要求的证据一项都还没有产生。原文第 3 节
> 引用的是 `master` 分支链接，本增补一律引用固定 tag 路径。

## 0. 看过什么

| 位置 | 事实 |
| --- | --- |
| GitHub Releases 元数据 | `v6.1` 2026-08-27 stable；`v6.0` 2026-03-20；`v6.0.3` 2026-09-02；`v5.5.5` 2026-07-17；`v5.5` 2025-07-21 |
| `v6.1 tools/idf_py_actions/constants.py:41` | `SUPPORTED_TARGETS` 含 `esp32`、`esp32s3`；`PREVIEW_TARGETS` 为 `linux`、`esp32h21`、`esp32h4`、`esp32s31` |
| `v6.1 components/esp_libc/priv_include/esp_stdatomic.h` | 与 `v5.5.5 components/newlib/priv_include/esp_stdatomic.h` **字节相同**（296 行） |
| `v6.1 components/esp_libc/src/stdatomic.c` | 与 `v5.5.5 components/newlib/src/stdatomic.c` **字节相同** |
| `v6.1 components/esp_libc/Kconfig:212` | 与 `v5.5.5 components/newlib/Kconfig:210` 的 `default` 表达式逐字相同 |
| `v6.1 components/soc/esp32s3/include/soc/soc_caps.h:158` | `SOC_CPU_CORES_NUM 2` |
| M5Unified `0.2.21`（2026-08-26）`CMakeLists.txt:24` | `if (IDF_VERSION_MAJOR GREATER_EQUAL 6)` 分支存在 |
| M5GFX `0.2.28`（2026-08-25）`src/M5GFX.cpp:2565,2622` | `board_M5CardputerADV` 与自动识别路径存在 |
| M5Unified `0.2.21 src/M5Unified.hpp` | `_speaker_enabled_cb_cardputer_adv`、`_microphone_enabled_cb_cardputer_adv` 存在 |
| arduino-esp32 `3.3.11`（2026-07-22） | 底座为 IDF `5.5.5` |
| arduino-esp32 `4.0.0-alpha1`（2026-05-27） | 预发布，底座为 `release/v6.0` 分支，自述 “Due to incompatibilities with ESP-IDF6, some of the components are not yet available”（Matter、RainMaker） |
| M5Unified `.github/workflows/IDFBuild.yml` | 构建矩阵覆盖 esp32/esp32s3 的 IDF `6.0.2`，**只构建不运行**，不含 6.1 |
| `v6.1 components/esp_driver_spi/include/driver/spi_common.h:127` | 新增 `spi_bus_config_t::dma_burst_size`；`v6.0.3`、`v6.0`、`v5.5.5` 的同一头文件中不存在该字段 |
| M5GFX `0.2.28 src/lgfx/v1/platforms/esp32/common.cpp:841` | `memset(&buscfg, ~0u, sizeof(spi_bus_config_t))`，对 `data_io_default_level`（≥5.4）与 `isr_cpu_id`（≥5.2）有版本分支，无 6.1 分支 |
| Cardputer Adv `esptool flash-id` 读回 | `ESP32-S3 (QFN56) revision v0.2`；Features 为 `Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded Flash 8MB (GD)`，**无 Embedded PSRAM**；flash quad / 3.3 V；USB mode `USB-Serial/JTAG` |
| Cardputer Adv 串口读回（两个版本一致） | `board=24 M5CardputerADV`、`240x135`、speaker/mic enabled、`MALLOC_CAP_SPIRAM` 总量 `0`、`__cplusplus=202400`、`gcc 15.2.0` |

组件在 v6.0 从 `components/newlib/` 改名为 `components/esp_libc/`，两处 atomic 实现只是
随之搬迁，内容没有任何改动。

## 1. 版本落点：本地 spike 用 `v6.1`

原文第 13 节要求“正式 spike 必须锁定精确 ESP-IDF 版本、工具链和开发板”，但没有指定版本；
原文各处引用 5.5.1 文档只是写作时的检索痕迹，不构成版本决策。本增补记录的落点是
**`v6.1`**（2026-08-27，HEAD `fff9895c82d744c7237be8847347bdd1b07c6643`）。

这个落点**附带一项持续义务**，见 1.1 节：`v6.1` 上 M5GFX `0.2.28` 会在 `M5.begin()` 处
启动即崩，必须打一行补丁才能运行。`v6.0.3` 经实测无需补丁（1.3 节两列对照），但落点仍定
为 `v6.1`；因此补丁的持久化机制是这个决定的一部分，不是可选项。

选 6.x 而不是 5.5 线的理由：

- **两颗目标芯片都是一等支持。** Cardputer Adv 的 ESP32-S3 与手上的独立经典 ESP32 都在
  `SUPPORTED_TARGETS` 里，不属于 preview。
- **M5 生态在 6.x 上实测可用。** M5Unified `0.2.21` 与 M5GFX `0.2.28` 作为纯 ESP-IDF
  component（不需要 Arduino-as-component）在 `v6.1`（加 1.1 节那行补丁）与 `v6.0.3`
  （原样）上都完成了编译、运行、点亮屏幕、板型识别与音频外设检测，见 1.3 节。
- **只有 Arduino 路线卡在 5.5 线上。** arduino-esp32 稳定版 `3.3.11` 的底座是 IDF `5.5.5`，
  支持 IDF 6 的只有 `4.0.0-alpha1`，且自述有组件缺失。**因此“选 6.x”与“不走 Arduino
  路线”是同一个决定的两面**，不能分开取。
- **5.5 线已过 Service 期。** 按乐鑫的 12 个月 Service + 18 个月 Maintenance 政策，
  `v5.5`（2025-07-21）已进入只收高危与安全修复的 Maintenance 期，官方不建议新项目采用。

其余核对结果：

- **M5 库的 IDF6 分支是真的走到了。** M5Unified `0.2.21` 的 `CMakeLists.txt:24` 有显式的
  `IDF_VERSION_MAJOR >= 6` 依赖分支；配置日志打印的正是该分支的 requires 列表。
- **component manager 能按精确版本解析。** `dependencies.lock` 记录
  `m5gfx 0.2.28`（hash `a0d59be9…`）与 `m5unified 0.2.21`（hash `869d7193…`）。

需要一并接受的代价，全部来自 v6.0 的默认值变更，与生态无关：

| v6.0 变更 | 对本 Core 的影响 |
| --- | --- |
| 默认 C++ 标准升到 `gnu++26`（C 升到 `gnu23`） | 本 Core 要求 C++20，需显式覆盖标准 |
| 默认把 warning 当 error | C++20 代码在新标准下要清一轮告警才能编过 |
| 默认 libc 由 Newlib 改为 Picolibc | 落在原文第 7 节 `std::filesystem` 与持久化语义的不确定区域上 |
| legacy I2S/ADC/DAC/timer/PCNT/RMT/SDM/温度传感器驱动移除 | 新代码无影响；只约束第三方组件 |
| 最低 Python 3.10、CMake 3.22 | 本机 Python 3.11.15、CMake 4.4.2 已满足 |

### 1.1 `v6.1` 的附带义务：`dma_burst_size` 事故

`v6.1` 在 `spi_bus_config_t` 里新增了一个字段：

```c
uint32_t dma_burst_size; ///< DMA data burst size in bytes. Only used when DMA is enabled.
                         ///  Set to 0 to use driver default.
```

（`v6.1 components/esp_driver_spi/include/driver/spi_common.h:127`）

M5GFX 在 `src/lgfx/v1/platforms/esp32/common.cpp:841` 用 `memset(&buscfg, ~0u, sizeof(...))`
填充这个结构体——这是为了让各 `*_io_num` 变成 `-1`（未使用）的惯用写法。该函数对
`data_io_default_level`（≥5.4）和 `isr_cpu_id`（≥5.2）都有 `ESP_IDF_VERSION` 分支，但没有
6.1 这一格，于是新字段停在 `0xFFFFFFFF`，既不是 0 也不是任何芯片支持的 burst 值。

后果不是编译失败，而是启动即崩：

```
E gdma: gdma_config_transfer(425): invalid max_data_burst_size: 4294967295
E spi_common: alloc_dma_chan(319): config gdma tx transfer failed
Guru Meditation Error: Core  1 panic'ed (LoadProhibited).   EXCVADDR: 0x00000004
```

调用链（`addr2line` 解码）：`M5Unified::begin()` → `LGFX_Device::init()` →
`M5GFX::init_impl()` → `M5GFX::autodetect()` → `Bus_SPI::init()` → `lgfx::v1::spi::init()` →
`spi_bus_initialize()` → `spicommon_dma_chan_free()`，在最后一帧 panic。

字段只在 6.1 存在：

| ESP-IDF | `spi_bus_config_t` 有 `dma_burst_size` |
| --- | --- |
| v6.1 | 有 |
| v6.0.3 / v6.0 | 无 |
| v5.5.5 | 无 |

因此 `v6.0.3` 上 M5GFX 那句 `memset` 碰不到这个字段，**无需任何补丁即可运行**；
`v6.1` 上必须补。补丁本身是一行：

```cpp
#if defined (ESP_IDF_VERSION_VAL)
  #if (ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 1, 0))
        buscfg.dma_burst_size = 0;   // 0 = 驱动默认值
  #endif
#endif
```

**关键约束：这行补丁不能只改 `managed_components/`。** component manager 每次重新解析
依赖都会把该目录还原，补丁随之消失，而症状是启动即崩的 boot loop——不是编译失败，所以
不会在构建阶段被发现。

落点选 `v6.1` 因此必须给补丁一个持久化载体。已采用的是 `override_path`：M5GFX `0.2.28`
的 registry 副本落到工程内 `vendor/m5gfx`，只改一个文件，差异以 patch 文件留档，
`main/idf_component.yml` 把依赖指向该路径。干净重解依赖后 `dependencies.lock` 记录的是
`source: {path: vendor/m5gfx, type: local}`（本地来源，无 `component_hash`），
`managed_components/` 里不再出现 m5gfx——覆盖确实生效，而不只是声明。

被覆盖路径不受 registry 校验，因此 vendored 副本里的 `CHECKSUMS.json` 与被改文件不再
相符；patch 文件才是差异的记录。退役路径是：上游修复发布后删掉 vendored 副本、去掉
`override_path`、上浮版本、重跑冒烟检查。

**冒烟检查是这个机制的必要一半，并且经过双向验证。** 摘掉补丁之后 `idf.py build` **仍然
成功**——这正是该失败模式的要害，所以门必须建在真机上而不是构建上：

| | 补丁在 | 补丁被摘掉 |
| --- | --- | --- |
| `idf.py build` | 成功 | **仍然成功** |
| 冒烟检查退出码 | 0 | 1 |
| 15 秒内 boots / panics | 2 / 0 | 95 / 94 |

检查读 15 秒串口，断言无 `Guru Meditation`、重启次数不超过自身的复位序列、bring-up 报告
打印完整、板型识别为 `MATCH`；失败信息按 `why:` / `remedy:` 直接点名丢失的文件与那一行。
一个从未见过红色的门不能证明任何事，所以上表的右列是实际跑出来的，不是设计意图。

已报上游：[m5stack/M5GFX#278](https://github.com/m5stack/M5GFX/issues/278)。同时观察到
ESP-IDF 6.1 一侧的问题：`spi_bus_initialize()` 在自己的错误清理路径里 panic，而不是把
`alloc_dma_chan()` 已经产生的错误返回出来（`spicommon_dma_chan_free()` 解引用了从未完整
分配的 DMA 上下文）。这一条尚未向 Espressif 提交。

**这个事故的一般形状值得单独记住**：M5 的上游 CI（`IDFBuild.yml`）覆盖 6.0.2 且**只构建
不运行**，而“上游给结构体加一个字段”这件事不需要改任何源码就能编过——所以无论矩阵里加
多少个版本，build-only 的 CI 结构上都不可能发现这一类不兼容。“声明支持某个 major”与“在
该 major 的某个 minor 上能跑”是两件事。

### 1.2 实测新增的一条移植代价

`int32_t` 在 `xtensa-esp-elf` 上是 `long int`，不是 `int`。因此：

- 任何 `%d` 配 `int32_t` 的格式串在 v6.0 的 warnings-as-errors 下**直接编译失败**
  （`-Werror=format=`），而不是告警；
- 任何“`int32_t` 就是 `int`”的隐含假设（重载决议、模板特化、`std::is_same`）在这里不成立。

本 Core 大量使用 `std::int32_t`，所以这条会成规模出现。它不是 v6.0 引入的（是 xtensa 的
ABI 事实），只是被 warnings-as-errors 从“告警”提升为“编译失败”。上表那一行“清一轮告警”
因此偏轻描淡写。

### 1.3 Cardputer Adv 真机 bring-up 结果

一个只做板型识别与点屏的最小工程（不做任何测量），两个版本各刷一次同一块板：

| | `v6.1` | `v6.0.3` |
| --- | --- | --- |
| 编译 | 0 error 0 warning | 0 error 0 warning |
| **未打补丁运行** | **15 秒内 282 次 panic 重启** | **0 panic** |
| 需要 M5GFX 补丁 | 是 | **否** |
| `getBoard()` | 24 `board_M5CardputerADV`（打补丁后） | 24 `board_M5CardputerADV` |
| 屏幕 | 240×135 点亮，人工确认 | 240×135 点亮，人工确认 |
| speaker / mic | enabled / enabled | enabled / enabled |
| `MALLOC_CAP_SPIRAM` 总量 | 0 字节 | 0 字节 |
| 内部堆 free / 最大连续块 | 368820 / 311296 | 369760 / 311296 |
| `__cplusplus` | 202400 | 202400 |
| 编译器 | gcc 15.2.0 | gcc 15.2.0 |

因果是隔离过的：6.1 那一列除了 M5GFX 里加的那一行 `buscfg.dma_burst_size = 0`，其余完全
相同，282 次 panic 随之变成 0 次；6.0.3 这一列用的是全新工程副本与重新拉取的未打补丁
M5GFX（已核对 `memset(&buscfg, ~0u, ...)` 原样在 842 行）。

两列除“要不要补丁”外没有差异——编译器、C++ 标准、外设、堆都一致。也就是说 `v6.0.3`
本可以用少一个 minor 换掉这个补丁；落点仍定为 `v6.1`，代价就是 1.1 节那条持续义务由本
项目承担。本节记录的是这次权衡的实测底数，不是对结论的追认。

`__cplusplus` 读回 `202400` 也实测确认了 v6.0 的默认 C++ 标准变更确实生效。

**这里的数字不能当测量结果用。** `internal free` 与最大连续块是这个点屏 demo 的值，不是
Core 的内存预算；本节唯一的用途是回答“M5 路线在该版本上是否可用”。

### 1.4 ES8311 音频路径已出声

§5 此前只记到“`M5.Speaker` 报告 enabled”，那距离“音频链路通了”还有一段。现已在同一块
板子上出声，两条路径都由人工听音确认：

- `tone()`：M5Unified 自带发生器，最便宜的可听证明；
- `playRaw()`：**在设备上生成的 int16 PCM**，按 codec 自己的采样率喂入
  （10560 samples / 21120 字节 / 220 ms）。

第二条才是与本 Core 相关的那条——LMDJ 产出的是采样，不是音调。两条路径播放同一组
C-E-G-C，听感一致。

codec 侧的实际配置（`M5.Speaker.config()` 读回）：

| 项 | 值 | 说明 |
| --- | --- | --- |
| sample rate | 48000 Hz | 单声道 |
| `use_dac` | false | 走 I2S codec；ESP32-S3 本身没有 DAC |
| `buzzer` | false | 是真 codec 输出，不是蜂鸣器 |
| DMA | 8 × 256 samples | 48 kHz 下约 **42.7 ms** |
| mixer task | priority 2，core `-1`（未固定） | M5Unified 默认 |

**42.7 ms 的 DMA 深度是这里唯一有前瞻价值的数字**：它是 M5Unified 默认给出的缓冲量，
本 Core 的音频回调将来必须在这个约束内工作。它是配置读回值，不是测量结果。

**本节不产生任何时序结论。** 播放调用返回耗时稳定在 171–181 ms，而缓冲区是 220 ms；
六轮循环重复一致。最可能的解释是 `isPlaying()` 在最后一块 DMA 尚未排空时就已归零
（8 × 256 ≈ 42.7 ms 与该差值接近得可疑），但这需要真正的时序方法才能定论，而不是靠一个
5 ms 轮询的忙等循环。因此它被记为 §5 的一个开放问题，不作为 quiescence 语义的结论。

### 1.5 麦克风：ES8311 采集在 IDF 5.5.1 起的回归上，本板 6.0.3 与 6.1 均复现

`M5.Mic` 在 Cardputer Adv 上采不到声音。症状精确到位：每个样本恒为 `f_gain × (−1)`
（`magnification=16` 时为 `−8`），`distinct(512) = 1`，两个 I2S slot 相同，对声音毫无反应。
出厂固件的麦克风测试是有效的，所以硬件没有问题。

这不是新问题。上游已有同一硬件、同一症状、同一寄存器读回的报告并完成了版本二分：
[espressif/esp-idf#18621](https://github.com/espressif/esp-idf/issues/18621)（2026-05-14，
`Status: In Progress`）——ES8311 mic 在 **IDF v5.4.2 正常、v5.5.1 起恒定 `−8`/`−1`**，Espressif
的假设是 v5.4→v5.5 I2S 驱动重构后 MCLK 未到达 codec，正在等示波器数据。
[m5stack/uiflow-micropython#97](https://github.com/m5stack/uiflow-micropython/pull/97) 的变通
是把 IDF 钉回 5.4；[m5stack/M5Unified#184](https://github.com/m5stack/M5Unified/issues/184)
的末条评论把 Cardputer Adv 的静音麦克风明确指向了这个 IDF 回归。

本增补新增的数据点（上游只有 5.4.2 与 5.5.1）：

| ESP-IDF | ES8311 采集 | codec 寄存器读回 |
| --- | --- | --- |
| v6.0.3 | 恒定 `−8` | `00=80 01=BA 0D=01 0E=02 14=10 17=BF` |
| v6.1 | 恒定 `−8` | 同上 |

**回归至少覆盖 5.5.1 → 6.0.3 → 6.1**，与 IDF 6 的其它变化无关。

为把原因收窄到 IDF 层，以下假设逐一在真机上被排除（每次只动一个变量）：

| 假设 | 实验 | 结果 |
| --- | --- | --- |
| 采样率 / codec 时钟不匹配 | 16 kHz → 48 kHz | 完全相同的常数 |
| 软件增益不足 | `magnification` 16/32/64/128 | 精确成比例 `−8/−16/−32/−64`；源码 `f_gain = magnification/(over_sampling<<1)` |
| 扬声器占用共享 codec（[M5Unified#347](https://github.com/m5stack/M5Unified/issues/347)） | `cfg.internal_spk = false` | 仍恒定 |
| I2S 端口错配 | mic 改到扬声器的 `I2S_NUM_1` | 仍恒定 |
| 单声道读错 slot | 立体声读回 L/R | 两个 slot 都是 `−8` |
| 时钟启动前 `0x0D` 写入被吸收（[M5Unified#348](https://github.com/m5stack/M5Unified/pull/348)，仅 StopWatch 注册） | 时钟运行后补写 `0x0D=0x01` ×3 | `0D` 前后均读回 `01`，数据不变 |
| 模拟输入增益 / 数字麦路径 | `0x14 = 0x1A`，再 `0x14 = 0x50 (DMIC_ON)` | 寄存器写入生效（读回 `1A`/`50`），数据不变 |

I2C 通路正常（扬声器走同一总线且正常出声；所有写入都能读回）、BCLK/WS 存在（采集任务持续
返回数据块）、codec 寄存器处于 ADC 模式——但 ASDOUT（GPIO46）始终读到全 1。这和
#18621 的观察一致。

**对本研究的结论：** 麦克风在 IDF 6.x 上不可用不是 M5Unified 或 codec 配置能解决的，
而是 IDF I2S 层的开放回归；在上游修复前，本板的采集只能通过降到 IDF 5.4.x 获得，
这与 1 节选 6.x 的理由冲突。麦克风本来就不在第一轮范围内
（[2026-09-03 分析](./2026-09-03-cardputer-adv-feasibility-analysis.md)第 271 行），
因此不改变落点，只把这条记为已知外部阻断。

测试中也证实了两个与本板相关的 M5Unified 0.2.21 事实：Cardputer Adv 的 mic case 没有像
ChainCaptain 那样显式设置 `i2s_port`（扬声器在 `I2S_NUM_1`，mic 默认 `I2S_NUM_0`，两者共享
BCLK 41 / WS 43）；以及 #348 的 post-start 修复只注册给了 StopWatch。两者在本板上都不是
静音的原因，但在上游修复 IDF 回归后值得回头核对。

## 2. 修正：atomic 退化的条件比原文第 3 节记录的更宽

原文第 3 节说“64 位 atomic 由一个全局 `portMUX_TYPE` 自旋锁模拟”。这一句是对的，但只覆盖
了一半：**开启 SPIRAM 时，Xtensa 上 32 位及以下的 atomic 也会离开硬件路径。**

### 2.1 三条判定

1. **64 位无条件退化。** `esp_stdatomic.h:24` 是 `#define HAS_ATOMICS_64 0`，注释为
   “no 64-bit atomics on Xtensa”，不带任何条件。这一条与选型无关，原文 9.3 节的结论成立。
2. **32 位路径由一个 Kconfig 决定。** `esp_stdatomic.h:21`：

   ```c
   #define HAS_ATOMICS_32 ((XCHAL_HAVE_S32C1I == 1) && !CONFIG_STDATOMIC_S32C1I_SPIRAM_WORKAROUND)
   ```

   而 `components/esp_libc/Kconfig:212` 的默认值是：

   ```
   default SPIRAM && (IDF_TARGET_ESP32 || IDF_TARGET_ESP32S3) && !IDF_TOOLCHAIN_CLANG # TODO IDF-9032
   ```

   即在 ESP32 或 ESP32-S3 上、开了 SPIRAM、用 GCC 时**默认打开**，于是 `HAS_ATOMICS_32`
   变成 0，1/2/4 字节的 `__atomic_*` 全部改由软件实现。
3. **软件实现里有一次运行时地址判断。** 每个软件实现函数的开头是 `esp_stdatomic.h:54` 的：

   ```c
   #define _ATOMIC_IF_NOT_EXT_RAM() \
       if (!((uintptr_t)ptr >= SOC_EXTRAM_DATA_LOW && (uintptr_t) ptr < SOC_EXTRAM_DATA_HIGH))
   ```

   指针落在内部 RAM 时转发到 `components/esp_libc/src/port/xtensa/stdatomic_s32c1i.c`，那里
   用的是真硬件 S32C1I；只有落在外部 PSRAM 的对象才继续往下走锁路径。

锁路径本身在双核上是 `esp_stdatomic.h:47` 的 `portENTER_CRITICAL_SAFE(&s_atomic_lock)`，
`s_atomic_lock` 是 `stdatomic.c` 里唯一一个 `static portMUX_TYPE`：**关中断 + 一把全固件
共享的跨核自旋锁**。ESP32-S3 是双核（`SOC_CPU_CORES_NUM 2`），走的正是这条。

### 2.2 按目标分布

| 目标配置 | ≤4 字节 atomic | 64 位 atomic |
| --- | --- | --- |
| Cardputer Adv（ESP32-S3FN8，无 PSRAM） | 真硬件 S32C1I | 全局自旋锁 + 关中断 |
| 经典 ESP32 或 S3，**开 SPIRAM**，GCC | 跨模块函数调用 + 运行时地址判断；PSRAM 中的对象再吃全局锁 | 全局自旋锁 + 关中断 |
| 经典 ESP32 或 S3，不开 SPIRAM | 真硬件 S32C1I | 全局自旋锁 + 关中断 |

对热路径的实质影响是：开 PSRAM 且用 GCC 时，连一个 `std::atomic<std::uint32_t>` 的读写
都从“一条 S32C1I 指令”变成“跨模块函数调用 + 地址范围判断”，内联全部消失。

### 2.3 对原文两处结论的影响

- **原文第 3 节偏乐观。** 它只把 64 位 atomic 列为阻断项；实际上原文 10.1 节推荐的
  “ESP32-S3 + ≥8 MiB PSRAM”恰好是触发 32 位退化的组合。第 3 节给出的技术方向
  （64 位改 32 位 lock-free counter、availability mask 拆两个 32 位）在**开 PSRAM 时不能
  假定 32 位那一侧是免费的**，必须以真机测量为准。
- **原文 2026-09-03 分析中的内存约束与这里的干净路径同源。** Cardputer Adv 用
  `ESP32-S3FN8`，数据手册与 M5Stack 规格都表明既无封装内 PSRAM 也无板载 PSRAM，所以
  SPIRAM 不会开启，这个 workaround 在这块板上不触发。**512 KiB SRAM 的紧约束和 32 位
  atomic 路径的干净是同一个事实的两面**：这块板适合先量 atomic 与 callback deadline，
  不适合量内存预算。

### 2.4 手上两件硬件的落点

两件实物都落在 2.2 表的末行，即 ≤4 字节 atomic 走真硬件 S32C1I，只有 64 位仍是全局
自旋锁加关中断。

| 实物 | 判定依据 |
| --- | --- |
| Cardputer Adv | `ESP32-S3FN8` 无封装内 PSRAM，M5Stack 规格也未提供板载 PSRAM |
| 独立 `ESP-32S` 模组（芯片 `ESP32-D0WD-V3`） | 芯片无封装内 PSRAM；模组为 WROOM 级，无板载 PSRAM |

`ESP-32S` 是 Ai-Thinker 的**模组**丝印，不是乐鑫的芯片型号；它在规格与引脚上对应
Espressif `ESP-WROOM-32`。模组内的芯片读作 `ESP32-D0WD-V3`：经典 ESP32 的 ECO V3
版本（chip revision v3.0），双核 Xtensa LX6、520 KiB 片上 SRAM，模组侧常见 4 MiB flash。

PSRAM 由此双重定案。带封装内 PSRAM 的经典 ESP32 变体在料号里带 `R`（例如
`ESP32-D0WDR2-V3`），`D0WD-V3` 不带，所以 PSRAM 只可能来自板载外挂；而 WROOM 级模组
不提供板载外挂 PSRAM，提供的那一类丝印会写 `WROVER`。

“裸模组”这一句仍是判定的必要部分，不能省。AI-Thinker 的 **ESP32-CAM** 板上贴的模组
丝印同样是 `ESP32-S`，芯片也可以是同一颗 `ESP32-D0WD-V3`，但那块板在模组内另配了
**4 MiB 外挂 PSRAM**，落在 2.2 表的中间一行。芯片料号与模组丝印都不足以单独定案，
必须连实物形态一起读：ESP32-CAM 认得出摄像头座子。

外挂 PSRAM 不写 efuse，所以 `esptool flash-id` 的 `Features` 行不报告它（`esptool.py` 与
`flash_id` 在 esptool 5.4.0 上均已弃用，改用 `esptool` 与 `flash-id`）。首次烧录时顺手
复核一次即可：开启 `CONFIG_SPIRAM` 的构建，启动日志不应出现 `esp_psram: Found ...`。
这是零成本的确认，不是阻塞项。

**Cardputer Adv 这一行已由真机确认。** 设备读回 `ESP32-S3 (QFN56) revision v0.2`，
Features 列出 `Embedded Flash 8MB (GD)` 而**没有** Embedded PSRAM；固件侧
`heap_caps_get_total_size(MALLOC_CAP_SPIRAM)` 在 `v6.1` 与 `v6.0.3` 上均读回 **0 字节**。
所以 `CONFIG_STDATOMIC_S32C1I_SPIRAM_WORKAROUND` 在这块板上确实不触发，2.2 表末行对它
成立，不再只是从料号推断。独立 `ESP-32S` 那一行仍是料号推断，尚未上电确认。

## 3. 未决线索：Clang 与 IDF-9032

上述 `default` 表达式带 `!IDF_TOOLCHAIN_CLANG`，且注释是 `# TODO IDF-9032`。这是上游的
未完成项，**不能读作“Clang 上 PSRAM 的 S32C1I 是安全的”**——更可能是 Clang 路径上这个
workaround 压根没有实现，问题仍在但没有保护。

这一条对本仓库尤其相关：Core 工具链刚从 Clang/LLVM 18 迁到 22（`45ea2312`，fixes #693）。
如果 ESP32 spike 也想用 Clang 工具链，必须先查清 IDF-9032 的实际内容，不得把
“Clang 下 workaround 不生效”当成绕过手段使用。

## 4. 本地环境：统一使用 EIM（macOS arm64）

> 2026-09-08 更新：本节取代原有的手动 ZIP 下载与 `install.sh` 安装步骤。

**ESP-IDF 统一通过 Espressif Installation Manager（EIM）下载、安装和管理。**
以后需要新的 ESP-IDF 版本或开发环境，也使用 EIM；不要另用手动 Git 克隆、ZIP 解压或
旧安装脚本建立平行安装。项目所需的精确版本由项目明确指定，安装方式不改变版本决策；
本 spike 仍使用第 1 节选定的 `v6.1`，不随 EIM 默认选项自动升级。

先在 EIM 中查看已有安装；缺少项目所需版本时，通过 EIM 界面选择该精确版本并完成安装。
已有对应版本时直接复用，不重复下载。终端按需进入环境：

```bash
eim list
eim shell v6.1
```

进入该 shell 后核对版本与源码身份：

```bash
idf.py --version
git -C "$IDF_PATH" describe --tags
git -C "$IDF_PATH" rev-parse HEAD
```

本 spike 的预期结果为 `ESP-IDF v6.1`、`v6.1` 与第 1 节记录的
`fff9895c82d744c7237be8847347bdd1b07c6643`。其他项目或后续获准的版本使用各自锁定的
身份，不套用这里的版本号。安装目录以 EIM 实际记录和激活后的 `IDF_PATH` 为准，
不把个人机器的绝对路径写进项目配置，也不在 shell profile 中自动激活旧 `export.sh`。

从旧安装切换时，保留项目源码、补丁和实验记录，重新生成引用旧 SDK 或 Python 路径的
构建缓存。清理旧 SDK 前检查本地改动与引用；共享工具链须确认 EIM 不再使用才能删除，
不能整目录删除 `~/.espressif`。第 1.1 节的 M5GFX 补丁义务仍然适用。

2026-09-08 本机检查：EIM 的 `v6.1` 状态为 `ok`，通过其环境运行 `idf.py --version`
与 Xtensa 编译器版本查询成功。这只证明环境可激活、工具可运行，不代表旧项目已经
重新编译或完成真机验收。原安装时记录的镜像速度只属于当时的网络观察，不再作为安装流程。

这套环境用于开发机上的外部 ESP32 工具链；`scripts/core.sh` 仍是宿主 Core 构建入口。

## 5. 仍未验证

- 本 Core 在 `gnu++26` + warnings-as-errors + Picolibc 下的编译结果。1.2 节只覆盖了格式串
  与 `int32_t` 这一类，Picolibc 与 `std::filesystem` 一侧完全没碰。
- ESP-IDF 6.1 一侧 `spi_bus_initialize()` 错误路径 panic 的问题尚未向 Espressif 提交。
- [M5GFX#278](https://github.com/m5stack/M5GFX/issues/278) 的上游处置结果。
- 任何 callback deadline、固件尺寸、峰值内存、linker map 归因或 underrun 数字。原文 10.2
  节要求的证据一项都还没有产生。1.3 节的堆数字来自一个点屏 demo，不能当测量结果引用。
- `M5.Speaker.isPlaying()` 的 quiescence 语义：它似乎在最后一块 DMA 排空前就归零
  （1.4 节）。这影响任何“等播放结束”的逻辑，需要用真正的时序方法确认，不能靠忙等观察。
- `M5.Mic` 采集：**已定性为 IDF I2S 回归**（1.5 节），等 [esp-idf#18621](https://github.com/espressif/esp-idf/issues/18621)。
  未验证的是"在 IDF 5.4.x 上本板确实正常"这一半——上游报告如此，本仓库没有复现。
- IDF-9032 的内容与状态。

## 6. 版本与文档

- Version impact: none。本文只增加研究资料，不改变 Product Build、Core Module、Host、
  Provider、Contract、Assembly 或运行时行为。ESP-IDF 与 M5 库版本是外部依赖的记录，不
  分配本仓库的任何版本身份。
- Documentation impact: none。改动只限 `docs/research/` 下三份研究文档；
  `apps/architecture-portal/docs` 下没有任何 `.mdx` 引用这些路径，也没有 Product Build 或
  Assembly 身份变更。若后续批准 Embedded Host 或 Product Assembly 变更，必须在同一实施
  Task 更新对应 Portal 路由并按版本政策处理身份。
- 本文不批准 spike、不批准硬件 SKU、不设定 Contract，也不回改原文的可行性分档与工期分档。
