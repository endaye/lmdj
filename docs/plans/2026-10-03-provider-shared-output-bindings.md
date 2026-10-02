# C1: Provider 输出端口共享内容

日期：2026-10-03。基线 `65d01253`；承接 #1803，Relates to #1164、#472。
本 Task 只交付 SDK 的绑定语义与兼容性，不交付 Stem 模型或 Host 功能。

## 实现与精确文件

- `packages/provider-sdk/src/attempt_store.cpp`：不同输出端口允许相同完整 Ref；
  同端口重复与同 digest 不同 Ref 拒绝。输入唯一性不变。
- `tests/core/provider/byte_harness.hpp`：现有 fixture 增加两端口同内容配置。
- `tests/core/provider/conformance_test.cpp`
- `tests/core/provider/output_validation_test.cpp`
- `tests/core/provider/attempt_output_read_test.cpp`
- `tests/core/provider/execution_crash_test.cpp`
- `tests/core/provider/callback_stress_test.cpp`
- `.agents/pitfalls/batch-key-omits-executed-host-test.md`（实测的 lane 输入遗漏；本 Task 不修改 CI 控制面）
- 本施工单 `docs/plans/2026-10-03-provider-shared-output-bindings.md`

复用现有物理文件去重、锁、独立输出 buffer/lease 和逐 binding validator；
不加入新的缓存或并发机制。逻辑输出 bytes 每个端口计费，实际保留的每份
buffer 各自占用 staging 配额。

## 验证与旅程

先以旧 SDK 构建基线 reader 并保存旧成功/失败 terminal。增加两 required
端口同 bytes 的真实 execute 用例，先观察第二次 sink 写入失败，再修复。
新 SDK 重开旧 terminal；旧 SDK reader 重开新共享 terminal 并按完整 Ref
读取每个角色。若不兼容，停止 MINOR 路线并重新决定格式，不能放宽 reader。

独立用例覆盖同端口重复、同 hash 不同 media_type/length、漏绑/多绑/换绑、
逐端口 Schema、output/staging 上限、失败清理与成功 Attempt 不变。
崩溃旅程覆盖 reserved/inputs/staged/validated/published/terminal 后 SIGKILL，
重开时仅终态可见，已成功的双角色 Artifact 完整身份/内容保持可读。
同内容输出保持原线程同步约束；异线程 source 竞争关闭时仍拒绝，关闭后
source/sink callback 不得改变 terminal 或预算。

最低层：`provider.conformance`、`provider.output_validation`、
`provider.attempt_output_read`、`provider.execution_crash`、
`provider.attempt_isolation`、`provider.artifact_source`、
`provider.spec_regression`、`provider.callback_stress`；适用 ASan/TSan。
另跑版本/依赖检查、门户完整 check、新文件 scope admission；提交后按实际
`local-ci --list` 执行 batch-only lanes，保留 exact-head evidence。无新 CI gate。

## Version Management

Version impact: required。兼容实验通过后 SDK 2.2.1 → 2.3.0，api_version 3 不变。
依赖级联仅 PATCH：application-facade 6.5.1、web-runtime-platform 5.6.1；
local.proof.success/failure 2.0.4、local.sample.slice 1.0.4；core-cli 3.3.12、
core-mcp 3.5.2、native-host 3.4.7、cardputer-host 1.0.7、web-runtime-host 4.3.7、
creator-web 4.8.1。各自以下 manifest 与派生身份同步，不改变 API version。

