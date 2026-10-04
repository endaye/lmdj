# C2 — Stem Capability、PCM16 输出与真实 SDK Proof

日期：2026-10-03。基线：`7e40a0e83a803997682302e88f06b62e10e02820`。
Relates to #1164、#1172、#472。依赖 C1（PR #1808）。用户已授权实现、push、PR、merge。

## 范围与边界

正式 Capability `stem.split.v1` / `1.0.0`，输入 `source_audio`，四个 required
输出 `drums`、`bass`、`vocals`、`other` 各 max_count=1，nondeterministic。
参数首版只允许空对象；不暴露增益、归一化、角色子集或模型切换参数。
输出为相对输入第一帧起点为零、同采样率/声道/帧数的 canonical PCM16 WAV。
浮点乘 32768 后 ties-to-even，拒绝非有限数和越界结果；不削波、移位或逐路归一化。
validator 不可能从 WAV 证明音源分离质量或模型的声学对齐，真实模型/隔离/资源验证留给 E1。

`local.proof.stem` 是纯代码测试 Provider：重放输入 PCM 至四个角色，不做乐器分离。
model_identity 必须为 null，Provider source-package 摘要覆盖全部源/header/manifest。
复用现有 Slice 的 PCM16 inspector，显式依赖 `local.sample.slice`，避免复制解码器；
将来需要独立公共音频模块时另立 Task，不在此改变 SDK/基础模块接口。
Assembly 只注册此 test-platform Proof，不自动选择；默认策略不授予 stem.split.execute。
这次库存接线满足现行清单完整性规则；P1 的生产平台/模型注册与产品验收仍未执行。

## 精确文件范围

