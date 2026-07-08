# Web Patch View Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `apps/web/` 落地 patch.json（`lmdj.patch.v1`）的第一个消费者——纯客户端 8-pad Focus View 工作台原型（pattern 回放 + pad 触发 + pad 静音）。

**Architecture:** 三层分离：`src/patch/`（契约层：schema 拷贝 + codegen 类型 + loader）、`src/engine/`（裸 WebAudio，lookahead 调度，不依赖 React）、`src/ui/`（React 组件）。设计依据：`docs/superpowers/specs/2026-07-07-lmdj-web-patch-view-design.md`。

**Tech Stack:** Vite + React 19 + TypeScript、ajv（draft 2020-12）、json-schema-to-typescript、Vitest + React Testing Library + jsdom。无 Tone.js、无后端。

## Global Constraints

- **契约纯度**：前端只读 `patch.json`；拖入目录中的 `lanes.json`/`chart.mid`/`report.json` 一律无视。
- **schema 单一真相源**：`packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`；web 侧拷贝与 `types.ts` 均为生成物（带"不得手改"注释头），由 `npm run sync-contract` 产生，`npm run check-contract` 防漂移。
- **scene 读取路径**：engine/UI 的 pattern 一律经 `activeScene（v1 = scenes[0]）→ pattern_ids → patterns` 解析，**不得直读 `patterns[0]`**；scene 引用未知 pattern 是加载错误。
- **pad 触发**：点击/按键触发 `behavior.element_ids` **全组**（分层同击）；`element_id`（primary）仅作标签。
- **reserved actions**（`scene_fill`/`scene_drop`/`mute_group`/`ai_variation`）与 `empty`：渲染禁用/空态，交互 no-op，不报错。
- **缺失素材模型**：PatchBundle 保留完整 patch（不预过滤 notes）+ `playableElementIds`/`missingElementIds`；engine 调度时查 buffer 跳过；StepGrid 完整显示缺失 lane 并标红。
- **调度**：`stepDuration = 60 / bpm / 4`；lookahead ~25ms tick / ~120ms 预排；pattern 按 `length_steps` 回卷；velocity 读取不映射。
- **状态色**：黑底之上仅 active green `#33ff66` / warning red `#ff4444` / rejected yellow `#ffcc33` / disabled gray `#555` 四色 + 亮度分级。
- **键盘**：`A S D F` → pad 0-3，`Z X C V` → pad 4-7；pad 右键 = 静音 toggle（`contextmenu` 必须 `preventDefault()`）。
- **内置示例**：`npm run make-example` 脚本生成（源 = demo `output/testsong` 的 patchify 产物）；只含 `patch.json` + `samples/*.wav`；总体积 ≤ 2MB；wav 走仓库既有 LFS 策略。
- **测试**：Vitest 全局 jsdom 环境；loader golden fixture 来自真实 patchify 输出；错误路径 fixture 从 golden 派生破坏。真实音频 e2e 不做。
- 范围外：Scenes 切换 UI、Modes、AI Talk、16-pad、量化触发、trigger_group 组员展开、录音/导出、移动端触控、任何后端。

---

## File Structure

- Create: `apps/web/package.json`、`vite.config.ts`、`tsconfig.json`、`index.html`、`src/main.tsx`、`src/test-setup.ts`
- Create: `apps/web/scripts/sync-contract.mjs`（拷 schema + codegen types.ts）
- Create: `apps/web/src/patch/schema/lmdj.patch.v1.schema.json`（生成物）、`src/patch/types.ts`（生成物）
- Create: `apps/web/src/patch/contract.test.ts`（防漂移）
- Create: `apps/web/src/patch/loader.ts` + `loader.test.ts` + `__fixtures__/patch.golden.json`
- Create: `apps/web/src/engine/clock.ts` + `clock.test.ts`（纯函数）
- Create: `apps/web/src/engine/AudioEngine.ts` + `AudioEngine.test.ts` + `src/test/fakes.ts`
- Create: `apps/web/src/ui/theme.css`、`App.tsx`、`DropZone.tsx`、`ErrorPanel.tsx` + `App.test.tsx`
- Create: `apps/web/src/ui/useEngine.ts`、`PadGrid.tsx`、`Transport.tsx` + `PadGrid.test.tsx`
- Create: `apps/web/src/ui/StepGrid.tsx`、`Inspector.tsx` + `StepGrid.test.tsx`
- Create: `apps/web/scripts/make-example.mjs`、`apps/web/README.md`
- Modify: 根 `.gitignore`（`node_modules/`、`dist/`）、`apps/README.md`（标注 web 已落地）

---

### Task 1: Scaffold + 契约同步（sync-contract / check-contract）

**Files:**
- Create: `apps/web/package.json`、`apps/web/vite.config.ts`、`apps/web/tsconfig.json`、`apps/web/index.html`、`apps/web/src/main.tsx`、`apps/web/src/test-setup.ts`
- Create: `apps/web/scripts/sync-contract.mjs`
- Create: `apps/web/src/patch/contract.test.ts`
- 生成: `apps/web/src/patch/schema/lmdj.patch.v1.schema.json`、`apps/web/src/patch/types.ts`
- Modify: 根 `.gitignore`

**Interfaces:**
- Consumes: `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`（只读）。
- Produces: `src/patch/types.ts` 导出 `LmdjPatchV1`（后续所有任务的 patch 类型根）；npm scripts `sync-contract` / `check-contract`；可构建的 Vite 应用骨架。

- [ ] **Step 1: 写 scaffold 配置文件**

Create `apps/web/package.json`:

```json
{
  "name": "lmdj-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "sync-contract": "node scripts/sync-contract.mjs",
    "check-contract": "vitest run src/patch/contract.test.ts",
    "make-example": "node scripts/make-example.mjs"
  },
  "dependencies": {
    "ajv": "^8.17.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "json-schema-to-typescript": "^15.0.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

Create `apps/web/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  base: "./",
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
```

Create `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vite/client"]
  },
  "include": ["src", "scripts"]
}
```

Create `apps/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>LMDJ Patch View</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `apps/web/src/main.tsx`（App 在 Task 5 落地，先占位保证可构建）:

```tsx
import { createRoot } from "react-dom/client";

createRoot(document.getElementById("root")!).render(<div>LMDJ Patch View</div>);
```

Create `apps/web/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Modify 根 `.gitignore` 的 `### Python` 节之前追加:

```gitignore
### Node
node_modules/
dist/
```

- [ ] **Step 2: 安装依赖并确认可构建**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm install
npm run build
```

Expected: `vite build` 成功产出 `dist/`（占位页面）。`package-lock.json` 生成，随本任务提交。

- [ ] **Step 3: 写 failing 契约防漂移测试**

Create `apps/web/src/patch/contract.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";
import { describe, expect, it } from "vitest";

const localSchemaUrl = new URL("./schema/lmdj.patch.v1.schema.json", import.meta.url);
const sourceSchemaUrl = new URL(
  "../../../../packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json",
  import.meta.url,
);
const typesUrl = new URL("./types.ts", import.meta.url);

const HEADER = `// GENERATED by npm run sync-contract — DO NOT EDIT.
// Source of truth: packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json
`;

describe("contract sync (npm run sync-contract)", () => {
  it("web schema copy is byte-identical to core-models source of truth", () => {
    const local = readFileSync(fileURLToPath(localSchemaUrl), "utf8");
    const source = readFileSync(fileURLToPath(sourceSchemaUrl), "utf8");
    expect(local).toBe(source);
  });

  it("types.ts is freshly generated from the schema", async () => {
    const schema = JSON.parse(readFileSync(fileURLToPath(localSchemaUrl), "utf8"));
    const expected = await compile(schema, "LmdjPatchV1", { bannerComment: HEADER });
    const actual = readFileSync(fileURLToPath(typesUrl), "utf8");
    expect(actual).toBe(expected);
  });
});
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm run check-contract
```

Expected: FAIL——`ENOENT ... schema/lmdj.patch.v1.schema.json`（拷贝尚不存在）。

- [ ] **Step 5: 写 sync-contract 脚本并执行**

Create `apps/web/scripts/sync-contract.mjs`:

```js
// 从 core-models 同步 lmdj.patch.v1 契约：拷贝 schema + 重新生成 types.ts。
// 契约变更时手动执行：npm run sync-contract
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = resolve(
  webRoot,
  "../../packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json",
);
const SCHEMA_COPY = resolve(webRoot, "src/patch/schema/lmdj.patch.v1.schema.json");
const TYPES = resolve(webRoot, "src/patch/types.ts");
const HEADER = `// GENERATED by npm run sync-contract — DO NOT EDIT.
// Source of truth: packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json
`;

mkdirSync(dirname(SCHEMA_COPY), { recursive: true });
copyFileSync(SOURCE, SCHEMA_COPY);
const schema = JSON.parse(readFileSync(SCHEMA_COPY, "utf8"));
const ts = await compile(schema, "LmdjPatchV1", { bannerComment: HEADER });
writeFileSync(TYPES, ts);
console.log(`synced ${SCHEMA_COPY}\nregenerated ${TYPES}`);
```

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm run sync-contract
```

