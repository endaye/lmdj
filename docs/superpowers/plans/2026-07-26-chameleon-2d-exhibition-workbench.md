# Chameleon 2D Exhibition Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不引入 3D Runtime 的前提下，把已批准的 Chameleon 线稿变成首页主上传入口、工作台 Assistant Dock 和真实产品状态可视化层。

**Architecture:** 在 `apps/web/src/chameleon/` 建立纯状态 Adapter、确定性 Visual Signature、单次展开 Controller 和可替换 2D Renderer。`App` 只提供现有上传、Job、Patch 与 AudioEngine 的公开状态；`WorkbenchShell` 只预留不遮挡内容的 Assistant 槽位。PNG、未来 SVG 与未来 3D 共享同一 Visual State，不修改 `lmdj.patch.v1` 或 API 契约。

**Tech Stack:** React 19、TypeScript 5.7、Vite 8、CSS Container Queries、Vitest、React Testing Library、Playwright；不新增运行时依赖。

## Global Constraints

- 执行分支必须是包含设计提交 `eb386da1` 的短期 `codex/` 分支；不得直接修改 `main`。
- 如果 `eb386da1` 已经通过 PR 进入 `main`，先同步 `main`，再建立 `codex/chameleon-exhibition-workbench` 隔离 worktree；如果尚未合并，必须明确记录实现分支以哪个提交为基底。
- 本计划只交付 2D 初版；不得安装 Three.js、React Three Fiber、Drei 或提交 GLB。
- 当前品牌源资产保持在 `docs/prd/assets/chameleon/chameleon-line-logo-approved-v1.png`，不得覆盖或重编码源文件。
- Web 运行时派生 PNG 固定为 512×512，文件大小不得超过 204800 bytes。
- 页面背景使用现有 `--paper: #f6f2e8`，结构使用 `--ink: #11110f`；音乐角色继续使用现有 Drums、Bass、Harmony、Lead、Loop、Action 色。
- Chameleon 只能消费浏览器交互、公开 Job 状态、`patch.json` 与 AudioEngine 的真实播放状态。
- 不读取或公开 `materials.json`、stems、`lanes.json`、`chart.mid` 或 Worker 私有文件。
- 不显示虚构阶段或进度百分比；未知 Worker 状态必须保留原始状态名。
- `ready` 每个事件自动展开一次并在 4000ms 后收起；`error` 每个事件自动展开一次并保持到用户关闭。
- 首页角色必须支持点击、Enter、Space 和音频文件拖放；状态不能只靠颜色。
- `prefers-reduced-motion: reduce` 下取消呼吸、视差、脉冲和路径动画。
- UI 继续只显示产品 SemVer 或 `dev`；Git SHA 只保留在 Console 与 `/health`。
- 每个 Task 必须先出现失败测试，再做最小实现，通过本 Task 的聚焦测试后创建一个 Conventional Commit。

---

## File Map

### 新建文件

- `apps/web/src/assets/chameleon-line-logo-approved-v1.png`
  - 由批准源图生成的 512×512 Web 派生图。
- `apps/web/src/chameleon/model.ts`
  - Renderer 无关的状态、事件、角色和 Signature 类型。
- `apps/web/src/chameleon/adapter.ts`
  - 将 App、Job、播放与交互输入映射为唯一 Visual State。
- `apps/web/src/chameleon/adapter.test.ts`
  - 状态优先级、真实标签和事件身份测试。
- `apps/web/src/chameleon/visualSignature.ts`
  - 从公开种子生成稳定的角度、偏移、密度和强调色。
- `apps/web/src/chameleon/visualSignature.test.ts`
  - 确定性和差异性测试。
- `apps/web/src/chameleon/playback.ts`
  - 将 AudioEngine 的真实 active element IDs 映射为公开 Pad 角色。
- `apps/web/src/chameleon/playback.test.ts`
  - 单角色、混合角色和空播放测试。
- `apps/web/src/chameleon/useChameleonController.ts`
  - 手动展开、单次自动展开、4000ms ready 收起和 error 保持。
- `apps/web/src/chameleon/useChameleonController.test.tsx`
  - Fake Timer 驱动的 Controller 生命周期测试。
- `apps/web/src/chameleon/viewTransition.ts`
  - 用可选 View Transitions API 连接 Gallery Stage 与 Dock；Reduced Motion 和不支持环境同步回退。
- `apps/web/src/chameleon/viewTransition.test.ts`
  - View Transition、无 API 和 Reduced Motion 三条路径测试。
- `apps/web/src/chameleon/Chameleon2D.tsx`
  - 当前 PNG Renderer 与图片失败占位。
- `apps/web/src/chameleon/Chameleon2D.test.tsx`
  - 媒体渲染、状态属性和失败回退测试。
- `apps/web/src/chameleon/ChameleonSurface.tsx`
  - Gallery Stage、Dock 和无框 Floating 三种位置语义。
- `apps/web/src/chameleon/ChameleonSurface.test.tsx`
  - Button、状态文字、alert/status 与关闭行为测试。
- `apps/web/src/chameleon/ChameleonUploadStage.tsx`
  - 首页 API Base、隐藏 File Input、点击和拖放上传入口。
- `apps/web/src/chameleon/ChameleonUploadStage.test.tsx`
  - 点击选文件、键盘、拖放和非法文件测试。
- `apps/web/src/ui/Wordmark.tsx`
  - Gallery 与 Workbench 共享的 LMDJ Wordmark。
- `apps/web/e2e/chameleon-exhibition.spec.ts`
  - 390、768、1440px 布局、无关键遮挡和 Reduced Motion 验收。

### 修改文件

- `apps/web/src/engine/AudioEngine.ts`
  - 暴露真实 active 状态与 active element IDs，并在 source 开始、结束时通知。
- `apps/web/src/engine/AudioEngine.test.ts`
  - 真实 source 生命周期测试。
- `apps/web/src/ui/SourcePanel.tsx`
  - 改为 Gallery Stage，使用 Chameleon 主上传入口，保留 Patch Package 次入口。
- `apps/web/src/ui/SourcePanel.test.tsx`
  - Gallery 结构与上传入口测试。
- `apps/web/src/ui/WorkbenchShell.tsx`
  - 新增正式 Assistant 槽位和 expanded 布局属性。
- `apps/web/src/ui/WorkbenchShell.test.tsx`
  - Assistant 槽位、landmark 顺序与 Inspector inert 边界测试。
- `apps/web/src/ui/App.tsx`
  - 注入真实 Visual State、Controller、Signature、Dock 与 Gallery 页面。
- `apps/web/src/ui/App.test.tsx`
  - API Job、ready/error 单次展开和真实播放映射集成测试。
- `apps/web/src/ui/theme.css`
  - Exhibition Workbench 表面、Chameleon 图形、Dock、响应式和 Reduced Motion。
- `docs/superpowers/specs/2026-07-26-chameleon-exhibition-workbench-design.md`
  - 全部验收通过后，将状态更新为“2D 初版已实现”，记录验证命令与仍未实现的 SVG/3D。

---

### Task 1: 建立纯 Visual State 与确定性 Signature

**Files:**
- Create: `apps/web/src/chameleon/model.ts`
- Create: `apps/web/src/chameleon/adapter.ts`
- Create: `apps/web/src/chameleon/adapter.test.ts`
- Create: `apps/web/src/chameleon/visualSignature.ts`
- Create: `apps/web/src/chameleon/visualSignature.test.ts`

**Interfaces:**
- Consumes: App 的 `phase`、公开 `jobState`、`queuePosition`、`patchId`、错误身份、真实播放布尔值与 Pad 角色。
- Produces: `deriveChameleonVisualState(input): ChameleonVisualState` 与 `createVisualSignature(seed, state): ChameleonVisualSignature`。

- [ ] **Step 1: 写 Adapter 失败测试**

创建 `apps/web/src/chameleon/adapter.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";

describe("deriveChameleonVisualState", () => {
  it("maps source interaction without inventing progress", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "source",
        interaction: "drag-ready",
      }),
    ).toMatchObject({
      phase: "drag-ready",
      placement: "stage",
      label: "Drop WAV or MP3",
      event: null,
    });
  });

  it.each([
    ["preflight", "uploading", "Uploading source"],
    ["queued", "queued", "Queued · position 2"],
    ["separating", "separating", "Separating stems"],
    ["extracting", "extracting", "Extracting materials"],
    ["patchifying", "patchifying", "Building 16-pad Patch"],
  ] as const)("maps %s to truthful %s", (jobState, phase, label) => {
    expect(
      deriveChameleonVisualState({
        appPhase: "processing",
        jobState,
        queuePosition: 2,
      }),
    ).toMatchObject({ phase, placement: "dock", label, event: null });
  });

  it("retains an unknown worker state in the visible label", () => {
    const state = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "spectralizing",
    });
    expect(state.label).toBe("Processing · spectralizing");
    expect(state.label).not.toMatch(/\d+%/);
  });

  it("gives error priority over playback", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "failed",
        errorKey: "submission-1:separating",
        errorLabel: "Service interrupted",
        isPlaying: true,
      }),
    ).toMatchObject({
      phase: "error",
      tone: "danger",
      label: "Service interrupted",
      event: { kind: "error", key: "submission-1:separating" },
    });
  });

  it("uses a stable Patch identity for ready and actual role for playing", () => {
    expect(
      deriveChameleonVisualState({
        appPhase: "loaded",
        patchId: "source-abc-patch",
      }),
    ).toMatchObject({
      phase: "ready",
      event: { kind: "ready", key: "source-abc-patch" },
    });
    expect(
      deriveChameleonVisualState({
        appPhase: "loaded",
        patchId: "source-abc-patch",
        isPlaying: true,
        playbackRole: "bass",
      }),
    ).toMatchObject({
      phase: "playing",
      label: "Playing bass",
      event: null,
    });
  });
});
```

- [ ] **Step 2: 运行 Adapter 测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/adapter.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './adapter'`。

- [ ] **Step 3: 实现 Renderer 无关类型**

创建 `apps/web/src/chameleon/model.ts`：

```ts
export type ChameleonPhase =
  | "idle"
  | "drag-ready"
  | "uploading"
  | "queued"
  | "separating"
  | "extracting"
  | "patchifying"
  | "ready"
  | "playing"
  | "error";

