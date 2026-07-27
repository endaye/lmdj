# Polanyi Living Instrument UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已确认的 Polanyi Living Instrument 设计落到 `apps/web`：全流程共享确定性 2D Visual Signature，直接 Pad 演奏产生一拍轨迹，所有 UI 统一直角、零阴影，同时保持音频、MIDI、状态真实性、响应式和 `lmdj.patch.v1` 契约不变。

**Architecture:** 在 `apps/web/src/ui/generative/` 建立纯 TypeScript Visual Signature 与 Performance Trace 生命周期，再以纯展示组件接入 My Songs、Processing、Workbench 和 Export。`App` 只传递 browser-owned submission identity、公开 Patch、Pad Press、BPM 和 playhead；生成层使用 CSS / SVG、`pointer-events: none` 和有界节点，不读取 Worker 私有文件、不接触 AudioEngine 调度。

**Tech Stack:** React 19、TypeScript 5.7、Vite 8、Vitest、React Testing Library、Playwright、CSS Container Queries；不新增运行时或开发依赖。

## Global Constraints

- 执行必须发生在包含设计提交 `c3f02009` 的短期 `codex/` 分支；不得直接修改 `main`。
- 设计真相源是 `docs/superpowers/specs/2026-07-27-polanyi-living-instrument-ui-design.md`。
- `docs/superpowers/specs/2026-07-24-stage1-creator-workspace-ui-design.md` 的布局、断点、Square Pad、Uniform Gap、状态真实性与可访问性继续有效；本计划只覆盖其圆角、阴影、Hover 上移、缩放回弹和持续环境动效。
- 所有 UI 控件、面板、Badge、Dialog、Sheet、Song Card、Pattern、Pad、Inspector 和 Status Bar 必须 `border-radius: 0`、`box-shadow: none`。
- 圆、弧线和自由曲线只允许存在于 `.pad-geometry`、`.project-signature__motif` 和 `.performance-trace__mark` 等 `aria-hidden` 生成艺术层。
- 高饱和色只用于音乐角色、真实状态、选择反馈和生成图形；基础 UI 继续使用现有 `--paper` / `--ink`。
- Performance Trace 只表示鼠标、触控、键盘或 MIDI 进入同一个 `pressPad` 路径的直接用户演奏；Pattern 自动播放不得生成 Trace。
- 单条 Trace 生命周期为 `60000 / bpm` 毫秒；进入新小节时清空；同时最多 8 条。
- `prefers-reduced-motion: reduce` 下不得渲染移动 Trace；现有 Pad Pressed 结构状态承担静态反馈。
- 视觉层只能消费 browser-owned `submissionId`、公开 `patch.json`、Pad、BPM、playhead 和现有 App / Job 状态。
- 不读取或公开 `materials.json`、stems、`lanes.json`、`chart.mid`、Separation manifest 或 Worker 私有文件。
- 不修改 `lmdj.patch.v1`、API、Patchify、Audio Worker 或 AudioEngine 调度语义。
- 不新增 Three.js、React Three Fiber、p5.js、Canvas Runtime、GLB、Chameleon、皮肤、钱包或 NFT。
- 所有生产变更必须先有失败测试；每个任务先完成 Red → Green → Refactor，再进入下一任务。
- 仓库规则覆盖通用技能的“每任务提交”建议：本次实现回合只创建一个最终原子提交。任务 1–6 只建立已验证检查点，不提交；Task 7 全量验收后统一提交。
- 最终只 stage 本计划范围内文件；不得包含无关 staged、unstaged 或 untracked 工作。
- 自动提交不授权 push、PR、merge、deploy 或 publish。

---

## File Map

### 新建

- `apps/web/src/ui/generative/visualSignature.ts`
  - 稳定 FNV-1a seed、Visual Signature、Pad 视觉角色和真实产品状态到离散视觉阶段的纯函数。
- `apps/web/src/ui/generative/visualSignature.test.ts`
  - 确定性、差异性、Pad 角色兼容和状态映射测试。
- `apps/web/src/ui/generative/ProjectSignature.tsx`
  - `band | stage | stamp` 三种纯展示位置；不拥有产品状态。
- `apps/web/src/ui/generative/ProjectSignature.test.tsx`
  - seed、phase、离散 cell 和无障碍边界测试。
- `apps/web/src/ui/generative/performanceTrace.ts`
  - Pad Press event、Beat 时长、有界 append / prune 的纯生命周期函数。
- `apps/web/src/ui/generative/performanceTrace.test.ts`
  - 一拍、8 条上限、过期清理与稳定 trace identity 测试。
- `apps/web/src/ui/generative/PerformanceTraceLayer.tsx`
  - Timer、bar boundary、Reduced Motion 和纯展示节点。
- `apps/web/src/ui/generative/PerformanceTraceLayer.test.tsx`
  - Pad Press、自动过期、小节清理、Reduced Motion 和 pointer boundary 测试。
- `apps/web/src/ui/theme.test.ts`
  - CSS 静态合同：全文件零阴影；非零圆角只能出现在生成艺术白名单。

### 修改

- `apps/web/src/ui/PadButton.tsx`
  - 使用共享 Visual Signature / Pad Role；移除本地重复哈希。
- `apps/web/src/ui/PadButton.test.tsx`
  - 锁定共享签名迁移不改变确定性。
- `apps/web/src/ui/MySongsView.tsx`
  - 每首提交使用 `submissionId` 的克制 Signature band。
- `apps/web/src/ui/MySongsView.test.tsx`
  - Signature seed 与真实状态映射。
- `apps/web/src/ui/NewSongView.tsx`
  - 固定 idle 网格，不创建假项目身份。
- `apps/web/src/ui/NewSongView.test.tsx`
  - idle Signature 是装饰层且上传入口不变。
- `apps/web/src/ui/ProcessingPanel.tsx`
  - `submissionId` seed 与真实 Job phase 驱动 stage Signature。
- `apps/web/src/ui/ProcessingPanel.test.tsx`
  - 同 seed、真实 phase、未知状态与无百分比。
- `apps/web/src/ui/ExportChecklist.tsx`
  - 相同项目 seed 的 stamp；Checklist 仍为主体。
- `apps/web/src/ui/ExportChecklist.test.tsx`
  - Ready / Review / Partial 对应 phase，错误和 Missing 不被覆盖。
- `apps/web/src/ui/App.tsx`
  - API LoadedSource 保留 `submissionId`；建立 Pad Press event；接入 Signature 与 Trace。
- `apps/web/src/ui/App.test.tsx`
  - submission seed 跨 Processing / Loaded / Export 连续，Example 使用 `patch_id`，直接 Pad Press 才生成 Trace。
- `apps/web/src/ui/theme.css`
  - Project Signature、Performance Trace、直角、零阴影和平面反馈。
- `apps/web/e2e/workbench-responsive.spec.ts`
  - Computed-style、Trace 裁切、Reduced Motion 和现有响应式不退化。
- `docs/superpowers/specs/2026-07-27-polanyi-living-instrument-ui-design.md`
  - 全量验收后更新为“本分支已实现；待 PR / CI”并记录验证。

---

### Task 1: 共享确定性 Visual Signature 并保持 Pad 兼容

**Files:**
- Create: `apps/web/src/ui/generative/visualSignature.ts`
- Create: `apps/web/src/ui/generative/visualSignature.test.ts`
- Modify: `apps/web/src/ui/PadButton.tsx:1-74`
- Modify: `apps/web/src/ui/PadButton.test.tsx:1-75`

