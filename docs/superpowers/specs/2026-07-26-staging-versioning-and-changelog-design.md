# LMDJ staging 版本号、Tag 与 Changelog 设计

日期：2026-07-26

状态：已实现

落点：扩展现有 GitHub Actions staging 部署链路，在成功部署后生成统一产品版本、Git Tag、GitHub Release 与 Markdown Changelog 附件。

实现：

- `scripts/release/release_version.py`：版本计算、回滚保护与 Changelog 渲染；
- `scripts/release/publish-staging-release.sh`：Tag、Release 与附件的幂等发布；
- `.github/workflows/deploy-server.yml`：部署后 revision gate 与发布编排；
- `scripts/release/tests/`、`scripts/deploy/tests/test-deploy-workflow.sh`：自动化契约测试。

## 目标

每次 staging 成功部署一个新的 `main` SHA 后，自动生成一个不可变的 LMDJ 产品版本：

```text
v0.2.0
v0.2.1
v0.3.0
```

每个版本同时具备：

- 指向实际部署 SHA 的 annotated Git Tag；
- 对应的 GitHub Release；
- 与 Release 正文完全相同的 `CHANGELOG-vX.Y.Z.md` 下载附件；
- 可追溯的部署 SHA、部署时间和 GitHub Actions 运行链接。

Tag 只在 staging 激活成功且服务器确认运行目标 SHA 后创建。失败的构建、上传或激活不占用版本号。

## 版本边界

本方案只管理 LMDJ 的统一产品版本，不将 Web、API、Audio Worker 或共享包拆成独立的部署版本。

当前 Web、API、Audio Worker 从同一个 Git SHA 构建并一起部署，且共同依赖 `lmdj.patch.v1` 契约；staging 回滚也以整套 release 的 SHA 为单位。因此一次 staging 部署只对应一个产品版本。

各 Python 包和 `apps/web/package.json` 中现有的 `0.1.0` 仍是内部包版本。本方案不自动修改它们。只有某个包将来需要独立发布、独立兼容或被外部项目消费时，才单独设计包版本生命周期。

## 方案选择

采用 GitHub 原生 Tag / Release 能力，加仓库内轻量版本和 Changelog 生成器。

不采用 `semantic-release`：

- 它偏向 npm 包发布和合并后立即发版；
- staging 是否真实激活不是它的天然发布门槛；
- 当前混合 Python、Node、Docker 仓库不需要它的插件体系。

不采用 `release-please`：

- 它通过 Release PR 在部署前确定版本；
- 本方案要求 staging 部署成功后才产生版本；
- 部署后再维护版本 PR 会让 Tag、部署 SHA 和 Changelog 提交形成循环依赖。

仓库根目录不维护累计 `CHANGELOG.md`。部署 Workflow 不绕过 `main` 的 PR-only 规则写回仓库；每个 Release 上传一份与该版本严格对应的 Markdown 附件。

## 版本号规则

### 格式

产品版本使用无预发布后缀的 SemVer Tag：

```text
v<major>.<minor>.<patch>
```

Tag 必须严格匹配该格式；带 `staging`、日期、构建元数据或其他后缀的 Tag 不参与版本计算。

### 初始版本

仓库不存在合规产品版本 Tag 时，第一个成功部署的新 SHA 固定生成：

```text
v0.2.0
```

首版 Changelog 覆盖目标 SHA 可达的完整仓库历史。启用版本管理后，后续版本只覆盖上一个产品 Tag 到本次目标 SHA 的提交。

### 自动递增

版本生成器扫描上一个产品 Tag（不含）到目标 SHA（含）之间的全部提交，并按最高影响等级递增一次：

| 提交信号 | 版本变化 | 示例 |
|---|---|---|
| 提交正文包含 `BREAKING CHANGE:`，或 Conventional Commit 类型后带 `!` | major | `v0.3.2 → v1.0.0` |
| 至少一个 `feat:`，且不存在 breaking 信号 | minor | `v0.2.3 → v0.3.0` |
| 其他非空提交范围 | patch | `v0.2.3 → v0.2.4` |

`fix:`、`perf:`、`docs:`、`refactor:`、`test:`、`build:`、`ci:`、`chore:` 和不符合 Conventional Commits 的提交都落入 patch。非规范提交不会阻止部署，但会进入 Changelog 的 `Other` 分类。

