# Project Bundle 收窄到 writer 当前级别（退役 v1–v4 schema，Build 1.0.57.0）

## Task

按[决策](../prd/decisions/2026-09-15-project-bundle-current-level-only.md)
把开发期 Project Bundle 收窄为只支持 writer 当前 Project Contract 级别
（`lmdj.project.v5`）：Bundle 枚举只剩当前级别，容器版本与 Contract 版本
同步为 `2.0.0`，旧容器与旧级别一律拒绝；`lmdj.project.v1`–`v4` 的
schema 定义退役，旧 checkpoint 仍由 Host loader 手写结构校验迁移读取。

Contract 变更与 Product Build `1.0.57.0` 分配同 PR 完成。最初曾计划拆成
两个 PR（先退役、后切版），但 `version_test.py` 的 `verify()`、
`ci_canary_metadata_proposal_test.py` 与 docs-site 的 repo-facts 门禁都把
磁盘上的 Contract 源绑定到 `assembly.json`：schema 一删/一升，assembly
不变则三条门禁必红，拆分不可行；而 Assembly 变化按版本政策必须分配新
Build。先例 #894 同样是单 commit 同时做 Contract 变更与 Build 分配。

Declared files:

- `contracts/project/lmdj.project-bundle.v1.schema.json`（枚举收窄、
  `x-lmdj-contract-version` 与 `contract_version` const 升 `2.0.0`）
- `contracts/project/lmdj.project.v1.schema.json`、`v2`、`v3`、`v4`
  （删除，退役）
- `tools/project-bundle/project_bundle.py`（`CONTRACT_VERSION`、
  `READABLE_CONTRACT_VERSIONS`、`PROJECT_CONTRACTS` 收窄；初始 checkpoint
  身份校验接受任意出生级别，head checkpoint 仍由当前级别 gate）
- `packages/project-io/src/project_bundle_transfer.cpp`（parse_index 只
  接受 `2.0.0` + `lmdj.project.v5`）
- `packages/web-runtime-platform/web/project_bundle_reader.mjs`（reader
  allowlist 收窄）与其测试 `test/project_bundle_reader.test.mjs`（旧容器
  用例改拒绝；reader 集合与 Contract const/enum 严格绑定）
- `tests/conformance/schema_contract_test.py`（删 v1–v4 schema 引脚与
  fixture 校验；共享规则改在 v5 上直接钉字面量，存续规则的可执行边界
  移植到 v5；Bundle 引脚更新）
- `tests/conformance/json_schema_test.py`（删 v2 schema/fixture 校验段）
- `tests/conformance/project_bundle_contract_test.py`（旧容器/旧级别改
  拒绝用例；绑定测试断言收窄）
- `tests/build/version_test.py`（`expected_contract_sources` 收缩；
  `assembly["contracts"]` 字面量删 v3/v4、bundle 升 `2.0.0`）
- `tests/build/ci_change_scope_test.py`、
  `tests/build/ci_canary_metadata_proposal_test.py`（示例路径指向仍
  存在的 schema）
- `tests/build/release_candidate_inputs_test.py`、
  `release_dispatch_receipt_test.py`、
  `release_orchestration_driver_test.py`、
  `tests/platform/cardputer/observation_wire_test.cpp`（Build/tag 引脚
  跟随 1.0.57.0）
- `tests/fixtures/contracts/project-bundle-valid.json`、
  `project-bundle-invalid-traversal.json`（升到 `2.0.0` + v5）；
  `project-v2-valid.json`、`project-v2-invalid-playback.json`（删除）；
  其余 v3/v4 fixture 保留为 loader checkpoint 数据
- `tests/core/facade/web_runtime_limits_test.cpp`、
  `tests/core/facade/sample_surface_test.cpp`、
  `tests/core/facade/application_test.cpp`、
  `tests/core/project_io/project_bundle_transfer_test.cpp`、
  `packages/web-runtime-platform/test/control_runtime_test.cpp`、
  `tests/platform/web/project_io/project_io_web_test.cpp`（合成 bundle
  index 辅助升到 `2.0.0` + v5）