**Interfaces:**
- Consumes: `seed: string`、公开 `Pad` 的 `action / index / element_id / slot`、公开产品 `state: string | null | undefined`。
- Produces:
  - `createVisualSignature(seed: string): VisualSignature`
  - `roleForPad(pad: Pick<Pad, "action" | "index">): VisualRole`
  - `projectVisualPhase(state, failed): ProjectVisualPhase`

- [ ] **Step 1: 写 Visual Signature 失败测试**

创建 `apps/web/src/ui/generative/visualSignature.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import golden from "../../patch/__fixtures__/patch.golden.json";
import type { Pad } from "../../patch/loader";
import {
  createVisualSignature,
  projectVisualPhase,
  roleForPad,
} from "./visualSignature";

describe("createVisualSignature", () => {
  it("is stable and versionable for the same public seed", () => {
    expect(createVisualSignature("submission-a")).toEqual({
      id: "wave-173-71-6-84",
      shape: "wave",
      angle: 173,
      offset: 71,
      density: 6,
      phase: 84,
    });
    expect(createVisualSignature("submission-a")).toEqual(
      createVisualSignature("submission-a"),
    );
  });

  it("changes for a different public seed", () => {
    expect(createVisualSignature("submission-b").id).toBe(
      "slice-94-42-2-85",
    );
    expect(createVisualSignature("submission-b")).not.toEqual(
      createVisualSignature("submission-a"),
    );
  });
});

describe("roleForPad", () => {
  const pads = structuredClone(golden.pads) as unknown as Pad[];

  it("preserves the current role mapping while the signature moves modules", () => {
    expect(pads.slice(0, 5).map(roleForPad)).toEqual([
      "drums",
      "bass",
      "harmony",
      "empty",
      "action",
    ]);
  });
});

describe("projectVisualPhase", () => {
  it.each([
    [undefined, false, "idle"],
    ["preflight", false, "preflight"],
    ["queued", false, "queued"],
    ["separating", false, "separating"],
    ["extracting", false, "extracting"],
    ["patchifying", false, "patchifying"],
    ["completed", false, "ready"],
    ["interrupted", false, "review"],
    ["failed", false, "error"],
    ["spectralizing", false, "processing"],
    [undefined, true, "error"],
  ] as const)("maps %s / failed=%s to %s", (state, failed, phase) => {
    expect(projectVisualPhase(state, failed)).toBe(phase);
  });
});
```

- [ ] **Step 2: 运行测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/visualSignature.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './visualSignature'`。

- [ ] **Step 3: 实现纯 Visual Signature**

创建 `apps/web/src/ui/generative/visualSignature.ts`：

```ts
import type { Pad } from "../../patch/loader";

export type SignatureShape = "circle" | "grid" | "slice" | "wave";
export type VisualRole =
  | "drums"
  | "bass"
  | "harmony"
  | "lead"
  | "action"
  | "empty";

export type ProjectVisualPhase =
  | "idle"
  | "preflight"
  | "queued"
  | "separating"
  | "extracting"
  | "patchifying"
  | "processing"
  | "ready"
  | "review"
  | "error";

export interface VisualSignature {
  id: string;
  shape: SignatureShape;
  angle: number;
  offset: number;
  density: number;
  phase: number;
}

