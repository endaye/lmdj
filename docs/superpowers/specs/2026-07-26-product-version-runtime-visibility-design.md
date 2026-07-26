# LMDJ 产品版本运行时可见性设计

日期：2026-07-26

状态：待实现

关联设计：`2026-07-26-staging-versioning-and-changelog-design.md`

落点：让同一次 LMDJ Web、API、Audio Worker staging 部署在运行时暴露同一个产品 SemVer 和 Git revision，并保证它们与最终 Git Tag 指向同一提交。

## 目标

已落地的 staging 发布链路会在成功部署后创建统一产品版本，例如：

```text
v0.2.0
```

本设计补齐运行中产品对该版本的可见性：

- Web UI 只显示产品 SemVer，例如 `v0.2.0`；
- 浏览器 console 启动时打印一次完整构建身份，例如：

  ```text
  [LMDJ] v0.2.0 · afa06994
  ```

- API `/health` 同时返回产品版本和完整 Git revision；
- 同一次 staging 构建中的 Web 与 API 使用完全相同的版本和 revision；
- 运行时产品版本、Git Tag 和服务器 `DEPLOYED_REVISION` 最终指向同一个目标 SHA。

## 版本模型

运行时身份由两个字段组成：

| 字段 | 示例 | 含义 |
|---|---|---|
| Product version | `v0.2.0` | 对用户和产品发布可见的统一 SemVer |
| Build revision | `afa06994...` | 构建来源的完整 40 位 Git SHA |

产品版本和构建 revision 是两个不同维度：

- 产品版本只在 staging 成功部署新的 `main` SHA 时按现有规则递增；
- 每个 commit 天然拥有不同的 Git SHA，不再额外递增 SemVer；
- Web console 可以将两者组合成可读的完整构建身份；
- API 保留完整 SHA，便于自动诊断和精确核对；
- UI 不显示 SHA，避免将工程信息变成面向用户的视觉噪音。

因此不采用“每个 commit 都把 patch 加一”的做法。开发提交量与产品发布节奏并不相同；若每个 commit 都修改版本文件，还会产生无意义提交、合并冲突和版本漂移。Git SHA 已经提供了逐 commit 唯一性。

## 统一产品版本边界

Web、API 和 Audio Worker 继续使用一个 LMDJ 产品版本，而不是分别拥有前端版本和后端版本。

原因与现有 staging 设计一致：

- 三者从同一个 Git SHA 构建并整体部署；
- staging 激活和回滚以整套 release 为单位；
- Web、API、Worker 共同受 `lmdj.patch.v1` 契约约束；
- 任一组件变化都会形成新的整体产品构建。

`apps/web/package.json` 和各 Python `pyproject.toml` 中的 `0.1.0` 仍是内部包版本，不作为页面或 `/health` 的产品版本来源，也不由部署 Workflow 自动修改。

## 运行时契约

### Web UI

当前页面角落的版本组件保留，但数据源从 `apps/web/package.json` 改为构建期注入的产品版本。

staging 示例：

```text
v0.2.0
```

本地开发示例：

```text
dev
```

UI 只读取产品版本，不读取或拼接 revision。

### 浏览器 console

Web 入口在每次页面启动时打印一次：

```text
[LMDJ] <product-version> · <short-revision>
```

规则：

- staging：`[LMDJ] v0.2.0 · afa06994`；
- 本地开发：`[LMDJ] dev · afa06994`；
- short revision 固定取完整 SHA 的前 8 位；
- 日志只在应用入口打印一次，不随 React 重渲染重复输出；
- UI 与 console 必须通过同一个前端版本模块读取数据，避免两个来源漂移。

前端新增一个聚焦的版本模块，拥有：

- 产品版本；
- 完整 build revision；
- short revision；
- console 完整身份文本；
- 单次启动日志函数。

### API `/health`

`GET /health` 扩展为：

```json
{
  "ok": true,
  "version": "v0.2.0",
  "revision": "afa06994..."
}
```

其中 `revision` 必须是完整 40 位目标 SHA。部署验证仍保留服务器文件 `DEPLOYED_REVISION` 作为激活控制器的事实来源；`/health` 的字段用于运行时观察和诊断，不替代服务器部署边界。