export type ChameleonPlacement = "stage" | "dock" | "floating";
export type ChameleonTone = "neutral" | "active" | "success" | "danger";
export type ChameleonMotion =
  | "still"
  | "ambient"
  | "processing"
  | "celebrate"
  | "recoil";
export type ChameleonPlaybackRole =
  | "drums"
  | "bass"
  | "harmony"
  | "lead"
  | "loop"
  | "action"
  | "mixed"
  | null;

export interface ChameleonEvent {
  kind: "ready" | "error";
  key: string;
}

export interface ChameleonVisualState {
  phase: ChameleonPhase;
  placement: ChameleonPlacement;
  label: string;
  tone: ChameleonTone;
  motion: ChameleonMotion;
  playbackRole: ChameleonPlaybackRole;
  event: ChameleonEvent | null;
}

export interface ChameleonStateInput {
  appPhase: "source" | "processing" | "failed" | "loaded";
  jobState?: string | null;
  queuePosition?: number | null;
  patchId?: string | null;
  errorKey?: string | null;
  errorLabel?: string | null;
  isPlaying?: boolean;
  playbackRole?: ChameleonPlaybackRole;
  interaction?: "none" | "drag-ready";
}

export interface ChameleonVisualSignature {
  seed: number;
  angle: number;
  offset: number;
  density: number;
  accent:
    | "neutral"
    | "drums"
    | "bass"
    | "harmony"
    | "lead"
    | "loop"
    | "action"
    | "mixed"
    | "success"
    | "danger";
}
```

- [ ] **Step 4: 实现状态 Adapter**

创建 `apps/web/src/chameleon/adapter.ts`：

```ts
import type {
  ChameleonStateInput,
  ChameleonVisualState,
} from "./model";

function state(
  value: Omit<ChameleonVisualState, "playbackRole">,
  input: ChameleonStateInput,
): ChameleonVisualState {
  return {
    ...value,
    playbackRole: input.playbackRole ?? null,
  };
}

export function deriveChameleonVisualState(
  input: ChameleonStateInput,
): ChameleonVisualState {
  if (input.appPhase === "failed") {
    return state({
      phase: "error",
      placement: "dock",
      label: input.errorLabel ?? "Processing failed",
      tone: "danger",
      motion: "recoil",
      event: {
        kind: "error",
        key: input.errorKey ?? "error:unknown",
      },
    }, input);
  }

  if (input.appPhase === "source") {
    const dragReady = input.interaction === "drag-ready";
    return state({
      phase: dragReady ? "drag-ready" : "idle",
      placement: "stage",
      label: dragReady ? "Drop WAV or MP3" : "Ready for a track",
      tone: dragReady ? "active" : "neutral",
      motion: dragReady ? "processing" : "ambient",
      event: null,
    }, input);
  }

  if (input.appPhase === "loaded") {
    if (input.isPlaying) {
      const role = input.playbackRole ?? "mixed";
      return state({
        phase: "playing",
        placement: "dock",
        label: `Playing ${role}`,
        tone: "active",
        motion: "processing",
        event: null,
      }, input);
    }
    const patchId = input.patchId ?? "patch:unknown";
    return state({
      phase: "ready",
      placement: "dock",
      label: "Patch ready",
      tone: "success",
      motion: "celebrate",
      event: { kind: "ready", key: patchId },
    }, input);
  }

  const jobState = input.jobState ?? "preflight";
  if (jobState === "preflight") {
    return state({
      phase: "uploading",
      placement: "dock",
      label: "Uploading source",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "queued") {
    return state({
      phase: "queued",
      placement: "dock",
      label: input.queuePosition == null
        ? "Queued"
        : `Queued · position ${input.queuePosition}`,
      tone: "active",
      motion: "ambient",
      event: null,
    }, input);
  }
  if (jobState === "separating") {
    return state({
      phase: "separating",
      placement: "dock",
      label: "Separating stems",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "extracting") {
    return state({
      phase: "extracting",
      placement: "dock",
      label: "Extracting materials",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  if (jobState === "patchifying") {
    return state({
      phase: "patchifying",
      placement: "dock",
      label: "Building 16-pad Patch",
      tone: "active",
      motion: "processing",
      event: null,
    }, input);
  }
  return state({
    phase: "patchifying",
    placement: "dock",
    label: `Processing · ${jobState}`,
    tone: "active",
    motion: "processing",
    event: null,
  }, input);
}
```

- [ ] **Step 5: 写 Signature 失败测试**

创建 `apps/web/src/chameleon/visualSignature.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";

describe("createVisualSignature", () => {
  const ready = deriveChameleonVisualState({
    appPhase: "loaded",
    patchId: "patch-a",
  });

  it("is deterministic for the same public seed and state", () => {
    expect(createVisualSignature("patch-a", ready)).toEqual(
      createVisualSignature("patch-a", ready),
    );
  });

  it("changes when the public Patch identity changes", () => {
    expect(createVisualSignature("patch-a", ready)).not.toEqual(
      createVisualSignature("patch-b", ready),
    );
  });

  it("uses semantic accents rather than private pipeline data", () => {
    expect(createVisualSignature("patch-a", ready).accent).toBe("success");
    const playing = deriveChameleonVisualState({
      appPhase: "loaded",
      patchId: "patch-a",
      isPlaying: true,
      playbackRole: "drums",
    });
    expect(createVisualSignature("patch-a", playing).accent).toBe("drums");
  });
});
```

- [ ] **Step 6: 运行 Signature 测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/visualSignature.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './visualSignature'`。

- [ ] **Step 7: 实现确定性 Signature**

创建 `apps/web/src/chameleon/visualSignature.ts`：

```ts
import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";

function hash(value: string): number {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return result >>> 0;
}

export function createVisualSignature(
  publicSeed: string,
  state: ChameleonVisualState,
): ChameleonVisualSignature {
  const seed = hash(`${publicSeed}:${state.phase}`);
  const accent =
    state.tone === "danger"
      ? "danger"
      : state.tone === "success"
        ? "success"
        : state.phase === "playing" && state.playbackRole
          ? state.playbackRole
          : "neutral";
  return {
    seed,
    angle: (seed % 361) / 10 - 18,
    offset: ((seed >>> 8) % 61) - 30,
    density: 2 + ((seed >>> 16) % 4),
    accent,
  };
}
```

- [ ] **Step 8: 运行聚焦测试**

Run:

```bash
cd apps/web
npm test -- src/chameleon/adapter.test.ts src/chameleon/visualSignature.test.ts
```

Expected: 2 个 test files 全部 PASS。

- [ ] **Step 9: 提交**

```bash
git add apps/web/src/chameleon/model.ts apps/web/src/chameleon/adapter.ts apps/web/src/chameleon/adapter.test.ts apps/web/src/chameleon/visualSignature.ts apps/web/src/chameleon/visualSignature.test.ts
git commit -m "feat(web): define Chameleon visual state"
```

---

### Task 2: 暴露真实播放生命周期与 Pad 角色

**Files:**
- Modify: `apps/web/src/engine/AudioEngine.ts`
- Modify: `apps/web/src/engine/AudioEngine.test.ts`
- Create: `apps/web/src/chameleon/playback.ts`
- Create: `apps/web/src/chameleon/playback.test.ts`

**Interfaces:**
- Consumes: AudioEngine 已有 `activeSources` 和 Patch 的公开 `pads[].role`。
- Produces: `engine.active`、`engine.activeElementIds()` 与 `activePlaybackRole(patch, ids)`。

- [ ] **Step 1: 写 AudioEngine 失败测试**

在 `apps/web/src/engine/AudioEngine.test.ts` 追加：

```ts
it("reports real active sources and notifies when the final source ends", () => {
  engine.load(makeBundle(materialPlaybackPatch()));
  const events: boolean[] = [];
  const unsubscribe = engine.subscribe(() => events.push(engine.active));

  engine.triggerPad(0);
  expect(engine.active).toBe(true);
  expect(engine.activeElementIds().size).toBe(1);

  ctx.sources.at(-1)!.onended?.({ type: "ended" });
  expect(engine.active).toBe(false);
  expect(engine.activeElementIds()).toEqual(new Set());
  expect(events).toEqual([true, false]);
  unsubscribe();
});
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/engine/AudioEngine.test.ts
```

Expected: FAIL，TypeScript 指出 `active` 和 `activeElementIds` 不存在。

- [ ] **Step 3: 实现真实 active 快照**

在 `AudioEngine` 的 `playing` getter 后增加：

```ts
get active(): boolean {
  return this.timer !== null || this.activeSources.size > 0;
}

activeElementIds(): Set<string> {
  return new Set(
    [...this.activeSources].map((source) => source.elementId),
  );
}
```

在 `playElement` 中把 `onended` 和 source 登记改为：

```ts
endedSource.onended = () => {
  if (this.activeSources.delete(active)) this.emit();
};
this.activeSources.add(active);
source.start(when ?? this.ctx.currentTime);
this.emit();
```

保留 `stop()` 现有的单次 `emit()`，不要让 `stopSources()` 逐 source 重复通知。
因为 source start/end 现在也是有意义的真实状态，既有
`"notifies subscribers on play/stop/mute"` 测试不得继续断言精确为 3 次。将其
末尾改为：

```ts
expect(events.length).toBeGreaterThanOrEqual(3);
const countBeforeUnsubscribe = events.length;
unsubscribe();
engine.toggleMutePad(0);
expect(events).toHaveLength(countBeforeUnsubscribe);
```

- [ ] **Step 4: 写 Pad 角色失败测试**

创建 `apps/web/src/chameleon/playback.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import { activePlaybackRole } from "./playback";

describe("activePlaybackRole", () => {
  const patch = structuredClone(golden) as unknown as Patch;

  it("returns the actual public Pad role", () => {
    const ids = new Set(padElementIds(patch.pads[3]));
    expect(activePlaybackRole(patch, ids)).toBe("bass");
  });

  it("returns mixed when active elements span roles", () => {
    const ids = new Set([
      ...padElementIds(patch.pads[0]),
      ...padElementIds(patch.pads[3]),
    ]);
    expect(activePlaybackRole(patch, ids)).toBe("mixed");
  });

  it("returns null when no public Pad owns an active element", () => {
    expect(activePlaybackRole(patch, new Set(["unknown-element"]))).toBeNull();
  });
});
```

- [ ] **Step 5: 运行角色测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/playback.test.ts
```

Expected: FAIL，错误包含 `Cannot find module './playback'`。

- [ ] **Step 6: 实现公开 Pad 角色映射**

创建 `apps/web/src/chameleon/playback.ts`：

```ts
import type { Patch } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import type { ChameleonPlaybackRole } from "./model";

const SUPPORTED_ROLES = new Set([
  "drums",
  "bass",
  "harmony",
  "lead",
  "loop",
  "action",
]);

export function activePlaybackRole(
  patch: Patch,
  activeElementIds: ReadonlySet<string>,
): ChameleonPlaybackRole {
  const roles = new Set<string>();
  for (const pad of patch.pads) {
    if (!padElementIds(pad).some((id) => activeElementIds.has(id))) continue;
    if (typeof pad.role === "string" && SUPPORTED_ROLES.has(pad.role)) {
      roles.add(pad.role);
    }
  }
  if (roles.size === 0) return null;
  if (roles.size > 1) return "mixed";
  return [...roles][0] as Exclude<ChameleonPlaybackRole, null | "mixed">;
}
```

- [ ] **Step 7: 运行聚焦测试**

Run:

```bash
cd apps/web
npm test -- src/engine/AudioEngine.test.ts src/chameleon/playback.test.ts
```

Expected: 2 个 test files 全部 PASS，既有 AudioEngine 测试不回归。

- [ ] **Step 8: 提交**

```bash
git add apps/web/src/engine/AudioEngine.ts apps/web/src/engine/AudioEngine.test.ts apps/web/src/chameleon/playback.ts apps/web/src/chameleon/playback.test.ts
git commit -m "feat(web): expose truthful playback state"
```

---

### Task 3: 实现单次展开 Controller

**Files:**
- Create: `apps/web/src/chameleon/useChameleonController.ts`
- Create: `apps/web/src/chameleon/useChameleonController.test.tsx`
- Create: `apps/web/src/chameleon/viewTransition.ts`
- Create: `apps/web/src/chameleon/viewTransition.test.ts`

**Interfaces:**
- Consumes: Task 1 的 `ChameleonVisualState.event`。
- Produces: `useChameleonController(state, readyDurationMs)`，返回最终 placement、`expanded`、`reveal()`、`dismiss()`、`toggle()`；`runChameleonViewTransition(update)` 提供有能力检测的共享位置过渡。

- [ ] **Step 1: 写 Hook 失败测试**

创建 `apps/web/src/chameleon/useChameleonController.test.tsx`：

```tsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { useChameleonController } from "./useChameleonController";

describe("useChameleonController", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("keeps the Gallery Stage visible", () => {
    const visual = deriveChameleonVisualState({ appPhase: "source" });
    const { result } = renderHook(() => useChameleonController(visual));
    expect(result.current.expanded).toBe(true);
    expect(result.current.visualState.placement).toBe("stage");
  });

  it("reveals ready once, closes after 4000ms, and does not replay the same key", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "loaded",
      patchId: "patch-1",
    });
    const { result, rerender } = renderHook(
      ({ state }) => useChameleonController(state),
      { initialProps: { state: visual } },
    );
    expect(result.current.expanded).toBe(true);
    expect(result.current.visualState.placement).toBe("floating");

    act(() => vi.advanceTimersByTime(4000));
    expect(result.current.expanded).toBe(false);
    rerender({ state: { ...visual } });
    expect(result.current.expanded).toBe(false);
  });

  it("keeps error open until dismissed", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "failed",
      errorKey: "submission-1:upload",
    });
    const { result } = renderHook(() => useChameleonController(visual));
    act(() => vi.advanceTimersByTime(10000));
    expect(result.current.expanded).toBe(true);
    act(() => result.current.dismiss());
    expect(result.current.expanded).toBe(false);
  });

  it("never auto-closes a manual reveal", () => {
    const visual = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "separating",
    });
    const { result } = renderHook(() => useChameleonController(visual));
    act(() => result.current.reveal());
    act(() => vi.advanceTimersByTime(10000));
    expect(result.current.expanded).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/useChameleonController.test.tsx
```

Expected: FAIL，错误包含 `Cannot find module './useChameleonController'`。

- [ ] **Step 3: 实现 Controller**

创建 `apps/web/src/chameleon/useChameleonController.ts`：

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChameleonVisualState } from "./model";

export function useChameleonController(
  input: ChameleonVisualState,
  readyDurationMs = 4000,
) {
  const seenEvents = useRef(new Set<string>());
  const [manualOpen, setManualOpen] = useState(false);
  const [automaticOpen, setAutomaticOpen] = useState(false);
  const eventKind = input.event?.kind ?? null;
  const eventKey = input.event?.key ?? null;

  useEffect(() => {
    if (input.placement === "stage") {
      setManualOpen(false);
      setAutomaticOpen(false);
      return;
    }
    if (!eventKind || !eventKey) return;
    if (seenEvents.current.has(`${eventKind}:${eventKey}`)) return;
    seenEvents.current.add(`${eventKind}:${eventKey}`);
    setAutomaticOpen(true);
    if (eventKind !== "ready") return;
    const timer = window.setTimeout(
      () => setAutomaticOpen(false),
      readyDurationMs,
    );
    return () => window.clearTimeout(timer);
  }, [eventKey, eventKind, input.placement, readyDurationMs]);

  const reveal = useCallback(() => setManualOpen(true), []);
  const dismiss = useCallback(() => {
    setManualOpen(false);
    setAutomaticOpen(false);
  }, []);
  const expanded =
    input.placement === "stage" || manualOpen || automaticOpen;
  const toggle = useCallback(() => {
    if (expanded) dismiss();
    else reveal();
  }, [dismiss, expanded, reveal]);

  return {
    expanded,
    visualState: {
      ...input,
      placement:
        input.placement === "stage"
          ? "stage" as const
          : expanded
            ? "floating" as const
            : "dock" as const,
    },
    reveal,
    dismiss,
    toggle,
  };
}
```

- [ ] **Step 4: 写共享位置过渡失败测试**

创建 `apps/web/src/chameleon/viewTransition.test.ts`：

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { runChameleonViewTransition } from "./viewTransition";

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "startViewTransition");
});