function hashSeed(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function createVisualSignature(seed: string): VisualSignature {
  const hash = hashSeed(seed);
  const shapes = ["circle", "grid", "slice", "wave"] as const;
  const shape = shapes[hash % shapes.length];
  const angle = (hash >>> 4) % 180;
  const offset = 18 + ((hash >>> 12) % 55);
  const density = 2 + ((hash >>> 20) % 5);
  const phase = (hash >>> 24) % 100;
  return {
    id: `${shape}-${angle}-${offset}-${density}-${phase}`,
    shape,
    angle,
    offset,
    density,
    phase,
  };
}

export function roleForPad(
  pad: Pick<Pad, "action" | "index">,
): VisualRole {
  if (pad.action === "empty") return "empty";
  if (pad.index === 0) return "drums";
  if (pad.index === 1) return "bass";
  if (pad.index === 2) return "harmony";
  if (pad.index === 3) return "lead";
  return "action";
}

export function projectVisualPhase(
  state: string | null | undefined,
  failed = false,
): ProjectVisualPhase {
  if (failed || state === "failed") return "error";
  if (!state) return "idle";
  if (state === "preflight") return "preflight";
  if (state === "queued") return "queued";
  if (state === "separating") return "separating";
  if (state === "extracting") return "extracting";
  if (state === "patchifying") return "patchifying";
  if (state === "completed") return "ready";
  if (state === "interrupted" || state === "cancelled") return "review";
  return "processing";
}
```

- [ ] **Step 4: 迁移 PadButton 到共享函数**

在 `apps/web/src/ui/PadButton.tsx`：

1. 删除本地 `hashSource`、`geometryFor` 和 `roleFor`。
2. 增加：

```ts
import {
  createVisualSignature,
  roleForPad,
} from "./generative/visualSignature";
```

3. 将组件内签名构建替换为：

```ts
const identity = pad.element_id ?? pad.slot;
const geometry = createVisualSignature(identity);
const geometryStyle = {
  "--pad-geometry-angle": `${geometry.angle}deg`,
  "--pad-geometry-offset": `${geometry.offset}%`,
  "--pad-geometry-density": String(geometry.density),
  "--pad-geometry-phase": `${geometry.phase}%`,
} as CSSProperties;
```

4. JSX 使用：

```tsx
className={`pad pad--role-${roleForPad(pad)} pad--${visualState}`}
data-geometry-signature={geometry.id}
data-geometry-shape={geometry.shape}
style={geometryStyle}
```

- [ ] **Step 5: 锁定迁移后的 Pad 签名**

在 `PadButton.test.tsx` 的现有
`keeps geometry stable for the same source and changes it after replacement`
测试中，在第一次读取 `first` 后增加：

```ts
expect(first).toMatch(/^(circle|grid|slice|wave)-\d+-\d+-\d+-\d+$/);
```

- [ ] **Step 6: 运行聚焦测试并确认 Green**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/visualSignature.test.ts src/ui/PadButton.test.tsx
```

Expected: 2 个测试文件全部 PASS；现有 Pad 状态、Pointer、Keyboard 和 Reduced Motion 测试无回归。

- [ ] **Step 7: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: 仅列出 Task 1 的 4 个文件；不提交，进入 Task 2。

---

### Task 2: 建立无状态 Project Signature 展示组件

**Files:**
- Create: `apps/web/src/ui/generative/ProjectSignature.tsx`
- Create: `apps/web/src/ui/generative/ProjectSignature.test.tsx`

**Interfaces:**
- Consumes: `seed`、Task 1 的 `ProjectVisualPhase`、`variant: "band" | "stage" | "stamp"`。
- Produces: `<ProjectSignature />`，包含稳定 `data-signature`、离散 `data-phase`、6 个 cell 和一个 motif；整个组件 `aria-hidden="true"`。

- [ ] **Step 1: 写 Project Signature 失败测试**

创建 `apps/web/src/ui/generative/ProjectSignature.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProjectSignature } from "./ProjectSignature";

describe("ProjectSignature", () => {
  it("renders a deterministic decorative band from the public seed", () => {
    render(
      <ProjectSignature
        seed="submission-a"
        phase="separating"
        variant="band"
        testId="signature"
      />,
    );

    const signature = screen.getByTestId("signature");
    expect(signature).toHaveAttribute("aria-hidden", "true");
    expect(signature).toHaveAttribute(
      "data-signature",
      "wave-173-71-6-84",
    );
    expect(signature).toHaveAttribute("data-phase", "separating");
    expect(signature).toHaveAttribute("data-variant", "band");
    expect(
      signature.querySelectorAll('[data-active="true"]'),
    ).toHaveLength(2);
  });

  it.each([
    ["idle", 0],
    ["preflight", 1],
    ["queued", 1],
    ["extracting", 3],
    ["patchifying", 4],
    ["review", 5],
    ["ready", 6],
    ["error", 2],
  ] as const)("uses discrete %s state without inventing a percent", (phase, active) => {
    render(
      <ProjectSignature
        seed="submission-b"
        phase={phase}
        variant="stage"
        testId={`signature-${phase}`}
      />,
    );
    const signature = screen.getByTestId(`signature-${phase}`);
    expect(signature.querySelectorAll('[data-active="true"]')).toHaveLength(
      active,
    );
    expect(signature).not.toHaveTextContent(/%/);
  });
});
```

- [ ] **Step 2: 运行测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/ProjectSignature.test.tsx
```

Expected: FAIL，错误包含 `Cannot find module './ProjectSignature'`。

- [ ] **Step 3: 实现 ProjectSignature**

创建 `apps/web/src/ui/generative/ProjectSignature.tsx`：

```tsx
import type { CSSProperties } from "react";
import {
  createVisualSignature,
  type ProjectVisualPhase,
} from "./visualSignature";

export type ProjectSignatureVariant = "band" | "stage" | "stamp";

const PHASE_CELLS: Record<ProjectVisualPhase, number> = {
  idle: 0,
  preflight: 1,
  queued: 1,
  separating: 2,
  extracting: 3,
  patchifying: 4,
  processing: 3,
  ready: 6,
  review: 5,
  error: 2,
};

export function ProjectSignature({
  seed,
  phase,
  variant,
  testId,
}: {
  seed: string;
  phase: ProjectVisualPhase;
  variant: ProjectSignatureVariant;
  testId?: string;
}) {
  const signature = createVisualSignature(seed);
  const style = {
    "--signature-angle": `${signature.angle}deg`,
    "--signature-offset": `${signature.offset}%`,
    "--signature-density": String(signature.density),
    "--signature-phase": `${signature.phase}%`,
  } as CSSProperties;

  return (
    <div
      className="project-signature"
      data-testid={testId}
      data-signature={signature.id}
      data-shape={signature.shape}
      data-phase={phase}
      data-variant={variant}
      aria-hidden="true"
      style={style}
    >
      <span className="project-signature__grid">
        {Array.from({ length: 6 }, (_, index) => (
          <i
            key={index}
            data-active={String(index < PHASE_CELLS[phase])}
          />
        ))}
      </span>
      <span
        className="project-signature__motif"
        data-shape={signature.shape}
      />
    </div>
  );
}
```

- [ ] **Step 4: 运行聚焦测试并确认 Green**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/visualSignature.test.ts src/ui/generative/ProjectSignature.test.tsx
```

Expected: 2 个测试文件全部 PASS。

- [ ] **Step 5: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: Task 1–2 文件，无其他修改；不提交，进入 Task 3。

---

### Task 3: 把同一项目 seed 贯穿主流程

**Files:**
- Modify: `apps/web/src/ui/MySongsView.tsx:118-236`
- Modify: `apps/web/src/ui/MySongsView.test.tsx:70-190`
- Modify: `apps/web/src/ui/NewSongView.tsx:14-34`
- Modify: `apps/web/src/ui/NewSongView.test.tsx:1-45`
- Modify: `apps/web/src/ui/ProcessingPanel.tsx:3-29`
- Modify: `apps/web/src/ui/ProcessingPanel.test.tsx:13-70`
- Modify: `apps/web/src/ui/ExportChecklist.tsx:30-150`
- Modify: `apps/web/src/ui/ExportChecklist.test.tsx:45-90`
- Modify: `apps/web/src/ui/App.tsx:70-115,285-315,392-430,840-1171`
- Modify: `apps/web/src/ui/App.test.tsx:430-610`

**Interfaces:**
- Consumes: API submission 的 `submissionId`；local / example 的 `patch_id`；真实 Job / Export 状态。
- Produces:
  - API `LoadedSource` 持续携带 `submissionId`
  - `ProcessingPanel.signatureSeed`
  - `ExportChecklist.signatureSeed`
  - My Songs / New Song / Processing / Failed / Export 的 Project Signature

- [ ] **Step 1: 写流程 seed 失败测试**

在 `MySongsView.test.tsx` 的
`shows browser scope, capacity, truthful sections, and product actions`
测试中增加：

```ts
expect(
  within(screen.getByTestId("song-card-job-a")).getByTestId(
    "song-signature-submission-a",
  ),
).toHaveAttribute("data-phase", "separating");
expect(
  within(screen.getByTestId("song-card-job-b")).getByTestId(
    "song-signature-submission-b",
  ),
).toHaveAttribute("data-phase", "queued");
expect(
  within(screen.getByTestId("song-card-job-c")).getByTestId(
    "song-signature-submission-c",
  ),
).toHaveAttribute("data-phase", "ready");
```

修改 `ProcessingPanel.test.tsx` 的 `renderPanel`：

```tsx
return render(
  <ProcessingPanel
    fileName="night-bloom.wav"
    signatureSeed="submission-night-bloom"
    state={state}
    lastNonterminalState={lastNonterminalState}
  />,
);
```

并在第一个参数化测试中增加：

```ts
expect(screen.getByTestId("processing-signature")).toHaveAttribute(
  "data-signature",
  "circle-37-26-4-2",
);
expect(screen.getByTestId("processing-signature")).toHaveAttribute(
  "data-phase",
  state === "completed" ? "ready" : state,
);
```

在 `ExportChecklist.test.tsx` 的 `StatefulChecklist` 调用中增加：

```tsx
signatureSeed="submission-export"
```

并在 `shows all four server item states...` 测试增加：

```ts
expect(screen.getByTestId("export-signature")).toHaveAttribute(
  "data-phase",
  "review",
);
expect(screen.getByTestId("export-signature")).toHaveAttribute(
  "aria-hidden",
  "true",
);
```

在 `NewSongView.test.tsx` 的现有 render 后增加：

```ts
expect(screen.getByTestId("new-song-signature")).toHaveAttribute(
  "data-phase",
  "idle",
);
```

- [ ] **Step 2: 运行流程组件测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/MySongsView.test.tsx src/ui/NewSongView.test.tsx src/ui/ProcessingPanel.test.tsx src/ui/ExportChecklist.test.tsx
```

Expected: FAIL；缺少 Signature test id 或 TypeScript 报告缺少
`signatureSeed` prop。

- [ ] **Step 3: 在页面组件中接入 ProjectSignature**

在 `MySongsView.tsx` 增加：

```ts
import { ProjectSignature } from "./generative/ProjectSignature";
import { projectVisualPhase } from "./generative/visualSignature";
```

在 `SongCard` 的 `.song-card__identity` 后、`.song-card__actions` 前增加：

```tsx
<ProjectSignature
  seed={job.submission.submissionId}
  phase={projectVisualPhase(technicalState(job), Boolean(job.clientError))}
  variant="band"
  testId={`song-signature-${job.submission.submissionId}`}
/>
```

在 `NewSongView.tsx` 导入 `ProjectSignature`，并在
`.source-limits` 后增加：

```tsx
<ProjectSignature
  seed="new-song"
  phase="idle"
  variant="stage"
  testId="new-song-signature"
/>
```

将 `ProcessingPanel` 签名改为：

```tsx
import { ProjectSignature } from "./generative/ProjectSignature";
import { projectVisualPhase } from "./generative/visualSignature";

export function ProcessingPanel({
  fileName,
  signatureSeed,
  state,
  lastNonterminalState,
}: {
  fileName: string;
  signatureSeed: string;
  state: string;
  lastNonterminalState: string;
}) {
  return (
    <section className="processing-panel" data-testid="processing-panel">
      <header className="state-heading">
        <span>Processing · live evidence</span>
        <h1>Building your Patch</h1>
        <p>
          Source retained · <strong>{fileName}</strong>
        </p>
      </header>
      <ProjectSignature
        seed={signatureSeed}
        phase={projectVisualPhase(state)}
        variant="stage"
        testId="processing-signature"
      />
      <UploadingView
        state={state}
        lastNonterminalState={lastNonterminalState}
      />
      <p className="processing-panel__hint">
        可以返回“我的歌曲”继续浏览；处理会在后台继续。
      </p>
    </section>
  );
}
```

在 `ExportChecklist.tsx` 增加 prop：

```ts
signatureSeed: string;
```

在组件内计算：

```ts
const signaturePhase =
  overall === "Ready" ? "ready" : "review";
```

并在 `.export-checklist__header` 后增加：

```tsx
<ProjectSignature
  seed={signatureSeed}
  phase={signaturePhase}
  variant="stamp"
  testId="export-signature"
/>
```

- [ ] **Step 4: 保留 API submission identity 到 Loaded / Export**

在 `App.tsx` 把 API LoadedSource 改为：

```ts
type LoadedSource =
  | {
      kind: "api";
      base: string;
      jobId: string;
      submissionId: string;
      fileName: string;
    }
  | { kind: "local" | "example" };
```

在 `openCompletedJob` 中传入：

```ts
{
  kind: "api",
  base,
  jobId,
  submissionId: job.submission.submissionId,
  fileName,
}
```

Processing render 增加：

```tsx
<ProcessingPanel
  fileName={state.fileName}
  signatureSeed={state.submissionId}
  state={state.jobState}
  lastNonterminalState={state.lastNonterminalStage}
/>
```

在 Loaded 分支建立：

```ts
const projectSignatureSeed =
  state.source.kind === "api"
    ? state.source.submissionId
    : bundle.patch.patch_id;
```

ExportChecklist 调用增加：

```tsx
signatureSeed={projectSignatureSeed}
```

Failed 页面在 `ErrorPanel` 前增加：

```tsx
<ProjectSignature
  seed={state.submissionId}
  phase="error"
  variant="stage"
  testId="failed-signature"
/>
```

- [ ] **Step 5: 写 App seed 连续性与失败状态测试**

在 `App API path` 中增加一个可控 Poll 的独立测试；不要复用会立即完成的默认
`fakeApi()`，否则 Processing Signature 会在断言前卸载：

```tsx
it("keeps one browser submission signature from Processing through Export", async () => {
  let resolvePoll: ((status: JobStatus) => void) | undefined;
  const pollJob = vi.fn<ApiClient["pollJob"]>(
    async (_base, _jobId, onState) => {
      onState?.(apiJob("job123", "separating"));
      return await new Promise<JobStatus>((resolve) => {
        resolvePoll = resolve;
      });
    },
  );
  renderAppWithApi(fakeApi({ pollJob }));
  await submitViaApi();

  const processingSignature = await screen.findByTestId(
    "processing-signature",
  );
  const signature = processingSignature.dataset.signature;
  expect(signature).toBeTruthy();

  await act(async () => {
    resolvePoll?.(
      apiJob("job123", "completed", {
        patch_id: "job123-abc",
        package_dir: "job123",
      }),
    );
    await Promise.resolve();
  });
  await waitFor(() =>
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument(),
  );
  await userEvent.click(screen.getByRole("button", { name: "Export" }));
  const exportSignature = await screen.findByTestId("export-signature");
  expect(exportSignature.dataset.signature).toBe(signature);
});
```

在 `failed job shows error in uploading view with a back button` 测试中增加：

```ts
expect(screen.getByTestId("failed-signature")).toHaveAttribute(
  "data-phase",
  "error",
);
```

在 `marks the example as remote-only in Export mode without status requests or a fake download`
测试中增加：

```ts
expect(screen.queryByTestId("export-signature")).not.toBeInTheDocument();
```

该断言保持 local / example 的真实边界：没有服务端 Export Checklist 时不伪造
Export stamp；后续 Workbench Trace 使用 `patch_id`。

- [ ] **Step 6: 运行流程测试并确认 Green**

Run:

```bash
cd apps/web
npm test -- src/ui/MySongsView.test.tsx src/ui/NewSongView.test.tsx src/ui/ProcessingPanel.test.tsx src/ui/ExportChecklist.test.tsx src/ui/App.test.tsx
```

Expected: 5 个测试文件全部 PASS；未知 Job 状态仍显示原值，Export Missing /
Partial 行为不变。

- [ ] **Step 7: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: Task 1–3 文件；无 Schema、API、Worker 或音频文件；不提交。

---

### Task 4: 实现一拍 Performance Trace 生命周期

**Files:**
- Create: `apps/web/src/ui/generative/performanceTrace.ts`
- Create: `apps/web/src/ui/generative/performanceTrace.test.ts`
- Create: `apps/web/src/ui/generative/PerformanceTraceLayer.tsx`
- Create: `apps/web/src/ui/generative/PerformanceTraceLayer.test.tsx`

**Interfaces:**
- Consumes:
  - `PadPressEvent { sequence, padIndex }`
  - `pads: readonly Pad[]`
  - `bpm`
  - `playheadStep`
  - project seed
- Produces:
  - `beatDurationMs`
  - `appendPerformanceTrace`
  - `prunePerformanceTraces`
  - `<PerformanceTraceLayer />`

- [ ] **Step 1: 写纯生命周期失败测试**

创建 `apps/web/src/ui/generative/performanceTrace.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import {
  appendPerformanceTrace,
  beatDurationMs,
  prunePerformanceTraces,
  type PerformanceTrace,
} from "./performanceTrace";

describe("performanceTrace", () => {
  it("uses exactly one quarter-note beat", () => {
    expect(beatDurationMs(120)).toBe(500);
    expect(beatDurationMs(90)).toBeCloseTo(666.666, 2);
  });

  it("creates a stable event and expires it after one beat", () => {
    const traces = appendPerformanceTrace(
      [],
      { sequence: 1, padIndex: 3 },
      "lead",
      "patch-a",
      120,
      1_000,
    );
    expect(traces).toEqual([
      {
        id: "patch-a:1:3",
        padIndex: 3,
        role: "lead",
        signatureSeed: "patch-a:3:1",
        expiresAt: 1_500,
      },
    ]);
    expect(prunePerformanceTraces(traces, 1_499)).toHaveLength(1);
    expect(prunePerformanceTraces(traces, 1_500)).toHaveLength(0);
  });

  it("keeps only the newest eight direct gestures", () => {
    const traces = Array.from({ length: 10 }, (_, index) => index).reduce<
      PerformanceTrace[]
    >(
      (current, sequence) =>
        appendPerformanceTrace(
          current,
          { sequence, padIndex: sequence % 16 },
          "action",
          "patch-a",
          100,
          sequence,
        ),
      [],
    );
    expect(traces).toHaveLength(8);
    expect(traces[0].id).toBe("patch-a:2:2");
    expect(traces[7].id).toBe("patch-a:9:9");
  });
});
```

- [ ] **Step 2: 运行纯生命周期测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/performanceTrace.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './performanceTrace'`。

- [ ] **Step 3: 实现纯生命周期**

创建 `apps/web/src/ui/generative/performanceTrace.ts`：

```ts
import type { VisualRole } from "./visualSignature";

export interface PadPressEvent {
  sequence: number;
  padIndex: number;
}

export interface PerformanceTrace {
  id: string;
  padIndex: number;
  role: VisualRole;
  signatureSeed: string;
  expiresAt: number;
}

const MAX_TRACES = 8;

export function beatDurationMs(bpm: number): number {
  return 60_000 / Math.max(1, bpm);
}

export function appendPerformanceTrace(
  current: readonly PerformanceTrace[],
  press: PadPressEvent,
  role: VisualRole,
  projectSeed: string,
  bpm: number,
  now: number,
): PerformanceTrace[] {
  const next = [
    ...current,
    {
      id: `${projectSeed}:${press.sequence}:${press.padIndex}`,
      padIndex: press.padIndex,
      role,
      signatureSeed: `${projectSeed}:${press.padIndex}:${press.sequence}`,
      expiresAt: now + beatDurationMs(bpm),
    },
  ];
  return next.slice(-MAX_TRACES);
}

export function prunePerformanceTraces(
  current: readonly PerformanceTrace[],
  now: number,
): PerformanceTrace[] {
  return current.filter((trace) => trace.expiresAt > now);
}
```

- [ ] **Step 4: 写 Trace Layer 失败测试**

创建 `apps/web/src/ui/generative/PerformanceTraceLayer.test.tsx`：

```tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../../patch/__fixtures__/patch.golden.json";
import type { Pad } from "../../patch/loader";
import { PerformanceTraceLayer } from "./PerformanceTraceLayer";

const pads = structuredClone(golden.pads) as unknown as Pad[];

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function motionPreference(reduced: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: reduced,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

describe("PerformanceTraceLayer", () => {
  it("renders a direct Pad press and removes it after one beat", () => {
    vi.useFakeTimers();
    motionPreference(false);
    render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );

    const layer = screen.getByTestId("performance-trace-layer");
    expect(layer).toHaveAttribute("aria-hidden", "true");
    expect(layer).toHaveStyle({ pointerEvents: "none" });
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    act(() => vi.advanceTimersByTime(499));
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("clears the previous bar at the next bar boundary", () => {
    vi.useFakeTimers();
    motionPreference(false);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={60}
        playheadStep={15}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={60}
        playheadStep={16}
        projectSeed="patch-a"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });

  it("accepts sequence one again after the project seed changes", () => {
    vi.useFakeTimers();
    motionPreference(false);
    const { rerender } = render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);

    rerender(
      <PerformanceTraceLayer
        press={null}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-b"
      />,
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
    rerender(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 1 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-b"
      />,
    );
    expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
    expect(screen.getByTestId("performance-trace")).toHaveAttribute(
      "data-pad-index",
      "1",
    );
  });

  it("leaves static Pad feedback to PadButton under reduced motion", () => {
    vi.useFakeTimers();
    motionPreference(true);
    render(
      <PerformanceTraceLayer
        press={{ sequence: 1, padIndex: 0 }}
        pads={pads}
        bpm={120}
        playheadStep={0}
        projectSeed="patch-a"
      />,
    );
    expect(screen.getByTestId("performance-trace-layer")).toHaveAttribute(
      "data-reduced-motion",
      "true",
    );
    expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 5: 运行 Layer 测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/PerformanceTraceLayer.test.tsx
```

Expected: FAIL，错误包含 `Cannot find module './PerformanceTraceLayer'`。

- [ ] **Step 6: 实现 PerformanceTraceLayer**

创建 `apps/web/src/ui/generative/PerformanceTraceLayer.tsx`：

```tsx
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type { Pad } from "../../patch/loader";
import {
  appendPerformanceTrace,
  beatDurationMs,
  type PadPressEvent,
  type PerformanceTrace,
} from "./performanceTrace";
import {
  createVisualSignature,
  roleForPad,
} from "./visualSignature";

function reducedMotionPreferred(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function PerformanceTraceLayer({
  press,
  pads,
  bpm,
  playheadStep,
  projectSeed,
}: {
  press: PadPressEvent | null;
  pads: readonly Pad[];
  bpm: number;
  playheadStep: number | null;
  projectSeed: string;
}) {
  const reducedMotion = reducedMotionPreferred();
  const [traces, setTraces] = useState<PerformanceTrace[]>([]);
  const timerIds = useRef(new Set<number>());
  const lastSequence = useRef<number | null>(null);
  const lastBar = useRef<number | null>(null);
  const lastProjectSeed = useRef(projectSeed);
  const padByIndex = useMemo(
    () => new Map(pads.map((pad) => [pad.index, pad])),
    [pads],
  );

  useEffect(() => () => {
    for (const timerId of timerIds.current) window.clearTimeout(timerId);
    timerIds.current.clear();
  }, []);

  useEffect(() => {
    if (projectSeed === lastProjectSeed.current) return;
    lastProjectSeed.current = projectSeed;
    lastSequence.current = null;
    lastBar.current = null;
    setTraces([]);
    for (const timerId of timerIds.current) window.clearTimeout(timerId);
    timerIds.current.clear();
  }, [projectSeed]);

  useEffect(() => {
    if (
      reducedMotion
      || !press
      || press.sequence === lastSequence.current
    ) return;
    lastSequence.current = press.sequence;
    const pad = padByIndex.get(press.padIndex);
    if (!pad) return;
    const now = Date.now();
    setTraces((current) =>
      appendPerformanceTrace(
        current,
        press,
        roleForPad(pad),
        projectSeed,
        bpm,
        now,
      )
    );
    const timerId = window.setTimeout(() => {
      setTraces((current) =>
        current.filter(
          (trace) =>
            trace.id !== `${projectSeed}:${press.sequence}:${press.padIndex}`,
        )
      );
      timerIds.current.delete(timerId);
    }, beatDurationMs(bpm));
    timerIds.current.add(timerId);
  }, [bpm, padByIndex, press, projectSeed, reducedMotion]);

  useEffect(() => {
    if (playheadStep === null) return;
    const bar = Math.floor(playheadStep / 16);
    if (lastBar.current !== null && bar !== lastBar.current) {
      setTraces([]);
      for (const timerId of timerIds.current) window.clearTimeout(timerId);
      timerIds.current.clear();
    }
    lastBar.current = bar;
  }, [playheadStep]);

  return (
    <div
      className="performance-trace-layer"
      data-testid="performance-trace-layer"
      data-reduced-motion={String(reducedMotion)}
      aria-hidden="true"
      style={{ pointerEvents: "none" }}
    >
      {!reducedMotion && traces.map((trace) => {
        const signature = createVisualSignature(trace.signatureSeed);
        const style = {
          "--trace-angle": `${signature.angle}deg`,
          "--trace-offset": `${signature.offset}%`,
          "--trace-duration": `${beatDurationMs(bpm)}ms`,
        } as CSSProperties;
        return (
          <span
            key={trace.id}
            className={`performance-trace performance-trace--${trace.role}`}
            data-testid="performance-trace"
            data-pad-index={trace.padIndex}
            data-signature={signature.id}
            style={style}
          >
            <i className="performance-trace__mark" />
          </span>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: 运行 Task 4 测试并确认 Green**

Run:

```bash
cd apps/web
npm test -- src/ui/generative/performanceTrace.test.ts src/ui/generative/PerformanceTraceLayer.test.tsx
```

Expected: 2 个测试文件全部 PASS；Fake Timer 执行后无残留警告。

- [ ] **Step 8: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: Task 1–4 文件；不提交。

---

### Task 5: 把直接 Pad Press 接入 Workbench Trace

**Files:**
- Modify: `apps/web/src/ui/App.tsx:190-245,285-330,1172-1272`
- Modify: `apps/web/src/ui/App.test.tsx:110-180`

**Interfaces:**
- Consumes: 现有统一 `pressPad(index)`，Task 4 的 `PadPressEvent` 和
  `<PerformanceTraceLayer />`。
- Produces: 只有直接 `pressPad` 才更新的 monotonically increasing
  `padPressEvent`；Example/local 使用 `patch_id`，API 使用 `submissionId`。

- [ ] **Step 1: 写 App 直接演奏失败测试**

在 `App.test.tsx` 增加：

```tsx
it("creates one bounded visual trace only after a direct Pad press", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  renderApp(golden);
  await userEvent.click(screen.getByRole("button", { name: /示例/i }));
  await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

  expect(screen.getByTestId("performance-trace-layer")).toBeInTheDocument();
  expect(screen.queryByTestId("performance-trace")).not.toBeInTheDocument();

  fireEvent.pointerDown(screen.getByTestId("pad-0"), {
    button: 0,
    pointerId: 1,
  });
  expect(screen.getAllByTestId("performance-trace")).toHaveLength(1);
  expect(screen.getByTestId("performance-trace")).toHaveAttribute(
    "data-pad-index",
    "0",
  );
  fireEvent.pointerUp(screen.getByTestId("pad-0"), {
    button: 0,
    pointerId: 1,
  });
});
```

- [ ] **Step 2: 运行测试并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/App.test.tsx -t "creates one bounded visual trace"
```

