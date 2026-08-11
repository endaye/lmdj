# Risk-Based CI Gating Design

日期：2026-08-11

状态：规格已批准，本地实现完成，远端迁移待单独授权

## 1. 结论

LMDJ 将 Pull Request CI 从“每次修改都运行完整 Core/Web 矩阵”改为集中式风险分类：

1. 每个 PR 先由唯一的 `Change Scope` 分类器读取完整 diff、PR 状态和显式标签；
2. Draft PR 只运行轻量反馈，Ready PR 只运行本次实际影响的正式 lane；
3. `ci:full`、共享控制面、高风险路径、未知路径和 `main` push 强制完整 PR 矩阵；
4. 唯一稳定 required check `PR Gate` 按版本化 scope manifest 校验本次应运行的所有 job；
5. `main` push 与 nightly 继续保留完整验证和压力采样；
6. CI 时限目标是非阻断 SLO，只有独立的 job 安全上限和测试行为 timeout 会失败；
7. 本设计不增加 runner，并以“归一化 routine GitHub-hosted minutes 不得持续高于旧基线”为
   预算目标；净效果必须经过观察周确认。runner 扩容在独立设计中讨论。

目标是在不把不确定性静默放行的前提下，将纯文档 Ready PR 的端到端反馈目标缩短到五分钟，
单一子系统 Ready PR 缩短到十至十五分钟，并让 Core、Web、Portal、Creator、Deploy 和
CI 控制面的门禁所有权可审计。

## 2. 背景与问题

当前 `.github/workflows/ci.yml` 对所有指向 `main` 的 PR 运行同一套 job，没有按 changed
paths 分类。纯 Markdown PR 也会运行 Ubuntu/macOS Core Proof、Linux/macOS sanitizer、
Coverage、Web Toolchain、Formal Web Runtime Host、Creator 和 Runtime Lab。

近期记录显示：

- 纯计划文档 PR 的完整 Core CI 仍约需十九分钟；
- Web Runtime Host 单 job 常需十八至二十八分钟；
- 自托管 Linux 池排队可把完整 PR 的端到端等待放大到三十至七十分钟；
- macOS 主 lane 通常只需二至四分钟，并不是主要长尾；
- `creator-web` 目前等待 `web-toolchain-conformance` 和 `core-ubuntu`，即使 job 之间不传递
  artifact，形成了不必要的串行关键路径。

GitHub 分支保护当前只硬性要求 `core (ubuntu-latest)` 和 `core (macos-latest)`，而仓库
治理要求每个适用的 PR CI job 成功。新设计用一个稳定聚合门禁消除“平台只强制两项、
政策要求全部适用项”的执行差距。

## 3. 目标

- 纯文档变更不运行 Core、Web Runtime、sanitizer 或 Coverage。
- 与 Core 无关的 Host、工具、测试和 CI 变更不运行 Core。
- 测试文件按被测执行面分类，而不是把 `tests/**` 视为 full。
- CI 文件按所控制的执行面分类；只有中央路由和 required gate 等共享控制面强制 full。
- Ready PR 的所有适用正式门禁仍是 merge 前证据。
- 未知、缺失、矛盾或无法解析的分类结果 fail closed。
- 新 commit 取消同一 PR 的旧运行，但不同 PR 不互相取消。
- 以旧无条件 PR/main 矩阵为 hosted-minutes 基线；focused 分流预计抵消新增控制 job 与 full-main
  工作，但在观察周数据确认前不承诺净用量必然下降。
- SLO 与 correctness gate 分离，慢但正确的执行不因软目标超时而失败。
- 保留既有 semantic failure、No-Retry 和 macOS infrastructure fallback 边界。

## 4. 非目标

本设计不包含：

- 增加、删除或重新配置 self-hosted runner；
- runner 主机、服务、凭据、标签或电源管理变更；
- 增加 GitHub Actions 预算；
- 修改 Core、Host、Provider、Contract 或 Product behavior；
- 修改 test tier、coverage floor、sanitizer workload 或 Product Proof 语义；
- release、deployment、Channel promotion 或 Product Build 分配；
- 用 merge 后验证替代本设计明确要求的高风险 merge 前门禁；
- 自动 retry 已发布的编译、Proof、测试、sanitizer 或 Coverage 失败。

## 5. 总体架构