精确级联文件：
- `packages/provider-sdk/module.json`
- `packages/application-facade/module.json`
- `packages/web-runtime-platform/module.json`
- `providers/local-proof-success/module.json`
- `providers/local-proof-success/CMakeLists.txt`
- `providers/local-proof-success/src/provider.cpp`
- `providers/local-proof-failure/module.json`
- `providers/local-proof-failure/CMakeLists.txt`
- `providers/local-proof-failure/src/provider.cpp`
- `providers/local-sample-slice/module.json`
- `providers/local-sample-slice/CMakeLists.txt`
- `providers/local-sample-slice/src/provider.cpp`
- `apps/core-cli/module.json`
- `apps/core-mcp/module.json`
- `apps/native-host/module.json`
- `apps/cardputer-host/module.json`
- `apps/web-runtime-host/module.json`
- `apps/creator-web/module.json`
- `apps/core-mcp/pyproject.toml`
- `apps/core-mcp/lmdj_core_mcp/__init__.py`
- `apps/cardputer-host/CMakeLists.txt`
- `apps/creator-web/package.json`
- `apps/creator-web/package-lock.json`
- `products/lmdj/version.json`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`
- `products/lmdj/src/compiled_assembly.cpp`
- `products/lmdj/src/cardputer_assembly.cpp`
- `products/lmdj/generated/web-runtime-identity.json`
- `products/lmdj/generated/web-runtime-identity.mjs`
- `tests/build/version_test.py`
- `tests/conformance/version_lock_test.py`
- `tests/host/native_host_source_boundary_test.py`（Native Host 精确 Facade 依赖断言）
- `tests/conformance/module_graph_test.py`（精确版本断言随级联同步）
- `tests/core/facade/assembly_loader_test.cpp`（精确版本断言随级联同步）
- `tests/core/provider/sample_slice_test.cpp`（精确版本断言随级联同步）
- `tests/core/provider/spec_regression_test.cpp`（精确版本断言随级联同步）

Product Build 根据最新 main 和开放 PR 分配：基线 2.0.76.0，#1800 已占用
2.0.77.0，候选 2.0.78.0；实施身份变动前再次核实。Contract wire shape 保持
lmdj.capability.v2 / terminal-attempt-v2。没有 release/tag/部署动作。

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/provider-sdk/ /contracts/capability/ /assembly/lmdj/ /operations/creator-changelog/ /operations/runtime-changelog/
Reason: 输出绑定、逐端口验证和预算语义变更，Assembly 依赖身份级联。

精确 current 文件：
- `apps/docs-site/docs/core/modules/provider-sdk.mdx`
- `apps/docs-site/docs/contracts/capability.mdx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/docs/operations/creator-changelog.mdx`（正式 generator 同步派生 Host 版本）
- `apps/docs-site/docs/operations/runtime-changelog.mdx`（同上）
- `apps/docs-site/test/repo-facts.test.mjs`（Host 版本投影断言）
- `apps/docs-site/diagrams/provider-sdk.architecture.json`
- `apps/docs-site/static/diagrams/provider-sdk.html`
- `apps/docs-site/static/diagrams/provider-sdk.svg`

版本快照是独立 freeze 步骤：源码提交干净后运行正式
`scripts/docs-site.sh version 2.0.78.0 canary`，只接纳生成器对该 Build 的
完整 inventory，以及最近五个快照保留规则精确选中的最旧 Build 删除清单。
生成后按 metadata 精确路径清单逐项核对，提交前做 projection 验证；source 与
snapshot 在同一 PR 内 squash，按政策核验等价 projection，需要时另行 witness。
源码阶段完整 check 在当前 snapshot 尚未产生时会报告缺失，先保存这个真实
结果，冻结后必须重新跑完整 check。旧快照不重写。

## 实测记录

- 最小红点：旧 SDK 构建成功后，`provider.attempt_output_read` 在
  `secondary_accepted` 断言失败，证实第二端口 sink 拒绝；修复后同用例通过。
- 基线 SDK 的独立静态链接 reader 保留于 `/tmp/lmdj-c1-compat/old-reader`；
  旧成功/失败由该基线真实 execute 生成。新 reader 读取两者通过；新 execute
  生成双 required 角色、单 blob terminal，旧 reader 对两角色逐项验证 digest、
  media type、length 和内容通过。未修改任何旧 terminal 或 reader。
- dev 八项定向测试全部通过；TSan `provider.callback_stress` 300 次关闭竞争通过。
- 版本/依赖与门户投影断言保持精确，不删除或放宽。提交后另在 PR body 记录
  exact-head batch-only lane 的机器生成 key。源码事实变动导致全矩阵选中。
- 快照生成 inventory 是该 Build metadata 的 `source_documents` / diagram 清单，
  与正式生成器固定边界一致；不在冻结后修改 current 源码，避免 projection 漂移。
