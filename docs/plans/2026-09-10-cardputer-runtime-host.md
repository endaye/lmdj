# Cardputer 最小产品闭环：D1 实施草案

日期：2026-09-10。状态：待产品批准；仅设计草案可交付，D1 尚未完成。
设计：[Cardputer Runtime Host](../design/2026-09-10-cardputer-runtime-host.md)。
总工作项：[Umbrella #1104](https://github.com/endaye/lmdj/issues/1104)。

## D1 当前文档边界

本次 partial delivery 的 exact files 仅为：

- `docs/design/2026-09-10-cardputer-runtime-host.md`
- `docs/plans/2026-09-10-cardputer-runtime-host.md`

不新建待批准 Decision，不改产品源码/Contract/manifest，不刷机、不分配 Build。
D1 #1105 结案还要求：用户确认产品选择；写入按实际确认日期命名的 Decision；
固定下面各 Task 的工程接口与封闭文件清单；完成 exact-head review 并合并。
当前草案 PR 使用 `Relates to #1105` 与 `Relates to #1104`，不用关闭指令。

最低层验证：`scripts/local-ci.sh --lanes docs_static`；检查两文档全部相对链接；
stage 后运行 `python3 tests/build/ci_change_scope_test.py` 和
`git diff --cached --check`。由于引用已记载的 Facade 与设备证据，运行
`scripts/docs-site.sh check`，但不把它报告为设备、runtime 或产品验收。
不增加 required gate，不改 coverage、timeout、stress 或 lane 选择规则。

## 依赖与分工

```text
D1 #1105（批准的产品目标与协议）
  → R1 #1106（同目标的真实容量/时限正向证据）
    → H1 #1107（薄 Host 与音频）
      → I1 #1108（键盘/显示） ┐
      → C1 #1109（导出/传输） ┴→ B1 #1110（测试 Build + 不可变快照）
                                  → A1 #1111（正式真机完整旅程）
```

依赖箭头代表验收前置，不是看到 Issue Closed 就通过。R1 负结果可以完成研究，
但 H1 仍等待独立修复与同口径正向复测；新增根因修复必须独立 Task 回链，不在
R1 的证据文档提交中夹带 Core 优化。单一操作者占用设备，不启动并行刷机。

## 后续工程清单：供 D1 批准前评审

以下文件名是具体候选，不授予目录级扩张权限；尚未存在的文件用 code 字体，
不创建假链接。每项开始时刷新 main、查实际构建注册点，再把必要调整纳入本计划
或该 Task 的封闭清单。D1 只有在接口与所有权审定后才能结案。

### R1 #1106 — 真实音乐容量

候选文件：`docs/research/2026-09-10-cardputer-music-capacity.md`、
`tests/fixtures/cardputer/music_fixture.py`、`tests/fixtures/cardputer/music_fixture.json`、
`tests/fixtures/cardputer/README.md`、`tests/build/cardputer_music_fixture_test.py`、
根目录 `CMakeLists.txt`（注册 Python 测试）。R1 拥有 fixture 生成方法、素材许可、事件表与完整
身份；若不采用生成素材，先声明替换的确切音频文件，不临时下载未许可素材。
仓库外 probe 使用 EIM SDK 和 exact source，不进入产品依赖。

最低层测试固定音乐帧数/事件表/identity 一致性；same-source Facade/codec 测试；
ESP32-S3 严格编译与实际链接、峰值模型/heap/stack/DMA 测量；设计 §3 的真实音乐
与 deadline 观测。分别输出 baseline、失败、根因假设与正向/负向结论。
完整 Host 尚未存在，屏幕/键盘/USB 的真实共同负载最终由 H1/I1/C1 和 A1 复验，
不能在 R1 用 fake I/O 宣称最终通过。缺陷：小夹具通过被误用为正常音乐容量。

### H1 #1107 — Audio Driver 与薄 Host

候选文件：`apps/cardputer-host/CMakeLists.txt`、`apps/cardputer-host/sdkconfig.defaults`、
`apps/cardputer-host/partitions.csv`、`apps/cardputer-host/main/CMakeLists.txt`、
`apps/cardputer-host/main/main.cpp`、`apps/cardputer-host/main/audio_driver.hpp`、
`apps/cardputer-host/main/audio_driver.cpp`、`apps/cardputer-host/main/runtime_host.hpp`、
`apps/cardputer-host/main/runtime_host.cpp`、`scripts/cardputer-host.sh`、
`tests/platform/cardputer/audio_lifecycle_test.cpp`、`tests/platform/cardputer/CMakeLists.txt`、
`tests/build/cardputer_host_build_test.py`、根目录 `CMakeLists.txt`、
`apps/docs-site/docs/platform/native-audio.mdx`。

H1 固定 platform I/O 到 control executor 的消息接口、音频任务/DMA 退出协议和
HostSettings（音量/接收模式），I1/C1 消费这些接口，不各自调用 Facade。
H1 拥有 Host 初始构建入口；I1/C1 顺序修改注册文件，每次刷新前项合并结果，
不并行覆盖。产品专有 reserve/profile 数值由 B1 Assembly 注入，探针值不得硬编码
为所有产品通用默认。工程依赖若要求 Core 变更，先拆根因 Task。

最低层：fake I/O 的预热/静音/drain/关闭顺序及分配失败；真实 I2S/codec 启停、
DMA drain 与持续音乐；窄 Facade link closure；新测试按 native/component 注册。
并发修改必须运行对应 stress/TSan/ASan，fake Driver 不代替真机音频。
缺陷：停钟杂音、销毁后 callback、串口/显示阻塞 render、未收敛资源预算。

### I1 #1108 — 键盘与屏幕

候选文件：`apps/cardputer-host/main/keyboard.hpp`、`keyboard.cpp`、`display.hpp`、
`display.cpp`、`input_controller.hpp`、`input_controller.cpp`（均在该 main 目录）、
`apps/cardputer-host/main/main.cpp`、`apps/cardputer-host/main/CMakeLists.txt`、
`tests/platform/cardputer/input_controller_test.cpp`、
`tests/platform/cardputer/CMakeLists.txt`、`apps/docs-site/docs/platform/input.mdx`。

I1 独占键盘映射/去重复/丢键恢复和显示状态投影；状态依据 H1 实际处理回执。
最低层：按下/释放/自动重复、queue full 重试、FIFO overflow、接收确认/取消、
empty 禁止触发、屏幕错误恢复；真机逐键及组合键、音量、同时音乐负载。
量化物理输入时延按设计 §3；软件注入不证明物理前半段。缺陷：重复触发、丢释放、
UI 显示成功但 Runtime 未处理、显示争用破坏音频 deadline。

### C1 #1109 — 电脑导出与 USB 传输

候选文件：`apps/core-cli/src/main.cpp`、`apps/core-cli/src/runtime_export.hpp`、
`apps/core-cli/src/runtime_export.cpp`、`apps/core-cli/CMakeLists.txt`、
`apps/cardputer-host/main/transfer.hpp`、`apps/cardputer-host/main/transfer.cpp`、
`apps/cardputer-host/main/main.cpp`、`apps/cardputer-host/main/CMakeLists.txt`、
`scripts/cardputer-transfer.py`、`tests/platform/cardputer/transfer_test.cpp`、
`tests/platform/cardputer/CMakeLists.txt`、`tests/build/cardputer_transfer_test.py`、
根目录 `CMakeLists.txt`、`apps/docs-site/docs/hosts/core-cli.mdx`。
跨语言 framing 的 Contract/schema、正反例和 conformance 注册点须在 D1 工程规范
中另列精确文件；当前没有批准或分配新的 Contract ID/version，不能在 C1 私定。

电脑导出只能调用 `Application::export_runtime_content`，Host 不解析 Project Bundle。
输出为完整 Runtime Content 加 identity；传输消费它，设备只向 H1 提交经过 framing
校验的完整不可变 bytes，由 Core 决定内容合法性。首个电脑发送入口建议支持
macOS/Linux 命令行，Windows、Creator UI 是明确未承诺范围。
最低层：export 的真实 Project 往返/不改 Truth；Python/C++ 同一正反例；半包、
坏长度、错会话、重复/冲突 chunk、超时、丢 COMMIT 回包、重连 STATUS；PTY 集成
与真实 USB 完整旅程。缺陷：把 admission ACK 当装载成功、旧事务重放、半成品播放。

### B1 #1110 — Assembly 与测试 Build

候选文件：`apps/cardputer-host/module.json`、`products/lmdj/assembly.json`、
`products/lmdj/assembly.lock.json`、`products/lmdj/version.json`、
`products/lmdj/CMakeLists.txt`、`products/lmdj/src/cardputer_assembly.cpp`、
`apps/docs-site/docs/hosts/cardputer-host.mdx`、`apps/docs-site/docs/hosts/overview.mdx`、
`apps/docs-site/docs/assembly/lmdj.mdx`、`apps/docs-site/sidebars.ts`，以及官方 generator
为精确新 Build 生成的冻结文件（在分配前列出具体输出路径，不手写 metadata）。
若前项公开 API/Contract 要 staged identity 同步，须在其实施清单中保留对应义务，
不能等 B1 才第一次发现不兼容，或在未声明旧版本的情况下分发新 Host。

B1 独占 Host/Product identity、Assembly profile、版本 lock 与快照生成；名称方案
建议独立 `cardputer-host`，精确 SemVer/Build 由当时 manifests 与兼容性审计决定。
最低层：version/Assembly verifier、Host 构建打包与 manifest hash、门户全检查、
完整 exact-main 候选测试证据；然后正式测试 Build/同 Build 快照，最后 A1。
若 squash 后需要 witness，用官方 generator 独立提交，不手改冻结内容。
缺陷：固件/Assembly/快照来源混用，或无正式身份即让用户做最终验收。

### A1 #1111 — 真实设备验收

候选文件：`docs/quality/2026-09-10-cardputer-runtime-acceptance.md`、
`apps/docs-site/docs/hosts/cardputer-host.mdx`、
`apps/docs-site/docs/platform/native-audio.mdx`、`apps/docs-site/docs/platform/input.mdx`。
日期按实际验收日锁定。A1 拥有正式证据记录，不修改产品以解释同一 Build 的失败。
先核对硬件型号、供电、备份、精确刷机范围及所有 Build/内容身份，再执行设计 §7
的每一腿及 §3 的全部测量；每腿记录 far-side 观测、原始日志/录音 hash 与操作者。
失败保留原镜像证据；修复产生新 Build/快照，不能在旧行回填 PASS。

最低层：证据链接/身份与测试声明校验、门户检查；真正验收由指定设备的操作、
听感和仪器结果完成。缺陷：拿桌面或 tone、软件注入或旧 Build 代替新产品实测。
缺仪器、人耳确认或任何旅程腿都保持 pending，不关闭 umbrella。

## Version Management

Version impact: none
Reason: 当前 D1 partial delivery 仅为两个待批准文档，不修改 active API、Contract、
Host/Module manifest、Product Assembly 或 Build。后续新 Host、跨语言协议与可能
Core 修复要逐项审计 SemVer/兼容性；B1 从当时精确 manifests 分配新的 Product
BUILD，不预填版本，不增加 MINOR，不复用失败编号，不改变 Project Contract。
测试 Build 必须带同 Build 不可变快照；研究 probe 没有正式 Product 身份。
不创建 tag/Release/intent，不部署或做 Channel 晋级；旧测试镜像/备份保持可审计。

## Documentation Impact

Documentation impact: none
Reason: D1 是待批准设计，不改变 current 产品支持或 Portal 身份；引用现有源码事实
所以额外运行 docs-site check。后续 H1/I1/C1 的实际公开边界、B1 Assembly 与 A1
平台证据必须声明 required，并更新上述真实路由；新 Host 页面对应路由暂拟
`/hosts/cardputer-host/`，它不是已经发布的页面。

## Pitfall Impact

Pitfall impact: none — 当前未发现新增的过程不变量缺陷；沿用完整旅程、snapshot
先于正式验收、负研究结案不等于依赖通过等规则。后续保留首次失败和精确身份，
产品缺陷用回归测试，流程缺陷按 ledger 去重/记录/升级，不建立另一个共享索引。
