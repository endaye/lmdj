# Cardputer ADV：Runtime Facade 真机资源与装载探针

日期：2026-09-09。结论：**探测完成，装载因资源不足被拒绝；未进入音频验收。**

## 1. 本轮问题与边界

在 Voice-state 紧凑存储与 Capture 按需分配合入后，使用用户唯一连接的 Cardputer
ADV 测量真实可用内存，并通过 Runtime Facade 尝试装载最小标准材料。不继续凭
静态尺寸推断上板成功，不缩减任何 Core 队列、Voice 或功能容量。

这不是完整 B2 T5：没有正式 ESP32 Host、传输协议、Product Assembly、音频 DMA、
I2S、屏幕、键盘、无线网络或声音验收。具体授权和步骤见
[本轮计划](../plans/2026-09-09-cardputer-runtime-resource-probe.md)。

## 2. 输入与可追溯性

- Product source：`692ac4837ce79c9681fed81d06eedfac9ee84f5c`。
- EIM-managed ESP-IDF v6.1：`fff9895c82d744c7237be8847347bdd1b07c6643`。
- Xtensa ESP GCC 15.2.0，工具包 `esp-15.2.0_20251204`，目标 ESP32-S3。
- 全部 18 个声明产品源文件编译；T4 的五个 producer CMake 文件对该 source 无差异。
  ELF 保留 17 个 Facade API roots，未把声明闭包中的 offline/file 源文件排除出编译。
  API-rooted linker GC 不等于这些 broad targets 已完成依赖拆分。
- 产品编译实际最后一个 language flag 为 `-std=gnu++20`，保留
  `-Wall -Wextra -Wpedantic -Werror`，展开 response file 后没有 `-Wno-*`。
  IDF 在前面提供的 `gnu++26` 被后面的 `gnu++20` 覆盖；真机打印 `cxx=202002`。
- 固件：`cardputer-runtime-resource`，独立研究镜像，不分配 Product Build。
- ELF SHA-256：`3b973b147be30605d0d72d7155fd45deb2271bd584f036ab0e037e845a64e2d9`。
  两次板上串口打印的 ELF digest 均与本地文件一致。
- 输入为 [既有 golden fixture](../../tests/fixtures/contracts/runtime-content-v1.hex)，
  **248 bytes**，SHA-256
  `5e441b59ea4a75e3a1a91f0ea10cb8e893a8b542f5923545e1d89596d8e65705`。
  与 [identity/metadata](../../tests/fixtures/contracts/runtime-content-valid.json)
  逐字节、digest 和长度核对；它包含两个 Pad、一个事件、一个共享的四帧 PCM 样本，
  不是足以进行人耳验收的音频素材。

Probe 独立目录为
`/Users/endaye/esp/lmdj-spike/cardputer-runtime-resource.RSMqZL/`。
原 T4、先前内存探针与 product source 均未覆盖或修改。

## 3. 设备安全与刷写

设备读回 ESP32-S3 revision v0.2、8 MB Flash、USB Serial/JTAG；Secure Boot 和
Flash Encryption 均未启用。未修改 eFuse、安全配置、电压或 microSD。

刷写前读回完整 **8,388,608-byte** Flash，随后 `verify-flash` 在设备端报告
`Verification successful (digest matched)`。备份仅在本地受限文件保存，不进入 Git
或公开产物。第一次 921600 波特率备份在约 35.6% 时出现
`Serial data stream stopped: Possible serial noise or corruption`，未产出完整文件；
460800 重试成功。降速与成功存在时序关系，但本轮没有定位 USB 中断的底层原因。

刷写由该构建生成的 `idf.py flash` 参数执行，仅写入 bootloader `0x0`、partition
table `0x8000` 和 app `0x10000` 的镜像范围；没有全盘 erase。写入后校验成功。
设备目前保留诊断固件，所以不会显示产品界面或发声。原 Flash 可由该备份恢复；
本轮未执行恢复，也未证明一次实际恢复启动。

## 4. 两次独立 reset 后的真实测量

两次启动的以下数值一致；内存 capability 为
`MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT`，不是把不同 capability 的重叠堆相加。

| 测量项 | 字节 | KiB |
| --- | ---: | ---: |
| 该固件可登记的内部 8-bit heap 总量 | 408412 | 398.84 |
| probe 入口空闲 heap | 351672 | 343.43 |
| 最大连续空闲块 | 286720 | 280.00 |
| 实际 PSRAM heap | 0 | 0 |
| `sizeof(RealtimeEngine)` | 446976 | 436.50 |
| Engine + Facade 的固定模型量 | 455396 | 444.72 |

使用 64-byte alignment 实际申请 **446976 bytes**，两次均返回空指针；申请前后
空闲总量与最大块未变化。该试验只申请 raw bytes，不绕过 Facade 构造 Engine。
单个 Engine 请求比最大块大 **160256 bytes（156.50 KiB）**，不是仅靠四帧样本变小
就能消除的限制。

Probe 已预分配 **24576-byte main task stack**。测试后最小剩余栈为 **14044 bytes**，
即该路径观察到 **10532 bytes** 使用量，不能沿用默认小栈假定。IDF 的
`uxTaskGetStackHighWaterMark` 返回 bytes；没有按通用 FreeRTOS 的 words 再乘四。
该值只覆盖本轮拒绝/校验路径，不证明完整成功装载或音频并发路径的栈峰值。

