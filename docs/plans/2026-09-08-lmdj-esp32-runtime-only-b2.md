# ESP32 Runtime-only B2：设计交付与候选实施分段

日期：2026-09-08。
状态：D0 为本轮授权的设计工作；T1–T5 是**待批准的候选拆分，不是可直接执行的实施计划**。
设计权威：[Runtime-only B2 提案](../design/2026-09-08-lmdj-esp32-runtime-only-b2.md)。
原 A/B1 已独立交付；本计划不覆盖其日志或更改失败结论。

## D0 — 本轮文档 Task

声明文件恰好为：

- `docs/design/2026-09-08-lmdj-esp32-runtime-only-b2.md`
- `docs/plans/2026-09-08-lmdj-esp32-runtime-only-b2.md`

检查当前 C++ include/link 边界、材料表示、生命周期和已有 A/B1 证据，记录已批准方向
与未决项；不动 product source、Contract schema、Host 或 SDK/probe。
最低层验证为 `scripts/local-ci.sh --lanes docs_static`、新文件 staging 后
`python3 tests/build/ci_change_scope_test.py`、`git diff --cached --check`，并检查本文
与设计中的相对文档/源码路径。由于设计引用已记载源码事实，额外运行
`scripts/docs-site.sh check`；这不是运行时测试或设备验收。
不增加 required check，不改变 lane、floor、timeout 或压力预算。

交付为一个 Conventional Commit；按 `issue-done` 核对 exact-head review 与 live
protection，再在适用授权内 push/PR/merge。设计文档的合并不是 T1–T5 实施授权，
也不代表表中的提案已被产品接受。保留工作树，不自动清理或发布。

## 进入实施前的批准边界

先完成设计 §7 的评审，至少固定首切片功能、装载/失败语义及所需 wire 语义；在一个
独立决策文件记录被批准内容。T1 可以单独批准为兼容性重构，但不自动批准新的设备
生命周期或 wire Contract。T2–T5 的 exact filenames、API、schema 与预算依赖该决策，
现在只给候选目录和验证责任；每项开始前必须替换成封闭的文件清单，不准以通配目录
作无限扩张的提交范围。

## 候选 Task 与验证责任

### T1 — 现有 performance ports 与链接目标解耦

候选文件：`packages/application-facade/include/lmdj/facade/application.hpp`、
`performance_runtime.hpp`、`performance_engine_adapter.hpp`（后二者在同目录）、
拟新增同目录 `performance_ports.hpp`、`packages/application-facade/CMakeLists.txt`、
`tests/core/facade/` 下一个独立最小消费者测试；如实际依赖审计要求源文件迁移，先
补全精确清单再实施。不得为了隔离改写既有 port 签名或删除 replay/session 行为。

最低层测试：新 consumer 编译/链接测试、现有 `facade.application`、
`facade.performance_runtime_bridge`、`facade.performance_engine_adapter`，以及受影响
Replay/Sequence 测试（先从 CMake 确认名字）。验证完整 Facade 的旧 include 使用仍
可编译；目标没有重复定义、反向依赖或隐式 Project IO/Provider SDK 链接。
缺陷：窄头文件仍拉入完整 Facade、目标遗漏实现或双重编译。
任何机制成为 required gate 前须确定性、命名缺陷并提供 why/remedy；当前不新增 gate。

### T2 — 派生内容 Contract 与电脑侧导出

候选目录：`contracts/` 的新 schema/正反例（ID 与路径待批准），
`packages/application-facade/` 的电脑导出入口，`packages/project-cooker/` 的编码实现
及对应 `tests/conformance/`、`tests/core/`。新 Module 是否有必要先以依赖审计决定。
先声明 exact file 清单和 source revision binding，再修改任何 schema/manifest。

最低层测试：相同源 revision 与选择的确定性导出；Pad Slot/事件/样本闭合；坏长度、
digest、必需能力、超限、溢出拒绝；完整身份包括 digest 和 byte length。固定样例
与跨端 reader 一起交付，禁止把 C++ Snapshot 内存 dump 当协议。
缺陷：错误/不完整材料被当成可播放版本，或 Host 解析 Project Bundle。

### T3 — Runtime Facade admission、发布与生命周期

