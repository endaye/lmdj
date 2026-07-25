# Stage 1 Creator Core + Workspace UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 Upload → 8-pad Play 链路升级为一条完整的 Stage 1 纵向切片：Upload Preflight → Instrument-first Creator Workspace → 固定 16 个数据 Pad → 通用 MIDI 演奏 → Creator Export ZIP，并通过响应式 UI 与 Ableton Live 验收。

**Architecture:** `lmdj.patch.v1` 继续作为 Web、CLI、Worker、API 的唯一 Patch 契约，但 `pads` 原子收紧为固定 16 项；Patchify、Web Schema 副本、fixtures 和消费者在同一提交内同步。Web 以 `WorkbenchViewModel` 驱动 Instrument-first Canvas，Pattern 在上、PadMatrix16 在下，Creator Tools / Context Inspector / Status Bar 围绕同一 Patch 状态组织；Audio Worker 生成 `lmdj.creator-export-source.v1` inventory，API 据此构建确定性 ZIP，Web 以 ExportChecklist 呈现结果。

**Tech Stack:** Python 3.11+、dataclasses、JSON Schema 2020-12、FastAPI、stdlib `wave` / `subprocess` / `zipfile` / `hashlib`、librosa（仅 `.venv-pfs` 子进程）、React 19、TypeScript、Web MIDI API、Vitest、React Testing Library、pytest。

## Global Constraints

- 已确认产品与技术设计：`docs/superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md`。
- 已确认 UI 设计：`docs/superpowers/specs/2026-07-24-stage1-creator-workspace-ui-design.md`；视觉实现以 `docs/superpowers/specs/2026-07-24-stage1-creator-workspace-ui-references/` 为校准基准。
- `patch.pads` 必须恰好 16 项，数组顺序和 `Pad.index` 都是 `0..15`；UI 不补槽、不截断、不创建 view-only Pad。
- 未分配素材的位置仍是正式 `Pad`，使用 `action: "empty"`；empty 和 reserved action 对所有输入保持 no-op。
- `Scene.pad_indexes` 必须完整覆盖 `0..15`。
- 16-pad Controller 默认 Note On `36..51` → Pad `0..15`；8-pad Controller 用 Bank A/B 映射 `0..7` / `8..15`。
- 键盘直接覆盖 16 个逻辑位置：顶排 `1 2 3 4 5 6 7 8` → `0..7`，底排 `Q W E R T Y U I` → `8..15`；键盘不随 MIDI Bank 切换。
- MIDI Learn 只有在取得 16 个或 8 个互不重复的 note number 后才能覆盖上一次有效映射。
- Workbench 使用 Instrument-first Canvas：Pattern 在 PadMatrix16 上方；≥960px 为 8×2，360–959px 为 4×4；每个 Pad 保持 1:1，4×4 的 row-gap 与 column-gap 相等。
- Inspector 断点约束：≥1280px 的常驻 Inspector 不得覆盖 Pad；960–1279px 的抽屉和 600–959px 的覆盖式抽屉可覆盖 Canvas，但打开时必须避开当前 selected / playing Pad 或以其他方式保持其 trigger feedback 可见；360–599px 使用全高参数 Sheet，必须有可访问的关闭路径，关闭后保留 selection / playback / mode 状态；Status Bar 在正常关闭状态不得遮挡 Pad。
- 视觉 token、Pad 状态、动效、响应式和可访问性直接采用 UI Design Spec；不得继续扩展旧 graphite Patch View 作为第二套视觉系统。
- 首条切片不呈现可交互的 Generate、Line-in、Chop / Sampler Edit、AI Preview、Take 或 Pattern A–D；这些入口随对应后续能力再启用。
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
- Create: `apps/web/src/ui/workbench/model.ts`, `apps/web/src/ui/workbench/model.test.ts` — Patch → Workbench ViewModel。
- Create: `apps/web/src/ui/WorkbenchShell.tsx`, `apps/web/src/ui/WorkbenchShell.test.tsx` — App Bar、Creator Tools、Canvas、Inspector、Status Bar 编排。
- Create: `apps/web/src/ui/CreatorToolRail.tsx`, `apps/web/src/ui/CreatorToolRail.test.tsx` — 首条切片只呈现 Source / Performance / Export。
- Create: `apps/web/src/ui/PatternSurface.tsx`, `apps/web/src/ui/PatternSurface.test.tsx` — Pattern 与播放头。
- Create: `apps/web/src/ui/PadMatrix16.tsx`, `apps/web/src/ui/PadMatrix16.test.tsx` — 8×2 / 4×4、选择、触发、状态与键位提示。
- Create: `apps/web/src/ui/PadButton.tsx`, `apps/web/src/ui/PadButton.test.tsx` — 单 Pad 的角色色、图形签名、ARIA 与动效。
- Create: `apps/web/src/ui/ContextInspector.tsx`, `apps/web/src/ui/ContextInspector.test.tsx` — Patch / Pad 只读上下文。
- Delete: `apps/web/src/ui/PadGrid.tsx`, `apps/web/src/ui/PadGrid.test.tsx`, `apps/web/src/ui/Inspector.tsx` — 新 Canvas 接管后移除旧 graphite surface。
- Modify: `apps/web/src/ui/StepGrid.test.tsx` — 把旧 Inspector 断言迁移到 ContextInspector tests。
- Create: `apps/web/src/ui/SourcePanel.tsx`, `apps/web/src/ui/SourcePanel.test.tsx` — Upload / example 与限制提示。
- Create: `apps/web/src/ui/ProcessingPanel.tsx`, `apps/web/src/ui/ProcessingPanel.test.tsx` — 真实 Job stage 与恢复动作。
- Modify: `apps/web/src/ui/App.tsx`, `apps/web/src/ui/App.test.tsx`, `apps/web/src/ui/theme.css` — Instrument-first 状态接线与 UI Design tokens。
- Create: `apps/web/playwright.config.ts`, `apps/web/e2e/workbench-responsive.spec.ts` — 真实浏览器响应式、正方形 Pad 与 uniform gap 验收。
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
- Create: `apps/web/src/ui/ExportChecklist.tsx`, `apps/web/src/ui/ExportChecklist.test.tsx` — Ready / Review / Missing / Partial Creator Export UI。
- Modify: `apps/web/src/ui/App.tsx`, `apps/web/src/ui/App.test.tsx`, `apps/web/src/ui/theme.css` — 仅 API Job 展示 Export。
- Create: `docs/release-evidence/2026-07-24-stage1-creator-core-and-ui.md` — 三次运行、响应式 UI、MIDI、DAW 和非开发者验收记录。

