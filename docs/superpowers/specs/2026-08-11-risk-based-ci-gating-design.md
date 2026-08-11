# Risk-Based CI Gating Design

日期：2026-08-11

状态：规格已批准，尚未实现

## 1. 结论

LMDJ 将 Pull Request CI 从“每次修改都运行完整 Core/Web 矩阵”改为集中式风险分类：

1. 每个 PR 先由唯一的 `Change Scope` 分类器读取完整 diff、PR 状态和显式标签；
2. Draft PR 只运行轻量反馈，Ready PR 只运行本次实际影响的正式 lane；
3. `ci:full`、共享控制面、高风险路径、未知路径和 `main` push 强制完整 PR 矩阵；
4. 唯一稳定 required check `PR Gate` 按版本化 scope manifest 校验本次应运行的所有 job；
5. `main` push 与 nightly 继续保留完整验证和压力采样；
6. CI 时限目标是非阻断 SLO，只有独立的 job 安全上限和测试行为 timeout 会失败；
7. 本设计不增加 runner，也不增加 GitHub-hosted 日常用量。runner 扩容在独立设计中讨论。

目标是在不把不确定性静默放行的前提下，将纯文档 Ready PR 的反馈目标缩短到三分钟，
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
- 不增加日常 GitHub-hosted 用量；路径分流应减少现有 hosted job 的启动次数。
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

所有正式 lane 只依赖 `Change Scope`。除了真实 artifact 或环境传递关系，lane 之间不得用
`needs` 制造顺序；完整结果统一由 `PR Gate` fan-in。macOS primary/fallback/adjudicator 内部
依赖继续保留，因为它们共同发布一个平台结果。

## 6. Change Scope

### 6.1 输入

分类器使用：

