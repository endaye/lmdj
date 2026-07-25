# Upload Job Visibility Release Evidence

日期：2026-07-26（Asia/Shanghai）

状态：`codex/queue-visibility` 分支已实现并验证，待 Pull Request；不表示已合并、推送或部署。

## 验收对象

- 基线 commit：`2368cef83eca27011ff177026d03d60110f4e118`
- 实现版本：包含本文件的 `feat(api): productionize upload job queue` 提交
- API：`http://127.0.0.1:8123`
- Web：`http://127.0.0.1:5174`
- 浏览器：Playwright CLI Chromium，桌面默认 viewport 与 `520 × 900`
- Job root：隔离临时目录 `/tmp/lmdj-queue-evidence.Ix2lET`

## 自动化门禁

| 边界 | 命令 | 结果 |
|---|---|---|
| Core Models | `packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q` | `7 passed` |
| Patchify | `packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q` | `18 passed` |
| Audio Worker | `workers/audio/.venv/bin/python -m pytest workers/audio/tests -q` | `335 passed` |
| App API | `apps/api/.venv/bin/python -m pytest apps/api/tests -q` | `87 passed`，1 条既有 Starlette deprecation warning |
| Web | `cd apps/web && npm test` | `23 files / 162 tests passed` |
| Web contract | `cd apps/web && npm run check-contract` | `4 passed` |
| Web build | `cd apps/web && npm run build` | TypeScript 与 Vite build 通过 |
| Repository smoke | `scripts/dev.sh smoke` | `testsong` 生成成功；`patch_id=testsong-6d0b984b`；16 pads；45 notes |

## 真实 API / Web 观察

启动命令：

```bash
env LMDJ_JOBS_ROOT=/tmp/lmdj-queue-evidence.Ix2lET \
  LMDJ_CORS_ORIGINS=http://127.0.0.1:5174 \
  apps/api/.venv/bin/uvicorn lmdj_api.app:app \
  --host 127.0.0.1 --port 8123

cd apps/web
env VITE_API_BASE=http://127.0.0.1:8123 \
  npm run dev -- --host 127.0.0.1 --port 5174
```

输入：

- `references/demos/lmdj-song-pipeline/output/testsong/input.wav`（32 秒）
- `/tmp/lmdj-queue-evidence-long.wav`（由上项循环到 120 秒，仅用于延长在途观察窗口）

### FIFO 与容量

在长任务 `c49ded56652b` 为 `separating` 时，通过同一 Web 任务面继续提交 `c56bfc58f27b`。浏览器实际显示：

```text
最大并发 1
正在处理 1
等待 1
c49ded56652b · separating
c56bfc58f27b · queued · 队列位置 1
```

随后前项完成，后项进入 `separating`；两项均保留文件名、Job ID、提交时间和状态。

### 刷新恢复

任务完成前后执行浏览器 reload。Web 从 `lmdj.upload-submissions.v1` 恢复本浏览器提交的任务，通过 `/jobs/{id}` 读取服务端状态；没有重新上传音频，也没有把服务器历史误当成账户级历史。

### submission 幂等

对已被 API 接受的 submission `0468af86-74e2-4f55-b219-194c6a34bfef` 重复执行：

```bash
curl -sS \
  -H 'Idempotency-Key: 0468af86-74e2-4f55-b219-194c6a34bfef' \
  -F 'file=@references/demos/lmdj-song-pipeline/output/testsong/input.wav;type=audio/wav' \
  http://127.0.0.1:8123/uploads
```

返回原 Job `c56bfc58f27b`，状态 `completed`，没有创建第二个 Job。

### API 重启

Job `be664c688746` 处于 `separating` 时停止 API，并以同一 Job root 重启。启动恢复将它持久化为：

```text
state=interrupted
error_code=service_interrupted
```

浏览器刷新后显示“服务中断”和重新选择源文件的指引，没有把它显示为 `Failed to fetch`。

### Patch 打开与播放入口

在刷新恢复后的任务列表点击 Job `4d80576784b9` 的 `Open Patch`：

- 通过既有 `/patch` 与 `/files/*` 路由加载；
- 进入 `lmdj.patch.v1` 的 16-pad Performance 工作台；
- 点击 Pad 1 成功触发 UI 交互，未出现新的浏览器运行时错误。

## 响应式与可读性

- 桌面和 `520 × 900` viewport 均实测。
- 窄屏容量指标与任务事实纵向堆叠，文件名和 Job ID 不截断。
- 实机检查发现并修复了两个单元测试无法覆盖的问题：`Open Patch` 深底深字，以及长 worker traceback 无限撑高卡片。最终按钮为高对比度，长错误限制在可滚动区域。

浏览器控制台只有开发环境 React DevTools 信息、缺失 `favicon.ico` 的 404，以及故障注入期间预期的 API connection-refused；Patch 加载与 Pad 点击没有产生新的运行时错误。

## 明确未覆盖的边界

- 队列仅为单 API 进程内的 FIFO；进程重启不会恢复 DSP 执行，而是明确终止为 `interrupted`。
- localStorage 只恢复当前浏览器自己提交的引用，不提供登录账户、跨设备或全局 Job 历史。
- 本切片没有加入鉴权、限流、取消、Redis/Postgres、对象存储、多 worker 或跨进程 durable workflow。
