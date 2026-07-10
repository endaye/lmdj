# Phase-1 Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 LMDJ 打包成"任意装了 docker 的机器 `docker compose up -d` 即起"的单机栈：Caddy 自动 HTTPS + 静态前端 + 反代 `/api`，同镜像双 venv 跑 api 与 demo(demucs)。

**Architecture:** 两个 task。Task 1：三处最小 env 化（api CORS / api jobs_root / web API base），有单测、dev 默认不变。Task 2：部署产物（Dockerfile 双 venv、compose、Caddyfile、.env.example、.dockerignore、部署文档），config 可校验 + 文档化冒烟。设计依据：`docs/superpowers/specs/2026-07-10-lmdj-phase1-deploy-design.md`。

**Tech Stack:** Docker + docker compose、Caddy 2、Python 3.11（双 venv：demo torch/numpy<2 + app numpy2）、Vite build、pytest/vitest（env 化回归）。

## Global Constraints

- 单镜像双 venv：demo venv 在 `references/demos/lmdj-song-pipeline/.venv`（torch/demucs/numpy<2 + 系统 ffmpeg），app venv 在 `/opt/app-venv`（core-models/patchify/audio-worker/api，numpy2）；`DemoPipelineRunner` 运行时代码零改（已 shell 到该 demo venv 路径）。
- Caddy `handle_path /api/*` 剥前缀转发 → uvicorn 路由保持 `/uploads`、`/jobs/...` 不变。
- 三处 env 化默认值必须保证 `scripts/dev.sh` / `npm run dev` / 既有全部单测行为不变。
- demucs 权重构建期预热（镜像内 `~/.cache`），避免首 job 现下模型。
- 前端 `dist` 由部署前 `npm run build`（`VITE_API_BASE=/api`）产出，Caddy 挂载 serve；不把 node 塞进 python 镜像。
- job 产物落 `/data/jobs`（volume 持久化）。
- 范围外：CI/CD、secrets manager、Postgres/对象存储/队列、GPU/多机、监控栈、鉴权/限流、job 自动清理。
- 用户前置（不代操作）：开云主机、域名、DNS A 记录、VM 装 docker。
- Commit scope：`feat(deploy): ...` / `feat(api): ...` / `feat(web): ...`。

---

## File Structure

- Modify: `apps/api/lmdj_api/app.py`（CORS origins + jobs_root 读 env）
- Modify: `apps/api/tests/test_app.py`（env 覆盖测试）
- Modify: `apps/web/src/ui/UploadPanel.tsx`（base 默认读 `VITE_API_BASE`）
- Modify: `apps/web/src/ui/App.test.tsx`（base env 覆盖测试）
- Create: `Dockerfile`、`.dockerignore`、`compose.yml`、`Caddyfile`、`.env.example`
- Create: `docs/deploy/phase-1.md`

---

### Task 1: 三处最小 env 化（带 dev-默认不变回归）

**Files:**
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/test_app.py`
- Modify: `apps/web/src/ui/UploadPanel.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`

**Interfaces:**
- Consumes: 既有 `create_app(runner=None, jobs_root=None)`、`UploadPanel`。
- Produces:
  - `apps/api/lmdj_api/app.py`：新增 `default_jobs_root() -> Path`、`_cors_origins() -> list[str]`；create_app 用它们，CORS 仅在非空时挂中间件。
  - 环境变量：`LMDJ_CORS_ORIGINS`、`LMDJ_JOBS_ROOT`、`VITE_API_BASE`。

- [ ] **Step 1: 写 failing 测试（api CORS + jobs_root）**

在 `apps/api/tests/test_app.py` 追加（不改既有测试）：

```python
from pathlib import Path
from fastapi.testclient import TestClient
from lmdj_api.app import create_app, default_jobs_root
from tests.conftest import FakeRunner


def test_cors_origins_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LMDJ_CORS_ORIGINS", "https://a.example,https://b.example")
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))
    r = client.get("/health", headers={"Origin": "https://a.example"})
    assert r.headers.get("access-control-allow-origin") == "https://a.example"


