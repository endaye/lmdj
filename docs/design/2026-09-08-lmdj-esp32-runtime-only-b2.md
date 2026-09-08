# ESP32 B2：Runtime-only 设计提案

日期：2026-09-08。
状态：**设计提案，未批准实施、未定义 active Contract、未实现。**

用户已同意进入“电脑准备内容、Cardputer 负责播放”的 B2 设计阶段，暂不移植完整
Project 存储。这是方向与设计工作的授权，不是本文新 API、线格式、并发协议、资源
上限或固件实施的批准。本文与[分阶段计划](../plans/2026-09-08-lmdj-esp32-runtime-only-b2.md)
一起供产品与架构评审；合入文档不自动批准其中的候选选择。

## 1. 权威与已知证据

- [Core redesign](2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)：
  Host 经 Application Facade，Project Truth 与 Runtime Snapshot 分离。
- [可行性评估 §7–11](../research/2026-08-27-esp32-core-feasibility-assessment.md)：
  Embedded Runtime Profile 是候选架构，容量、传输、持久化是待产品确认的问题。
- [A → B 原计划](../plans/2026-09-08-lmdj-esp32-render-probe.md) 与
  [已交付结果 §8–9](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)：
  A 为选定 14 个源文件完整编译/链接；B1 为 30/31 编译，阻塞于 native storage，
  没有 B1 ELF/map。B2 不把失败改记为成功，也不覆盖原始证据。
- 本次源码核对基线：`e403352322a1dfdfb0949d5d12c74df481dd148f`。
  这是设计输入的 revision，不是固件、Product Build 或验证候选身份。

目标实验设备是用户之前 bring-up 的 M5 Cardputer ADV。既有研究记录 ESP32-S3、
8 MB Flash、无 PSRAM；继续沿用 EIM 管理且精确固定的 IDF v6.1 工具链，不新建
平行 SDK。旧屏幕/PCM tone 演示只证明平台 bring-up，不证明 LMDJ 新路径可运行。

## 2. 职责边界

| 边界 | 提议承担 | 明确不承担 |
| --- | --- | --- |
| 电脑侧 Host → 完整 Facade | 选择 Project/revision、完成 authoring 与 Cook、发起派生运行内容导出 | Host 直接读取/解释 Project Bundle |
| 电脑侧 Core 导出器 | 固定源 revision，解析 Pad/Pattern、收集材料、校验与编码派生运行内容 | 将指针、C++ 内存布局或 mutable Project 当传输协议 |
| 设备 Host | 提供有界字节输入、设备生命周期、输入设备与音频驱动 | 解析 Project、解析运行内容业务字段、直接构造内部 Snapshot/Engine |
| 设备 Runtime Facade | 校验输入、预算 admission、构建不可变运行态、发布、播放控制与状态 | Project IO、Provider 执行、编辑/录制 Project Truth |
| 设备 Audio Runtime | 单 audio owner 执行 render；复用既有播放语义 | 文件/网络 IO、分配释放、等待锁或解析输入 |

```text
电脑 Host → 完整 Application Facade → Core Cook / 派生内容导出
                                      │ 有界、可校验字节
设备 Host ───────────────────────────→ Runtime Facade → Audio Runtime
    └─ I2S callback / DMA 生命周期 ──→ Facade render 入口 ──→ 驱动输出
```

“电脑准备”不等于电脑生成 ABI 内存镜像。接收端仍需做有界解码、验证、内存分配和
本地运行态准备；这些都在 control 侧，由 Core 负责，不是设备端 Project Cook。
产品专用 pin、驱动、资源配置与对象组合最终只归 Product Assembly；本轮不创建 Host
或 Assembly，也不把仓库外 probe 变成正式产品输入。

## 3. Facade 拆分：头文件与目标一起闭合

当前 `performance_runtime.hpp` 与 `performance_engine_adapter.hpp` 均包含
`application.hpp`；后者引入 Project IO / Provider 声明。`lmdj_application` 也 PUBLIC
链接这些库。因此单独取消一个 include 或期待 linker GC 不能证明 B2 依赖隔离。

候选拆分分两步：

1. 抽取现有 performance port 声明到独立 Facade 头文件；原 `application.hpp` 继续
   包含它，保持现有 namespace、签名和 include 使用兼容。Replay 声明已有独立头文件，
   不制造第二套相同协议。此步不承诺 ESP32 可链接。
