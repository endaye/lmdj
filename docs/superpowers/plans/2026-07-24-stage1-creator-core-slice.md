# Stage 1 Creator Core First Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 Upload → 8-pad Play 链路升级为 Upload Preflight → 16 个数据 Pad / 16 位 UI → 通用 MIDI 演奏 → Creator Export ZIP，并通过 Ableton Live Smoke Test。

**Architecture:** `lmdj.patch.v1` 继续作为 Web、CLI、Worker、API 的唯一 Patch 契约，但 `pads` 原子收紧为固定 16 项；Patchify、Web Schema 副本、fixtures 和消费者在同一提交内同步。Audio Worker 在 Patchify 后生成独立的 `lmdj.creator-export-source.v1` inventory，API 只基于该 inventory 构建确定性 ZIP；Web MIDI 通过独立适配层进入现有 `AudioEngine.triggerPad(index)`。

**Tech Stack:** Python 3.11+、dataclasses、JSON Schema 2020-12、FastAPI、stdlib `wave` / `subprocess` / `zipfile` / `hashlib`、librosa（仅 `.venv-pfs` 子进程）、React 19、TypeScript、Web MIDI API、Vitest、React Testing Library、pytest。

## Global Constraints

- 已确认设计：`docs/superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md`。
- `patch.pads` 必须恰好 16 项，数组顺序和 `Pad.index` 都是 `0..15`；UI 不补槽、不截断、不创建 view-only Pad。
- 未分配素材的位置仍是正式 `Pad`，使用 `action: "empty"`；empty 和 reserved action 对所有输入保持 no-op。
- `Scene.pad_indexes` 必须完整覆盖 `0..15`。
- 16-pad Controller 默认 Note On `36..51` → Pad `0..15`；8-pad Controller 用 Bank A/B 映射 `0..7` / `8..15`。
- MIDI Learn 只有在取得 16 个或 8 个互不重复的 note number 后才能覆盖上一次有效映射。
- Upload 默认限制为 `200 MiB` 和 `600 秒`；环境变量名固定为 `LMDJ_UPLOAD_MAX_BYTES`、`LMDJ_UPLOAD_MAX_DURATION_SECONDS`。
- Upload 被拒绝时不得创建 Job，也不得写入 `queued`。
- API、Web 和 Export Builder 只消费 `patch.json`、`export-source.json` 及其中显式引用的文件；不得回读 `lanes.json`、`chart.mid` 或 `report.json` 补产品数据。
- Key 分析只在 `workers/audio/.venv-pfs` 子进程运行；不得把 numpy/librosa 加入 Audio Worker 主环境或 `apps/api`。
- Export ZIP 使用固定 entry 顺序、固定时间戳和 `ZIP_STORED`，同一 Job 重复请求必须逐字节一致。
- 所有 package 代码进入 `apps/`、`packages/`、`workers/`；不得修改冻结的 `references/demos/lmdj-song-pipeline/`。
- 每项实现遵循 TDD；每个 Task 通过自己的测试后单独 Conventional Commit。

---

## File Structure

