# ESP32 固件开发与测试手册

维护方式：持续更新。首次整理：2026-09-09。

这是后续 ESP32 实验的操作入口，不是新的 Embedded Host、硬件选型或发布批准。
以下板级经验主要来自 **Cardputer ADV / ESP32-S3**；不能直接套到普通 Cardputer、
经典 ESP32 或带 PSRAM 的板子。具体 Task 的设计、版本锁与验收要求优先。
本手册不改变已有实验结论，也不把串口 PASS 改写为人工听音 PASS。

## 1. 开始前：先确定五件事

1. **做什么**：本轮只验证哪一个事实？写明成功条件、失败停止点和不做的范围。
2. **哪块板**：板型、芯片、Flash 容量、PSRAM、供电、串口和音频输出路径。
   设备身份放在私有记录；不要仅凭模组丝印或串口路径认定是上次那块板。
3. **哪份源码**：独立 worktree、完整 Git SHA、是否有 overlay、外部工程与补丁的身份。
   `main` 会变化，旧实验成功不代表新 HEAD 已经验证。
4. **哪套环境**：项目锁定的 IDF revision、编译器、target、M5 库和配置。
5. **怎么回去**：烧录前确认原固件备份可读、长度与 SHA-256 匹配、属于同一设备，
   并且恢复范围明确；缺任一项就停在构建，不写设备。

后续实验优先复用已留存的完整工程和证据清单；若只有本地路径、拿不到源码/补丁，
明确记录为“不可重放”，不要凭日志拼出一个号称相同的固件。
下面流程是人工清单，本手册不引入一键固件入口；脚本整合属于后续独立 Task。

## 2. 环境与构建：复用 EIM，锁住实际输入

### 环境

ESP-IDF **只用 EIM 下载、安装和管理**。先查已有安装，缺版本时通过 EIM 安装项目
明确锁定的版本，不用手动 Git/ZIP/旧安装脚本另建平行环境，也不跟随默认项升级。

以下 `v6.1` 仅重放 2026-09-07～09 的这组实验；不是所有项目的版本要求或最新版推荐。
该组 IDF revision 为 `fff9895c82d744c7237be8847347bdd1b07c6643`。见
[工具链研究 §4](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)。

```bash
eim list
eim shell v6.1
# 以下命令在新进入的 EIM shell 内执行：
idf.py --version
git -C "$IDF_PATH" describe --tags
git -C "$IDF_PATH" rev-parse HEAD
```

不要把个人 SDK 绝对路径写入项目配置。切换 SDK 后，在本 Task 的独立构建目录重新生成
引用旧 SDK/Python 的缓存；保留失败日志，不清理其他工程或共享 EIM 工具链。

### 从干净工程到可审计固件

1. 核对工程的 `idf_component.yml`、`dependencies.lock`、`sdkconfig.defaults`、
   实际 `sdkconfig` 和本地 override/patch。默认配置不是实际配置的替代品。
2. 对这组 ADV 工程，在**独立且已保存配置的工程副本**中先执行
   `idf.py set-target esp32s3`，再构建。该命令会重建配置/构建状态，不在共享或尚未
   留证的目录盲用。旧配置不能直接覆盖回来而不核对 target。
3. 保留完整构建输出和失败状态。下面是已进入本轮工程、`evidence/` 已存在且
   `build-01.log` 尚不存在时的示例；后续尝试换新编号，不能覆盖失败记录。

   ```bash
   set -o pipefail
   idf.py build 2>&1 | tee evidence/build-01.log
   build_result=$?
   printf 'build/log pipeline exit status: %s\n' "$build_result"
   ```

   `build_result` 是开启 pipefail 后的流水线退出码，构建或日志写入失败都会报非零，
   此时立即停在构建阶段；打印成功或仅 `tee` 成功都不算构建通过。

4. 检查最终编译命令，而不仅是 CMake 声明：Core 使用显式 C++20；审计有效的最后一个
   `-std=` 及 `-Wno-*` / `-Wno-error=*`。这组工具链默认标准曾读回 `202400`，
   不能把“编过”当作与宿主 C++20、警告策略等价。
5. 留存完整 ELF、map、烧录参数及对应 bootloader/partition/app 镜像，记录长度与
   SHA-256。检查要求保留的 API/对象确实进入最终 ELF；中间对象或 `WHOLE_ARCHIVE`
   本身不能证明最终链接没有裁剪。最终产物不完整就不进入烧录。