```text
Pull Request event
        |
        v
Change Scope ---- ci:full / Draft / Ready / main / unknown-path policy
        |
        +---- versioned scope manifest + job summary + retained artifact
        |
        +---- Docs / Static
        +---- Architecture Portal
        +---- Core Ubuntu / ASan / Coverage / macOS
        +---- Web Toolchain / Runtime Host / Creator / Runtime Lab
        +---- Deploy Contract / CI Contract
        |
        v
PR Gate ---- validate manifest, current SHA, expected jobs and actual results
        |
        v
required branch-protection result
```

所有正式 lane 都直接依赖 `Change Scope`；需要可信 runner 池的 lane 还依赖对应 selector。
除了 runner 选择、真实 artifact 或环境传递关系，lane 之间不得用 `needs` 制造顺序；完整结果
统一由 `PR Gate` fan-in。macOS primary/fallback/adjudicator 内部依赖继续保留，因为它们共同
发布一个平台结果。

## 6. Change Scope

### 6.1 输入

分类器使用：

- PR base SHA 和 head SHA；
- base/head 之间含状态、NUL 分隔且未经截断的完整 changed-file inventory；
- PR 是否为 Draft；
- 当前标签中是否存在 `ci:full`；
- event 是 Pull Request、`main` push 还是显式 dispatch；
- 版本化路径归属配置。

workflow 只为读取实时 PR Draft/label metadata 增加最小 `pull-requests: read`；changed files 仍来自
本地 Git objects，不用 PR Files API。fork PR 不因读取 metadata 获得任何 self-hosted 或 secret
权限。

checkout 必须包含可验证的 exact base/head Git objects。分类器优先使用本地
`git diff --name-status -z BASE HEAD` 生成 inventory，从根源避开 GitHub Compare/Files API
约 3,000 文件的响应上限。只有对象无法安全取得时才允许使用分页 API fallback；fallback
必须证明分页完整，任何达到服务上限、页数/总数矛盾或疑似截断的响应都升级 `full` 并在
manifest 记录原因。无法证明完整性时分类 job 失败。

文件删除和重命名必须按旧路径与新路径的并集分类。分类器不得只检查最后一个 commit，
也不得依赖 PR title、branch name 或提交信息推断风险。

### 6.2 输出合同

分类器输出版本化 JSON，最少包含：

```json
{
  "schema": "lmdj.ci-scope.v1",
  "base_sha": "<40-hex>",
  "head_sha": "<40-hex>",
  "mode": "focused",
  "reasons": ["apps/web-runtime-host/** changed"],
  "changed_files": [
    {
      "result": "renamed",
      "paths": [
        "apps/web-runtime-host/README-old.md",
        "apps/web-runtime-host/README.md"
      ]
    }
  ],
  "lanes": {
    "docs_static": true,
    "portal": true,
    "core_ubuntu": false,
    "core_asan": false,
    "core_coverage": false,
    "core_macos": false,
    "web_toolchain": false,
    "web_runtime_host": true,
    "creator": false,
    "web_runtime_lab": false,
    "deploy_contract": false,
    "ci_contract": false,
    "chameleon_lab": false,
    "package": false
  },
  "required_jobs": [
    "docs-static", "portal", "select-ubuntu-runner", "web-runtime-host"
  ]
}
```

schema、mode、lane 和 job name 都使用闭合 allowlist。lane 的完整 v1 枚举是：

- `docs_static`、`portal`、`ci_contract`；
- `core_ubuntu`、`core_asan`、`core_coverage`、`core_macos`；
- `web_toolchain`、`web_runtime_host`、`creator`、`web_runtime_lab`；
- `deploy_contract`、`chameleon_lab`、`package`。

E2E、package/version contract 和 Apple/native stress 是上述 lane 内部的 workload selector，
不是额外 lane：E2E 属于 `core_ubuntu`，package/version contract 属于 `package`，Apple/native
stress 属于 `core_macos`。因此路径归属表不得产生枚举外值。

`required_jobs` 必须包含 selected lane job 及其本次实际需要的 selector/adjudicator 等支持
job；未被选择的支持 job 不得运行。未知字段、未知枚举、重复或冲突 job、SHA 不匹配和非
canonical path 必须拒绝。manifest 同时写入 job summary 并上传为
artifact；summary 必须解释每个被选择或升级 lane 的具体理由。

`changed_files` 的闭合字段是 `result` 与 `paths`。普通增删改记录恰好一个 path；rename/copy
记录恰好两个 path，并按旧路径与新路径的消费者并集分类。对 `focused` manifest，validator
必须在 normal Ready/no-label 语义下从该 inventory 重新计算 ownership 与昂贵族升级：lane map
必须与路径并集完全相等；未知、未归属、full-rule 或三个昂贵族都拒绝 focused 编码。

### 6.3 模式