Expected: 打印 synced/regenerated 两行；`src/patch/schema/lmdj.patch.v1.schema.json` 与 `src/patch/types.ts`（含 `export interface LmdjPatchV1`）出现。

- [ ] **Step 6: 跑测试确认通过**

```bash
npm run check-contract
```

Expected: `2 passed`。

- [ ] **Step 7: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web .gitignore
git commit -m "feat(web): scaffold vite app with contract sync and drift check"
```

---

### Task 2: Patch Loader

**Files:**
- Create: `apps/web/src/patch/loader.ts`
- Create: `apps/web/src/patch/__fixtures__/patch.golden.json`
- Create: `apps/web/src/patch/loader.test.ts`

**Interfaces:**
- Consumes: `LmdjPatchV1` from Task 1 的 `./types`；schema 拷贝。
- Produces（后续任务全部依赖）:
  - `type Patch = LmdjPatchV1`、`type Pad`、`type Pattern`、`type Note`、`type PatchElement`（`Patch` 的索引派生型）
  - `interface PatchBundle<B> { patch: Patch; buffers: Map<string, B>; playableElementIds: Set<string>; missingElementIds: Set<string>; warnings: string[] }`
  - `class PatchValidationError extends Error { issues: string[] }`
  - `loadPatch<B>(files: Map<string, ArrayBuffer>, decodeAudio: (data: ArrayBuffer) => Promise<B>): Promise<PatchBundle<B>>`（files 的 key 为**包相对路径**，如 `patch.json`、`samples/kick.wav`）
  - `scenePatterns(patch: Patch): Pattern[]`（scene 契约读取路径的唯一实现）
  - `padElementIds(pad: Pad): string[]`

- [ ] **Step 1: 生成 golden fixture（真实 patchify 输出）**

```bash
cd /Users/endaye/Projects/lmdj
scripts/dev.sh smoke   # 确保 demo output/testsong 及其 patch.json 存在
mkdir -p apps/web/src/patch/__fixtures__
cp references/demos/lmdj-song-pipeline/output/testsong/patch.json \
   apps/web/src/patch/__fixtures__/patch.golden.json
```

Expected: fixture 为真实 `testsong-*` patch（5 elements、45 notes、length_steps 64）。

- [ ] **Step 2: 写 failing loader 测试**

Create `apps/web/src/patch/loader.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import golden from "./__fixtures__/patch.golden.json";
import { loadPatch, PatchValidationError, padElementIds, scenePatterns, type Patch } from "./loader";

const enc = (data: unknown) => new TextEncoder().encode(JSON.stringify(data)).buffer as ArrayBuffer;
const fakeDecode = async (data: ArrayBuffer) => ({ decodedBytes: data.byteLength });

/** golden patch + 每个 element 一份占位 wav 字节 */
function goldenFiles(patch: unknown = golden): Map<string, ArrayBuffer> {
  const files = new Map<string, ArrayBuffer>([["patch.json", enc(patch)]]);
  for (const el of (patch as Patch).elements) {
    files.set(el.source_path, new ArrayBuffer(8));
  }
  return files;
}

describe("loadPatch", () => {
  it("loads the golden patch with all elements playable", async () => {
    const bundle = await loadPatch(goldenFiles(), fakeDecode);

    expect(bundle.patch.schema).toBe("lmdj.patch.v1");
    expect(bundle.playableElementIds.size).toBe(bundle.patch.elements.length);
    expect(bundle.missingElementIds.size).toBe(0);
    expect(bundle.warnings).toEqual([]);
    expect(bundle.buffers.size).toBe(bundle.patch.elements.length);
  });

  it("rejects a directory without patch.json", async () => {
    await expect(loadPatch(new Map(), fakeDecode)).rejects.toThrow(PatchValidationError);
  });

  it("rejects schema-invalid patch.json with issue paths", async () => {
    const broken = structuredClone(golden) as Patch;
    (broken.pads[0] as { action: string }).action = "definitely_not_an_action";
    const err = await loadPatch(goldenFiles(broken), fakeDecode).catch((e) => e);

    expect(err).toBeInstanceOf(PatchValidationError);
    expect((err as PatchValidationError).issues.join("\n")).toContain("/pads/0/action");
  });

  it("marks missing wav as missing element without blocking the patch", async () => {
    const files = goldenFiles();
    const first = (golden as Patch).elements[0];
    files.delete(first.source_path);

    const bundle = await loadPatch(files, fakeDecode);
    expect(bundle.missingElementIds.has(first.element_id)).toBe(true);
    expect(bundle.playableElementIds.has(first.element_id)).toBe(false);
    expect(bundle.warnings.some((w) => w.includes(first.source_path))).toBe(true);
    // note 数据不预过滤
    expect(bundle.patch.patterns[0].notes.length).toBe((golden as Patch).patterns[0].notes.length);
  });

  it("marks undecodable wav as missing element", async () => {
    const failing = async () => {
      throw new Error("decode failed");
    };
    const bundle = await loadPatch(goldenFiles(), failing);
    expect(bundle.missingElementIds.size).toBe((golden as Patch).elements.length);
  });

  it("rejects a scene referencing an unknown pattern", async () => {
    const broken = structuredClone(golden) as Patch;
    broken.scenes[0].pattern_ids = ["pattern_ghost"];
    await expect(loadPatch(goldenFiles(broken), fakeDecode)).rejects.toThrow(/pattern_ghost/);
  });
});

describe("scenePatterns", () => {
  it("resolves patterns via activeScene.pattern_ids, not patterns[0]", () => {
    const patch = structuredClone(golden) as Patch;
    const real = structuredClone(patch.patterns[0]);
    real.pattern_id = "pattern_real";
    const decoy = structuredClone(patch.patterns[0]);
    decoy.pattern_id = "pattern_decoy";
    decoy.notes = [];
    patch.patterns = [decoy, real]; // decoy 在前
    patch.scenes[0].pattern_ids = ["pattern_real"];

    const resolved = scenePatterns(patch);
    expect(resolved.map((p) => p.pattern_id)).toEqual(["pattern_real"]);
    expect(resolved[0].notes.length).toBeGreaterThan(0);
  });
});