候选目录：`packages/application-facade/` 的新窄运行入口、
`packages/audio-runtime/` 中审计证明必需的封装、对应 `tests/core/facade/` 和
`tests/core/audio/`。wire decoder 是 Core，不是 Host。T2/T3 的生产者/消费者接口
依赖先闭合；未批准的 session/epoch/receipt/失败协议不能由实现者自行补定。

最低层测试：设计 §5 的完整生命周期逐腿 far-side 断言，分配失败/预算失败保留正确
状态；禁止 control 的 stop/reclaim 与活跃 callback 重叠；stale epoch、队列满及
重复命令按批准协议拒绝/回应；桌面既有语义不回归。并发改动加相应 stress/TSan，
保持已有 stress 预算。不得仅测 ready 而漏 stop/drain、unload、失败重试与 reset。
缺陷：半成品 publication、use-after-free、虚假 stop、跨代控制或资源超限。

### T4 — B2 exact-revision 交叉编译与静态预算探针

仓库外单独 probe，不覆盖 A/B1；仓库内候选文件为既有研究附录的新结果节。
使用已批准 T1–T3 的窄入口、完整声明闭包；固定 EIM IDF/GCC、ESP32-S3、gnu++20、
严格警告、无 PSRAM。probe-local 配置先保留原失败证据，不复制或私改产品源码。

验证：保留全部源对象与可核对 roots、未过滤 build 退出码、ELF/map/size 与逐 archive
归因、实际 callback closure 的 atomic helpers；positive control 检查计数工具。
budget 同时报告固定对象、stack 与动态准备成本，不把静态 BSS 当全部 RAM。
最低层控制为 T1–T3 相关主机测试在相同源码 revision 再跑。失败同样是有效研究结果，
不是通过；完整链接不证明 deadline、声音或可用容量。代码修复另开独立 Task。

### T5 — 最小 Host 与 Cardputer ADV 真机闭环

须先批准传输、信任边界、断连行为、Host/Assembly 身份、资源上限及刷机范围。
候选目录为 `apps/` 新薄 Host、`products/` 产品组合、对应平台测试与物理验收文档；
在单 Task 无法保持可审查时分为 driver/Host、Assembly allocation、验收三个独立 Task。
不是把仓库外 probe 或 demo 直接作为正式产品依赖。

验收顺序：装载有效内容并核对完整身份 → 播放 → 按批准范围触发 Pad/Pattern →
stop 后可观察静音与 callback drain → unload → 装载新内容核对身份与声音 →
坏输入失败后不能播放半成品 → 重试成功 → 断连/复位符合批准行为。
每腿都有 far-side 断言；记录 callback 最大值/p99.9、underrun、heap/最大连续块，
不能用旧 PCM tone、假驱动或主机 PASS 代替人耳与硬件结果。未运行的腿明确 pending。
本轮不执行这些步骤，也不要求用户现在接设备。

## Version Management

Version impact: none
Reason: D0 只提交两个文档，没有 active API/schema/manifest、Product Build、Channel
或发布变化。T1 的 API 兼容性与 Module 影响需独立判断；T2 新 Contract 要正式 ID、
SemVer、正反例与 conformance；T3 的公开能力、T5 的 Host/Assembly 需要核对当时
manifest 决定相应版本，禁止预填猜测版本号。
每个未来 Task 都必须有自己的 Version Management 章节；正式测试 Build 必须冻结
不可变 Portal snapshot。此计划不批准 tag、Release、deploy 或 Channel promotion。

## Documentation Impact

Documentation impact: none
Reason: D0 是待评审提案，不把 ESP32 加入 current 已支持产品，不改变 Portal 身份或
现有实现边界。T1–T3 若改变公开 Facade/Contract/依赖，必须同 Task 声明并更新实际
受影响 Portal 路由与源图；T5 Assembly 不能声明 none。开始实施时补齐 exact routes。

## Pitfall Impact

Pitfall impact: none — 本轮没有新增过程缺陷。沿用证据与授权分离，不把旧 bring-up
当新运行证据、不把符号缺席当完整依赖证明，也不把 native 测试当 ESP32 存储语义证明。
若后续 Task 发现符合 ledger 条件的机制缺陷，按 `issue-done` 在该 Task 记录或 bump。