---

### Task 1: 原子收紧 16-Pad Patch 契约并同步 Web

**Files:**
- Modify: `packages/core-models/lmdj_core_models/model.py`
- Modify: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`
- Modify: `packages/core-models/tests/test_model.py`
- Modify: `packages/core-models/tests/test_schema.py`
- Modify: `packages/patchify/lmdj_patchify/pad_mapper.py`
- Modify: `packages/patchify/lmdj_patchify/patchify.py`
- Modify: `packages/patchify/tests/test_pad_mapper.py`
- Modify: `packages/patchify/tests/test_patchify.py`
- Regenerate: `apps/web/src/patch/schema/lmdj.patch.v1.schema.json`
- Regenerate: `apps/web/src/patch/types.ts`
- Regenerate: `apps/web/src/patch/__fixtures__/patch.golden.json`
- Regenerate: `apps/web/public/example-patch/patch.json`
- Modify: `apps/web/src/patch/loader.ts`
- Modify: `apps/web/src/patch/loader.test.ts`
- Modify: `apps/web/src/patch/contract.test.ts`
- Modify: `apps/web/src/ui/PadGrid.test.tsx`

**Interfaces:**
- Produces: `PAD_COUNT = 16`、`Patch.__post_init__()` 的连续索引校验、`map_focus_pads(elements) -> list[Pad]` 固定 16 项。
- Produces: `assertPadShape(patch: Patch): void`；两个 Web fixture 都是合法、顺序固定的 16-Pad Patch。
- Preserves: 前八项既有 Focus View 语义；索引 `8..15` 是 `action="empty"` 的正式数据 Pad。
- Preserves: `loadPatch()` 是唯一 Web 加载入口；empty/reserved Pad 仍由 `padElementIds()` 返回空数组。

- [x] **Step 1: 写失败测试**

在 core-models 测试中增加 16 Pad 合法 fixture，并加入：

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

`loader.test.ts` 增加 15 项、17 项、乱序 index、Scene 缺 index 四个拒绝用例；`contract.test.ts` 读取 source schema、Web schema、types 和两个 fixture，断言无 drift 且：

```ts
expect(patch.pads.map((pad) => pad.index)).toEqual(
  Array.from({ length: 16 }, (_, index) => index),
);
expect(patch.scenes[0].pad_indexes).toEqual(
  Array.from({ length: 16 }, (_, index) => index),
);
```

旧 `PadGrid.test.tsx` 在被 Task 3 替换前必须把正则改为 `/^pad-\d+$/` 并断言 16 项，确保 contract 迁移提交本身仍通过 Web 全套测试；不得在这里扩展旧视觉或复制第二套 layout 规则。

- [x] **Step 2: 运行测试确认失败**

```bash
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
cd apps/web
npx vitest run src/patch/contract.test.ts src/patch/loader.test.ts
```

Expected: core-models / Patchify 因仍是 8 Pad 语义而 FAIL；Web fixtures 仍为 8 Pad，loader 也尚未执行连续索引语义校验。

- [x] **Step 3: 实现 producer、共享 Schema 与 Web 语义不变量**

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

同步 Web 产物和 fixtures：

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

`assertPadShape()` 必须在 Schema 校验之后、audio decode 之前运行，避免无效 Patch 进入 ViewModel 或 AudioEngine。此 Task 不改 UI；新版 Workbench 在 Task 2–3 一次接入，避免先扩展旧 Patch View 再废弃。

- [x] **Step 4: 运行整个原子迁移门禁**

```bash
scripts/dev.sh test
cd apps/web
npm run check-contract
npm test
npm run build
```

Expected: core-models、Patchify、Web contract、loader 与 TypeScript build 全部 PASS；producer、schema 副本、types、fixtures 和 consumer 都只接受恰好 16 Pad。

- [x] **Step 5: Commit**

```bash
git add packages/core-models packages/patchify \
  apps/web/src/patch apps/web/public/example-patch apps/web/src/ui/PadGrid.test.tsx
git commit -m "feat(contract): require sixteen Pad slots"
```

---

### Task 2: Workbench ViewModel 与 Instrument-first Shell

**Files:**
- Create: `apps/web/src/ui/workbench/model.ts`
- Create: `apps/web/src/ui/workbench/model.test.ts`
- Create: `apps/web/src/ui/WorkbenchShell.tsx`
- Create: `apps/web/src/ui/WorkbenchShell.test.tsx`
- Create: `apps/web/src/ui/CreatorToolRail.tsx`
- Create: `apps/web/src/ui/CreatorToolRail.test.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces:
  - `type WorkbenchMode = "source" | "performance" | "export"`
  - `type WorkbenchReadiness = "ready" | "needs-review" | "partial"`
  - `interface WorkbenchExportState { status: "unknown" | "complete" | "partial"; missing: string[]; key: string | null }`
  - `interface WorkbenchViewModel`
  - `buildWorkbenchViewModel(bundle, selectedPadIndex, exportState): WorkbenchViewModel`
  - `CreatorToolRail` props `{ mode, onModeChange, availableModes }`
  - `WorkbenchShell` 的结构区域：App Bar、Creator Tools、Instrument Canvas、Context Inspector、Status Bar。
- Preserves: Patch/audio 仍只由 `loadPatch()` 进入；ViewModel 不复制音频 buffer，也不改写 Patch。

