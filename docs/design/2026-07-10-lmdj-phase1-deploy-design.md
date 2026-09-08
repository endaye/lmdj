# LMDJ 阶段一部署设计（单机 docker compose）

日期：2026-07-10
状态：已评审设计（brainstorming 流程产出）
落点：仓库根新增 `Dockerfile` / `compose.yml` / `Caddyfile` / `.env.example`；`docs/deploy/`；`apps/api` 与 `apps/web` 各一处最小 env 化。

## 定位

把当前单节点应用（api 后台线程跑 job、子进程调 demo pipeline、文件系统 job 库）打包成"任意装了 docker 的机器上 `docker compose up -d` 即起"的可复现栈：Caddy 自动 HTTPS + 静态前端 + 反代 API，同镜像含 demo 的 torch venv 跑 demucs。目标是内测/演示级的完整可访问站点，不是生产多机架构（那是 infra spec 的 phase 2）。

## 已确认的设计决策

| 决策点 | 结论 |
|--------|------|
| 部署目标 | 自托管 VM（Hetzner/DO/Vultr，16GB 起）+ docker compose |
| 镜像形态 | 单镜像，双 venv：demo（torch/demucs/numpy<2 + ffmpeg）+ app（fastapi/patchify/audio-worker，numpy2）；api 子进程 shell 到 demo venv 路径（`DemoPipelineRunner` 不改） |
| 入口 | compose 内 Caddy：自动 HTTPS、serve `apps/web` 静态构建、反代 `/api/*` → uvicorn（前后端同源） |
| 配置 | 三处最小 env 化（CORS origins / jobs_root / web API base），不引入配置框架 |
| 架构 | 方案 A：单镜像 + compose(app + caddy)，匹配阶段一单节点 |

## 镜像与拓扑

### Dockerfile（单镜像，双 venv）

```text
FROM python:3.11-slim（兼容 demo requires-python>=3.10 与 app>=3.11）
apt: ffmpeg, git, build 基础
demo venv  → references/demos/lmdj-song-pipeline/.venv
             pip install -e .[generate]（torch/torchaudio/demucs/numpy<2）
app  venv  → /opt/app-venv
             pip install -e packages/core-models packages/patchify workers/audio apps/api
构建期预热：跑一次 demucs 加载（触发权重下载到镜像内 ~/.cache），
           否则首个 job 现下模型（慢，离线直接失败）
CMD: /opt/app-venv/bin/uvicorn lmdj_api.app:app --host 0.0.0.0 --port 8000
```

关键约束：两套 numpy 不能共存（demo numpy<2 因 demucs/numba，app numpy2）——这正是子进程隔离的由来，镜像必须双 venv。`DemoPipelineRunner` 已 shell 到 `{demo_dir}/.venv/bin/song-pipeline`，镜像在该路径建 demo venv 即可，运行时代码零改。

### compose.yml

```text
services:
  app:
    build: .
    environment:
      LMDJ_JOBS_ROOT: /data/jobs
      LMDJ_CORS_ORIGINS: ""        # 同源部署，留空即可（dev 默认 localhost:5173）
    volumes:
      - data:/data                 # job 产物持久化，重启不丢
    expose: ["8000"]               # 不对外，只给 caddy
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./apps/web/dist:/srv/web    # 前端静态构建（部署前本地/CI npm run build 产出）
      - caddy_data:/data
      - caddy_config:/config
volumes: { data: {}, caddy_data: {}, caddy_config: {} }
```

前端静态构建方式：`apps/web` 的 `npm run build`（`VITE_API_BASE=/api`）产出 `dist/`，由 Caddy 直接 serve。设计取"部署前本地/CI build 出 dist 再随 compose 挂载"，避免把 node 工具链塞进这个已很重的 python 镜像。

### Caddyfile

```text
{$LMDJ_DOMAIN} {
    handle_path /api/* {
        reverse_proxy app:8000
    }
    handle {
        root * /srv/web
        try_files {path} /index.html
        file_server
    }
}
```

`handle_path /api/*` 剥掉 `/api` 前缀再转发，所以 uvicorn 侧仍是 `/uploads`、`/jobs/...` 原路由，api 代码零改。`{$LMDJ_DOMAIN}` 从 env 取（本地测可设 `localhost`，Caddy 自签；线上设真实域名，Caddy 自动 Let's Encrypt）。