最低证据包应能回答：源码与补丁是什么、实际 SDK/编译参数是什么、生成了哪几个镜像、
刷到哪块设备、设备实际跑的是哪份固件。完整源码闭包可用归档或可获取的 immutable
revision 加补丁清单保存，不能只记录一个已经消失的工作目录。

## 3. 烧录、重放与恢复：每一步都要有另一侧证据

这里不提供通用 Flash offset 或整片擦除命令；不同芯片、分区和加密配置不能共用它们。

| 阶段 | 动作 | 通过条件 / 停止条件 |
| --- | --- | --- |
| 写入前 | 确认设备、串口无人占用、备份身份与哈希、候选镜像和实际烧录范围 | 任一不符则不写入；不停止其他会话的串口程序 |
| 烧录 | 使用该工程生成的参数及 IDF 支持的 `idf.py -p PORT flash`；`PORT` 必须替换为已核实端口 | 命令成功且写入校验通过；失败保留日志，不直接重试擦除 |
| 启动 | 在同一 EIM shell 用 `idf.py -p PORT monitor`，保存完整启动/测试日志 | 核对板型、固件身份、panic/复位次数、配置读回；monitor 的打开不是启动 PASS |
| 重放 | 按本 Task 定义的复位、播放、stop/drain、卸载、错误输入、有效重载顺序执行 | 每一步有完成侧断言；漏一步就保留缺口，不能只检查最后的 PASS 字样 |
| 结束 | 读回静音/停止状态，说明当前留下的镜像 | 原固件“有备份”和“已恢复”是两种状态 |
| 恢复 | 在覆盖恢复操作的授权下，用同设备备份和已审计的写入方案恢复 | 重新核对写入/读回、启动及原有功能；失败停止并保留备份和失败镜像 |

`monitor` 可能影响设备复位/运行状态；先协调设备占用，不把它当纯文件查看器。
不做 erase-all、eFuse、Flash 加密设置或额外分区操作来“顺便排障”。
备份、设备标识和原始串口日志可能包含私有数据；原始材料私有保存，仓库只放脱敏结论、
可分享的源码/补丁、长度/哈希和取得证据的入口。不要将整片 Flash 备份提交到 Git。

## 4. 快速排查：先隔离一层，再改一个变量

这些是具名历史实验的经验，不保证后续 SDK/库版本仍有同一个缺陷。遇到新版本时，
先重新验证适用性；上游“已修复”还需在锁定版本和本板上验证。

| 症状 | 优先核对 | 已有证据与边界 |
| --- | --- | --- |
| ADV GPIO 编译报错 | 实际 target 是否误选为默认 `esp32`，而非 `esp32s3` | [分配顺序研究](../research/2026-09-09-cardputer-allocation-order.md)保留首次失败及显式切换后的恢复 |
| 编译通过，启动连续 panic | M5GFX patch 是否实际进入依赖解析结果，是否只改了会被覆盖的 `managed_components/` | [工具链研究 §1.1](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)：当时 v6.1 + M5GFX 0.2.28 的 `dma_burst_size` 补丁用 vendor + `override_path` 持久化；build-only 检查抓不到启动失败 |
| free heap 足够却分配失败 | **同一 capability 下的 free、最大连续块、单次请求尺寸和分配顺序** | [分配顺序研究](../research/2026-09-09-cardputer-allocation-order.md)：free 106452 B，但最大块 51200 B，无法容纳 52416 B 请求；不要先降队列容量或 reserve |
| 同一代码在 Xtensa 的格式化告警失败 | 固定宽度整数不等于固定的基础类型，审计格式串与实际 ABI | [工具链研究 §1.2](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)：该工具链 `int32_t` 为 `long int`；修正确类型/格式，不关闭告警 |
| lock-free 断言失败或延迟异常 | 目标位宽、实际 Kconfig、atomic 所在内存与最终实现 | [工具链研究 §2、§7](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)：不能删断言、把 64 位直接窄化或用锁伪装实时兼容；并发方案需独立设计 |
| 扬声器 enabled / I2S 写入成功但听不到 | 先分清软件波形、I2S/codec 配置与读回、模拟输出、人工听感 | enabled/写入计数都不能替代物理输出验证；不要直接猜是增益、接线或 Core 静音 |
| 麦克风读回常量，不随声音变化 | 统计样本 distinct/min/max，再用单变量实验区分采样路径和增益 | [工具链研究 §1.5](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)记录当时 v6.0.3/v6.1 的常量问题；不声称上游当前状态，也不自动降级 SDK |