Expected: FAIL，找不到 `performance-trace-layer`。

- [ ] **Step 3: 在 App 记录 Pad Press event**

在 `App.tsx` 增加：

```ts
import { PerformanceTraceLayer } from "./generative/PerformanceTraceLayer";
import type { PadPressEvent } from "./generative/performanceTrace";
```

在 `pressedPadIndices` state 后增加：

```ts
const [padPressEvent, setPadPressEvent] = useState<PadPressEvent | null>(null);
const padPressSequenceRef = useRef(0);
```

在 `pressPad` 的 `setPressedPadIndices` 后、`engine.triggerPad` 前增加：

```ts
padPressSequenceRef.current += 1;
setPadPressEvent({
  sequence: padPressSequenceRef.current,
  padIndex: index,
});
```

在 `enterLoaded` 中 `engine.load(bundle)` 后增加：

```ts
padPressSequenceRef.current = 0;
setPadPressEvent(null);
```

在 `showLibrary` 和 `showNewUpload` 的 `engine.stop()` 后增加：

```ts
setPadPressEvent(null);
```

- [ ] **Step 4: 在 Workbench Canvas 接入 Layer**

在 `.workbench-performance-view` 内，`PatternSurface` 前增加：

```tsx
<PerformanceTraceLayer
  press={padPressEvent}
  pads={bundle.patch.pads}
  bpm={model.bpm}
  playheadStep={playheadStep}
  projectSeed={projectSignatureSeed}
/>
```