- PR base SHA 和 head SHA；
- base/head 之间含状态的完整 changed-file inventory；
- PR 是否为 Draft；
- 当前标签中是否存在 `ci:full`；
- event 是 Pull Request、`main` push 还是显式 dispatch；
- 版本化路径归属配置。

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
    {"status": "modified", "path": "apps/web-runtime-host/tools/example.py"}
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
    "ci_contract": false
  },
  "required_jobs": ["docs-static", "portal", "web-runtime-host"]
}
```

schema、mode、lane 和 job name 都使用闭合 allowlist。未知字段、未知枚举、重复或冲突
job、SHA 不匹配和非 canonical path 必须拒绝。manifest 同时写入 job summary 并上传为
artifact；summary 必须解释每个被选择或升级 lane 的具体理由。

### 6.3 模式

分类器只有三种模式：

- `draft`：轻量反馈，不建立正式 merge 证据；
- `focused`：Ready PR 运行实际影响的正式 lane；
- `full`：运行现有完整 PR 矩阵，但不包含 nightly 重复采样或生产部署。

以下情况强制 `full`：

- PR 包含 `ci:full`；
- 修改 Change Scope、PR Gate、scope schema 或主 PR workflow；
- 修改 required-check 汇总、共享 runner 路由/fallback 或共享构建控制面；
- 修改根 CMake、公共 test registration/taxonomy、共享 fixture、Product Assembly 或 Contract；
- 同一 PR 横跨三个或更多执行面；
- 新增未知顶层路径或出现不能安全归属的删除/重命名；
- `main` push；
- 显式 full dispatch。

未知路径是可成功分类的 `full`，不是静默忽略。diff 获取失败、manifest 无法生成或输入不可信
则分类 job 失败并阻断，不猜测结果。

## 7. PR 生命周期

主 workflow 明确监听 `opened`、`synchronize`、`reopened`、`ready_for_review`、
`converted_to_draft`、`labeled` 和 `unlabeled`。

| 状态或事件 | 行为 |
| --- | --- |
| Draft 新建/更新 | 运行 draft 反馈 |
| 转为 Ready | 同一 head SHA 重新分类并运行正式 focused/full 门禁 |
| Ready 推入新 commit | 取消旧 SHA 未完成运行，按新 SHA 重跑 |
| 添加 `ci:full` | 重新触发并升级 full |
| 删除 `ci:full` | 按当前完整 diff 重新分类；summary 必须记录降级原因 |
| 转回 Draft | 取消尚未完成的重型运行并回到 draft |
| `main` push | 强制 full |

同一 PR 使用稳定 concurrency group，不同 PR 和 `main` 使用不同 group。被后续 commit 取消的
旧 run 不构成当前 SHA 的语义失败；当前 SHA 的正式 `PR Gate` 必须完整发布。

Draft 只运行预计五分钟以内的检查：Change Scope、自身契约、`git diff --check`、workflow
静态校验、文档影响快速检查，以及不要求完整 CMake build、浏览器或 Web toolchain 的相关
Python/Node 单测。Draft 不安装 Emscripten/Playwright，不运行 C++ 构建、Core Proof、
sanitizer、Coverage、macOS 或完整 Portal build。Draft 不能替代转为 Ready 后的新正式结果。

## 8. 路径归属

### 8.1 产品与源码

| 路径 | focused 正式门禁 |
| --- | --- |
| 普通 Markdown、`docs/superpowers/**`、研究与计划 | Docs static |
| `docs/governance/**` | Docs static + Portal |
| `apps/architecture-portal/**` | Portal |
| `apps/creator-web/**` | Creator |
| `apps/web-runtime-host/**` | Web Runtime Host |
| `apps/web-runtime-lab/**` | Web Runtime Lab |
| `apps/chameleon-lab/**` | Chameleon Lab 自身测试 |
| `apps/core-cli/**`、`apps/core-mcp/**` | Core Ubuntu Proof；跨平台 Host 变更增加 macOS |
| `apps/native-test-host/**` | Core Ubuntu + macOS native |
| `packages/web-runtime-platform/web/**`、仅 MJS 的 test | Web Toolchain + Web Runtime Host |
| `packages/web-runtime-platform/CMakeLists.txt`、`module.json`、C++ source/test | 完整 Core + Web Toolchain + Web Runtime Host |
| 其他 `packages/**` | 完整 Core PR 矩阵 |
| `providers/**` | Core Proof + ASan + Coverage；Provider/Assembly 路径增加 E2E |
| `contracts/**` | full |
| `products/lmdj/**` | full + Portal |
| `workers/**` | 对应 Provider/Host；不能分类时 full |
| 根 CMake、共享 CMake、版本/Assembly Lock | full |
| 未知或新增顶层路径 | full |

Architecture Portal 是否运行还要保留现有文档影响路径集合：`AGENTS.md`、`CLAUDE.md`、PR
模板、相关 workflow、`apps/**`、`packages/**`、`providers/**`、`workers/**`、
`contracts/**`、`products/lmdj/**`、`docs/governance/**` 和门户脚本。
Portal 是表中门禁的附加 lane：命中该集合的 Creator、Web Host、Core 或其他实现变更仍要
运行 Portal，不因主要执行面已经选中而省略。

### 8.2 脚本

| 路径 | focused 正式门禁 |
| --- | --- |
| `scripts/core.sh`、`scripts/core-coverage.sh`、Core dependency/build 脚本 | 完整 Core |
| `scripts/web-toolchain-conformance.sh` | Web Toolchain |
| `scripts/web-runtime-host.sh` | Web Runtime Host |
| `scripts/creator-web.sh` | Creator |
| `scripts/web-runtime-lab.sh` | Web Runtime Lab |
| `scripts/architecture-portal.sh` | Portal |
| `scripts/web-runtime-deploy.sh` | Deploy contract；不部署、不运行 Core |
| `scripts/version.py`、`scripts/package-core.py` | Core Proof + package/version contract |
| 新增共享脚本或消费者不明 | full |

### 8.3 测试

测试代码继承被测对象的 lane：

| 路径 | focused 正式门禁 |
| --- | --- |
| `tests/core/**` | Core Ubuntu + ASan + Coverage |
| `tests/core/audio/**`、concurrency/stress | 上述门禁 + macOS/native stress |
| `tests/platform/audio/**` | macOS Core/native sanitizer |
| `tests/platform/web/toolchain/**` | Web Toolchain |
| `tests/platform/web/host/**` | Web Runtime Host |
| `tests/platform/web/creator/**` | Creator |
| `tests/platform/web/deployment/**` | Deploy contract/browser smoke；不实际部署 |
| `tests/quality/**` | Coverage 实现及自身测试 |
| `tests/build/ci_*` | CI contract + workflow static；不运行 Core |
| `tests/build/web_runtime_deploy_*` | Deploy contract；不运行 Core |
| version/module graph/Contract conformance | Core/Contract lane |
| `tests/host/**`、`tests/e2e/**` | Core Proof；Apple-specific 增加 macOS |
| `tests/distribution/**` | Package lane |
| test registration、taxonomy、公共 helper | 完整 Core |

只修改 CI 契约测试不自动选择 Runtime；若同一 PR 同时修改实际 CI 控制面，则控制面规则优先。

### 8.4 Fixture、Golden 与 lockfile

- `tests/fixtures/audio/**`、Golden WAV/hash：Core audio + Web Runtime Host + Creator；
- Contract fixture：所有消费对应 Contract 的 Core/Web lane；
- Project/E2E fixture：Core Proof；
- `tests/platform/web/package-lock.json`：共享该浏览器工具链的所有 Web lane；
- Creator lockfile：Creator；Portal lockfile：Portal；
- Emscripten、Playwright、compiler 或 sanitizer pin：对应执行面的完整门禁；
- 共享 fixture generator/hash 规则：所有消费者，不仅生成器单测。

## 9. CI 控制面归属

| 变更 | focused/full 规则 |
| --- | --- |
| Change Scope、PR Gate、`.github/workflows/ci.yml` | full + CI contract |
| 共享 runner selector、fallback、build acceleration | 所有消费者；改变总路由时 full |
| macOS gate action | macOS Core + native sanitizer + fallback contract |
| Portal workflow | Portal + workflow static |
| Deploy workflow | Deploy contract + workflow static |
| Nightly workflow | 对应 stress/sanitizer 单次验证 + workflow static |
| 仅 `tests/build/ci_*` | CI contract；不运行 Runtime |
| 仅注释/展示名称 | workflow static + CI contract；不运行 Runtime |

中央分类器、PR Gate、主 workflow、required-check name、runner 选择/fallback 和 manifest schema
永远不能走快速通道。实施 PR 必须显式带 `ci:full`，并在 PR body 列出预期运行/跳过的 lane。

## 10. Job 拓扑与 runner

- 各正式 lane 只依赖 Change Scope，并尽可能并行；
- 移除 Creator 对 Web Toolchain/Core 的非 artifact 串行依赖；
- selector 只在至少一个消费者 lane 被选择时运行；纯文档 PR 不查询或占用 Linux/macOS runner；
- Core、ASan、Coverage、Web Runtime Host 继续优先现有 self-hosted Linux pool；
- Web Toolchain 和 Creator 暂时保持当前 GitHub-hosted 路由，但因路径分流减少启动次数；
- macOS 继续优先受信 M1；
- fork PR 不进入可信 self-hosted runner；
- 本设计不增加 runner 或 hosted fallback。

缓存统计是诊断证据，不替代语义结果。未来 runner 扩容、Web 专用池或 hosted-to-self-hosted
迁移需要独立设计和现场容量验证。

## 11. PR Gate 合同

`PR Gate` 是唯一长期 required check。它始终读取 current head SHA 对应的 manifest 和静态
声明的全部 job results，逐项验证 `required_jobs`。

| 条件 | 结果 |
| --- | --- |
| 所有 required job 为 `success` | pass |
| 未要求的 job 为 `skipped` | pass |
| required job 为 `skipped` | fail |
| required job 为 `failure` 或 `cancelled` | fail |
| job result 缺失 | fail |
| manifest 缺失、schema 未知或非法 | fail |
| manifest head SHA 与当前 SHA 不同 | fail |
| lane 与 required job 映射矛盾 | fail |

PR workflow 本身始终触发，不使用 workflow 级 `paths` 过滤 required gate。Architecture Portal
的 PR job 通过可复用 workflow 或等价的同一 fan-in 方式接入 `PR Gate`；Portal 的 main push、
deployment smoke 和 Netlify Preview 可保留独立事件边界。

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

| Lane | 非阻断 SLO | Job 安全上限 |
| --- | ---: | ---: |
| Change Scope / PR Gate | 1 分钟 | 5 分钟 |
| Docs/static | 3 分钟 | 10 分钟 |
| Portal | 5 分钟 | 15 分钟 |
| Core Ubuntu | 10 分钟 | 30 分钟 |
| ASan/Coverage | 15 分钟 | 35 分钟 |
| Web Toolchain | 15 分钟 | 35 分钟 |
| Web Runtime Host | 15 分钟 | 45 分钟 |
| Creator | 15 分钟 | 35 分钟 |
| macOS primary | 10 分钟 | 保持 30 分钟 |

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

- 每个已知顶层路径有归属；
- docs-only 不选择 Core/Web Runtime；
- Core、Web、Creator、Portal、Deploy 互不误触发；
- 测试继承被测执行面；
- shared fixture 选择所有消费者；
- 删除/重命名使用新旧路径并集；
- `ci:full` 只能升级；
- Draft、Ready、main 模式；
- 未知路径升级 full；
- diff/API/input failure 阻断；
- 分类器、PR Gate、主 workflow 的自修改强制 full。

### 15.2 Gate 契约

测试 success、allowed skipped、required skipped、failure、cancelled、missing result、invalid
manifest、unknown schema、SHA mismatch 和 lane/job conflict。现有 runner fallback、required check
name、build acceleration 和 fixture hydration contract 要迁移到新拓扑，而不是删除。

### 15.3 Workflow 验证

- actionlint/YAML；
- CI contract test；
- Architecture Portal check；
- 实施 PR 的 `ci:full` 完整矩阵；
- merge 后 `main` full run；
- retained scope manifest 与 job summary 人工核对；
- 至少用自动化 fixture 模拟 docs-only、single Web Host、Core test、CI control-plane、rename、
  unknown path 和 `ci:full` 七类 diff。

## 16. 可观测性

每个正式 run summary 记录：

- mode、base/head SHA；
- changed paths 与分类理由；
- requested、success、skipped lane；
- `ci:full`、共享路径或未知路径升级原因；
- 各 lane 排队时间、执行时间和最长关键路径；
- SLO 达成情况，但不改变 gate result。

实施后观察一周，再用 focused/full 比例、P50/P95 queue、P50/P95 execution、hosted minutes 和
误分类/人工 `ci:full` 次数评估效果。runner 扩容只使用该报告作为后续设计输入。

## 17. 回滚

- 当前 PR 怀疑漏判时添加 `ci:full`；
- 修复分类器的 PR 自身必须 full；
- `PR Gate` 无法可靠汇总时，先把旧两个 Core contexts 恢复为 required；
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
2. 单一执行面变更只选择所有权矩阵规定的 lane；
3. 测试、fixture、CI control-plane、rename 和 unknown path 分类契约全部通过；
4. required job 意外 skipped/missing 必然让 `PR Gate` 失败；
5. `ci:full` 和 `main` 必然选择完整 PR 矩阵；
6. Draft 不产生可替代 Ready 正式门禁的证据；
7. semantic failure 不被 retry/fallback 隐藏；
8. macOS 既有 infrastructure fallback 语义保持；
9. 迁移期间旧 required checks 在新门禁验证完成前不移除；
10. 实施 PR full、merge 后 main full、Portal 和全部 CI contract 通过；
11. SLO 超标只记录，不因软目标使正确 job 失败；
12. 没有 runner、release、deployment、Product Build 或 Channel 外部状态变更。