内存还要记录最低剩余堆、最大块、堆完整性和实际运行任务的 stack high-water。
PSRAM 不能靠 Flash 容量推断；点屏 demo 的空闲堆不能拿来作 Core 内存预算。
“fixed-first”改善了那次测得的布局，不保证任意碎片化堆都可加载。

时序必须先定义计量边界：render、格式转换、driver 阻塞分别计时，块时长由帧数/采样率
计算。[单声部 I2S 实验](../research/2026-09-09-cardputer-allocation-order.md)的处理余量
最差仅约 261 µs，不能外推为正常多声部能力、模拟 underrun 为零或普遍实时保证。

## 5. 音频对照：同一输入，分开数字证据与人工验收

先定义每条路径的预期差异。要比较发生器、raw PCM 与 Core render，就固定频率、
采样率、声道、时长、淡入淡出、幅度、重复次数、间隔、codec 音量、Host 增益和输出设备；
能使用同一 PCM 时记录其 hash，不能相同时写明差异。每轮只改一个变量。

- **软件层**：记录输入身份、PCM 峰值/RMS/非零帧、有限值和参考输出比较方法。
  “有非零样本”不证明音量合适；“听起来差不多”也不证明样本相等。
- **数字设备层**：记录实际 codec/I2S 配置、写入长度、错误、通知、stop 后的软件静音
  与 DMA 零尾。`isPlaying()==false` 不能未经验证就当成 DMA 已排空。
- **物理层**：明确请人听哪一组、持续多久、预期音高/次数、音量及爆音/杂音；收集原话。
  50 ms 的短促音与较长参考音不能直接作音量等价对照。循环短音可能本来就有密集纹理，
  参见[短循环听感误分类](../../.agents/pitfalls/short-loop-hearing-misclassification.md)。

结果分列 `PASS / FAIL / NOT RUN`，并写清测试边界。数字 PASS、听不见或很小声可以
同时成立，不能因此把任一方抹掉。没有人工反馈就写待验收；有反馈也只适用于该候选、
该输入和该输出路径。音频问题未确认因果前记录为假设，不升级为确定的硬件/软件故障。

## 6. 每轮结束：留下能接着做的最小记录

可将以下模板用于新实验的 `docs/research/YYYY-MM-DD-<topic>.md`，原始证据另存。

```text
日期 / Task / 要验证的事实：
板型 / target / 供电与输出路径（私有设备身份另存）：
源码 revision / overlay 与外部工程清单：
IDF revision / 编译器 / 依赖锁 / 补丁 / 实际 sdkconfig：
ELF、镜像、输入素材的长度与 SHA-256：
原固件备份校验 / 本次实际写入范围：
复现步骤 / 预期 / 实际 / 完整日志与取得位置：
失败尝试 / 单变量对照 / 已确认原因 / 尚未排除的假设：
软件验证 / 数字设备验证 / 人工听音（分别记状态与边界）：
停止与恢复结果 / 当前设备留下的镜像：
下一步 / 阻断条件 / 所需授权：
```

知识按用途落位，不再开第二套“经验总账”：

- 日常顺序与可复用步骤更新本手册；不复制大量串口输出。
- 具名实验、失败与恢复证据放日期研究文档；后续结论通过新记录补充，不重写冻结结果。
- 无法从代码推导的流程失误按[坑账规范](../governance/pitfall-ledger.md)检索
  `.agents/pitfalls/` 的相关 `area`，同根因复发更新原条目；单纯阅读旧坑不算复发。
  已有确定性回归覆盖的产品缺陷不另造流程坑。
- 重复、稳定且可机械判定的动作才考虑后续脚本；新 gate 必须说明捕获什么缺陷。
  版本引用遵循[引用不等于选型](../../.agents/pitfalls/unpinned-upstream-citation-read-as-decision.md)，
  使用不可变来源并标明适用范围。

### 原始实验入口

- [工具链、EIM、M5 兼容性、atomic 与首次编译](../research/2026-09-07-esp32-idf6-toolchain-and-atomics-amendment.md)
- [Runtime 资源测量](../research/2026-09-09-cardputer-runtime-resource-probe.md)
- [I2S 首次实验与拒绝加载](../research/2026-09-09-cardputer-i2s-probe.md)
- [分配顺序修正、完整数字旅程及其验收边界](../research/2026-09-09-cardputer-allocation-order.md)

Version impact: none — 仅整理既有实验经验，不改变任何产品或依赖版本身份。
Documentation impact: none — 不改变产品行为、平台支持承诺、既有实验结果或正式
部署/验收规则；这里只为独立 ESP32 实验增加操作索引，不引入新的门户事实。
