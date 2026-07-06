# LMDJ AI-Native Sampler Workstation Design

Date: 2026-07-06
Status: draft for review

## Product Thesis

LMDJ is an AI-native sampler workstation. It is not a traditional MPC copied into software, and it is not only an AI song generator. Its core product action is turning a music idea or an existing song into a playable, editable sampler patch.

The product should keep a high professional ceiling while lowering the entry barrier through AI. Professional users need control, explainability, exportable materials, and remixable assets. Newer users need a natural way to start, guided decisions, and immediate musical feedback.

## Core Workflow

LMDJ starts from two input paths:

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

After patch creation, both paths share the same workflow:

```text
Patch View
  -> Scene Variations
  -> Perform / Arrange / Mix
  -> Export Song / Share Video
  -> Remix / Sample / Fork inside the platform
```

This shared action is called **Patchify**: turn an idea or song into a playable, editable sampler patch.

## Product Objects

LMDJ should use a layered object model:

- `Session`: one creative conversation and workflow with AI.
- `Project`: a saved music work that can continue over time.
- `Patch`: the main sampler workstation state.
- `Pad`: a smart control unit inside a patch.
- `Scene`: a coherent musical state made from pads, patterns, mix, and energy.
- `Element`: sample, loop, chop, stem, pattern, pad action, or other reusable material.
- `Render`: exported audio, video, cover, or share clip.
- `Lineage`: remix, sample, and fork relationships between works and elements.

The durable output of AI work should be a patch or project state, not only a rendered audio file.

## Patch View

Patch View is the main workstation surface. The user may begin with chat, but the first real workspace should be a patch, not a blank timeline or a chat transcript.

Patch View contains:

```text
Pads + Scenes + Modes + AI Talk + Inspector
```

### Pads

Pads are smart musical controls. A pad can trigger a sample, loop, chop group, scene, FX action, AI variation, mute/solo state, or energy/density change.

The default layout should be adaptive:

- `8-pad Focus View`: default first view for low cognitive load.
- `16-pad Pro View`: expanded view for more professional control.
- `Custom Pad Banks`: later advanced layer for user-defined mappings.

The default 8-pad layout should use fixed semantic slots with AI-filled content:

```text
[ Drums ] [ Bass ] [ Harmony ] [ Lead/Vocal ]
[ Fill ]  [ Drop ] [ Mute ]    [ FX/Variation ]
```

This keeps the interface learnable while still allowing every patch to feel personal.

### Scenes

A scene is a playable musical state. AI variations should default to creating new scenes instead of overwriting the current patch.

Examples:

```text
Scene A: Original
Scene B: Darker
Scene C: Club
Scene D: Breakdown
```

Internally, variations can exist at pad, pattern, mix, or scene level. The user-facing default should be Scene Variation because it maps naturally to arrangement and performance.

### Modes

Modes define how the same pad surface behaves. Initial modes:

- `Sample`: inspect and edit sounds, chops, loops, and pad materials.
- `Perform`: play and control the patch live.
- `Arrange`: organize scenes into a song structure.
- `AI`: review suggestions, action history, and generated alternatives.
- `Mix`: adjust balance, effects, and broad sonic polish.

Mode switching should be explicit by default. AI may suggest or assist mode changes, but it must explain the reason and keep the user oriented.

Rules:

- In production work, AI suggests mode changes and asks for confirmation when needed.
- In exploratory flow, AI can queue assisted changes with visible notice and undo.
- During live performance, AI must not unexpectedly change pad semantics or mode behavior.

## AI Interaction Model

LMDJ should use a hybrid AI model:

```text
Entry: chat-first
Project work: command layer + contextual co-pilot
```

Users can start with natural language, including mood, scene, reference, or production intent. Once inside a project, AI becomes a workstation control layer rather than only a chat interface.

### AI Talk Button

The main AI interaction should be a push-to-talk control:

```text
Hold AI button
  -> speak
Release
  -> AI parses intent
  -> AI executes, previews, or asks for confirmation
```

Useful variants:

- `Tap`: open or close the AI panel.
- `Hold`: speak a general command.
- `Hold + Pad`: speak about a specific pad or element.

This makes AI feel like part of the device, not a separate chatbot.

### Assist Modes

AI execution policy should depend on the user's assist mode:

- `Manual`: AI explains and suggests. Project-changing actions require confirmation.
- `Guided`: low-risk edits can execute directly; high-risk edits require confirmation.
- `Flow`: AI can perform bounded assisted changes during exploration, with notice and undo.

Default should be `Guided`.

Every AI action should create readable history. Users should know what AI understood, what changed, and how to compare or undo it.

Feedback should combine:

- readable intent/action cards,
- before/after listening,
- visible patch or parameter highlights.

## History And Trust

The history system should combine:

- `Undo / Redo`: for normal editing.
- `AI Action History`: for readable AI changes.
- `Versions / Takes`: for important creative branches, performance takes, and publishable states.

AI should often generate alternatives as variations rather than destructively editing the current state. This keeps creative exploration reversible and professional users in control.

## Sharing And Community

External sharing should be Song-first. The first impression outside LMDJ is the music work itself, supported by visual identity such as artwork, character, cover, or generated short video.

Inside the LMDJ platform, the same song should open into creation actions:

```text
Listen
Remix This
Sample This
Open Patch
Fork From Moment
```

For professional users, `Remix This` and `Sample This` are more important than passive listening. The platform should treat samples, loops, chops, patterns, and patches as reusable creative material.

The long-term community loop is:

```text
Create Patch
  -> Render Song
  -> Share externally
  -> Bring users back to LMDJ
  -> Sample / Remix / Fork
  -> New Patch
  -> New Song
```

Lineage is a core product concept. Users should be able to see where an element came from, who used it, and what works emerged from it.

## V1 Scope

V1 should validate this core claim:

```text
Users can start from an idea or uploaded song and get a playable, editable, shareable AI-generated sampler patch.
```

V1 should include:

- idea input,
- song upload input,
- Patchify result with loops, sounds, and patterns,
- 8-pad Focus Patch,
- 16-pad Pro expansion,
- basic AI Talk concept, implemented as voice if feasible or a temporary text substitute if needed,
- Scene Variation,
- basic undo and AI action history,
- song render,
- share export entry point,
- internal actions for Listen, Remix This, Sample This, and Open Patch.

V1 should not attempt:

- full DAW timeline,
- full mixer,
- hardware-grade live performance guarantees,
- complete community recommendation feed,
- complete licensing marketplace,
- full custom pad-action editor,
- real-time AI bandmate behavior,
- collaborative multi-user editing,
- full performance video replay export.

## Key Risks

- If Patchify quality is weak, the product will feel like a toy.
- If AI changes are not explainable or reversible, professional users will not trust the system.
- If default pads are too abstract, newer users will not understand how to play.
- If sharing only exports audio without a path back to patch/remix/sample actions, the community loop will be weak.
- If V1 tries to build both a full workstation and a full social platform, scope will become unmanageable.

## Recommended First Product Shape

The first product should be a Patchify-centered prototype:

```text
Idea or Upload
  -> Patchify
  -> 8-pad Patch View
  -> Scene Variation + AI Talk
  -> Render Song
  -> Share / Remix / Sample path
```

This keeps the product grounded in the AI-native sampler workstation thesis while leaving room for the later community and real-time AI performance systems.