分类器只有三种模式：

- `draft`：轻量反馈，不建立正式 merge 证据；
- `focused`：Ready PR 运行实际影响的正式 lane；
- `full`：把 §6.2 全部 v1 lane 设为 true；不包含 nightly 重复采样或生产部署。

以下情况强制 `full`：

- PR 包含 `ci:full`；
- 修改 Change Scope、PR Gate、scope schema 或主 PR workflow；
- 修改 required-check 汇总、共享 runner 路由/fallback 或共享构建控制面；
- 修改根 CMake、公共 test registration/taxonomy、共享 fixture、Product Assembly 或 Contract；
- 同一 PR 横跨三个或更多昂贵执行族；
- 新增未知顶层路径或出现不能安全归属的删除/重命名；
- `main` push；
- 显式 full dispatch。

未知路径是可成功分类的 `full`，不是静默忽略。diff 获取失败、manifest 无法生成或输入不可信
则分类 job 失败并阻断，不猜测结果。

昂贵执行族只统计 `core`、`web-runtime`、`creator` 和 `deploy/package`：Core 的四个 lane
合计一个族，Web Toolchain/Runtime Host/Lab 合计一个族。`docs_static`、`portal`、
`ci_contract` 和 `chameleon_lab` 不参与“三个或更多”升级计数。因而 docs + Portal + 单一
Web Host 仍是 focused，不会仅因廉价文档 lane 被升级 full。

## 7. PR 生命周期

主 required workflow 明确监听 `opened`、`synchronize`、`reopened`、`ready_for_review` 和
`converted_to_draft`，不监听 `labeled`/`unlabeled`。Change Scope 每次运行都通过 PR read API
读取当前实时标签，不使用可能过期的原始 event label snapshot。

| 状态或事件 | 行为 |
| --- | --- |
| Draft 新建/更新 | 运行 draft 反馈 |
| 转为 Ready | 同一 head SHA 重新分类并运行正式 focused/full 门禁 |
| Ready 推入新 commit | 取消旧 SHA 未完成运行，按新 SHA 重跑 |
| 添加 `ci:full` | 标签本身不触发；需要立即升级同一 SHA 时，先等待当前 run 结束或显式取消它，再对该 run 执行 Re-run all jobs；分类器读取实时标签并 full |
| 删除 `ci:full` | 不取消、不自动降级当前证据；后续普通触发或显式 rerun 才按实时标签重新分类 |
| 转回 Draft | 取消尚未完成的重型运行并回到 draft |
| `main` push | 强制 full |

不监听标签事件是有意的安全边界：如果主 workflow 监听所有 `labeled`/`unlabeled`，无关标签
会进入同一 concurrency group 并取消接近完成的 run；即使快速 no-op，静态声明的 skipped
`PR Gate` 也可能成为同 SHA 的最新 required check。显式 rerun 复用原 PR-associated check
suite。若原 run 仍在执行，GitHub 不允许重跑，因此操作者必须等待或取消后再 rerun；这既让
`ci:full` 在同一 SHA 上明确升级，又不为 triage/priority 标签创建第二套 required 结果。

PR 的 `opened`、`synchronize`、`reopened` 和状态转换使用按 PR number 稳定的
concurrency group，并启用 `cancel-in-progress`。不同 PR 不互相取消。`main` push 使用
per-SHA group，`cancel-in-progress: false`；连续 merge 的每个 main SHA 都必须保留自己的完整
结果，不能用后一个 push 取消前一个证据。PR 与 `main` group 永不相同。

被后续 commit 取消的旧 PR run 不构成当前 SHA 的语义失败；当前 SHA 的正式 `PR Gate`
必须完整发布。

Draft 只发布轻量的 Change Scope、Docs/static 与 CI Contract 证据：Docs/static 对精确
base/head 执行 `git diff --check`，CI Contract 执行 pinned actionlint 与 `ci_*` Python 契约。
Draft 不运行 Portal、Node 产品单测、Emscripten/Playwright、C++ 构建、Core Proof、sanitizer、
Coverage 或 macOS。转为 Ready 会对同一 head 重新分类；Draft 结果不能替代该正式结果。

## 8. 路径归属

路径匹配采用所有命中规则的 lane 并集，不采用 first-match，也不允许更具体规则减去上层
规则。风险升级在求并集后执行。例如 `apps/creator-web/README.md` 同时选择 `docs_static`、
`creator` 和 Portal 附加 lane；`apps/creator-web/src/editor.ts` 选择 `creator` 和 Portal。
文件级规则只能增加消费者。分类契约必须覆盖目录、扩展名和文件级规则重叠的用例。