describe("padElementIds", () => {
  it("returns the full group for trigger_group pads", () => {
    const drums = (golden as Patch).pads[0];
    expect(padElementIds(drums)).toEqual(
      (drums.behavior as { element_ids: string[] }).element_ids,
    );
    expect(padElementIds(drums).length).toBeGreaterThan(1);
  });

  it("returns [] for empty/reserved pads", () => {
    const patch = golden as Patch;
    const reserved = patch.pads.find((p) => p.action === "scene_fill")!;
    expect(padElementIds(reserved)).toEqual([]);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/patch/loader.test.ts
```

Expected: FAIL——`Cannot find module './loader'`。

- [ ] **Step 4: 实现 loader**

Create `apps/web/src/patch/loader.ts`:

```ts
import Ajv2020 from "ajv/dist/2020";
import schema from "./schema/lmdj.patch.v1.schema.json";
import type { LmdjPatchV1 } from "./types";

export type Patch = LmdjPatchV1;
export type Pad = Patch["pads"][number];
export type PatchElement = Patch["elements"][number];
export type Pattern = Patch["patterns"][number];
export type Note = Pattern["notes"][number];

export interface PatchBundle<B = AudioBuffer> {
  patch: Patch;
  buffers: Map<string, B>;
  playableElementIds: Set<string>;
  missingElementIds: Set<string>;
  warnings: string[];
}

export class PatchValidationError extends Error {
  constructor(public readonly issues: string[]) {
    super(`patch.json failed lmdj.patch.v1 validation:\n${issues.join("\n")}`);
    this.name = "PatchValidationError";
  }
}

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validate = ajv.compile(schema as object);

/** scene 契约读取路径的唯一实现：activeScene（v1 = scenes[0]）→ pattern_ids → patterns */
export function scenePatterns(patch: Patch): Pattern[] {
  const scene = patch.scenes[0];
  const byId = new Map(patch.patterns.map((p) => [p.pattern_id, p]));
  return scene.pattern_ids.map((id) => {
    const pattern = byId.get(id);
    if (!pattern) {
      throw new PatchValidationError([
        `scene ${scene.scene_id} references unknown pattern: ${id}`,
      ]);
    }
    return pattern;
  });
}

/** trigger 类 pad 的全组 element id；empty/reserved 返回 [] */
export function padElementIds(pad: Pad): string[] {
  if (pad.action !== "trigger_element" && pad.action !== "trigger_group") return [];
  const ids = (pad.behavior as { element_ids?: unknown }).element_ids;
  if (Array.isArray(ids)) return ids.filter((id): id is string => typeof id === "string");
  return pad.element_id ? [pad.element_id] : [];
}

export async function loadPatch<B>(
  files: Map<string, ArrayBuffer>,
  decodeAudio: (data: ArrayBuffer) => Promise<B>,
): Promise<PatchBundle<B>> {
  const raw = files.get("patch.json");
  if (!raw) throw new PatchValidationError(["patch.json not found in dropped directory"]);

  let data: unknown;
  try {
    data = JSON.parse(new TextDecoder().decode(raw));
  } catch (error) {
    throw new PatchValidationError([`patch.json is not valid JSON: ${String(error)}`]);
  }

  if (!validate(data)) {
    throw new PatchValidationError(
      (validate.errors ?? []).map((e) => `${e.instancePath || "/"} ${e.message ?? "invalid"}`),
    );
  }
  const patch = data as Patch;
  scenePatterns(patch); // scene→pattern 引用完整性在加载期 fail-fast

  const buffers = new Map<string, B>();
  const playableElementIds = new Set<string>();
  const missingElementIds = new Set<string>();
  const warnings: string[] = [];

  for (const element of patch.elements) {
    const bytes = files.get(element.source_path);
    if (!bytes) {
      missingElementIds.add(element.element_id);
      warnings.push(`missing sample file: ${element.source_path} (${element.element_id})`);
      continue;
    }
    try {
      buffers.set(element.element_id, await decodeAudio(bytes.slice(0)));
      playableElementIds.add(element.element_id);
    } catch {
      missingElementIds.add(element.element_id);
      warnings.push(`failed to decode: ${element.source_path} (${element.element_id})`);
    }
  }

  return { patch, buffers, playableElementIds, missingElementIds, warnings };
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
npx vitest run src/patch/loader.test.ts
```

Expected: `9 passed`。

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/patch
git commit -m "feat(web): patch loader with scene contract and missing-asset model"
```

---

### Task 3: Engine 时钟纯函数

**Files:**
- Create: `apps/web/src/engine/clock.ts`
- Create: `apps/web/src/engine/clock.test.ts`

**Interfaces:**
- Consumes: `Note` from Task 2 的 `../patch/loader`。
- Produces:
  - `stepDuration(bpm: number): number`
  - `interface ScheduledNote { note: Note; time: number }`（time = 自 transport 起点的秒）
  - `notesInWindow(notes: readonly Note[], lengthSteps: number, stepDur: number, from: number, to: number): ScheduledNote[]`（半开区间 `[from, to)`，跨 loop 边界回卷）
  - `playheadStep(elapsed: number, lengthSteps: number, stepDur: number): number`

- [ ] **Step 1: 写 failing 测试**

Create `apps/web/src/engine/clock.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { Note } from "../patch/loader";
import { notesInWindow, playheadStep, stepDuration } from "./clock";

const note = (step: number, element_id = "el_kick"): Note => ({
  element_id,
  lane: 0,
  pitch: 36,
  step,
  velocity: 100,
});

describe("stepDuration", () => {
  it("is a 16th note at the given bpm", () => {
    expect(stepDuration(120)).toBeCloseTo(0.125);
    expect(stepDuration(89.1)).toBeCloseTo(60 / 89.1 / 4);
  });
});

describe("notesInWindow", () => {
  const stepDur = 0.125; // bpm 120
  const lengthSteps = 16; // loop = 2s

  it("returns notes whose time falls in [from, to)", () => {
    const notes = [note(0), note(4), note(8)];
    const hits = notesInWindow(notes, lengthSteps, stepDur, 0.4, 1.1);
    expect(hits.map((h) => [h.note.step, h.time])).toEqual([[4, 0.5], [8, 1.0]]);
  });

  it("is half-open: a note exactly at `to` is excluded, at `from` included", () => {
    const notes = [note(4)];
    expect(notesInWindow(notes, lengthSteps, stepDur, 0.5, 0.6)).toHaveLength(1);
    expect(notesInWindow(notes, lengthSteps, stepDur, 0.4, 0.5)).toHaveLength(0);
  });

  it("wraps across the loop boundary", () => {
    const notes = [note(0), note(15)];
    // loop 长 2s；窗口 [1.9, 2.1) 不含 step15@1.875，应含下一圈 step0@2.0
    const hits = notesInWindow(notes, lengthSteps, stepDur, 1.9, 2.1);
    expect(hits.map((h) => [h.note.step, h.time])).toEqual([[0, 2.0]]);
  });

  it("covers multiple loops in one window", () => {
    const notes = [note(0)];
    const hits = notesInWindow(notes, 4, stepDur, 0, 1.6); // loop=0.5s → step0 @ 0,0.5,1.0,1.5
    expect(hits.map((h) => h.time)).toEqual([0, 0.5, 1.0, 1.5]);
  });
});

describe("playheadStep", () => {
  it("advances and wraps", () => {
    expect(playheadStep(0, 16, 0.125)).toBe(0);
    expect(playheadStep(0.13, 16, 0.125)).toBe(1);
    expect(playheadStep(2.0, 16, 0.125)).toBe(0); // 整圈回卷
    expect(playheadStep(1.999, 16, 0.125)).toBe(15);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/engine/clock.test.ts
```

Expected: FAIL——`Cannot find module './clock'`。

- [ ] **Step 3: 实现**

Create `apps/web/src/engine/clock.ts`:

```ts
import type { Note } from "../patch/loader";

/** 16 分音符时长（秒） */
export function stepDuration(bpm: number): number {
  return 60 / bpm / 4;
}

export interface ScheduledNote {
  note: Note;
  time: number; // 自 transport 起点的秒
}

/** 半开窗口 [from, to) 内应发声的 note，跨 loop 回卷 */
export function notesInWindow(
  notes: readonly Note[],
  lengthSteps: number,
  stepDur: number,
  from: number,
  to: number,
): ScheduledNote[] {
  const loopDur = lengthSteps * stepDur;
  const out: ScheduledNote[] = [];
  const firstLoop = Math.floor(from / loopDur);
  const lastLoop = Math.floor(to / loopDur);
  for (let loop = firstLoop; loop <= lastLoop; loop += 1) {
    for (const note of notes) {
      const time = loop * loopDur + note.step * stepDur;
      if (time >= from && time < to) out.push({ note, time });
    }
  }
  return out.sort((a, b) => a.time - b.time);
}

/** 当前播放头所在 step（回卷到 [0, lengthSteps)） */
export function playheadStep(elapsed: number, lengthSteps: number, stepDur: number): number {
  const loopDur = lengthSteps * stepDur;
  const inLoop = ((elapsed % loopDur) + loopDur) % loopDur;
  return Math.floor(inLoop / stepDur) % lengthSteps;
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
npx vitest run src/engine/clock.test.ts
```

Expected: `6 passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/engine
git commit -m "feat(web): pure clock functions for step scheduling"
```

---

### Task 4: AudioEngine

**Files:**
- Create: `apps/web/src/test/fakes.ts`
- Create: `apps/web/src/engine/AudioEngine.ts`
- Create: `apps/web/src/engine/AudioEngine.test.ts`

**Interfaces:**
- Consumes: `stepDuration` / `notesInWindow` / `playheadStep` from Task 3；`PatchBundle` / `Pattern` / `scenePatterns` / `padElementIds` from Task 2。
- Produces（UI 任务依赖）:
  - `interface AudioLike { currentTime: number; destination: unknown; createGain(): GainLike; createBufferSource(): SourceLike; resume(): Promise<void> }`（`GainLike`/`SourceLike` 见实现）
  - `class AudioEngine`：`load(bundle: PatchBundle<unknown>): void`、`play(): Promise<void>`、`stop(): void`、`get playing: boolean`、`triggerPad(index: number): void`、`toggleMutePad(index: number): void`、`isPadMuted(index: number): boolean`、`playhead(): number | null`、`subscribe(fn: () => void): () => void`

- [ ] **Step 1: 写 fake AudioContext**

Create `apps/web/src/test/fakes.ts`:

```ts
export class FakeGain {
  gain = { value: 1 };
  connected: unknown[] = [];
  connect(dst: unknown): void {
    this.connected.push(dst);
  }
}

export class FakeSource {
  buffer: unknown = null;
  connectedTo: unknown = null;
  startedAt: number[] = [];
  connect(dst: unknown): void {
    this.connectedTo = dst;
  }
  start(when = 0): void {
    this.startedAt.push(when);
  }
}

export class FakeAudioContext {
  currentTime = 0;
  destination = { fake: "destination" };
  gains: FakeGain[] = [];
  sources: FakeSource[] = [];
  resumed = 0;

  createGain(): FakeGain {
    const gain = new FakeGain();
    this.gains.push(gain);
    return gain;
  }
  createBufferSource(): FakeSource {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
  async resume(): Promise<void> {
    this.resumed += 1;
  }
}
```

- [ ] **Step 2: 写 failing engine 测试**

Create `apps/web/src/engine/AudioEngine.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch, PatchBundle } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "./AudioEngine";

function makeBundle(patch: Patch = structuredClone(golden) as Patch): PatchBundle<unknown> {
  const buffers = new Map<string, unknown>();
  for (const el of patch.elements) buffers.set(el.element_id, { buf: el.element_id });
  return {
    patch,
    buffers,
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
}

describe("AudioEngine", () => {
  let ctx: FakeAudioContext;
  let engine: AudioEngine;

  beforeEach(() => {
    vi.useFakeTimers();
    ctx = new FakeAudioContext();
    engine = new AudioEngine(ctx);
  });
  afterEach(() => {
    engine.stop();
    vi.useRealTimers();
  });

  it("triggerPad plays the whole group simultaneously", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const drums = bundle.patch.pads[0]; // trigger_group
    const ids = padElementIds(drums);
    expect(ids.length).toBeGreaterThan(1);

    engine.triggerPad(0);
    expect(ctx.sources).toHaveLength(ids.length); // kick+snare+hat 同击
  });

  it("reserved and empty pads are no-ops", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    for (const pad of bundle.patch.pads) {
      if (pad.action === "trigger_element" || pad.action === "trigger_group") continue;
      engine.triggerPad(pad.index);
      engine.toggleMutePad(pad.index);
    }
    expect(ctx.sources).toHaveLength(0);
    expect(bundle.patch.pads.every((p) => !engine.isPadMuted(p.index))).toBe(true);
  });

  it("toggleMutePad zeroes the whole group's gains and restores them", () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const ids = new Set(padElementIds(bundle.patch.pads[0]));

    engine.toggleMutePad(0);
    expect(engine.isPadMuted(0)).toBe(true);
    const groupGains = ctx.gains.filter((_, i) =>
      ids.has(bundle.patch.elements[i].element_id),
    );
    expect(groupGains.length).toBe(ids.size);
    expect(groupGains.every((g) => g.gain.value === 0)).toBe(true);

    engine.toggleMutePad(0);
    expect(engine.isPadMuted(0)).toBe(false);
    expect(groupGains.every((g) => g.gain.value === 1)).toBe(true);
  });

  it("schedules only the active scene's patterns (decoy pattern is never played)", async () => {
    const patch = structuredClone(golden) as Patch;
    const real = structuredClone(patch.patterns[0]);
    const decoy = structuredClone(patch.patterns[0]);
    decoy.pattern_id = "pattern_decoy";
    decoy.notes = decoy.notes.map((n) => ({ ...n, element_id: "el_ghost" }));
    patch.patterns = [decoy, real];
    patch.scenes[0].pattern_ids = [real.pattern_id];

    const bundle = makeBundle(patch);
    bundle.buffers.set("el_ghost", { buf: "ghost" });
    engine.load(bundle);
    await engine.play();

    // 首个 tick 已排 [0, 0.12) 窗口——step0 的 note 应来自 real pattern
    const scheduledBuffers = ctx.sources.map((s) => (s.buffer as { buf: string }).buf);
    expect(scheduledBuffers.length).toBeGreaterThan(0);
    expect(scheduledBuffers).not.toContain("ghost");
  });

  it("skips notes whose element has no buffer (missing asset)", async () => {
    const bundle = makeBundle();
    const step0Elements = new Set(
      bundle.patch.patterns[0].notes.filter((n) => n.step === 0).map((n) => n.element_id),
    );
    expect(step0Elements.size).toBeGreaterThan(0);
    for (const id of step0Elements) bundle.buffers.delete(id); // 模拟缺失

    engine.load(bundle);
    await engine.play();
    const played = ctx.sources.map((s) => (s.buffer as { buf: string }).buf);
    for (const id of step0Elements) expect(played).not.toContain(id);
  });

  it("playhead is null when stopped and a step index while playing", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    expect(engine.playhead()).toBeNull();

    await engine.play();
    ctx.currentTime = 0.01;
    expect(engine.playhead()).toBe(0);
    engine.stop();
    expect(engine.playhead()).toBeNull();
  });

  it("notifies subscribers on play/stop/mute", async () => {
    const bundle = makeBundle();
    engine.load(bundle);
    const events: number[] = [];
    const unsubscribe = engine.subscribe(() => events.push(1));

    await engine.play();
    engine.toggleMutePad(0);
    engine.stop();
    unsubscribe();
    engine.toggleMutePad(0);
    expect(events.length).toBe(3);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/engine/AudioEngine.test.ts
```

Expected: FAIL——`Cannot find module './AudioEngine'`。

- [ ] **Step 4: 实现 AudioEngine**

Create `apps/web/src/engine/AudioEngine.ts`:

```ts
import type { Pattern, PatchBundle } from "../patch/loader";
import { padElementIds, scenePatterns } from "../patch/loader";
import { notesInWindow, playheadStep, stepDuration } from "./clock";

export interface GainLike {
  gain: { value: number };
  connect(dst: unknown): void;
}
export interface SourceLike {
  buffer: unknown;
  connect(dst: unknown): void;
  start(when?: number): void;
}
export interface AudioLike {
  currentTime: number;
  destination: unknown;
  createGain(): GainLike;
  createBufferSource(): SourceLike;
  resume(): Promise<void>;
}

const TICK_MS = 25;
const LOOKAHEAD_SEC = 0.12;

export class AudioEngine {
  private readonly ctx: AudioLike;
  private bundle: PatchBundle<unknown> | null = null;
  private patterns: Pattern[] = [];
  private stepDur = 0;
  private gains = new Map<string, GainLike>();
  private mutedPads = new Set<number>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private startTime = 0;
  private scheduledUntil = 0;
  private listeners = new Set<() => void>();

  constructor(ctx: AudioLike) {
    this.ctx = ctx;
  }

  load(bundle: PatchBundle<unknown>): void {
    this.stop();
    this.bundle = bundle;
    // scene 契约：activeScene → pattern_ids → patterns（不得直读 patterns[0]）
    this.patterns = scenePatterns(bundle.patch);
    this.stepDur = stepDuration(bundle.patch.bpm);
    this.gains = new Map();
    for (const element of bundle.patch.elements) {
      const gain = this.ctx.createGain();
      gain.connect(this.ctx.destination);
      this.gains.set(element.element_id, gain);
    }
    this.mutedPads = new Set();
    this.emit();
  }

  get playing(): boolean {
    return this.timer !== null;
  }

  async play(): Promise<void> {
    if (!this.bundle || this.timer) return;
    await this.ctx.resume(); // 浏览器手势解锁
    this.startTime = this.ctx.currentTime;
    this.scheduledUntil = 0;
    this.tick();
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.emit();
  }

  stop(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null; // 已发声的 one-shot 自然播完（v1 不做硬切）
    this.emit();
  }

  triggerPad(index: number): void {
    const pad = this.bundle?.patch.pads[index];
    if (!pad) return;
    const ids = padElementIds(pad); // reserved/empty → [] → no-op
    if (ids.length === 0) return;
    void this.ctx.resume();
    for (const id of ids) this.playElement(id);
  }

  toggleMutePad(index: number): void {
    const pad = this.bundle?.patch.pads[index];
    if (!pad) return;
    const ids = padElementIds(pad);
    if (ids.length === 0) return;
    const muted = this.mutedPads.has(index);
    for (const id of ids) {
      const gain = this.gains.get(id);
      if (gain) gain.gain.value = muted ? 1 : 0;
    }
    if (muted) this.mutedPads.delete(index);
    else this.mutedPads.add(index);
    this.emit();
  }

  isPadMuted(index: number): boolean {
    return this.mutedPads.has(index);
  }

  /** 播放中返回当前 step（取 scene 首 pattern 的 length_steps），停止时 null */
  playhead(): number | null {
    if (!this.timer || this.patterns.length === 0) return null;
    const elapsed = this.ctx.currentTime - this.startTime;
    return playheadStep(elapsed, this.patterns[0].length_steps, this.stepDur);
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private tick(): void {
    const now = this.ctx.currentTime - this.startTime;
    const from = Math.max(this.scheduledUntil, now);
    const to = now + LOOKAHEAD_SEC;
    if (to <= from) return;
    for (const pattern of this.patterns) {
      for (const hit of notesInWindow(pattern.notes, pattern.length_steps, this.stepDur, from, to)) {
        this.playElement(hit.note.element_id, this.startTime + hit.time);
      }
    }
    this.scheduledUntil = to;
  }

  private playElement(elementId: string, when?: number): void {
    const buffer = this.bundle?.buffers.get(elementId);
    const gain = this.gains.get(elementId);
    if (!buffer || !gain) return; // 缺失素材：跳过发声，note 数据不动
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(gain);
    source.start(when ?? this.ctx.currentTime);
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
npx vitest run src/engine/AudioEngine.test.ts
```

Expected: `7 passed`。

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/engine apps/web/src/test
git commit -m "feat(web): audio engine with lookahead scheduler and group semantics"
```

---

### Task 5: App 壳——主题、落地态、加载与错误面板

**Files:**
- Create: `apps/web/src/ui/theme.css`
- Create: `apps/web/src/ui/DropZone.tsx`
- Create: `apps/web/src/ui/ErrorPanel.tsx`
- Create: `apps/web/src/ui/useEngine.ts`
- Create: `apps/web/src/ui/App.tsx`
- Create: `apps/web/src/ui/App.test.tsx`
- Create: `apps/web/src/ui/Transport.tsx`、`PadGrid.tsx`、`StepGrid.tsx`、`Inspector.tsx`（占位，Task 6/7 替换）
- Modify: `apps/web/src/main.tsx`

**Interfaces:**
- Consumes: `loadPatch`/`PatchValidationError`/`PatchBundle` from Task 2；`AudioEngine` from Task 4。
- Produces:
  - `useEngineTick(engine: AudioEngine): void`（emit 时强制重渲）
  - `getAudio(): Promise<{ engine: AudioEngine; decode: (b: ArrayBuffer) => Promise<AudioBuffer> }>`（浏览器单例；测试不使用）
  - `App` props：`{ engine: AudioEngine; decode: (b: ArrayBuffer) => Promise<unknown>; fetchExample?: () => Promise<Map<string, ArrayBuffer>> }`（依赖注入以便测试）
  - `readPickedFiles(list: FileList)` / `readDroppedItems(items: DataTransferItemList)` → `Promise<Map<string, ArrayBuffer>>`
  - CSS class 约定：`pad--normal|empty|reserved|muted|error`、`banner-rejected`、`step-missing`、`step-playhead`

- [ ] **Step 1: 补装依赖并写 failing App 测试**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm install -D @testing-library/user-event@^14.5.0
```

Create `apps/web/src/ui/App.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "../engine/AudioEngine";
import { App } from "./App";

const enc = (data: unknown) => new TextEncoder().encode(JSON.stringify(data)).buffer as ArrayBuffer;
const fakeDecode = async () => ({ fake: "buffer" });

function exampleFiles(patch: unknown): () => Promise<Map<string, ArrayBuffer>> {
  return async () => {
    const files = new Map<string, ArrayBuffer>([["patch.json", enc(patch)]]);
    for (const el of (patch as Patch).elements) files.set(el.source_path, new ArrayBuffer(8));
    return files;
  };
}

function renderApp(patch: unknown) {
  const engine = new AudioEngine(new FakeAudioContext());
  return render(
    <App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(patch)} />,
  );
}

describe("App", () => {
  it("starts on the landing screen with a drop zone and example button", () => {
    renderApp(golden);
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /示例/i })).toBeInTheDocument();
  });

  it("loads the example patch into the workstation view", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-grid")).toBeInTheDocument());
    expect(screen.getByText(/BPM/)).toBeInTheDocument();
  });

  it("shows the error panel on schema-invalid patch and stays on landing", async () => {
    const broken = structuredClone(golden) as Patch;
    (broken.pads[0] as { action: string }).action = "nope";
    renderApp(broken);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
    expect(screen.getByTestId("error-panel").textContent).toContain("/pads/0/action");
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
  });

  it("shows the rejected banner when metadata.status is rejected", async () => {
    const rejected = structuredClone(golden) as Patch;
    (rejected.metadata as Record<string, unknown>).status = "rejected";
    renderApp(rejected);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("banner-rejected")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run src/ui/App.test.tsx
```

Expected: FAIL——`Cannot find module './App'`。

- [ ] **Step 3: 实现主题、DropZone、ErrorPanel、useEngine、App**

Create `apps/web/src/ui/theme.css`:

```css
:root {
  --bg: #000;
  --green: #33ff66;
  --green-dim: #1a8038;
  --red: #ff4444;
  --yellow: #ffcc33;
  --gray: #555;
  color-scheme: dark;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--green);
  font-family: "SF Mono", "Fira Code", Menlo, Consolas, monospace;
  font-size: 14px;
}

button {
  font: inherit;
  color: inherit;
  background: transparent;
  border: 1px solid var(--green);
  cursor: pointer;
}
button:hover { background: rgba(51, 255, 102, 0.12); }

.app { max-width: 1080px; margin: 0 auto; padding: 16px; }

.drop-zone {
  border: 1px dashed var(--green-dim);
  padding: 48px 24px;
  text-align: center;
  white-space: pre;
  margin-bottom: 16px;
}
.drop-zone--over { border-color: var(--green); background: rgba(51, 255, 102, 0.06); }

.error-panel {
  border: 1px solid var(--red);
  color: var(--red);
  padding: 12px;
  margin-top: 16px;
  white-space: pre-wrap;
}

.banner-rejected {
  border: 1px solid var(--yellow);
  color: var(--yellow);
  padding: 8px 12px;
  margin-bottom: 12px;
}

.workstation { display: grid; grid-template-columns: 1fr 320px; gap: 16px; }
.workstation-bottom { grid-column: 1 / -1; }

.transport { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
.transport button { width: 48px; height: 32px; }

.pad-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.pad {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1px solid var(--green);
  user-select: none;
}
.pad-key { font-size: 11px; opacity: 0.7; }
.pad-slot { font-size: 11px; opacity: 0.7; }
.pad-label { font-weight: bold; }
.pad--empty { border-color: var(--green-dim); color: var(--green-dim); }
.pad--reserved { border-color: var(--gray); color: var(--gray); cursor: default; }
.pad--reserved:hover { background: transparent; }
.pad--muted { border-color: var(--green-dim); color: var(--green-dim); }
.pad--muted .pad-label { text-decoration: line-through; }
.pad--error { border-color: var(--red); color: var(--red); }
.pad--flash { background: rgba(51, 255, 102, 0.35); }

.inspector { border: 1px solid var(--green-dim); padding: 12px; font-size: 12px; }
.inspector h3 { margin: 0 0 8px; font-size: 12px; }
.inspector .missing { color: var(--red); }
.inspector .warn { color: var(--yellow); }

.step-grid { border: 1px solid var(--green-dim); padding: 12px; overflow-x: auto; }
.step-grid table { border-collapse: collapse; }
.step-grid td, .step-grid th { padding: 0 1px; font-size: 13px; text-align: center; }
.step-grid th { text-align: right; padding-right: 8px; font-weight: normal; }
.step-missing { color: var(--red); }
.step-playhead { background: var(--green); color: var(--bg); }
```

Create `apps/web/src/ui/useEngine.ts`:

```ts
import { useEffect, useReducer } from "react";
import type { AudioEngine } from "../engine/AudioEngine";

/** engine emit 时强制重渲 */
export function useEngineTick(engine: AudioEngine): void {
  const [, force] = useReducer((x: number) => x + 1, 0);
  useEffect(() => engine.subscribe(force), [engine]);
}

let singleton: { engine: AudioEngine; decode: (b: ArrayBuffer) => Promise<AudioBuffer> } | null =
  null;

/** 浏览器入口用的单例（测试不走这里，走依赖注入） */
export async function getAudio(): Promise<{
  engine: AudioEngine;
  decode: (b: ArrayBuffer) => Promise<AudioBuffer>;
}> {
  if (!singleton) {
    const { AudioEngine } = await import("../engine/AudioEngine");
    const ctx = new AudioContext();
    singleton = { engine: new AudioEngine(ctx), decode: (b) => ctx.decodeAudioData(b) };
  }
  return singleton;
}
```

Create `apps/web/src/ui/DropZone.tsx`:

```tsx
import { useRef, useState } from "react";

const ASCII = String.raw`
   ┌───────────────────────────────┐
   │  drop a patch package here    │
   │  (folder with patch.json)     │
   └───────────────────────────────┘`;

/** 目录选择器：webkitRelativePath 形如 "pkgdir/patch.json" → 去掉首段得包相对路径 */
export async function readPickedFiles(list: FileList): Promise<Map<string, ArrayBuffer>> {
  const files = new Map<string, ArrayBuffer>();
  for (const file of Array.from(list)) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    const path = rel.includes("/") ? rel.split("/").slice(1).join("/") : rel;
    files.set(path, await file.arrayBuffer());
  }
  return files;
}

/** 拖放目录：webkitGetAsEntry 递归遍历（readEntries 需循环取批次） */
export async function readDroppedItems(
  items: DataTransferItemList,
): Promise<Map<string, ArrayBuffer>> {
  const files = new Map<string, ArrayBuffer>();

  async function allEntries(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
    const reader = dir.createReader();
    const out: FileSystemEntry[] = [];
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((res, rej) =>
        reader.readEntries(res, rej),
      );
      if (batch.length === 0) return out;
      out.push(...batch);
    }
  }

  async function walk(entry: FileSystemEntry, path: string): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File>((res, rej) =>
        (entry as FileSystemFileEntry).file(res, rej),
      );
      files.set(path, await file.arrayBuffer());
    } else if (entry.isDirectory) {
      for (const child of await allEntries(entry as FileSystemDirectoryEntry)) {
        await walk(child, path ? `${path}/${child.name}` : child.name);
      }
    }
  }

  for (const item of Array.from(items)) {
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) await walk(entry, ""); // 顶层目录名不入包相对路径
    else if (entry) await walk(entry, entry.name);
  }
  return files;
}

export function DropZone({
  onFiles,
  onExample,
}: {
  onFiles: (files: Map<string, ArrayBuffer>) => void;
  onExample: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      className={`drop-zone${over ? " drop-zone--over" : ""}`}
      data-testid="drop-zone"
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void readDroppedItems(e.dataTransfer.items).then(onFiles);
      }}
    >
      <div>{ASCII}</div>
      <p>
        <button onClick={() => inputRef.current?.click()}>选择 package 目录</button>{" "}
        <button onClick={onExample}>加载示例 patch</button>
      </p>
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        // @ts-expect-error 非标准属性，主流浏览器均支持
        webkitdirectory=""
        multiple
        onChange={(e) => {
          if (e.target.files) void readPickedFiles(e.target.files).then(onFiles);
        }}
      />
    </div>
  );
}
```

Create `apps/web/src/ui/ErrorPanel.tsx`:

```tsx
export function ErrorPanel({ issues }: { issues: string[] }) {
  return (
    <div className="error-panel" data-testid="error-panel">
      <strong>patch.json 未通过 lmdj.patch.v1 校验：</strong>
      {"\n"}
      {issues.join("\n")}
    </div>
  );
}
```

Create `apps/web/src/ui/App.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { DropZone } from "./DropZone";
import { ErrorPanel } from "./ErrorPanel";
import { Inspector } from "./Inspector";
import { PadGrid, PAD_KEYS } from "./PadGrid";
import { StepGrid } from "./StepGrid";
import { Transport } from "./Transport";

/** 内置示例：fetch public/example-patch/（浏览器路径；测试注入替身） */
export async function fetchExampleFiles(): Promise<Map<string, ArrayBuffer>> {
  const res = await fetch("example-patch/patch.json");
  if (!res.ok) {
    throw new PatchValidationError(["示例 patch 不存在——先运行 npm run make-example"]);
  }
  const patchBytes = await res.arrayBuffer();
  const files = new Map<string, ArrayBuffer>([["patch.json", patchBytes]]);
  const patch = JSON.parse(new TextDecoder().decode(patchBytes)) as {
    elements?: { source_path: string }[];
  };
  for (const el of patch.elements ?? []) {
    const r = await fetch(`example-patch/${el.source_path}`);
    if (r.ok) files.set(el.source_path, await r.arrayBuffer());
  }
  return files;
}

type AppState =
  | { phase: "landing"; issues: string[] | null }
  | { phase: "loaded"; bundle: PatchBundle<unknown> };

export function App({
  engine,
  decode,
  fetchExample = fetchExampleFiles,
}: {
  engine: AudioEngine;
  decode: (b: ArrayBuffer) => Promise<unknown>;
  fetchExample?: () => Promise<Map<string, ArrayBuffer>>;
}) {
  const [state, setState] = useState<AppState>({ phase: "landing", issues: null });

  const fail = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    setState({ phase: "landing", issues });
  }, []);

  const handleFiles = useCallback(
    async (files: Map<string, ArrayBuffer>) => {
      try {
        const bundle = await loadPatch(files, decode);
        engine.load(bundle);
        setState({ phase: "loaded", bundle });
      } catch (error) {
        fail(error);
      }
    },
    [engine, decode, fail],
  );

  // 键盘：A S D F / Z X C V → pad 0-7（仅 loaded 后生效）
  useEffect(() => {
    if (state.phase !== "loaded") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const index = PAD_KEYS.indexOf(e.key.toUpperCase());
      if (index >= 0) engine.triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, engine]);

  if (state.phase === "landing") {
    return (
      <div className="app">
        <h1>LMDJ PATCH VIEW</h1>
        <DropZone
          onFiles={(f) => void handleFiles(f)}
          onExample={() => void fetchExample().then(handleFiles, fail)}
        />
        {state.issues && <ErrorPanel issues={state.issues} />}
      </div>
    );
  }

  const { bundle } = state;
  const status = (bundle.patch.metadata as Record<string, unknown> | undefined)?.status;
  return (
    <div className="app">
      {status === "rejected" && (
        <div className="banner-rejected" data-testid="banner-rejected">
          质量分未过阈（status: rejected）——仍可播放，仅作提示
        </div>
      )}
      <Transport engine={engine} bundle={bundle} />
      <div className="workstation">
        <PadGrid engine={engine} bundle={bundle} />
        <Inspector bundle={bundle} />
        <div className="workstation-bottom">
          <StepGrid engine={engine} bundle={bundle} />
        </div>
      </div>
    </div>
  );
}
```

Modify `apps/web/src/main.tsx`:

```tsx
import { createRoot } from "react-dom/client";
import { App } from "./ui/App";
import { getAudio } from "./ui/useEngine";
import "./ui/theme.css";

const root = createRoot(document.getElementById("root")!);
void getAudio().then(({ engine, decode }) => {
  root.render(<App engine={engine} decode={decode} />);
});
```

- [ ] **Step 4: 写 Task 6/7 组件的最小占位（同接口，本任务内让测试可绿）**

Create `apps/web/src/ui/PadGrid.tsx`（占位，Task 6 替换）:

```tsx
import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export const PAD_KEYS = ["A", "S", "D", "F", "Z", "X", "C", "V"];

export function PadGrid(_props: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return <div className="pad-grid" data-testid="pad-grid" />;
}
```

Create `apps/web/src/ui/Transport.tsx`（占位，Task 6 替换）:

```tsx
import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export function Transport({ bundle }: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return (
    <div className="transport">
      <span>BPM {bundle.patch.bpm}</span>
      <span>patch: {bundle.patch.patch_id}</span>
    </div>
  );
}
```

Create `apps/web/src/ui/StepGrid.tsx`（占位，Task 7 替换）:

```tsx
import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";

export function StepGrid(_props: { engine: AudioEngine; bundle: PatchBundle<unknown> }) {
  return <div className="step-grid" data-testid="step-grid" />;
}
```

Create `apps/web/src/ui/Inspector.tsx`（占位，Task 7 替换）:

```tsx
import type { PatchBundle } from "../patch/loader";

export function Inspector(_props: { bundle: PatchBundle<unknown> }) {
  return <div className="inspector" data-testid="inspector" />;
}
```

- [ ] **Step 5: 跑测试确认通过**

```bash
npx vitest run src/ui/App.test.tsx
```

Expected: `4 passed`。

- [ ] **Step 6: 全量测试 + 构建**

```bash
npm test && npm run build
```

Expected: 全部通过（contract 2 + loader 9 + clock 6 + engine 7 + app 4 = 28）；build 成功。

- [ ] **Step 7: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web
git commit -m "feat(web): app shell with landing, loading, and error handling"
```

---

### Task 6: PadGrid + Transport + 键盘

**Files:**
- Modify: `apps/web/src/ui/PadGrid.tsx`（替换占位）
- Modify: `apps/web/src/ui/Transport.tsx`（替换占位）
- Create: `apps/web/src/ui/PadGrid.test.tsx`

**Interfaces:**
- Consumes: `AudioEngine`（triggerPad/toggleMutePad/isPadMuted/playing/play/stop）、`padElementIds`、`useEngineTick`。
- Produces: `PAD_KEYS: string[]`（保持 Task 5 占位已导出的值不变）。

- [ ] **Step 1: 写 failing 测试**

Create `apps/web/src/ui/PadGrid.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import type { Patch, PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { PadGrid } from "./PadGrid";

function setup(mutate?: (patch: Patch, bundle: PatchBundle<unknown>) => void) {
  const patch = structuredClone(golden) as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(patch.elements.map((e) => [e.element_id, { buf: e.element_id }])),
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
  mutate?.(patch, bundle);
  const ctx = new FakeAudioContext();
  const engine = new AudioEngine(ctx);
  engine.load(bundle);
  render(<PadGrid engine={engine} bundle={bundle} />);
  return { ctx, engine, bundle };
}

describe("PadGrid", () => {
  it("renders 8 pads with slot names and key hints", () => {
    setup();
    const pads = screen.getAllByTestId(/^pad-\d$/);
    expect(pads).toHaveLength(8);
    expect(screen.getByText("Drums")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument(); // pad 0 键提示
  });

  it("reserved pads are disabled, empty pads marked empty", () => {
    const { bundle } = setup();
    const reserved = bundle.patch.pads.find((p) => p.action === "scene_fill")!;
    expect(screen.getByTestId(`pad-${reserved.index}`)).toHaveClass("pad--reserved");
    const empty = bundle.patch.pads.find((p) => p.action === "empty");
    if (empty) expect(screen.getByTestId(`pad-${empty.index}`)).toHaveClass("pad--empty");
  });

  it("click triggers the whole group", () => {
    const { ctx } = setup();
    fireEvent.click(screen.getByTestId("pad-0")); // Drums trigger_group
    expect(ctx.sources.length).toBeGreaterThan(1);
  });

  it("contextmenu toggles mute (and is prevented)", () => {
    const { engine } = setup();
    const pad = screen.getByTestId("pad-0");
    const notPrevented = fireEvent.contextMenu(pad);
    expect(notPrevented).toBe(false); // preventDefault() 已调用
    expect(engine.isPadMuted(0)).toBe(true);
    expect(pad).toHaveClass("pad--muted");
    fireEvent.contextMenu(pad);
    expect(engine.isPadMuted(0)).toBe(false);
  });

  it("pads with missing assets render the error state", () => {
    const { bundle } = setup((patch, b) => {
      const drums = patch.pads[0];
      const ids = (drums.behavior as { element_ids: string[] }).element_ids;
      b.missingElementIds.add(ids[0]);
      b.playableElementIds.delete(ids[0]);
    });
    expect(bundle.missingElementIds.size).toBe(1);
    expect(screen.getByTestId("pad-0")).toHaveClass("pad--error");
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/ui/PadGrid.test.tsx
```

Expected: FAIL——占位 PadGrid 无 pad 元素（`Unable to find ... pad-0` 等）。

- [ ] **Step 3: 实现 PadGrid 与 Transport**

Replace `apps/web/src/ui/PadGrid.tsx`:

```tsx
import { useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { padElementIds, type Pad, type PatchBundle } from "../patch/loader";
import { useEngineTick } from "./useEngine";

export const PAD_KEYS = ["A", "S", "D", "F", "Z", "X", "C", "V"];

type PadState = "normal" | "empty" | "reserved" | "muted" | "error";

function padState(pad: Pad, bundle: PatchBundle<unknown>, engine: AudioEngine): PadState {
  if (pad.action === "empty") return "empty";
  if (pad.action !== "trigger_element" && pad.action !== "trigger_group") return "reserved";
  if (padElementIds(pad).some((id) => bundle.missingElementIds.has(id))) return "error";
  if (engine.isPadMuted(pad.index)) return "muted";
  return "normal";
}

function PadCell({
  pad,
  bundle,
  engine,
}: {
  pad: Pad;
  bundle: PatchBundle<unknown>;
  engine: AudioEngine;
}) {
  const [flash, setFlash] = useState(false);
  const state = padState(pad, bundle, engine);
  const interactive = state === "normal" || state === "muted" || state === "error";

  return (
    <button
      data-testid={`pad-${pad.index}`}
      className={`pad pad--${state}${flash ? " pad--flash" : ""}`}
      onClick={() => {
        if (!interactive) return;
        engine.triggerPad(pad.index);
        setFlash(true);
        setTimeout(() => setFlash(false), 120);
      }}
      onContextMenu={(e) => {
        e.preventDefault(); // 契约：右键静音，不弹浏览器菜单
        if (interactive) engine.toggleMutePad(pad.index);
      }}
    >
      <span className="pad-key">{PAD_KEYS[pad.index]}</span>
      <span className="pad-slot">{pad.slot}</span>
      <span className="pad-label">{pad.label}</span>
    </button>
  );
}

export function PadGrid({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  useEngineTick(engine);
  return (
    <div className="pad-grid" data-testid="pad-grid">
      {bundle.patch.pads.map((pad) => (
        <PadCell key={pad.index} pad={pad} bundle={bundle} engine={engine} />
      ))}
    </div>
  );
}
```

Replace `apps/web/src/ui/Transport.tsx`:

```tsx
import type { AudioEngine } from "../engine/AudioEngine";
import type { PatchBundle } from "../patch/loader";
import { useEngineTick } from "./useEngine";

export function Transport({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  useEngineTick(engine);
  return (
    <div className="transport">
      <button
        data-testid="play-toggle"
        onClick={() => (engine.playing ? engine.stop() : void engine.play())}
      >
        {engine.playing ? "■" : "▶"}
      </button>
      <span>BPM {bundle.patch.bpm}</span>
      <span>loop {bundle.patch.loop_seconds}s</span>
      <span>patch: {bundle.patch.patch_id}</span>
    </div>
  );
}
```

- [ ] **Step 4: 跑测试确认通过（含回归）**

```bash
npx vitest run
```

Expected: 全部通过（新增 PadGrid 5 → 共 33）。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/ui
git commit -m "feat(web): pad grid with group trigger, mute, and keyboard mapping"
```

---

### Task 7: StepGrid + Inspector

**Files:**
- Modify: `apps/web/src/ui/StepGrid.tsx`（替换占位）
- Modify: `apps/web/src/ui/Inspector.tsx`（替换占位）
- Create: `apps/web/src/ui/StepGrid.test.tsx`

**Interfaces:**
- Consumes: `scenePatterns`、`PatchBundle`、`AudioEngine.playhead()/playing`。
- Produces: 无新接口（终端组件）。

- [ ] **Step 1: 写 failing 测试**

Create `apps/web/src/ui/StepGrid.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type Patch, type PatchBundle } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { Inspector } from "./Inspector";
import { StepGrid } from "./StepGrid";

function makeBundle(mutate?: (b: PatchBundle<unknown>) => void): PatchBundle<unknown> {
  const patch = structuredClone(golden) as Patch;
  const bundle: PatchBundle<unknown> = {
    patch,
    buffers: new Map(patch.elements.map((e) => [e.element_id, {}])),
    playableElementIds: new Set(patch.elements.map((e) => e.element_id)),
    missingElementIds: new Set(),
    warnings: [],
  };
  mutate?.(bundle);
  return bundle;
}

function renderGrid(bundle: PatchBundle<unknown>) {
  const engine = new AudioEngine(new FakeAudioContext());
  engine.load(bundle);
  render(<StepGrid engine={engine} bundle={bundle} />);
  return engine;
}

describe("StepGrid", () => {
  it("renders one row per element with notes, cells matching the pattern", () => {
    const bundle = makeBundle();
    renderGrid(bundle);
    const pattern = scenePatterns(bundle.patch)[0];
    const elementIds = new Set(pattern.notes.map((n) => n.element_id));
    expect(elementIds.size).toBeGreaterThan(0);
    for (const id of elementIds) {
      const row = screen.getByTestId(`step-row-${id}`);
      const filled = row.textContent?.match(/█/g)?.length ?? 0;
      const steps = new Set(
        pattern.notes.filter((n) => n.element_id === id).map((n) => n.step),
      );
      expect(filled).toBe(steps.size);
    }
  });

  it("marks rows of missing elements", () => {
    const bundle = makeBundle((b) => {
      const first = b.patch.patterns[0].notes[0].element_id;
      b.missingElementIds.add(first);
    });
    renderGrid(bundle);
    const first = bundle.patch.patterns[0].notes[0].element_id;
    expect(screen.getByTestId(`step-row-${first}`)).toHaveClass("step-missing");
  });
});

describe("Inspector", () => {
  it("shows patch facts, score, and unmapped/warnings", () => {
    const bundle = makeBundle((b) => {
      b.warnings.push("missing sample file: samples/ghost.wav (el_ghost)");
      (b.patch.metadata as Record<string, unknown>).unmapped_element_ids = ["el_orphan"];
    });
    render(<Inspector bundle={bundle} />);

    expect(screen.getByTestId("inspector")).toHaveTextContent(bundle.patch.patch_id);
    expect(screen.getByTestId("inspector")).toHaveTextContent("el_orphan");
    expect(screen.getByTestId("inspector")).toHaveTextContent("ghost.wav");
    for (const el of bundle.patch.elements) {
      expect(screen.getByTestId("inspector")).toHaveTextContent(el.name);
    }
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/ui/StepGrid.test.tsx
```

Expected: FAIL——占位组件无 step-row/内容。

- [ ] **Step 3: 实现**

Replace `apps/web/src/ui/StepGrid.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import type { AudioEngine } from "../engine/AudioEngine";
import { scenePatterns, type PatchBundle } from "../patch/loader";

export function StepGrid({
  engine,
  bundle,
}: {
  engine: AudioEngine;
  bundle: PatchBundle<unknown>;
}) {
  const pattern = scenePatterns(bundle.patch)[0]; // scene 契约路径；v1 单 pattern
  const [playhead, setPlayhead] = useState<number | null>(null);

  useEffect(() => {
    const id = setInterval(() => setPlayhead(engine.playhead()), 50);
    return () => clearInterval(id);
  }, [engine]);

  const rows = useMemo(() => {
    const byElement = new Map<string, Set<number>>();
    for (const note of pattern.notes) {
      if (!byElement.has(note.element_id)) byElement.set(note.element_id, new Set());
      byElement.get(note.element_id)!.add(note.step);
    }
    return bundle.patch.elements
      .filter((el) => byElement.has(el.element_id))
      .map((el) => ({ element: el, steps: byElement.get(el.element_id)! }));
  }, [bundle.patch, pattern]);

  return (
    <div className="step-grid" data-testid="step-grid">
      <table>
        <tbody>
          {rows.map(({ element, steps }) => (
            <tr
              key={element.element_id}
              data-testid={`step-row-${element.element_id}`}
              className={bundle.missingElementIds.has(element.element_id) ? "step-missing" : ""}
            >
              <th>{element.name}</th>
              {Array.from({ length: pattern.length_steps }, (_, step) => (
                <td key={step} className={step === playhead ? "step-playhead" : ""}>
                  {steps.has(step) ? "█" : "·"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Replace `apps/web/src/ui/Inspector.tsx`:

```tsx
import type { PatchBundle } from "../patch/loader";

export function Inspector({ bundle }: { bundle: PatchBundle<unknown> }) {
  const { patch, missingElementIds, warnings } = bundle;
  const meta = (patch.metadata ?? {}) as Record<string, unknown>;
  const unmapped = Array.isArray(meta.unmapped_element_ids)
    ? (meta.unmapped_element_ids as string[])
    : [];

  return (
    <div className="inspector" data-testid="inspector">
      <h3>INSPECTOR</h3>
      <div>patch_id: {patch.patch_id}</div>
      <div>schema: {patch.schema}</div>
      <div>bpm: {patch.bpm} / loop: {patch.loop_seconds}s</div>
      <div>status: {String(meta.status ?? "n/a")} / score: {String(meta.score ?? "n/a")}</div>
      <div>scene: {patch.scenes[0]?.name}</div>
      <h3>ELEMENTS</h3>
      <ul>
        {patch.elements.map((el) => (
          <li
            key={el.element_id}
            className={missingElementIds.has(el.element_id) ? "missing" : ""}
          >
            [{el.lane}] {el.name} ({el.kind}, pitch {el.pitch})
            {missingElementIds.has(el.element_id) ? " — MISSING" : ""}
          </li>
        ))}
      </ul>
      {unmapped.length > 0 && (
        <>
          <h3>UNMAPPED</h3>
          <ul>
            {unmapped.map((id) => (
              <li key={id} className="warn">{id}</li>
            ))}
          </ul>
        </>
      )}
      {warnings.length > 0 && (
        <>
          <h3>WARNINGS</h3>
          <ul>
            {warnings.map((w) => (
              <li key={w} className="warn">{w}</li>
            ))}
          </ul>
        </>
      )}
      {patch.renders.length > 0 && (
        <>
          <h3>RENDERS</h3>
          <ul>
            {patch.renders.map((r) => (
              <li key={r.path}>{r.kind}: {r.path}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 跑测试确认通过（含回归）**

```bash
npx vitest run
```

Expected: 全部通过（新增 3 → 共 36）。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/ui
git commit -m "feat(web): step grid with playhead and patch inspector"
```

---

### Task 8: 示例 patch、README 与最终验证

**Files:**
- Create: `apps/web/scripts/make-example.mjs`
- 生成: `apps/web/public/example-patch/`（patch.json + samples/*.wav）
- Create: `apps/web/README.md`
- Modify: `apps/README.md`

**Interfaces:**
- Consumes: demo `output/testsong` 的 patchify 产物（由 `scripts/dev.sh smoke` 保证存在）。
- Produces: 可开箱运行的示例；`npm run make-example`。

- [ ] **Step 1: 写 make-example 脚本**

Create `apps/web/scripts/make-example.mjs`:

```js
// 生成内置示例 patch：从 demo output/testsong 的 patchify 产物拷贝。
// 前置：仓库根目录先运行 `scripts/dev.sh smoke`。
// 约束（spec）：只含 patch.json + samples/*.wav；总体积 ≤ 2MB；不含 preview wav。
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = resolve(webRoot, "../../references/demos/lmdj-song-pipeline/output/testsong");
const DST = resolve(webRoot, "public/example-patch");
const LIMIT = 2 * 1024 * 1024;

if (!existsSync(join(SRC, "patch.json"))) {
  console.error(`missing ${join(SRC, "patch.json")} — 先在仓库根目录运行: scripts/dev.sh smoke`);
  process.exit(1);
}

rmSync(DST, { recursive: true, force: true });
mkdirSync(DST, { recursive: true });
copyFileSync(join(SRC, "patch.json"), join(DST, "patch.json"));

const patch = JSON.parse(readFileSync(join(DST, "patch.json"), "utf8"));
let total = statSync(join(DST, "patch.json")).size;
for (const el of patch.elements) {
  const dst = join(DST, el.source_path);
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(join(SRC, el.source_path), dst);
  total += statSync(dst).size;
}

if (total > LIMIT) {
  console.error(`example patch is ${total} bytes (> ${LIMIT}) — 超出 2MB 上限，拒绝生成`);
  rmSync(DST, { recursive: true, force: true });
  process.exit(1);
}
console.log(`example-patch generated: ${patch.patch_id}, ${total} bytes`);
console.log("provenance: scripts/dev.sh smoke → lmdj-patchify output/testsong");
```

- [ ] **Step 2: 生成示例并验证体积**

```bash
cd /Users/endaye/Projects/lmdj
scripts/dev.sh smoke          # 幂等；确保 patch.json 与真 wav 存在
cd apps/web && npm run make-example
```

Expected: 打印 `example-patch generated: testsong-… , N bytes`（N ≤ 2097152）。`public/example-patch/` 下有 `patch.json` + `samples/*.wav`（真实音频；wav 按仓库根 `.gitattributes` 走 LFS）。

- [ ] **Step 3: 写 README 并更新 apps/README**

Create `apps/web/README.md`:

````markdown
# LMDJ Web Patch View

`lmdj.patch.v1` 的第一个消费者：8-pad Focus View 工作台原型。设计文档见
`docs/superpowers/specs/2026-07-07-lmdj-web-patch-view-design.md`。

## 运行

```bash
npm install
npm run make-example   # 首次；前置：仓库根目录 scripts/dev.sh smoke
npm run dev            # http://localhost:5173
```

拖入任意 patchify 产出的 package 目录，或点击"加载示例 patch"。
操作：▶ 播放/停止；点击 pad 或按 `A S D F / Z X C V` 触发；右键 pad 静音整组。

## 测试与契约

```bash
npm test                 # 全部单测（Vitest + RTL）
npm run check-contract   # schema 拷贝与 types.ts 未漂移
npm run sync-contract    # core-models 契约变更后重新同步
```

契约纯度：本应用只读 `patch.json`，不读 `lanes.json`/`chart.mid`。
````

Modify `apps/README.md`——把这一行：

```markdown
- `apps/web/`：LMDJ Web App。负责 idea input、song upload、job progress、Patch View、render/share/remix 入口。
```

改为：

```markdown
- `apps/web/`：LMDJ Web App。负责 idea input、song upload、job progress、Patch View、render/share/remix 入口。已落地：Patch View 工作台原型（消费 `patch.json`，见 `apps/web/README.md`）。
```

- [ ] **Step 4: 最终验证**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm test && npm run check-contract && npm run build
```

Expected: 36 tests 全绿；contract 2 passed；build 成功。

手动冒烟清单（`npm run dev` 后在浏览器执行，结果记入 commit message 或 PR 描述）：

1. 点"加载示例 patch" → 2 秒内出现完整 Patch View；
2. ▶ 播放 → groove 与 demo `render_preview.wav` 听感一致，StepGrid 播放头行进并回卷；
3. 右键 Drums pad → kick/snare/hat 全部消声，再右键恢复；
4. 点击/按键 A → Drums 全组同击；F（Lead/Vocal empty）无声不报错；Fill/Drop/Mute/FX 灰色不可点；
5. 拖入 demo `output/testsong` 目录 → 同样加载成功（验证 lanes.json 等文件被无视）；
6. 拖入一个只有 `lanes.json` 的目录 → 错误面板提示缺 patch.json。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web apps/README.md
git commit -m "feat(web): built-in example patch, docs, and final wiring"
```

---

## Verification

全计划验证（Task 8 之后）：

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npm test              # expected: 36 passed
npm run check-contract
npm run build
npm run dev           # 手动冒烟按 Task 8 Step 4 清单
```

## Out Of Scope For This Plan

- Scenes 切换 UI、Modes、AI Talk、16-pad Pro View。
- 量化触发（`behavior.quantize` 不执行）、trigger_group 组员展开。
- 录音/导出、移动端触控、真实音频 e2e、任何后端与部署。

## Self-Review

- Spec 覆盖：契约纯度（loader 只认 patch.json + 手动冒烟第 5 条）、scene 读取路径（loader/engine/StepGrid 共用 `scenePatterns` + decoy 测试）、全组触发（engine 测试 + PadGrid 测试）、缺失素材模型（loader/engine/StepGrid/Inspector 四处 + 测试）、check-contract（Task 1）、示例约束（Task 8 脚本内置体积上限与来源记录）、状态色/键盘/contextmenu（theme.css + PadGrid 测试 + App 键盘 effect）、错误处理五情形（App 测试 + Inspector + AudioContext resume 于 play/triggerPad）——逐条可指到任务。
- 类型一致性：`PatchBundle<B>`/`scenePatterns`/`padElementIds`/`PAD_KEYS`/`AudioLike` 的签名在 Task 2/4/5/6 的 Interfaces 块与实现一致；Task 5 占位组件与 Task 6/7 正式实现同 props 签名。
- 已知取舍：`AudioEngine.stop()` 不硬切已发声 one-shot（尾音自然播完，v1 接受，代码注释注明）；`playhead()` 以 scene 首 pattern 的 `length_steps` 计（v1 单 pattern）。
