# LMDJ 云端架构与 Infra 设计

日期：2026-07-06
状态：架构草案

## 背景

LMDJ 的产品方向是 AI-native sampler workstation。用户可以从两类入口开始：

```text
Idea
  -> AI 生成音乐材料
  -> Patchify
  -> Patch View

Uploaded Song
  -> 分析 / 分轨 / 切片 / 提取
  -> Patchify
  -> Patch View
```

这两条路径最终都应该落到同一个核心对象：可演奏、可编辑、可分享的 `Patch`。云端架构的首要目标不是马上做完整社区平台，而是先稳定支持：

- 上传或生成音乐材料。
- 异步处理重任务。
- 生成 `patch.json` 和相关音频资产。
- 给 Web / CLI 提供同一套访问接口。
- 为后续分享、remix、sample、fork 和 lineage 留出数据模型。

## 总体判断

早期不建议把产品后端拆成很多微服务。更合适的方式是：

```text
App Backend 合在一起
Audio / AI / Render Workers 分开
```

原因：

- `Project`、`Patch`、`User`、`Job`、`Community` 等产品对象强关联，过早拆微服务会增加协调成本。
- 音频处理、AI 生成、视频渲染都是长任务，不能阻塞主 API。
- 不同 worker 对 CPU / GPU / 内存的需求不同，需要独立扩缩容。
- Web 和 CLI 应该调用同一套 API，避免形成两套产品逻辑。

推荐第一版系统形态：

```text
Web App / CLI
  -> App Backend
  -> Job Queue
  -> Audio Worker / Generation Worker / Render Worker
  -> Object Storage
  -> Postgres
  -> CDN
```

## 参考项目边界

`lmdj-song-pipeline` 是高嘉丰提供的个人参考项目，用来证明“音频输入 / MusicGen 输出 -> samples + chart.mid + lanes.json + report.json”这条技术链路。它是重要的技术素材库，但不是 LMDJ 最终云端系统的源码边界。

后续设计应遵守：

- 可以复用其中已经验证过的音频能力：分轨、loop finding、切片、MIDI chart、validation、测试 fixture。
- 可以参考它的 package contract：`samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`、preview audio。
- 不默认继承它的目录结构、API 形态、CLI 形态、状态模型或最终 product contract。
- LMDJ 自己需要沉淀独立的 `Patch / Pad / Scene / Element` 产品对象。
- `Patchify` 应该被视为参考 pipeline 输出到 LMDJ 产品对象之间的 adapter layer，而不是简单给参考项目追加一个字段。

因此，云端实现时可以先把 `lmdj-song-pipeline` 作为 worker 内部依赖或可迁移代码来源；但 App Backend、Patch model、Job model、Storage model 和 Community model 应按 LMDJ 自身产品架构定义。

## 服务清单

### 1. Web App

Web App 是主要用户界面，负责：

- idea input。
- song upload。
- job progress 展示。
- Patch View。
- 8-pad Focus View / 16-pad Pro View。
- Scene Variation。
- AI Talk 入口。
- render / share 入口。
- remix / sample / fork 入口。

Web App 不应该直接处理音频重任务。它只负责上传、展示状态、播放资产、编辑 patch 状态，并调用后端 API。

### 2. CLI Client

CLI 面向专业用户、本地批处理和内部调试。它不应该绕过云端产品逻辑，而应该复用同一套 API。

可能命令：

```bash
lmdj upload song.wav
lmdj idea "make a cold late-night club patch"
lmdj jobs get <job_id>
lmdj patch download <patch_id>
lmdj patchify <song_id>
lmdj render <project_id>
```

CLI 可以后续支持本地 fallback，但第一版云端架构里，它应该是 API client。

### 3. App Backend

App Backend 是主产品后端。早期建议做成一个模块化 monolith，而不是拆成多个产品微服务。

负责：

- 用户、账号、权限。
- Project / Session / Patch / Scene / Element metadata。
- 上传任务创建。
- idea session 创建。
- job status 查询。
- patch 读取和保存。
- render 请求。
- share link 创建。
- remix / sample / fork 关系记录。
- lineage 查询。

核心 API 示例：

```http
POST /uploads
POST /ideas
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
GET  /projects/{project_id}
GET  /patches/{patch_id}
POST /patches/{patch_id}/remix
POST /elements/{element_id}/sample
POST /renders
GET  /shares/{share_id}
```

### 4. Job Queue

所有长任务都进入队列，不在 API request 中同步执行。

任务类型：

```text
upload-song
generate-from-idea
separate-stems
extract-elements
build-patch
render-song
render-share-video
```

可选实现：

- MVP：Redis Queue、RQ、Celery。
- 云上托管：SQS、Cloud Tasks、Pub/Sub。

第一版可以从 Redis queue 开始，等负载和失败恢复需求明确后再迁移到托管队列。