- Modify: `packages/core-models/lmdj_core_models/model.py` — Python Patch 形状不变量。
- Modify: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json` — `pads` / scene 的 16 项结构约束。
- Modify: `packages/core-models/tests/test_model.py`, `packages/core-models/tests/test_schema.py` — 16 Pad contract tests。
- Modify: `packages/patchify/lmdj_patchify/pad_mapper.py`, `packages/patchify/lmdj_patchify/patchify.py` — 固定输出 16 Pad。
- Modify: `packages/patchify/tests/test_pad_mapper.py`, `packages/patchify/tests/test_patchify.py` — mapper / scene / empty-slot tests。
- Regenerate: `apps/web/src/patch/schema/lmdj.patch.v1.schema.json`, `apps/web/src/patch/types.ts` — Web contract outputs。
- Regenerate: `apps/web/src/patch/__fixtures__/patch.golden.json`, `apps/web/public/example-patch/patch.json` — 16 Pad fixtures。
- Modify: `apps/web/src/patch/loader.ts`, `apps/web/src/patch/loader.test.ts` — 16 个连续索引的语义校验。
- Modify: `apps/web/src/ui/PadGrid.tsx`, `apps/web/src/ui/PadGrid.test.tsx`, `apps/web/src/ui/App.tsx`, `apps/web/src/ui/App.test.tsx`, `apps/web/src/ui/theme.css` — 2×8 UI 与键盘 Bank。
- Create: `apps/web/src/midi/mapping.ts`, `apps/web/src/midi/mapping.test.ts` — 纯 MIDI 映射与 Learn 状态。
- Create: `apps/web/src/midi/MidiInput.ts`, `apps/web/src/midi/MidiInput.test.ts` — Web MIDI 生命周期适配。
- Create: `apps/web/src/ui/MidiPanel.tsx`, `apps/web/src/ui/MidiPanel.test.tsx` — 连接、Learn、Bank 状态 UI。
- Create: `apps/api/lmdj_api/preflight.py`, `apps/api/tests/test_preflight.py` — 上传落盘、大小、格式与时长检测。
- Modify: `apps/api/lmdj_api/app.py`, `apps/api/tests/test_app.py`, `apps/api/tests/test_config.py` — Preflight 接线与 HTTP 错误。
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/key_analysis.py` — PFS 环境内的 Key 估计 CLI。
- Create: `workers/audio/lmdj_audio_worker/music_metadata.py`, `workers/audio/tests/test_music_metadata.py` — 主 Worker 子进程包装。
- Create: `workers/audio/lmdj_audio_worker/export_source.py`, `workers/audio/tests/test_export_source.py` — inventory 生成与校验。
- Modify: `workers/audio/lmdj_audio_worker/job.py`, `workers/audio/tests/test_job.py` — Job 完成前写 inventory。
- Create: `apps/api/lmdj_api/export_builder.py`, `apps/api/tests/test_export_builder.py` — Manifest 与确定性 ZIP。
- Modify: `apps/api/lmdj_api/app.py`, `apps/api/tests/test_app.py` — `GET /jobs/{job_id}/export`。
- Modify: `apps/web/src/api/client.ts`, `apps/web/src/api/client.test.ts` — Export 下载与 409 missing-items。
- Create: `apps/web/src/ui/ExportPanel.tsx`, `apps/web/src/ui/ExportPanel.test.tsx` — Creator Pack UI。
- Modify: `apps/web/src/ui/App.tsx`, `apps/web/src/ui/App.test.tsx`, `apps/web/src/ui/theme.css` — 仅 API Job 展示 Export。
- Create: `docs/release-evidence/2026-07-24-stage1-creator-core.md` — 三次运行、MIDI、DAW 和非开发者验收记录。

---

### Task 1: 原子收紧 16-Pad Patch 契约

**Files:**
- Modify: `packages/core-models/lmdj_core_models/model.py`
- Modify: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`
- Modify: `packages/core-models/tests/test_model.py`
- Modify: `packages/core-models/tests/test_schema.py`
- Modify: `packages/patchify/lmdj_patchify/pad_mapper.py`
- Modify: `packages/patchify/lmdj_patchify/patchify.py`
- Modify: `packages/patchify/tests/test_pad_mapper.py`
- Modify: `packages/patchify/tests/test_patchify.py`

**Interfaces:**
- Produces: `PAD_COUNT = 16`、`Patch.__post_init__()` 的连续索引校验、`map_focus_pads(elements) -> list[Pad]` 固定 16 项。
- Preserves: 前八项既有 Focus View 语义；索引 `8..15` 是 `action="empty"` 的正式数据 Pad。

- [ ] **Step 1: 写失败测试**

在 core-models 测试中把 `_sample_patch()` 改成 16 Pad，并加入：

```python
def test_patch_rejects_non_contiguous_pad_indexes():
    patch = _sample_patch()
    bad = list(patch.pads)
    bad[15] = Pad(99, "Slot 16", "Empty", "empty", None, {})
    with pytest.raises(ValueError, match="pads must have indexes 0..15"):
        replace(patch, pads=bad)


def test_schema_rejects_any_pad_count_other_than_16():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    for pads in (data["pads"][:15], data["pads"] + [data["pads"][-1]]):
        invalid = {**data, "pads": pads}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
```

在 Patchify 测试中断言：

```python
assert len(pads) == 16
assert [pad.index for pad in pads] == list(range(16))
assert all(pad.action == "empty" for pad in pads[8:16])
assert data["scenes"][0]["pad_indexes"] == list(range(16))
```

- [ ] **Step 2: 运行测试确认失败**

```bash
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
```

Expected: core-models 因当前只含一个 Pad、Patchify 因当前只产出 8 Pad 而 FAIL。

- [ ] **Step 3: 实现 Python 与 Schema 不变量**

在 `model.py` 的常量区增加 `PAD_COUNT`，并在现有 `Patch` dataclass 的全部字段之后加入 `__post_init__`：

```python
PAD_COUNT = 16

