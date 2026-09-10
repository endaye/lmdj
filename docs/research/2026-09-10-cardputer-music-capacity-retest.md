# Cardputer 真实音乐容量 R2：保留旧失败与扫描修复后复测

日期：2026-09-10。Relates to #1131；Parent umbrella: #1104。

## 当前结论

下文 §1–§6 保留 `22a62ada` 的原 CPU 负结果；它不是当前源码的重复测量。
§7 新增已合入扫描修复 `6d4c6804` 的证据：同素材 native、完整目标 ABI 预算、
两轮各 100 次实际 I2S 生命周期均通过对应检查，最差服务加发布开销分别为
1876 / 1874 µs，低于未改变的 4266.666… µs 限额。另一次绑定独立镜像的
6 段音乐试听获操作者确认清楚、逐档变响，但有可接受的轻微“刺啦”声。

这些补齐了最低存储/短程 CPU/生命周期的正向技术证据，不是完整产品 PASS。
R2 的前置独立评审证据仍有缺口（§2、§7.1），本报告不自行豁免或按 merge 状态
补造批准；#1131 / #1176 的结案及 H1 进入条件须与评审证据分别核实。
完整 Host 的 USB/LCD/键盘成本、30 分钟、物理 underrun 和输入到模拟输出时延
仍未完成，不能因报告列出这些 gap 就视为风险已消除。

## 1. 原负结果裁决与边界

**PARTIAL / CPU_MARGIN_FAIL，不是正向容量准入。** M1/M2 后同一组原创 A/B
音乐可以在实际无 PSRAM 目标上完成装载、演奏、停止和卸载；但 240 MHz、O2、
真实 I2S DMA 的第三次短程旅程出现 CPU 余量失败。最差服务时间加观测发布开销为
4284 µs，超过原定 `256 / 48000 × 0.8 = 4266.666… µs`，未调高阈值。