function media(matches: boolean): MediaQueryList {
  return {
    matches,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
}

describe("runChameleonViewTransition", () => {
  it("uses the browser transition when motion is allowed", () => {
    vi.stubGlobal("matchMedia", () => media(false));
    const start = vi.fn((update: () => void) => update());
    Object.assign(document, { startViewTransition: start });
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(start).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("updates synchronously when reduced motion is requested", () => {
    vi.stubGlobal("matchMedia", () => media(true));
    const start = vi.fn();
    Object.assign(document, { startViewTransition: start });
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(start).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("updates synchronously when the API is unavailable", () => {
    vi.stubGlobal("matchMedia", () => media(false));
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(update).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 5: 运行过渡测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/viewTransition.test.ts
```

Expected: FAIL，`viewTransition` 模块不存在。

- [ ] **Step 6: 实现有回退的共享位置过渡**

创建 `apps/web/src/chameleon/viewTransition.ts`：

```ts
import { flushSync } from "react-dom";

type TransitionDocument = Document & {
  startViewTransition?: (update: () => void) => unknown;
};

export function runChameleonViewTransition(update: () => void): void {
  const reduced =
    typeof matchMedia === "function"
    && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = (document as TransitionDocument).startViewTransition;
  if (reduced || typeof start !== "function") {
    update();
    return;
  }
  start.call(document, () => flushSync(update));
}
```

- [ ] **Step 7: 运行 Controller 与过渡测试**

Run:

```bash
cd apps/web
npm test -- src/chameleon/useChameleonController.test.tsx src/chameleon/viewTransition.test.ts
```

Expected: 7 tests PASS。重复 React render 不得取消 ready 的 4000ms timer。

- [ ] **Step 8: 提交**

```bash
git add apps/web/src/chameleon/useChameleonController.ts apps/web/src/chameleon/useChameleonController.test.tsx apps/web/src/chameleon/viewTransition.ts apps/web/src/chameleon/viewTransition.test.ts
git commit -m "feat(web): control Chameleon assistant reveals"
```

---

### Task 4: 添加优化资产、2D Renderer 与三位置 Surface

**Files:**
- Create: `apps/web/src/assets/chameleon-line-logo-approved-v1.png`
- Create: `apps/web/src/chameleon/Chameleon2D.tsx`
- Create: `apps/web/src/chameleon/Chameleon2D.test.tsx`
- Create: `apps/web/src/chameleon/ChameleonSurface.tsx`
- Create: `apps/web/src/chameleon/ChameleonSurface.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `ChameleonVisualState`、`ChameleonVisualSignature`。
- Produces: `Chameleon2D` 与 `ChameleonSurface`；不拥有业务状态。

- [ ] **Step 1: 生成产品 Web 派生 PNG**

从仓库根目录执行：

```bash
ffmpeg -hide_banner -loglevel error -y \
  -i docs/prd/assets/chameleon/chameleon-line-logo-approved-v1.png \
  -vf scale=512:512:flags=lanczos \
  -c:v png -pred mixed -compression_level 9 \
  apps/web/src/assets/chameleon-line-logo-approved-v1.png
```

验证：

```bash
file apps/web/src/assets/chameleon-line-logo-approved-v1.png
test "$(wc -c < apps/web/src/assets/chameleon-line-logo-approved-v1.png | tr -d ' ')" -le 204800
git diff -- docs/prd/assets/chameleon/chameleon-line-logo-approved-v1.png
```

Expected:

- `file` 报告 `PNG image data, 512 x 512`；
- `test` exit 0；
- 品牌源文件没有 diff。

- [ ] **Step 2: 写 Renderer 失败测试**

创建 `apps/web/src/chameleon/Chameleon2D.test.tsx`：

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";
import { Chameleon2D } from "./Chameleon2D";

describe("Chameleon2D", () => {
  const state = deriveChameleonVisualState({ appPhase: "source" });
  const signature = createVisualSignature("lmdj", state);

  it("renders decorative media with explicit visual-state attributes", () => {
    render(<Chameleon2D state={state} signature={signature} />);
    expect(screen.getByTestId("chameleon-2d")).toHaveAttribute(
      "data-phase",
      "idle",
    );
    expect(screen.getByRole("img", { hidden: true })).toHaveAttribute("alt", "");
  });

  it("shows a non-image silhouette fallback when the asset fails", () => {
    render(<Chameleon2D state={state} signature={signature} />);
    fireEvent.error(screen.getByRole("img", { hidden: true }));
    expect(screen.getByTestId("chameleon-fallback")).toBeVisible();
  });
});
```

- [ ] **Step 3: 写 Surface 失败测试**

创建 `apps/web/src/chameleon/ChameleonSurface.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { deriveChameleonVisualState } from "./adapter";
import { createVisualSignature } from "./visualSignature";
import { ChameleonSurface } from "./ChameleonSurface";

describe("ChameleonSurface", () => {
  it("uses a real button for the Gallery upload entrance", async () => {
    const state = deriveChameleonVisualState({ appPhase: "source" });
    const activate = vi.fn();
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("lmdj", state)}
        onActivate={activate}
        onToggle={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", {
        name: "Choose a WAV or MP3 to make a Patch",
      }),
    );
    expect(activate).toHaveBeenCalledTimes(1);
  });

  it("announces error text and exposes an explicit close action", async () => {
    const dock = deriveChameleonVisualState({
      appPhase: "failed",
      errorKey: "submission-1:upload",
      errorLabel: "Upload failed",
    });
    const state = { ...dock, placement: "floating" as const };
    const dismiss = vi.fn();
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("submission-1", state)}
        onActivate={vi.fn()}
        onToggle={vi.fn()}
        onDismiss={dismiss}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed");
    await userEvent.click(screen.getByRole("button", { name: "Close assistant" }));
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  it("keeps processing collapsed in a labeled Dock button", () => {
    const state = deriveChameleonVisualState({
      appPhase: "processing",
      jobState: "separating",
    });
    render(
      <ChameleonSurface
        state={state}
        signature={createVisualSignature("submission-1", state)}
        onActivate={vi.fn()}
        onToggle={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", {
        name: "Chameleon assistant · Separating stems",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("chameleon-dock-state")).toHaveTextContent("S");
  });
});
```

- [ ] **Step 4: 运行测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/Chameleon2D.test.tsx src/chameleon/ChameleonSurface.test.tsx
```

Expected: 2 个 test files 因组件不存在而 FAIL。

- [ ] **Step 5: 实现 Chameleon2D**

创建 `apps/web/src/chameleon/Chameleon2D.tsx`：

```tsx
import { useState, type CSSProperties } from "react";
import chameleonImage from "../assets/chameleon-line-logo-approved-v1.png";
import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";

export function Chameleon2D({
  state,
  signature,
  compact = false,
  sharedTransition = false,
}: {
  state: ChameleonVisualState;
  signature: ChameleonVisualSignature;
  compact?: boolean;
  sharedTransition?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const style = {
    "--chameleon-angle": `${signature.angle}deg`,
    "--chameleon-angle-negative": `${-signature.angle}deg`,
    "--chameleon-offset": `${signature.offset}px`,
    "--chameleon-density": signature.density,
    "--chameleon-step": `${12 * signature.density}px`,
  } as CSSProperties;
  return (
    <span
      className={[
        "chameleon-2d",
        compact ? "chameleon-2d--compact" : "",
        sharedTransition ? "chameleon-2d--shared" : "",
      ].filter(Boolean).join(" ")}
      data-testid="chameleon-2d"
      data-phase={state.phase}
      data-tone={state.tone}
      data-motion={state.motion}
      data-accent={signature.accent}
      style={style}
      aria-hidden="true"
    >
      <span className="chameleon-2d__pattern" />
      {!failed && (
        <img
          src={chameleonImage}
          alt=""
          draggable={false}
          onError={() => setFailed(true)}
        />
      )}
      {failed && (
        <span
          className="chameleon-2d__fallback"
          data-testid="chameleon-fallback"
        >
          CH
        </span>
      )}
    </span>
  );
}
```

- [ ] **Step 6: 实现 ChameleonSurface**

创建 `apps/web/src/chameleon/ChameleonSurface.tsx`：

```tsx
import type {
  ChameleonVisualSignature,
  ChameleonVisualState,
} from "./model";
import { Chameleon2D } from "./Chameleon2D";

const PHASE_GLYPH = {
  idle: "·",
  "drag-ready": "↓",
  uploading: "↑",
  queued: "Q",
  separating: "S",
  extracting: "E",
  patchifying: "P",
  ready: "✓",
  playing: "▶",
  error: "!",
} as const;

export function ChameleonSurface({
  state,
  signature,
  onActivate,
  onToggle,
  onDismiss,
}: {
  state: ChameleonVisualState;
  signature: ChameleonVisualSignature;
  onActivate: () => void;
  onToggle: () => void;
  onDismiss: () => void;
}) {
  if (state.placement === "stage") {
    return (
      <button
        type="button"
        className="chameleon-stage-trigger"
        data-testid="chameleon-stage-trigger"
        aria-label="Choose a WAV or MP3 to make a Patch"
        onClick={onActivate}
      >
        <Chameleon2D
          state={state}
          signature={signature}
          sharedTransition
        />
        <span className="chameleon-stage-trigger__label">
          <strong>
            {state.phase === "drag-ready" ? "DROP WAV OR MP3" : "DROP A TRACK"}
          </strong>
          <span>WAV / MP3 · click or drag</span>
        </span>
      </button>
    );
  }

  const expanded = state.placement === "floating";
  return (
    <div
      className={`chameleon-assistant${expanded ? " chameleon-assistant--expanded" : ""}`}
      data-testid="chameleon-assistant"
      data-phase={state.phase}
    >
      <button
        type="button"
        className="chameleon-dock"
        aria-label={`Chameleon assistant · ${state.label}`}
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <Chameleon2D
          state={state}
          signature={signature}
          compact
          sharedTransition
        />
        <span
          className="chameleon-dock__state"
          data-testid="chameleon-dock-state"
          aria-hidden="true"
        >
          {PHASE_GLYPH[state.phase]}
        </span>
        <span className="chameleon-dock__label">{state.label}</span>
      </button>
      {expanded && (
        <section
          className="chameleon-floating"
          data-testid="chameleon-floating"
          role={state.phase === "error" ? "alert" : "status"}
          aria-live={state.phase === "error" ? "assertive" : "polite"}
        >
          <button
            type="button"
            className="chameleon-floating__close"
            aria-label="Close assistant"
            onClick={onDismiss}
          >
            ×
          </button>
          <Chameleon2D state={state} signature={signature} />
          <strong>{state.label}</strong>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 7: 运行组件测试**

Run:

```bash
cd apps/web
npm test -- src/chameleon/Chameleon2D.test.tsx src/chameleon/ChameleonSurface.test.tsx
```

Expected: 5 tests PASS。

- [ ] **Step 8: 提交**

```bash
git add apps/web/src/assets/chameleon-line-logo-approved-v1.png apps/web/src/chameleon/Chameleon2D.tsx apps/web/src/chameleon/Chameleon2D.test.tsx apps/web/src/chameleon/ChameleonSurface.tsx apps/web/src/chameleon/ChameleonSurface.test.tsx
git commit -m "feat(web): add Chameleon 2D renderer"
```

---

### Task 5: 把首页角色变成主音频上传入口

**Files:**
- Create: `apps/web/src/chameleon/ChameleonUploadStage.tsx`
- Create: `apps/web/src/chameleon/ChameleonUploadStage.test.tsx`
- Create: `apps/web/src/ui/Wordmark.tsx`
- Modify: `apps/web/src/ui/SourcePanel.tsx`
- Modify: `apps/web/src/ui/SourcePanel.test.tsx`

**Interfaces:**
- Consumes: `onUpload(base, file)`，不直接调用 API Client。
- Produces: Gallery Stage 点击、键盘和拖放上传；原 Patch Package DropZone 仍为次入口。

- [ ] **Step 1: 写 Upload Stage 失败测试**

创建 `apps/web/src/chameleon/ChameleonUploadStage.test.tsx`：

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChameleonUploadStage } from "./ChameleonUploadStage";

describe("ChameleonUploadStage", () => {
  it("opens the hidden audio chooser and uploads the selected file", async () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    const input = screen.getByTestId("api-file-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click");

    await userEvent.click(
      screen.getByRole("button", {
        name: "Choose a WAV or MP3 to make a Patch",
      }),
    );
    expect(click).toHaveBeenCalledTimes(1);

    const file = new File(["audio"], "song.wav", { type: "audio/wav" });
    await userEvent.upload(input, file);
    expect(upload).toHaveBeenCalledWith("http://localhost:8000", file);
  });

  it("accepts one dropped WAV and shows drag-ready before drop", () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    const stage = screen.getByTestId("chameleon-upload-stage");
    const file = new File(["audio"], "song.wav", { type: "audio/wav" });

    fireEvent.dragEnter(stage, { dataTransfer: { files: [file] } });
    expect(screen.getByTestId("chameleon-2d")).toHaveAttribute(
      "data-phase",
      "drag-ready",
    );
    fireEvent.drop(stage, { dataTransfer: { files: [file] } });
    expect(upload).toHaveBeenCalledWith("http://localhost:8000", file);
  });

  it("does not upload unsupported dropped files", () => {
    const upload = vi.fn();
    render(<ChameleonUploadStage onUpload={upload} />);
    fireEvent.drop(screen.getByTestId("chameleon-upload-stage"), {
      dataTransfer: {
        files: [new File(["text"], "notes.txt", { type: "text/plain" })],
      },
    });
    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose one WAV or MP3 file",
    );
  });
});
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/chameleon/ChameleonUploadStage.test.tsx
```

Expected: FAIL，组件不存在。

- [ ] **Step 3: 实现 Upload Stage**

创建 `apps/web/src/chameleon/ChameleonUploadStage.tsx`：

```tsx
import { useRef, useState } from "react";
import { deriveChameleonVisualState } from "./adapter";
import { ChameleonSurface } from "./ChameleonSurface";
import { createVisualSignature } from "./visualSignature";

function isSupportedAudio(file: File): boolean {
  return (
    file.type === "audio/wav"
    || file.type === "audio/mpeg"
    || /\.(wav|mp3)$/i.test(file.name)
  );
}

export function ChameleonUploadStage({
  onUpload,
}: {
  onUpload: (base: string, file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined)
      ?? "http://localhost:8000",
  );
  const [dragReady, setDragReady] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const visualState = deriveChameleonVisualState({
    appPhase: "source",
    interaction: dragReady ? "drag-ready" : "none",
  });
  const submit = (file: File) => {
    if (!isSupportedAudio(file)) {
      setLocalError("Choose one WAV or MP3 file");
      return;
    }
    setLocalError(null);
    onUpload(base, file);
  };

  return (
    <section
      className={`chameleon-upload-stage${dragReady ? " chameleon-upload-stage--over" : ""}`}
      data-testid="chameleon-upload-stage"
      onDragEnter={(event) => {
        event.preventDefault();
        dragDepth.current += 1;
        setDragReady(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragReady(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragReady(false);
        const file = event.dataTransfer.files[0];
        if (file) submit(file);
      }}
    >
      <label className="chameleon-upload-stage__api">
        <span>API</span>
        <input
          className="api-base"
          data-testid="api-base-input"
          value={base}
          onChange={(event) => setBase(event.target.value)}
          spellCheck={false}
        />
      </label>
      <input
        ref={inputRef}
        type="file"
        accept=".wav,.mp3,audio/wav,audio/mpeg"
        data-testid="api-file-input"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) submit(file);
        }}
      />
      <ChameleonSurface
        state={visualState}
        signature={createVisualSignature("lmdj:gallery", visualState)}
        onActivate={() => {
          if (inputRef.current) inputRef.current.value = "";
          inputRef.current?.click();
        }}
        onToggle={() => undefined}
        onDismiss={() => undefined}
      />
      {localError && <p role="alert">{localError}</p>}
    </section>
  );
}
```

- [ ] **Step 4: 提取共享 Wordmark**

创建 `apps/web/src/ui/Wordmark.tsx`：

```tsx
export function Wordmark() {
  return (
    <div className="wordmark">
      LMDJ<span className="wordmark-sub">patch view</span>
    </div>
  );
}
```

从 `App.tsx` 删除文件末尾的本地 `Wordmark` 函数，并改为：

```ts
import { Wordmark } from "./Wordmark";
```

- [ ] **Step 5: 将 SourcePanel 改为 Gallery Stage**

把 `SourcePanel.tsx` 改为：

```tsx
import { ChameleonUploadStage } from "../chameleon/ChameleonUploadStage";
import { DropZone } from "./DropZone";
import { Wordmark } from "./Wordmark";

export function SourcePanel({
  onFiles,
  onExample,
  onUpload,
}: {
  onFiles: (files: Map<string, ArrayBuffer>) => void;
  onExample: () => void;
  onUpload: (base: string, file: File) => void;
}) {
  return (
    <section
      className="source-panel gallery-stage"
      data-testid="source-panel"
    >
      <header className="gallery-stage__header">
        <Wordmark />
        <span>AI MUSIC MATERIAL INSTRUMENT · STAGE 01</span>
      </header>
      <div className="gallery-stage__hero">
        <header className="gallery-stage__title">
          <span>Source · Stage 01</span>
          <h1>Feed it<br />a sound</h1>
          <p>One track enters. A playable 16-pad Patch comes back.</p>
        </header>
        <ChameleonUploadStage onUpload={onUpload} />
      </div>
      <div className="source-limits" aria-label="Upload limits">
        <strong>WAV / MP3</strong>
        <span>200 MiB max</span>
        <span>600 秒 max</span>
      </div>
      <div className="source-example">
        <span>Already have a patch package?</span>
        <DropZone onFiles={onFiles} onExample={onExample} />
      </div>
    </section>
  );
}
```

- [ ] **Step 6: 更新 SourcePanel 测试**

在既有 `SourcePanel.test.tsx` 测试中增加：

```ts
expect(
  screen.getByRole("button", {
    name: "Choose a WAV or MP3 to make a Patch",
  }),
).toBeEnabled();
expect(screen.getByText(/AI MUSIC MATERIAL INSTRUMENT/i)).toBeInTheDocument();
expect(screen.getByTestId("api-file-input")).toHaveAttribute(
  "accept",
  ".wav,.mp3,audio/wav,audio/mpeg",
);
```

保留对 Patch Package 示例入口和上传限制的既有断言。

- [ ] **Step 7: 运行聚焦测试**

Run:

```bash
cd apps/web
npm test -- src/chameleon/ChameleonUploadStage.test.tsx src/ui/SourcePanel.test.tsx
```

Expected: 2 个 test files 全部 PASS。

- [ ] **Step 8: 提交**

```bash
git add apps/web/src/chameleon/ChameleonUploadStage.tsx apps/web/src/chameleon/ChameleonUploadStage.test.tsx apps/web/src/ui/Wordmark.tsx apps/web/src/ui/SourcePanel.tsx apps/web/src/ui/SourcePanel.test.tsx apps/web/src/ui/App.tsx
git commit -m "feat(web): make Chameleon the upload entrance"
```

---

### Task 6: 在 WorkbenchShell 预留不遮挡内容的 Assistant 槽位

**Files:**
- Modify: `apps/web/src/ui/WorkbenchShell.tsx`
- Modify: `apps/web/src/ui/WorkbenchShell.test.tsx`

**Interfaces:**
- Consumes: 任意 `assistant: ReactNode`、`assistantExpanded: boolean` 与 `onCanvasInteraction()`。
- Produces: App Bar 内正式 Dock 槽位、`data-assistant-open` 布局状态和工作区交互收起信号；不读取 Chameleon 业务状态。

- [ ] **Step 1: 写 Shell 失败测试**

在 `WorkbenchShell.test.tsx` 增加：

```tsx
it("reserves an assistant slot without changing landmark order", () => {
  const onCanvasInteraction = vi.fn();
  render(
    <WorkbenchShell
      model={model()}
      mode="source"
      onModeChange={() => undefined}
      availableModes={["source", "performance", "export"]}
      appBar={<span>app bar</span>}
      assistant={<button>assistant dock</button>}
      assistantExpanded
      onCanvasInteraction={onCanvasInteraction}
      instrumentCanvas={<span>instrument canvas</span>}
      contextInspector={<span>context inspector</span>}
      statusBar={<span>status bar</span>}
    />,
  );
  expect(screen.getByTestId("app-bar")).toHaveAttribute(
    "data-assistant-open",
    "true",
  );
  expect(screen.getByTestId("assistant-slot")).toContainElement(
    screen.getByRole("button", { name: "assistant dock" }),
  );
  expect(
    screen.getByTestId("app-bar").compareDocumentPosition(
      screen.getByTestId("instrument-canvas"),
    ),
  ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  fireEvent.pointerDown(screen.getByTestId("instrument-canvas"));
  expect(onCanvasInteraction).toHaveBeenCalledTimes(1);
});
```

同时把测试文件的 Testing Library import 改为：

```ts
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/ui/WorkbenchShell.test.tsx
```

Expected: FAIL，props 与 `assistant-slot` 不存在。

- [ ] **Step 3: 扩展 Shell 接口**

在 `WorkbenchShell` props 中增加：

```ts
assistant?: ReactNode;
assistantExpanded?: boolean;
onCanvasInteraction?: () => void;
```

为解构参数提供：

```ts
assistant,
assistantExpanded = false,
onCanvasInteraction,
```

把 App Bar 内容改为：

```tsx
<header
  className="workbench-app-bar"
  data-testid="app-bar"
  data-compact={isPhone ? "true" : "false"}
  data-assistant-open={assistantExpanded ? "true" : "false"}
  inert={modalOpen}
>
  <div className="workbench-app-bar__main">{appBar}</div>
  {assistant && (
    <div
      className="workbench-assistant-slot"
      data-testid="assistant-slot"
    >
      {assistant}
    </div>
  )}
  <button
    ref={toggleRef}
    type="button"
    className="workbench-inspector-toggle"
    data-testid="inspector-toggle"
    aria-controls="workbench-context-inspector"
    aria-expanded={inspectorVisible}
    onClick={() => setInspectorOpen((open) => !open)}
  >
    <span aria-hidden="true">◧</span>
    <span>Inspector</span>
  </button>
</header>
```

在 instrument canvas 的 `<main>` 上增加：

```tsx
onPointerDownCapture={onCanvasInteraction}
```

这让真实 Pad、Pattern 或 Canvas 操作可以收起已展开角色，不需要 Chameleon
组件知道工作台内部结构。Inspector modal 自己的 focus/inert 规则保持不变。

不要把 Assistant 放入 `workbench-shell__content`，避免与 Inspector 的 modal/inert
规则耦合。

- [ ] **Step 4: 更新既有 Shell 调用测试**

所有 `WorkbenchShell` 测试调用可以省略可选新 props。确认 Inspector 打开时
App Bar（含 Assistant）继续整体获得 `inert`，不建立第二套 focus trap。

- [ ] **Step 5: 运行 Shell 测试**

Run:

```bash
cd apps/web
npm test -- src/ui/WorkbenchShell.test.tsx
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add apps/web/src/ui/WorkbenchShell.tsx apps/web/src/ui/WorkbenchShell.test.tsx
git commit -m "feat(web): reserve Chameleon assistant dock"
```

---

### Task 7: 将真实 App 状态接入 Gallery、Dock 与 Floating

**Files:**
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`

**Interfaces:**
- Consumes: Tasks 1–6 的 Adapter、Signature、Playback、Controller、Surface 和 Shell slot。
- Produces: 真实端到端 Chameleon UI；不修改 API 或 Patch contract。

- [ ] **Step 1: 写 App 状态集成失败测试**

在 `App.test.tsx` 增加：

```tsx
it("starts on the Gallery Stage with the Chameleon upload entrance", () => {
  renderApp(golden);
  expect(
    screen.getByRole("button", {
      name: "Choose a WAV or MP3 to make a Patch",
    }),
  ).toBeEnabled();
  expect(screen.queryByTestId("creator-tools")).not.toBeInTheDocument();
});

it("keeps ordinary processing collapsed in the truthful Dock", async () => {
  let releasePoll: ((status: JobStatus) => void) | undefined;
  const pollJob = vi.fn<ApiClient["pollJob"]>(
    async (_base, _jobId, onState) => {
      const separating = apiJob("job123", "separating");
      onState?.(separating);
      return await new Promise<JobStatus>((resolve) => {
        releasePoll = resolve;
      });
    },
  );
  renderAppWithApi(fakeApi({ pollJob }));
  await submitViaApi();
  const dock = await screen.findByRole("button", {
    name: "Chameleon assistant · Separating stems",
  });
  expect(dock).toHaveAttribute("aria-expanded", "false");
  act(() => releasePoll?.(apiJob("job123", "cancelled")));
});

it("auto-reveals a loaded Patch once and lets the user dismiss it", async () => {
  renderApp(golden);
  await userEvent.click(screen.getByRole("button", { name: /示例/i }));
  const dock = await screen.findByRole("button", {
    name: "Chameleon assistant · Patch ready",
  });
  expect(dock).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(screen.getByRole("button", { name: "Close assistant" }));
  expect(dock).toHaveAttribute("aria-expanded", "false");
});

it("maps a real active Pad source to playing state", async () => {
  const engine = new AudioEngine(new FakeAudioContext());
  render(
    <App
      engine={engine}
      decode={fakeDecode}
      fetchExample={exampleFiles(golden)}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /示例/i }));
  await screen.findByTestId("pad-matrix");
  await userEvent.click(screen.getByTestId("pad-3"));
  expect(
    screen.getByRole("button", {
      name: "Chameleon assistant · Playing bass",
    }),
  ).toBeInTheDocument();
});
```

在 API 测试的 cleanup 中确保悬而未决的 Promise 被终止，避免 Vitest 残留异步更新。
同时更新既有测试基线：

```ts
async function submitViaApi() {
  const file = new File(
    [new Uint8Array([1, 2, 3])],
    "song.wav",
    { type: "audio/wav" },
  );
  await userEvent.upload(screen.getByTestId("api-file-input"), file);
}
```

删除 helper 中对旧“传歌”按钮的点击。把启动页测试中的
`workbench-shell` 断言改为
`expect(screen.getByTestId("source-panel")).toHaveClass("gallery-stage")`，
把 `api-panel` 断言改为 `chameleon-upload-stage`；Patch 加载后的 Workbench
断言保持不变。

- [ ] **Step 2: 运行聚焦 App 测试并确认失败**

Run:

```bash
cd apps/web
npm test -- src/ui/App.test.tsx
```

Expected: 新增测试因 Gallery、Dock 和状态接入尚不存在而 FAIL。

- [ ] **Step 3: 添加 App imports 与真实 Engine 订阅**

在 `App.tsx` 增加：

```ts
import { deriveChameleonVisualState } from "../chameleon/adapter";
import { ChameleonSurface } from "../chameleon/ChameleonSurface";
import { activePlaybackRole } from "../chameleon/playback";
import { useChameleonController } from "../chameleon/useChameleonController";
import { createVisualSignature } from "../chameleon/visualSignature";
import { runChameleonViewTransition } from "../chameleon/viewTransition";
import { useEngineTick } from "./useEngine";
```

在 `App` 状态 hooks 后调用：

```ts
useEngineTick(engine);
```

这是为了消费 AudioEngine 的真实 source start/end 通知，不使用定时猜测 one-shot
时长。

在 `App` 内、`state` hook 后增加：

```ts
const transitionTo = useCallback((next: AppState) => {
  runChameleonViewTransition(() => setState(next));
}, []);
```

把三条 stage/dock 边界改为调用 `transitionTo`：

```ts
transitionTo({
  phase: "loaded",
  bundle,
  source,
  exportState: { kind: "idle" },
});
```

```ts
transitionTo({ phase: "source", issues: null, issueTitle: null });
```

```ts
transitionTo({
  phase: "processing",
  file,
  base: root,
  submissionId: submission.submissionId,
  jobState: "preflight",
  lastNonterminalStage: "preflight",
});
```

对应 `enterLoaded`、`backToUpload` 和 `submitUpload` callbacks 的 dependency
arrays 加入 `transitionTo`。processing 到 failed 等同一 Dock 位置的变化继续用
普通 `setState`。

- [ ] **Step 4: 在所有条件 return 前推导唯一 Visual State**

在键盘 `useEffect` 后、首个 `if (state.phase === "source")` 前加入：

```ts
const activeJob =
  state.phase === "processing"
    ? trackedJobs.find(
        (job) =>
          job.submission.submissionId === state.submissionId,
      )
    : undefined;
const patchId =
  state.phase === "loaded" ? state.bundle.patch.patch_id : null;
const playbackRole =
  state.phase === "loaded"
    ? activePlaybackRole(
        state.bundle.patch,
        engine.activeElementIds(),
      )
    : null;
const chameleonVisual = deriveChameleonVisualState({
  appPhase: state.phase,
  jobState: state.phase === "processing" ? state.jobState : null,
  queuePosition: activeJob?.status?.queue_position ?? null,
  patchId,
  errorKey:
    state.phase === "failed"
      ? `${state.submissionId}:${state.failedAt}`
      : null,
  errorLabel:
    state.phase === "failed" ? state.issueTitle : null,
  isPlaying: state.phase === "loaded" && engine.active,
  playbackRole,
});
const chameleon = useChameleonController(chameleonVisual);
const chameleonSeed =
  state.phase === "loaded"
    ? state.bundle.patch.patch_id
    : state.phase === "processing" || state.phase === "failed"
      ? state.submissionId
      : "lmdj:gallery";
const assistant = state.phase === "source"
  ? undefined
  : (
      <ChameleonSurface
        state={chameleon.visualState}
        signature={createVisualSignature(
          chameleonSeed,
          chameleon.visualState,
        )}
        onActivate={() => undefined}
        onToggle={chameleon.toggle}
        onDismiss={chameleon.dismiss}
      />
    );
```

Hooks 必须保持无条件调用，不能移入某个 `phase` 分支。

- [ ] **Step 5: 将 source 分支改为独立 Gallery 页面**

用以下结构替换 source 分支的 `CreatorStateShell`：

```tsx
if (state.phase === "source") {
  return (
    <AppFrame>
      <SourcePanel
        onFiles={(files) =>
          void handleFiles(files, { kind: "local" })
        }
        onExample={() =>
          void fetchExample().then(
            (files) => handleFiles(files, { kind: "example" }),
            failPatch,
          )
        }
        onUpload={(base, file) => void handleUpload(base, file)}
      />
      <section className="gallery-stage__jobs">
        <JobQueuePanel
          jobs={trackedJobs}
          capacity={queueCapacity}
          onOpenCompleted={(job) => void openCompletedJob(job)}
        />
      </section>
      {state.issues && (
        <ErrorPanel
          title={
            state.issueTitle
              ?? "patch.json 未通过 lmdj.patch.v1 校验"
          }
          issues={state.issues}
        />
      )}
    </AppFrame>
  );
}
```

Gallery 不渲染 Creator Tool Rail 或 Inspector；上传被接受后才进入工作台。

- [ ] **Step 6: 为 processing 与 failed 注入 Assistant**

扩展 `CreatorStateShell` props：

```ts
assistant?: ReactNode;
assistantExpanded?: boolean;
onCanvasInteraction?: () => void;
```

同时把 `assistant`、`assistantExpanded`、`onCanvasInteraction` 加入
`CreatorStateShell` 的函数参数解构，并将 props 传给 `WorkbenchShell`：

```tsx
assistant={assistant}
assistantExpanded={assistantExpanded}
onCanvasInteraction={onCanvasInteraction}
```

在 processing 与 failed 两个调用点分别加入：

```tsx
assistant={assistant}
assistantExpanded={chameleon.expanded}
onCanvasInteraction={chameleon.dismiss}
```

- [ ] **Step 7: 为 loaded Workbench 注入 Assistant**

在 loaded 分支的 `WorkbenchShell` 调用加入：

```tsx
assistant={assistant}
assistantExpanded={chameleon.expanded}
onCanvasInteraction={chameleon.dismiss}
```

保留现有 Wordmark、项目元数据、Eject、Inspector Toggle 和 Status Bar。

把 `AppFrame` 的版本展签内容改为：

```tsx
LMDJ · {PRODUCT_VERSION}
```

它仍然只包含产品 SemVer 或 `dev`，不得拼接 revision。

- [ ] **Step 8: 运行 App 与相关组件测试**

Run:

```bash
cd apps/web
npm test -- src/ui/App.test.tsx src/ui/WorkbenchShell.test.tsx src/chameleon
```

Expected: App、Shell 和全部 Chameleon tests PASS；Console 不出现 `act(...)`
警告。

- [ ] **Step 9: 提交**

```bash
git add apps/web/src/ui/App.tsx apps/web/src/ui/App.test.tsx
git commit -m "feat(web): connect Chameleon to product state"
```

---

### Task 8: 实施 Exhibition Workbench CSS 与无遮挡响应式布局

**Files:**
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Consumes: Tasks 4–7 的 class、data attribute 和 Shell assistant slot。
- Produces: Gallery Stage、2D pattern、Dock、Floating、移动状态层和 Reduced Motion。

- [ ] **Step 1: 先运行现有响应式测试作为基线**

Run:

```bash
cd apps/web
npm run test:e2e -- e2e/workbench-responsive.spec.ts
```

Expected: 既有 responsive suite PASS。若基线失败，先记录并修复现有失败，不把它
归因给 Chameleon CSS。

- [ ] **Step 2: 统一页面表面和版本展签**

在 `:root` 把：

```css
color-scheme: dark;
```

改为：

```css
color-scheme: light;
```

把 `body` 背景改为：

```css
body {
  margin: 0;
  min-height: 100vh;
  background:
    linear-gradient(90deg, transparent 0 23px, rgba(17, 17, 15, .08) 24px 25px, transparent 26px),
    var(--paper);
  background-size: 96px 100%;
  color: var(--ink);
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
```

将 `.app-version` 改为单色展签：

```css
.app-version {
  position: fixed;
  right: max(12px, env(safe-area-inset-right));
  bottom: max(10px, env(safe-area-inset-bottom));
  z-index: 40;
  padding: 3px 0;
  border: 0;
  border-top: 1px solid currentColor;
  background: transparent;
  color: color-mix(in srgb, var(--ink) 58%, transparent);
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .08em;
  line-height: 1.2;
  pointer-events: none;
}
```

- [ ] **Step 3: 添加 Gallery Stage CSS**

在 `theme.css` 末尾加入：

```css
.gallery-stage {
  position: relative;
  min-height: min(880px, calc(100vh - 48px));
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  gap: 18px;
  overflow: hidden;
  border: 3px solid var(--ink);
  background:
    linear-gradient(
      90deg,
      transparent calc(100% - 1px),
      rgba(17, 17, 15, .08) calc(100% - 1px)
    ) 0 0 / 8.333333% 100%,
    var(--paper);
  color: var(--ink);
  box-shadow: 10px 10px 0 var(--ink);
}
.gallery-stage::before {
  content: "";
  position: absolute;
  inset: 54px 0 auto;
  height: 3px;
  background: var(--ink);
  pointer-events: none;
}
.gallery-stage__header {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 14px;
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .12em;
}
.gallery-stage__hero {
  min-height: 520px;
  display: grid;
  grid-template-columns: minmax(220px, .75fr) minmax(360px, 1.25fr);
  align-items: center;
  gap: 24px;
  padding: 28px clamp(18px, 4vw, 64px);
}
.gallery-stage__title {
  position: relative;
  z-index: 2;
}
.gallery-stage__title > span,
.gallery-stage__title p {
  font-family: "IBM Plex Mono", monospace;
  font-size: 10px;
  font-weight: 800;
}
.gallery-stage__title h1 {
  margin: 8px 0 14px;
  font-family: "Chakra Petch", sans-serif;
  font-size: clamp(64px, 9vw, 148px);
  font-weight: 700;
  line-height: .72;
  letter-spacing: -.08em;
  text-transform: uppercase;
}
.gallery-stage__title p {
  max-width: 34ch;
  margin: 0;
}
.gallery-stage > .source-limits,
.gallery-stage > .source-example {
  margin-inline: clamp(18px, 4vw, 64px);
}
.gallery-stage > .source-example {
  margin-bottom: 28px;
}
.gallery-stage__jobs {
  margin-top: 28px;
}
```

- [ ] **Step 4: 添加 2D 图形、上传区域和状态纹理**

继续加入：

```css
.chameleon-upload-stage {
  position: relative;
  min-height: 480px;
  display: grid;
  place-items: center;
  isolation: isolate;
}
.chameleon-upload-stage::before,
.chameleon-upload-stage::after {
  content: "";
  position: absolute;
  z-index: -2;
  border: 3px solid var(--ink);
}
.chameleon-upload-stage::before {
  width: min(46vw, 520px);
  aspect-ratio: 1;
  background: var(--lead);
  transform: rotate(-7deg);
}
.chameleon-upload-stage::after {
  width: min(34vw, 390px);
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--action);
  transform: translate(18%, 5%);
}
.chameleon-upload-stage--over::before {
  background: var(--harmony);
}
.chameleon-upload-stage__api {
  position: absolute;
  z-index: 4;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
  font-weight: 800;
}
.chameleon-upload-stage__api .api-base {
  width: min(240px, 42vw);
  border: 1px solid var(--ink);
  border-radius: 0;
  background: color-mix(in srgb, var(--paper) 92%, transparent);
  color: var(--ink);
  padding: 5px 7px;
}
.source-panel .chameleon-stage-trigger {
  position: relative;
  z-index: 2;
  width: min(100%, 520px);
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  box-shadow: none;
}
.source-panel .chameleon-stage-trigger:hover {
  border-color: transparent;
  background: transparent;
}
.chameleon-stage-trigger__label {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: -26px;
  padding: 7px 10px;
  border: 2px solid var(--ink);
  background: var(--paper);
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
}
.chameleon-stage-trigger__label strong {
  font-size: 11px;
  letter-spacing: .12em;
}
.chameleon-2d {
  --chameleon-accent: var(--ink);
  position: relative;
  width: clamp(200px, 38vw, 480px);
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  transform: translateX(var(--chameleon-offset));
}
.chameleon-2d--shared {
  view-transition-name: lmdj-chameleon;
  contain: layout;
}
::view-transition-old(lmdj-chameleon),
::view-transition-new(lmdj-chameleon) {
  animation-duration: 360ms;
  animation-timing-function: cubic-bezier(.2, .8, .2, 1);
}
.chameleon-2d[data-accent="drums"] { --chameleon-accent: var(--drums); }
.chameleon-2d[data-accent="bass"] { --chameleon-accent: var(--bass); }
.chameleon-2d[data-accent="harmony"] { --chameleon-accent: var(--harmony); }
.chameleon-2d[data-accent="lead"] { --chameleon-accent: var(--lead); }
.chameleon-2d[data-accent="loop"] { --chameleon-accent: var(--loop); }
.chameleon-2d[data-accent="action"],
.chameleon-2d[data-accent="mixed"] { --chameleon-accent: var(--action); }
.chameleon-2d[data-accent="success"] { --chameleon-accent: var(--harmony); }
.chameleon-2d[data-accent="danger"] { --chameleon-accent: var(--red); }
.chameleon-2d__pattern {
  position: absolute;
  inset: 12%;
  z-index: -1;
  border: 2px solid var(--ink);
  background:
    repeating-linear-gradient(
      var(--chameleon-angle),
      var(--chameleon-accent) 0 12px,
      transparent 12px var(--chameleon-step)
    );
  transform: rotate(var(--chameleon-angle-negative));
}
.chameleon-2d[data-phase="separating"] .chameleon-2d__pattern {
  background:
    repeating-linear-gradient(
      90deg,
      var(--drums) 0 18px,
      var(--bass) 18px 36px,
      var(--harmony) 36px 54px,
      var(--lead) 54px 72px
    );
}
.chameleon-2d[data-phase="extracting"] .chameleon-2d__pattern {
  background:
    radial-gradient(circle, var(--action) 0 5px, transparent 6px)
    0 0 / var(--chameleon-step) var(--chameleon-step);
}
.chameleon-2d[data-phase="patchifying"] .chameleon-2d__pattern {
  background:
    linear-gradient(var(--ink) 2px, transparent 2px)
    0 0 / var(--chameleon-step) var(--chameleon-step),
    linear-gradient(90deg, var(--ink) 2px, var(--lead) 2px)
    0 0 / var(--chameleon-step) var(--chameleon-step);
}
.chameleon-2d[data-phase="ready"] .chameleon-2d__pattern {
  background: var(--harmony);
}
.chameleon-2d[data-phase="error"] .chameleon-2d__pattern {
  background:
    repeating-linear-gradient(
      -45deg,
      var(--red) 0 12px,
      var(--paper) 12px 24px
    );
}
.chameleon-2d img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
  user-select: none;
}
.chameleon-2d__fallback {
  width: 72%;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border: 3px solid var(--ink);
  border-radius: 50%;
  background: var(--paper);
  font-family: "Chakra Petch", sans-serif;
  font-size: clamp(42px, 8vw, 92px);
  font-weight: 800;
}
.chameleon-2d[data-motion="ambient"] {
  animation: chameleon-breathe 5s ease-in-out infinite;
}
.chameleon-2d[data-motion="processing"] {
  animation: chameleon-process 1.8s ease-in-out infinite;
}
.chameleon-2d[data-motion="celebrate"] {
  animation: chameleon-celebrate 700ms ease-out both;
}
.chameleon-2d[data-motion="recoil"] {
  animation: chameleon-recoil 360ms ease-out both;
}
@keyframes chameleon-breathe {
  0%, 100% { transform: translateX(var(--chameleon-offset)) scale(1); }
  50% { transform: translateX(var(--chameleon-offset)) scale(1.018); }
}
@keyframes chameleon-process {
  0%, 100% { transform: translateX(var(--chameleon-offset)) rotate(-1deg); }
  50% { transform: translateX(var(--chameleon-offset)) rotate(1deg); }
}
@keyframes chameleon-celebrate {
  0% { transform: translateX(var(--chameleon-offset)) scale(.92); }
  65% { transform: translateX(var(--chameleon-offset)) scale(1.04); }
  100% { transform: translateX(var(--chameleon-offset)) scale(1); }
}
@keyframes chameleon-recoil {
  0% { transform: translateX(var(--chameleon-offset)); }
  45% { transform: translateX(calc(var(--chameleon-offset) - 12px)); }
  100% { transform: translateX(var(--chameleon-offset)); }
}
```

- [ ] **Step 5: 添加 Dock、Floating 和 Shell clearance**

继续加入：

```css
.workbench-app-bar {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
}
.workbench-app-bar__main {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.workbench-assistant-slot {
  position: relative;
  z-index: 42;
  align-self: center;
}
.workbench-app-bar[data-assistant-open="true"] {
  padding-bottom: 188px;
}
.chameleon-assistant {
  position: relative;
}
.chameleon-dock {
  position: relative;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  overflow: visible;
  border: 2px solid var(--ink);
  border-radius: 50%;
  padding: 0;
  background: var(--paper);
  color: var(--ink);
  box-shadow: 3px 3px 0 var(--ink);
}
.chameleon-dock .chameleon-2d {
  width: 42px;
}
.chameleon-dock .chameleon-2d__pattern {
  display: none;
}
.chameleon-dock__state {
  position: absolute;
  right: -3px;
  bottom: -3px;
  min-width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border: 2px solid var(--ink);
  border-radius: 50%;
  background: var(--paper);
  color: var(--ink);
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
  font-weight: 900;
}
.chameleon-dock__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.chameleon-floating {
  position: absolute;
  top: 56px;
  right: 0;
  width: 180px;
  min-height: 170px;
  display: grid;
  place-items: center;
  padding: 8px 8px 24px;
  border: 0;
  background: transparent;
  color: var(--ink);
}
.chameleon-floating .chameleon-2d {
  width: 150px;
}
.chameleon-floating > strong {
  padding: 4px 6px;
  border-top: 2px solid var(--ink);
  background: var(--paper);
  font-family: "IBM Plex Mono", monospace;
  font-size: 9px;
  text-transform: uppercase;
}
.chameleon-floating__close {
  position: absolute;
  z-index: 3;
  top: 0;
  right: 0;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 2px solid var(--ink);
  border-radius: 50%;
  padding: 0;
  background: var(--paper);
  color: var(--ink);
  font-weight: 900;
}
```

Header 的 `padding-bottom` 为展开内容预留真实布局空间，因此 Floating 的 bounding
box 必须位于 `workbench-shell__content` 上方，不能靠高 z-index 覆盖工作区。

- [ ] **Step 6: 添加 768px 与 390px 响应式规则**

继续加入：

```css
@media (max-width: 767px) {
  .gallery-stage {
    min-height: calc(100vh - 24px);
    box-shadow: 5px 5px 0 var(--ink);
    background:
      linear-gradient(
        90deg,
        transparent calc(100% - 1px),
        rgba(17, 17, 15, .08) calc(100% - 1px)
      ) 0 0 / 25% 100%,
      var(--paper);
  }
  .gallery-stage__header {
    align-items: flex-start;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
  }
  .gallery-stage__hero {
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    padding: 20px 14px;
  }
  .gallery-stage__title h1 {
    font-size: clamp(54px, 20vw, 88px);
  }
  .chameleon-upload-stage {
    min-height: 330px;
  }
  .chameleon-upload-stage::before {
    width: min(76vw, 320px);
  }
  .chameleon-upload-stage::after {
    width: min(60vw, 250px);
  }
  .chameleon-upload-stage__api {
    position: static;
    width: 100%;
    justify-content: flex-end;
  }
  .chameleon-upload-stage__api .api-base {
    width: min(220px, 64vw);
  }
  .chameleon-2d {
    width: clamp(200px, 70vw, 280px);
  }
  .workbench-app-bar[data-assistant-open="true"] {
    padding-bottom: 156px;
  }
  .chameleon-dock {
    width: 44px;
    height: 44px;
  }
  .chameleon-floating {
    position: absolute;
    top: 50px;
    right: -46px;
    width: min(280px, calc(100vw - 40px));
    min-height: 144px;
    grid-template-columns: 112px minmax(0, 1fr);
    padding: 8px;
  }
  .chameleon-floating .chameleon-2d {
    width: 112px;
  }
}
```

- [ ] **Step 7: 扩展 Reduced Motion**

在既有 `@media (prefers-reduced-motion: reduce)` 中加入：

```css
.chameleon-2d,
.chameleon-2d__pattern,
.chameleon-stage-trigger,
.chameleon-floating {
  animation: none !important;
  transition: none !important;
  transform: none !important;
}
```

状态文字、状态 `data-*` 和颜色仍保留。

- [ ] **Step 8: 运行构建和既有响应式 suite**

Run:

```bash
cd apps/web
npm run build
npm run test:e2e -- e2e/workbench-responsive.spec.ts
```

Expected: TypeScript/Vite build PASS；既有 responsive suite PASS。

- [ ] **Step 9: 提交**

```bash
git add apps/web/src/ui/theme.css
git commit -m "feat(web): style Chameleon exhibition workbench"
```

---

### Task 9: 增加浏览器验收、完成全量验证并更新实现状态

**Files:**
- Create: `apps/web/e2e/chameleon-exhibition.spec.ts`
- Modify: `docs/superpowers/specs/2026-07-26-chameleon-exhibition-workbench-design.md`

**Interfaces:**
- Consumes: 完整 2D 实现。
- Produces: 关键宽度无遮挡证据、Reduced Motion 证据、最终构建证据和准确文档状态。

- [ ] **Step 1: 写 1440 / 768 / 390px E2E**

创建 `apps/web/e2e/chameleon-exhibition.spec.ts`：

```ts
import { expect, test, type Locator, type Page } from "@playwright/test";

type Box = { x: number; y: number; width: number; height: number };

async function box(locator: Locator): Promise<Box> {
  const value = await locator.boundingBox();
  expect(value).not.toBeNull();
  return value!;
}

function overlaps(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width
    && a.x + a.width > b.x
    && a.y < b.y + b.height
    && a.y + a.height > b.y
  );
}

async function openReadyPatch(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: /加载示例 patch/i }).click();
  await expect(page.getByTestId("pad-matrix")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Chameleon assistant · Patch ready",
    }),
  ).toHaveAttribute("aria-expanded", "true");
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`${viewport.width}px keeps Chameleon out of Creator controls`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await openReadyPatch(page);

    const floating = await box(page.getByTestId("chameleon-floating"));
    const content = await box(page.getByTestId("workbench-content"));
    const matrix = await box(page.getByTestId("pad-matrix"));
    const status = await box(page.getByTestId("status-bar"));

    expect(overlaps(floating, content)).toBe(false);
    expect(overlaps(floating, matrix)).toBe(false);
    expect(overlaps(floating, status)).toBe(false);
  });
}