保持 `PadMatrix16`、`MidiPanel` 和键盘监听继续调用同一个 `pressPad`。
不得从 AudioEngine active sources 或 Pattern notes 反向生成 Trace。

- [ ] **Step 5: 运行 App、Pad 与 MIDI 回归**

Run:

```bash
cd apps/web
npm test -- src/ui/App.test.tsx src/ui/PadButton.test.tsx src/ui/PadMatrix16.test.tsx src/ui/MidiPanel.test.tsx src/midi/MidiInput.test.ts
```

Expected: 5 个测试文件全部 PASS；Pointer、Keyboard、MIDI、Mute、Loop 和
Phrase 排他测试无回归。

- [ ] **Step 6: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: 仅 Task 1–5 文件；不提交。

---

### Task 6: 建立直角、零阴影 CSS 合同与平面反馈

**Files:**
- Create: `apps/web/src/ui/theme.test.ts`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Consumes: Task 2 / 4 的 class names 与现有 Workbench / flow classes。
- Produces:
  - 全文件 `box-shadow` 只能为 `none`
  - 非零 `border-radius` 仅允许生成艺术白名单
  - Project Signature 与 Performance Trace 布局
  - Hover / Pressed / Selected / Focus 平面反馈

- [ ] **Step 1: 写 CSS 静态合同失败测试**