2. 新增 storage-free 的 Runtime Facade 静态目标（名称待实施计划批准），完整 Facade
   单向依赖它；设备只依赖该子目标。移动源文件的所有权，不在两目标各自编译同一份
   实现。独立最小消费者只 include Runtime Facade 公共头并链接该目标。

公开设备边界使用字节输入、opaque session / generation handle、Pad Slot 控制、状态
和 render buffer；不要求 Host 持有 `RealtimeEngine&`、`RuntimeSnapshot` 或
`PreparedSampleBank`。现有 engine adapter 可以作为 Core 内部机制复用，但不能直接
充当新的 Host API。协议名与 C++ 签名在 API 评审后确定。

边界证明必须同时检查头文件传递依赖、CMake link closure 和实际保留符号：不得依赖
`application.cpp`、Project IO、Provider SDK、文件型 artifact hash 或 offline WAV 路径。
不能仅靠 `nm` 未出现某符号宣称代码已被正确编译。允许保留现有 domain / cooker
值类型；是否进一步拆分它们由实测依赖决定，不为“Runtime-only”预先重写整个 Core。

## 4. 派生运行内容：语义草案，不是新 Contract 注册

传输对象称为“派生运行内容”，暂不分配 Contract ID / SemVer / media type。本轮不增加
schema，也不恢复任何 retired Contract。以下是后续 wire review 的必需语义，不是
可以直接照抄的字段或二进制布局：

| 信息 | 验证责任 |
| --- | --- |
| 编码兼容版本、所需能力、完整内容身份 | Core 校验支持集合、完整 digest 与 byte length；未知必需能力拒绝 |
| 来源 Project ID、revision、所选 Pattern 身份 | 只作派生来源与一致性依据；不能变回设备端可编辑 Project |
| Pad Slot 映射、已解析播放范围、增益、trigger mode | Core 拒绝无效 slot、越界范围、非有限值与不支持的语义 |
| Pattern 时间与事件 | 事件引用 Pad Slot，不直接引用 Asset；验证 tempo/PPQ/loop、事件界限及映射闭合 |
| 去重样本清单、字节身份、格式、帧数/声道/采样率 | 解码前检查乘加溢出、长度与容量；验证材料完整性，不信任 manifest 自报预算 |

只传选定内容及闭合依赖，不偷带完整 Project Bundle、Workspace/Provider 设置或 Attempt。
Digest 证明内容一致性，不证明发送方可信；传输鉴权、信任根、是否支持签名是独立待决项。
禁止文件路径逃逸、可执行载荷和按输入 URL 任意拉取依赖。若要支持压缩，必须额外
限制解压后大小与工作内存；不能把它当作无成本扩展。

建议第一验证切片使用一个 Pattern 与极短样本，沿用已支持的 48 kHz / PCM16 材料
表达做一致性实验；这不是批准新的样本格式、最大 Voice 数或完整产品容量。
当前 `cooker::PcmSample` 持有 PCM16，但 `PreparedSampleBank` 持有 mono float，
`PreparedPatternView` 还保留 PCM16 owners。必须计入可能同时存在的两种材料，不能
把 wire bytes、decoded bytes、实际驻留峰值混为一谈。

## 5. 生命周期与失败语义提案

建议首切片**仅停止状态装载**，先避免把无 PSRAM 设备的双 Bank 热切换当默认承诺。
需要用户确认这一体验限制；不能据此删掉既有桌面 publication 测试或降低覆盖。

1. `empty → receiving`：有界接收，尚不可播放；只返回接收状态。若 stopped 仍持有
   旧 generation，先执行第 6 步卸载，不同时保留旧 Bank 与新候选。
2. `receiving → validated`：完整身份、结构、能力及预算通过；任何失败丢弃候选，
   不发布半成品。保留失败原因与可重试状态。
3. `validated → ready`：control 侧准备成功后发布一致的 generation；状态返回该
   generation 的完整内容身份。准备失败不得报告 ready。
4. `ready → playing`：启动成功才接受当前 epoch 的控制；队列满、stale epoch、
   未映射 slot 显式拒绝。请求接收与真正应用的结果分开。
5. `playing → stopped`：Host 先关闭 callback admission 并排空已进入 callback，再由
   Facade stop/drain；音频输出归零，之后才能释放材料。枚举 stopped 不是 quiescence。
