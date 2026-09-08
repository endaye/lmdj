# LMDJ 单服务器分支与部署工作流设计

日期：2026-07-15
状态：已确认方向，待实施
关联设计：`docs/design/2026-07-10-lmdj-phase1-deploy-design.md`

## 目标

在当前只有一台服务器的前提下，建立一套简单、可追溯、可回滚的交付流程：

1. `main` 是唯一长期集成分支，并始终保持可部署；
2. 所有改动通过短期分支和 Pull Request 进入 `main`；
3. PR 与 `main` 提交自动运行 CI；
4. 服务器暂时作为唯一的 `staging` 环境，由人工从 GitHub Actions 触发部署，只接收已经进入 `main` 的提交；
5. 每次部署记录精确 commit SHA，不创建长期 `release` 或 `deploy` 分支。

本设计面向当前内测/演示级单机部署，不同时常驻 `staging` 与 `production`，也不处理多机编排、蓝绿发布或长期多版本维护。

## 环境模型

- 本地开发机是 `development`；
- 唯一服务器是 `staging`，承载当前可远程访问的内测版本；
- 当前不创建永久 `production` 环境；
- 部署时可在同一服务器短暂启动隔离的 `smoke` Compose project，健康检查后立即销毁；它不是第二个常驻环境；
- 对外正式开放时，将这台服务器从 `staging` 原地晋级为 `production`，而不是在同一台机器上同时运行两套长期环境。

同一台服务器上的两个常驻环境会共享 CPU、内存、磁盘、Docker daemon 和网络故障域，不能提供真实隔离，反而会让 Demucs 等重任务互相争抢资源。因此当前只维护一个永久环境。

## 分支模型

### 长期分支

- `main`：唯一长期分支；远端默认分支；服务器部署版本只来自这里。
- 不创建 `develop`、`release` 或 `production` 长期分支。

### 短期分支

- `feat/<topic>`：功能开发；
- `fix/<topic>`：缺陷修复；
- `chore/<topic>`：工具、依赖或仓库维护；
- Codex 创建的分支使用仓库约定的 `codex/` 前缀，例如 `codex/feat-single-server-deploy`。

短期分支通过 PR 合并后删除。线上紧急修复也从最新 `main` 创建 `fix/*`，验证后仍通过 PR 回到 `main`。

## 主干保护

在 CI 工作流首次进入 `main` 后，为 `main` 启用以下规则：

- 必须通过 Pull Request 合并；
- 必须通过 CI 必需检查；
- 合并前分支必须与最新 `main` 同步；
- 禁止 force push；
- 禁止删除 `main`；
- 当前只有一名维护者时不强制第二人审批，后续增加协作者再要求至少一名 reviewer。

管理员保留应急绕过能力，但正常开发不直接 push `main`。

## CI 工作流

新增 `.github/workflows/ci.yml`，触发条件：

- 对 `main` 的 Pull Request；
- push 到 `main`。

CI 只做确定性验证，不访问 staging 服务器。检查按现有子项目边界拆分：

1. `core-models`：安装 package 并运行 pytest；
2. `patchify`：安装 package 并运行 pytest；
3. `audio-worker`：安装 package 并运行 pytest；
4. `api`：安装 package 并运行 pytest；
5. `web`：`npm ci`、测试、类型检查/构建；
6. 配置检查：Docker Compose 配置可解析，前提是部署文件已落地。

各 job 可并行运行。主干保护要求所有必需 job 成功，避免只验证 Web 或只验证 Python 的半成品进入 `main`。

## 单服务器 staging 部署

### 触发方式

新增 `.github/workflows/deploy-server.yml`，绑定 GitHub `staging` Environment，只允许 `workflow_dispatch` 手动触发。工作流提供可选的 `commit_sha` 输入：留空时部署触发时最新的 `main`，填写时必须是 `main` 历史中的完整 SHA；任意 feature branch 提交会被拒绝。

初期流程：

```text
PR 合并
  -> main CI 全绿
  -> 维护者在 GitHub Actions 点击 Run workflow（staging）
  -> 打包 main 当前 commit
  -> 上传到服务器
  -> 短暂 smoke 栈启动并通过 API 健康检查
  -> staging Docker Compose 更新
  -> 健康检查
```

这相当于当前唯一远程环境的人工批准门。连续稳定运行后，可以把触发条件改为 `main` CI 成功后自动部署 staging，而不需要改变分支模型。

### 发布单元

部署单元是一个 commit SHA，而不是一个分支：