- [x] **Step 1: 写失败测试**

`model.test.ts` 使用 golden bundle 覆盖：

```ts
expect(model.padCount).toBe(16);
expect(model.selectedPad?.index).toBe(3);
expect(model.durationSeconds).toBe(golden.patch.loop_seconds);
expect(model.key).toBeNull();
expect(model.readiness).toBe("ready");
expect(model.blockers).toEqual([]);
```

再构造 `missingElementIds` 和 warnings，断言 `needs-review` 与 blocker 数量；传入 partial export state 时断言 `partial` 和缺失项；非法 selected index 回退为 `undefined`。

`WorkbenchShell.test.tsx` 使用 landmark / test id 断言 DOM 顺序固定为：

```text
app-bar → creator-tools → instrument-canvas → context-inspector → status-bar
```

`CreatorToolRail.test.tsx` 断言只呈现 Source / Performance / Export，且切换模式不改变 Pad selection；首条切片不存在可点击的 Generate、Line-in、Chop、AI Preview、Take、Pattern A–D 控件，避免用 disabled 假入口制造能力错觉。`App.test.tsx` 断言加载 example 后进入同一个 WorkbenchShell，而不是旧 graphite Patch View。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run \
  src/ui/workbench/model.test.ts \
  src/ui/CreatorToolRail.test.tsx \
  src/ui/WorkbenchShell.test.tsx \
  src/ui/App.test.tsx
```

Expected: FAIL——ViewModel 与 WorkbenchShell 尚不存在。

- [x] **Step 3: 实现 ViewModel 与视觉基础**

ViewModel 保持纯函数：

```ts
export interface WorkbenchViewModel {
  patchId: string;
  bpm: number;
  key: string | null;
  durationSeconds: number;
  padCount: 16;
  selectedPad?: Patch["pads"][number];
  readiness: WorkbenchReadiness;
  blockers: string[];
}

export function buildWorkbenchViewModel(
  bundle: PatchBundle,
  selectedPadIndex?: number,
  exportState: WorkbenchExportState = {
    status: "unknown",
    missing: [],
    key: null,
  },
): WorkbenchViewModel {
  const blockers = [
    ...bundle.warnings,
    ...[...bundle.missingElementIds].map((id) => `missing audio: ${id}`),
    ...exportState.missing.map((item) => `export missing: ${item}`),
  ];
  return {
    patchId: bundle.patch.patch_id,
    bpm: bundle.patch.bpm,
    key: exportState.key,
    durationSeconds: bundle.patch.loop_seconds,
    padCount: 16,
    selectedPad: bundle.patch.pads.find((pad) => pad.index === selectedPadIndex),
    readiness:
      exportState.status === "partial"
        ? "partial"
        : blockers.length === 0
          ? "ready"
          : "needs-review",
    blockers,
  };
}
```

`WorkbenchShell` 只负责布局和 slots，不持有播放或网络副作用。`CreatorToolRail` 只接收 `availableModes`；首条切片传入 `["source", "performance", "export"]`，不创建后置 mode 的 DOM。

`theme.css` 先逐项落 UI Design Spec 的 authoritative tokens：

```css
:root {
  --paper: #f6f2e8;
  --ink: #11110f;
  --drums: #ff4f31;
  --bass: #8a4af3;
  --harmony: #46c79b;
  --lead: #ffd21c;
  --loop: #32c7e9;
  --action: #ff69c8;
  --muted: #d5cfc2;
}
```

再实现桌面三栏骨架、硬边框、信息层级和低高度纵向滚动；不得复用旧 graphite surface 颜色作为新 token 别名。Top App Bar 只启用真实可用的 Play / Export 和 Patch metadata；Undo、Save、Record 随能力落地后再启用，不渲染伪按钮。

桌面结构以 `docs/superpowers/specs/2026-07-24-stage1-creator-workspace-ui-references/instrument-first-desktop-v3.html` 为校准输入，但组件必须由 WorkbenchViewModel 驱动，不复制参考稿中的静态假数据。

`App` 只建立一份 `selectedPadIndex` 和 `WorkbenchViewModel`，把既有 transport/engine 回调注入 shell slots；Source、Processing、Failed 状态仍留待 Task 6 统一视觉化。

- [x] **Step 4: 运行 Web 验证**

```bash
cd apps/web
npx vitest run \
  src/ui/workbench/model.test.ts \
  src/ui/CreatorToolRail.test.tsx \
  src/ui/WorkbenchShell.test.tsx \
  src/ui/App.test.tsx
