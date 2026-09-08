# LMDJ Web → API 接入设计

日期：2026-07-10
状态：已评审设计（brainstorming 流程产出）
落点：`apps/web/`（新增 `src/api/`，改 `src/ui/App.tsx` 与 landing）

## 定位

把 `apps/web` 的 Patch View 从"只能拖本地目录"扩展为"填 API 地址 → 传歌 → 30 秒后玩到 patch"。这是让整条云链路（upload → job → patch）在浏览器里对用户首次可见闭环的一步。**与拖目录/示例并存**，不替换。

## 已确认的设计决策

| 决策点 | 结论 |
|--------|------|
| API 地址 | landing 上一个文本输入框，默认 `http://localhost:8000`（可改） |
| 进度 UI | 新增 `uploading` 态：状态行按 `queued → separating → patchifying → completed` 逐阶段显示，已过变暗、当前高亮；`failed` 显 error |
| 架构 | 方案 A：新增 `src/api/client.ts`（纯 fetch，无 React）+ App 加 `uploading` 态，三条加载路复用同一 `loadPatch` |

## 架构

```text
src/api/client.ts   纯 fetch 客户端（无 React，可 mock fetch 独立测）
src/ui/App.tsx      状态机加 uploading 态 + landing 第三入口
                    engine / PadGrid / StepGrid / loader 全不改
```

三条加载路（拖目录 / 示例 / API）都汇成 `Map<path, ArrayBuffer>` → 调**同一个 `loadPatch`** → 同构 `PatchBundle` → 同一 engine。契约纯度延续：前端仍只认 patch.json + samples，不碰 lanes/chart。

## apiClient 与数据流

```text
landing "传歌"（base + file）
  → uploadSong(base, file)          POST {base}/uploads (multipart "file") → {job_id}
  → App 切 uploading 态
  → pollJob(base, job_id, onState)  GET {base}/jobs/{id} 每 1500ms
       每次回调 onState(status) 更新 UI；completed → 继续；failed → 抛带 error
       总超时 300s → 抛超时错
  → fetchPatchBundle(base, job_id, decode)
       GET {base}/jobs/{id}/patch → patch.json bytes
       解析 elements[].source_path，对每个 GET {base}/jobs/{id}/files/{source_path}
       缺失的 sample（非 200）跳过（loader 的 missing 模型处理），不阻塞
       拼 Map{ "patch.json": bytes, <source_path>: bytes... } → loadPatch(map, decode)
  → App 切 loaded，engine.load(bundle)
```

### `src/api/client.ts` 接口

- `normalizeBase(base: string): string`——去尾斜杠；空 → `http://localhost:8000`。
- `uploadSong(base: string, file: File): Promise<string>`——POST multipart，返回 `job_id`；非 2xx 抛 `ApiError`。
- `pollJob(base, jobId, onState?, opts?): Promise<JobStatus>`——间隔 1500ms、总超时 300s（可注入以便测试用短值）；每轮 `onState(status)`；`state==="completed"` 返回，`"failed"` 抛 `ApiError(带 status.error)`，超时抛 `ApiError`。
- `fetchPatchBundle(base, jobId, decode): Promise<PatchBundle>`——拉 patch.json + samples 拼 Map，调 `loadPatch`。
- `type JobStatus`（结构化：`{state, error, patch_id, ...}`，前端只读用到的字段）；`class ApiError extends Error`。

## UI

- **landing**：现有 DropZone（拖放 + "加载示例"）下方加一块 "从 API 加载"：
  - API 地址输入框（`defaultValue="http://localhost:8000"`）
  - 文件选择（`<input type="file" accept="audio/*">`）
  - "传歌" 按钮（无文件时禁用）
- **uploading 态**：ASCII 风，四阶段 `queued / separating / patchifying / completed` 横向或纵向列出，已过阶段变暗（`--green-dim`）、当前高亮（`--green`）；底部 spinner 或 `…`。`failed` → 红字（`--red`）显 error + "返回" 按钮回 landing。
- 状态色沿用既有规范（active green / warning red / disabled gray）。
- **loaded 态不变**：进入现有 workstation 视图。

## 错误处理

| 情况 | 行为 |
|------|------|
| 上传请求失败（网络 / CORS / 非 2xx） | 留在 landing，红字提示（含 base URL 排查提示） |
| job `failed` | uploading 态显 `status.error` + "返回" |
| 轮询超时（>300s） | uploading 态显超时提示 + "返回" |
| patch.json fetch 失败 / 非法 | 走现有 `PatchValidationError` → landing 错误面板 |
| 某 sample fetch 非 200 | 该 element 进 `missingElementIds`（loader 既有模型），pad/StepGrid 标红，不阻塞 |

## 测试

- **Vitest（mock `fetch`，零真实后端）**：`normalizeBase` 边界；`uploadSong` 发对 multipart、非 2xx 抛错；`pollJob` 轮询到 completed / failed 抛 error / 超时抛错（注入短 interval+timeout + 假 fetch 序列）；`fetchPatchBundle` 组 Map 并产出与拖目录同构的 bundle，含"某 sample 404 → 进 missingElementIds"。
- **React Testing Library（注入 fake client）**：landing 的 API 面板渲染 + 无文件禁用；`uploading` 态阶段高亮（queued/separating/... class）；`failed` 分支显 error + 返回回 landing；completed → 进 loaded（pad-grid 出现）。
- **不做**：真实后端 e2e（手动冒烟：起 apps/api uvicorn + apps/web dev，浏览器填 localhost:8000、传 demo `output/testsong/input.wav`，30s 后玩到 patch）；contract-sync 测试不受影响（已有）。

## 范围外（v1 不做）

engine / PadGrid / StepGrid / Inspector / loader 的任何改动、ideas/生成入口、鉴权、分享/remix、多 job 历史列表、上传进度条百分比、断线重连、生产 API 地址配置（env 覆盖属后续）。

## 成功标准

1. `npm run dev` + 本地 `apps/api` 起服务；landing 填 `http://localhost:8000`、选 demo `input.wav`、点"传歌"；
2. uploading 态逐阶段推进（queued→separating→patchifying），约 30s 后自动进 workstation；
3. 进入的 patch 与该歌一致（pads/notes 与直接 CLI patchify 同款），可播放/静音/触发；
4. 后端 `failed` / 网络错 / 超时都有可读提示且能返回 landing，无白屏；
5. 拖目录、示例两条老路不受影响；全部单测绿且不依赖真实后端。