R2 #1131 保持 OPEN，H1 #1107 / B1 #1110 的正向容量前置仍未满足。研究记录的
完成、存储修复的合并或前两次短程绿色均不解锁这些任务。需要独立定位并修复 CPU
根因（后续 [#1176](https://github.com/endaye/lmdj/issues/1176)），再以 exact merged
source 重跑同口径 R2。尚未执行完整 Host 的 30 分钟、
100 次 I2S 替换、物理按键到模拟输出时延或听感验收。

本报告沿用 [原设计](../design/2026-09-10-cardputer-runtime-host.md)、
[R1](2026-09-10-cardputer-music-capacity.md) 和
[D2/M1/M2/R2 计划](../plans/2026-09-10-runtime-compact-storage.md)：4 Pads、
48 kHz、总计 48000 mono PCM16 frames（96000 bytes）、32 Pattern events、
至少 4 实际声部、32768-byte platform reserve，均未缩减。30 分钟和 1000 次
物理时延采样的既定要求仍由完整产品验收兑现，不以 native 循环替代。

## 2. 被测身份与证据保管

被测产品源码为 `22a62ada74f8fb387240648b23973a0f1d9ce6ce`，即 M2 PR #1162
实际合入的 main revision；编译前和设备运行后核对 96 个受管源码/fixture 文件，
没有产品源码 overlay。M2 的实际 owner merge 是可验证事实，但不能补造此前
自动评审失败的通过证据：该 PR 的 review run `34438366412` attempt `1`
保留 `no-model-reviewed` 失败，本次未观察到可采纳的独立评审 attestation。
计划要求的前置评审证据缺口与实际已合并状态分别记录。

环境使用 EIM 管理的 ESP-IDF v6.1，SDK revision
`fff9895c82d744c7237be8847347bdd1b07c6643`；Xtensa GCC 15.2.0
`esp-15.2.0_20251204`。严格构建包含 18 个真实 producer translation units、
17 个 Runtime Facade public roots，C++20、`-Wall -Wextra -Wpedantic -Werror`，
无警告豁免、无 fast-math。静态 ABI 探针为 160 MHz / Og；下述 I2S 探针明确为
240 MHz / O2，两者不能混用时间测量。所有镜像均是研究探针，不是 Product Build。

保留的本机证据目录（不是公共下载地址）：

- Native/reference/静态 ABI：`/Users/endaye/esp/lmdj-spike/cardputer-capacity-r2.8BOCKa`。
- 真实 I2S：`/Users/endaye/esp/lmdj-spike/cardputer-capacity-i2s.u3pYjy`。

每个目录的 `run.py` 记录实际 argv、退出码与完整日志；静态目录的 `budget.log`
含预算及完整 artifact 清单，I2S 的 `strict-verification-01.log` 含 ELF、map、
config、compile commands、源码清单等完整哈希。原失败记录、原备份及中间 CPU
探针保留；本报告的 I2S 裁决仅引用以下指定镜像，不拼接不同镜像的最好数值。

| I2S 证据 | bytes | SHA-256 |
| --- | ---: | --- |
| ELF | 36627408 | `fd1310c6568a1206f3118885932a2dda5fc671a21195e8642cee03bf87c06c02` |
| app bin | 746272 | `f7d6bccc23bb14ebc94f6fb54baa5f094399719ec4b1e5c2a3009dad9ca66059` |
| map | 13091924 | `48e20cbfd41181b69aa55969aa571a724e8a94190cedd9afa3dfe9ea61c3e527` |
| sdkconfig | 91867 | `8d59bfa2d9aacafe7e00470af7fada734b167ab0aa8d9977f763a92e4cb1b65f` |
| 96-file source inventory | 18195 | `a99beea35e86ecd6bf0e0a3ba0977613f7e53cd88ffc156472ed2a216ab2b370` |
| `run-01.serial.log` | 523853 | `3cc03aa37d572c33abafdd8c74c29fa54f31985b0466cb9246ec0dc38f1811c7` |

I2S 的 `source-after-device-01` 和 `probe-after-device-01` 回执分别确认 96 个
受管文件及 22 个外部探针/fixture 条目未变。实际采集器为
`serial-capture-i2s.py`（SHA-256
`b8adc407922c164e68676ea62e2d0af516b53478c7a53401ccca4d486e518494`），
它的执行前哈希和 argv 单独保留，不虚称包含在先冻结的 22-file 清单中。
采集回执的历史字段 `rendered_cycles=0` 只计数旧 `RENDER` 前缀；原回执不改写。
`analyze-i2s.py` 从完整 `AUDIO` 与逐块 `TIMING` 行重新验证：3 cycles、
3016 music blocks、3407 总 EOF 行，24.333 秒采集。采集退出 0 仅表示日志完整，
不是 CPU 或容量 PASS。

## 3. 同素材 native reference 与完整生命周期

两份 RuntimeContent 都是 96808 bytes；独立 wire reader 对所有 PCM、Pad、
32 events 和完整 identity 做 34 项检查。8 秒 stereo PCM16 reference 各为
1536000 bytes，与 R1 的输出逐字节一致，A/B 输出互异。

| 内容 | RuntimeContent SHA-256 | 8 秒 reference SHA-256 |
| --- | --- | --- |
| A | `2b3ae5e4f1a1753acfd9e3039439e7ae07c6e2fd885fd8375233184821009d63` | `f2c219d884075378d5016ad9fa8a9fd0c5c64b73f5a4c54aa13dd5a88b39d38e` |
| B | `7ce684007a4d47e71a590a644f88ce0c81834c3343267e9682026e3a876424e9` | `806b6a1d4ab9761e55e27962b0ae794911a8dfde6b2b53333ec8bf672915d2af` |

Native 同一 Facade 的 100 次 A/B 交替旅程逐次验证：

1. 错 byte length、错 digest 分别拒绝，远端状态 Empty、无 identity、双声道静音。
2. 正确内容装载为 Ready，完整 identity 相等；start 后旧 epoch 被拒绝。
3. 4 个 live Pad 命令获得对应 epoch/sequence 回执；16 blocks 非零、有限、
   同内容重复输出 bit-exact，A/B 不同。回执数不冒充实际并发声部数。
4. request-stop → Draining → stop → Stopped，每步验证状态，停止后双声道静音。
5. unload 后 Empty、无内容 identity、poll 为 0；100 次卸载后的 tracked live
   bytes 均为 8464，最终析构后为 0；另验证 running reset 后 Empty 且静音。

普通/aligned allocation positive control 分别请求 123/456 bytes，合计 579
bytes/2 calls 后归零；render 内普通及 aligned new/delete 都禁止。每份内容
prepared 请求量 181248 bytes，准备峰值 181688 bytes；100 次循环峰值 181720
bytes，最终析构为 0。这是 C++ allocation requested bytes，不含 C malloc、
allocator overhead 或 RSS，编码输入另计；不是目标机 heap 测量。

`native-reference` 共 3536405 个 assertions，不能称作同数量独立测试。
`fixtures.cardputer_music`、`cooker.runtime_content`、`facade.runtime_facade`
精确 CTest 3/3 通过；fixture Python 12/12 通过，generator `--check` 通过。
本证据 Task 没有修改并发产品代码，不把这些定向检查表述为全量 CI 或 sanitizer 重跑。

## 4. 目标 ABI 预算与实际内存分别记录

目标 ELF 实测 `sizeof(RealtimeEngine)=40448`、Facade handle 4、Impl 8416、
Bank 2608 bytes，N=128 queue payload 20592 bytes。完整 admission 模型如下：

| 目标 ABI 预算项 | bytes |
| --- | ---: |
| fixed | 69460 |
| 编码输入 | 96808 |
| PCM16 | 96000 |
| prepared float | 0 |
| metadata | 4107 |
| preparation workspace | 3240 |
| platform reserve | 32768 |
| 合计 admission | 302383 |

这解决了 R1 的 763071-byte 准备模型不能装入的问题，但模型不是 heap PASS。
实际 I2S 镜像在 driver/queues/stacks 建立后、Facade 和输入分配前测得 cap
328664 bytes，三次 load 的 admission 都为 302383。编码内容保留完整 RAM 输入，
不是只用 flash 常量规避传输缓冲成本。

实际最低 free heap 58568 bytes；三次 loaded-with-input free heap 分别
59040/59012/59020，largest block 31744 bytes。最后一次卸载后 free heap
319992、largest block 159744；最终 driver/queue cleanup 后 free heap
351096、largest block 286720。heap integrity 检查通过，PSRAM 为 0。
Audio stack 分配 8192、最小剩余 3568 bytes；control stack 分配 24576，
post-load 剩余 13436 bytes。free heap 总量超过 reserve 不意味着可以满足任意
同等大小的连续分配，largest block 单独保留。尚无 USB、LCD、键盘完整 Host 成本。

## 5. 实际 I2S 方法、结果与不能推导的结论

研究镜像使用 48 kHz、stereo PCM16、6×256-frame DMA（6144 bytes），
BCLK 41、WS 43、DOUT 42、无 MCLK。该几何是研究配置，未选定为产品默认值。
I2S 创建/启用、GDMA IRQ 与 audio task 同在 core 1：SDK 在用户 EOF callback
之后才把可写 buffer 加入自己的 queue，同核保证 audio task 不抢在 ISR 返回前
调用 write。EOF callback 只记录时间/序号并发送有界事件；control 日志不在 audio
线程打印。实际 write 使用 timeout 0，拒绝 backlog、丢事件、短写等异常。

逐块测量从用户 EOF 时间戳到实际 DMA buffer readback，分别保留唤醒、Core render、
float→PCM16、write、校验和 wait-call wall time。write 完成后对实际 DMA buffer
做完整 PCM memcmp，并在后续 EOF 检查 buffer rotation 与 committed generation。
等待下一 EOF 的时间与 CPU 服务分开；观测记录发布的最大开销另加在最差服务上。
该保守和可能来自不同 blocks，不伪称同一块完整 CPU 实测值。

外部链接观察器只在 render 返回后执行 lock-free atomic 记录；实际调用重定向由
`observation-link-01` 反汇编回执验证。`Engine::telemetry()` 含 mutex，仅 control
线程读取；不在 audio callback 调用。三次观察到的实际 active voice 峰值均至少
为 6，采样间隔最大 10007/10009/10010 µs：这是采样下界，不是精确全程峰值。
此观察器不是产品 Host API，产品 Host 仍只能用 Facade。

| cycle / 内容 | music blocks | Core max / p99.9 µs | EOF→DMA verify max / p99.9 µs | 加发布开销的保守 max µs | 原 CPU 余量超限 blocks |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 / A | 1500 | 4034 / 3922 | 4224 / 4100 | 4232 | 0 |
| 1 / B | 1500 | 3947 / 3931 | 4150 / 4142 | 4157 | 0 |
| 2 / A | 16 | 4073 / 4073 | 4280 / 4280 | 4284 | 2 |

p99.9 为每次旅程自身 music blocks 的 nearest-rank，16-block 行没有长期统计
代表性。cycle 2 的两块即使不加发布开销也超过 4266.666… µs，因此结论不是由
保守相加单独制造。Core 是已测服务的主要耗时部分，但尚未通过函数级 profiling
确认具体算法根因；不能仅凭源码中的全容量扫描就宣布其为已证实瓶颈。

三次 EOF→refill 均未超过 5333.333… µs 一个周期；短写、PCM mismatch、buffer
rotation/generation witness、event drops/backlog、driver overflow、raw drop、
nonfinite 和 I2S enable/write/disable 错误计数均为 0。**这些不等于物理 underrun
为 0**：generation witness 在 EOF 采样，未测 buffer 被 DMA 开始读取的物理时刻，
也不包含硬件 IRQ 到用户 callback 前的开销。CLK/模拟输出没有同步外部仪器证据。

每次旅程完整断言 wrong identity 拒绝、正确 load、时钟 warmup、start、命令回执、
music finished、Draining、Stopped、静音、audio quiescent、zero tail、unload。
每次至少 500 ms warmup，停止后至少 24 个零块再加 12 个尾部零块，join 成功才
卸载/释放。第三次记录 CPU FAIL 后安全结束，不继续把未运行的余下 97 次记为通过。
控制线程触发 Pad 受实际调度影响，不要求与桌面固定触发 block 的整段输出相同。

原探针全程写 `0x32=0`，其 `mute_readback` 名称只证明该寄存器值回读成功，
不能证明显式 DAC mute 位已设置；先前把这一结果写成“codec 全程静音”并不严谨。
退出清理通过，实际 I2S 数字数据确已发送；该轮没有人工可听音乐确认，更没有
声压或音质 PASS。刷写前重新验证同一设备身份和
原 8 MiB 备份，前镜像三段比对通过；本镜像 bootloader/partition/app 三段回读
验证通过。当时设备留在这份低音量研究镜像，复位会重放研究测试，尚无 Product UI；
后续试听镜像与退出状态另见 §7.4，不把原始回执改写成新的 mute 证明。

## 6. 复核、后续与完成条件

I2S 目录的 `python3 analyze-i2s.py run-01` 从日志重算所有 max/p99.9、序号连续性、
music index、生命周期断言和 CPU 失败；`analysis-01` 成功指的是**验证负结果成功**。
`python3 test-analyze-i2s.py` 的 14 个反例通过，覆盖采集不完整/长度/摘要、丢失或
重复 timing、短写、DMA mismatch/witness、raw drop、不足 4 voices、遗漏停止或卸载、
伪造 CPU PASS、终结失败数；仅在内存注入反例，不重写原始回执。

后续 CPU Task #1176 须先固定红色重现与耗时归因，再声明最小产品改动和精确文件；
维持 128 voice 公共容量、既有 mix 顺序和完整生命周期，不缩减音乐/声部目标或
抬高频率/超时/性能阈值来变绿。实际修复必须经过对应 Core 回归和 exact-head review，
再对 merged source 新建 R2 探针重跑，旧失败证据永久保留。

R2 正向准入之外，H1 的完整输入/显示/USB/I2S 开销与恢复旅程、B1 的正式测试
Product Build 和 immutable Portal snapshot、A1 的完整 30 分钟/替换/物理时延/
主观听感仍是独立待办。本 Task 不分配版本、不发布 Release、不部署或提升 Channel。

## 7. 扫描修复后的 exact-source 复测

### 7.1 身份、源码闭包与评审边界

被测源码为 `6d4c68042eaf53bbfdc5f16c2398694fbf1c7dfb`，即
[PR #1178](https://github.com/endaye/lmdj/pull/1178) 的实际 main 合入提交。
96-file 闭包相对原负结果只有 `realtime_engine.hpp/.cpp` 改变；没有 fixture、
产品增益或其它 Core overlay。沿用 EIM SDK/GCC、240 MHz/O2、48 kHz、
6×256-frame DMA、原 128-voice 公共容量及原 reserve。严格编译再次覆盖 18 个
真实 translation units 与 17 个 Facade public roots，保持 C++20 与 warnings-as-errors。
报告工作树后来快进到 `1dcaf5621c06dcc908a222373a5e5b6bb2b19784`，仅增加
原 R2 报告及两页门户；`evidence-audit-01` 逐项核对 Git 中被测 revision 的全部
96 文件与当前实际字节相等，不冒称报告 HEAD 就是烧录源码。

PR #1178 的实际合入不等于独立评审 PASS：head
`e5e5eb0bf582224137866b5c1c9508baecfec77e` 的 review run `34456258170`
attempt 1 保留 `not-reviewed` / backend `runtime_failure`；本次 live 查询没有
review 或 owner 采纳记录。实现的归因与定向回归见该 PR 和
[扫描预算计划](../plans/2026-09-10-runtime-voice-scan-budget.md)。这些前置证据缺口
与下列新的实际技术结果分别陈述，不通过本报告追认评审，也不重复实现已合入的修复。

新本机证据目录：`/Users/endaye/esp/lmdj-spike/cardputer-capacity-postscan.bIfER9`。
命令均经 `run.py` 保留 argv、完整输出、退出码和 SHA-256；`strict-verification-01`
绑定 SDK/config/compile commands/ELF/map，`budget-01` 绑定 native/ABI，
`evidence-audit-01` 核对已有命令回执与原始日志，旧失败目录不删除、不覆盖。

| 新 I2S 证据 | bytes | SHA-256 |
| --- | ---: | --- |
| ELF | 36627392 | `3ece476fc5c9371b62c3f2402806cbce966aa4673c4571a0b267632a29955809` |
| app bin | 746240 | `50aa6771402412f50c33b3274b7516ab3736022e56d4c9502303786cd3c9bd19` |
| map | 13092556 | `37e1a23393b9fd2513144bb6fb76ed4f1c837aae0bab01acedef3cef7c0cfdfc` |
| 96-file source inventory | 18197 | `25c0c6386a0c9d783c2b63661bff9fb23789359b1f26acc0a9d7fed6037139c6` |
| `run-01.serial.log` | 2922448 | `48e0be7e3deb6f810d11c53f57ef48b46376d2c43a33b3920306c7aad27debff` |
| `run-02.serial.log` | 2922766 | `b5b9db718ca7c8a71c8a1838b9ee8b6a92c2e8aad4e291556fe6c682cb79c52f` |

### 7.2 Native、预算与目标实际资源

重新编译实际 Core producer 后，native 再执行 3536405 个 assertions，包括 §3
全部远端断言、ordinary/aligned allocator positive control 与同实例 100 次旅程。
新生成的 A/B RuntimeContent 和整段 reference 均逐字节等于设备实际嵌入的旧
fixture/reference；不是只对短 digest 做相等检查。独立 wire reader 34 项通过，
prepared 181248、准备峰值 181688、循环峰值 181720 bytes，卸载 8464、析构 0，
测量范围仍是 C++ requested allocation，不冒充目标 heap 或 C malloc 覆盖。

新 ELF 的 ABI 与 §4 完整模型相同，admission 仍为 302383 bytes，prepared float
为 0。两轮设备的全部 100 次装载都实测 cap 328664、admitted 302383，保留完整
96808-byte RAM 编码输入。每轮最低 free heap 58556，loaded free 59000–59040，
loaded largest block 31744 bytes。100 个卸载端点在 319992/320000 之间波动，
每轮首末净差 0；largest block 为 159744–180224，不能从总空闲推断连续分配能力。
最终 cleanup free 351096、largest 286720；全部 heap integrity 为 1、PSRAM 为 0。
最小 audio stack 剩余 3344/8192、control 剩余 13420/24576 bytes。
这些是有驱动、任务和观测开销的短程实测，仍不包括完整 USB/显示/键盘 Host 成本。

### 7.3 两轮实际 I2S 生命周期与时限

每轮均完成 100 次 A/B 交替：前两次各 1500 music blocks（各 8 秒），后 98 次
各 16 blocks，共 4568 music blocks；采集约 122.4 秒，含 warmup、静音尾部和
清理。第二轮独立复位重跑，不将它拼成一个连续 30 分钟旅程。

| 轮次 | music blocks / 全部 timing rows | Core max / p99.9 µs | EOF→DMA verify max / p99.9 µs | 加发布的保守 max µs |
| --- | ---: | ---: | ---: | ---: |
| run-01 | 4568 / 17670 | 1649 / 1647 | 1869 / 1868 | 1876 |
| run-02 | 4568 / 17672 | 1649 / 1647 | 1870 / 1868 | 1874 |

本表 p99.9 对各轮全部 4568 music blocks 取 nearest-rank；逐 cycle 的原统计保留在
`analysis-01/02.log`。所有 200 cycles 的 CPU 余量检查通过，未观察到 EOF→refill
超过一个周期；短写、PCM mismatch、rotation/witness、event/raw drops、driver
overflow、nonfinite 和 I2S 错误均为 0。每 cycle 实际 active voice 采样下界至少 6。
沿用 §5 的观测盲区：以上不是物理 underrun=0，不测 IRQ 前段或模拟输出。

两轮每次均验证坏 length/digest 拒绝 → 正确重试/load → warmup → start →
Pad 命令与回执 → music finished → Draining → Stopped → 零输出/尾部 →
audio quiescent/join → unload；旧 epoch 拒绝与最终 I2S/codec/bus cleanup 通过。
native 另覆盖 running reset 清空 identity；设备复位是另一次完整启动，不混称
同实例的 running-reset 断言。`analyze-i2s.py` 对两轮都通过，原采集器的
`capacity_acceptance=NOT_ESTABLISHED` 保持原样，采集成功不自行产生全产品批准。
`analysis-controls-01` 的 14 个坏证据反例均拒绝，覆盖完整性、hash/length、丢失/
重复 timing、短写、DMA 错误、低声部数、缺 stop/unload、伪造 CPU verdict 和
终结计数；只在内存修改反例，不改写原始证据。

### 7.4 独立短时音乐试听与残留杂音

容量探针 `0x32=0` 的读回不作为硬静音或音乐清晰度证明。后续试听在独立目录
`/Users/endaye/esp/lmdj-spike/cardputer-music-listen.krVCjm` 保留新严格构建和
bootloader/partition/app 三段烧录读回；Core 96-file 闭包与素材不变。
探针显式设置 DAC mute 位，等待操作者启动，具有独立停止输入；先做零播放的
stop-control 验证，再依次以 codec −12/−6/0 dB 各播放 A/B 两段 8 秒音乐，
PCM 输出 scale 固定 0.25。这是试听配置，不是正式 Host 默认档位或声压认证。

该镜像 ELF SHA-256 为
`4428a99d7ec4b1c93217daebe9824e9e19ad1cda20ce343f257a1ae5f5692ef1`；
`run-01.serial.log` 为 1506619 bytes / SHA-256
`9cf1d1eb5ce6a688bf3c8b3bd31ef4c92c4e93d9ad7b116c7890aba84a5c8d74`。
6 cycles / 9000 music blocks / 9786 timing rows 均通过数字检查，服务加发布最大
1710 µs、最低 free heap 58556 bytes；不与上表两轮容量镜像混算。

操作者确认逐渐变响、各段均能听清、后几段较洪亮，没有很强的破音，但有微弱
“刺啦”声，认为可以接受。完整原话单独绑定于 `run-01.human-feedback.md`
（SHA-256 `36071885bce42fff2bef39a6a4ae6dea2fd255ea4f8f44ba117b7e759a873979`）。
轻微杂音确实存在，原因未确定；不能把操作者对喇叭的推测写成硬件诊断。
结束的显式 mute、I2S/codec/bus cleanup 通过，当前设备不播放；复位等待启动输入。

### 7.5 复核与未完成交付

本轮重新执行 fixture generator `--check`、fixture Python 12/12，以及
`fixtures.cardputer_music`、`cooker.runtime_content`、`facade.runtime_facade`
定向 CTest；报告 Task 不修改产品并发代码，不声称重跑全部 sanitizer 或全量 CI。
文档的 docs_static/portal 检查与提交回执属于本 Task 的独立验证边界。

后续仍须完成前置和本报告的独立评审证据；H1 的 Facade-only Host、显式音量与
静音/错误恢复，I1 的真实输入显示，C1 的完整 USB 事务，B1 的正式 Build/快照，
以及 A1 的完整旅程、30 分钟/约 337500 blocks、1000 次物理按键到模拟输出测量
和真实音乐质量验收。轻微杂音须在完整 Host 验收中复查，不能仅凭本次主观可接受
关闭音质风险。本报告不分配版本、不发布、不部署，也不将任一原生子任务记为完成。

## Version Management

Version impact: none — 仅追加指定源码的研究证据，无产品源码、fixture、manifest、
ABI 或 Product Build 身份变更；不创建版本快照。

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /platform/native-audio/

Reason: 两页同步区分旧 CPU 负结果、修复后短程正向实测、人工试听反馈、评审缺口
和未完成产品验收；不以 Issue/merge 状态替代技术或批准证据。