6. `stopped → empty → receiving`：显式卸载旧 generation，再接收新内容；新装载失败
   时保持 empty，不承诺自动恢复旧内容。只有预算允许且未来另行批准，才设计保留旧
   generation 的事务替换。
7. 中断/复位：未发布候选不可恢复为 ready；重启默认 empty、重新装载。播放中传输
   断开是否继续，需与首版传输选择一起批准；不把断连误当已经 stop/drain。

本协议提案不新增设备持久化、掉电续播、录音 journal、回传编辑或性能 session 重放。
现有 Performance port 的 session/receipt 语义不自动适用于无 Project 的设备命令；
新的 volatile 命令身份、乱序/重复策略和 epoch 耗尽策略须在 API 评审时封闭。

## 6. 内存、实时与平台验证

预算必须覆盖：输入缓冲 + 校验/解码工作区 + Snapshot/Pattern + PCM16 owners + float
Bank + FX 工作区 + Engine/队列/voices + task stacks + I2S DMA + SDK/驱动余量。
区分 static/map 数据、构造后 heap、准备峰值、运行峰值和最大连续块；不重复扣减已
包含在 free heap 中的静态占用。预算失败在分配/发布前拒绝，不静默截断事件或样本。

Cardputer 无 PSRAM，不能照搬桌面默认配额；更不能调高配额、缩短 stress 或把可播放
Voice 数写成未经测试的保证。先测空引擎、FX 与最小内容是否能共存，再提出容量上限。
若仅引擎固定成本就无法容纳，停止并另审结构优化，不用接设备掩盖问题。

A 的 atomic 零计数已通过完整保留与 positive control 修复可信性；它不证明新 Facade
路径没有 helper。B2 要对实际 callback closure 重查 `__atomic_*_8`、锁、分配释放与
文件/网络调用，区分 control 侧正常行为及 SDK 符号。静态检查不代替 deadline 测量。

只有获准实施并通过主机/交叉编译后才连接同一台 Cardputer，另行取得刷机范围确认，
保留旧固件与恢复方式。真机阶段分别记录内容身份、首声、stop 静音、reload、失败后
重试、callback 最大值/p99.9、underrun 与 heap。此前 tone、host test、完整链接均不
填作这些 PASS；非零 underrun 不靠改 deadline 或减少已批准的 journey 来过关。

## 7. 评审前需收敛的产品选择

| 选择 | 当前提案 / 未决边界 | 最晚处理点 |
| --- | --- | --- |
| 工作模式 | 已同意设计 Runtime-only，电脑保留 Project Truth | 本轮仅记录方向 |
| 第一闭环 | 建议单 Pattern、短样本；是否包含实时 Pad 触发与 Pattern 切换待定 | API / fixture 固定前 |
| 输入介质 | USB、SD、Wi-Fi、预装 Flash 未选；先使用内存字节测试替身 | transport / Host Task 前 |
| 更新体验 | 建议 stop → unload → load；失败保持 empty，无掉电续播 | lifecycle API 批准前 |
| 编码与容量 | 建议沿用 PCM16 实验；最大 pads/events/voices/bytes 由预算与体验共同确定 | Contract / admission 实施前 |
| 安全与断连 | digest 不等于鉴权；可信来源与运行中断连行为未定 | transport 实施前 |

未决项是本设计的评审清单，不是新建的 live Issue 状态或已关闭的产品问题。不改写
旧决策日志。批准具体结论时按 `docs/prd/decisions/README.md` 写独立决策；若涉及已有
Question Issue，核实并按其流程处理，不以本提案代替正式结论。

## 8. Version Management

Version impact: none
Reason: 本轮只有设计与计划文本，不注册 Contract，不改变 Module API、Host、Provider、
Product Assembly、Build、Channel 或 release 身份。未来新增公开 Facade 能力、Contract
或正式 Host 必须在各自实施 Task 核对当时 manifest，决定版本变化与兼容策略。
不提前猜版本号，不创建 tag、快照、Release 或部署。

## 9. Documentation Impact

Documentation impact: none
Reason: 本文是待评审设计，不改变 current Portal 的已实现能力、投影身份或 active
模块边界；不是 ESP32 产品能力发布。正式批准并实施公开边界时必须同步相应 Portal
页面与源图。本轮仍运行文档检查以核对来源链接与设计声明。