- `providers/local-proof-stem/{module.json,CMakeLists.txt}`
- `providers/local-proof-stem/include/lmdj/providers/local_proof_stem/{factory.hpp,validation.hpp}`
- `providers/local-proof-stem/src/{provider.cpp,validation.cpp}`
- `contracts/capability/stem.split.v1.json`
- `contracts/artifact-audio/lmdj.audio.stem-pcm16-wav.v1.md`
- `contracts/stem/lmdj.stem-parameters.v1.schema.json`
- `tests/fixtures/contracts/stem/parameters.json`
- `tests/core/provider/{CMakeLists.txt,stem_split_test.cpp}`
- `tests/conformance/schema_contract_test.py`
- `tests/build/version_test.py`
- `tests/core/facade/assembly_loader_test.cpp`
- `tests/core/facade/c_api_test.cpp`（安装清单的四项精确断言）
- `tests/host/{cli_test.py,mcp_stdio_test.py,performance_cli_session_test.py}`（安装清单）
- `tests/e2e/headless_core_proof.py`（跨 CLI/MCP 清单一致性）
- `packages/web-runtime-platform/test/control_runtime_test.cpp`（安装清单）
- `tests/platform/web/provider_owner_journey.mjs`（双 packaged Host 的四项清单）
- `CMakeLists.txt`（Provider target / coverage object inventory）
- `products/lmdj/{CMakeLists.txt,version.json,assembly.json,assembly.lock.json}`
- `products/lmdj/src/{compiled_assembly.cpp,cardputer_assembly.cpp}`
- `products/lmdj/generated/web-runtime-identity.{json,mjs}`
- `apps/cardputer-host/CMakeLists.txt`（Product Build 派生副本）
- `apps/docs-site/docs/providers/{local-proof-stem.mdx,overview.mdx}`
- `apps/docs-site/docs/contracts/capability.mdx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `apps/docs-site/sidebars.ts`
- `apps/docs-site/test/repo-facts.test.mjs`（新增 Provider/Contract 库存断言）
- `apps/docs-site/scripts/lib/snapshot-provenance.mjs`（新页面使完整性库存从 49 增至 50）
- `.agents/pitfalls/batch-key-omits-executed-host-test.md`（相同输入闭包问题第二次复发与升级 Issue）
- 本施工单
- 正式命令生成的 `apps/architecture-portal/versions.json`、
  `versioned_docs/version-PRODUCT_BUILD/**`、`versioned_metadata/version-PRODUCT_BUILD.json`、
  `versioned_sidebars/version-PRODUCT_BUILD-sidebars.json`、`static/versions/PRODUCT_BUILD/diagrams/**`。
  PRODUCT_BUILD = `2.0.80.0`；已核对最新 main 与全部 open PR 的实际 version.json，不删除旧快照。

如果定向检查证实存在其他精确身份断言，先将确切文件补入本施工单再修改。
不改 CI policy、阈值、超时、并发机制或旧 Slice 行为。

## 验证与缺陷

基线运行 `provider.sample_slice`。最低层 `provider.stem_split` component 测试：

- descriptor 与正式 JSON / 参数正反例完全一致；权限不默认授予。
- PCM16 编码上下限、正负 ties-to-even 与不同 fenv 舍入模式；NaN/Inf/越界拒绝，
  连同错 shape，防止无效数值进入 Artifact。
- 真实 execute 产生四路静音，同 Ref 仍保留四角色；非静音 PCM 重放形状/样本身份保持，允许的输入 metadata 被规范化而源 bytes 不变。
- 缺/重复/未知角色、错采样率/声道/帧数、坏 WAV、非 canonical metadata、篡改完整 Ref 被独立消费 validator 拒绝。
- 每个角色都必须校验；失败不发布部分 Candidate、释放 staging；失败终态重开一致。
- 成功后通过独立重开的 AttemptStore 逐角色读取，核对 digest/长度/媒体类型/bytes；
  null 模型身份与实现/参数身份持久化，源 sentinel 不变。

参数 Schema conformance、version/lock/module graph、Assembly loader、旧 Slice 与共享
输出回归；新增文件暂存后的 scope ownership；完整 Portal check。新增 component test
捕获上述已具名缺陷，不新增 CI gate。最终 committed inputs 的 batch_only lanes 按
现行规则记录真实 pass key；不依赖已知缺漏输入的旧缓存。

## Version Management

Version impact: required。
新 Provider `local.proof.stem` / `1.0.0`、API version 3，依赖 SDK `2.3.0` 与
Slice `1.0.4`。新 Capability `stem.split.v1` / `1.0.0`、输出 profile
`lmdj.audio.stem-pcm16-wav.v1` / `1.0.0`、参数 `lmdj.stem-parameters.v1` / `1.0.0`。
现存 SDK、Module、Host、Provider 和 wrapper Contract 无语义/依赖变化，不分配级联版本。
新增 Assembly 成员分配新 Product Build，正式生成 lock/compiled catalog/Runtime identity；
Cardputer product identity 同步，平台能力不扩大。正式 snapshot 与 squash provenance 必须通过。
Product Build 最终分配：`2.0.80.0`，重新核对 main 为 `2.0.78.0`，open PR 最高为本 PR 的未合入 `2.0.79.0`。

## Documentation Impact

Documentation impact: required。
Affected portal pages: /providers/local-proof-stem/ /providers/overview/ /contracts/capability/ /assembly/lmdj/
Reason: 正式四角色/量化/参数定义、Proof 接线与准确限制需要更新 current 页面。
新 Provider/Profile/参数的版本均由 active manifests 派生；不手填门户身份。

## 实现验证记录

最低层定向回归 `provider.stem_split`、`provider.sample_slice`、`facade.assembly_loader`、
`provider.output_validation`、`provider.attempt_output_read` 通过；Schema、version、module graph
与 Runtime identity checks 通过。Portal current 检查通过，新增页面同步完整性 pin 至 50。
正式完整 check 已运行；新 Build 的 snapshot 尚未生成，在实现提交后以 clean HEAD 运行
官方 version 命令，生成边界单独冻结，完整 Portal/投影验证通过后才允许 shipping。
本 Task 未发现符合 ledger 的新流程坑；集合排序比较由 SDK 既有语义与测试表达覆盖。

完整批次发现既有 Host/C ABI/Web 测试仍假定三个 Provider，补齐第四项的精确库存断言。
这些测试路径和施工单不在已冻结 source projection 中；保持官方不可变快照，不重写它。
修正后重跑受影响 native、sanitizer、coverage、packaged Web 和 package 验证。
首次 review 发布因 GitHub primary rate limit 403 失败（run 37087536590/1）；
保留原始失败证据，在日志给出的 reset 后重新运行完整 review，不以等待替代审查。

库存修正定向测试：host.cli、host.mcp_stdio、host.performance-cli-session、
facade.c_api、host.web_control_runtime、e2e.headless_core_proof，6/6 通过。

`package` 的 key 未包含实际执行的 C ABI test，跨库存修正仍不变；
已记录既有 pitfall 第二次复发并升级 https://github.com/endaye/lmdj/issues/1811。本 Task 不修改 CI 控制面，
受影响测试的旧失败与新 committed inputs 的 --no-cache 完整结果均保留。

## 当前 head 审查修正

审查产物 37087536590/1 的超大输入分类意见已接受：Provider 自身的 16 MiB
输入上限返回 UNSUPPORTED_AUDIO/source_audio_unsupported。测试允许 SDK 使用更大
输入预算，再供应结构有效的大 WAV，经真实 execute/独立重开确认 typed failure，
而不是只触发 SDK quota。输入替换意见通过 SDK custody 边界处置：替换 resolver
bytes 的相同长度/形状反例在 Provider run 前拒绝，原始输入/终态保持不变。
validator 明确记录 SDK 鉴权 immutable handle 的依赖，不重复哈希或访问 Project。

源码修正改变已冻结 projection。`2.0.79.0` 从未合入 main，不重写其已冻结 bytes：
保留原始 source/freeze 提交，撤回本 PR 最终树中的 79 生成目录及 versions 条目；
只以官方命令在 clean 修正提交上冻结新 `2.0.80.0`。既有 main 快照全部保留。
精确生成范围追加 `version-2.0.80.0/**`、metadata/sidebar、
`static/versions/2.0.80.0/**` 和 versions.json；79 的 Task 自有生成边界仅撤回，
不清理工作树、分支或原始 source commit。所有受源码/身份变化影响的 lanes 重跑。
