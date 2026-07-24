# Stage 1 Creator Core + Workspace UI Release Evidence

执行日期：2026-07-25

分支：`codex/align-creator-ui-spec`

验证基线：`0caa88a7`（Task 1–9）

## 结论

**NOT READY — PR Ready 被阻塞。**

自动化代码门禁全部通过，固定 16 Pad、响应式 Workbench、Creator Export
以及同一 Job 内重复下载的字节确定性均有证据。但同一固定音频连续三次
真实处理产生了三个不同的 `patch_id`，违反“三次 patch_id 必须一致”的
release gate。实体 MIDI、Ableton Live 和无指导用户测试也因缺少设备、
软件和参与者而未执行；这些项目必须完成后才能把 PR 标为 Ready。

## 环境与方法

- macOS `26.5.2`（Build `25F84`）。
- Google Chrome `150.0.7871.182`。
- 固定音频：
  `references/demos/lmdj-song-pipeline/output/testsong/input.wav`。
- Live API：`uvicorn lmdj_api.app:app`，使用默认
  `DemoPipelineRunner` 和生产 `POST /uploads`、Job、Patch、Export 路由；
  Job 数据根为临时目录 `/tmp/lmdj-stage1-live-jobs.O4rtsK`。
- Key 分析：通过 `scripts/dev.sh setup-pfs` 创建的隔离
  `workers/audio/.venv-pfs`。
- `system_profiler SPUSBDataType` 未发现 MIDI/controller；
  `/Applications` 未发现 Ableton Live。

shell helper 的自动验证使用本地 HTTP fixture server，只验证
`creator-smoke` 的成功/失败契约；下面“三次真实运行”的证据不使用 fixture。

## 自动门禁

| 门禁 | 结果 | 证据 |
|---|---|---|
| `scripts/tests/test_creator_smoke.sh` | PASS | 成功输出六个要求字段；15-Pad contract、HTTP 500、不同 ZIP hash 均非零退出 |
| `scripts/dev.sh test` | PASS | core-models `7 passed`；Patchify `18 passed` |
| Worker 全套 | PASS | 安装声明的 `[metrics]` extra 并使用 `metrics-constraints.txt` 后，`327 passed` |
| API 全套 | PASS | `64 passed`；1 条既有 Starlette/httpx deprecation warning |
| `npm run check-contract` | PASS | `4 passed` |
| `npm test` | PASS | `21` files、`146 passed`；覆盖 Loaded 默认 Performance、Source / Performance 真实内容切换与 preflight probe timeout 呈现 |
| `npm run test:e2e` | PASS | 8 个容器边界 + 五个 viewport 交互 + 两个相反侧 drawer + 一个手机状态保持，`16 passed` |
| `npm run build` | PASS | TypeScript + Vite production build |

Worker 在隔离 worktree 中使用以下等价命令，以显式提供仓库内不写入
package metadata 的 path dependencies：

```bash
PYTHONPATH=workers/audio:packages/core-models:packages/patchify \
  /Users/endaye/Projects/lmdj/workers/audio/.venv/bin/python \
  -m pytest workers/audio/tests -q
```

## 三次真实 Creator smoke

启动命令：

```bash
PYTHONPATH=apps/api:workers/audio:packages/core-models:packages/patchify \
LMDJ_JOBS_ROOT=/tmp/lmdj-stage1-live-jobs.O4rtsK \
  /Users/endaye/Projects/lmdj/apps/api/.venv/bin/python \
  -m uvicorn lmdj_api.app:app --host 127.0.0.1 --port 8765
```

每次执行：

```bash
LMDJ_API_BASE_URL=http://127.0.0.1:8765 \
  scripts/dev.sh creator-smoke \
  references/demos/lmdj-song-pipeline/output/testsong/input.wav
```