API 新增一个聚焦的版本模块，从环境变量读取并规范化版本身份，供 app factory 和测试复用。

## 注入变量

staging 构建使用：

| 消费方 | 产品版本 | Build revision |
|---|---|---|
| Vite | `VITE_PRODUCT_VERSION` | `VITE_BUILD_REVISION` |
| API container | `LMDJ_PRODUCT_VERSION` | `LMDJ_BUILD_REVISION` |

约束：

- staging 的产品版本必须严格匹配 `v<major>.<minor>.<patch>`；
- staging revision 必须是目标完整 SHA；
- Vite 变量在 Web 构建时固化；
- API 变量通过 Docker build argument 写入镜像环境；
- 两组变量必须来自 Workflow 的同一组输出，禁止分别计算。

## staging 构建与发布数据流

现有 Workflow 是部署成功后才计算版本。为了让构建产物携带最终 Tag，版本必须在构建前先完成只读规划，但 Tag 仍只能在部署成功后创建。

```text
解析并验证目标 main SHA
  → fetch 产品 Tags
  → 只读规划目标产品版本
  → 用同一版本和 SHA 构建 Web 与 API 镜像
  → 打包、上传并激活 staging
  → 验证服务器 DEPLOYED_REVISION
  → 重新读取 Tag 历史并核对规划版本
  → 用真实部署时间生成 Release/Changelog 正文
  → 创建或补齐相同版本的 Tag、GitHub Release 和 Markdown 附件
```

### 构建前规划

`release_version.py` 扩展为两个明确阶段：

1. **Plan**
   - 输入：仓库和目标 SHA；
   - 输出：`tag`、`previous_tag`、`existing`；
   - 不要求部署时间、GitHub 仓库名或 Workflow URL；
   - 不生成 Release 正文；
   - 不创建 Tag 或修改远端状态。

2. **Render**
   - 输入：仓库、目标 SHA、构建前规划的 expected tag、真实部署时间、仓库名和 Workflow URL；
   - 重新执行版本规划；
   - 只有重新计算的 Tag 与 expected tag 完全一致时才生成正文；
   - 输出 `CHANGELOG-vX.Y.Z.md` 和发布步骤所需字段。

这样不需要在构建前伪造部署时间，也不会让 Changelog 将构建时间错误记录为 staging 激活时间。

### Web 构建

`Build web` 从 Plan 输出读取：

```text
VITE_PRODUCT_VERSION=<planned tag>
VITE_BUILD_REVISION=<target full SHA>
```

`apps/web/package.json` 不参与产品版本计算。

### API 镜像构建

`docker build` 接收：

```text
LMDJ_PRODUCT_VERSION=<planned tag>
LMDJ_BUILD_REVISION=<target full SHA>
```

`Dockerfile` 通过对应 `ARG` 和 `ENV` 将两个值固化在镜像内。Compose 不需要在 staging 激活时再次计算或覆盖它们。

## 竞态与失败策略

Workflow 已使用：

```text
concurrency.group = deploy-staging
cancel-in-progress = false
```

这会串行化仓库内的 staging 部署，但仍需要防御人工 Tag 或其他发布流程在构建期间改变 Tag 历史。

部署后 Render 阶段必须重新 fetch 产品 Tags 并核对 expected tag：

- 重新计算结果等于构建前规划：继续发布；
- 目标 SHA 已被幂等地创建同一个 Tag：继续补齐 Release/附件；
- Tag 历史变化导致应生成另一个版本：停止发布，不创建错误 Tag；
- planned tag 已指向其他 SHA：停止发布，不移动或覆盖 Tag。

后一类异常意味着 staging 已经运行一个携带 planned version、但无法安全获得该 Tag 的构建。Workflow 必须明确报告“部署成功，但版本发布因 Tag 历史竞态失败”。修复 Tag 历史后，应重新部署目标 SHA，让构建前规划和最终发布重新形成闭环；不能只绕过核对补写元数据。

产品 Tag 应只由此 staging Workflow 创建。人工创建产品格式 Tag 会被视为需要处理的异常状态。

## 本地开发

`scripts/dev.sh dev` 为 API 和 Web 计算一次共同的本地身份：

```text
product version = dev
build revision = git rev-parse HEAD
```