### 8.1 产品与源码

| 路径 | focused 正式门禁 |
| --- | --- |
| 普通 Markdown、`docs/**`、研究与计划 | Docs static |
| `docs/governance/**` | Docs static + Portal |
| `docs/quality/**`、`docs/deploy/architecture-portal.md` | Docs static + Portal |
| `docs/deploy/web-runtime-host.md` | Docs static + Portal + `deploy_contract` |
| `apps/README.md` | Docs static + Portal |
| `apps/architecture-portal/**` | Portal |
| `apps/creator-web/**` | Creator |
| `apps/web-runtime-host/**` | Web Runtime Host |
| `apps/web-runtime-lab/**` | Web Runtime Lab |
| `apps/chameleon-lab/**` | `chameleon_lab` |
| `apps/core-cli/**`、`apps/core-mcp/**` | Core Ubuntu Proof；跨平台 Host 变更增加 macOS |
| `apps/native-test-host/**` | Core Ubuntu + macOS native |
| `packages/web-runtime-platform/web/**`、仅 MJS 的 test、source-boundary test | Portal + Web Toolchain + Web Runtime Host |
| `packages/web-runtime-platform/CMakeLists.txt`、`module.json`、`include/**`、`src/**`、C++ test | Portal + 完整 Core + Web Toolchain + Web Runtime Host |
| 其他现存 `packages/<module>/**` | Portal + 完整 Core PR 矩阵；新增未知 package 未显式归属时 full |
| `providers/**` | `core_ubuntu` + `core_asan` + `core_coverage`；Provider/Assembly 路径在 `core_ubuntu` 内增加 E2E |
| `contracts/**` | full |
| `products/lmdj/**` | full + Portal |
| `workers/**` | 对应 Provider/Host；不能分类时 full |
| 根 CMake、共享 CMake、版本/Assembly Lock | full |
| 未知或新增顶层路径 | full |

Architecture Portal 是否运行至少保留现有文档影响路径集合：`AGENTS.md`、`CLAUDE.md`、PR
模板、相关 workflow、`apps/**`、`packages/**`、`providers/**`、`workers/**`、
`contracts/**`、`products/lmdj/**`、`docs/governance/**` 和门户脚本，并补上被 current Portal
声明为 source/evidence 的 `docs/quality/**` 与上述 `docs/deploy/**`。
Portal 是表中门禁的附加 lane：命中该集合的 Creator、Web Host、Core 或其他实现变更仍要
运行 Portal，不因主要执行面已经选中而省略。

### 8.2 其他现存顶层路径

| 路径 | focused 正式门禁 |
| --- | --- |
| `tools/web-runtime/**` | Web Toolchain + Web Runtime Host + Creator |
| `tools/project-bundle/**` | Creator |
| `packaging/core/**` | `package` + Core Ubuntu |
| `cmake/**`、`CMakePresets.json` | full；同时影响 native Core 与 Web CMake |
| `testdata/**` | Docs static；当前只有未接入 active Core 的 benchmark manifest/docs |
| `references/**` | Docs static；冻结参考材料永远不作为 active product source |
| `output/playwright/**` | Portal；当前是受控说明书截图 |
| `netlify.toml` | `portal` + `ci_contract` |
| `.gitattributes` | ownership 并集为完整 Core + `web_runtime_host` + `creator` + `package` + `ci_contract`，随后按昂贵族规则升级 full |
| `.gitignore` | full；影响 clean-tree、generated output 与 toolchain cache 边界 |
| `AGENTS.md`、`CLAUDE.md` | Docs static + Portal |
| 根 `README.md` | Docs static |
| `.github/**` | 按 §9 CI 控制面表求并集；未知 GitHub 配置 full |

`testdata/**` 当前没有 active New Headless Core 消费者；若未来代码开始消费它，新增消费者的
同一 Task 必须更新路径归属和契约测试，不能继续沿用 docs-only。`.gitattributes` 的 LFS 规则
控制 WAV、二进制和包资产的 checkout/hydration，所以按全部现有 fixture/package 消费者求
并集，而不是归入普通仓库元数据；该并集横跨 Core、Web、Creator、package 三个以上昂贵族，
因此按统一升级规则成为 `full`，没有文件级豁免。

### 8.3 脚本

