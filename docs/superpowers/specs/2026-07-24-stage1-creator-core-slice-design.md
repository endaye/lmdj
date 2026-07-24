# LMDJ Stage 1 Creator Core 首条纵向切片设计

日期：2026-07-24

状态：待用户书面复核（方向与范围已在讨论中确认）

上游依据：[LMDJ 软件 MVP Stage 1–4 与团队协作 Memo｜2026-07-18](https://fcn8wuu8uotg.feishu.cn/docx/ZK5eduti6oE9Dox8Pkbc8r0vnPb)（`approved-for-planning`，读取 revision 63）

## 1. 定位

这条切片把当前已运行的“上传歌曲后得到 8-pad Patch View”推进为首个可由 DAW 创作者验收的 Creator Core 闭环：

```text
Upload WAV/MP3
  → Preflight Validation
  → Existing Audio Pipeline
  → 8 Active Pads
  → Keyboard / Generic MIDI Play
  → Creator Export ZIP
  → Ableton Live Smoke Test
```

它验证的是“用户拥有的音频能否成为可演奏、可继续制作的素材包”，不是生成入口、完整 Sampler、完整 DAW 或 16-pad 系统。

## 2. 已确认的产品决策

| 决策点 | 本切片结论 |
| --- | --- |
| 有效 Pad 数 | 只支持当前 8 个有效 Pad，索引为 `0..7` |
| 16-pad 外观 | UI 使用 2×8 的 16 位布局；位置 `8..15` 是 view-only 空槽，不写入 `patch.json`，不参与播放 |
| 16 个有效 Pad | 延后；本切片不做 Bank 切换，不宣称支持 16 个有效逻辑 Pad |
| Patch 契约 | 保持 `lmdj.patch.v1`；不因 UI 空槽修改 Schema |
| MIDI | 是本切片验收项；键盘只是备用输入 |
| Export | 通用 ZIP + 明确 Manifest；不生成 `.als`、Logic、FL Studio 等专有工程文件 |
| 首个 DAW | Ableton Live，只做真实导入 Smoke Test |
| 执行顺序 | 先完成 Upload → Play → Export；Prompt、Agent Orchestration、AI Variation 后置 |

## 3. 方案比较

### 3.1 Pad 扩展

**采用：8 个数据 Pad + 16 位 UI 外观。**

- 优点：保留现有 Patchify 和 `lmdj.patch.v1` 语义，不用制造八个虚假产品对象；界面又能提前验证 2×8 的设备形态。
- 代价：后 8 位暂时不可交互，未来扩成 16 个有效 Pad 时仍需单独设计槽位语义和 Bank 映射。

**不采用：立即让 Patchify 固定输出 16 个 Pad。**

- 这会把空位写成产品数据，并迫使 Scene、键盘、MIDI、测试和文案同时宣称 16-pad 能力，超出当前范围。

**不采用：继续只显示 8 位 UI。**

- 改动最少，但不能验证已确认的 2×8 产品形态，也会让后续 UI 扩展产生第二次布局迁移。

### 3.2 Export

**采用：开放文件 ZIP。**

- 能被不同 DAW 使用，容易检查内容完整性和版本，且不绑定任何私有工程格式。

**延后：直接生成 `.als` 或其他原生工程。**

- 专有格式兼容和版本测试会把本切片变成 DAW 工程转换项目。

**不采用：只保留现有逐文件下载端点。**

- 这不能形成一次完整、可移交、可验收的 Creator Export Pack。

### 3.3 MIDI

**采用：Web MIDI + 默认映射 + MIDI Learn。**

- 默认将 Note On `36..43` 映射到 Pad `0..7`。
- 用户可进入 MIDI Learn，依次敲击八个实体 Pad；系统记录八个不同 note number，并保存在浏览器 `localStorage`。
- 键盘 `A S D F / Z X C V` 继续映射到 Pad `0..7`。

**不采用：只支持键盘。**

- 不满足 Stage 1 对通用 MIDI Pad 的明确验收。

**延后：现在实现两组 Bank。**

- 当前只有 8 个有效 Pad，Bank 没有可切换的第二组内容。

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

### 5.2 Pad Surface

`patch.json` 继续包含最多八个当前有效 Pad。Web 创建固定 16 位视图：

- `0..7`：由 `patch.pads` 驱动；
- `8..15`：渲染为 disabled / empty 的占位视图；
- 占位视图没有 `Pad` 产品对象，不传给 `AudioEngine`，不接受键盘、鼠标或 MIDI 触发；
- UI 文案使用“8 个可演奏 Pad”，不宣称已支持 16 个有效 Pad。

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
- 只触发 `0..7`；
- 默认监听用户授权后可用的全部 MIDI input；
- 设备断开时显示非阻塞状态，键盘和鼠标仍可用；
- 浏览器不支持 Web MIDI 或用户拒绝权限时给出明确提示，不伪装为已连接；
- MIDI Learn 未完成八个不同 note number 前不覆盖上一次有效映射。

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

已加载 API Job 的工作台显示“导出 Creator Pack”按钮：

- complete：下载 ZIP；
- partial：显示缺失项和重试/返回入口；
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
- Pad UI：始终渲染 16 位；只有前八位来自 Patch；后八位 disabled 且不会调用 `triggerPad`。
- MIDI adapter：默认映射、velocity 0、未知 note、learn 完成、learn 中断、设备断开、权限拒绝。
- Export Builder：ZIP 文件清单、SHA-256、稳定排序、路径穿越、缺少 Key/MIDI/Sample、只列真实 Stem。
- Web：API Job 显示导出按钮；local/example 不显示；409 显示缺失项；下载失败保留 loaded 状态。
- Contract：`npm run check-contract` 继续通过；`lmdj.patch.v1` 无漂移。

### 8.2 Release Evidence

使用同一份固定测试音频连续运行三次，记录：

- 三次均从 Upload 到可播放工作台；
- 同一输入得到相同 `patch_id`；
- 实体 MIDI Pad 的八个键分别触发正确的八个逻辑位置；
- 导出的 ZIP 三次均通过完整性校验；
- 在 Ableton Live 中导入 Stems/Samples 和 MIDI，设置 Manifest BPM 后可以继续编排；
- 一位非开发者在无口头指导下完成 Upload、MIDI 演奏和 Export；
- 已知问题和失败截图进入 Release Evidence。

## 9. 本切片明确不做

- 第 9–16 个有效 Pad；
- 8-Pad Controller 的 Bank 切换；
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

1. 本切片：Upload → 8 Active Pads / 16-position UI → MIDI → Creator Export ZIP。
2. Stage 1 第二切片：Sampler Edit + Take Recording，并把 Take 纳入 Creator Export。
3. Stage 1 后段：Prompt/Voice → Generation → 同一个 Patch Engine。
4. Stage 2：AI Variation、Patch Versioning、Project Bin / Global Library。