然后分别注入：

```text
LMDJ_PRODUCT_VERSION=dev
LMDJ_BUILD_REVISION=<full SHA>
VITE_PRODUCT_VERSION=dev
VITE_BUILD_REVISION=<full SHA>
```

这保证本地 Web console 与 API `/health` 仍能互相核对。

若代码不在可解析 Git revision 的环境中运行，测试和独立启动使用确定性回退值：

```text
version = dev
revision = unknown
```

`unknown` 只允许用于本地、测试或非正式构建；staging Workflow 和 Docker build 测试必须拒绝缺失或非法 revision。

## 组件边界

实现拆成五个可独立验证的部分：

1. **Release planner**
   - 在构建前输出产品版本；
   - 在部署后按 expected tag 重新验证并渲染 Changelog；
   - 不负责修改前后端包版本。

2. **Web version module**
   - 读取 Vite 构建变量；
   - 向 UI 提供产品版本；
   - 生成并打印一次 console 完整构建身份。

3. **API version module**
   - 读取 API 镜像环境变量；
   - 向 `/health` 提供产品版本和完整 revision。

4. **Build injection**
   - GitHub Actions 把同一 Plan 输出注入 Vite 和 Docker；
   - Dockerfile 固化 API 版本身份。

5. **Local dev injection**
   - `scripts/dev.sh dev` 向两个进程传入同一个本地 SHA；
   - 不创建 Tag，不参与 SemVer 递增。

## 测试与验收

### Release planner

至少覆盖：

1. Plan 阶段无需部署元数据即可输出版本；
2. Render 阶段使用真实部署时间生成现有格式的 Changelog；
3. expected tag 与重新规划结果不一致时失败；
4. 目标 SHA 已有相同 Tag 时允许幂等补齐；
5. 现有 SemVer 递增、回滚和多 Tag 防护测试继续通过。

### Web

至少覆盖：

1. UI 只显示构建期产品版本；
2. UI 不显示 full 或 short revision；
3. console 精确打印 `[LMDJ] v0.2.0 · afa06994`；
4. 日志函数每次应用启动只被调用一次，不受 React 重渲染影响；
5. 本地回退显示 `dev`；
6. 修改 `package.json` 版本不会改变产品版本输出。

### API

至少覆盖：

1. `/health` 返回 `ok`、`version`、`revision`；
2. staging 格式保留完整 40 位 SHA；
3. 环境变量能被 app factory 的隔离测试可靠覆盖；
4. 未注入时返回确定性的 `dev` / `unknown`。

### Workflow、Docker 与本地脚本

静态和脚本级测试至少断言：

1. Plan 位于 Web 和服务器镜像构建之前；
2. Web 与 Docker 使用相同的 Plan tag 和目标 SHA；
3. Render 位于 staging revision 验证之后；
4. Render 接收并核对 expected tag；
5. Dockerfile 声明并保留两个版本 build argument；
6. `scripts/dev.sh dev` 向 Web 和 API 注入同一个 Git SHA；
7. Tag 仍只在 staging 激活成功后创建；
8. 现有部署、离线镜像、回滚和 Release 幂等测试继续通过。

### 真实 staging 验收

部署一个新版本后核对：

1. 页面只显示最终 Tag，例如 `v0.2.1`；
2. console 打印该 Tag 和目标 SHA 前 8 位；
3. `/health` 返回同一 Tag 和完整目标 SHA；
4. 服务器 `DEPLOYED_REVISION` 等于该完整 SHA；
5. Git Tag、GitHub Release 和 Changelog 指向同一 SHA；
6. 对同一 SHA 重跑部署时复用相同版本；
7. 下一次新 SHA 部署按 Conventional Commit 规则生成新产品版本。

## 非目标

- 不为每个 commit 自动递增 SemVer；
- 不自动修改 `package.json` 或 Python `pyproject.toml` 包版本；
- 不把 revision 显示在 UI；
- 不拆分前端、API、Worker 的产品版本；
- 不在部署成功前创建产品 Tag；
- 不新增独立版本 API；沿用 `/health`；
- 不改变 staging 版本递增和 Changelog 分类规则；
- 不实现 production promotion 或独立组件发布。