创建 `apps/web/src/ui/theme.test.ts`：

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");

function declarationRules(name: string): Array<{
  selector: string;
  value: string;
}> {
  return css.split("}").flatMap((chunk) => {
    const open = chunk.lastIndexOf("{");
    if (open === -1) return [];
    const selector = chunk.slice(0, open).trim().split("\n").at(-1)?.trim() ?? "";
    const body = chunk.slice(open + 1);
    const expression = new RegExp(`${name}:\\s*([^;]+)`, "g");
    return [...body.matchAll(expression)].map((match) => ({
      selector,
      value: match[1].trim(),
    }));
  });
}

describe("Polanyi flat UI contract", () => {
  it("does not use shadows anywhere in the product theme", () => {
    const shadows = declarationRules("box-shadow");
    expect(shadows.length).toBeGreaterThan(0);
    expect(shadows.every(({ value }) => value === "none")).toBe(true);
  });

  it("allows rounded geometry only inside decorative generative marks", () => {
    const allowed =
      /pad-geometry|project-signature__motif|performance-trace__mark/;
    const rounded = declarationRules("border-radius").filter(
      ({ value }) => value !== "0" && value !== "0px",
    );
    expect(rounded.length).toBeGreaterThan(0);
    expect(rounded.every(({ selector }) => allowed.test(selector))).toBe(true);
  });
});
```

- [ ] **Step 2: 运行 CSS 合同并确认 Red**

Run:

```bash
cd apps/web
npm test -- src/ui/theme.test.ts
```

Expected: FAIL；输出列出当前硬阴影和非生成艺术圆角。

- [ ] **Step 3: 机械移除 UI 阴影与圆角**

编辑 `theme.css`：

1. 把全部现有 `box-shadow` 声明改为 `box-shadow: none`。
2. 把全部现有 `border-radius` 改为 `0`。
3. 只在以下生成艺术 selector 重新引入非零圆角：

```css
.pad[data-geometry-shape="circle"] .pad-geometry,
.project-signature__motif[data-shape="circle"],
.performance-trace__mark {
  border-radius: 50%;
}

