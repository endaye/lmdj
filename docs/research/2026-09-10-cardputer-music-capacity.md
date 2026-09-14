# Cardputer 真实音乐容量：R1

日期：2026-09-10。结论：**BLOCKED — 当前常驻数据已超过目标片上 SRAM；
研究负结果，不进入该源码的真机长跑，不解除 H1/B1 容量依赖。**
关联 [R1 #1106](https://github.com/endaye/lmdj/issues/1106) 与
[Umbrella #1104](https://github.com/endaye/lmdj/issues/1104)。
目标遵循[已批准设计 §3](../design/2026-09-10-cardputer-runtime-host.md#3-固定验收口径)。

## Task 开始记录与文件边界

基线：`bd28364a6a95fd8b7a11a74184bcf917b410f1a6`。D1 已经合并；
本 Task 不实现 Core 优化、正式 Host，不分配 Build，不操作设备或发布。
先验证静态/构造/准备峰值；若容量拒绝，运行指标保持未测而非零。

封闭文件清单：

- `docs/research/2026-09-10-cardputer-music-capacity.md`
- `tests/fixtures/cardputer/music_fixture.py`
- `tests/fixtures/cardputer/music_fixture.json`
- `tests/fixtures/cardputer/README.md`
- `tests/build/cardputer_music_fixture_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/platform/native-audio.mdx`
- `scripts/ci/scope_policy.json`
- `tests/build/ci_change_scope_test.py`

相对 D1 清单增加后四项：两处 Portal 是 R1 Issue 已声明义务；新 fixture
前缀和测试文件没有现存 ownership，补 canonical routing 及其定向回归。
不新增 required gate，不改变现存阈值或删除任何 lane。
仓库外 probe 及回执在测量章节列出完整位置、身份、命令与退出码。

最低层验证：fixture 单事实测试（固定帧数/事件/PCM digest/可复现性）；
same-source Runtime Facade 与 Content codec 测试；目标严格编译/链接与 ABI
预算证据；stage 后 ownership、diff check；Portal 全检查。
fixture 测试防止以更短/单音内容替换已批准的容量负载，不证明听感或设备性能。

## 1. 同源音乐夹具与身份

[原创整数鼓音生成器](../../tests/fixtures/cardputer/music_fixture.py)和
[固定 manifest](../../tests/fixtures/cardputer/music_fixture.json)记录 CC0 素材、
PCM digest/长度和每个事件。A/B 各有 kick 12000、snare 12000、hat 4800、
clap 19200 mono frames，48 kHz PCM16，共 48000 frames / 96000 bytes；
120 BPM、4/4、两小节、PPQ 960、loop 7680 ticks、32 events。每个鼓音具有
非空衰减尾段；B 改变合成 seed/鼓身频率，保留事件表以隔离声音变化。
尚未由人耳确认这些合成鼓音的音色质量。

仓库外 `native.cpp` 用当前 Core encoder 生成内容，独立 Python wire reader
复核所有 PCM、Pad、事件和几何，不在 Python generator 复制 Content codec。
设备侧尚未接收这些 bytes。内容身份如下：

| 产物 | byte length | SHA-256 |
| --- | ---: | --- |
| A Runtime Content | 96808 | `2b3ae5e4f1a1753acfd9e3039439e7ae07c6e2fd885fd8375233184821009d63` |
| B Runtime Content | 96808 | `7ce684007a4d47e71a590a644f88ce0c81834c3343267e9682026e3a876424e9` |
| A native stereo PCM16 reference | 1536000 | `f2c219d884075378d5016ad9fa8a9fd0c5c64b73f5a4c54aa13dd5a88b39d38e` |
| B native stereo PCM16 reference | 1536000 | `806b6a1d4ab9761e55e27962b0ae794911a8dfde6b2b53333ec8bf672915d2af` |

各 reference 为 1500 blocks / 384000 frames / 8 秒，包含 Pattern 和两次
四 Pad 同 block press、中间 release；每次四个 `voice_started` receipt，
每个 variant 合计八个。render 全程禁止 C++ 普通/对齐分配，输出 finite、左右一致、
非静音；stop 后输出零，unload 后 empty，坏身份失败 empty，重载/reset 后 empty。
A/B 输出确实不同；它们在两个独立实例上运行，不冒充同实例 A → B 的设备换内容
旅程。receipt 不是精确峰值 active voice 数的测量；该指标随目标运行继续 pending。

## 2. 工具链、源码和链接边界

- 完整产品源码基线 `bd28364a6a95fd8b7a11a74184bcf917b410f1a6`；
  五个 package 的 86 个 tracked 文件逐个与该 Git object 比较，无 product overlay。
- EIM `v6.1` `[ok]`，ESP-IDF `fff9895c82d744c7237be8847347bdd1b07c6643`；
  Xtensa GCC `15.2.0` / `esp-15.2.0_20251204`。没有另装 SDK。
- native 从本工作区全新 configure/build 的实际五个 archive 链接；目标编译
  同一 18 个 producer translation units，保留全部 17 个公开 Runtime Facade
  链接根。完整 archive 编译不等于所有桌面函数都成为设备可达路径。
- 目标为 ESP32-S3、C++20、exceptions、无 PSRAM，控制栈配置 24576 bytes；
  18 个产品 TU 和 2 个 probe TU 均有效启用 `-Wall -Wextra -Wpedantic -Werror`
  与 `-fstack-usage`，展开 compiler response file 后确认没有 `-Wno-*`。
- 目标 probe 的 `app_main` 为空；其用途是严格链接和读取真实 ABI/DWARF。
  **没有执行目标 load，没有刷机，没有操作当前设备镜像或恢复备份。**

## 3. 资源分解与裁决

目标 ELF 给出 `sizeof(RuntimeFacade)=4`、private `Impl=8416`（DWARF）、
`RealtimeEngine=201024`、独立 receipt-bounded VoiceState storage `52416`。
四者合计 **261860 bytes fixed**；独立 storage 没有因为移出 `sizeof(Engine)` 被漏计。
按 unchanged `RuntimeFacade::load` 的公式、该 ABI 和真实 fixture footprint 得到：

| 准备峰值模型项 | ESP32-S3 bytes |
| --- | ---: |
| fixed | 261860 |
| encoded input | 96808 |
| decoded PCM16 | 96000 |
| prepared float | 192000 |
| metadata | 4107 |
| preparation workspace | 79528 |
| platform reserve 下限 | 32768 |
| 合计 admission | **763071** |

这是**目标 ABI 推导的模型，不是目标 allocator 的实测峰值**。更强的拒绝依据是：
成功 load 后当前实现同时持有 fixed、PCM16 Snapshot 与 float Bank，三项常驻
payload 下界就有 **549860 bytes**。Espressif 的
[ESP32-S3 硬件说明](https://www.espressif.com/en/chip/esp32-s3-en)列出 512 KiB
普通 SRAM、另有 16 KiB RTC SRAM；即使不现实地把两者全部当作可用 heap，
也只有 540672 bytes，仍小于该下界。无需借用旧探针的 331176-byte cap，
无需假装新 Host 的可用 heap 已实测，也无需通过刷机再触发一次已可确定的拒绝。

map 中 `.dram0.data=13067`、`.dram0.bss=7600`、`.iram0.text=48611`，仅表示
本空入口镜像的链接布局，**不是峰值 RAM 或可用 heap**。编译栈报告中 load 自身
2672 bytes、内部 Content decode 自身 6800 bytes，不是完整调用链 high-water；
完整 archive 的更大桌面函数栈不被误报为窄入口可达栈。目标 minimum/free heap、
largest block、任务 high-water、allocator 碎片/控制块和 DMA 未执行测量。
显示/键盘/USB 新 Host 成本仍须在既有 reserve 之外解释并实测，不能借它容纳内容。

### 桌面分配观测：与目标数据分开

AppleClang 原生执行使用记录 requested bytes 的普通/对齐 C++ allocation
instrument。两者正向控制都命中；它不覆盖直接 C `malloc`、allocator 内部记账、
进程 RSS 或目标 ABI。因此这些数字只诊断 Core 准备重叠，不推算目标可用内存。
A/B 相同：

| 原生时刻 | tracked requested bytes |
| --- | ---: |
| Facade 构造后 | 8432 |
| load 内准备峰值（输入 bytes 已在计数范围外） | 636856 |
| load 成功常驻 | 562576 |
| start 后 | 562608 |
| unload 后（Facade 与外部 epoch 仍活着） | 8464 |
| 相关对象全部销毁后 | 0 |

原生准备峰值加同时借用的 encoded input 为 733664 bytes，尚不含 allocator
记账和平台预留；原生 ABI admission 模型为 772339 bytes。原生 cap 524288 的
独立 load 实际返回 `budget_exceeded`、empty、无 published identity；这不是
ESP32-S3 上执行到的返回值。每个 variant 仅此诊断旅程，不宣称 100 周期无泄漏。

### 首次无效测量与修正

`native-reference.log` 首次报告常驻 301328、准备峰值 375608：测量器只拦截
普通 `operator new`，漏掉 over-aligned Engine/storage 分配，读数低于源码的
常驻 payload 下界，因此无效。保留原日志，不以退出码 0 当测量有效。
`native-reference-v2.log` 补齐全部对齐分配/释放及 123+456-byte 正向控制，
并由独立 verifier 断言常驻不低于 fixed+PCM+float，得到上表修正值。
首版 probe 源文件未在修改前单独冻结；该次读数不用于任何定量裁决。

`static-verification.log` 首次以 exit 1 拒绝未展开的 compiler response file；
v2 按编译目录解析 response 内容后重新检查全部有效 flags，未放松 warning policy。

## 4. 未执行指标与后续阻塞

以下值均为 **未测 / pending**，不是零，也不是 PASS：目标 callback/render+
conversion max/p99.9、真实 deadline miss/underrun、峰值 active voices、30 分钟
337500-block 稳定性、100 个完整资源周期、物理按键到模拟输出 p99/1000 次触发、
实际 heap minimum/largest block/stack high-water、DMA/键盘/显示/USB 同时负载，
以及成功装载后断线、接收失败丢弃、重连和 A → B 设备旅程。

容量阻塞转交 [紧凑存储设计 #1124](https://github.com/endaye/lmdj/issues/1124)：
先分别证明固定队列配置与 PCM/float 重复表示的根因，设计经独立评审，拆出
具体实现/复测 Task。不能在本研究提交中顺便改变队列、并发或音频表示。
H1 #1107、B1 #1110 必须等待原音乐目标的正向复测；R1 研究结案与 #1124
设计结案都不能按 Closed 状态自动解除该阻塞。
恢复条件是原 4 Pad/1 秒/32 events/4 声部目标在真实平台预算中通过，保留
reserve 和新 Host 开销，然后完成所有暂未执行的指标。桌面 128 voices、队列
能力、完整回执与所有已批准旅程不缩减。

## 5. 原始产物和命令回执

仓库外目录：`/Users/endaye/esp/lmdj-spike/cardputer-music-capacity.J7U8yn/`。
以下全部为本机保留的研究证据，不是发布资产；`run.py` 记录完整 argv、cwd、
UTC 开始、耗时、退出码以及 stdout/stderr 合并日志的 byte length/SHA-256。

| 命令/证据 | 实际范围与退出码 |
| --- | --- |
| `scripts/core.sh configure dev`；按目标构建 `lmdj_runtime_facade_tests lmdj_runtime_content_tests` | 全新 native 配置/构建，均 exit 0 |
| `ctest-baseline.json` | 3/3 CTest PASS，exit 0；fixture 内 12 tests，Facade main 14 scenarios、codec main 8 scenarios，不把它们混成单一测试数 |
| `native-build-v2.json`、`native-reference-v2.json` | 两个 variant 共 3000 blocks / 16 秒离线生成；2304090 次实际断言，exit 0；不是同数目的独立用例或实时长跑 |
| `independent-fixture.json` | 2 variants、34 checks，exit 0；使用既存独立 wire reader |
| `eim run 'idf.py build' v6.1` | 18 个产品 TU + 2 个 probe TU 严格编译/实际链接，exit 0；非设备测试 |
| `static-verification-v2.json` | 188 checks，exit 0；完整 source/flags/roots/ABI/fixture 验证，容量裁决仍 BLOCKED |
| `toolchain.json` | IDF/compiler/SDK revision 查询 exit 0 |

首轮目标 configure 日志为 `build/log/idf_py_stdout_output_29710`，SHA-256
`b2e08337e9ba84bc302a0bb03032d4cd5d8c9754e0f27fea20b891721ef82298`；
完整 ninja 构建（含 bootloader）日志 `_31978` 的 SHA-256 为
`feccf3880dc56c639ec30cfcdb3b5e26f09ee6a2b0b51fab5d37f7ac903a3070`。
SDK 输出的默认 bool/rename Kconfig 提示保留，产品 warning policy 未关闭。

首次 Portal check 的 116 tests/44 pages/10 diagrams 均通过，随后在既有
`1.0.50.0` 的 snapshot provenance 失败，exit 1：缺 introducing commit
`c68790864970f46acaf7dd3fd532a580c0170668` 的 authenticated squash witness。
刷新后确认修复已在 [PR #1122](https://github.com/endaye/lmdj/pull/1122) 合入；
将本分支 fast-forward 到 `656d1786` 再验证，完整 staged Task patch 保持不变，
上述五个 package 相对被测源码的 diff 仍为空。不手写或重新冻结已有快照，
也不把该文档基线修复描述成产品容量修复。
复跑 Portal 全检查 exit 0：116 tests、44 pages、10 sources/20 diagram outputs、
匹配的既有 Build snapshot、TypeScript 和静态构建的 44 routes/内部链接全部通过。
fixture 12 tests、stage 后 ownership 70 tests 与 3 个相对文件链接也通过；
这些是研究提交验证，不增加任何目标设备 PASS。

| 核心证据文件 | byte length | SHA-256 |
| --- | ---: | --- |
| `static-verification-v2.log`（含 86 文件 source inventory、完整 artifact inventory） | 26988 | `65e65c6c6414d337966f8f27fcd8be7a2dd295ef47371fcd4ce35947e88d3d25` |
| `build/cardputer-music-capacity.elf` | 28171304 | `c656eb4f8a479e0e96e5238d5b76dc1f1258b2a6d16381a10769cf3685293c2b` |
| `build/cardputer-music-capacity.bin`（未刷写） | 491744 | `5ac73fcf2aa10bd7e3af92de78a80a3d2128a5220fdae0ac104263901477ee95` |
| `build/cardputer-music-capacity.map` | 19060366 | `f2b78f2ab6db44377ebb17f342d2091edffdabf615fd6da5372faa53c269765d` |

产物取回后必须先比对完整身份，再按 receipt 的 argv 重跑；生成器只写不存在的
输出目录，回执工具拒绝覆盖同名 run。无仪器或设备执行证据的指标继续保持空缺。

## Version Management

Version impact: none — 只增加研究夹具、证据与路径归属；不修改产品源码、
API/ABI、Contract 或 manifests。研究构建无正式 Product Build 身份。

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /platform/native-audio/
Reason: 更新指定源码/夹具的容量证据，不把研究结果扩大为正式设备支持。
Core 公共边界未变，无需改源图。

## Pitfall Impact

Pitfall impact: none — 保留首次失败及测量盲点，负研究结果不解除产品依赖；
尚无新增的非源码可推导流程缺陷。