npm run build
```

Expected: 定向测试与 build 全部 PASS；旧 Patch View 不再是 loaded state 根节点。

- [x] **Step 5: Commit**

```bash
git add apps/web/src/ui
git commit -m "feat(web): add Instrument-first workbench shell"
```

---

### Task 3: PatternSurface、PadMatrix16 与响应式验收

**Files:**
- Create: `apps/web/src/ui/PatternSurface.tsx`
- Create: `apps/web/src/ui/PatternSurface.test.tsx`
- Create: `apps/web/src/ui/PadMatrix16.tsx`
- Create: `apps/web/src/ui/PadMatrix16.test.tsx`
- Create: `apps/web/src/ui/PadButton.tsx`
- Create: `apps/web/src/ui/PadButton.test.tsx`
- Create: `apps/web/src/ui/ContextInspector.tsx`
- Create: `apps/web/src/ui/ContextInspector.test.tsx`
- Delete: `apps/web/src/ui/PadGrid.tsx`
- Delete: `apps/web/src/ui/PadGrid.test.tsx`
- Delete: `apps/web/src/ui/Inspector.tsx`
- Modify: `apps/web/src/ui/StepGrid.test.tsx`
- Modify: `apps/web/src/ui/WorkbenchShell.tsx`
- Modify: `apps/web/src/ui/WorkbenchShell.test.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/workbench-responsive.spec.ts`

**Interfaces:**
- Produces:
  - `PatternSurface` props `{ bundle, engine, playheadStep }`
  - `PadMatrix16` props `{ bundle, engine, selectedPadIndex, onSelect, keyHints }`
  - `PadButton` props `{ pad, visualState, keyHint, onSelect, onTrigger }`
  - `ContextInspector` props `{ model }`
  - `npm run test:e2e`
- Preserves: `AudioEngine.triggerPad(index)` 是 click / keyboard / MIDI 的唯一 Pad 播放入口。

- [x] **Step 1: 写组件失败测试**

`PadMatrix16.test.tsx` 断言恰好渲染 `patch.pads` 的 16 项，DOM 与 `Pad.index` 都是 `0..15`，empty slot 也有稳定名称与 no-op 状态；点击有素材 Pad 同时 `onSelect(index)` 并调用 `engine.triggerPad(index)`，empty/reserved Pad 只更新选择，不伪造播放。

`PadButton.test.tsx` 覆盖 Idle、Selected、Playing、Muted、Missing / Error、Empty；每种状态除颜色外还必须有文字、边框或图标差异。相同 `element_id` / slot 输入生成相同几何签名，Replace 后的不同 `element_id` 生成不同签名；`prefers-reduced-motion` 下不依赖位移或回弹表达状态。

`PatternSurface.test.tsx` 覆盖 transport、step 状态、播放头和无 Pattern 时的明确空态。`ContextInspector.test.tsx` 覆盖未选择时显示 Patch 摘要、quality、unmapped / warning，选择后显示 Pad label/action/source 状态；把 `StepGrid.test.tsx` 中混入的旧 Inspector 测试迁到这里。`App.test.tsx` 断言 `PatternSurface` 在 `PadMatrix16` 之前，选择 Pad 后 Inspector 同步更新；每个 Pad 的 accessible name 同时包含 index、label 和状态。

- [x] **Step 2: 运行组件测试确认失败**

```bash
cd apps/web
npx vitest run \
  src/ui/PatternSurface.test.tsx \
  src/ui/PadMatrix16.test.tsx \
  src/ui/PadButton.test.tsx \
  src/ui/ContextInspector.test.tsx \
  src/ui/WorkbenchShell.test.tsx \
  src/ui/App.test.tsx
```

Expected: FAIL——四个 Instrument Canvas 组件尚不存在。

- [x] **Step 3: 实现 Instrument Canvas**

`PadMatrix16` 必须直接 map contract data：

```tsx
<div className="pad-matrix" data-testid="pad-matrix">
  {bundle.patch.pads.map((pad) => (
    <button
      key={pad.index}
      className="pad"
      data-pad-index={pad.index}
      aria-label={`Pad ${pad.index + 1}: ${pad.label}, ${pad.action}`}
      onClick={() => {
        onSelect(pad.index);
        if (padElementIds(pad).length > 0) engine.triggerPad(pad.index);
      }}
    >
      {/* status, label, key hint */}
    </button>
  ))}
</div>
```

CSS 使用 `aspect-ratio: 1 / 1`，不以固定高度伪造正方形：

```css
.pad {
  min-width: 44px;
  min-height: 44px;
  aspect-ratio: 1 / 1;
}

.pad-matrix {
  --pad-gap: clamp(8px, 1.4cqw, 16px);
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  column-gap: var(--pad-gap);
  row-gap: var(--pad-gap);
}

@media (min-width: 960px) {
  .pad-matrix {
    grid-template-columns: repeat(8, minmax(0, 1fr));
  }
}
```

`PadButton` 用 role token、确定性 `element_id` / slot hash 几何和文字/图标共同表达状态；button 最小触点为 `44×44px`，focus 不被 hover 覆盖，trigger 120ms、inspector 160ms，并为 `prefers-reduced-motion` 提供静态分支。

`PatternSurface` 位于 Canvas 顶部，PadMatrix16 位于其下；ContextInspector 不复制 selection state，只消费 Task 2 的 ViewModel。替换 loaded state 中旧 `PadGrid`，保留可复用的 Transport / StepGrid 子组件，并删除不再引用的 `PadGrid` / `Inspector` 文件；不保留第二套同时可达的 Pad Surface。

- [x] **Step 4: 写并运行真实浏览器响应式验收**

安装 `@playwright/test` 为 dev dependency，增加：

```json
"test:e2e": "playwright test"
```

`workbench-responsive.spec.ts` 对 `1440×900`、`1280×720`、`1024×768`、`768×1024`、`390×844` 逐个打开 example patch，并用 bounding boxes / computed style 断言：

- viewport `>=960` 为 8 列、2 行；`360..959` 为 4 列、4 行；
- 每个 Pad `abs(width - height) <= 1px`；
- 4×4 的 computed `rowGap === columnGap`；
- 任意两个相邻 Pad 的 bounding boxes 不重叠；
- Pattern 在第一排 Pad 上方；≥1280px 的常驻 Inspector 和正常关闭状态的 Status Bar 不覆盖 Pad；960–1279px 的抽屉及 600–959px 的覆盖式抽屉打开时，当前 selected / playing Pad 的 trigger feedback 仍可见；360–599px 的全高参数 Sheet 有可访问的关闭路径，关闭后保留 selection / playback / mode 状态；
- 低高度页面可滚动到最后一排 Pad；
- focus outline、selected、playing、empty、missing 五类状态可区分。

```bash
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Expected: 五个 viewport 全部 PASS。以 `pad-visual-language-v1.html` 和 `responsive-system-v8.html` 逐项校准层级、间距、字体、颜色和状态；差异记录在测试注释或 PR evidence，不另起第二份视觉规范。

- [x] **Step 5: 运行 Web 全套验证**

```bash
cd apps/web
npm run check-contract
npm test
npm run test:e2e
npm run build
```

Expected: contract、Vitest、Playwright 与 build 全部 PASS。

