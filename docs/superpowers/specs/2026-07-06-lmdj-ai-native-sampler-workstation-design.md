# LMDJ AI-Native Sampler Workstation 设计

日期：2026-07-06
状态：待评审草案

## 产品判断

LMDJ 是一个 AI-native sampler workstation。它不是把传统 MPC 原样搬进软件，也不是单纯的 AI song generator。它最核心的产品动作，是把一个音乐 idea 或一首已有歌曲转化成一个可演奏、可编辑的 sampler patch。

产品需要同时做到两件事：用 AI 降低入门门槛，同时保留足够高的专业上限。专业用户需要控制感、可解释性、可导出的音乐材料，以及可 remix 的资产；新用户需要自然的起点、被引导的决策过程，以及立刻听得到的音乐反馈。

## 核心工作流

LMDJ 从两种输入路径开始：

```text
Idea
  -> AI generates music materials
  -> system builds loops / sounds / patterns
  -> system creates a patch
  -> patch maps to pads

Uploaded song
  -> system analyzes, separates, chops, and extracts
  -> system builds loops / sounds / patterns
  -> system creates a patch
  -> patch maps to pads
```

Patch 生成之后，两条路径进入同一个后续流程：

```text
Patch View
  -> Scene Variations
  -> Perform / Arrange / Mix
  -> Export Song / Share Video
  -> Remix / Sample / Fork inside the platform
```

这个统一动作叫 **Patchify**：把 idea 或歌曲转化为可演奏、可编辑的 sampler patch。

## 产品对象

LMDJ 应该使用分层对象模型：

- `Session`：用户和 AI 的一次创作对话与工作流。
- `Project`：可以持续制作和保存的音乐作品。
- `Patch`：主要的 sampler workstation 状态。
- `Pad`：patch 里的智能控制单元。
- `Scene`：由 pads、patterns、mix、energy 组成的一组完整音乐状态。
- `Element`：sample、loop、chop、stem、pattern、pad action 或其他可复用音乐材料。
- `Render`：导出的音频、视频、封面或分享片段。
- `Lineage`：作品和元素之间的 remix、sample、fork 关系。

AI 工作的持久化输出应该是 patch 或 project state，而不应该只是一段 render 后的音频。

## Patch View

Patch View 是主要工作台。用户可以从 chat 开始，但第一次真正进入工作空间时，应该看到 patch，而不是空白 timeline 或聊天记录。

Patch View 包含：

```text
Pads + Scenes + Modes + AI Talk + Inspector
```

### Pads

Pads 是智能音乐控制单元。一个 pad 可以触发 sample、loop、chop group、scene、FX action、AI variation、mute/solo state，或者 energy/density change。

默认 layout 应该是自适应的：

- `8-pad Focus View`：默认第一屏，降低认知负担。
- `16-pad Pro View`：展开后的专业视图，提供更多控制。
- `Custom Pad Banks`：后续高级层，允许用户自定义 mapping。

默认 8-pad layout 使用固定语义槽位，但内容由 AI 自动填充：

```text
[ Drums ] [ Bass ] [ Harmony ] [ Lead/Vocal ]
[ Fill ]  [ Drop ] [ Mute ]    [ FX/Variation ]
```

这样既能保持界面可学习，又能让每个 patch 都有个人化结果。

### Scenes

Scene 是一组可演奏的音乐状态。AI 生成 variation 时，默认应该创建新 scene，而不是覆盖当前 patch。

示例：

```text
Scene A: Original
Scene B: Darker
Scene C: Club
Scene D: Breakdown
```

内部可以支持 pad、pattern、mix 或 scene 层级的 variation。用户默认看到的应该是 Scene Variation，因为它最自然地对应编曲和演出。

### Modes

Modes 定义同一组 pad surface 当前如何工作。初始 modes：

- `Sample`：查看和编辑 sounds、chops、loops、pad materials。
- `Perform`：现场演奏和控制 patch。
- `Arrange`：把 scenes 组织成 song structure。
- `AI`：查看 suggestions、action history、generated alternatives。
- `Mix`：调整 balance、effects 和整体声音质感。

Mode 切换默认应该显性。AI 可以建议或辅助切换 mode，但必须解释原因，并让用户始终知道当前上下文。

规则：

- 在 production work 中，AI 可以建议 mode change，并在需要时请求确认。
- 在 exploratory flow 中，AI 可以排队执行辅助切换，但需要明确提示并允许 undo。
- 在 live performance 中，AI 不能意外改变 pad semantics 或 mode behavior。