| 路径 | focused 正式门禁 |
| --- | --- |
| `scripts/core.sh` | 完整 Core + `package`；它同时拥有 package 子命令 |
| `scripts/core-coverage.sh`、Core dependency/build 脚本 | 完整 Core |
| `scripts/web-toolchain-conformance.sh` | Web Toolchain |
| `scripts/web-runtime-host.sh` | Web Runtime Host |
| `scripts/creator-web.sh` | Creator |
| `scripts/web-runtime-lab.sh` | Web Runtime Lab |
| `scripts/chameleon-lab.sh` | Chameleon Lab |
| `scripts/architecture-portal.sh` | Portal |
| `scripts/web-runtime-deploy.sh` | Deploy contract；不部署、不运行 Core |
| `scripts/version.py`、`scripts/package-core.py` | `core_ubuntu` + `package` |
| 新增共享脚本或消费者不明 | full |

### 8.4 测试

测试代码继承被测对象的 lane：

| 路径 | focused 正式门禁 |
| --- | --- |
| `tests/core/**` | Core Ubuntu + ASan + Coverage |
| `tests/core/audio/**`、concurrency/stress | 上述门禁 + macOS/native stress |
| `tests/core/facade/c_api_stress_test.cpp` | 完整 Core，包含 macOS/native stress |
| `tests/core/project_io/storage_platform_contract_test.cpp`、`project_bundle_transfer_test.cpp` | 完整 Core，包含 macOS/native concurrency/stress |
| `tests/core/support/**`、`tests/core/provider/CMakeLists.txt` | 完整 Core；公共 helper/test registration 输入 |
| `tests/platform/audio/**` | macOS Core/native sanitizer |
| `tests/platform/web/toolchain/**` | Web Toolchain |
| `tests/platform/web/audio/**` | Web Toolchain + Web Runtime Host |
| `tests/platform/web/project_io/**` | Web Toolchain |
| `tests/platform/web/host/**` | Web Runtime Host |
| `tests/platform/web/creator/**` | Creator |
| `tests/platform/web/deployment/**` | Deploy contract/browser smoke；不实际部署 |
| `tests/quality/**` | `core_coverage` |
| `tests/build/ci_*` | `ci_contract`；不运行 Core |
| `tests/build/web_runtime_deploy_*`、`tests/build/web_runtime_public_deployment_docs_test.py` | `deploy_contract`；不运行 Core |
| `tests/conformance/version_lock_test.py` | `core_ubuntu` + `package` |
| version/module graph/Contract conformance | `core_ubuntu`；version/package 检查增加 `package` |
| `tests/host/**`、`tests/e2e/**` | Core Proof；Apple-specific 增加 macOS |
| `tests/distribution/**` | `package` |
| test registration、taxonomy、公共 helper | 完整 Core |

只修改 CI 契约测试不自动选择 Runtime；若同一 PR 同时修改实际 CI 控制面，则控制面规则优先。

### 8.5 Fixture、Golden 与 lockfile

- `tests/fixtures/audio/**`、Golden WAV/hash：Core audio + Web Runtime Host + Creator；
- Contract fixture：所有消费对应 Contract 的 Core/Web lane；
- Project/E2E fixture：Core Proof；
- `tests/platform/web/package.json`、`package-lock.json`、`playwright.config.mjs`：共享该浏览器工具链的所有 Web lane；
- Creator lockfile：Creator；Portal lockfile：Portal；
- Emscripten、Playwright、compiler 或 sanitizer pin：对应执行面的完整门禁；
- 共享 fixture generator/hash 规则：所有消费者，不仅生成器单测。

## 9. CI 控制面归属

workflow static、actionlint/YAML、runner fallback contract 和 scope/gate contract 都是
`ci_contract` 内部 workload，不是额外 lane。

| 变更 | focused/full 规则 |
| --- | --- |
| Change Scope、PR Gate、`.github/workflows/ci.yml` | full（包含 `ci_contract`） |
| 共享 runner selector、fallback、build acceleration | `ci_contract` + 所有消费者；改变总路由时 full |
| macOS gate action 与 result assertion script | `core_macos` + `ci_contract` |
| 精确的 `architecture-portal.yml`、`architecture-portal-smoke.yml` | `portal` + `ci_contract`；相似未知 workflow 名称 full |
| Deploy workflow | `deploy_contract` + `ci_contract` |
| Nightly workflow | `ci_contract` + 对应 Core stress/sanitizer lane 的单次验证 |
| 仅 `tests/build/ci_*` | `ci_contract`；不运行 Runtime |
| 仅注释/展示名称 | `ci_contract`；不运行 Runtime |

中央分类器、PR Gate、主 workflow、required-check name、runner 选择/fallback 和 manifest schema
永远不能走快速通道。实施 PR 必须显式带 `ci:full`，并在 PR body 列出预期运行/跳过的 lane。