- [x] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat(web): build responsive sixteen-Pad workspace"
```

---

### Task 4: 纯 MIDI 映射、Learn 与持久化

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

- [x] **Step 1: 写映射测试**

```ts
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 36, "A")).toBe(0);
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 51, "B")).toBe(15);
expect(padIndexForNote({ mode: "banked-8", notes: [36,37,38,39,40,41,42,43] }, 36, "A")).toBe(0);
expect(padIndexForNote({ mode: "banked-8", notes: [36,37,38,39,40,41,42,43] }, 36, "B")).toBe(8);
expect(padIndexForNote(DEFAULT_DIRECT_MAPPING, 52, "A")).toBeNull();
```

Learn 测试必须覆盖重复 note 不计数、未完成时返回 `null`、第 16/8 个唯一 note 完成、损坏 localStorage 回退默认映射。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/midi/mapping.test.ts
```

Expected: FAIL——`mapping.ts` 尚不存在。

- [x] **Step 3: 实现纯映射**

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

- [x] **Step 4: 运行测试确认通过**

```bash
cd apps/web
npx vitest run src/midi/mapping.test.ts
```

Expected: PASS。

- [x] **Step 5: Commit**

```bash
git add apps/web/src/midi
git commit -m "feat(web): add sixteen-Pad MIDI mappings"
```

---

### Task 5: Web MIDI 生命周期、Bank UI 与 16 键盘映射

**Files:**
- Create: `apps/web/src/midi/MidiInput.ts`
- Create: `apps/web/src/midi/MidiInput.test.ts`
- Create: `apps/web/src/ui/MidiPanel.tsx`
- Create: `apps/web/src/ui/MidiPanel.test.tsx`
- Modify: `apps/web/src/ui/PadMatrix16.tsx`
- Modify: `apps/web/src/ui/PadMatrix16.test.tsx`
- Modify: `apps/web/src/ui/WorkbenchShell.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Consumes: `padIndexForNote()`、`AudioEngine.triggerPad(index)`。
- Produces:
  - `class MidiInput`
  - `interface MidiSnapshot { support: "unknown"|"unsupported"|"available"; connection: "idle"|"requesting"|"connected"|"denied"|"disconnected"; devices: string[] }`
  - `MidiPanel` props `{ onTrigger(index), bank, onBankChange }`。

- [x] **Step 1: 写失败测试**

构造 fake `MIDIAccess` 与两个 fake input，验证：

```ts
input.emit([0x90, 36, 100]); // 触发
input.emit([0x90, 36, 0]);   // 不触发
input.emit([0x80, 36, 100]); // 不触发
expect(triggered).toEqual([0]);
```

再覆盖：监听全部 inputs、连接后新增设备、断开状态、权限拒绝、unsupported、dispose 后不触发。`MidiPanel.test.tsx` 覆盖 Connect、Direct/8-pad Learn、Bank A/B 切换和 Learn 未完成不覆盖旧 mapping。

`App.test.tsx` 覆盖：

```ts
await pressKey("1");
await pressKey("8");
await pressKey("Q");
await pressKey("I");
expect(engine.triggerPad).toHaveBeenNthCalledWith(1, 0);
expect(engine.triggerPad).toHaveBeenNthCalledWith(2, 7);
expect(engine.triggerPad).toHaveBeenNthCalledWith(3, 8);
expect(engine.triggerPad).toHaveBeenNthCalledWith(4, 15);
```

切换 MIDI Bank 后，相同键盘输入仍触发同一逻辑 index；repeat/meta/ctrl/alt、输入框和 contenteditable 内的按键不触发。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/midi/MidiInput.test.ts src/ui/MidiPanel.test.tsx src/ui/App.test.tsx
```

Expected: FAIL——适配器和面板尚不存在。

- [x] **Step 3: 实现适配器与 UI**

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

`App` 持有 `midiBank: MidiBank`，它只参与 8-pad Controller note 映射。键盘直接映射固定为：

```ts
const PAD_KEYS = [
  "1", "2", "3", "4", "5", "6", "7", "8",
  "Q", "W", "E", "R", "T", "Y", "U", "I",
] as const;
```

keydown 将 `event.key.toUpperCase()` 在 `PAD_KEYS` 中的位置直接作为 Pad index；不得读取 `midiBank`，也不使用 Shift 切 Bank。`PadMatrix16` 始终显示全部 16 个键盘提示；MIDI Bank 只显示在 MidiPanel / Status Bar，避免把硬件分页误解成数据或 UI 分页。

`MidiPanel` 的 note 回调通过当前 mapping 和 `midiBank` 得到 index 后调用 engine。切换 Bank 不发声，不改变 selected Pad；Direct-16 mapping 下 Bank 控件显示为“不适用”且不改变映射结果。

- [x] **Step 4: 运行 Web 全套验证**

```bash
cd apps/web
npm test
npm run build
```

Expected: 全部 PASS；jsdom 测试无真实 MIDI 权限请求。

- [x] **Step 5: Commit**

```bash
git add apps/web/src/midi apps/web/src/ui
git commit -m "feat(web): play sixteen Pads through MIDI banks"
```

---

### Task 6: Upload Preflight、Source/Processing/Failed 状态与拒绝语义

**Files:**
- Create: `apps/api/lmdj_api/preflight.py`
- Create: `apps/api/tests/test_preflight.py`
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/conftest.py`
- Modify: `apps/api/tests/test_app.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/ErrorPanel.tsx`
- Modify: `apps/web/src/ui/UploadPanel.tsx`
- Modify: `apps/web/src/ui/UploadingView.tsx`
- Create: `apps/web/src/ui/SourcePanel.tsx`
- Create: `apps/web/src/ui/SourcePanel.test.tsx`
- Create: `apps/web/src/ui/ProcessingPanel.tsx`
- Create: `apps/web/src/ui/ProcessingPanel.test.tsx`
- Modify: `apps/web/src/ui/WorkbenchShell.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces:
  - `UploadLimits(max_bytes: int, max_duration_seconds: float)`
  - `limits_from_env() -> UploadLimits`
  - `PreflightError(status_code: int, detail: dict[str, object])`
  - `persist_and_probe(file: UploadFile, destination: Path, limits: UploadLimits) -> AudioProbe`
  - `AudioProbe(format_name: str, codec_name: str, duration_seconds: float)`