.pad[data-geometry-shape="slice"] .pad-geometry,
.project-signature__motif[data-shape="slice"] {
  border-radius: 50% 0;
}

.pad[data-geometry-shape="wave"] .pad-geometry,
.project-signature__motif[data-shape="wave"] {
  border-radius: 45% 55% 40% 60%;
}
```

4. 保持所有控件 `box-sizing: border-box`。不得用新的 pseudo-element 阴影补偿。

- [ ] **Step 4: 增加 Project Signature 平面样式**

在 `theme.css` 的 Workbench flow 区域加入：

```css
.project-signature {
  --signature-color: var(--loop);
  position: relative;
  isolation: isolate;
  min-width: 0;
  overflow: hidden;
  border: 2px solid var(--ink);
  background: var(--paper);
  pointer-events: none;
}
.project-signature[data-phase="queued"],
.project-signature[data-phase="preflight"] { --signature-color: var(--yellow); }
.project-signature[data-phase="separating"],
.project-signature[data-phase="extracting"],
.project-signature[data-phase="patchifying"],
.project-signature[data-phase="processing"] { --signature-color: var(--mint); }
.project-signature[data-phase="ready"] { --signature-color: var(--lead); }
.project-signature[data-phase="review"] { --signature-color: var(--yellow); }
.project-signature[data-phase="error"] { --signature-color: var(--red); }
.project-signature[data-variant="band"] { width: 96px; min-height: 58px; }
.project-signature[data-variant="stage"] { min-height: 116px; }
.project-signature[data-variant="stamp"] { min-height: 72px; }
.project-signature__grid {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
}
.project-signature__grid i {
  border-right: 1px solid var(--ink);
  background: transparent;
}
.project-signature__grid i:last-child { border-right: 0; }
.project-signature__grid i[data-active="true"] {
  background: var(--signature-color);
}
.project-signature__motif {
  position: absolute;
  right: calc(var(--signature-offset) * -0.2);
  bottom: -35%;
  width: clamp(52px, 22%, 118px);
  aspect-ratio: 1;
  border: 3px solid var(--ink);
  background:
    repeating-linear-gradient(
      var(--signature-angle),
      color-mix(in srgb, var(--signature-color) 76%, var(--paper)) 0 7px,
      transparent 7px 14px
    );
  transform: rotate(var(--signature-angle));
}
.song-card {
  grid-template-columns: minmax(0, 1fr) 96px auto;
}
.processing-panel > .project-signature {
  width: 100%;
}
.export-checklist > .project-signature {
  margin-bottom: 12px;
}
```

- [ ] **Step 5: 增加 Performance Trace 与平面交互样式**

在 `theme.css` 加入：

```css
.workbench-performance-view {
  position: relative;
  isolation: isolate;
}
.performance-trace-layer {
  position: absolute;
  z-index: 8;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.performance-trace {
  --trace-color: var(--action);
  position: absolute;
  left: calc((var(--trace-offset) / 100) * 58%);
  bottom: 4%;
  width: 44%;
  height: 54%;
  border: 5px solid var(--trace-color);
  border-left-color: transparent;
  border-bottom-color: transparent;
  opacity: .72;
  transform: skewX(-18deg) rotate(var(--trace-angle));
  animation: performance-trace-fade var(--trace-duration) linear forwards;
}
.performance-trace--drums { --trace-color: var(--drums); }
.performance-trace--bass { --trace-color: var(--bass); }
.performance-trace--harmony { --trace-color: var(--harmony); }
.performance-trace--lead { --trace-color: var(--lead); }
.performance-trace--action { --trace-color: var(--action); }
.performance-trace--empty { --trace-color: var(--muted); }
.performance-trace__mark {
  position: absolute;
  right: 8%;
  top: 8%;
  width: 14px;
  height: 14px;
  border: 3px solid var(--ink);
  background: var(--trace-color);
}
@keyframes performance-trace-fade {
  from { opacity: .72; }
  to { opacity: 0; }
}

.pad:hover {
  background: var(--ink);
  color: var(--paper);
  transform: none;
}
.pad[data-pressed="true"] {
  border-width: 5px;
  background: var(--pad-role);
  color: var(--ink);
  transform: translateY(1px);
}
.pad[data-selected="true"]::after {
  content: "";
  position: absolute;
  z-index: 4;
  inset: 3px;
  border: 2px solid var(--ink);
  pointer-events: none;
}
.pad:focus-visible {
  outline: 3px solid var(--paper);
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .performance-trace { display: none; }
  .pad,
  .pad:hover,
  .pad[data-pressed="true"] {
    transition: none;
    transform: none;
  }
}
```

删除旧 `.pad:hover`、`.pad:focus-visible`、`.pad--selected` 和
`.pad[data-pressed="true"]` 中的阴影、上移、Scale 和回弹定义，避免重复规则
互相覆盖。

- [ ] **Step 6: 运行 CSS 合同与 UI 单测**

Run:

```bash
cd apps/web
npm test -- src/ui/theme.test.ts src/ui/generative/ProjectSignature.test.tsx src/ui/generative/PerformanceTraceLayer.test.tsx src/ui/PadButton.test.tsx
```

Expected: 4 个测试文件全部 PASS。

- [ ] **Step 7: 运行静态审计**

Run:

```bash
cd apps/web
rg -n "box-shadow:" src/ui/theme.css
rg -n "border-radius:" src/ui/theme.css
```

Expected:

- 每个 `box-shadow` 值都是 `none`；
- 非零 `border-radius` 只属于 `.pad-geometry`、
  `.project-signature__motif` 或 `.performance-trace__mark`。

- [ ] **Step 8: 检查本任务边界**

Run:

```bash
git diff --check
git status --short
```

Expected: Task 1–6 文件；不提交。

---

### Task 7: 浏览器验收、Spec 状态与单一原子提交

**Files:**
- Modify: `apps/web/e2e/workbench-responsive.spec.ts`
- Modify: `docs/superpowers/specs/2026-07-27-polanyi-living-instrument-ui-design.md`
- Stage: Task 1–7 的全部任务文件，且只能是本计划 File Map 中的路径

**Interfaces:**
- Consumes: Task 1–6 的完整实现。
- Produces: computed-style 和响应式证据、更新后的 Spec 状态、一个
  Conventional Commit。

- [ ] **Step 1: 增加 computed-style helper**

在 `workbench-responsive.spec.ts` 的 `visualSignature` helper 后增加：

```ts
async function expectRectilinearShadowless(locator: Locator): Promise<void> {
  const style = await locator.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      borderRadius: computed.borderRadius,
      boxShadow: computed.boxShadow,
    };
  });
  expect(style.borderRadius).toBe("0px");
  expect(style.boxShadow).toBe("none");
}
```

- [ ] **Step 2: 写 Workbench 平面 UI 浏览器测试**

在 `workbench-responsive.spec.ts` 增加：

```ts
test("Creator UI is rectilinear and shadowless while generative marks stay decorative", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openExampleWithMissingAsset(page);

  const surfaces = [
    page.getByTestId("workbench-shell"),
    page.getByTestId("app-bar"),
    page.getByTestId("pattern-surface"),
    page.getByTestId("pad-0"),
    page.getByTestId("context-inspector"),
    page.getByTestId("status-bar"),
  ];
  for (const surface of surfaces) {
    await expectRectilinearShadowless(surface);
  }

  const traceLayer = page.getByTestId("performance-trace-layer");
  await expect(traceLayer).toHaveCSS("pointer-events", "none");
  await page.getByTestId("pad-0").dispatchEvent("pointerdown", {
    button: 0,
    pointerId: 1,
    isPrimary: true,
  });
  const trace = page.getByTestId("performance-trace");
  await expect(trace).toBeVisible();
  const canvasBox = await box(page.getByTestId("instrument-canvas"));
  const traceBox = await box(trace);
  expect(traceBox.x).toBeGreaterThanOrEqual(canvasBox.x);
  expect(traceBox.y).toBeGreaterThanOrEqual(canvasBox.y);
  expect(traceBox.x + traceBox.width).toBeLessThanOrEqual(
    canvasBox.x + canvasBox.width,
  );
  expect(traceBox.y + traceBox.height).toBeLessThanOrEqual(
    canvasBox.y + canvasBox.height,
  );
});
```

- [ ] **Step 3: 写 Reduced Motion 浏览器测试**

增加：

```ts
test("Reduced Motion keeps direct Pad feedback without a moving trace", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openExampleWithMissingAsset(page);
  await page.getByTestId("pad-0").dispatchEvent("pointerdown", {
    button: 0,
    pointerId: 1,
    isPrimary: true,
  });

  await expect(page.getByTestId("pad-0")).toHaveAttribute(
    "data-pressed",
    "true",
  );
  await expect(page.getByTestId("performance-trace")).toHaveCount(0);
});
```

- [ ] **Step 4: 运行新增浏览器测试并修正真实布局问题**

Run:

```bash
cd apps/web
npm run test:e2e -- workbench-responsive.spec.ts --grep "rectilinear|Reduced Motion"
```

Expected: 2 个新增测试 PASS。若 Trace 越界，只调整
`.performance-trace-layer / .performance-trace` 尺寸或裁切；不得移动 Pad、
Pattern、Inspector 或 Status Bar 来迁就装饰层。

- [ ] **Step 5: 运行完整 Web 验证**

Run:

```bash
cd apps/web
npm test
npm run check-contract
npm run build
npm run test:e2e -- workbench-responsive.spec.ts
```

Expected:

- Vitest 全部 PASS；
- Contract 检查 PASS；
- TypeScript / Vite build exit 0；
- Playwright 七档视口与新增 flat UI / trace tests 全部 PASS；
- 控制台无 React act、Timer、Audio 或 hydration warning。

- [ ] **Step 6: 更新 Spec 状态和验证记录**

在
`docs/superpowers/specs/2026-07-27-polanyi-living-instrument-ui-design.md`
把状态改为：

```markdown
- 状态：本分支已实现并通过自动化验证；待 PR / CI
```

在文末增加：

````markdown
## 20. 本分支实现验证

实现范围：

- 共享确定性 Visual Signature；
- My Songs / Processing / Workbench / Export 的同 seed 视觉连续性；
- 直接 Pad Press 的一拍 Performance Trace；
- 全部 UI 直角、零阴影和平面反馈；
- Reduced Motion、响应式、状态真实性与契约纯度回归。

验证命令：

```bash
cd apps/web
npm test
npm run check-contract
npm run build
npm run test:e2e -- workbench-responsive.spec.ts
```

该状态只表示本实现分支通过本地自动化验证，不表示已推送、已创建 PR、已合并
或已部署。
````

- [ ] **Step 7: 最终范围审计**

Run:

```bash
git diff --check
git status --short
git diff --name-only
```

Expected: 只包含 File Map 中列出的实现、测试、CSS、E2E 和本 Spec；不得包含
`.superpowers/brainstorm/`、生成 build 产物、契约生成物或无关文件。

- [ ] **Step 8: 创建本实现回合唯一原子提交**

Stage 只包含 `git diff --name-only` 中经 Task 7 审计通过的文件：

```bash
git add \
  apps/web/src/ui/generative/visualSignature.ts \
  apps/web/src/ui/generative/visualSignature.test.ts \
  apps/web/src/ui/generative/ProjectSignature.tsx \
  apps/web/src/ui/generative/ProjectSignature.test.tsx \
  apps/web/src/ui/generative/performanceTrace.ts \
  apps/web/src/ui/generative/performanceTrace.test.ts \
  apps/web/src/ui/generative/PerformanceTraceLayer.tsx \
  apps/web/src/ui/generative/PerformanceTraceLayer.test.tsx \
  apps/web/src/ui/PadButton.tsx \
  apps/web/src/ui/PadButton.test.tsx \
  apps/web/src/ui/MySongsView.tsx \
  apps/web/src/ui/MySongsView.test.tsx \
  apps/web/src/ui/NewSongView.tsx \
  apps/web/src/ui/NewSongView.test.tsx \
  apps/web/src/ui/ProcessingPanel.tsx \
  apps/web/src/ui/ProcessingPanel.test.tsx \
  apps/web/src/ui/ExportChecklist.tsx \
  apps/web/src/ui/ExportChecklist.test.tsx \
  apps/web/src/ui/App.tsx \
  apps/web/src/ui/App.test.tsx \
  apps/web/src/ui/theme.css \
  apps/web/src/ui/theme.test.ts \
  apps/web/e2e/workbench-responsive.spec.ts \
  docs/superpowers/specs/2026-07-27-polanyi-living-instrument-ui-design.md