| Run | job_id | patch_id | Pads | Export SHA-256 A | Export SHA-256 B | 单 Job 确定性 |
|---|---|---|---:|---|---|---|
| 1 | `40e5f4e7f582` | `40e5f4e7f582-b3f6cb0b` | 16 | `ed122516319ccfd55317278bcf034039b0a8ef16c5f91aec4836a93d4132d002` | `ed122516319ccfd55317278bcf034039b0a8ef16c5f91aec4836a93d4132d002` | PASS |
| 2 | `c38da0338c2f` | `c38da0338c2f-99735e74` | 16 | `21243d0eaf6c53aac3e84bd2077b481e657db1dd5a45b523b3b6b02af43e6ff1` | `21243d0eaf6c53aac3e84bd2077b481e657db1dd5a45b523b3b6b02af43e6ff1` | PASS |
| 3 | `9f427e4c3b23` | `9f427e4c3b23-9cb2e79c` | 16 | `9466ed64e054de5fcfbebf474620a29b5b08f576addaa855962e15c1241234a7` | `9466ed64e054de5fcfbebf474620a29b5b08f576addaa855962e15c1241234a7` | PASS |

跨运行 Repeatability：**FAIL**。

- full `patch_id` 包含每次随机生成的 Job ID，因此按当前命名设计本身就无法
  在三个 Job 间相同。
- 三个内容 hash 后缀 `b3f6cb0b`、`99735e74`、`9cb2e79c` 也不同，不是
  只有前缀差异。
- Run 1 的 `lanes.json` SHA-256 为
  `dadf39a091d7e602c8b13e3e2bd22812cdd0cb26aa2ec9a42fbdc5e80626384a`，
  lanes 为 `drum_low / drum_high / bass / melody_a`。
- Run 2 与 Run 3 的 `lanes.json` SHA-256 都是
  `68e5cf2c34da47ac48f206f9775804638727a1065b053af0c527a14212f24abd`，
  lanes 为 `kick / snare / hat / bass / melody_a`；但 `chart.mid`
  SHA-256 分别是
  `77a0124a2c72b01336bd74df0c67fcdf4175dbcf9ffb8fe2f1f45ad19d225928`
  和
  `92dd237993525f2d96e1f5733608402054c2c25c63f71123efc605297b4dad8b`。

后续需要分别解决 patch identity 的 Job-ID 耦合和 pipeline 的跨运行输出
非确定性；本 evidence task 不修改音频算法。

## Workspace UI 自动验收

`apps/web/e2e/workbench-responsive.spec.ts` 在真实 Chromium 页面上执行 16
个测试：先在同一个宽 viewport 内把 Workbench inline content box 精确设为
`1280`、`960/1279`、`600/959`、`360/599`，并额外把 Workbench 嵌入
`676px` 窄容器，验证响应式只取决于容器而不是设备或 viewport；随后对五个
evidence viewport 执行 Pad 几何、Inspector 交互状态和 reduced-motion
断言，并以两个相反侧 drawer case 和一个手机 Sheet case 验证触发反馈与状态保持：

| Viewport | Grid | 外围结构 | Inspector 行为 | 结果 |
|---|---:|---|---|---|
| [`1440×900`](artifacts/2026-07-24-stage1/workbench-loaded-1440x900.png) | 8×2 | 左侧文字栏 + Canvas + 右侧常驻栏 | 常驻且不遮挡 Pad | PASS |
| [`1280×720`](artifacts/2026-07-24-stage1/workbench-loaded-1280x720.png) | 8×2 | 实测 shell content `1250px`：左侧图标栏 + Canvas | 可访问 drawer | PASS |
| [`1024×768`](artifacts/2026-07-24-stage1/workbench-loaded-1024x768.png) | 8×2 | 左侧图标栏 + Canvas | 可访问 drawer | PASS |
| [`768×1024`](artifacts/2026-07-24-stage1/workbench-loaded-768x1024.png) | 4×4 | Canvas + 底部工具栏 | 覆盖式 drawer | PASS |
| [`390×844`](artifacts/2026-07-24-stage1/workbench-loaded-390x844.png) | 4×4 | 紧凑 Top Bar + 底部 mode bar | 全高 Sheet | PASS |

两个 4×4 viewport 的 row-gap 与 column-gap 相等。五个 viewport 都验证了
16 Pad 数量、Pad 之间不重叠、Pattern 顺序、关闭 drawer / Sheet 后的
Canvas 边界、Status 边界和最后一个 Pad 可见性。窄屏 Inspector 打开时按
spec 覆盖 Canvas，但 `600–1279px` drawer 会按所选 Pad 的列从相反侧打开，
宽度不超过容器 50%，因此不会盖住当前 selected / playing 反馈；全宽 Sheet
仅用于 `360–599px`。自动化另行验证显式 toggle 的
`aria-expanded` / `aria-controls`、图标模式的可访问名称、背景区域
`inert`、Inspector 内 Tab / Shift+Tab focus trap，以及 Escape、backdrop、
Close button 三种关闭路径和焦点归还。键盘与 MIDI 使用同一 trigger callback，
会先同步当前 Pad / Inspector，再触发 AudioEngine。`npm test` 同时覆盖 Source、
Processing、Failed、Loaded 与 Export Checklist 的层级、状态文字和共享
视觉 token。CreatorToolRail 测试确认没有 Generate、Line-in、Chop、
AI Preview、Take 或 Pattern A–D 伪交互入口。