- Extends: `ApiError` 增加 `detail?: unknown`；`uploadSong()` 将 API 的结构化 `detail` 转为用户可见错误。
- Produces: 与 loaded Workbench 共用 UI tokens 的 `Source`、`Processing`、`Failed` 页面状态；processing 只展示真实 Job state，不伪造百分比。

- [x] **Step 1: 写失败测试**

使用 stdlib `wave` 生成短 WAV；用 monkeypatch 的 `subprocess.run` 返回 ffprobe JSON。覆盖：WAV 成功、MP3 成功、超过 bytes→413、损坏/无 audio stream→415、伪造扩展名→415、超过 duration→422、环境默认值和覆盖值。

API 测试额外断言：

```python
response = client.post("/uploads", files={"file": oversized})
assert response.status_code == 413
assert not (tmp_path / "jobs").exists()
```

Web client / App 测试断言 413、415、422 分别显示服务端返回的最大字节数、支持格式和最大秒数，而不是统一的 `upload failed`；`ErrorPanel` 在 Upload 错误时使用“上传未通过检查”标题，在 Patch 校验错误时保留原标题。

再覆盖新版页面状态：

- Source 只提供 Upload 与载入 example，不出现 Generate / Line-in；
- Source 在选择前显示 WAV / MP3、`200 MiB`、`600 秒`限制；
- Processing 将 `queued → separating → patchifying → completed` 映射为 Input Validated → Stem Separation → Chop + Map → Patch Verify，无虚假进度百分比；
- 未知 Job state 显示 Unknown 和原始 state string，不回退 source；
- Failed 保留已选择的文件名和失败阶段，并提供 Retry / Back；
- Retry 重新经过 preflight，不直接复用失败 Job；
- 所有状态延续 Workbench 的 paper/ink/token 系统和 App Bar，不回退旧 graphite landing。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_preflight.py tests/test_app.py tests/test_config.py -q
cd ../web
npx vitest run \
  src/api/client.test.ts \
  src/ui/SourcePanel.test.tsx \
  src/ui/ProcessingPanel.test.tsx \
  src/ui/App.test.tsx
```

Expected: FAIL——preflight 模块、结构化 HTTP 拒绝路径和新版页面状态尚不存在。

- [x] **Step 3: 实现流式落盘与 ffprobe**

每次读取 `1024 * 1024` bytes，累计超过 `max_bytes` 立即删除 destination 并抛 413。Preflight error detail 固定为结构化对象：

```json
{"code":"file_too_large","max_bytes":209715200}
{"code":"unsupported_audio","supported":["wav","mp3"]}
{"code":"duration_too_long","max_duration_seconds":600}
```

只接受 `.wav` / `.mp3`；落盘后执行：

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

将 `AppState` 明确为 `source | processing | loaded | failed`。`processing` 保存 `{ file, jobId?, jobState }`，`failed` 保存 `{ file, failedAt, issues }`，使 Retry/Back 有足够来源信息；不要把错误折回无上下文的 source state。

`SourcePanel` 组合既有 DropZone / UploadPanel；`ProcessingPanel` 取代 loaded tree 中直接使用 UploadingView 的路径。它们与 `ErrorPanel` 复用 WorkbenchShell 的 App Bar / main canvas shell，但只渲染与当前真实能力相符的控件。状态文案从既有 Worker state 映射生成，不使用 `setInterval` 递增假进度；保留旧小组件仅作为内部输入控件，不再作为独立页面视觉系统。

Source、Processing、Ready、Review、Failed 与 Export 的层级和状态表现以 `docs/superpowers/specs/2026-07-24-stage1-creator-workspace-ui-references/stage1-product-states-v1.html` 校准；参考稿中的后置控件不得进入首条切片。

- [x] **Step 4: 运行 API 验证**

```bash
cd apps/api
.venv/bin/python -m pytest tests -q
cd ../web
npx vitest run \
  src/api/client.test.ts \
  src/ui/SourcePanel.test.tsx \
  src/ui/ProcessingPanel.test.tsx \
  src/ui/App.test.tsx
npm run build
```

Expected: API、Web 状态测试和 build 全部 PASS。

- [x] **Step 5: Commit**

```bash
git add apps/api/lmdj_api/preflight.py apps/api/lmdj_api/app.py apps/api/tests \
  apps/web/src/api apps/web/src/ui
git commit -m "feat(stage1): validate uploads and source states"
```

---

### Task 7: Key 分析与 Export Source Inventory

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

- [x] **Step 1: 写失败测试**

PFS Key 单测用合成 C-major chroma 替换 librosa 特征函数，断言 `C major` 和 `0 <= confidence <= 1`。子进程包装测试覆盖成功 JSON、非零退出、超时、`.venv-pfs` 缺失。

Inventory 测试构造含 `patch.json`、`stems/drums.wav`、samples、chart.mid 的 package，断言：

```python
assert source["schema"] == "lmdj.creator-export-source.v1"
assert source["patch"] == "patch.json"
assert source["stems"] == ["stems/drums.wav"]
assert source["samples"] == sorted({element.source_path for element in patch.elements})
assert source["midi"] == ["chart.mid"]
assert source["music"]["time_signature"]["source"] == "fixed-v1"
active_pattern_id = patch.scenes[0].pattern_ids[0]
active_pattern = next(p for p in patch.patterns if p.pattern_id == active_pattern_id)
assert source["music"]["loop"]["steps"] == active_pattern.length_steps
```

再覆盖缺 Key warning、只列真实 stem、绝对路径/`..` 路径拒绝。Job 测试断言 completed 前已写 `export-source.json`。

- [x] **Step 2: 运行测试确认失败**

```bash
workers/audio/.venv/bin/python -m pytest \
  workers/audio/tests/test_music_metadata.py \
  workers/audio/tests/test_export_source.py \
  workers/audio/tests/test_job.py -q
