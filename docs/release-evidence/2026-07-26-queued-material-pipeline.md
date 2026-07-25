# Queue + Material Pipeline v1 Integration Evidence

日期：2026-07-26
分支：`codex/queued-material-pipeline`

## 验证边界

本记录验证 `eb212c4f`（上传任务可见性/FIFO 队列）和 `2fa029af`
（Material Pipeline v1）组合后的交叉契约。它证明实现可集成，不代表
`materials-v1` 已通过发布晋升门槛。

## 自动化回归

在集成 worktree 的独立依赖环境中执行：

| 范围 | 结果 |
|---|---:|
| Core Models | 18 passed |
| Patchify | 23 passed |
| Audio Worker | 351 passed，3 个 Python 标准库弃用 warning |
| App API | 94 passed，1 个既有 Starlette/httpx 弃用 warning |
| Web | 165 passed |
| Web contract drift gate | 4 passed |
| Web production build | passed |
| Legacy `scripts/dev.sh smoke` | passed；`testsong-6d0b984b`，16 Pads，45 notes |

组合新增用例锁定：

- Material Job 处于 `extracting` 时占用唯一执行槽；
- 后续 Material Job 保持 `queued`，FIFO 位置为 `1`；
- submission 幂等命中原 Job，并保留首次选定的 `materials-v1`；
- API 重启把 `extracting` / `queued` Material Job 写为明确
  `interrupted`，同时保留 pipeline；
- Job 记录的 pipeline 与实际 runner 不一致时明确拒绝，不静默跑错链路。

## 浏览器闭环

使用本地 Web + API 和注入式 stage-aware Material fixture runner 验证组合 UI。
该 runner 只替代耗时的真实分离/提取模型；API、队列、Worker 状态、Patchify、
Patch 加载和 Web Audio 行为均走产品代码。

观察结果：

1. Material Job 状态按 `queued → extracting → completed` 可见，完成状态持久化
   `pipeline: materials-v1`。
2. 完成 Job 经 API 加载为固定 16 Pad，accepted 位置为 Kick A、Bass A、
   Phrase A、Kick B，其余位置保持真实 Empty。
3. 点击 Phrase A 后其状态为 selected；再点击 Kick A 后，Phrase A 回到 idle，
   Kick A 成为 selected，验证 full-mix Phrase 与普通素材的双向排他。
4. 两个未完成 Job 同时存在时，界面显示最大并发 `1`、正在处理 `1`、等待 `1`；
   第一条为 `extracting`，第二条为 `queued` 且队列位置 `1`。
5. 页面刷新后原文件名、Job ID、状态、容量和位置均恢复。
6. API 在这两条 Job 未完成时重启；刷新后两条都显示“服务中断”、
   `interrupted` 和可操作的重新提交说明，不继续伪装处理中。
7. `materials.json` 与 `separation.json` 公共文件路由均返回 `404`；
   Web 仍只通过 `patch.json` 和样本资产工作。
8. fixture Export 正确识别 Samples、MIDI 和 Timing；因 fixture runner 不提供
   真实 Stems/Key，状态如实为 partial，而不是伪报完整。

## 尚未关闭的发布门槛

以下项目不属于本次组合实现的自动化闭环，完成前默认 runner 必须继续保持
`legacy`：

- 固定真实曲库每首连续三次的模型级重复性；
- 新旧 pipeline 盲听与可演奏性对照；
- 实体 8-Pad Bank A/B 与原生 16-Pad Controller；
- 非开发者无口头指导完成 Upload → Play → Export；
- Creator Export 导入 Ableton Live 的真实 Smoke；
- 基于上述证据冻结生产 separator/checkpoint 与 extraction config。