Loaded Workbench 默认进入并高亮 `Performance`，中央区域显示 Pattern、MIDI
与 16 Pad 乐器。切换到 `Source` 后，中央区域和 Inspector 都改为真实的
“已加载来源”上下文，显示已知的来源类型、API 文件名或 package 类型、
Patch ID、16 Pad contract、可播放/缺失音频资产；不会继续显示 Performance
内容，也不会仅改变高亮。切换模式本身不卸载 Patch，返回 `Performance`
后 Pad selection 与播放状态仍保留；只有显式点击“更换音频”才返回 Upload。
E2E 在手机工作台中验证了上述模式内容差异与状态保持。

以上链接是本轮在对应 viewport 设置下、真实 Loaded Workbench 页面生成的
Playwright 截图。`1440×900` 与 `1280×720` 保存 viewport 画面；
`1024×768`、`768×1024`、`390×844` 因页面高度超过 viewport 而保存
full-page 画面，以保留 Pattern、16 Pads、底部 mode bar（适用时）和
Status Bar。窄屏截图保持 Inspector 关闭，避免用有意的 modal 覆盖遮住
instrument；drawer / Sheet 的打开、内容可访问性与关闭路径由上述真实浏览器
测试记录。截图与可重复的几何/状态断言共同构成本轮 UI evidence。

## MIDI、音频、Export 与 Ableton 验收

`NOT RUN` 按 release gate 视为未通过；不会用单元测试替代实体设备、听感、
DAW 或真人任务证据。

| 验收项 | 状态 | 证据 / 原因 |
|---|---|---|
| 16-pad controller Note `36..51` → Pad `0..15` | NOT RUN / FAIL | 未发现实体 MIDI controller；仅映射单测通过 |
| 8-pad Bank A → Pad `0..7` | NOT RUN / FAIL | 未发现实体 MIDI controller；仅映射单测通过 |
| 8-pad Bank B → Pad `8..15` | NOT RUN / FAIL | 未发现实体 MIDI controller；仅映射单测通过 |
| 键盘 `1..8` / `Q..I` 固定映射且不受 MIDI Bank 影响 | PASS (automated) | Web MIDI / App Vitest 覆盖 |
| 有素材 Pad 发出正确声音 | NOT RUN / FAIL | 无实体 controller + 监听验收 |
| empty Pad 无声且无异常 | PASS (automated only) | Web Audio / Pad action tests；未做实体 controller 复核 |
| ExportChecklist 显示 Ready / Review / Missing / Partial；必需项缺失不下载伪 ZIP；下载名使用 Patch ID | PASS (automated) | Web `ExportChecklist` / App 与 API 409 测试 |
| ZIP 中 Stems、Samples、MIDI、Manifest 可导入 Ableton Live | NOT RUN / FAIL | `/Applications` 未安装 Ableton Live |
| 按 Manifest BPM 设置工程后可继续编排 | NOT RUN / FAIL | `/Applications` 未安装 Ableton Live |
| 非开发者无口头指导完成 Upload、MIDI 演奏、Export | NOT RUN / FAIL | 本轮没有招募测试参与者 |

## Ready 阻塞项

1. 修复同一音频跨 Job 的 patch identity 与 pipeline 输出非确定性，重新跑三次，
   要求三个 full `patch_id` 一致。
2. 使用实体 16-pad 与 8-pad controller 完成 Note、Bank、声音和 empty Pad 验收。
3. 在 Ableton Live 导入 Creator ZIP 的 Stems、Samples、MIDI、Manifest，
   按 Manifest BPM 继续编排。
4. 由至少一名非开发者无口头指导完成 Upload、MIDI 演奏和 Export。

上述任一项未通过，PR 都不得标记 Ready。