```

Expected: FAIL——三个新接口尚不存在。

- [x] **Step 3: 实现隔离分析和 inventory**

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

`build_export_source()` 仅从 Patch 获取 samples / MIDI / BPM / loop，从 `package_dir/stems/*.wav` 获取实际 stems。Loop 从 active scene 的首个 `pattern_id` 解析对应 Pattern，不直读 `patch.patterns[0]`；计算固定为 `steps=length_steps`、`beats=steps/4`、`bars=beats/4`。所有相对路径先 `resolve()` 并确认严格位于 package root 内。

`process_job()` 在 Patchify 后分析 `input_copy`，写 `export-source.json`，然后才 emit `completed`。

- [x] **Step 4: 运行 Worker 验证**

```bash
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
scripts/dev.sh smoke
```

Expected: Worker 全部 PASS；smoke 的 package 含 16-Pad `patch.json`。

- [x] **Step 5: Commit**

```bash
git add workers/audio
git commit -m "feat(worker): inventory Creator export sources"
```

---

### Task 8: 确定性 Creator Export Builder 与 API

**Files:**
- Create: `apps/api/lmdj_api/export_builder.py`
- Create: `apps/api/tests/test_export_builder.py`
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/test_app.py`

**Interfaces:**
- Produces:
  - `ExportIncomplete(missing: list[str])`
  - `inspect_creator_export(package_dir: Path) -> CreatorExportStatus`
  - `build_creator_export(package_dir: Path, output_dir: Path) -> Path`
  - `GET /jobs/{job_id}/export/status`
  - `GET /jobs/{job_id}/export`
- Status response: `{ status, downloadable, items, missing, warnings, music }`；`items` 固定为 stems、samples、midi、music 四项，每项状态为 `ready | review | missing`。
- Download response: complete 返回 ZIP attachment；incomplete 返回 HTTP 409 `{"detail":{"code":"export_incomplete","missing":[...]}}`。

- [x] **Step 1: 写失败测试**

覆盖 status inspection、完整 ZIP、同一 package 连续两次 SHA-256 相同、ZIP entry 顺序稳定、每个 manifest entry 的 bytes/hash、只列真实 stems、路径穿越拒绝、缺 patch/key/MIDI/all samples 分别 409。

API 测试断言未完成 Job 的 status / download 都为 409、本地未知 Job 为 404；完整 Job 的 status 返回 `downloadable: true` 和实际 Key，成功 download response 的 `content-disposition` 文件名为 `creator-export-{patch_id}.zip`；缺 Key 时 status 为 partial、music item 为 missing、download 为 409。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_export_builder.py tests/test_app.py -q
```

Expected: FAIL——builder 和 route 尚不存在。

- [x] **Step 3: 实现 Manifest 与 ZIP**

`inspect_creator_export()` 是唯一完整性判断入口，返回：

```json
{
  "status": "complete",
  "downloadable": true,
  "items": {
    "stems": {"status": "review", "paths": ["stems/drums.wav"]},
    "samples": {"status": "ready", "paths": ["samples/kick.wav"]},
    "midi": {"status": "ready", "paths": ["midi/chart.mid"]},
    "music": {"status": "ready", "missing": []}
  },
  "missing": [],
  "warnings": ["optional stems unavailable: vocals"],
  "music": {"bpm": 89.1, "key": {"value": "A minor", "confidence": 0.72}}
}
```

缺必需项时 `status: "partial"`、`downloadable: false`。可选 Stem 缺失只形成 Review/warning，不进入 required `missing`。Builder 和 status route 必须复用 inspection 结果，不允许两套完整性规则漂移。

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

两个 API route 使用既有 `_job_dir()` 与 completed/package_dir guard。status route 返回 inspection JSON；download route 捕获 `ExportIncomplete` 后抛 `HTTPException(status_code=409, detail={"code": "export_incomplete", "missing": error.missing})`，不返回 ZIP。

- [x] **Step 4: 运行 API 全套验证**

```bash
cd apps/api
.venv/bin/python -m pytest tests -q
```

Expected: 全部 PASS。

- [x] **Step 5: Commit**

```bash
git add apps/api/lmdj_api apps/api/tests
git commit -m "feat(api): build deterministic Creator export packs"
```

---

### Task 9: ExportChecklist 与 Creator Export 下载体验

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Create: `apps/web/src/ui/ExportChecklist.tsx`
- Create: `apps/web/src/ui/ExportChecklist.test.tsx`
- Modify: `apps/web/src/ui/ContextInspector.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces:
  - `fetchCreatorExportStatus(base, jobId): Promise<CreatorExportStatus>`
  - `downloadCreatorExport(base, jobId): Promise<Blob>`
  - `type ExportItemStatus = "ready" | "review" | "missing"`
  - `ExportChecklist` props `{ apiBase, jobId, status, apiClient, onStatusChange }`
- Consumes: Task 6 已加入的 `ApiError.detail?: unknown`。
- App loaded state扩为 `{ bundle, source, exportState }`；`source` 为 `{ kind:"api"; base; jobId } | { kind:"local"|"example" }`，`exportState` 同时驱动 ExportChecklist、App Bar Key 和 Status Bar readiness。

- [x] **Step 1: 写失败测试**

client 测试覆盖 status JSON、成功 Blob、409 `body.detail.missing` 保留在 `ApiError.detail`、网络错误。组件测试固定覆盖四种可见语义：

- Stems、Samples / Slices、MIDI、BPM / Key / Time Signature / Loop Metadata 每项显示 Ready / Review / Missing；
- 有 warning 但必需项齐全时总体为 Review，仍允许下载；
- 409 后总体为 Partial，逐项列出 missing，且不创建 Blob URL、不点击下载；
- 请求失败后可 Retry，PadMatrix16 与当前 selection 仍存在。

App 测试覆盖 API Job 切到 Export mode 时获取 status、Context Inspector 显示“导出 Creator Pack”、App Bar 显示服务端 Key；拖放和 example 明确显示“仅远端 Job 可导出”，不发 status 请求，也不渲染伪可用下载按钮。

- [x] **Step 2: 运行测试确认失败**

```bash
cd apps/web
npx vitest run src/api/client.test.ts src/ui/ExportChecklist.test.tsx src/ui/App.test.tsx
```

Expected: FAIL——download client 和 ExportChecklist 尚不存在。

- [x] **Step 3: 实现下载与 source provenance**

`fetchCreatorExportStatus()` GET `/jobs/{jobId}/export/status`，以服务端 inspection 结果作为 checklist 唯一事实；不得从 Patch 猜测 Stem 或 Key 是否存在。`downloadCreatorExport()` GET `/jobs/{jobId}/export`；非 2xx 尝试读取 JSON 并附到 `ApiError.detail`。只有 2xx Blob 交给 `ExportChecklist`：

```ts
const url = URL.createObjectURL(blob);
const anchor = document.createElement("a");
anchor.href = url;
anchor.download = filename;
anchor.click();
URL.revokeObjectURL(url);
```

`enterLoaded()` 同时接收 source provenance；API 路径保留 normalized base + jobId，example/local 分别标记。切到 Export mode 时拉取一次 status，并将其规范化为 loaded state 的 `exportState`，从而同步 Checklist、App Bar Key 和 Status Bar；不改变 App phase、不 stop engine、不清空 bundle。409 显示 `missing.join("、")` 与重试按钮，并刷新 status 为 Partial；不得把 409 response body 包成 `.zip` 或触发 anchor。

Checklist 直接呈现服务端四个 item 状态：缺必需项为 Missing；可选 Stem 或质量 warning 为 Review；其余为 Ready。Full Take 和 DAW-specific project 不出现在首条切片清单。UI 使用文字、图标和边框共同编码状态，不只依赖颜色。

- [x] **Step 4: 运行 Web 全套验证**

```bash
cd apps/web
npm run check-contract
npm test
npm run build
```

Expected: 全部 PASS。

- [x] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(web): download Creator export packs"
```

---

### Task 10: 全链路验证与 Release Evidence

**Files:**
- Modify: `scripts/dev.sh`
- Modify: `README.md`
- Modify: `apps/api/README.md` if created by the implementation branch; otherwise document API commands in root `README.md`.
- Create: `docs/release-evidence/2026-07-24-stage1-creator-core-and-ui.md`

**Interfaces:**
- Produces: `scripts/dev.sh creator-smoke <audio>`，依次上传、轮询、校验 16 Pad、下载两次 Export 并比较 SHA-256。

- [x] **Step 1: 给 smoke helper 写 shell-level 验证**

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

- [x] **Step 2: 运行所有自动门禁**

```bash
scripts/dev.sh test
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
cd apps/web && npm run check-contract && npm test && npm run test:e2e && npm run build
```

Expected: 四组全部 PASS；Web 门禁同时包含 contract、Vitest、五 viewport Playwright 和 production build。

- [x] **Step 3: 连续运行固定音频三次**

启动 API/Web 后，对同一固定音频执行三次 `scripts/dev.sh creator-smoke <audio>`。在 evidence 文档逐次记录 job_id、patch_id、16 Pad 检查、两个 ZIP SHA-256 和结果；三次 patch_id 必须一致，每次两个 ZIP hash 必须一致。

同时保存 `1440×900`、`1280×720`、`1024×768`、`768×1024`、`390×844` 的 Workbench 截图或 Playwright artifact，并记录：

- Pattern 始终位于 PadMatrix16 上方；
- `>=960px` 是 8×2，`360–959px` 是 4×4；
- 4×4 row-gap 与 column-gap 相等；
- 16 个 Pad 都是正方形；常驻 Inspector 与正常关闭状态的 Status Bar 不覆盖 Pad；960–1279px 的抽屉和 600–959px 的覆盖式抽屉打开时，当前 selected / playing Pad 的 trigger feedback 可见；360–599px 的全高参数 Sheet 有可访问的关闭路径，关闭后保留 selection / playback / mode 状态；
- Source / Processing / Failed / Loaded / Export Checklist 与 reference 使用同一视觉 token 和层级；
- Generate、Line-in、Chop、AI Preview、Take、Pattern A–D 没有伪交互入口。

- [ ] **Step 4: 实体 MIDI 与 Ableton Live 验收**

在 evidence 文档记录控制器型号、浏览器版本和：

- 16-pad 控制器 note `36..51` 直接对应 Pad `0..15`；
- 8-pad 控制器 Bank A 的 8 键对应 Pad `0..7`；
- 8-pad 控制器 Bank B 的 8 键对应 Pad `8..15`；
- 键盘 `1..8` 对应 Pad `0..7`，`Q..I` 对应 Pad `8..15`，切换 MIDI Bank 不改变键盘结果；
- 有素材 Pad 发出正确声音；
- empty Pad 无声且无异常；
- ExportChecklist 可见 Ready / Review / Missing / Partial，必需项缺失时不下载伪成功 ZIP；
- ZIP 中 Stems、Samples、MIDI、Manifest 可在 Ableton Live 导入；
- 按 Manifest BPM 设置工程后可继续编排；
- 非开发者在无口头指导下完成 Upload、MIDI 演奏、Export。

每项记录 `PASS` 或 `FAIL`；任一 FAIL 阻止 PR 标记 Ready。

- [x] **Step 5: Commit**

```bash
git add scripts/dev.sh README.md docs/release-evidence/2026-07-24-stage1-creator-core-and-ui.md
[ ! -f apps/api/README.md ] || git add apps/api/README.md
git commit -m "docs: record Stage 1 Creator release evidence"
```

- [x] **Step 6: 最终分支检查**

```bash
git status --short
git log --oneline --decorate -10
```

Expected: 工作区干净；Task 1–10 均有独立 Conventional Commit。
