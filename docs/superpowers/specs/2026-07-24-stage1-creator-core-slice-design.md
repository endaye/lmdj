# LMDJ Stage 1 Creator Core 首条纵向切片设计

日期：2026-07-24

状态：产品范围已确认；本次 UI 整合待用户书面复核（2026-07-24）

上游依据：[LMDJ 软件 MVP Stage 1–4 与团队协作 Memo｜2026-07-18](https://fcn8wuu8uotg.feishu.cn/docx/ZK5eduti6oE9Dox8Pkbc8r0vnPb)（`approved-for-planning`，读取 revision 63）

UI 规范：[LMDJ Stage 1 Creator Workspace UI 设计](./2026-07-24-stage1-creator-workspace-ui-design.md)。本文不重复定义布局、视觉、响应式、Pad 状态或页面状态；UI 实现与验收直接采用该文档。

## 1. 定位

这条切片把当前已运行的“上传歌曲后得到 8-pad Patch View”推进为首个可由 DAW 创作者验收的 Creator Core 闭环：

```text
Upload WAV/MP3
  → Preflight Validation
  → Existing Audio Pipeline
  → Instrument-first Creator Workspace
  → 16 Data Pads / 16-position UI
  → Keyboard / Generic MIDI Play
  → Creator Export ZIP
  → Ableton Live Smoke Test
```

它验证的是“用户拥有的音频能否成为 16-slot Playable Patch，并作为完整素材包进入 DAW 继续制作”，不是生成入口、完整 Sampler 或完整 DAW。

## 2. 已确认的产品决策

| 决策点 | 本切片结论 |
| --- | --- |
| 有效 Pad 数 | 固定 16 个数据 Pad，索引为 `0..15` |
| 空槽 | 未分配素材的位置也是 `patch.pads[]` 中的真实 Pad，使用 `action: "empty"` |
| UI 设计 | 直接采用 Creator Workspace UI Design Spec：Instrument-first Canvas、Pattern 在上、16-pad 在下、桌面 8×2、窄屏 4×4 |
| Patch 契约 | 在首条切片内原子收紧 `lmdj.patch.v1`：`pads` 必须恰好 16 项，并同步所有消费者和 fixture |
| MIDI | 是本切片验收项；键盘只是备用输入 |
| 8-pad Controller | 使用 Bank A/B 覆盖 `0..7` 和 `8..15` |
| 键盘 | 直接映射 16 个逻辑位置：顶排 `1 2 3 4 5 6 7 8`，底排 `Q W E R T Y U I` |
| Export | 通用 ZIP + 明确 Manifest；不生成 `.als`、Logic、FL Studio 等专有工程文件 |
| 首个 DAW | Ableton Live，只做真实导入 Smoke Test |
| 执行顺序 | 先完成 Upload → Play → Export；Prompt、Agent Orchestration、AI Variation 后置 |

## 3. 方案比较

### 3.1 Pad 扩展

**采用：固定 16 个数据 Pad + UI Design Spec 的 PadMatrix16。**

- 数据、Scene、输入映射和 UI 共享同一组 `0..15` 索引；空槽是明确的产品状态，不存在 UI 合成数据。
- UI 的信息架构、8×2 / 4×4 响应式、正方形 Pad、视觉 token、状态、动效和可访问性全部由 UI Design Spec 定义，本文不维护第二份规则。
- 代价：需要原子更新 Patchify、Schema、Web fixture、输入映射和测试。

**不采用：8 个数据 Pad + 8 个 view-only UI 占位。**

- 这会让屏幕上的后八个位置没有对应产品对象，数据、输入和 UI 无法保持一致。

**不采用：可变长度 Pad 数组。**

- 可变长度会迫使每个消费者自行补槽或截断，无法形成稳定的 8×2 产品契约。

### 3.2 Export

**采用：开放文件 ZIP。**

- 能被不同 DAW 使用，容易检查内容完整性和版本，且不绑定任何私有工程格式。

**延后：直接生成 `.als` 或其他原生工程。**

- 专有格式兼容和版本测试会把本切片变成 DAW 工程转换项目。

**不采用：只保留现有逐文件下载端点。**

- 这不能形成一次完整、可移交、可验收的 Creator Export Pack。

### 3.3 MIDI

**采用：16-pad 直接映射 + 8-pad Bank A/B + MIDI Learn。**

- 16-pad Controller 默认将 Note On `36..51` 映射到 Pad `0..15`。
- 8-pad Controller 学习八个实体 note number；Bank A 映射 `0..7`，Bank B 映射 `8..15`。
- 用户可进入 MIDI Learn；完整映射成功后保存在浏览器 `localStorage`。
- 键盘不使用 Bank：`1 2 3 4 5 6 7 8` 直接触发 `0..7`，`Q W E R T Y U I` 直接触发 `8..15`。

**不采用：只支持键盘。**

- 不满足 Stage 1 对通用 MIDI Pad 的明确验收。

**不采用：只映射前八个 Pad。**

- 这会让 `8..15` 的数据 Pad 无法通过已经确认的通用 8-pad Controller 访问。

## 4. 当前基线与保留边界

保留现有链路：

```text
apps/web
  → POST /uploads
  → apps/api JobExecutor
  → DemoPipelineRunner
  → packages/patchify
  → lmdj.patch.v1
  → apps/web loadPatch
```

本切片不等待多 Separator 最终选型，也不把 `PipelineFromStemsRunner` 晋级生产设为前置条件。Separator benchmark 和 timing analysis 继续作为 Stage 1 的技术风险消除工作，但不得阻塞固定素材的 Creator 闭环验收。

契约纯度保持不变：Web、Export Builder 和其他消费者以 `patch.json` 为产品真相；只有 Worker/Patchify 适配层可以读取 pipeline package 内的 `lanes.json`、`chart.mid` 和 `report.json`。Audio Worker 在 Patchify 后额外写出内部的 `lmdj.creator-export-source.v1`，显式登记可导出的文件和音乐元数据；Export Builder 不回读 demo contract 补数据。

## 5. 组件与职责

### 5.1 Upload Preflight

`apps/api` 在提交 Job 前完成：

- 只接受 WAV 和 MP3；
- 默认最大文件大小 `200 MiB`；
- 默认最大时长 `600 秒`；
- 使用内容探测确认文件可解码，不只相信文件名；
- 大小超限返回 HTTP `413`；
- 不支持或损坏的音频返回 HTTP `415`；
- 时长超限返回 HTTP `422`；
- 被拒绝的文件不创建 Job，不进入 `queued`。

限制值通过环境变量覆盖，但上述值是无配置时的产品默认值。

### 5.2 Pad 数据契约与 UI 规范

`patch.json` 固定包含 16 个 Pad。Patchify 和 Web 使用相同索引：

- `0..15`：全部由 `patch.pads` 驱动；
- 未分配素材的位置使用 `action: "empty"`，由既有 no-op 规则处理；
- UI 不补齐、不截断、不生成合成 Pad；
- `Scene.pad_indexes` 包含 `0..15`；
- 不接受 8-pad 旧 Patch 作为 Stage 1 正式输入；producer、fixtures 和消费者必须原子迁移；
- empty 状态不宣称拥有可播放素材。

当前 standard profile 保留既有前八个槽位语义；若 pipeline 没有更多可映射素材，索引 `8..15` 仍以真实 empty Pad 输出。后续可以在不改变数组形状的前提下逐步填充。

所有 UI 要求直接采用 UI Design Spec，尤其是：

- Instrument-first Canvas，Pattern Surface 在 PadMatrix16 上方；
- 桌面 8×2、600–959px 为 4×4、每个 Pad 保持 1:1；
- Pad 顺序固定 01–16，视觉位置与数据索引一一对应；
- Creator Tools、Context Inspector、Status Bar、Pad 状态、动效、响应式和可访问性不在本文重复定义；
- 本切片只启用 Upload、Processing、Patch Ready、Quality Needs Review、Failed 和 Creator Export 所需能力；Generate、Line-in、Chop 编辑、AI Preview、Take 保持后置。

### 5.3 MIDI Input

新增独立的浏览器 MIDI 适配层，不把 Web MIDI 事件处理写进 React 组件或 `AudioEngine`：

```text
Web MIDI Note On
  → MidiInput adapter
  → note-to-pad mapping
  → onTrigger(padIndex)
  → AudioEngine.triggerPad(padIndex)
```

规则：

- 只处理 command 为 Note On 且 velocity `> 0` 的消息；
- Note On velocity `0` 按 Note Off 处理，不触发；
- 支持触发 `0..15`；empty/reserved Pad 继续安全 no-op；
- 8-pad Controller 的 Bank A/B 分别增加偏移 `0` 和 `8`；
- 键盘按 UI Design Spec 直接覆盖 16 个位置，不与 MIDI Bank 联动；
- 默认监听用户授权后可用的全部 MIDI input；
- 设备断开时显示非阻塞状态，键盘和鼠标仍可用；
- 浏览器不支持 Web MIDI 或用户拒绝权限时给出明确提示，不伪装为已连接；
- MIDI Learn 未形成一套完整的 16-pad direct mapping 或 8-pad banked mapping 前，不覆盖上一次有效映射。

### 5.4 Music Metadata

Creator Export Manifest 必须包含 BPM、Key、拍号和 Loop 元数据：

- BPM 使用 `patch.bpm`；
- 拍号在 V1 明确记录为固定 `4/4`，来源标记为 `fixed-v1`；
- Loop 记录 `loop_seconds`、`length_steps`、`beats` 和 `bars`；
- Key 由 Audio Worker 的独立 metadata analysis 产出，包含 `value` 和 `confidence`；
- Key 分析失败时 Export 状态为 `partial`，UI 必须显示缺失项，不能把它标成完整成功。

Key analysis 在 `PipelineFromStemsRunner` 的 `.venv-pfs` 子进程边界运行，避免把 librosa/numpy DSP 依赖带入 Audio Worker 主包或 `apps/api`。Key metadata 是 Export 产物，不加入 `lmdj.patch.v1` 的必填字段。

### 5.5 Export Source Inventory

Audio Worker 在 Patchify 成功后生成 `export-source.json`（`lmdj.creator-export-source.v1`）。它只包含 Job 内相对路径和结构化元数据：

- `patch`: `patch.json`；
- `stems`: Runner 实际产出的 Stem 列表；
- `samples`: 从 Patch Elements 的 `source_path` 得到的素材列表；
- `midi`：从 Patch Pattern `source.path` 得到的 MIDI 列表；
- `music`: BPM、Key、拍号和 Loop；
- `warnings`: Runner 缺失可选 Stem 或 metadata 退化原因。

生成 inventory 时允许 Worker/Patchify 适配层读取 legacy package；生成之后，API 只消费 `patch.json`、`export-source.json` 和其中明确引用的文件。

### 5.6 Creator Export Builder

`apps/api` 提供 `GET /jobs/{job_id}/export`。Builder 在 Job 已完成后根据 `export-source.json` 从合法 package 目录创建确定性的 ZIP：

```text
creator-export-{patch_id}.zip
  manifest.json
  patch.json
  stems/
    drums.wav
    bass.wav
    vocals.wav
    other.wav
  samples/
    ...
  midi/
    chart.mid
```

若当前 Runner 没有独立 `vocals.wav`，Manifest 必须按真实存在的文件列出，不生成假 Stem。`manifest.json` 使用 `lmdj.creator-export.v1`，至少包含：

```json
{
  "schema": "lmdj.creator-export.v1",
  "status": "complete",
  "patch_id": "testsong-ab12cd34",
  "music": {
    "bpm": 89.1,
    "key": {"value": "A minor", "confidence": 0.72},
    "time_signature": {"numerator": 4, "denominator": 4, "source": "fixed-v1"},
    "loop": {"seconds": 10.6696, "steps": 64, "beats": 16, "bars": 4}
  },
  "files": {
    "stems": [],
    "samples": [],
    "midi": ["midi/chart.mid"],
    "takes": []
  },
  "warnings": []
}
```

每个文件条目包含 ZIP 内相对路径、字节数和 SHA-256。路径必须从 Job package 根目录解析并通过 traversal guard。ZIP entry 按相对路径稳定排序并使用固定时间戳，使同一 Job 重复构建得到相同字节。

完整性规则：

- `patch.json`、至少一个 sample、`chart.mid`、BPM、Key 和 Loop 元数据均存在时为 `complete`；
- 缺少可选 Stem 可以产生 warning，但必须忠实列出；
- 缺少 Key、MIDI、全部 Samples 或 Patch 时为 `partial`，端点返回 HTTP `409` 和结构化缺失项，不提供一个被标成成功的 ZIP；
- ZIP 文件名和 Manifest 不包含用户原始绝对路径。

### 5.7 Web Export UI

Creator Export 使用 UI Design Spec 的 `ExportChecklist`，不降级为单一成功 Toast。已加载 API Job 的工作台显示“导出 Creator Pack”入口：

- complete：下载 ZIP；
- partial：逐项显示 Ready / Review / Missing 和缺失项，当前切片不下载被标成成功的部分 ZIP；
- 本地拖放或内置示例没有 Job ID 时不显示远端导出按钮；
- 下载失败不卸载当前 Patch，也不停止演奏。

## 6. 数据流

```text
WAV/MP3
  → API size/container/duration preflight
  → Job
  → existing pipeline + Patchify
  → patch.json + export-source.json + samples + stems + chart.mid + music metadata
  → Web loads patch.json
  → keyboard/mouse/MIDI trigger active pads
  → Export Builder validates package
  → manifest.json + deterministic ZIP
  → Ableton Live import smoke
```

## 7. 错误处理

| 场景 | 产品行为 |
| --- | --- |
| 文件过大 | 上传前置失败，HTTP 413，显示最大值 |
| 格式损坏或不支持 | 上传前置失败，HTTP 415，显示支持 WAV/MP3 |
| 时长超限 | 上传前置失败，HTTP 422，显示最大秒数 |
| Pipeline 失败 | 保持现有 `failed` Job 状态和明确错误 |
| 浏览器无 Web MIDI | 显示不支持；键盘/鼠标仍可用 |
| MIDI 权限拒绝 | 显示未授权；不反复自动弹权限请求 |
| MIDI 设备断开 | 显示断开；不影响已加载 Patch |
| Export 缺少必需项 | HTTP 409 + 缺失项；不下载伪成功 ZIP |
| ZIP 下载失败 | 保留当前工作台和 Patch，允许重试 |

## 8. 测试与验收

### 8.1 自动测试

- API：WAV/MP3 成功；超过 `200 MiB`；超过 `600 秒`；损坏音频；伪造扩展名。
- Contract：`patch.pads` 恰好 16 项、索引连续且唯一；unused slot 为真实 `empty` Pad；Scene 覆盖 `0..15`。
- Pad UI：执行 UI Design Spec §13 的组件、响应式、可访问性测试；渲染 `patch.pads` 的 16 项且顺序一致，不生成 view-only Pad，empty Pad no-op。
- MIDI adapter：16-pad direct、8-pad Bank A/B、默认映射、velocity 0、未知 note、learn 完成、learn 中断、设备断开、权限拒绝。
- Export Builder：ZIP 文件清单、SHA-256、稳定排序、路径穿越、缺少 Key/MIDI/Sample、只列真实 Stem。
- Web：Pattern 位于 PadMatrix16 上方；API Job 显示 ExportChecklist；local/example 不显示远端导出；409 显示缺失项；下载失败保留 loaded 状态。
- Contract：`npm run check-contract` 继续通过；`lmdj.patch.v1` 无漂移。

### 8.2 Release Evidence

使用同一份固定测试音频连续运行三次，记录：

- 三次均从 Upload 到可播放工作台；
- 同一输入得到相同 `patch_id`；
- 16 个数据 Pad 与 16 个 UI 位置逐项一致；
- 8-pad MIDI Controller 切换 Bank A/B 后覆盖全部 16 个逻辑位置；有素材的 Pad 触发正确声音，empty Pad 保持 no-op；
- 导出的 ZIP 三次均通过完整性校验；
- 在 Ableton Live 中导入 Stems/Samples 和 MIDI，设置 Manifest BPM 后可以继续编排；
- 一位非开发者在无口头指导下完成 Upload、MIDI 演奏和 Export；
- 已知问题和失败截图进入 Release Evidence。

## 9. 本切片明确不做

- Prompt / Voice 生成和 Generation Provider；
- Agent Orchestration 实现；
- AI Replace / Variation；
- Sampler Start/End、Loop、Swap、Roll、Chop 编辑；
- Take 录制；
- Asset Library、账号和云同步；
- `.als`、Logic、FL Studio 等专有工程文件；
- 完整 Separator 选型或 Timing Analyzer 迁移；
- Learn / Arcade。

## 10. 后续顺序

1. 本切片：Upload → 16 Data Pads / 16-position UI → MIDI + Bank A/B → Creator Export ZIP。
2. Stage 1 第二切片：Sampler Edit + Take Recording，并把 Take 纳入 Creator Export。
3. Stage 1 后段：Prompt/Voice → Generation → 同一个 Patch Engine。
4. Stage 2：AI Variation、Patch Versioning、Project Bin / Global Library。