- workflow 解析并验证目标 SHA 可从 `origin/main` 到达，再 checkout 该精确 SHA；
- Web 在 CI runner 上以 `VITE_API_BASE=/api` 构建；
- 源码与 `apps/web/dist` 打成 release archive；
- archive 上传到服务器的 `${DEPLOY_PATH}/releases/<sha>/`；
- 以独立 project name `lmdj-smoke` 启动 app，并只映射服务器本机临时端口；健康检查后立即 `down -v`；
- `${DEPLOY_PATH}/current` 原子切换到本次 release；
- 在 `current` 中用固定 project name `lmdj` 执行 Docker Compose，确保 named volumes 跨 release 复用；
- `${DEPLOY_PATH}/shared/.env` 只存在服务器上，不进入 Git。

服务器不需要 GitHub 仓库读权限，也不需要在工作目录执行 `git pull`。这样 staging 状态由 release 目录和 SHA 明确表示，不会受服务器本地分支或未提交文件影响。

### GitHub Secrets

部署工作流需要在 GitHub `staging` Environment 中配置以下 secrets：

- `DEPLOY_HOST`：服务器域名或 IP；
- `DEPLOY_USER`：SSH 用户；
- `DEPLOY_SSH_KEY`：仅用于部署的私钥；
- `DEPLOY_SSH_KNOWN_HOSTS`：预先核验的服务器 host key；
- `DEPLOY_PATH`：服务器部署根目录，例如 `/opt/lmdj`。

应用运行时配置（例如 `LMDJ_DOMAIN`）保存在服务器 `${DEPLOY_PATH}/shared/.env`，不重复放进 GitHub Secrets。

### 服务器目录

```text
/opt/lmdj/
├── current -> releases/<sha>/
├── releases/
│   ├── <previous-sha>/
│   └── <current-sha>/
└── shared/
    └── .env
```

Compose 使用固定 project name `lmdj`，因此 job 数据和 Caddy 证书 volume 不随 release 目录变化。

## 健康检查与失败处理

smoke 阶段检查 app 容器可以启动且临时端口的 `/health` 成功，然后销毁整个 `lmdj-smoke` project 及临时 volume。更新 staging 后必须检查：

1. `docker compose -p lmdj ps` 中服务已启动；
2. 本机通过 Caddy 请求 `/` 成功；
3. 通过 `/api/health` 请求 API 成功；
4. 失败时工作流标红，并输出容器状态与尾部日志，但不输出 `.env` 或 secrets。

若新版本启动失败，部署脚本将 `current` 切回上一 release，并再次执行 Compose。自动回滚只覆盖“启动或健康检查失败”；功能性回归由维护者手动重新部署上一 SHA 处理。

## 版本与回滚

- 每次成功部署记录 SHA、时间和 GitHub Actions run URL；
- 手动回滚时重新触发 server workflow，并把 `commit_sha` 设为上一成功部署的 `main` SHA；
- 对外里程碑使用 SemVer 预发布 tag，例如 `v0.1.0-demo.1`；
- tag 只标记已经验证的 `main` 提交，不触发另一套构建；
- 不使用 `release` 分支表达线上版本；
- 初期至少保留最近两个 release 目录，保证可快速回滚。

## 安全边界

- SSH key 使用独立低权限部署用户；
- `DEPLOY_SSH_KNOWN_HOSTS` 必须预先核验，不在工作流中无条件信任 `ssh-keyscan` 输出；
- 部署用户只拥有 `${DEPLOY_PATH}` 和运行项目所需的 Docker 权限；
- workflow 不打印 secrets、服务器 `.env` 或私钥；
- PR workflow 永远不能访问 staging secrets；只有手动部署 workflow 使用它们；
- GitHub `staging` Environment 只允许从 `main` 部署。

## 实施顺序

1. 完成既有 Phase-1 Docker Compose 部署计划；
2. 新增并验证 CI workflow；
3. 新增 release 打包与服务器部署脚本；
4. 新增手动 server workflow，并绑定 GitHub `staging` Environment；
5. 在服务器创建目录、`.env` 和部署用户；
6. 创建 GitHub `staging` Environment 并配置 Environment Secrets；
7. 首次手动部署并做真实冒烟；
8. CI workflow 合并到 `main` 后开启主干保护。

## 成功标准

1. 本地 `main` 与 `origin/main` 保持同步，日常改动不直接提交到 `main`；
2. PR 无法在必需 CI 失败时合并；
3. server workflow 只向 `staging` 部署 `main` 的已验证提交；
4. 服务器可以从 release 目录明确读出当前部署 SHA；
5. job 数据与 Caddy 证书在升级和回滚后保留；
6. 新版本健康检查失败时自动恢复上一 release；
7. 整个流程不需要 `release` 或 `deploy` 长期分支。
