# LMDJ Web Patch View 原型设计

日期：2026-07-07
状态：已评审设计（brainstorming 流程产出）
落点：`apps/web/`

## 定位

`patch.json`（`lmdj.patch.v1`）的第一个消费者：一个纯客户端的 **8-pad Focus View 工作台原型**，验证"patch.json 能驱动一个可玩、可看、可静音编辑的 sampler 界面"。

明确不是：webdemo0702 素材（`docs/lmdj-web-prototype-spec.md`）描述的 "prompt → pipeline → Z X N M 下落音符引导演奏" 三步 demo。该素材保留为参考；其"前端直读 `lanes.json`/`chart.mid`"的做法与 2026-07-07 决策（truth 三段式）冲突，本原型不采用。

## 已确认的设计决策

| 决策点 | 结论 |
|--------|------|
| 定位 | Patch View 工作台（非生成流程、非引导演奏） |
| patch 加载 | 拖入 package 目录（webkitdirectory）+ 内置示例 patch 一键加载 |
| 交互深度 | pattern 循环回放 + pad 点击触发 + pad 静音（右键/长按 toggle 全组） |
| 技术栈 | Vite + React + TypeScript，裸 Web Audio API（无 Tone.js、无 Next.js——纯客户端应用，SSR 无用武之地且与 `apps/api/` 边界冲突） |
| 视觉 | 黑底 + 终端绿 ASCII 气质（沿 `references/demos/ascii-matrix-camera/`），全等宽字体 |
| 架构 | 方案 A：三层分离（patch 契约层 / 音频引擎层 / React UI 层） |

## 架构

```text
apps/web/src/
  patch/    契约层：types.ts（由 lmdj.patch.v1 schema codegen）
            loader.ts（目录 → 校验 → 解码 → PatchBundle）
            schema/lmdj.patch.v1.schema.json（构建期从 packages/core-models 拷贝，带"不得手改"注释头）
  engine/   AudioEngine：裸 WebAudio，不依赖 React
  ui/       React 组件 + useEngine hook
```

### 数据流

```text
拖入目录 / 点击内置示例
  → loader：读 patch.json → ajv 按 lmdj.patch.v1 校验
  → 按 elements[].source_path 找 wav → decodeAudioData → AudioBuffer
  → PatchBundle { patch, buffers: Map<element_id, AudioBuffer>, warnings[] }
  → AudioEngine.load(bundle)
  → UI 渲染
```

### 契约纯度（硬约束）

- 前端**只读 `patch.json`**，拖入目录中的 `lanes.json`/`chart.mid`/`report.json` 一律无视——truth 三段式决策的第一次消费方落地。
- schema 单一真相源在 `packages/core-models/`；web 侧提供 `npm run sync-contract` 脚本：从 core-models 拷贝 schema 文件并用 `json-schema-to-typescript` 重新生成 `types.ts`——契约变更时手动执行，拷贝与生成物均带"不得手改"注释头并提交入库。
- reserved action pads（`scene_fill`/`scene_drop`/`mute_group`/`ai_variation`）渲染为禁用态、点击 no-op——契约前向兼容规则的第一次消费方验证。

## AudioEngine 语义

- **调度**：lookahead 模式——`setInterval` ~25ms tick，向前预排 ~120ms；`stepDuration = 60 / bpm / 4`；播放头按 `AudioContext.currentTime` 推算；pattern 到 `length_steps` 末尾无缝回卷。
- **发声**：note → `AudioBufferSourceNode`（one-shot 播完整 buffer，与"v1 无 duration"契约一致）→ 每 element 一条 `GainNode`（静音用）→ 主输出。
- **pad 触发**：点击立即播 primary `element_id` 的 buffer；`trigger_group` 同样只播 primary（组员展开为后续增强）。
- **pad 静音**：toggle 该 pad `behavior.element_ids` 全组的 GainNode（Drums = kick+snare+hat 整组）；已排程 note 照排、靠 gain 消声。
- **velocity**：读取但不映射增益（契约注明 v1 恒 100）。

## UI 布局

```text
┌──────────────────────────────────────────────────┐
│ TRANSPORT  ▶/■  BPM 89.1  patch: testsong-6d0b   │
├────────────────────────┬─────────────────────────┤
│    PAD GRID (2×4)      │   INSPECTOR             │
│  上排 A S D F           │   elements / status /   │
│  下排 Z X C V           │   score / unmapped /    │
│                        │   warnings / renders    │
├────────────────────────┴─────────────────────────┤
│ STEP GRID：lanes × steps 字符网格（█ note，· 空）  │
│            播放头列反色                            │
└──────────────────────────────────────────────────┘
```

- pad 状态：正常（绿框，触发闪光）/ empty（暗）/ 禁用（灰，reserved）/ 静音（变暗 + 标签划线）/ 素材错误（红字 warning）。
- 键盘：上排 `A S D F` → pad 0-3，下排 `Z X C V` → pad 4-7，与点击等效。
- 落地态：拖放区（ASCII 提示画）+ "加载示例" 按钮。
- 内置示例：`apps/web/public/example-patch/`——对 demo `output/testsong` 运行 `lmdj-patchify` 产出的 `patch.json` + 该输出目录的**真 wav**（注意 patchify 测试用的 golden fixture 内 wav 是占位字节，不能作示例音源）。

## 错误处理

| 情况 | 行为 |
|------|------|
| patch.json 不过 schema 校验 | 停在落地态，错误面板列出 ajv 错误路径 |
| wav 缺失 / 解码失败 | 该 element 记 warning，pad 显示错误态，pattern 跳过其 note，不阻塞整个 patch |
| `metadata.status = "rejected"` | 黄色横幅提示，仍可播放 |
| `unmapped_element_ids` 非空 | Inspector 单独列出 |
| AudioContext 需用户手势 | 首次交互时 resume |

## 测试

- **Vitest**：loader 校验（golden `patch.json` fixture + 破坏型变体）、step 数学（stepDuration、末尾回卷）、mute 集合逻辑、调度窗口计算（抽为纯函数）。
- **React Testing Library**：PadGrid 各状态渲染、rejected 横幅。
- **不做**：真实音频 e2e（headless 音频不可靠）；手动冒烟 = 加载示例 → 播放 → 静音 → 触发。

## 范围外（v1 不做）

Scenes 切换（只展示 scene_original 名称）、Modes、AI Talk、16-pad Pro View、量化触发（`behavior.quantize` 读取但不执行）、trigger_group 组员展开、录音/导出、移动端触控、任何后端。

## 成功标准

1. 拖入任意 patchify 产出的 package 目录（或点示例），2 秒内看到完整 Patch View。
2. 播放的 groove 与 demo `render_preview.wav` 听感一致（step 时序正确）。
3. 静音 Drums pad 时 kick/snare/hat 全部消声，恢复即回来。
4. 坏 patch（schema 不过 / wav 缺失）给出可读错误而非白屏。
5. 全程未读 `lanes.json`/`chart.mid`。