## 10. Job 拓扑与 runner

- Change Scope 位于每个 PR 的关键路径，必须使用 checkout + shell/Python 3.11 标准库完成；
  不运行 `npm install`、`pip install`、CMake configure、browser 或 toolchain setup，也不访问
  runner inventory API；其正常执行 SLO 不超过三十秒；
- 各正式 lane 直接依赖 Change Scope；可信池消费者还依赖 selector，其余尽可能并行；
- 移除 Creator 对 Web Toolchain/Core 的非 artifact 串行依赖；
- selector 只在至少一个消费者 lane 被选择时运行；纯文档 PR 不查询或占用 Linux/macOS runner；
- Core、ASan、Coverage、Web Runtime Host 与 Core Package 继续优先现有 self-hosted Linux pool；
- Web Toolchain 和 Creator 暂时保持当前 GitHub-hosted 路由，但因路径分流减少启动次数；
- macOS 继续优先受信 M1；
- fork PR 不进入可信 self-hosted runner；
- Package 保持 LFS hydration、禁用 ccache，并复用现有 Ubuntu selector；正常可信分支优先避免
  hosted 执行，外部 fork、token/API/池可用性不足时仍使用既有 hosted fallback；
- 本设计不增加 runner、retry 或新的 fallback 机制；Package 会在 fork、token/API 或可信池容量
  fallback 时执行 hosted，但复用的是现有 selector 路由。

缓存统计是诊断证据，不替代语义结果。未来 runner 扩容、Web 专用池或 hosted-to-self-hosted
迁移需要独立设计和现场容量验证。

“selector 在 Change Scope 后按需运行”是本次保守默认。观察周必须单独记录
`Change Scope complete -> selector complete` 的串行开销；若它成为 focused Core/Web 的关键
路径瓶颈，可在不改变分类语义的后续 Task 中让 selector 与 Change Scope 并行，代价是 docs-only
PR 多一次短 hosted 查询。该调优不能提前并入本 Task，也不能占用实际 workload runner。

## 11. PR Gate 合同

`PR Gate` 是唯一长期 required check。它始终读取 event 对应的 exact base/head SHA、manifest
和静态声明的全部 job results，逐项验证 `required_jobs`。

| 条件 | 结果 |
| --- | --- |
| 所有 required job 为 `success` | pass |
| 未要求的 job 为 `skipped` | pass |
| required job 为 `skipped` | fail |
| required job 为 `failure` 或 `cancelled` | fail |
| 未要求的 job 为 `success`、`failure` 或 `cancelled` | fail；说明 scope 与实际拓扑失配 |
| job result 缺失 | fail |
| manifest 缺失、schema 未知或非法 | fail |
| manifest base/head SHA 与当前 event SHA 不同 | fail |
| lane 与 required job 映射矛盾 | fail |

PR workflow 本身始终触发，不使用 workflow 级 `paths` 过滤 required gate。Architecture Portal
的验证逻辑必须暴露为 `workflow_call`，由主 PR workflow 作为同一次 workflow run 中的 job
调用，并被 `PR Gate.needs` 静态引用。禁止通过 Checks API 轮询另一个 workflow，也禁止依赖
跨 run 的同名 check，因为两者都有竞态且不能提供同一 fan-in 合同。Portal 的 deployment
smoke 和 Netlify Preview 继续保持独立事件边界；main push 的 Portal 验证由主 full run 调用。

## 12. 失败、重试与基础设施恢复

- 编译、Proof、测试、sanitizer 和 Coverage 失败是最终语义结果，不自动 retry；
- selector 在开始前选择现有 self-hosted 或既有 hosted fallback；
- macOS self-hosted checkout/setup/通信/30 分钟 job limit 若未发布终态，可运行现有一次 hosted
  fallback；
- macOS 已发布准备、Core Proof 或 sanitizer failure 不触发 fallback；
- 本设计不增加 Linux hosted retry。Linux job timeout 阻断当前 PR，由人工诊断或显式 rerun；
- 新 commit 取消旧 SHA 不视为当前 SHA failure；
- `PR Gate` 不得把 infrastructure absence 解释为测试成功。

## 13. SLO 与硬超时

SLO 只用于衡量与容量决策，不阻断 merge，也不作为测试 assertion。

