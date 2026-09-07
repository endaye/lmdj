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
> 证据边界：全部结论来自上游 tag 的静态源码核对与 GitHub Releases 元数据，未执行交叉
> 编译、烧录、I2S 真机输出或任何时间测量。原文第 3 节引用的是 `master` 分支链接，本
> 增补一律引用固定 tag 路径。

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

组件在 v6.0 从 `components/newlib/` 改名为 `components/esp_libc/`，两处 atomic 实现只是
随之搬迁，内容没有任何改动。

## 1. 版本落点：本地 spike 用 `v6.1`

原文第 13 节要求“正式 spike 必须锁定精确 ESP-IDF 版本、工具链和开发板”，但没有指定版本；
原文各处引用 5.5.1 文档只是写作时的检索痕迹，不构成版本决策。本增补记录的落点是 `v6.1`。

支持这个落点的核对结果：

- **两颗目标芯片都是一等支持。** Cardputer Adv 的 ESP32-S3 与手上的独立经典 ESP32 都在
  `SUPPORTED_TARGETS` 里，不属于 preview。
- **M5 生态已声明 IDF 6 支持。** M5Unified `0.2.21` 与 M5GFX `0.2.28` 都是发布版，前者的
  `CMakeLists.txt` 有显式的 `IDF_VERSION_MAJOR >= 6` 依赖分支，后者已含
  `board_M5CardputerADV` 与自动识别，M5Unified 里也已有 Cardputer Adv 的扬声器与麦克风
  回调。这两个库可以作为纯 ESP-IDF component 使用，不需要 Arduino-as-component。
- **只有 Arduino 路线卡在 5.5 线上。** arduino-esp32 稳定版 `3.3.11` 的底座是 IDF `5.5.5`，
  支持 IDF 6 的只有 `4.0.0-alpha1`，且自述有组件缺失。**因此“选 v6.1”与“不走 Arduino
  路线”是同一个决定的两面**，不能分开取。
- **5.5 线已过 Service 期。** 按乐鑫的 12 个月 Service + 18 个月 Maintenance 政策，
  `v5.5`（2025-07-21）已进入只收高危与安全修复的 Maintenance 期，官方不建议新项目采用。

需要一并接受的代价，全部来自 v6.0 的默认值变更，与生态无关：

| v6.0 变更 | 对本 Core 的影响 |
| --- | --- |
| 默认 C++ 标准升到 `gnu++26`（C 升到 `gnu23`） | 本 Core 要求 C++20，需显式覆盖标准 |
| 默认把 warning 当 error | C++20 代码在新标准下要清一轮告警才能编过 |
| 默认 libc 由 Newlib 改为 Picolibc | 落在原文第 7 节 `std::filesystem` 与持久化语义的不确定区域上 |
| legacy I2S/ADC/DAC/timer/PCNT/RMT/SDM/温度传感器驱动移除 | 新代码无影响；只约束第三方组件 |
| 最低 Python 3.10、CMake 3.22 | 本机 Python 3.11.15、CMake 4.4.2 已满足 |

M5 那两个库虽然**声明**了 IDF 6 支持，但这一路径尚无本仓库的实测证据。“M5Unified 在
v6.1 下能编过、能点亮屏、能出声”必须作为独立的前置验证步骤完成，不能与 Core 移植混在
同一次测量里。

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

## 3. 未决线索：Clang 与 IDF-9032

上述 `default` 表达式带 `!IDF_TOOLCHAIN_CLANG`，且注释是 `# TODO IDF-9032`。这是上游的
未完成项，**不能读作“Clang 上 PSRAM 的 S32C1I 是安全的”**——更可能是 Clang 路径上这个
workaround 压根没有实现，问题仍在但没有保护。

这一条对本仓库尤其相关：Core 工具链刚从 Clang/LLVM 18 迁到 22（`45ea2312`，fixes #693）。
如果 ESP32 spike 也想用 Clang 工具链，必须先查清 IDF-9032 的实际内容，不得把
“Clang 下 workaround 不生效”当成绕过手段使用。