### 数据流（生产同源）

```text
浏览器 https://域名/           → Caddy → /srv/web 静态（Patch View）
Web fetch /api/uploads|/jobs   → Caddy handle_path 剥 /api → app:8000 uvicorn
job 产物                       → /data/jobs（volume，重启保留）
demucs 权重                    → 镜像内预热缓存（构建期已下）
```

## 三处最小 env 化（deploy-enabling，带单测回归）

1. **`apps/api` CORS origins** — create_app 读 `LMDJ_CORS_ORIGINS`（逗号分隔；空串 → 空列表/不加中间件；默认 `http://localhost:5173` 保 dev）。同源部署下 CORS 实质无关，留空即可。
2. **`apps/api` jobs_root** — 模块级 `app = create_app()` 的 jobs_root 读 `LMDJ_JOBS_ROOT`（默认现值 `apps/api/jobs`；生产 `/data/jobs`）。create_app 已接受 jobs_root 参数，仅默认值改为读 env。
3. **`apps/web` API base** — `UploadPanel` 默认 base 改为 `import.meta.env.VITE_API_BASE ?? "http://localhost:8000"`；docker 前端构建设 `VITE_API_BASE=/api`。`normalizeBase("/api")` 原样通过（非空、无尾斜杠），`fetch("/api/uploads")` 为同源相对请求。

三处都以既有单测确认 dev 默认行为不变（新增各一条 env 覆盖测试）。

## 错误处理 / 运维

| 情况 | 行为 |
|------|------|
| demucs 权重未预热且离线 | 构建期预热避免；若跳过，首 job `failed` 带下载错误（status.json 可查） |
| job 产物盘写满 | 由 `data` volume 承载；文档提示监控磁盘（阶段一无自动清理） |
| 容器重启 | `/data/jobs` 持久化，已完成 job 的 status/patch 仍可取；进行中 job 丢失（无队列/持久任务，phase 2 解决） |
| Caddy 证书 | `caddy_data` volume 持久化，避免重签触发 LE 限流 |

## 测试 / 验证

- 基础设施无单测；验收 = 可复现构建 + 真实冒烟：
  1. `docker build` 成功（双 venv、ffmpeg、权重预热）；
  2. `docker compose up -d`（本地设 `LMDJ_DOMAIN=localhost`）；
  3. 浏览器 `https://localhost` 或 `curl` 传 demo `input.wav` → 轮询 completed → 取 patch（过 `lmdj.patch.v1` schema）。
- 三处 env 化的单测：CORS 空/自定义、jobs_root env 覆盖、web base env 覆盖——均确认 dev 默认不变。

## 产出物

- 仓库根：`Dockerfile`、`compose.yml`、`Caddyfile`、`.env.example`（`LMDJ_DOMAIN` / `LMDJ_CORS_ORIGINS` / `LMDJ_JOBS_ROOT`）
- `docs/deploy/phase-1.md`：开机器 → 装 docker → 拉码 → `npm run build`（前端）→ `docker compose up -d` → 指 DNS A 记录 → 验证冒烟，一步步。
- `.dockerignore`（排除各 `.venv`、`node_modules`、`jobs/`、`output/`）。

## 范围外（阶段一不做）

CI/CD 流水线、secrets manager、Postgres/对象存储/队列（phase 2）、worker 独立扩缩容/GPU、监控告警日志栈、多机/负载均衡、job 产物自动清理、鉴权/限流（沿用 apps/api 已记的接受风险）。

## 执行期用户前置（我无法代操作）

开云主机、购买/指定域名、DNS A 记录指向 VM、在 VM 上安装 docker + compose。本设计交付的是"任意装了 docker 的机器上 `docker compose up` 即起"的配置与文档，不含云账号/域名/DNS 的实际操作。

## 成功标准

1. 全新装了 docker 的机器：拉码 → 前端 build → `docker compose up -d` → 起栈无手工干预；
2. `https://{域名}/` 打开 Patch View，填同源（默认 `/api`）传 demo 歌，约 30s 后进 workstation 可播放；
3. 容器重启后已完成 job 的 patch 仍可访问；证书不重签；
4. 三处 env 化默认值保证本地 `scripts/dev.sh` / `npm run dev` / 各单测行为不变；
5. 镜像可在另一台机器复现构建（无隐式本地依赖）。