def __post_init__(self) -> None:
    expected = list(range(PAD_COUNT))
    if [pad.index for pad in self.pads] != expected:
        raise ValueError("pads must have indexes 0..15 in array order")
    for scene in self.scenes:
        if scene.pad_indexes != expected:
            raise ValueError(f"scene {scene.scene_id} must cover pad indexes 0..15")
```

Schema 的 `pads` 使用 `minItems: 16`、`maxItems: 16`；`pad.index` 和 `scene.pad_indexes[]` 使用 `maximum: 15`，scene 数组使用 `minItems: 16`、`maxItems: 16`、`uniqueItems: true`。Python 不变量负责 Schema 无法表达的“数组位置等于 index”跨字段规则。

在 `pad_mapper.py` 将 `FOCUS_SLOTS` 扩为 16 项，并在既有 8 项后追加：

```python
_EMPTY_SLOTS = [f"Slot {index + 1:02d}" for index in range(8, 16)]

controls = [
    Pad(4, "Fill", "Fill", "scene_fill", None, {"quantize": "1 bar"}),
    Pad(5, "Drop", "Drop", "scene_drop", None, {"quantize": "1 bar"}),
    Pad(6, "Mute", "Mute", "mute_group", None, {"target": "selected_or_master"}),
    Pad(7, "FX/Variation", "FX", "ai_variation", None, {"scope": "scene"}),
]
empty = [
    Pad(index, slot, "Empty", "empty", None, {})
    for index, slot in enumerate(_EMPTY_SLOTS, start=8)
]
return semantic + controls + empty
```

`patchify.py` 保持 `Scene.pad_indexes=[pad.index for pad in pads]`，由 16 项 mapper 自动输出 `0..15`。

- [ ] **Step 4: 运行测试确认通过**

```bash
scripts/dev.sh test
```

Expected: core-models 与 patchify 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add packages/core-models packages/patchify
git commit -m "feat(contract): require sixteen Pad slots"
```

---

### Task 2: 同步 Web 契约、fixtures 与 2×8 Pad Surface

**Files:**
- Regenerate: `apps/web/src/patch/schema/lmdj.patch.v1.schema.json`
- Regenerate: `apps/web/src/patch/types.ts`
- Regenerate: `apps/web/src/patch/__fixtures__/patch.golden.json`
- Regenerate: `apps/web/public/example-patch/patch.json`
- Modify: `apps/web/src/patch/loader.ts`
- Modify: `apps/web/src/patch/loader.test.ts`
- Modify: `apps/web/src/ui/PadGrid.tsx`
- Modify: `apps/web/src/ui/PadGrid.test.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces: `assertPadShape(patch: Patch): void`；`PadGrid` 只渲染 `bundle.patch.pads` 的 16 项。
- Preserves: `AudioEngine.triggerPad(index)`；empty/reserved Pad 仍由 `padElementIds()` 返回空数组。

- [ ] **Step 1: 写失败测试**

`loader.test.ts` 增加 15 项、乱序 index、Scene 缺 index 三个拒绝用例；`PadGrid.test.tsx` 改为：

```ts
it("renders exactly the sixteen contract pads in array order", () => {
  setup();
  const pads = screen.getAllByTestId(/^pad-\d+$/);
  expect(pads).toHaveLength(16);
  expect(pads.map((node) => node.getAttribute("data-testid"))).toEqual(
    Array.from({ length: 16 }, (_, index) => `pad-${index}`),
  );
});
```

`App.test.tsx` 断言 landing 文案包含“16 个 Pad Slot”，ghost grid 有 16 项。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npm run sync-contract
npm test -- --run src/patch/loader.test.ts src/ui/PadGrid.test.tsx src/ui/App.test.tsx
```

Expected: fixtures 仍为 8 Pad，UI 和文案断言 FAIL。

- [ ] **Step 3: 同步产物并实现语义校验**

```bash
scripts/dev.sh smoke
cp references/demos/lmdj-song-pipeline/output/testsong/patch.json apps/web/src/patch/__fixtures__/patch.golden.json
cd apps/web
npm run sync-contract
npm run make-example
```

在 `loader.ts` 的 Schema 校验后调用：