git diff --cached --check
git diff --cached --name-only
git commit -m "feat(web): build Polanyi living instrument UI"
```

Expected: 一个 Conventional Commit；不得出现额外 staged 文件。

- [ ] **Step 9: 提交后核对**

Run:

```bash
git show --stat --name-status --oneline HEAD
git status --short --branch
```

Expected:

- Commit 只包含 Task 1–7 文件；
- Worktree 无 task-local 未提交修改；
- 不 push、不创建 PR、不 merge、不 deploy。

---

## Final Acceptance Checklist

- [ ] Visual Signature 相同 seed 稳定、不同 seed 可观察不同。
- [ ] API submission 用 `submissionId` 贯穿 My Songs、Processing、Loaded 和 Export。
- [ ] Local / Example 不伪造服务端 Export；Workbench 使用 `patch_id`。
- [ ] 直接 Pointer、Keyboard、Touch 和 MIDI Pad Press 进入同一 Trace 路径。
- [ ] Pattern 自动播放不生成 Trace。
- [ ] Trace 一拍过期、小节清理、最多 8 条、`pointer-events: none`。
- [ ] Reduced Motion 无移动 Trace，Pad 仍有静态 Pressed 状态。
- [ ] 所有 UI 直角、零阴影。
- [ ] 非零圆角只存在于生成艺术白名单。
- [ ] Hover 反色、Pressed 内增边框、Selected 内框、Focus 使用 outline。
- [ ] 错误、未知 Job 状态、Needs Review、Partial 和 Export blocker 仍显性。
- [ ] 8×2 / 4×4 Pad、Square Pad、Uniform Gap、Inspector Focus Trap 不退化。
- [ ] 不读取 Worker 私有文件，不修改 `lmdj.patch.v1`。
- [ ] 不新增运行时或开发依赖。
- [ ] `npm test`、`check-contract`、`build`、Playwright 全部通过。
- [ ] 本实现回合只有一个原子提交。
- [ ] 未 push、未创建 PR、未 merge、未 deploy。
