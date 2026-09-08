# 32-bit observation protocol experiment

独立、可重复运行的三缓冲遥测原型。不依赖 LMDJ Core，正式产品不得依赖它。
它把已讨论的候选协议变成可检查代码，不表示 Engine 已实现或支持 ESP32。

## 运行

需要 Python 3.9+、支持 C++20 的编译器和标准线程库，无第三方依赖。

```bash
bash demos/32bit-observation/run.sh
bash demos/32bit-observation/run.sh tsan
```

可以用 `CXX` 选择编译器。脚本失败即退出，打印并保留临时构建目录；不把二进制
写进仓库。TSan 的编译或运行失败不是 PASS，也不自动退回普通运行。

## 协议与边界

每个单写者域有三个初始合法的值槽：写者 W、读者 R、交换槽 M。一个
`atomic<uint32_t>` 保存 M 索引与 dirty 位；不使用 atomic64 或递增序列戳。
多个非实时调用者持同一 mutex，取得 R 并复制完值后才释放锁。写者不接触锁。

- 写者从独立权威计数构造完整副本，填入 W，以 acq_rel exchange 发布；返回的
  旧 M 成为 W。不能在循环回来的旧槽上继续累加，也不能只复制发生变化的字段。
- 锁内读者 acquire 检查 dirty；有新值则以 acq_rel exchange 交还旧 R、取得
  交换当时的 M，再复制 R。没有新值则继续复制其私有 R。
- 发布 release → 消费 acquire 保护新 payload；交还 release → 写者 acquire
  保护旧 R 在复制结束后才被重写。交换返回后、私有索引赋值前不访问 payload。
  依据 [C++ 原子内存序规则](https://eel.is/c++draft/atomics.order)。SC 小模型并不能
  代替这些 C++ happens-before 义务，也没有模拟弱内存重排序。
- 暂停读者始终只持一个槽，写者可继续在另外两个槽交换。最后发布的值位于 M
  或已被读者取得的 R。写者停止且与后续读取建立同步后，不需要额外发布来追平。
- 发布者换线程或 reset 必须先排空旧发布者并建立同步，再正常发布值。
  **不能重置三槽或角色索引**：旧读者可能仍持有 R。析构前所有调用者必须退出。

`publish` 不含算法重试、分配或锁操作，只复制固定值并执行一次原子交换。
这不是目标 wait-free 或时限证明：底层 exchange 可能重试，中断、调度和缓存
也不在该结论内。mutex 读者不是无锁接口，不保证公平，不能从音频 callback 调用。

## 实验覆盖

`model.py` 穷举三次发布、两次串行读取的 SC 交错，拆开高低字访问、交换和索引
赋值，验证不撕裂、不倒退及停止后的最终值。提前归还读者槽的错误变体必须被拒绝；
另保存有限序列回绕接受未发布组合值的负例。状态数只描述这个有限模型。

`test.cpp` 检查初值、32 位低字进位、循环槽不作为累加基准、持锁读者暂停期间
写者完成 65,537 次发布、没有下一次发布时的最终值、读者暂停跨 reset，以及
同步后的发布者换线程；四个读者各读 100,000 次，同时写者发布 200,000 次。
暂停钩子与 10 秒超时仅在测试代码中，超时是死锁诊断，不是实时 deadline。

未覆盖：任意交错的机器证明、Pattern 所有权/取消/激活/回收、跨域关联、Engine
生命周期与 Transport 原时点、ESP32 目标编译/反汇编、真机音频和实时性能。
TSan 即使成功也只是本次主机执行的动态检查，不证明所有执行都无数据竞争。

## 本轮结果（2026-09-08）

主机：arm64 macOS，Apple clang 21.0.0（clang-2100.1.1.101）。
上述普通与 TSan 命令均退出 0，多线程测试通过，TSan 本轮没有报告数据竞争。
SC 模型遍历 429 个状态、750 条转换、7 个终态；过早归还槽的错误变体被
`torn snapshot` 拒绝。最初只有两次发布时未能检测该变体，增加第三次发布才
覆盖到错误槽位复用；保留这个负向检测，防止模型范围缩小后出现虚假的通过。

这些是主机原型结果，不是 ESP32 交叉编译或产品集成结果。

## ESP32-S3 对象代码实验

在 EIM 管理的 v6.1 环境中运行：

```bash
bash demos/32bit-observation/codegen.sh
```

也可将 `CODEGEN_CXX` 指向该 EIM 安装中的 `xtensa-esp32s3-elf-g++`。
脚本在独立临时目录保留 -O2/-Os 对象、反汇编、undefined symbols 和编译器版本，
不修改原 Step A 的配置或失败证据。`codegen_control.cpp` 单独编译，故意使用
atomic64 load，确认诊断确实能看到 `__atomic_load_8`；它不是原型 fallback。

这是使用目标编译器和 32 位 ABI 的**对象编译**，不是完整 ESP-IDF 工程构建或链接。
没有复用旧 probe cache 的 SDK include/specs，也未配置 PSRAM、执行硬件或分配
目标内存。实际集成还必须核对 SDK 编译参数、内存放置、libc 解析及完整链接图。

2026-09-08 实测：`eim list` 为 v6.1，SDK revision 为
`fff9895c82d744c7237be8847347bdd1b07c6643`；编译器为
`esp-15.2.0_20251204` / GCC 15.2.0。-O2 和 -Os 均退出 0：

- 对象格式 `elf32-xtensa-le`，五个指定函数全部保留，text 为 169 字节，data/bss
  为 0。这只是这份小对象的尺寸，不是固件 Flash/IRAM 或三缓冲对象内存占用。
- `demo_publish` 和 `demo_exchange` 的交换为 `wsr.scompare1` / `s32c1i` /
  `bne` 回跳；`demo_claim` 的 fetch-or 同样是 CAS 重试环，失败结果成为下一轮
  expected。单个 C++ RMW 调用不能视作一条固定耗时的目标指令。
- seq_cst 标志 store/load 各为相应 32 位访问及前后 `memw`。
- 候选对象唯一 undefined symbol 为 `memcpy`，发布函数有两次 24-byte memcpy
  调用；未引用 atomic64、mutex 或分配 helper。独立正对照引用 `__atomic_load_8`。
  **未链接 memcpy，不据此断言其最终实现或时延。**

代码形态与先前“CAS 失败后采用新观察值”的条件式争用分析一致，但这并未验证
中断影响、内存放置或完整协议的工作界限。原 Step A 仍需修复设计并获实施授权
后重新构建；不得用本对象不存在 atomic64 来替代原探针的完整归因检查。
