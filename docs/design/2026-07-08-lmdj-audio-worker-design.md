# LMDJ Audio Worker v1 设计

日期：2026-07-08
状态：已评审设计（brainstorming 流程产出）
落点：`workers/audio/`

## 定位

`workers/README.md` 声明的第一优先级链路的正式落地：**音频输入 → pipeline → patchify → patch.json**，以 LMDJ-owned job 单元的形式。它是未来 `apps/api/`（包装本 job 函数）与队列消费者（infra 待决）的公共内核；v1 无队列、无 HTTP、无数据库。

## 已确认的设计决策

| 决策点 | 结论 |
|--------|------|
| 形态 | Job 库 + CLI（`lmdj-audio-worker`）：核心是可调用的 `process_job()`，未来 API/queue 直接包裹；不自带队列/HTTP |
| demo 集成 | **子进程**调 demo 自己 venv 的 `song-pipeline run --out ... --fast`；worker 包保持轻量（不进 torch/numpy<2 锁），把冻结的 demo 当外部工具——符合参考项目定位与 truth 三段式 |
| 状态粒度 | `state` 合法值 = infra spec 全枚举（queued/generating/separating/extracting/patchifying/rendering/completed/failed/cancelled，写入契约）；v1 实际发射 `queued → separating → patchifying → completed | failed`。未来细化不破契约 |
| 架构 | 方案 A 三模块分层：`runner.py` / `job.py` / `status.py` + `cli.py` |

## Job 模型与目录布局

```text
workers/audio/               lmdj-audio-worker（Python ≥3.11；依赖 lmdj-patchify + lmdj-core-models，本地 editable 安装）
{jobs_root}/{job_id}/        默认 jobs_root = workers/audio/jobs/（gitignored，根 .gitignore 增加 workers/audio/jobs/）
  input/<原文件名>            提交音频的拷贝
  source-<sha256(audio)>/    package：demo pipeline `--out {job_dir} --song-id source-<sha256(audio)>` 直写 + patchify 产出 patch.json
  status.json                状态唯一真相，原子写（tmp + os.replace）
```

`job_id`、job 目录和 `status.json` 是每次运行的随机、Job-scoped 身份。Worker 流式计算上传音频字节的 SHA-256，并以 `source-<full-hex-digest>` 作为 `--song-id` 和 package 目录名；`status.json.package_dir` 记录该相对目录名，所有 package 查找都必须经由它，而不能从 `job_id` 推导。于是当相同音频经过确定性 pipeline 得到相同 `lanes.json` 与 `chart.mid` 时，完整 `patch_id`（`{song_id}-{内容hash}`）可跨 Job 稳定；source hash 不替代或弱化既有内容 hash。

- `job_id`：调用方可指定；缺省 `uuid4().hex[:12]`，仅为运行标识。
- `song_id` / `package_dir`：`source-<sha256(audio bytes)>`，与随机 Job 身份独立。
- `status.json` 契约：

```json
{
  "job_id": "a1b2c3d4e5f6",
  "state": "completed",
  "error": null,
  "patch_id": "source-250670be...9709-6d0b984b",
  "package_dir": "source-250670be...9709",
  "quality": "passed",
  "created_at": "2026-07-08T00:00:00Z",
  "updated_at": "2026-07-08T00:03:21Z"
}
```

  - `state`：合法值为 infra 全枚举；每次状态转移前落盘。
  - `quality`：pipeline `report.status` 透传（`passed` / `rejected`）；**`rejected` 是 `completed` + `quality: "rejected"`，不是 `failed`**——与 patchify 对 rejected 包照常转换的行为一致。
  - `error`：仅 `failed` 时非空；含子进程 stderr 尾部（截断至 ~2000 字符）。
  - 时间戳 ISO 8601 UTC。

## Runner 与编排

### `runner.py`

- `PipelineRunner` 协议：`run(audio: Path, out_dir: Path, song_id: str) -> Path`，返回 package 目录；失败抛 `PipelineRunError(message, stderr_tail)`。
- `DemoPipelineRunner(demo_dir, fast=True, timeout_sec=1800)`：
  - 子进程：`{demo_dir}/.venv/bin/python workers/audio/lmdj_audio_worker/deterministic_bootstrap.py <sha256(audio)-derived-seed> {demo_dir}/.venv/bin/song-pipeline run <audio> --out {job_dir} --song-id source-<sha256(audio)> [--fast]`；bootstrap 在 demo 导入 Demucs 前 seed child `random`，但属于 Worker 而非冻结 demo；
  - demo venv 缺失 → 可读错误（提示 `scripts/dev.sh setup-demo`）；
  - 超时 → kill + `PipelineRunError`；非零退出码 → 抓 stderr 尾部；
  - 成功判定：package 目录存在且含 `lanes.json`（其余交给 patchify 的 loader 校验）。