test("Gallery keeps the main character and version edition mark separate", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const character = await box(page.getByTestId("chameleon-stage-trigger"));
  const version = await box(page.getByTestId("app-version"));
  expect(overlaps(character, version)).toBe(false);
  await expect(
    page.getByRole("button", {
      name: "Choose a WAV or MP3 to make a Patch",
    }),
  ).toBeVisible();
});

test("Reduced Motion removes Chameleon animation without hiding state", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const character = page.getByTestId("chameleon-2d");
  await expect(character).toHaveAttribute("data-phase", "idle");
  const style = await character.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      animationName: computed.animationName,
      transitionDuration: computed.transitionDuration,
    };
  });
  expect(style.animationName).toBe("none");
  expect(style.transitionDuration).toBe("0s");
});
```

- [ ] **Step 2: 运行新 E2E 并修复真实布局问题**

Run:

```bash
cd apps/web
npm run test:e2e -- e2e/chameleon-exhibition.spec.ts
```

Expected: 5 tests PASS。若 bounding box 重叠，只调整 Gallery、Assistant slot 和
Floating 的布局尺寸；不得通过隐藏 Inspector、Pad、Export 或断言规避失败。

- [ ] **Step 3: 运行完整 Web 验证**

Run:

```bash
cd apps/web
npm test
npm run check-contract
npm run build
npm run test:e2e
```

Expected:

- Vitest 全部 PASS；
- `check-contract` PASS，Schema copy 与生成 types 无 drift；
- TypeScript 与 Vite build PASS；
- 全部 Playwright tests PASS。

- [ ] **Step 4: 执行静态边界检查**

从仓库根目录运行：

```bash
git diff --check
rg -n "three|@react-three|drei|\\.glb" apps/web/package.json apps/web/src
rg -n "materials\\.json|lanes\\.json|chart\\.mid" apps/web/src/chameleon
test "$(wc -c < apps/web/src/assets/chameleon-line-logo-approved-v1.png | tr -d ' ')" -le 204800
```

Expected:

- `git diff --check` exit 0；
- 3D dependency 搜索无新结果；
- Chameleon 内部数据搜索无结果；
- 运行时 PNG 大小检查 exit 0。

- [ ] **Step 5: 更新设计文档实现状态**

将设计文档头部：

```markdown
- 状态：用户已逐节确认；尚未实施
```

改为：

```markdown
- 状态：用户已逐节确认；2D 初版已实现
```

在“已落地”增加：

```markdown
- 首页 Gallery Stage、Chameleon 音频上传入口、工作台 Assistant Dock、
  真实 Visual State、单次 ready/error 展开、响应式回退和 Reduced Motion
  已通过 Web 单元测试、构建与浏览器验收。