## 4. 本地环境（macOS arm64）

```bash
brew install ninja dfu-util
mkdir -p ~/esp && cd ~/esp
git clone -b v6.1 --recursive https://github.com/espressif/esp-idf.git
cd ~/esp/esp-idf
./install.sh esp32s3,esp32     # 同时装 S3 与经典 ESP32 工具链
alias get_idf='. $HOME/esp/esp-idf/export.sh'
```

`export.sh` 不写进 shell profile，只用 alias 按需激活。ESP32-S3 有原生
USB-Serial/JTAG，macOS 不需要额外 USB 桥驱动。

这套环境与 `scripts/core.sh` 的宿主构建互不干扰：仓库内目前**没有**任何 ESP-IDF
component、target 或 CI 通道，本节只描述开发机上的外部工具链。

## 5. 仍未验证

- M5Unified `0.2.21` + M5GFX `0.2.28` 在 v6.1 下对 Cardputer Adv 的实际编译与运行结果。
- 本 Core 在 `gnu++26` + warnings-as-errors + Picolibc 下的编译结果。
- 手上那颗独立经典 ESP32 是否带 PSRAM，因而它落入 2.2 表的哪一行。见 5.1。
- 任何 callback deadline、固件尺寸、峰值内存或 underrun 数字。原文 10.2 节要求的证据一项
  都还没有产生。
- IDF-9032 的内容与状态。

### 5.1 `ESP-32S` 是模组丝印，不足以判定 PSRAM

手上那颗独立芯片的丝印是 `ESP-32S`。这不是乐鑫的芯片型号，而是 Ai-Thinker 的**模组**
丝印，规格与引脚同 Espressif `ESP-WROOM-32` 基本一致；模组内是经典 ESP32（双核
Xtensa LX6、520 KiB 片上 SRAM），常见 4 MiB flash。

关键歧义：AI-Thinker 的 **ESP32-CAM** 板上贴的也是丝印为 `ESP32-S` 的模组，而那块板带
**4 MiB 外部 PSRAM**。同一丝印因此对应 2.2 表的两行：

| 实物 | 落在 2.2 表 | ≤4 字节 atomic |
| --- | --- | --- |
| 裸 `ESP-32S` / `ESP-WROOM-32` 模组或 DevKit（无 PSRAM） | 末行 | 真硬件 S32C1I |
| ESP32-CAM（外挂 4 MiB PSRAM） | 中间行 | 开 SPIRAM 后退化为函数调用 + 地址判断 |

丝印与模组外观都不足以定论，必须在设备上读。外挂 PSRAM 不写 efuse，因此
`esptool.py -p <port> flash_id` 的 `Features` 行不会报告它，只能确认芯片型号、revision
与 flash 容量。定论方式是烧一个开启 `CONFIG_SPIRAM` 的固件并读启动日志：出现
`esp_psram: Found ...` 即有 PSRAM，检测失败即无。

在做出这一判定之前，不得把这颗芯片上的任何 atomic 或时序测量结果归因到 2.2 表的某一行。

## 6. 版本与文档

- Version impact: none。本文只增加研究资料，不改变 Product Build、Core Module、Host、
  Provider、Contract、Assembly 或运行时行为。ESP-IDF 与 M5 库版本是外部依赖的记录，不
  分配本仓库的任何版本身份。
- Documentation impact: none。改动只限 `docs/research/` 下三份研究文档；
  `apps/architecture-portal/docs` 下没有任何 `.mdx` 引用这些路径，也没有 Product Build 或
  Assembly 身份变更。若后续批准 Embedded Host 或 Product Assembly 变更，必须在同一实施
  Task 更新对应 Portal 路由并按版本政策处理身份。
- 本文不批准 spike、不批准硬件 SKU、不设定 Contract，也不回改原文的可行性分档与工期分档。