### `job.py`

- `process_job(audio: Path, *, job_id: str | None, jobs_root: Path, runner: PipelineRunner) -> JobStatus`：
  1. 建随机 job 目录、落 `queued`；流式 hash 输入字节为 source ID，再拷贝 input；
  2. 落 `separating`（整个 pipeline 子进程期间的粗粒度状态）→ `runner.run(..., source_id)`；
  3. 落 `patchifying` → 库调 `lmdj_patchify.patchify_package(package_dir)`（轻依赖，同 venv）；
  4. 终态：`completed`（带 patch_id/quality）或 `failed`（带 error）；任何异常必落盘，不吞。
- 同步执行（阻塞至终态）；并发/队列属未来层。

### `status.py`

- `JobStatus` dataclass + `write_status()`（tmp + `os.replace` 原子写）+ `read_status(jobs_root, job_id)`。

### `cli.py`

```bash
lmdj-audio-worker run <audio> [--job-id X] [--jobs-root DIR] [--demo-dir DIR] [--no-fast]
    # 同步跑完；打印每次状态转移与最终 patch.json 路径；failed 时退出码 1
lmdj-audio-worker status <job_id> [--jobs-root DIR]
    # 打印 status.json 内容
```

- `--demo-dir` 缺省为仓库内 `references/demos/lmdj-song-pipeline`（相对 worker 包定位）。
- 含 `python -m lmdj_audio_worker.cli` 入口（`__main__` guard，与 web/patchify 同惯例）。

## 错误处理

| 情况 | 行为 |
|------|------|
| demo venv 不存在 | `failed`，error 提示 `scripts/dev.sh setup-demo` |
| 子进程非零退出 / 超时 | `failed`，error 含 stderr 尾部 / timeout 说明 |
| pipeline 产出缺 `lanes.json` | `failed`，error 指明产物不完整 |
| patchify 抛错（含 loops profile 拒绝） | `failed`，error 透传 `ValueError` 信息 |
| pipeline `rejected` | `completed` + `quality: "rejected"` |
| 输入文件不存在 | 建 job 前即报错（CLI 退出码 1），不产生 job 目录 |

## 测试

- **零 demucs/torch**：`FakeRunner` 将 `packages/patchify/tests/fixtures/testsong/`（golden fixture，monorepo 跨包相对路径引用——web contract test 已有先例）拷贝为 package 目录。
- 覆盖：happy path 状态序列（queued→separating→patchifying→completed，逐次落盘可见）、rejected 透传、runner 抛错 → failed + error、缺 lanes.json → failed、原子写（读到的 status.json 永远是完整 JSON）、CLI run/status 出口码。
- `DemoPipelineRunner` 的子进程参数构造用单测锁定（不真跑）；真实端到端 = 手动冒烟：`lmdj-audio-worker run` 对一首真歌（或 demo testsong 的 input.wav）。

## 范围外（v1 不做）

队列（Redis/RQ/云托管——infra 待决）、HTTP API（`apps/api/` 职责）、并发/多 job 调度、cancel 语义（枚举预留）、数据库/对象存储、generation worker、LMDJ 中间格式（truth 三段式退出条件，属 pipeline 正式化的独立计划）、进度百分比。

## 成功标准

1. `lmdj-audio-worker run 一首歌.mp3` 同步产出 `{jobs_root}/{job_id}/source-<sha256(audio)>/patch.json`（过 schema），并通过 `status.json.package_dir` 查找，status.json 终态 `completed`；
2. 全过程状态转移逐次落盘，外部进程任意时刻读 status.json 都是合法完整 JSON；
3. demo venv 缺失/子进程失败/劣质包，全部落 `failed` + 可读 error，无未捕获异常；
4. worker 包 venv 无 torch/numpy<2 锁（`pip list` 干净）；
5. 单测全绿且不依赖 demucs/MusicGen/ffmpeg。
