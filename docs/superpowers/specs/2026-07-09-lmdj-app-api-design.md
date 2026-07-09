# LMDJ App Backend (apps/api) v1 设计

日期：2026-07-09
状态：已评审设计（brainstorming 流程产出）
落点：`apps/api/`

## 定位

云架构 Phase 1（Cloud Patchify MVP）的 HTTP 入口：把 audio worker 的 `process_job` 包成 REST 后端——**上传音频 → 建 job → 轮询状态 → 拉取 patch 产物**。它是 Web / CLI 未来共用的同一套产品 API 的最小起点。v1 无队列、无数据库、无鉴权。

## 已确认的设计决策

| 决策点 | 结论 |
|--------|------|
| 执行模型 | 后台线程 + 轮询：`POST` 立即返回 job_id，`process_job` 在后台跑，客户端 `GET /jobs/{id}` 轮询 status.json。单 `threading.Lock` 串行化（demucs 走子进程，不再是线程安全问题，而是避免并发子进程抢爆 CPU/内存） |
| 框架 | FastAPI（infra spec v1 选型；复用 Python `process_job`） |
| 端点 | 上传 + 状态 + 产物服务（见下） |
| 持久化/鉴权 | 复用 audio worker 的文件系统 job 库（jobs_root + status.json）；无 Postgres / 对象存储 / 账号 / 鉴权 |
| 架构 | 方案 A 薄层：`executor.py`（后台单槽执行器）+ `app.py`（路由工厂），依赖 `lmdj-audio-worker`（本地 editable） |

## 端点契约

```text
GET  /health                        → {"ok": true}
POST /uploads                       multipart file → 存 job/input/ → executor.submit
                                    → 200 {"job_id": "...", "state": "queued"}
GET  /jobs/{job_id}                 → 完整 JobStatus JSON（status.json 内容）；未知 id → 404
GET  /jobs/{job_id}/patch           → patch.json（application/json）
                                    未 completed → 409（body 含当前 state）；文件缺失 → 404
GET  /jobs/{job_id}/files/{path}    → 包内任意相对文件（samples/*.wav、loop_preview.wav 等）
                                    audio/wav 等按扩展名；穿越（含 / 前缀或 ..）→ 400；缺失 → 404
```

- **通用产物端点**：用 `/files/{path:path}` 而非 `/samples/{name}`，因为真实 patch 的 `elements[].source_path` 是 `samples/xxx.wav`、而 `renders[].path` 是包根的 `loop_preview.wav`——一个端点覆盖两类，路径即 patch.json 里的相对路径。
- **Web 消费契约（与拖目录一致）**：Web 拿 `job_id` → 轮询 `/jobs/{id}` 到 `completed` → `GET /jobs/{id}/patch` 拿 patch.json → 对每个 `elements[].source_path` 请求 `/jobs/{id}/files/{source_path}` 拿 wav。组装出的对象与拖目录时的 `PatchBundle` 完全同构，Web 只需多一个"从 API 加载"入口。
- **CORS**：dev 放行 `http://localhost:5173`（Web dev server），让跨端口调用可行。
- **串行排队**：一个 job 在跑时，新 `POST /uploads` 照常建 job 落 `queued`、排队等锁；status.json 如实反映（`queued` 直到轮到它）。

## 模块

### `executor.py`

- `JobExecutor(runner: PipelineRunner, jobs_root: Path)`：
  - `submit(audio_path: Path, job_id: str) -> None`：起 daemon 线程，线程内 `process_job(audio_path, jobs_root=..., runner=..., job_id=...)`；一个实例级 `threading.Lock` 在线程内 `process_job` 外围 acquire，保证任意时刻只有一个 job 真正在跑。
  - `process_job` 自身已把所有异常落盘为 failed；executor 线程只做兜底 `logging.exception`（不吞、不崩线程）。

### `app.py`

- `create_app(runner: PipelineRunner | None = None, jobs_root: Path | None = None) -> FastAPI` 工厂：
  - 缺省 `runner = DemoPipelineRunner(默认 demo-dir)`、`jobs_root = apps/api/jobs/` 相对包定位；测试注入 `FakeRunner` + tmp jobs_root。
  - 装配 CORS、路由、`JobExecutor` 单例。
- 模块级 `app = create_app()` 供 `uvicorn lmdj_api.app:app --port 8000`。
- 上传：`uuid4().hex[:12]` 生成 job_id，落 `job/input/<原名>`（实际 input 拷贝由 executor 内 process_job 完成——app 层把上传字节先落到一个临时文件再交给 executor），executor.submit 后立即返回。

## 错误处理

| 情况 | 响应 |
|------|------|
| 未知 job_id（任何 /jobs/* 端点） | 404 `{"detail": "unknown job_id"}` |
| `/patch` 或 `/files` 但 job 未 completed | 409 `{"detail": "job not completed", "state": "<当前态>"}` |
| patch.json / 请求的 file 不存在 | 404 |
| `/files/{path}` 路径穿越（绝对路径、`..`、逃出包目录） | 400 `{"detail": "invalid path"}` |
| 上传缺 file 字段 | 422（FastAPI 默认校验） |
| job 处理失败 | 不是 HTTP 错误——`GET /jobs/{id}` 返回 `state: "failed"` + error；`/patch` 返回 409（未 completed） |

## 测试

- **FastAPI TestClient + FakeRunner（零 demucs/torch/ffmpeg）**：复用 audio worker 的 `FakeRunner`（拷 golden fixture 为 package）与 golden 音频 fixture。
- 覆盖：`/health`；`POST /uploads` 返回 job_id + queued；轮询 `/jobs/{id}` 到 completed；`/patch` 过 `lmdj.patch.v1` schema 校验；`/files/samples/xxx.wav` 取到字节；未知 job → 404；未完成取 patch → 409；路径穿越（`../../etc/passwd`、绝对路径）→ 400；串行锁（并发提交两个 job，验证不同时跑——用带同步屏障的 FakeRunner 观察）。
- `create_app` 依赖注入使测试完全不碰真实 demo venv；真实端到端 = 手动冒烟：`uvicorn` 起服务 + `curl` 上传 demo testsong 的 input.wav。

## 范围外（v1 不做）

队列（Redis/RQ/云托管——infra 待决）、Postgres / 对象存储、账号 / 鉴权 / 限流、`POST /ideas` 与 generation 入口、remix / sample / fork / share / lineage 端点、`cancel` 实现（infra 枚举已预留）、**Web 侧接入 API 的改动（单独 web 小计划）**、部署 / 容器化 / 生产 CORS 收紧。

## 成功标准

1. `uvicorn lmdj_api.app:app` 起服务，`curl -F file=@song.wav localhost:8000/uploads` 返回 `{job_id, state:"queued"}`；
2. `curl localhost:8000/jobs/{id}` 轮询可见 `queued → separating → patchifying → completed`；
3. completed 后 `GET /jobs/{id}/patch` 返回过 schema 校验的 patch.json，`GET /jobs/{id}/files/samples/<name>.wav` 返回音频字节；
4. 未知 job → 404、未完成取 patch → 409、路径穿越 → 400，均无未捕获异常 / 500；
5. 并发提交两个 job 时串行执行（不同时跑 demucs 子进程）；
6. 全部单测绿且不依赖 demucs/MusicGen/ffmpeg；apps/api venv 无 torch。