“上一个产品 Tag”是仓库中 SemVer 数值最高的合规产品 Tag。若它不是目标 SHA 的祖先，流程失败，不跨分叉历史生成版本。

## 部署与发布数据流

现有 `deploy-server.yml` 保持“只部署 `main` 可达、已有成功 CI 的 SHA”这一入口约束。发布步骤追加在 staging 激活之后：

```text
解析并验证目标 main SHA
  → 构建 Web 与服务器镜像
  → 打包并上传 release
  → 激活 staging
  → 读取服务器 DEPLOYED_REVISION 并核对目标 SHA
  → 解析目标 SHA 上的产品版本 Tag
      → 已有一个 Tag：进入幂等补齐
      → 没有 Tag：计算下一个版本并创建 annotated Tag
      → 已有多个 Tag：失败，要求人工处理
  → 生成 GitHub Release
  → 从同一正文上传 CHANGELOG-vX.Y.Z.md
```

服务器验证使用现有 SSH 连接读取 `$DEPLOY_PATH/DEPLOYED_REVISION`。只有其内容与目标完整 SHA 完全一致时，才允许进入 Tag 步骤。

Workflow 的并发组继续使用 `deploy-staging` 且不取消进行中的部署，从而避免两个 staging 发布同时计算同一个下一个版本。发布 Job 需要：

- `actions: read`：验证目标 SHA 的 CI；
- `contents: write`：推送 Tag、创建 Release 和上传附件。

权限只授予执行部署的 Workflow，不扩大其他 CI Job 的权限。

## Tag 与幂等性

Tag 使用 annotated Tag，Tag message 记录 staging 部署事实和 GitHub Actions Run URL。Tag 永久指向实际部署 SHA，不移动、不覆盖、不强推。

目标 SHA 的处理规则：

1. 没有产品版本 Tag：正常计算并创建新版本。
2. 恰好一个产品版本 Tag：复用该版本，不再次递增。
3. 多个产品版本 Tag：停止，避免任意选择版本。

发布步骤允许安全重跑：

- Tag 创建前失败：重跑部署后重新计算并创建。
- Tag 已创建但 Release 创建失败：重跑复用 Tag 并补建 Release。
- Release 已存在但 Markdown 附件缺失：从已存在的 Release 正文生成附件并补传。
- Tag、Release 和附件都已存在：成功退出，不覆盖既有内容。

当 Release 已存在时，它是正文的事实来源；补附件时不重新生成可能发生漂移的内容。

## 回滚规则

回滚继续通过 `Deploy server` 的 `commit_sha` 输入选择以前的完整 `main` SHA。

- 目标 SHA 已有产品版本 Tag：部署并复用该版本，不创建新 Tag 或 Release。
- 目标 SHA 没有产品版本 Tag，且仓库已经启用版本管理：发布阶段失败，不给旧代码倒序分配新版本。
- 仓库尚无任何产品版本 Tag：只允许当前 `origin/main` 作为初始 `v0.2.0` 目标；显式选择更旧 SHA 时停止。

staging 激活可能已在发布阶段失败前完成，因此 Workflow 的错误输出必须明确区分“部署已完成，发布元数据失败”和“部署失败”。操作者可再次运行同一 SHA 补齐发布元数据。

## Changelog 内容

GitHub Release 正文与 `CHANGELOG-vX.Y.Z.md` 使用同一份生成文件，不分别生成。

正文结构：

```markdown
# v0.3.0

- Environment: staging
- Commit: <full SHA>
- Deployed at: <UTC ISO 8601 timestamp>
- Workflow: <GitHub Actions Run URL>

## Features
## Fixes
## Performance
## Documentation
## Maintenance
## Other
```

只输出有内容的分类。分类规则：

| Conventional Commit 类型 | Changelog 分类 |
|---|---|
| `feat` | Features |
| `fix` | Fixes |
| `perf` | Performance |
| `docs` | Documentation |
| `refactor`、`test`、`build`、`ci`、`chore`、`style` | Maintenance |
| 无法识别的提交 | Other |

条目保留 scope 和简短描述，链接到对应 commit。若 squash commit 标题以 `(#<number>)` 结尾，同时链接对应 Pull Request。正文中的 breaking 变更在所属条目前增加显著标记。

Changelog 不读取或修改各包的内部版本字段。

