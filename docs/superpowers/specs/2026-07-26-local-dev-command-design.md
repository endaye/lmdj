# LMDJ 前后端联合启动命令设计

日期：2026-07-26

状态：待书面评审

落点：扩展根目录 `scripts/dev.sh`，新增 `dev` 命令及其脚本级测试。

## 目标

为本地 Creator Workspace 开发提供一个仓库级入口：

```bash
scripts/dev.sh dev
```

该命令同时启动：

- Web：Vite，`http://localhost:5173`
- API：Uvicorn，`http://localhost:8000`

命令只负责编排已经准备好的本地环境，不自动安装依赖。任一服务退出或用户按下 `Ctrl+C` 时，命令必须结束两个子进程，避免遗留后台服务。

## 已确认的方案

直接在现有 `scripts/dev.sh` 中实现 `cmd_dev`。不增加独立启动脚本，不引入 `concurrently` 等第三方进程管理依赖。

选择这一方案的原因：

- 用户只需记住现有仓库入口；
- API、Web 和路径约定继续由 `scripts/dev.sh` 集中维护；
- 不给 Python/Node 混合项目增加只为启动进程而存在的 npm 依赖；
- 可以使用 Bash 3.2 支持的 `trap`、`kill -0` 和 `wait` 实现 macOS 兼容的生命周期管理。

## 启动前检查

`dev` 在创建任何后台进程前依次检查：

1. `apps/api/.venv/bin/uvicorn` 可执行；
2. API venv 能导入 `lmdj_api`、`lmdj_audio_worker`、`lmdj_patchify` 和 `lmdj_core_models`；
3. `apps/web/node_modules/.bin/vite` 可执行；
4. Demo venv 的 Python 可执行，且能导入 `torch` 和 `demucs`；
5. 本机存在 `curl`，供启动就绪检查使用。

任一检查失败时，命令必须在启动服务前退出，并给出对应恢复命令：

- API：

  ```bash
  cd apps/api
  python3 -m venv .venv
  .venv/bin/pip install -e ../../packages/core-models
  .venv/bin/pip install -e ../../packages/patchify
  .venv/bin/pip install -e ../../workers/audio
  .venv/bin/pip install -e .
  ```

- Web：`cd apps/web && npm install`
- Demo：`scripts/dev.sh setup-demo`

该检查必须验证真实 import，而不能只判断 venv 或命令入口是否存在；否则会重复出现入口存在但缺少 `torch` 的假就绪状态。

## 进程与数据流

API 在 `apps/api/` 下启动，使用该目录自己的 venv：

```text
apps/api/.venv/bin/uvicorn lmdj_api.app:app
  --host 127.0.0.1
  --port 8000
```

API 继续使用既有默认 Jobs 目录 `apps/api/jobs/`。该目录已被 `.gitignore` 排除。

Web 在 `apps/web/` 下启动：

```text
npm run dev -- --host 127.0.0.1 --port 5173
```

Web 的默认 API Base 保持 `http://localhost:8000`；API 的默认 CORS Origin 保持 `http://localhost:5173`。

## 生命周期与错误处理

1. API 与 Web 作为两个后台子进程启动并记录 PID。
2. `trap` 监听 `EXIT`、`INT`、`TERM` 和 `HUP`。
3. 启动阶段轮询：
   - `http://127.0.0.1:8000/health`
   - `http://127.0.0.1:5173/`
4. 两端都返回成功后，打印两个用户可访问的 `localhost` URL。
5. 进入监督循环：只要两个 PID 都存活就继续等待。
6. 任一服务异常退出时，终止另一端、回收两个子进程，并让联合命令以非零状态退出。
7. 用户按下 `Ctrl+C` 时，同时终止并回收两个子进程，不留下监听 5173 或 8000 的进程。

macOS 自带 Bash 为 3.2，不支持 `wait -n`。实现必须使用 Bash 3.2 可用的轮询和 `wait`，不能依赖 Homebrew Bash。

若 5173 或 8000 已被占用，对应子进程会启动失败；监督逻辑负责关闭另一端并返回失败，不主动终止占用端口的既有进程。

## 测试与验收

脚本级自动化测试至少覆盖：

1. `scripts/dev.sh --help` 包含 `dev`；
2. 缺失 API、Web 或 Demo 依赖时，在启动任何子进程前失败，并显示正确恢复命令；
3. 两个假服务正常启动时，联合命令进入 ready 状态；
4. 任一假服务退出时，另一个服务被终止；
5. 向联合命令发送 `SIGINT` 后，两个子进程均被回收；
6. 测试和实现兼容 Bash 3.2。

真实验收：

```bash
bash -n scripts/dev.sh
scripts/dev.sh dev
curl --fail http://localhost:8000/health
curl --fail http://localhost:5173/
```

随后按 `Ctrl+C`，确认 5173 和 8000 不再监听。

## 非目标

- 不自动创建 venv 或运行 `npm install`；
- 不下载 Torch、Demucs 或模型权重；
- 不支持自定义端口、热切换端口或 HTTPS；
- 不改变 API/Web 的生产部署方式；
- 不替代 staging 的 GitHub Actions 部署流程。
