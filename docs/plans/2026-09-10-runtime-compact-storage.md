# Runtime-only 紧凑存储实施计划

日期：2026-09-10。状态：待独立评审，未授权以预测替代正向容量证据。

依据：[设计](../design/2026-09-10-runtime-compact-storage.md)、
[#1124](https://github.com/endaye/lmdj/issues/1124) 与原
[Cardputer 计划](2026-09-10-cardputer-runtime-host.md)。每项一个 Conventional
Commit、一个独立当前 head 评审 PR；当前设计 PR 不实施 storage。

## D2：设计交付

封闭文件为本计划、对应设计，以及
`apps/docs-site/docs/core/modules/application-facade.mdx`、
`apps/docs-site/docs/core/modules/audio-runtime.mdx`。
检查相对链接、`scripts/local-ci.sh --lanes docs_static`、
`scripts/docs-site.sh check`、stage 后 `python3 tests/build/ci_change_scope_test.py`
与 `git diff --cached --check`。不新增 required CI gate。
设计结案前创建 M1、M2、R2 开放工作项，并在 H1/B1 和 umbrella 上转移容量阻塞；
工作项的 Closed 状态不能充当原 D1 的正向验收。

## M1 #1129：回执有界队列存储

前置：D2 当前提交独立评审合并。将新显式 N profile 传到控制/结果/状态队列，
构造后固定，不改变旧默认及旧无参数 receipt-bounded 构造组合。

封闭文件：

- `packages/audio-runtime/include/lmdj/audio/detail/runtime_spsc_storage.hpp`（新）
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `packages/application-facade/src/runtime_facade.cpp`
- `tests/core/audio/fixed_spsc_queue_test.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `tests/core/facade/runtime_facade_test.cpp`
- `tests/core/facade/runtime_facade_stress_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`

先写最低层红测试，分别固定 N=1/128/1024 的满/空、wrap、全宽 payload、
精确 storage bytes、非法 N、旧两个构造组合不变。Facade 组件验证 full/retry
不消耗序号、旧 Voice terminal 加满额短音、空/部分 poll 后再提交、stop 取消、
unload/reset 后回执及 identity、每个 allocation failure 后 empty/静音/重试。
测试不得只检查 sizeof 变小；必须计入每一独立分配和 sentinel cell。

使用现有测试目标，不新增 stress 名称或缩减 coverage 排除边界。命令：

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev fast
scripts/core.sh test dev stress
cmake --preset asan
cmake --build --preset asan
ctest --preset asan -L native --output-on-failure
cmake --preset tsan
cmake --build --preset tsan
ctest --preset tsan --output-on-failure
bash scripts/verify-core-dependencies.sh
scripts/docs-site.sh check
```

ASan/TSan 必须在支持对应运行时的环境实际执行；无法运行是待补证据，不是 PASS。
并发用例使用真实新存储、满额命令与部分 poll，覆盖 acquired-consumption →
drain → retire 顺序；callback allocator guard 同时检测 new/delete 和 aligned 形式。
目标 EIM strict build/link 验证所有活跃源码、公开入口、C++20 与 warnings-as-errors，
不可只编译 probe stub 或靠 overlay。保留 exact revision、ELF/map/编译命令和 hash。
失败恢复：停止后续容量准入，修复已定位缺陷，不能下调 N/Voice/测试强度使之通过。

## M2 #1130：只读 PCM Bank 路径

前置：D2 评审通过；可独立验证表示变更，按 M1 → M2 顺序落地以减少集成冲突。
封闭文件：

- `packages/audio-runtime/include/lmdj/audio/prepared_sample_bank.hpp`
- `packages/audio-runtime/src/prepared_sample_bank.cpp`
- `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
- `packages/audio-runtime/src/realtime_engine.cpp`
- `packages/application-facade/src/runtime_facade.cpp`
- `tests/core/audio/prepared_sample_bank_test.cpp`
- `tests/core/audio/realtime_engine_test.cpp`
- `tests/core/audio/realtime_engine_stress_test.cpp`
- `tests/core/facade/runtime_facade_test.cpp`
- `tests/core/facade/runtime_facade_stress_test.cpp`
- `apps/docs-site/docs/core/modules/audio-runtime.mdx`
- `apps/docs-site/docs/core/modules/application-facade.mdx`

最低层红测试：PCM owner lifetime、空/坏参数不半更新、slot 表示替换与字节账本、
mono/stereo 极值转换、同一素材多 Pad/不同 playback，以及 float 路径不变。
组件测试逐 sample 比较原 float 与 PCM live Pad/Pattern 输出，分别覆盖触发模式、
trim/loop/ramp、release tail、mute、preview/audition 及 publication retirement。
预算断言只对窄路径要求无 float duplication，不能改 codec 的通用 footprint。
load 失败位置逐项注入，allocator positive controls 覆盖普通和 aligned 分配；
不能使用遗漏 aligned new 的测量批准节省量。

执行 M1 同一组 build/fast/stress/ASan/TSan/dependency/portal 命令，目标严格构建
也必须重跑。并发覆盖旧 Bank Voice 未结束时新 Bank 发布/回收与 PCM raw view
存活；检查 callback 无 allocation/free/shared-owner destruction。不得用旧 float
分支的 green stress 代替新 PCM 分支。失败时保持现有 fixture、期限和 reserve。

## R2 #1131：同口径正向复测

前置：R1 研究提交与 M1/M2 均完成当前 head 评审合并；不得依赖未合入 overlay。
封闭文件：

- `docs/research/2026-09-10-cardputer-music-capacity-retest.md`（新）
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/platform/native-audio.mdx`

复用 R1 已提交 generator/manifest；不改 fixture。外部 probe/evidence 使用唯一
目录、完整源码 inventory/hash、SDK/toolchain/config 身份及实际命令退出码。
native 使用真实 Core encode/load/render，验证 A/B bytes identity、完整 PCM/events、
四个同时 Pad press、相同内容停止静音、卸载清空 identity、坏内容拒绝/正确重试，
并在同一 Facade 实例完成 A → stop/unload → B（每腿都有 far-side assertion）。
所有 allocator 工具先通过 positive controls，保留失败版本与盲区。

目标严格构建后重测实际 ABI、准备峰值与显式 reserve。只有模型准入后才执行
设备 probe，逐项记录 target free/min heap、largest block、stack high-water、
render deadline/late/underrun 与原 D1 全部目标。脚本未运行或设备不可用时标 pending，
禁止将 native、ELF section 或零初始化 counter 填成目标实测。
完整 Host 新增 I/O、USB/LCD/按键和 DMA 的成本属于 H1 后续验收，不能由空 app_main
模型宣布整个 Host 可装入。按原计划区分 R2 的最低正向准入与 H1/B1 完整验收。
R2 结论仍为负则保持后续阻塞，创建封闭根因修复，不调整音乐目标。

报告校验运行 D2 的 docs_static/portal/ownership/diff 命令，并重新运行 R1 fixture
检查及实际 Core 测试。不新建“模型小于总 SRAM 就通过”的 required CI gate；
该静态比较只能拒绝不可能情况，不能证明 OS/Host/碎片/时限通过。

## Version Management

Version impact: none — D2/R2 仅设计或证据，不分配 Product Build、Module tag 或快照。

源码基线 `de78b1e35767a172bb27a2b6df1c89c07052e444` 的 manifests 为
audio-runtime 4.0.1 / api_version 2、application-facade 5.0.0 / api_version 3。
M1 改 Engine 布局，M2 改 Bank 布局，均属于 C++ ABI 不兼容；所有静态消费者须
一致重编。沿原 Cardputer 计划将身份分配留在 B1，M1/M2 明确记为 staged source，
不得把未更新 manifest 的源码打独立 Package tag 或作为旧 ABI 二进制替换。
若 B1 一次集成两项，Audio Runtime 从当时基线分配下一个 MAJOR；若中间独立发布，
后一次布局变化必须再次 MAJOR。实施前刷新 live manifests，不能复用已占用版本。
Facade typed 签名/布局、opaque epoch 和 wire 不变；内部预算优化在分配时评估 PATCH，
但 exact Audio dependency pin 必须一起更新。不存在 Contract/Project 迁移。

B1 负责 `packages/audio-runtime/module.json`、
`packages/application-facade/module.json` 与所有实际 exact-dependency 消费者 manifest、
Product Assembly/lock/source digests、新 Build 及 immutable Portal snapshot；届时先列
精确文件，再分配。M1/M2 不扩张到这些分配文件，不隐式启动 release。
tag 目标只允许后续已验证 exact-main candidate；本计划不创建任何 tag/Release、
Channel promotion 或部署。rollback 保留既有不可变 Build，源码回退采用独立修复 PR，
不移动历史 tag 或改写冻结 snapshot。

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /core/modules/audio-runtime/
Reason: D2 记录待实现 storage 方案及容量阻塞；M1/M2 同 Task 更新实际状态。
R2 另更新 /platform/native-audio/，只发布实际测得证据，不宣称完整设备验收。
