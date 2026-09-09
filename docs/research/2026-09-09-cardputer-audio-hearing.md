# Cardputer ADV：有界 Core 听测与独立音量对照

日期：2026-09-09。结论：**指定 1000 Hz 素材的直出／Core 听感一致，两次复核通过；
独立音量对照通过。不是完整 Cardputer Host、正常音乐容量或发布验收。**

本文收束[文档 Task](../plans/2026-09-09-cardputer-audio-evidence.md)，衔接
[分配顺序修复](2026-09-09-cardputer-allocation-order.md)。后续外部探针没有修改
Core；采用的产品源码为已提交的
`32d8ff6f48d7215aaa7fdf9b56ea8b9c5c49c268`，不是本文的文档 revision 或移动的
current main。该分配修复由 [PR #1085](https://github.com/endaye/lmdj/pull/1085)
squash 合入；其合入本身不提供听测证明。

## 1. 观察顺序与未被覆盖的旧结果

| 阶段 | 数字证据与改变范围 | 操作者观察及结论 |
| --- | --- | --- |
| 早期 format/gain-only Core 探针 | `cardputer-core-audible.JQooxa`；70 项旅程检查通过，显式设置 codec 格式与增益，但没有静音时钟预热 | 只听到三声、相隔几秒，最后一声很弱；不符合两组各四声的预期，听测不通过 |
| Core 时钟顺序对照 | `cardputer-core-timing.YrVdeX`；74 项检查通过，仅调整预热及静音／停钟顺序，保留 480 Hz／50 ms 素材与增益 | 能听到预期两组短音，但仍很轻；顺序是需要保留的 Host 行为，不据此断言先前三声一定是启停杂音 |
| 同 PCM 的 480 Hz 直出／Core 对照 | `cardputer-pcm-compare.4INZ96`；100 项检查及幅度统计一致 | 三组均听见、响度相近，但都很轻；未发现此素材在 Core 路径额外衰减 |
| 仅延长 480 Hz 音长 | `speaker-duration.YV6zts`；三对 50／750 ms，峰值与 codec 设置不变；45 项检查通过 | 六声符合顺序，但仍很轻；延长音长未解决这次听感问题 |
| 仅改变频率 | F1；两轮 480／1000／1500 Hz，均 750 ms、峰值 4095；44 项检查通过 | “后两声明显更响和更清楚”；频率影响可听程度，但未测得具体扬声器频响 |
| 固定 1000 Hz 回到 Core | C1；一次直出、两次完整 Core 旅程，每组四声 50 ms；两次 reset 各 100 项检查通过 | 首次确认“一致”，原样重播后确认“三次一致”；两次均指三个组的响度和清晰度一致 |
| 固定 1000 Hz 的独立音量对照 | L1；两轮峰值 4095 → 8190 → 4095，每声 750 ms；44 项检查通过 | “两轮三声都正常，符合预期，没有刺耳和破音”；只通过这次音量模式与主观质量观察 |

此前独立诊断还使用过峰值 8192 的档位，因此 L1 的 8190 没有超出先前听过的
数字幅度上限。这不是声压安全限值。原诊断的早期主机身份校验曾失败：固件只打印
九字符 ELF 摘要，不能满足完整摘要比较；即使 `DIAG_END` 为零也不算身份验证通过。
该失败记录没有改写，本文正向证据使用打印完整 32-byte ELF SHA-256 的后续镜像。

各外部 `RESULTS.md` 和串口的 `hearing=PENDING` 是当时的自动化记录，工具不会
自行证明听感。上表是之后由用户明确反馈补充的人工证据；不修改原始日志，
不把后来镜像的确认反填成早期镜像的 PASS。

## 2. 最终正向证据身份

输出路线为同一台 Cardputer ADV 的内置扬声器，用户确认未插耳机。ESP32-S3、
8 MiB Flash、无 PSRAM；EIM 管理的 ESP-IDF v6.1，
SDK revision `fff9895c82d744c7237be8847347bdd1b07c6643`，
Xtensa GCC 15.2.0（`esp-15.2.0_20251204`）。这是被测工具链身份，不是新选的
全产品版本。每次刷机前检查同一设备、原始完整 Flash 备份的长度／摘要及当时
镜像的 bootloader／partition／app 三个范围；私有设备标识与恢复镜像不公开。

| ID | 外部保留目录标识 | 镜像与运行范围 |
| --- | --- | --- |
| C1 | `cardputer-core-1khz.ss8JuD` | `cardputer-i2s-probe`；run-01 于 14:49:17 UTC 开始捕获，run-02 于 15:21:53 UTC 开始捕获；同一镜像原样重播 |
| F1 | `speaker-frequency.2aR05T` | `speaker-diagnostic`；run-01，两轮频率对照；不链接 Core |
| L1 | `speaker-level.8RiFWW` | `speaker-diagnostic`；run-01，两轮幅度对照；不链接 Core |

完整镜像与原始串口记录身份如下；字节数为文件实际长度，不是 Flash 分区大小：

| 文件 | Bytes | SHA-256 |
| --- | ---: | --- |
| C1 ELF | 29011520 | `9d976a714ec10d203a64b362b0bd2ea95767dd2490a054ac55d7d02eb448858d` |
| C1 app bin | 568496 | `c470d366de5f16e22613cb0d09b2190e57bb1ba606371cd468e660e5fbcc0ca5` |
| C1 run-01.serial.log | 13687 | `cc8b7b9d1680adf3637e709d51a07c786ba3b86557d3d4e36d7087d46d670ba7` |
| C1 run-02.serial.log | 13674 | `5960be94c66e50defadea89459cfa630e3b8660bde531b7bfa7560cb7b33d45a` |
| F1 ELF | 4205172 | `1cde4699aee65f8897718c169fe356ade5f5ce09d2f726340c8a19d0c44ddaaf` |
| F1 app bin | 223120 | `2a6bcd12a91f68a28aaad32f98fb4318e2413f24dabab14afa92eab025d47c56` |
| F1 run-01.serial.log | 8111 | `5d36cb9be69f2467b515aa0e030e16a1a33054f36edb5c35c34ed14040517722` |
| L1 ELF | 4200732 | `3d1e5b71fc2d56c17a920e02793e8adce23b441f567bd8d4e33c3189b2eb6805` |
| L1 app bin | 222816 | `82456765f60a530ecbae8cf482dd891fadb869167c73a3f335b29c67420fbd68` |
| L1 run-01.serial.log | 8159 | `a05f0bd045e5f2156b3a6c356a12c25d482168e3f9daeca69f8d64633ce90682` |

C1 的全部 84 个 producer-tree 文件与上述提交相同，没有产品 overlay；全部
18 个产品 translation unit 编译、17 个 Facade roots 保留。有效 gnu++20，
Wall/Wextra/Wpedantic/Werror，没有 Wno 逃逸。外部 Host 只经 Runtime Facade
播放内容；构建前重新检查 native libraries，native producer 经真实 Facade
生成参考 PCM，不以直出发生器冒充 Core render。

C1 输入是 5008-byte RuntimeContent，SHA-256
`29b4127f0facf674b0e0e202bb4801628b2ca6c3d498b468ed9818c290880810`。
一个 One Shot Pad、无 Pattern events，mono 48 kHz／2400 frames／50 ms／1000 Hz；
native 检查确认 50 个周期。转换后的 stereo reference 为 12288 bytes，SHA-256
`67e6d7e0f1172c557d4f63b2a28420f860de65ea8c17e596bf4ac5d35fedfa41`，
其中 2400 帧音频后是已检查的零尾。直出只复制该参考的同一声道到左右两路。

## 3. C1 的完整旅程与实测边界

每次 reset 包含下列顺序；原有 checker 对顺序、完整身份和每腿结果逐项验证：

| 转换 | Far-side 证据 |
| --- | --- |
| 驱动／任务准备 → 内容装载 | I2C／I2S／DMA／task checks、`load`、`loaded_identity`；完整 digest 与 byte length |
| 静止的 Core audio worker → 直接播放 | `direct_audio_idle` 后单一 control owner 写 I2S；clock warmup、四次 direct tone、PCM 幅度、全量写入、零尾／静音／disable |
| ready → running → 时钟预热 | `start`、preclock mute、实际 DMA sent 至少 94 个 block，elapsed 至少 500000 µs；随后 codec readback，再开始播放 |
| 四次 Pad admission → 四次真实处理回执 | 每次 `pad_accepted` 对应同 epoch／sequence 的 `voice_started`，每个 sequence 仅一次；实际 PCM 非零、峰值与平方和匹配 |
| running → draining → stopped | request_stop／draining／stopped；至少 24 个 stopped zero blocks，控制侧先写／读回 mute，音频侧再排空 12 个 zero-tail blocks 并 disable |
| 音频退出 → unload | `audio_quiescent` 后读统计、软件静音断言；unload 后 empty、无 content identity 且 render 静音 |
| 错误 identity → 拒绝 → 正确同内容重载 | 修改 byte length 的 identity 被拒绝；empty／无 identity／静音，随后 `retry_load` 成功 |
| 第二次运行 → 最终退出 | 再完整执行四音／回执／stop／mute／unload；task、I2S、codec、bus 清理及 heap integrity 通过 |

两次 reset 各有两次 Core 旅程，共四次；每次 reset 的一次直出加两次 Core 输出，
其实际送给 I2S 的 PCM 汇总完全一致：

- 左／右 peak 均为 **4095**，每声平方和 17396212763、非零帧 2294；
  每组四声平方和 **69584851052**、非零帧 **9176**，左右 mismatch 为零。
- 每组 tone interval 为 9600 frames，RMS 约 **2692.2894**。
  这是测得的幅度汇总一致，不声称捕获了目标 Core 的逐字节完整流。
- 每次 Core 旅程 544 render blocks、12 个额外零尾、569344 bytes、556 次
  DMA sent 通知；无 short write、driver error、queue overflow、nonfinite PCM、
  stopped-silence violation 或测得的 processing deadline miss。
- 四次 Core 旅程 render-plus-conversion 最大值分别为
  **5277／5272／5285／5270 µs**，每 block 时长 5333.333 µs；
  最小余量约 **48.3 µs（0.91%）**。这是短时单声部探针，没有 p99.9、
  持续负载或物理 underrun 测量；DMA 通知无溢出不等于模拟输出无 underrun。

admission 仍为 **326465 bytes**，可用 cap **331176 bytes**，reserve
**32768 bytes**。幅度统计使 AudioStats 比早期时钟探针增加 40 bytes，linker
padding 由 99 降至 91 bytes，因此 heap start 实际只移动 32 bytes；没有降低 reserve。
每个 Core audio task 8192-byte stack 的观测剩余为 3972 bytes；cleanup 时 internal
heap free 347744、观测 minimum 43760、largest block 278528，PSRAM 为零，所有
heap integrity 端点通过。这些结果不是零泄漏或任意碎片化堆都可 admission 的保证。

## 4. 已验证的外部 Host 顺序，不是 Core 增益修复

被测配置为 I2C 0x18、SDA 8／SCL 9；I2S BCLK 41／WS 43／DOUT 42，无外部
MCLK pin，48 kHz stereo PCM16，六个 256-frame DMA buffers 共 6144 bytes。
codec 0x09 明确写入／读回 0x0C，播放时 0x32 为 0xBF；不把这些实验值自动
设为正式 Host 的默认值。

Host 保持 muted → enable I2S → 实际发送至少半秒静音时钟 → unmute/readback
→ PCM → stop／零块 → mute/readback → 排空零尾 → disable／quiesce → reclaim。
I2S 阻塞写在 Host task，codec 操作在串行 control task，ISR 只计数，不进入 Core
render。直出只在 Core audio worker 静止时接管 I2S，不增加第二个并发 owner。

初次 format 与 gain 同时改变，后来又调整时钟顺序，不能把其中任一项独自称为
已证明根因。随后才依次控制素材、音长、频率与幅度。1000 Hz 的最终对照支持：
**对该素材与配置，没有发现 Core 在送入 I2S 前额外压低幅度，听感与直出一致。**
它不证明物理 I2S 波形、DAC 电压、声压、频响、THD 或所有素材的音量正常。

C1 的原始素材约半幅，Host conversion 再乘 0.25，最终峰值约为 PCM16 满幅的
八分之一。这是保守的测试幅度，不是 Core 必须改大的证据。F1 的三个频率使用
共同发生器和相同 5 ms edge fades，数字 RMS 近乎相同，操作者仍听到高两声
更响／更清楚；这证明此场景的频率听感差异，不归因到某一具体硬件部件。

L1 固定 1000 Hz，仅把共同 baseline 的每个 integer PCM sample 乘二，然后返回
baseline；两轮每声 750 ms。实测 peak 4095／8190、平方和
299135380849／1196541523396、RMS 2882.5884／5765.1769，非零帧均 34499，
无左右 mismatch 或数字 clipping。操作者确认预期模式且无刺耳／破音；这不是
仪器失真测量，也不是已选定产品音量。

C1 没有采用 750 ms 素材：其现有 content limit 为 4096 frames，且在相同模型下
将 2400-frame 素材扩至 36000 frames，估算 admission 会从 326465 增至
729665 bytes，超过实测 cap。没有扩大限制或削减 reserve 来强行运行。
F1／L1 的独立长音不能作为 Core 长素材能力证明。

## 5. 记录保全、复核与下一门禁

文档收束时离线重跑 C1 `check-i2s.py run-01 run-02`，两次各 **100 checks**
及 **31 negative controls** 通过；F1 `check-output.py run-01` 为 **44／14**，
L1 为 **44／15**。同时逐项重新计算这三个目录共 37 份命令回执所指日志的
length／SHA-256，核对镜像／原始串口身份。复核没有再 reset、刷机或播放。
Native metrics／sine tests 的 ASan/UBSan、严格 target build 和原始失败记录均保留。

早期 same-PCM 探针曾把 heap shift 错假设为至少 40 bytes，preflight 因实际
32 bytes 而失败；修正为完整 BSS object 与 linker padding 差分后才通过。
这是检查器归因修正，不是修改预算或丢弃失败。旧 resource-refusal、编译失败、
短摘要校验失败、未符合预期的听测均继续保留。

源文件、工具、native reference、ELF/bin/map、原始 run／reset／flash 及命令回执
保留在上述外部目录；本文只发布可核对的摘要，不上传私有设备信息、备份或原始
Flash 数据。这些目录不是仓库拥有的可安装 Host，也没有正式 Product Build。
报告时设备保留 L1 独立测试镜像，完成后已静音；复位会重新播放诊断，
不是恢复原厂固件或进入产品 UI。

[B2 T5](../plans/2026-09-08-lmdj-esp32-runtime-only-b2.md) 仍需独立确认 transport、
信任与断连行为、Host／Assembly 身份、资源上限和完整设备验收。本文只重载同一
fixture，未验证换成新内容后的身份与声音；未走物理 Pad／Pattern 交互、传输断连、
产品复位恢复、正常音乐负载、端到端 latency、p99.9、仪器 underrun／模拟测量
或长时间稳定性。没有自动升级 T5、选择默认增益、修改 Core、分配版本、发布、
部署或清理任何旧证据。下一步是收敛最小 Host 的设计边界，而不是继续加大测试音量。