```

在“尚未实施”只保留：

```markdown
- 用户未来提供的正式 SVG 局部动画；
- 独立评审后的 3D 模型、Rig、动画、GLB 和 WebGL Runtime。
```

不得把 SVG 或 3D 标记为部分实现。

- [ ] **Step 6: 再次运行文档和最终状态检查**

Run:

```bash
git diff --check
git status --short
```

Expected: 只出现本 Task 的 E2E 与设计状态修改；没有测试产物、截图、Trace、
`node_modules` 或无关文件。

- [ ] **Step 7: 提交**

```bash
git add apps/web/e2e/chameleon-exhibition.spec.ts docs/superpowers/specs/2026-07-26-chameleon-exhibition-workbench-design.md
git commit -m "test(web): verify Chameleon exhibition workflow"
```

- [ ] **Step 8: 检查最终提交链与工作区**

Run:

```bash
git log --oneline --decorate -10
git show --stat --oneline HEAD
git status --short --branch
```

Expected:

- Tasks 1–9 各自形成可审查的 Conventional Commit；
- 最终工作区干净；
- 未执行 push、PR、merge 或 deploy。

---

## Execution Notes for Claude Opus 5

1. 开始前完整阅读
   `docs/superpowers/specs/2026-07-26-chameleon-exhibition-workbench-design.md`
   和本计划，不从旧 brainstorm HTML 或浏览器截图推断未记录需求。
2. 严格按 Task 顺序执行。每个 Task 先运行指定失败测试，再实现，再运行聚焦测试，
   最后创建自己的 commit。
3. 当前 PNG 是有意的 2D 回退，不要重新生成角色、描摹新 SVG 或用 CSS 透视伪造
   3D。
4. 如果现有 SVG 与 PNG 看起来相同，也不能把
   `chameleon-line-logo-master-v1.svg` 自动升级为用户未来的正式 SVG。
5. 如果 App 状态或现有测试与计划中的代码位置发生漂移，保持本文接口和产品边界，
   先用 live evidence 更新最小调用点，不重写 Creator Core。
6. 任何需要修改 API、Worker、`lmdj.patch.v1`、Audio Material contract 或引入
   3D dependency 的发现都超出本计划，停止该扩展并单独提出设计问题。