| Lane | 非阻断执行 SLO | Job 安全上限 |
| --- | ---: | ---: |
| Change Scope | 30 秒 | 3 分钟 |
| PR Gate | 30 秒 | 3 分钟 |
| Docs/static | 2 分钟 | 10 分钟 |
| Portal | 5 分钟 | 15 分钟 |
| Core Ubuntu | 10 分钟 | 30 分钟 |
| ASan/Coverage | 15 分钟 | 35 分钟 |
| Web Toolchain | 15 分钟 | 35 分钟 |
| Web Runtime Host | 15 分钟 | 45 分钟 |
| Creator | 15 分钟 | 35 分钟 |
| macOS primary | 10 分钟 | 保持 30 分钟 |

docs-only Ready PR 的端到端非阻断 SLO 是五分钟，明确包含 Change Scope、job dispatch、
Docs/static 和 PR Gate，不把表内各 job SLO 简单相加当作新的硬锁。

不设置整个 PR 的三十分钟全局硬锁。排队时间单独记录，目标不超过五分钟；超标只进入一周
容量报告。测试自己的 CTest/browser timeout 继续表达行为预算，达到时仍是测试失败。

## 14. 分支保护迁移

required checks 使用双门禁过渡，禁止先删除旧门禁：

1. 功能分支加入新分类器、条件 lane 和 `PR Gate`；
2. 实施 PR 带 `ci:full`，完整运行旧矩阵；
3. 先把 `PR Gate` 加为 required，同时保留 `core (ubuntu-latest)` 和
   `core (macos-latest)`；
4. 验证实施 PR 与 merge 后 `main` full run；
5. 再通过单独授权更新分支保护，移除旧两个 required contexts；
6. 复核 strict branch update 和 conversation resolution 仍启用。

本地 commit、push、PR、merge 和分支保护修改是独立权限。本设计批准不授权远端状态变更。

## 15. 验证策略

### 15.1 分类器契约

自动化矩阵必须覆盖：

- 每个当前 tracked path 都命中显式 ownership 或显式 full rule；新增未知路径仍 fail closed；
- docs-only 不选择 Core/Web Runtime；
- 扩展名、目录和文件级重叠规则按 lane 并集计算；
- Core、Web、Creator、Portal、Deploy 互不误触发；
- 测试继承被测执行面；
- shared fixture 选择所有消费者；
- 删除/重命名使用新旧路径并集；
- 本地 Git diff 覆盖超大 inventory，API fallback 截断或无法证明完整时 full/fail closed；
- `ci:full` 只能升级；
- Draft、Ready、main 模式；
- 主 workflow 不订阅 label event；无关 label 不创建/取消 run，显式 rerun 能读取实时
  `ci:full` 并升级正式门禁；
- 连续 main push 使用 per-SHA、non-cancelling group；
- 未知路径升级 full；
- diff/API/input failure 阻断；
- 分类器、PR Gate、主 workflow 的自修改强制 full。
- changed-file schema、path count/canonical/duplicate 校验与 `draft`/`focused`/`full` lane 一致性；
- focused manifest 从 inventory 重算 Ready ownership，拒绝 lane 降级、遗漏消费者与 full trigger；
- summary 完整列出 rename/copy 双路径、逐 lane 理由并转义不可信 Markdown/control text。

### 15.2 Gate 契约

测试 success、allowed skipped、required skipped、required failure/cancelled、未要求 job 的
unexpected success/failure/cancelled、missing result、invalid manifest、unknown schema、SHA
mismatch 和 lane/job conflict。现有 runner fallback、required check name、build acceleration 和
fixture hydration contract 要迁移到新拓扑，而不是删除。

### 15.3 Workflow 验证

- actionlint/YAML；
- CI contract test；
- Architecture Portal check；
- 实施 PR 的 `ci:full` 完整矩阵；
- merge 后 `main` full run；
- retained scope manifest 与 job summary 人工核对；
- 至少用自动化 fixture 模拟 docs-only、single Web Host、Core test、CI control-plane、rename、
  overlapping README、超大/截断 inventory、unrelated label、连续 main push、unknown path 和
  `ci:full`。

## 16. 可观测性

每个正式 run summary 记录：

- mode、base/head SHA；
- changed paths 与分类理由；
- requested、success、skipped lane；
- `ci:full`、共享路径或未知路径升级原因；
- 各 lane 排队时间、执行时间和最长关键路径；
- SLO 达成情况，但不改变 gate result。