- `products/lmdj/version.json`（Build 56 → 57）、`assembly.json`
  （product version 1.0.57.0；contracts 删 v3/v4、bundle 升 2.0.0）、
  `assembly.lock.json` 与 `products/lmdj/src/compiled_assembly.cpp`
  （`scripts/version.py lock` 生成）、`products/lmdj/src/cardputer_assembly.cpp`
  （Build 与 Assembly 摘要绑定，先例 #1203）、
  `products/lmdj/generated/web-runtime-identity.{json,mjs}`
  （`tools/web-runtime/generate_runtime_identity.py` 生成）
- `apps/cardputer-host/CMakeLists.txt`（PROJECT_VER 引脚）
- `apps/docs-site/docs/contracts/project-bundle.mdx`、
  `apps/docs-site/docs/contracts/project.mdx`（当前事实改写；frontmatter
  `contracts` 删 v3/v4 与 assembly 对齐）、
  `apps/docs-site/docs/assembly/lmdj.mdx`、`hosts/cardputer-host.mdx`、
  `hosts/overview.mdx`、`product/capability-map.mdx`（当前 Build 引用）
- `apps/docs-site/test/fixtures/retired-page.md`（source_paths 指向仍
  存在的文件）
- Portal 不可变快照：`scripts/docs-site.sh version 1.0.57.0 canary`
  产物（versions.json、`versioned_docs/version-1.0.57.0/`、
  versioned_metadata、versioned_provenance）
- `docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md`、
  本计划

## Verification

```bash
python3 scripts/version.py verify --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json
python3 tests/build/version_test.py
python3 tests/build/ci_canary_metadata_proposal_test.py
python3 tests/build/ci_change_scope_test.py
python3 tests/build/release_candidate_inputs_test.py
python3 tests/build/release_dispatch_receipt_test.py
python3 tests/build/release_orchestration_driver_test.py
python3 tests/conformance/schema_contract_test.py
python3 tests/conformance/json_schema_test.py
python3 tests/conformance/project_bundle_contract_test.py
node --test packages/web-runtime-platform/test/project_bundle_reader.test.mjs
cmake --build build/core/dev -j 8
ctest --test-dir build/core/dev -R 'project_bundle|web_runtime_limit|sample_surface|web_control_runtime|facade.application' --output-on-failure
bash tests/build/test_active_tree.sh
scripts/docs-site.sh check
```

`tests/platform/web/project_io/project_io_web_test.cpp` 属 Emscripten lane，
本机无 emcc，由 CI 的 Web Host proof 覆盖；改动与其他五个已验证的合成
index 辅助同型。

## Version Management

- Contract `lmdj.project-bundle.v1`：`1.3.0` → `2.0.0`（MAJOR：枚举收窄
  与旧容器拒绝都是不兼容变更）。
- Contract `lmdj.project.v1`–`v4`：定义退役，从 active Assembly 移除，
  不再分配新版本；`lmdj.project.v5` 保持 `5.0.0` 不变。
- Product Build：`1.0.56.0` → `1.0.57.0`（同一 PR 分配，原因见 Task 节；
  先例 #894）。Channel 不变更；不可变 Portal 快照 `1.0.57.0 · canary`
  随本 PR 冻结。
- 无 Module SemVer 变化：Project I/O 等模块的公开 API 未变，仅 reader
  allowlist 收窄。

## Documentation Impact

Documentation impact: required

受影响路由：`/contracts/project-bundle/`、`/contracts/project/`（当前
级别事实与退役说明，frontmatter 与 active Assembly 对齐）、
`/assembly/lmdj/`、`/hosts/cardputer-host/`、`/hosts/overview/`、
`/product/capability-map/`（当前 Build 引用）。Assembly 变化按政策
冻结不可变快照 `version-1.0.57.0`。