```ts
function assertPadShape(patch: Patch): void {
  const expected = Array.from({ length: 16 }, (_, index) => index);
  const actual = patch.pads.map((pad) => pad.index);
  if (actual.some((index, position) => index !== expected[position])) {
    throw new PatchValidationError(["pads must be ordered with indexes 0..15"]);
  }
  for (const scene of patch.scenes) {
    if (
      scene.pad_indexes.length !== 16 ||
      scene.pad_indexes.some((index, position) => index !== expected[position])
    ) {
      throw new PatchValidationError([
        `scene ${scene.scene_id} must cover pad indexes 0..15`,
      ]);
    }
  }
}
```

`PadGrid` 保持直接 `bundle.patch.pads.map`；将 `data-lane` 只赋给索引 `0..3`。CSS 桌面布局设为 `grid-template-columns: repeat(8, 1fr)`，形成 2 行 × 8 列；窄屏 media query 退化为 4 列。`GHOST_SLOTS` 扩为 16 项，landing 文案改为“16 个 Pad Slot”。

- [ ] **Step 4: 运行 Web 验证**

```bash
cd apps/web
npm run check-contract
npm test
npm run build
```

Expected: contract、全部 Vitest、TypeScript build 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): render sixteen contract Pad slots"
```

---

### Task 3: 纯 MIDI 映射、Learn 与持久化

**Files:**
- Create: `apps/web/src/midi/mapping.ts`
- Create: `apps/web/src/midi/mapping.test.ts`

**Interfaces:**
- Produces:
  - `type MidiBank = "A" | "B"`
  - `type MidiMapping = { mode: "direct-16"; notes: number[] } | { mode: "banked-8"; notes: number[] }`
  - `DEFAULT_DIRECT_MAPPING`
  - `padIndexForNote(mapping, note, bank): number | null`
  - `MidiLearnSession.capture(note): MidiMapping | null`
  - `loadMidiMapping(storage): MidiMapping`
  - `saveMidiMapping(storage, mapping): void`

- [ ] **Step 1: 写映射测试**

```ts
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 36, "A")).toBe(0);
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 51, "B")).toBe(15);
expect(padIndexForNote({ mode: "banked-8", notes: [36,37,38,39,40,41,42,43] }, 36, "A")).toBe(0);
expect(padIndexForNote({ mode: "banked-8", notes: [36,37,38,39,40,41,42,43] }, 36, "B")).toBe(8);
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 52, "A")).toBeNull();
```

Learn 测试必须覆盖重复 note 不计数、未完成时返回 `null`、第 16/8 个唯一 note 完成、损坏 localStorage 回退默认映射。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/midi/mapping.test.ts
```

Expected: FAIL——`mapping.ts` 尚不存在。

- [ ] **Step 3: 实现纯映射**

核心实现固定为：

```ts
export const DEFAULT_DIRECT_MAPPING: MidiMapping = {
  mode: "direct-16",
  notes: Array.from({ length: 16 }, (_, index) => 36 + index),
};

export function padIndexForNote(
  mapping: MidiMapping,
  note: number,
  bank: MidiBank,
): number | null {
  const physical = mapping.notes.indexOf(note);
  if (physical < 0) return null;
  return mapping.mode === "direct-16" ? physical : physical + (bank === "A" ? 0 : 8);
}
```

`MidiLearnSession` 的 constructor 接收 mode，目标数量由 mode 决定为 16 或 8；`capture()` 忽略 `<0`、`>127` 和重复值，只有达到目标数量才返回新的不可变 mapping。localStorage key 固定为 `lmdj.midi.mapping.v1`，读取时重新验证 mode、长度、范围和唯一性。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd apps/web
npx vitest run src/midi/mapping.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/midi
git commit -m "feat(web): add sixteen-Pad MIDI mappings"
```

---

### Task 4: Web MIDI 生命周期、Bank UI 与键盘

**Files:**
- Create: `apps/web/src/midi/MidiInput.ts`
- Create: `apps/web/src/midi/MidiInput.test.ts`
- Create: `apps/web/src/ui/MidiPanel.tsx`
- Create: `apps/web/src/ui/MidiPanel.test.tsx`
- Modify: `apps/web/src/ui/PadGrid.tsx`
- Modify: `apps/web/src/ui/PadGrid.test.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Consumes: `padIndexForNote()`、`AudioEngine.triggerPad(index)`。
- Produces:
  - `class MidiInput`
  - `interface MidiSnapshot { support: "unknown"|"unsupported"|"available"; connection: "idle"|"requesting"|"connected"|"denied"|"disconnected"; devices: string[] }`
  - `MidiPanel` props `{ onTrigger(index), bank, onBankChange }`。