**幂等要求（2026-07-07 决策）：** 每个 job 类型必须声明重跑语义。音频/生成/渲染类 job 的基线规则是：同输入必须产生同 storage key 的产物，覆盖写安全（`patch_id` 内容派生正是为此设计）。worker 崩溃后重新投递同一 job 不得产生重复资产或错乱状态。重试上限与死信队列去向见"待决问题"。

### 5. Audio Pipeline Worker

Audio Worker 负责把已有音频变成 pipeline package 和产品 patch。

流程：

```text
input audio
  -> stems
  -> loop finding
  -> slicing
  -> sequencing
  -> validation
  -> Patchify
```

输出：

```text
samples/*.wav
chart.mid
lanes.json
report.json
patch.json
loop_preview.wav
render_preview.wav
```

这个 worker 应该和 App Backend 分开部署，因为它慢、吃资源，并且失败率高于普通 API。

### 6. AI Orchestrator

AI Orchestrator 是 LLM 决策层。早期可以作为 App Backend 的内部模块，但逻辑上应该独立。

负责：

- 理解用户自然语言 idea。
- 生成 creative brief。
- 生成 sound palette。
- 决定 generation plan。
- 决定 patch plan。
- 决定默认 pad mapping intent。
- 把用户后续 AI Talk command 转成结构化 action。

它不直接承担音频计算，而是调度 Generation Worker、Audio Worker、Patchify module 或后续编辑模块。

### 7. Generation Worker

Generation Worker 负责从 idea / creative brief 生成音乐材料。

可能流程：

```text
idea / brief
  -> rough song
  -> loops / samples / stems
  -> Audio Pipeline Worker
  -> Patchify
```

它可能需要 GPU，也可能先调用第三方模型/API。建议和 Audio Worker 分开，因为它的依赖、成本、扩缩容方式都不同。

### 8. Patchify Module / Service

Patchify 是核心 adapter layer：

```text
reference pipeline package
  -> product Patch
  -> Pads
  -> Scenes
  -> Elements
```

当前已确认落点（2026-07-07 修订）：

```text
packages/core-models/
  -> Patch / Pattern / Pad / Scene / Element 产品对象模型
  -> lmdj.patch.v1 JSON Schema（四方契约的机器可读来源）

packages/patchify/
  -> LMDJ-owned Patchify Core（纯 adapter，依赖 core-models）
  -> consumes reference pipeline package as input
  -> emits product patch.json
```

`references/demos/lmdj-song-pipeline/` 只作为参考 demo、fixture 来源或可迁移代码来源，不再作为正式 Patchify 功能的落点。`Patchify` 的职责是 LMDJ 自己的产品对象映射，而不是继承参考项目的最终格式。

第一版职责：

- 验证 `lanes.json`、`chart.mid`、`report.json`（以 demo 真实契约为准：lane 的 wav key 是 `sample`，`song_id` 取自 `report.json`）。
- 确认 sample files 存在。
- 确认 MIDI pitches 都能在 `lanes.json` 中找到。
- 解析 `chart.mid` 为 normalized pattern notes（`length_steps = beats × 4`）。
- profile 检测（v1 只支持 standard，ABC/DEF 包显式报 unsupported）。
- 映射默认 8-pad Focus View（trigger_group 语义，melody 第二候选 fallback 到 Lead/Vocal）。
- 输出 `patch.json`（`lmdj.patch.v1`，patch_id 内容派生，输出必须通过 JSON Schema 校验）。

### 9. Render / Export Worker

Render Worker 负责导出可传播资产。

输出类型：

- song audio。
- share video。
- cover image。
- preview clip。
- 未来的 performance replay。

它读取 project / patch / assets，然后把 render 结果写入 Object Storage。视频渲染和音频处理一样，不应该阻塞 App Backend。

### 10. Object Storage

音频和视频资产不进数据库，统一进入对象存储。

建议 bucket / prefix：

```text
raw_uploads/
generated_audio/
stems/
samples/
patches/
renders/
share_videos/
covers/
```

可选服务：

- AWS S3。
- Cloudflare R2。
- Google Cloud Storage。
- Supabase Storage。

前端播放、下载和分享应该通过 CDN 分发。

### 11. Postgres

Postgres 存产品数据、关系数据和 job 状态，不存大文件。

核心表（v1，2026-07-07 收缩）：

```text
users
sessions
projects
patches
elements
jobs
renders
shares
lineage_edges
permissions
```

其中：

- `patches` 可以存 `patch.json` 的 current version metadata，也可以只存 object storage key。
- `elements` 存 sample / loop / chop / stem / pattern 的 metadata 和 storage key（lineage 外键需要它，故 v1 保留）。
- `lineage_edges` 存 remix、sample、fork 关系。
- `jobs` 存异步任务状态、错误、进度和产物引用。
- **v1 不单独建 `pads` / `scenes` 表**：pads 和 scenes 随 `patch.json` 整体存储。在出现服务端 patch 编辑功能之前归一化它们，只会制造 `patch.json` 与表之间的双写一致性问题。

### 12. Realtime Status

用户生成或上传后，需要看到明确进度。

标准状态：