## AI 交互模型

LMDJ 应该采用 hybrid AI model：

```text
Entry: chat-first
Project work: command layer + contextual co-pilot
```

用户可以用自然语言开始，包括 mood、scene、reference 或 production intent。进入 project 后，AI 应该变成 workstation 的控制层，而不只是聊天窗口。

### AI Talk Button

主要 AI 交互应该是 push-to-talk control：

```text
Hold AI button
  -> speak
Release
  -> AI parses intent
  -> AI executes, previews, or asks for confirmation
```

可用变体：

- `Tap`：打开或收起 AI panel。
- `Hold`：说一个通用 command。
- `Hold + Pad`：针对某个 pad 或 element 说话。

这样 AI 会像设备的一部分，而不是独立 chatbot。

### Assist Modes

AI 的执行策略取决于用户的 assist mode：

- `Manual`：AI 解释和建议。任何会改变 project 的动作都需要确认。
- `Guided`：低风险编辑可以直接执行；高风险编辑需要确认。
- `Flow`：探索时，AI 可以执行有边界的辅助变化，但必须有提示和 undo。

默认应该是 `Guided`。

每个 AI action 都应该生成可读 history。用户需要知道 AI 理解了什么、改了哪里，以及如何 compare 或 undo。

反馈应该组合：

- readable intent/action cards，
- before/after listening，
- visible patch or parameter highlights。

## History And Trust

History system 应该结合：

- `Undo / Redo`：普通编辑。
- `AI Action History`：可读的 AI changes。
- `Versions / Takes`：重要创作分支、performance takes 和 publishable states。

AI 应该经常生成 alternatives as variations，而不是破坏性地直接修改当前状态。这样可以保持创作探索可回退，也让专业用户拥有控制感。

## Sharing And Community

外部分享应该是 Song-first。用户在 LMDJ 外部看到的第一印象是音乐作品本身，并由 artwork、character、cover 或 generated short video 这类视觉身份支撑。

在 LMDJ 平台内部，同一首歌应该打开为创作动作：

```text
Listen
Remix This
Sample This
Open Patch
Fork From Moment
```

对专业用户来说，`Remix This` 和 `Sample This` 比被动收听更重要。平台应该把 samples、loops、chops、patterns 和 patches 都当成可复用创作材料。

长期 community loop 是：

```text
Create Patch
  -> Render Song
  -> Share externally
  -> Bring users back to LMDJ
  -> Sample / Remix / Fork
  -> New Patch
  -> New Song
```

Lineage 是核心产品概念。用户应该能看到一个 element 来自哪里、谁使用了它，以及它衍生出了哪些作品。

## V1 范围

V1 应该验证这个核心命题：

```text
Users can start from an idea or uploaded song and get a playable, editable, shareable AI-generated sampler patch.
```

V1 应该包含：

- idea input，
- song upload input，
- 包含 loops、sounds、patterns 的 Patchify result，
- 8-pad Focus Patch，
- 16-pad Pro expansion，
- basic AI Talk concept，如果可行用 voice 实现；如果暂时不可行，可以先用 text substitute，
- Scene Variation，
- basic undo and AI action history，
- song render，
- share export entry point，
- 平台内的 Listen、Remix This、Sample This、Open Patch 动作定义。

V1 不尝试做：

- full DAW timeline，
- full mixer，
- hardware-grade live performance guarantees，
- complete community recommendation feed，
- complete licensing marketplace，
- full custom pad-action editor，
- real-time AI bandmate behavior，
- collaborative multi-user editing，
- full performance video replay export。

## 关键风险

- 如果 Patchify 质量弱，产品会像玩具。
- 如果 AI changes 不可解释或不可回退，专业用户不会信任系统。
- 如果默认 pads 太抽象，新用户不知道怎么玩。
- 如果分享只导出音频，但没有回到 patch/remix/sample actions 的路径，community loop 会很弱。
- 如果 V1 同时做完整 workstation 和完整 social platform，范围会失控。

## 推荐的第一版产品形态

第一版产品应该是 Patchify-centered prototype：

```text
Idea or Upload
  -> Patchify
  -> 8-pad Patch View
  -> Scene Variation + AI Talk
  -> Render Song
  -> Share / Remix / Sample path
```

这能让产品稳定落在 AI-native sampler workstation 的判断上，同时为后续 community 和 real-time AI performance system 留出空间。