- [ ] **Step 1: 写失败测试**

构造 fake `MIDIAccess` 与两个 fake input，验证：

```ts
input.emit([0x90, 36, 100]); // 触发
input.emit([0x90, 36, 0]);   // 不触发
input.emit([0x80, 36, 100]); // 不触发
expect(triggered).toEqual([0]);
```

再覆盖：监听全部 inputs、连接后新增设备、断开状态、权限拒绝、unsupported、dispose 后不触发。`MidiPanel.test.tsx` 覆盖 Connect、Direct/8-pad Learn、Bank A/B 切换和 Learn 未完成不覆盖旧 mapping。

`App.test.tsx` 覆盖键盘 A 在 Bank A 触发 `0`、Shift 后 A 触发 `8`、repeat/meta/ctrl/alt 不触发。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/midi/MidiInput.test.ts src/ui/MidiPanel.test.tsx src/ui/App.test.tsx
```

Expected: FAIL——适配器和面板尚不存在。

- [ ] **Step 3: 实现适配器与 UI**

`MidiInput` constructor 接收：

```ts
constructor(
  private readonly onNote: (note: number) => void,
  private readonly requestAccess: () => Promise<MIDIAccess> =
    () => navigator.requestMIDIAccess({ sysex: false }),
) {}
```

消息处理只允许：

```ts
const command = data[0] & 0xf0;
const note = data[1];
const velocity = data[2];
if (command === 0x90 && velocity > 0) this.onNote(note);
```

`connect()` 给 `access.inputs` 中每个 input 绑定 handler，并通过 `access.onstatechange` 重新绑定；`dispose()` 清空所有 handler。权限拒绝只更新 snapshot，不自动重试。

`App` 持有 `bank: MidiBank`；键盘八键数组仍为 `A S D F Z X C V`，触发 index 为 `keyIndex + (bank === "A" ? 0 : 8)`；Shift 只切换 Bank，不发声。`PadGrid` 接收 bank，只在当前 Bank 的八个 Pad 上显示键盘提示。`MidiPanel` 的 note 回调通过当前 mapping 和 bank 得到 index 后调用 engine。

- [ ] **Step 4: 运行 Web 全套验证**

```bash
cd apps/web
npm test
npm run build
```

Expected: 全部 PASS；jsdom 测试无真实 MIDI 权限请求。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/midi apps/web/src/ui
git commit -m "feat(web): play sixteen Pads through MIDI banks"
```

---

### Task 5: Upload Preflight 与拒绝语义

**Files:**
- Create: `apps/api/lmdj_api/preflight.py`
- Create: `apps/api/tests/test_preflight.py`
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/conftest.py`
- Modify: `apps/api/tests/test_app.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/ErrorPanel.tsx`

**Interfaces:**
- Produces:
  - `UploadLimits(max_bytes: int, max_duration_seconds: float)`
  - `limits_from_env() -> UploadLimits`
  - `PreflightError(status_code: int, detail: str)`
  - `persist_and_probe(file: UploadFile, destination: Path, limits: UploadLimits) -> AudioProbe`
  - `AudioProbe(format_name: str, codec_name: str, duration_seconds: float)`
- Extends: `ApiError` 增加 `detail?: unknown`；`uploadSong()` 将 API 的结构化 `detail` 转为用户可见错误。

- [ ] **Step 1: 写失败测试**

使用 stdlib `wave` 生成短 WAV；用 monkeypatch 的 `subprocess.run` 返回 ffprobe JSON。覆盖：WAV 成功、MP3 成功、超过 bytes→413、损坏/无 audio stream→415、伪造扩展名→415、超过 duration→422、环境默认值和覆盖值。

API 测试额外断言：

```python
response = client.post("/uploads", files={"file": oversized})
assert response.status_code == 413
assert not (tmp_path / "jobs").exists()
```

Web client / App 测试断言 413、415、422 分别显示服务端返回的最大字节数、支持格式和最大秒数，而不是统一的 `upload failed`；`ErrorPanel` 在 Upload 错误时使用“上传未通过检查”标题，在 Patch 校验错误时保留原标题。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_preflight.py tests/test_app.py tests/test_config.py -q
```