```text
queued
generating
separating
extracting
patchifying
rendering
completed
failed
cancelled
```

第一版可以使用 polling：

```http
GET /jobs/{job_id}
```

后续再升级为 SSE 或 WebSocket。

### 13. Community / Lineage

第一版不必实现完整 community feed，但必须提前定义 lineage 数据关系。

核心动作：

```text
Remix This
Sample This
Open Patch
Fork From Moment
```

Lineage 示例：

```text
Song A
  -> Element X
  -> sampled by Song B
  -> remixed into Project C
```

这部分是后续网络效应的基础：一个音色、loop、chop 或 patch 可以在不同作品之间流转。

## 数据流

### Uploaded Song To Patch

```text
Web / CLI upload
  -> App Backend creates upload + job
  -> raw file stored in Object Storage
  -> Job Queue dispatches Audio Worker
  -> Audio Worker runs pipeline
  -> Patchify writes patch.json
  -> artifacts stored in Object Storage
  -> metadata stored in Postgres
  -> client opens Patch View
```

### Idea To Patch

```text
Web / CLI idea input
  -> App Backend creates session + job
  -> AI Orchestrator creates creative brief
  -> Generation Worker creates audio materials
  -> Audio Worker / Patchify builds patch
  -> artifacts stored in Object Storage
  -> metadata stored in Postgres
  -> client opens Patch View
```

### Patch To Share

```text
Patch / Project
  -> user requests render
  -> App Backend creates render job
  -> Render Worker creates audio/video/cover
  -> output stored in Object Storage
  -> share record stored in Postgres
  -> CDN URL returned to Web / CLI
```

## 推荐阶段

### Phase 1: Cloud Patchify MVP

目标：证明云端可以把一首歌变成 patch。

范围：

```text
Web/CLI upload
  -> App Backend
  -> Job Queue
  -> Audio Worker
  -> patch.json
  -> download/open patch
```

必须完成：

- 文件上传。
- job 创建和状态查询。
- Audio Worker 跑 pipeline。
- `patch.json` 生成。
- artifacts 存储。
- 简单 patch 读取 API。

不做：

- 完整 AI idea generation。
- 完整社区。
- 完整视频分享。

### Phase 2: Idea To Patch

目标：接入 AI-native 入口。

范围：

```text
idea
  -> LLM brief
  -> generation worker
  -> patchify
  -> Patch View
```

必须完成：

- creative brief schema。
- AI Orchestrator。
- Generation Worker。
- idea job 状态。
- generated material 到 Patchify 的稳定接口。

### Phase 3: Share / Remix Network

目标：形成创作、分享、再创作循环。

范围：

```text
render song/video
  -> share
  -> remix/sample/fork
  -> lineage
```

必须完成：

- Render Worker。
- share link。
- `Remix This`。
- `Sample This`。
- `Fork From Moment`。
- lineage graph。

## MVP Infra 建议

如果要尽快上云，建议第一版使用：

```text
App Backend: FastAPI / Node.js
Queue: Redis + RQ/Celery 或 BullMQ
Worker: Python audio workers
DB: Postgres
Storage: S3/R2/GCS
CDN: Cloudflare 或云厂商 CDN
Deploy: Docker containers
```

更具体地：

- App Backend 可以先用 FastAPI，方便复用现有 Python pipeline。
- Audio Worker 继续用 Python。
- Generation Worker 可以单独容器化，方便接 GPU 或第三方 API。
- Render Worker 单独容器化，避免 ffmpeg/video 依赖污染主后端。
- Postgres 作为唯一关系数据库。
- Object Storage 作为唯一大文件存储。

## 关键架构原则

- 产品对象先合并，重计算能力先拆开。
- Web 和 CLI 共用同一套 API。
- 大文件不进数据库。
- 长任务必须异步。
- Pitch/sample truth 采用三段式模型（2026-07-07 决策）：
  1. v1 内 `lanes.json`/`chart.mid` 是 Patchify 的**输入 truth**（demo 契约，已冻结）；
  2. `patch.json` 生成之后即**产品侧唯一 truth**（含 normalized patterns/notes），下游任何消费方不得回读 `lanes.json` 或 `chart.mid`；
  3. 退出条件：`workers/audio/` 正式实现时直接产出 LMDJ 中间格式，demo 契约 loader 转入维护模式。
- 先把 Cloud Patchify 跑通，再做完整 AI idea generation。
- 先保留 lineage 数据结构，再做完整 community feed。

## 待决问题

- App Backend 使用 FastAPI 还是 Node.js。
- Queue 第一版使用 Redis-based queue 还是云托管队列。
- Object Storage 选 S3、R2、GCS 还是 Supabase Storage。
- `patch.json` 存数据库 JSONB，还是只存 object storage key。
- AI Orchestrator 是否第一版就单独部署。
- Generation Worker 第一版接第三方 API 还是自建模型。
- Share video 第一版是否进入 MVP。
- Job 重试上限、退避策略与死信队列去向（幂等基线已定，见 Job Queue 节）。