## 5. Facade admission 和拒绝后的行为

`maximum_admitted_bytes` 取构造 Facade 之前测得的 **351672 bytes**。
`platform_reserve_bytes=32768` 是明确的探针保护余量，不是实测完成的最终 Host/DMA
预算。这个 cap 未向上调，reserve 未向下改，也没有修改产品模型去强行通过。

| RuntimeBudget 字段 | 字节 |
| --- | ---: |
| fixed | 455396 |
| encoded | 248 |
| pcm | 8 |
| prepared float | 32 |
| metadata | 907 |
| preparation workspace | 2248 |
| provisional platform reserve | 32768 |
| **admitted** | **491607** |
| measured cap | 351672 |
| **模型超出 cap** | **139935（136.66 KiB）** |

即使不计算该 provisional reserve，模型 subtotal 仍为 **458839 bytes**，超过
入口空闲量 **107167 bytes（104.66 KiB）**。这里只用于说明并非 reserve 一项导致
拒绝，不意味着批准移除 reserve。

两次启动中，每次的第一次 load 与同条件 retry 都返回 `budget_exceeded`，phase
保持 `empty`。每次 11 条逐腿断言通过：

1. 初始为空；load 给出资源类拒绝；拒绝后无已发布 identity。
2. 拒绝后的 render 写出双声道全零；start 返回 `wrong_state`；unload 成功。
3. 错误 byte length 被拒绝为 `invalid_content`，之后仍为空且静音。
4. 同一份完整 identity 重试得到相同资源拒绝，仍为空且静音；reset 后仍为空且静音。

每次日志末尾为 `ADMISSION status=BLOCKED_RESOURCE` 和
`PROBE_END checks_failed=0 audio_test=NOT_RUN`。
**检查通过的是拒绝行为和证据完整性，不是装载成功。**

最低空闲 heap 为 342244 bytes，所有采样点 heap integrity 为 1。Facade 析构后
空闲量为 351624 bytes，比入口少 48 bytes；本轮未归因这 48 bytes，不能声称
零残留或完成泄漏证明。成功装载后的 start/submit/非零 PCM/receipt/stop/unload/
reload 分支没有执行，I2S、声音、deadline、jitter 与 underrun 均未测试。

## 6. 本地验证与保留证据

- `build-01.json/log`：fresh target configure/build 成功，保留完整输出和真实退出码。
- `preflash-verification-02.json/log`：18 sources 的 exact-revision 内容、有效编译
  flags、17 roots、16 个 target sizes、fixture 与 ELF/bin/map/config 哈希通过。
  第一版检查器误将前面的 IDF language default 当成最终语言，退出失败；修正为
  展开 response file 并检查最后一个 `-std`，没有修改产品编译 flags。
- `backup-attempt-02.json/log`、`backup-verify.json/log`、`flash-01.json/log`：
  完整备份、设备一致性校验、刷写校验均成功。首次备份中断没有完整本地原始日志，
  只保留了当次工具回显中的错误和进度，不能与后续完整 receipt 混同。
- `run-01.serial.log`、`run-02.serial.log` 和对应 `serial-run-*.json/log`：
  两次独立 reset、同一 ELF、相同资源结果、完整结束标记；不是重复解析同一日志。
- 同一 source 的 fresh native `lmdj_runtime_content_tests` 与
  `lmdj_runtime_facade_tests` 构建成功；`cooker.runtime_content` 和
  `facade.runtime_facade` **2/2 PASS**。
- `python3 tests/conformance/runtime_content_contract_test.py --consumer
  build/core/dev/bin/lmdj_runtime_content_tests`：独立 wire/schema/C++ conformance PASS。
- `check-serial.py`：核对完整 11-leg 拒绝旅程，并以缺结束标记、缺重试断言和失败
  静音断言作为 6 个负对照，均被拒绝。两次 reset 的结构化资源记录一致。
- `probe-evidence.tar.gz`：71 个文件，10366383 bytes，SHA-256
  `28c841085886e9d07db42372df3b03fe5b0625709cd2eecb11e427edf65ff419`。
  封包后逐文件重新校验 digest/length；不含原设备 Flash 或带设备身份的备份、刷写、
  reset 日志。上述私有日志仍单独保留在本地目录。该封包本轮没有上传或公开发布。
- 文档与提交验证结果在本轮计划的 completion 中记录。

## 7. 对下一步的约束

当前存在两个独立障碍：**总可用内存不足**，以及 **Engine 单块申请超过最大连续块**。
只把 Engine 拆成多次分配不能解决总量；只再省约 8 KiB 的 FX 队列也不足以消除
本轮差距。下一项应根据实际大缓冲占用评审方案，保留字段宽度、FIFO、溢出语义和
完整能力；任何按设备缩减容量或关闭功能的选择都需要独立批准。

在资源问题解决并重新完成装载探针前，不把接上 I2S 或听到测试音当作 B2 可用。
完整 Host/Assembly、成功生命周期和真实音频闭环仍是后续明确范围的 Task。