Expected: FAIL——preflight 模块和 HTTP 拒绝路径尚不存在。

- [ ] **Step 3: 实现流式落盘与 ffprobe**

每次读取 `1024 * 1024` bytes，累计超过 `max_bytes` 立即删除 destination 并抛 413。只接受 `.wav` / `.mp3`；落盘后执行：

```python
[
    "ffprobe", "-v", "error", "-select_streams", "a:0",
    "-show_entries", "stream=codec_name:format=format_name,duration",
    "-of", "json", str(destination),
]
```

`.wav` 要求 detected format 含 `wav`，`.mp3` 要求含 `mp3`；无 audio stream、JSON 损坏、ffprobe 非零均为 415。duration 大于限制为 422。

`uploads()` 先创建独立临时目录并完成 preflight，再生成 `job_id` 和调用 `executor.submit()`；`PreflightError` 转为同 status 的 `HTTPException`，失败时用 `shutil.rmtree(temp_dir)` 清理。

Web `uploadSong()` 对非 2xx 先读取 JSON，将 `body.detail` 传入 `ApiError.detail` 并用于 message；`ErrorPanel` 增加必填 `title` prop，由 App 的 Patch 校验路径传“patch.json 未通过 lmdj.patch.v1 校验”，Upload preflight 路径传“上传未通过检查”。

- [ ] **Step 4: 运行 API 验证**

```bash
cd apps/api
.venv/bin/python -m pytest tests -q
cd ../web
npx vitest run src/api/client.test.ts src/ui/App.test.tsx
```

Expected: API 与 Web 定向测试全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/api/lmdj_api/preflight.py apps/api/lmdj_api/app.py apps/api/tests \
  apps/web/src/api apps/web/src/ui/App.test.tsx apps/web/src/ui/ErrorPanel.tsx
git commit -m "feat(api): validate uploads before job creation"
```

---

### Task 6: Key 分析与 Export Source Inventory

**Files:**
- Create: `workers/audio/lmdj_audio_worker/pipeline_from_stems/key_analysis.py`
- Create: `workers/audio/lmdj_audio_worker/music_metadata.py`
- Create: `workers/audio/lmdj_audio_worker/export_source.py`
- Create: `workers/audio/tests/test_music_metadata.py`
- Create: `workers/audio/tests/test_export_source.py`
- Modify: `workers/audio/lmdj_audio_worker/job.py`
- Modify: `workers/audio/tests/test_job.py`

**Interfaces:**
- Produces:
  - `KeyEstimate(value: str, confidence: float)`
  - `PfsKeyAnalyzer.analyze(audio: Path) -> KeyEstimate`
  - `build_export_source(package_dir: Path, patch: Patch, key: KeyEstimate | None, warnings: list[str]) -> dict`
  - `write_export_source(package_dir: Path, source: dict) -> Path`
- `process_job(..., key_analyzer: KeyAnalyzer | None = None)`；未注入时使用 `PfsKeyAnalyzer`，失败只形成 warning 和 partial export source，不把 playable Job 改为 failed。

- [ ] **Step 1: 写失败测试**

PFS Key 单测用合成 C-major chroma 替换 librosa 特征函数，断言 `C major` 和 `0 <= confidence <= 1`。子进程包装测试覆盖成功 JSON、非零退出、超时、`.venv-pfs` 缺失。

Inventory 测试构造含 `patch.json`、`stems/drums.wav`、samples、chart.mid 的 package，断言：

```python
assert source["schema"] == "lmdj.creator-export-source.v1"
assert source["patch"] == "patch.json"
assert source["stems"] == ["stems/drums.wav"]
assert source["samples"] == sorted({element.source_path for element in patch.elements})
assert source["midi"] == ["chart.mid"]
assert source["music"]["time_signature"]["source"] == "fixed-v1"
assert source["music"]["loop"]["steps"] == patch.patterns[0].length_steps
```

再覆盖缺 Key warning、只列真实 stem、绝对路径/`..` 路径拒绝。Job 测试断言 completed 前已写 `export-source.json`。

- [ ] **Step 2: 运行测试确认失败**

```bash
workers/audio/.venv/bin/python -m pytest \
  workers/audio/tests/test_music_metadata.py \
  workers/audio/tests/test_export_source.py \
  workers/audio/tests/test_job.py -q