实施后观察一周，再用 focused/full 比例、P50/P95 queue、P50/P95 execution、hosted minutes 和
误分类/人工 `ci:full` 次数评估效果。hosted minutes 必须与变更前“每个 PR 与 main 都启动无条件
矩阵”的可比基线对照，并区分 focused PR 节省、新增 Change Scope/Docs/CI Contract/Gate、
full-main 工作和 Package hosted fallback。focused 节省预计覆盖这些新增工作，但这是待验证假设。
按 PR 更新与 merge 数量归一化后，routine hosted minutes 不得持续高于可比基线；任何持续回退
都要求永久迁移先采用不放宽证据的路由或 job consolidation 修正；无法修正时按 §17 回滚到
all-PR full 的安全配置并重新评估，不能通过
增加预算、retry 或弱化门禁掩盖。runner 扩容只使用该报告作为后续独立设计输入。

观察周还必须把 Web lane 的 bootstrap 与 semantic workload 分开计时：emsdk clone/install、
Emscripten activation、`npm ci`、Playwright browser/system dependency install，以及真正的
configure/build/test/proof。若 bootstrap 仍占 Web Runtime Host 十八至二十八分钟长尾的主要
部分，单独建立“pinned Web toolchain/bootstrap reuse”Task，评估受信 self-hosted 预装或精确
key 的 checkout 外缓存。该 Task 与 runner 扩容分开，不增加 hosted 用量，不放宽 exact
Emscripten/Playwright identity，也不在本 CI 分类实现中夹带缓存语义变更。

## 17. 回滚

- 当前 PR 怀疑漏判时添加 `ci:full`；
- 修复分类器的 PR 自身必须 full；
- `PR Gate` 无法可靠汇总时，回滚必须作为一个逻辑原子、fail-closed 的两阶段事务执行：
  `PR Gate` 保持 required，先合入“所有 PR 强制 full”的回滚配置；确认 docs-only 也实际运行
  并发布旧两个 Core contexts 后，再把 `core (ubuntu-latest)` 和 `core (macos-latest)` 加回
  required；只有旧保护已生效后才允许移除 `PR Gate`；
- 禁止只恢复旧 contexts 而保留 focused skip，因为 GitHub 接受 skipped required check，
  那样不能恢复旧保护强度；
- 分类优化可以退回“所有 PR full”，但不能退回无聚合门禁；
- 回滚走正常 PR，不直接提交 `main`，不绕过失败结果。

## 18. Version Management

Version impact: none.

原因：本设计和未来实现只改变 CI 的选择、编排、汇总与可观测性，不改变 Product Build、
Core Module、Host、Provider、Contract identity 或运行时 artifact。不得为本 Task 分配 Product
Build、生成版本快照、创建 tag 或进行 Channel promotion。

## 19. Documentation Impact

本设计文档 Task 的 Documentation impact: none。

原因：本提交只记录“已批准、尚未实现”的未来策略，不改变 Architecture Portal 当前已实现
事实。提前修改 current 页面会把未落地 CI 描述成现状。

未来实现 Task 的 Documentation impact: required。

Affected portal pages: `/operations/testing-and-proof/`

实现 Task 必须同时更新：

- `docs/quality/core-test-policy.md`；
- `docs/governance/git-workflow.md`；
- Architecture Portal 的 CI/testing current 页面与必要源图；
- PR template 中的 documentation impact 和 CI scope 声明（若实施计划采用该表面）。

## 20. 验收标准

实现完成需同时满足：

1. docs-only Ready PR 的 manifest 不选择任何 Core/Web Runtime lane；
2. docs-only Ready PR 端到端五分钟是非阻断 SLO，Change Scope 零依赖安装且执行 SLO 三十秒；
3. 单一执行面变更只选择所有权矩阵规定的 lane，重叠规则取并集；
4. 测试、fixture、现存顶层路径、CI control-plane、rename、超大 inventory 和 unknown path
   分类契约全部通过；
5. required job 意外 skipped/missing，或未要求 job 意外执行，必然让 `PR Gate` 失败；
6. `ci:full` 和每个 `main` SHA 必然选择完整 PR 矩阵，连续 main push 不互相取消；
7. 无关标签不创建、取消或替代正式 run；`ci:full` + 显式 rerun 能在同一 SHA 升级 full；
8. Draft 不产生可替代 Ready 正式门禁的证据；
9. semantic failure 不被 retry/fallback 隐藏；
10. macOS 既有 infrastructure fallback 语义保持；
11. Portal 是同一次主 workflow run 内被 `PR Gate.needs` 引用的 job；
12. 迁移期间旧 required checks 在新门禁验证完成前不移除；
13. 实施 PR full、merge 后 main full、Portal 和全部 CI contract 通过；
14. SLO 超标只记录，不因软目标使正确 job 失败；
15. 没有 runner、release、deployment、Product Build 或 Channel 外部状态变更。