## 组件边界

实现拆成三个可独立理解和验证的部分：

1. **版本与正文生成器**
   - 输入：Git 仓库、目标 SHA、仓库 URL、部署时间和 Workflow URL；
   - 输出：版本 Tag、上一个 Tag、发布 Markdown；
   - 负责 SemVer 解析、提交扫描、影响等级选择和分类；
   - 不访问 GitHub，不创建 Tag。

2. **幂等发布控制脚本**
   - 输入：目标 SHA 和生成器产物；
   - 负责读取远端 Tag、创建 annotated Tag、创建或检查 GitHub Release、上传附件；
   - 使用 `git` 与已安装的 GitHub CLI；
   - 禁止覆盖或移动既有 Tag、Release 和附件。

3. **GitHub Actions 编排**
   - 保留现有构建、上传和激活顺序；
   - 增加服务器 revision 验证；
   - 在 revision 通过后调用生成器和发布脚本；
   - 只负责传递 GitHub 上下文和 Secret，不承载版本算法。

## 错误处理

以下情况必须令发布步骤失败：

- 服务器 `DEPLOYED_REVISION` 不存在或不等于目标 SHA；
- 产品 Tag 格式非法但被配置为版本来源；
- 最新产品 Tag 不在目标 SHA 的祖先链；
- 目标 SHA 同时存在多个产品版本 Tag；
- 新计算出的 Tag 已在其他 SHA 上存在；
- Git Tag、GitHub Release 或附件与预期目标不一致；
- GitHub API 或 Tag push 失败。

错误信息必须包含目标 SHA、已完成阶段和可安全重跑的建议。脚本不得删除远端 Tag、覆盖 Release 正文或使用 force push 自动“修复”冲突。

## 测试与验收

版本生成器使用临时 Git 仓库做脚本级测试，至少覆盖：

1. 无历史版本时生成 `v0.2.0`；
2. `fix`、文档、维护和非规范提交递增 patch；
3. `feat` 递增 minor；
4. `BREAKING CHANGE:` 和 `type!:` 递增 major；
5. 混合提交选择最高影响等级；
6. Changelog 分类、commit/PR 链接和 breaking 标记；
7. 上一个 Tag 不在目标祖先链时拒绝生成。

发布控制脚本使用假的 `git` / `gh` 命令或隔离远端测试，至少覆盖：

1. 新 SHA 创建 Tag、Release 和附件；
2. 同一 SHA 已有一个 Tag 时不递增；
3. 同一 SHA 多 Tag 时失败；
4. Tag 已有、Release 缺失时补建；
5. Release 已有、附件缺失时从 Release 正文补传；
6. 全部存在时幂等成功；
7. 旧的无 Tag SHA 被当作回滚目标时拒绝创建版本。

Workflow 静态测试至少断言：

- revision 验证在发布步骤之前；
- `contents: write` 和 `actions: read` 权限明确；
- 发布步骤只位于成功激活路径；
- 不存在 force push、Tag 覆盖或直接提交 `main`；
- 现有 current-main activation controller 与离线镜像打包约束仍保留。

最终验证：

```bash
bash scripts/release/tests/test-release-versioning.sh
bash scripts/deploy/tests/test-deploy-workflow.sh
bash scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-activate-release.sh
```

首次上线后的真实验收：

1. 合并实现 PR 并等待目标 SHA 的 CI 成功；
2. 运行 `Deploy server` 部署当前 `main`；
3. 确认服务器 `DEPLOYED_REVISION`、`v0.2.0` Tag 和 Release 指向同一 SHA；
4. 下载 `CHANGELOG-v0.2.0.md`，确认与 Release 正文一致；
5. 对同一 SHA 重跑 Workflow，确认不产生新版本；
6. 部署下一条 `fix:` SHA，确认生成 `v0.2.1`；
7. 回滚 `v0.2.0` 的 SHA，确认复用版本且不创建新 Tag。

## 非目标

- 不实现 production 环境或 production promotion；
- 不自动更新 Python/npm 包版本；
- 不生成或提交仓库根目录 `CHANGELOG.md`；
- 不自动 push 开发分支、创建实现 PR、合并或部署；
- 不改变 `main` 必须通过 PR 和 CI 合入的规则；
- 不允许删除、移动或覆盖已发布 Tag。