```

Expected: FAIL——三个新接口尚不存在。

- [ ] **Step 3: 实现隔离分析和 inventory**

PFS CLI 用 `librosa.load(..., sr=22050, mono=True)` 与 `librosa.feature.chroma_cqt()`；对平均 chroma 分别和 Krumhansl major/minor profile 的 12 个旋转做 Pearson correlation，最高项决定 Key，confidence 使用最高与第二名相关系数差归一化并 clamp 到 `0..1`。stdout 只输出：

```json
{"value":"A minor","confidence":0.72}
```

主 Worker 命令固定为：

```python
[str(pfs_python), "-m",
 "lmdj_audio_worker.pipeline_from_stems.key_analysis",
 "--audio", str(audio)]
```

`build_export_source()` 仅从 Patch 获取 samples / MIDI / BPM / loop，从 `package_dir/stems/*.wav` 获取实际 stems。Loop 计算固定为 `steps=length_steps`、`beats=steps/4`、`bars=beats/4`。所有相对路径先 `resolve()` 并确认严格位于 package root 内。

`process_job()` 在 Patchify 后分析 `input_copy`，写 `export-source.json`，然后才 emit `completed`。

- [ ] **Step 4: 运行 Worker 验证**

```bash
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
scripts/dev.sh smoke
```

Expected: Worker 全部 PASS；smoke 的 package 含 16-Pad `patch.json`。

- [ ] **Step 5: Commit**

```bash
git add workers/audio
git commit -m "feat(worker): inventory Creator export sources"
```

---

### Task 7: 确定性 Creator Export Builder 与 API

**Files:**
- Create: `apps/api/lmdj_api/export_builder.py`
- Create: `apps/api/tests/test_export_builder.py`
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/test_app.py`

**Interfaces:**
- Produces:
  - `ExportIncomplete(missing: list[str])`
  - `build_creator_export(package_dir: Path, output_dir: Path) -> Path`
  - `GET /jobs/{job_id}/export`
- Response: complete 返回 ZIP attachment；incomplete 返回 HTTP 409 `{"detail":"export incomplete","missing":[...]}`。

- [ ] **Step 1: 写失败测试**

覆盖完整 ZIP、同一 package 连续两次 SHA-256 相同、ZIP entry 顺序稳定、每个 manifest entry 的 bytes/hash、只列真实 stems、路径穿越拒绝、缺 patch/key/MIDI/all samples 分别 409。

API 测试断言未完成 Job 为 409、本地未知 Job 为 404、成功 response 的 `content-disposition` 文件名为 `creator-export-{patch_id}.zip`。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_export_builder.py tests/test_app.py -q
```

Expected: FAIL——builder 和 route 尚不存在。

- [ ] **Step 3: 实现 Manifest 与 ZIP**

Manifest 的文件字段固定为对象：

```json
{
  "files": {
    "patch": {"path":"patch.json","bytes":123,"sha256":"..."},
    "stems": [{"path":"stems/drums.wav","bytes":123,"sha256":"..."}],
    "samples": [{"path":"samples/kick.wav","bytes":123,"sha256":"..."}],
    "midi": [{"path":"midi/chart.mid","bytes":123,"sha256":"..."}],
    "takes": []
  }
}
```

将 inventory 的源路径映射到 ZIP 内 `stems/`、`samples/`、`midi/`，拒绝 basename 冲突。先计算所有文件 entry，再序列化稳定 key 顺序的 `manifest.json`。使用：

```python
info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
info.compress_type = zipfile.ZIP_STORED
info.external_attr = 0o100644 << 16
archive.writestr(info, payload)
```

entry 顺序固定为 `manifest.json`、`patch.json`、其余 archive path 字典序。先写临时文件，再 `os.replace()` 到 `output_dir / f"creator-export-{patch_id}.zip"`。

API route 使用既有 `_job_dir()` 与 completed/package_dir guard；捕获 `ExportIncomplete` 返回结构化 409，不返回 ZIP。

- [ ] **Step 4: 运行 API 全套验证**

```bash
cd apps/api
.venv/bin/python -m pytest tests -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/api/lmdj_api apps/api/tests
git commit -m "feat(api): build deterministic Creator export packs"
```

---

### Task 8: Web Creator Export 下载体验

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Create: `apps/web/src/ui/ExportPanel.tsx`
- Create: `apps/web/src/ui/ExportPanel.test.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces:
  - `downloadCreatorExport(base, jobId): Promise<Blob>`
  - `ExportPanel` props `{ apiBase, jobId, apiClient }`
- Consumes: Task 5 已加入的 `ApiError.detail?: unknown`。
- App loaded state扩为 `{ bundle, source: { kind:"api"; base; jobId } | { kind:"local"|"example" } }`。

- [ ] **Step 1: 写失败测试**

client 测试覆盖成功 Blob、409 body 中 `missing` 保留在 `ApiError.detail`、网络错误。组件测试覆盖下载成功、409 显示缺失项、重试、失败后 PadGrid 仍存在。

App 测试覆盖 API Job 显示“导出 Creator Pack”，拖放和示例不显示。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/api/client.test.ts src/ui/ExportPanel.test.tsx src/ui/App.test.tsx
```

Expected: FAIL——download client 和 ExportPanel 尚不存在。

- [ ] **Step 3: 实现下载与 source provenance**

`downloadCreatorExport()` GET `/jobs/{jobId}/export`；非 2xx 尝试读取 JSON 并附到 `ApiError.detail`。成功 Blob 交给 `ExportPanel`：

```ts
const url = URL.createObjectURL(blob);
const anchor = document.createElement("a");
anchor.href = url;
anchor.download = filename;
anchor.click();
URL.revokeObjectURL(url);
```

`enterLoaded()` 同时接收 source provenance；API 路径保留 normalized base + jobId，example/local 分别标记。Export 下载状态只属于面板，不改变 App phase、不 stop engine、不清空 bundle。409 显示 `missing.join("、")` 与重试按钮。

- [ ] **Step 4: 运行 Web 全套验证**

```bash
cd apps/web
npm run check-contract
npm test
npm run build
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): download Creator export packs"
```

---

### Task 9: 全链路验证与 Release Evidence

**Files:**
- Modify: `scripts/dev.sh`
- Modify: `README.md`
- Modify: `apps/api/README.md` if created by the implementation branch; otherwise document API commands in root `README.md`.
- Create: `docs/release-evidence/2026-07-24-stage1-creator-core.md`

**Interfaces:**
- Produces: `scripts/dev.sh creator-smoke <audio>`，依次上传、轮询、校验 16 Pad、下载两次 Export 并比较 SHA-256。

- [ ] **Step 1: 给 smoke helper 写 shell-level 验证**

`creator-smoke` 必须在任何 HTTP 或 contract 失败时非零退出，并打印：

```text
job_id: <id>
patch_id: <id>
pads: 16
export_sha256_a: <sha>
export_sha256_b: <sha>
deterministic: yes
```

实现使用 `curl --fail-with-body` 和 package venv 内 Python `jsonschema`；不得用 `jq` 作为额外系统依赖。

- [ ] **Step 2: 运行所有自动门禁**

```bash
scripts/dev.sh test
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
cd apps/web && npm run check-contract && npm test && npm run build
```

Expected: 四组全部 PASS。

- [ ] **Step 3: 连续运行固定音频三次**

启动 API/Web 后，对同一固定音频执行三次 `scripts/dev.sh creator-smoke <audio>`。在 evidence 文档逐次记录 job_id、patch_id、16 Pad 检查、两个 ZIP SHA-256 和结果；三次 patch_id 必须一致，每次两个 ZIP hash 必须一致。

- [ ] **Step 4: 实体 MIDI 与 Ableton Live 验收**

在 evidence 文档记录控制器型号、浏览器版本和：

- Bank A 的 8 键对应 Pad `0..7`；
- Bank B 的 8 键对应 Pad `8..15`；
- 有素材 Pad 发出正确声音；
- empty Pad 无声且无异常；
- ZIP 中 Stems、Samples、MIDI、Manifest 可在 Ableton Live 导入；
- 按 Manifest BPM 设置工程后可继续编排；
- 非开发者在无口头指导下完成 Upload、MIDI 演奏、Export。

每项记录 `PASS` 或 `FAIL`；任一 FAIL 阻止 PR 标记 Ready。

- [ ] **Step 5: Commit**

```bash
git add scripts/dev.sh README.md docs/release-evidence/2026-07-24-stage1-creator-core.md
[ ! -f apps/api/README.md ] || git add apps/api/README.md
git commit -m "docs: record Creator Core release evidence"
```

- [ ] **Step 6: 最终分支检查**

```bash
git status --short
git log --oneline --decorate -10
```

Expected: 工作区干净；Task 1–9 均有独立 Conventional Commit。