def test_cors_absent_when_env_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LMDJ_CORS_ORIGINS", "")
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))
    r = client.get("/health", headers={"Origin": "https://a.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_default_is_dev_localhost(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("LMDJ_CORS_ORIGINS", raising=False)
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_default_jobs_root_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LMDJ_JOBS_ROOT", str(tmp_path / "custom-jobs"))
    assert default_jobs_root() == tmp_path / "custom-jobs"


def test_default_jobs_root_fallback(monkeypatch):
    monkeypatch.delenv("LMDJ_JOBS_ROOT", raising=False)
    assert default_jobs_root().name == "jobs"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/api
.venv/bin/python -m pytest tests/test_app.py -q
```

Expected: FAIL——`cannot import name 'default_jobs_root'`。

- [ ] **Step 3: 改 app.py**

修改 `apps/api/lmdj_api/app.py`：加 `import os`；把 `_API_ROOT`/`DEFAULT_JOBS_ROOT` 段与 create_app 头部替换为：

```python
import os
# ... 其余 import 不变

_API_ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_JOBS_ROOT = _API_ROOT / "jobs"
DEFAULT_DEMO_DIR = _API_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]

_CONTENT_TYPES = {".wav": "audio/wav", ".json": "application/json", ".mid": "audio/midi"}


def default_jobs_root() -> Path:
    """jobs_root 默认值：LMDJ_JOBS_ROOT 环境变量，否则包内 jobs/。"""
    env = os.environ.get("LMDJ_JOBS_ROOT")
    return Path(env) if env else _FALLBACK_JOBS_ROOT


def _cors_origins() -> list[str]:
    """CORS 允许来源：LMDJ_CORS_ORIGINS 逗号分隔；未设 → dev 默认；空串 → 空列表（不启用）。"""
    raw = os.environ.get("LMDJ_CORS_ORIGINS")
    if raw is None:
        return DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(runner: PipelineRunner | None = None, jobs_root: Path | None = None) -> FastAPI:
    jobs_root = jobs_root or default_jobs_root()
    runner = runner or DemoPipelineRunner(DEFAULT_DEMO_DIR)
    executor = JobExecutor(runner=runner, jobs_root=jobs_root)

    app = FastAPI(title="LMDJ API")
    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    # ↓ 以下 _job_dir 与所有路由保持原样，一字不改
```

（原文件里 `DEFAULT_JOBS_ROOT` 常量若被别处引用需一并改名为 `_FALLBACK_JOBS_ROOT` 或保留别名；确认无其他引用后删除旧常量。`_job_dir` 及五个路由函数原样保留。）

- [ ] **Step 4: 跑 api 测试确认通过**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 全绿（既有 11 + 新增 5 = 16）。

- [ ] **Step 5: 写 failing 测试（web base env）**

在 `apps/web/src/ui/App.test.tsx` 追加（不改既有；`vi` 若已 import 则复用）：

```tsx
import { afterEach, vi } from "vitest";

afterEach(() => vi.unstubAllEnvs());

describe("UploadPanel base URL default", () => {
  it("uses VITE_API_BASE when set", async () => {
    vi.stubEnv("VITE_API_BASE", "/api");
    const { UploadPanel } = await import("./UploadPanel");
    render(<UploadPanel onUpload={() => {}} />);
    expect(screen.getByTestId("api-base-input")).toHaveValue("/api");
  });
});
```

- [ ] **Step 6: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/ui/App.test.tsx
```

Expected: FAIL——base 仍硬编码 `http://localhost:8000`。

- [ ] **Step 7: 改 UploadPanel.tsx**

`apps/web/src/ui/UploadPanel.tsx` 的 `useState` 默认值改为读 env：

```tsx
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000",
  );
```

- [ ] **Step 8: 跑 web 全量确认通过**

```bash
npx vitest run
```

Expected: 全绿（既有 51 + 新增 1 = 52；未设 env 时既有"默认 localhost:8000"断言仍成立）。

- [ ] **Step 9: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/api/lmdj_api/app.py apps/api/tests/test_app.py apps/web/src/ui/UploadPanel.tsx apps/web/src/ui/App.test.tsx
git commit -m "feat(api): env-configurable cors and jobs_root; feat(web): VITE_API_BASE default"
```

---

### Task 2: 部署产物（Dockerfile / compose / Caddy / 文档）

**Files:**
- Create: `Dockerfile`、`.dockerignore`、`compose.yml`、`Caddyfile`、`.env.example`、`docs/deploy/phase-1.md`

**Interfaces:**
- Consumes: Task 1 的 env 变量（`LMDJ_JOBS_ROOT` / `LMDJ_CORS_ORIGINS` / `VITE_API_BASE`）。
- Produces: 可 `docker compose up` 的栈；无代码接口。

- [ ] **Step 1: 写 .dockerignore**

Create `.dockerignore`:

```gitignore
**/.venv
**/node_modules
**/dist
**/__pycache__
**/*.egg-info
**/jobs
references/demos/lmdj-song-pipeline/output
.git
.superpowers
.playwright-mcp
```

- [ ] **Step 2: 写 Dockerfile（双 venv + ffmpeg + demucs 预热）**

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/lmdj
COPY . .

# demo venv：torch/demucs/numpy<2（重；基础版即含 audio worker 所需 demucs/torch，不带 [generate]/MusicGen）
RUN python -m venv references/demos/lmdj-song-pipeline/.venv \
    && references/demos/lmdj-song-pipeline/.venv/bin/pip install --no-cache-dir -U pip \
    && references/demos/lmdj-song-pipeline/.venv/bin/pip install --no-cache-dir \
       -e "references/demos/lmdj-song-pipeline"

# app venv：fastapi/patchify/audio-worker（numpy2，轻）
RUN python -m venv /opt/app-venv \
    && /opt/app-venv/bin/pip install --no-cache-dir -U pip \
    && /opt/app-venv/bin/pip install --no-cache-dir \
       -e packages/core-models -e packages/patchify -e workers/audio -e apps/api

# 预热 demucs 权重到镜像内缓存（避免首 job 现下模型）
RUN references/demos/lmdj-song-pipeline/.venv/bin/python -c \
    "from demucs.pretrained import get_model; get_model('htdemucs')"

ENV LMDJ_JOBS_ROOT=/data/jobs
EXPOSE 8000
CMD ["/opt/app-venv/bin/uvicorn", "lmdj_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

> 若某一步的 pip 目标名/extra 与 demo pyproject 不符，以 demo `pyproject.toml` 的实际 `name`/extras 为准调整（demo 提供 `song-pipeline` 控制台脚本，`DemoPipelineRunner` 依赖它存在于 `.venv/bin/`）。

- [ ] **Step 3: 写 Caddyfile**

Create `Caddyfile`:

```
{$LMDJ_DOMAIN:localhost} {
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

- [ ] **Step 4: 写 compose.yml**

Create `compose.yml`:

```yaml
services:
  app:
    build: .
    environment:
      LMDJ_JOBS_ROOT: /data/jobs
      LMDJ_CORS_ORIGINS: ""
    volumes:
      - data:/data
    expose:
      - "8000"
    restart: unless-stopped

  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    environment:
      LMDJ_DOMAIN: ${LMDJ_DOMAIN:-localhost}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./apps/web/dist:/srv/web
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - app
    restart: unless-stopped

volumes:
  data:
  caddy_data:
  caddy_config:
```

- [ ] **Step 5: 写 .env.example**

Create `.env.example`:

```
# 部署域名（Caddy 自动 HTTPS 用；本地测试用 localhost 自签）
LMDJ_DOMAIN=example.com
# API 允许的 CORS 来源（同源 Caddy 部署留空即可；逗号分隔多个）
LMDJ_CORS_ORIGINS=
# job 产物目录（容器内，映射到 data volume）
LMDJ_JOBS_ROOT=/data/jobs
```

- [ ] **Step 6: 写部署文档**

Create `docs/deploy/phase-1.md`:

````markdown
# LMDJ 阶段一部署（单机 docker compose）

单节点栈：Caddy(HTTPS + 静态前端 + 反代 /api) + app(uvicorn，后台跑 job，子进程调 demucs)。
设计见 `docs/superpowers/specs/2026-07-10-lmdj-phase1-deploy-design.md`。

## 前置（需你自己完成）
1. 开一台 ≥16GB RAM 的 VM（Hetzner/DO/Vultr）。
2. 域名一枚，DNS A 记录指向 VM 公网 IP。
3. VM 安装 docker + docker compose plugin。

## 部署步骤
```bash
git clone <repo> && cd lmdj

# 1. 构建前端（同源相对 /api）
cd apps/web && npm ci && VITE_API_BASE=/api npm run build && cd ../..
#    产出 apps/web/dist/，compose 挂载给 Caddy

# 2. 配置域名
cp .env.example .env    # 编辑 .env：设 LMDJ_DOMAIN=你的域名

# 3. 起栈（首次构建镜像含 torch/demucs，较慢，数 GB）
docker compose up -d --build

# 4. 验证
curl -k https://你的域名/api/health        # {"ok":true}
#    浏览器打开 https://你的域名/ → 传一首歌 → ~30s 后进 workstation
```

## 运维
- job 产物在 `data` volume（`/data/jobs`）；重启保留已完成 job。
- 磁盘：无自动清理，定期看 `docker system df` 与 volume 用量。
- 日志：`docker compose logs -f app`。
- 更新：`git pull && (cd apps/web && VITE_API_BASE=/api npm run build) && docker compose up -d --build`。

## 已知限制（阶段一）
- 单机、串行 job（一个锁）；无队列/DB/对象存储/鉴权（见 spec 范围外与 apps/api 接受风险）。
- 上传无体积上限、临时文件不清理（本地/内测可接受）。
````

- [ ] **Step 7: 校验配置可解析**

```bash
cd /Users/endaye/Projects/lmdj
docker compose config >/dev/null && echo "compose OK"
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile" caddy:2 \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && echo "caddyfile OK"
```

Expected: 两行 OK。若本机无 docker，记录为"未在此环境校验，待部署机验证"，不阻塞。

- [ ] **Step 8: 全量镜像构建 + 冒烟（能力允许时）**

```bash
cd /Users/endaye/Projects/lmdj
cd apps/web && VITE_API_BASE=/api npm run build && cd ../..   # 前端 dist 供挂载
LMDJ_DOMAIN=localhost docker compose up -d --build            # 首次数 GB，慢
sleep 5 && curl -k https://localhost/api/health               # {"ok":true}
docker compose down
```

Expected: health 返回 ok。若环境无法完成重镜像构建，记录并交部署机/终审在真实机器上跑（本步为文档化冒烟，非单测门）。

- [ ] **Step 9: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add Dockerfile .dockerignore compose.yml Caddyfile .env.example docs/deploy/phase-1.md
git commit -m "feat(deploy): single-node docker compose stack with caddy and dual-venv image"
```

---

## Verification

- Task 1：`apps/api` 16 passed、`apps/web` 52 passed（dev 默认不变）。
- Task 2：`docker compose config` 解析通过、`caddy validate` 通过；能力允许时 `docker compose up --build` + `curl /api/health` ok + 浏览器传歌冒烟。
- 真实部署验收（用户机器）：DNS 生效后 `https://域名/` 传 demo 歌 → workstation 可播放；重启后已完成 job 的 patch 仍可取。

## Out Of Scope For This Plan

CI/CD、secrets manager、Postgres/对象存储/队列、GPU/多机/负载均衡、监控告警日志栈、鉴权/限流、job 自动清理、`[generate]`/MusicGen 路径（基础镜像只装 demucs/torch 支撑上传路径）。

## Self-Review

- Spec 覆盖：双 venv 镜像 + ffmpeg + 权重预热（Task 2 Dockerfile）；Caddy handle_path /api 反代 + 静态（Caddyfile/compose）；三处 env 化（Task 1，带 dev 默认回归）；jobs volume 持久化（compose）；.env.example / 部署文档 / .dockerignore（Task 2）——逐条可指到任务。
- 类型一致性：`default_jobs_root()` / `_cors_origins()` 在 app.py 定义并被 create_app 与测试引用；env 变量名 `LMDJ_JOBS_ROOT`/`LMDJ_CORS_ORIGINS`/`VITE_API_BASE`/`LMDJ_DOMAIN` 在 Dockerfile/compose/Caddyfile/.env.example/文档间一致。
- 已知取舍：完整镜像构建重（torch 数 GB），Step 8 冒烟标注"能力允许时/交部署机"，不作硬单测门——基础设施本就靠构建+运行验收；demo 装基础版（不带 [generate]）以减小镜像，gen 路径留待需要时。
