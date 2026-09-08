# LMDJ Detached Build Manifest 实施计划

- 日期：2026-08-24
- Issue：#286
- 决策：[`../../prd/decisions/2026-08-24-build-manifest-detached.md`](../prd/decisions/2026-08-24-build-manifest-detached.md)（#211）
- 分支：`feat/detached-build-manifest`，一个可评审 Conventional Commit

## 目标

Core 归档只含 payload；`build-manifest.json` 作为并列 detached 资产
`<package-name>.build-manifest.json` 与 `<package-name>.zip`、`.zip.sha256`、
`.zip.sha256.asc` 一起进入 Release 资产清单。`lmdj.build-manifest.v1` 的
Contract 与字段不变，`build_time`/`platform` 保留（version-management.md §4）。

## 现状事实

- `scripts/package-core.py` 把 Manifest 写进 staged package root，`create_zip()`
  打进归档；归档外只有 `.zip.sha256`。
- 资产清单有三处精确闸门，全部硬编码"product profile = 3 资产"：
  `tools/release/profiles.py::_profile_asset_paths`（persisted 资产复核）、
  `tools/release/prepare.py::_verify_profile_assets`（新构建资产）、
  `tools/release/audit.py::_asset_problem`（已发布 Release 资产）。
- `tools/release/profiles.py::build_core_package` 在 `build/dist` 找恰好一个
  ZIP + 其 `.sha256`，`_stage_and_sign` 产出 3 资产。
- transitions / publish-release.yml / rehearsal 不硬编码资产数，跟随 release
  plan 的资产表，无需改动。
- `tests/distribution/package_acceptance_test.py` 断言 Manifest 在归档内；
  `tests/build/release_prepare_test.py` 有一个 core-package persisted 资产夹具
  （3 资产）。audit/transitions 的 product 夹具全部走 web-runtime-host，不受影响。

## 任务

### Task 1 — `scripts/package-core.py`：Manifest 写出归档

- `package()` 把 Manifest 写到 `output_dir / f"{package_name}.build-manifest.json"`
  （`generate_manifest` 的 `artifacts_root` 仍是 staged package root，输出路径在
  root 之外，生成器本身不变），chmod 0644；不再写入 `package_root`。
- 更新 "detached digest is the only out-of-band integrity signal" 注释：Manifest
  现在也在归档外。
- 验收：`tests/distribution/package_acceptance_test.py` 见 Task 2。

### Task 2 — 分发验收测试

- `tests/distribution/package_acceptance_test.py`：期望文件集移除
  `build-manifest.json`；断言归档旁存在 `<stem>.build-manifest.json` 且其
  product / assembly_lock_sha256 / git_revision / artifacts 与解包内容逐文件一致
  （沿用现有断言，改读 detached 文件）。
- 验收：该测试在 Task 1 的代码上通过；未改 Task 1 时按新形状失败（先写测试
  确认红，再实现）。

### Task 3 — `tools/release/`：core-package 四资产清单

- `profiles.py`：
  - `build_core_package` 额外要求 `build/dist` 中恰好一个
    `<archive-stem>.build-manifest.json` 常规文件；`_stage_and_sign` 增加
    `extra` 参数把 Manifest 原样 staged（不签名；签名校验链不变，只签
    checksum），返回 4 资产。
  - `_profile_asset_paths` 增加 `profile` 参数：core-package 要求
    `<stem>.build-manifest.json` 存在于同一目录，错误消息按 profile 说明
    期望数量；web-runtime-host 保持 3 资产。
  - `verify_existing_profile` 传入 profile；core-package 额外解析 Manifest：
    `contract == "lmdj.build-manifest.v1"`、`product.version == intent.identity`、
    `git_revision == intent.target_revision`，不符则 ProfileError。这防止把
    属于别的 Build 的 Manifest 挂进 Release。
- `prepare.py::_verify_profile_assets`：按 `intent.profile` 决定期望资产集
  （core-package 4、web-runtime-host 3、source-only 0）。
- `audit.py::_asset_problem`：同样按 profile 决定期望数量与名称集。
- 验收：`python3 -m unittest tests.build.release_prepare_test`（含更新的
  core-package 夹具与新增负例：缺 Manifest、Manifest 身份不符）、
  `python3 -m unittest tests.build.release_audit_test`、
  `python3 -m unittest tests.build.release_transitions_test`。

### Task 4 — 文档与 Portal

- `packaging/core/README.md`：Manifest 段改为"与归档并列的
  `<package-name>.build-manifest.json` 记录 Product Build、source revision、
  Assembly lock 与每个文件的 SHA-256；解包后可逐文件核验"。
- `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`：
  资产清单示例补 detached Manifest（core-package 四资产，source-only 不变）。
- Portal `apps/architecture-portal/docs/operations/version-and-release.mdx`：
  把 2026-08-24 决策句从"将移出/机器任务 A3 落地时生效"改为已实现——四资产
  清单自此生效；`source_paths` 已有决策文件，无需新增。
- `docs/quality/2026-08-17-machine-task-todo.md`：A3 行标记 done 并链接 #286
  与本计划。
- `docs/quality/2026-08-16-outstanding-work-before-stage9.md`：A3 节补实现落
  地记录。

## 不做的事

- 不加 Core 包的 two-clean-build 门禁（本变更使其成为可能，是否启用另行决定）。
- 不改 `lmdj.build-manifest.v1` 任何字段；不改 `generate_manifest`。
- 不改 web-runtime-host profile、source-only profile、transitions、
  publish-release.yml、rehearsal。
- 不做 Manifest 逐文件 hash 对归档内容的深度复核（release plan 的逐资产
  sha256 已绑定字节；深度复核留作后续硬化）。
- 无 tag、Release、部署、发布、Channel promotion。

## 验证

- `python3 -m unittest tests.build.release_prepare_test tests.build.release_audit_test tests.build.release_transitions_test tests.build.release_skill_test`
- `python3 tests/conformance/version_lock_test.py`
- `python3 tests/distribution/package_acceptance_test.py --build-root build/core/release`（本机已有 Release 构建树）
- `scripts/architecture-portal.sh check`
- `bash tests/build/test_active_tree.sh`
- `git diff --check origin/main...HEAD`

## Version Management

Canonical policy：`docs/governance/version-management.md`。

**Version impact: none.**

- Product Build：不变。没有 Assembly 成员、Module API、Host 协议或可运行产品
  行为变化；打包工具与 Release 机器改变，打包出的 Assembly 相同。
- Core Modules / Hosts / Providers：不变。不触碰 `packages/`、`apps/`、
  `providers/`、`products/`。
- Contracts：不变。`lmdj.build-manifest.v1` 字段与 SemVer 不变，只有发布位置
  变化（决策 #211 已记录）。
- 变更文件在 `scripts/`、`tools/`、`tests/`、`packaging/`、`docs/` 与 Portal
  当前页，均无版本身份。
- 无 tag、Release、Channel promotion 或部署被授权。

## Documentation impact

**required。** Affected portal routes：`/operations/version-and-release/`。
四资产清单在本 Task 从"已决策"变为"已实现"。
