# Godot Engine 源码级跨平台、模块化与 LMDJ 技术相关性报告

> 日期：2026-07-29
>
> 文档状态：技术研究报告，不是已批准设计、实现计划或发布证明
>
> Godot 基线：`4.7.1-stable`，源码提交 `a13da4feb8d8aefc283c3763d33a2f170a18d541`
>
> LMDJ 基线：`37c8145eb89e9b388cb8f2ca0510a8ee7a9f38a7`
>
> 配套资料：[Godot 产品调研](./2026-07-29-godot-engine-product-research.md) · [可交互架构图](./diagrams/2026-07-29-godot-lmdj-architecture.html)

## 1. 结论先行

### 1.1 总体判断

Godot 与 LMDJ 的最佳关系不是“用游戏引擎重写现有产品”，而是：

> **保留 React Creator Web、FastAPI、Audio Worker、Core Models、Patchify 与 `lmdj.patch.v1`；如需原生演奏端、舞台视觉端或装置端，再把 Godot 作为一个新的 Patch 消费者。**

理由如下：

1. **Godot 的跨平台优势主要在客户端运行时。**

   它把窗口、输入、音频、渲染、文件系统和导出封装为统一接口，再由各平台实现。LMDJ 的 16-pad 演奏、MIDI、Scene/Pattern 切换、实时视觉和原生打包都能受益。

2. **Godot 不能替代 LMDJ 的音频理解流水线。**

   Demucs、librosa、Material Extractor、质量门、Patchify 和 Job 状态都属于 Python/后端职责。桌面 Godot 可以启动子进程，但 Web、移动端和商店沙箱不能把“携带 Python + Torch”当作通用跨平台方案。

3. **Godot 的模块化很强，但层次不同。**

   它同时具有 SCons 构建模块、Server/Driver 后端注册、GDExtension 动态扩展、项目脚本/插件和平台导出模板。应先用内置能力与 GDScript 验证，再按测量结果决定是否引入 GDExtension；不应一开始维护自定义引擎分叉。

4. **`interactive_music` 是最接近 LMDJ 音乐对象的内置模块，但不是 Patch 播放器。**

   它支持按下一拍、下一小节或流结尾切换片段，并提供淡入、淡出、交叉淡化、自动推进和 filler。它适合未来 Scene/Pattern 过渡，但不理解 `lmdj.patch.v1`，也不负责 16-pad 多采样触发或 Step Sequencer。

5. **Godot Web 不是现有 React Web 的低成本升级。**

   它会增加 WebAssembly/WebGL 运行时、加载体积和 Canvas UI；线程和 GDExtension 还涉及跨源隔离。对上传、队列、恢复、可访问性和普通表单交互，现有 DOM 应用仍更合适。

### 1.2 建议等级

| 方向 | 结论 | 原因 |
|---|---|---|
| Godot 原生演奏 / 舞台视觉客户端 | **值得做受控原型** | 高度匹配 Audio、MIDI、输入、视觉和桌面打包 |
| Godot Web 独立演奏 Surface | **条件式评估** | 可复用 Patch，但需验证包体、音频路径、Canvas 可访问性与浏览器限制 |
| 用 Godot 替换 React Creator Web | **当前不建议** | 会重做上传、作业恢复、DOM UI、Schema 校验和导出流程 |
| 用 Godot 替换 Audio Worker / Patchify | **不建议** | 不匹配 Python DSP、模型推理和服务端队列职责 |
| 自定义 Godot 引擎模块 | **暂不建议** | 集成最深，但引擎构建、升级和多平台发布成本最高 |
| GDExtension 原生 DSP / Apple API | **测量后再决定** | 可隔离高性能或平台专有能力，但需要逐平台二进制和兼容管理 |

---

## 2. 研究范围与证据口径

### 2.1 本次研究回答的问题

- Godot 源码如何组织跨平台能力？
- 统一 API 与平台实际能力之间的边界在哪里？
- Godot 如何在编译期、运行期和项目层进行模块化？
- 哪些 Godot Server、Driver、Module、Core API 与 LMDJ 直接相关？
- `lmdj.patch.v1` 如何成为 Godot 客户端的稳定接入边界？
- 哪些方向值得原型验证，哪些方向应保持在现有 LMDJ 后端？

### 2.2 证据标签

| 标签 | 含义 |
|---|---|
| **源码事实** | 在 Godot `4.7.1-stable` 或 LMDJ 当前代码中直接核对 |
| **官方约束** | Godot 官方文档明确描述的平台或兼容性限制 |
| **架构推断** | 基于源码边界得出的工程判断，仍需原型或测量 |
| **研究建议** | 为 LMDJ 提出的候选方向，不代表已批准 |

### 2.3 不在本报告中承诺的事项

- 不改变 `lmdj.patch.v1`。
- 不创建 Godot 客户端实现。
- 不批准 Sampler Edit、Take Recording 或 Scene Variation 的产品契约。
- 不声称 Godot 已达到 LMDJ 当前 Web Audio 的时序、延迟或浏览器兼容水平。
- 不把本地源码编译能力当作已验证的 Windows、Linux、Android、iOS 或 Web 发布证据。

---

## 3. Godot 源码中的跨平台架构

Godot 的跨平台能力可以概括为六层：

```text
SCons 构建选择
  └─ platform/<target>/detect.py + SCsub
      └─ OS / DisplayServer / AudioDriver / MIDI / 网络 / 文件系统后端
          └─ AudioServer / RenderingServer / TextServer / PhysicsServer...
              └─ Scene / Resource / Input / UI
                  └─ 内置 Module + GDExtension + GDScript/C#
```

关键点是：**跨平台不是把所有能力抹平成完全相同，而是给消费者一个稳定入口，同时允许平台实现返回不同的 feature 或 `ERR_UNAVAILABLE`。**

### 3.1 构建目标：只编入目标平台和启用模块

Godot 根目录的 [`SConstruct`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/SConstruct) 会扫描 `platform/*`，导入每个平台的 `detect.py`，并根据构建参数选择：

- `platform=windows|macos|linuxbsd|web|android|ios|visionos`
- `target=editor|template_debug|template_release`
- `arch`、`precision`、编译器、渲染驱动、线程和 sanitizer
- `module_<name>_enabled`
- `custom_modules`
- `disable_3d`

**对 LMDJ 的意义：**

- 如果未来只有 2D Pad、Pattern 和视觉层，可以评估 `disable_3d=yes` 的自定义导出模板，减少不需要的引擎内容。
- 平台模板不是同一个二进制到处运行，而是每个目标分别构建、测试和签名。
- 自定义模板会带来持续构建责任，只有包体或扩展需求明确时才值得承担。

### 3.2 OS 抽象：统一入口，不保证统一能力

[`core/os/os.h`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/os/os.h) 定义抽象 `OS`，包含：

- 进程执行与实例创建
- 环境变量与系统目录
- 动态库加载
- 时间、熵源和主循环
- MIDI 输入管理
- 平台 feature 查询

平台实现包括：

- Windows：`OS_Windows`
- Linux/BSD：`OS_LinuxBSD -> OS_Unix`
- macOS：`OS_MacOS -> OS_Unix`
- Web：`OS_Web -> OS_Unix`
- Android：`OS_Android -> OS_Unix`
- iOS / visionOS：`OS_AppleEmbedded`

但抽象方法可以明确返回不可用。例如：

- Web 的 `kill()` 不可用。
- Web 的 `execute()` 只能通过宿主 JavaScript 回调模拟，不是本地子进程。
- Web 的低层 socket 大量方法返回 `ERR_UNAVAILABLE`。
- Android、Web、Headless 的文件或显示能力均存在差异。

**LMDJ 结论：**

不能把桌面端可启动 Python Worker 的能力外推到 Web 和移动端。需要先定义能力矩阵，再为每个平台选择后端 API、原生扩展或禁用路径。

### 3.3 DisplayServer：窗口能力通过 feature 检测

[`DisplayServer`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/display/display_server.h) 是窗口、屏幕、剪贴板、IME、触摸、原生对话框等能力的抽象层。平台后端通过 `register_create_function()` 注册，运行时通过 `has_feature()` 查询：

- 鼠标与触摸屏
- 剪贴板
- HiDPI
- IME
- 原生文件对话框
- 子窗口
- HDR 输出
- 屏幕阅读器等

引擎始终保留 Headless DisplayServer 作为后备。

**LMDJ 结论：**

- Pad、键盘、触摸、文件选择需要按 feature 降级。
- Godot 的 Canvas UI 不是现有 DOM 可访问性的自动等价替代。
- 如果 Godot 客户端成为正式 Creator Surface，必须单独验证键盘导航、屏幕阅读器、文本缩放、IME 和焦点系统。

### 3.4 Server / Driver：跨平台能力的核心解耦点

Godot 的“Server”不是独立网络服务，而是引擎内的系统边界：

| Server | 职责 | 与 LMDJ 的相关性 |
|---|---|---|
| `AudioServer` | Mixer、Bus、Effect、Stream/Sample 播放、输入 | **高**：Pad 播放、Mute、Gain、录音和效果链 |
| `DisplayServer` | 窗口、屏幕、输入法、剪贴板、原生 UI 能力 | **高**：跨平台 Creator / Performance UI |
| `RenderingServer` | 2D/3D 渲染和 GPU 资源 | **中高**：舞台视觉、波形和实时反馈 |
| `TextServer` | 字形、排版、复杂文本 | **中高**：中英文 Creator UI |
| `CameraServer` | 摄像头输入 | **低 / 条件式**：未来互动视觉，不是音频输入 |
| Physics / Navigation | 物理与寻路 | **低**：当前 LMDJ 无直接需求 |
| XR Server | XR 设备和空间交互 | **远期**：装置或表演实验 |

Audio 后端由 `AudioDriver` 实现并注册：

- Windows：WASAPI、XAudio2
- macOS / Apple Embedded：CoreAudio
- Linux/BSD：PulseAudio、ALSA
- Android：OpenSL
- Web：AudioWorklet，必要时回退 ScriptProcessor

这意味着 LMDJ 可以复用同一个 `AudioServer` 调用模型，但仍需逐平台测量输出延迟、输入权限、设备切换和后台行为。

### 3.5 平台能力矩阵

| 平台 | Godot 音频后端 | 源码内 MIDI 输入 | 动态扩展 / 进程 | LMDJ 主要判断 |
|---|---|---|---|---|
| Windows | WASAPI / XAudio2 | WinMIDI | 支持 DLL 与桌面进程 | **最适合原生演奏端原型**；需测声卡与 ASIO 缺口 |
| macOS | CoreAudio | CoreMIDI | 支持 dylib 与桌面进程 | **最适合首个原型**；可接 Apple 专有 API |
| Linux/BSD | PulseAudio / ALSA | ALSA MIDI | 支持 `.so` 与 Unix 进程 | 可支持创作者桌面端；需处理发行版和音频栈差异 |
| Web | Web Audio / AudioWorklet | WebMIDI | GDExtension 需 Web 动态链接；无普通本地子进程 | 可做独立演奏 Surface，但不是当前 React Web 的无损替换 |
| Android | OpenSL | 4.7.1 源码未发现内置 Android MIDI Driver | 支持平台库/插件；进程受沙箱限制 | 音频可行，MIDI 和低延迟必须做 Android 专项方案 |
| iOS | CoreAudio | 4.7.1 平台层未注册 CoreMIDI Driver | 原生库/平台插件；商店沙箱 | 音频可行，MIDI、文件交换和后台行为需原生专项验证 |
| visionOS | CoreAudio / Apple Embedded | 未发现独立 MIDI Driver | 平台插件 | 远期装置方向，不是当前优先级 |

> “未发现内置 MIDI Driver”仅指本次固定源码快照中的平台注册路径，不等于操作系统本身不支持 MIDI。

### 3.6 Web 是一个独立能力档位

Godot Web 使用 Emscripten、WebAssembly 和 WebGL 2.0。源码与官方文档共同表明：

- 4.3 起，单线程 Web 导出是默认与推荐路径。
- Web 默认 Sample 播放路径可降低无多线程时的音频延迟，但不支持 AudioEffects、程序化音频等完整能力。
- 切到 Stream 播放可恢复更多引擎音频能力，但会增加延迟，尤其在无多线程时。
- 多线程依赖 `SharedArrayBuffer` 和跨源隔离。
- Web GDExtension 需要 `dlink_enabled=yes` 的模板、导出时启用 Extensions Support，并需要跨源隔离。
- HTTP 受同源策略、非阻塞轮询和浏览器网络 API 限制。
- `user://` 的持久化依赖 IndexedDB，隐私模式、iframe 和浏览器清理策略会影响可靠性。
- 浏览器切到后台标签页会暂停或节流主循环。

**对 LMDJ 的直接影响：**

1. 现有 React Web Audio 已有专门的 look-ahead scheduler；迁移不能只比较“能否发声”，必须比较抖动、后台恢复和 Note 爆发行为。
2. 如果需要 Godot 的完整 Bus/Effect/Generator 路径，Web 端可能要在延迟与跨源隔离之间做取舍。
3. Canvas UI 会降低当前 DOM 对上传、状态、文本摘要和辅助技术的天然适配。
4. Godot Web 更适合单独的“Performance / Visual Surface”，而不是首要的上传与作业管理入口。

官方依据：

- [Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)
- [Compiling for the Web](https://docs.godotengine.org/en/stable/engine_details/development/compiling/compiling_for_web.html)

---

## 4. Godot 的模块化机制

Godot 的模块化不是一种机制，而是至少五种不同成本的机制。

### 4.1 编译期内置模块

[`methods.py`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/methods.py) 的 `detect_modules()` 要求模块包含：

- `register_types.h`
- `SCsub`
- `config.py`

每个模块可以：

- 在 `can_build(env, platform)` 中限制平台或依赖。
- 通过 `module_add_dependencies()` 声明必选或可选依赖。
- 通过 `module_<name>_enabled` 开关。
- 在 CORE、SERVERS、SCENE、EDITOR 初始化层注册类型。

[`modules/modules_builders.py`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/modules_builders.py) 会生成启用模块列表和统一注册代码。

**优点：** 与引擎结合最紧、性能和类型访问最好。

**代价：** 需要自定义引擎构建；升级、补丁、安全和每个平台模板都由团队承担。

**LMDJ 建议：** 暂不使用。只有当 GDExtension 无法满足、且收益经过测量后，才评估自定义模块。

### 4.2 Server / Driver 后端注册

DisplayServer、AudioDriver、RenderingDevice 等通过注册函数挂载平台后端。上层逻辑依赖抽象接口，平台启动时选择可用实现。

**LMDJ 可借鉴的设计：**

- `PatchTransport`：本地 ZIP、HTTP API、编辑器 fixture。
- `AudioAssetLoader`：WAV、MP3、Ogg。
- `InputBackend`：键盘、触摸、桌面 MIDI、WebMIDI、未来平台插件。
- `NativeAnalysisProvider`：无实现、Apple 实现、桌面 DSP 实现。

这些应是 LMDJ Godot Adapter 内部接口，不应改写公共 Patch 契约。

### 4.3 GDExtension

[`core/extension/gdextension.h`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/extension/gdextension.h) 与 Loader/Manager 支持在运行时加载原生库，并使用与内置模块相同的 CORE、SERVERS、SCENE、EDITOR 初始化层。

适合 LMDJ 的候选能力：

- 高性能波形降采样、FFT 或实时 DSP。
- 原生音频设备能力。
- macOS/iOS 的 Apple 专有框架桥接。
- 移动端 MIDI 插件。
- 经测量后确有必要的低延迟处理。

不适合直接承担：

- 把 Python、Torch、Demucs 完整嵌进所有目标平台。
- 复刻 Audio Worker 队列、状态和文件治理。
- 让客户端成为 `lmdj.patch.v1` 的第二个真相源。

GDExtension 仍需要：

- 每个平台和架构分别编译库。
- 与 Godot / godot-cpp 版本和精度配置保持兼容。
- 在 `.gdextension` 中声明 `compatibility_minimum` / `compatibility_maximum`。
- Web 端使用特殊动态链接模板。

官方依据：

- [What is GDExtension?](https://docs.godotengine.org/en/latest/engine_details/engine_api/gdextension/what_is_gdextension.html)
- [The .gdextension file](https://docs.godotengine.org/en/latest/engine_details/engine_api/gdextension/gdextension_file.html)

### 4.4 项目脚本与编辑器插件

GDScript、C#、EditorPlugin 和普通项目资源不要求自定义引擎。

**LMDJ 建议的起点：**

- GDScript 实现 Patch Adapter、HTTP/ZIP Loader、输入路由和播放原型。
- EditorPlugin 仅用于开发期 fixture 检查、Patch 浏览或调试面板。
- 不把 Godot Resource 文件变成 `patch.json` 的权威副本。

`mono` / C# 能提升复杂客户端代码的类型能力，但 Godot 4 的 Web 导出仍不支持 C#，因此会扩大平台差异。首个跨平台原型应优先 GDScript。

### 4.5 导出模板与 PCK

[`EditorExportPlatform`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/editor/export/editor_export_platform.h) 定义平台导出接口，并支持：

- `template_debug` / `template_release`
- 平台 ExportPlugin
- PCK / ZIP 打包
- Patch pack
- 共享库与平台资源收集
- 签名、平台配置和设备运行

**必须区分两种“包”：**

- Godot PCK：引擎项目与导出资源包。
- LMDJ Patch Package：`patch.json + samples` 的产品内容包。

LMDJ Patch Package 不应被隐式改造成 Godot PCK。运行时内容应继续由 LMDJ 契约描述，Godot 只是加载器和播放器。

### 4.6 扩展方式决策表

| 方式 | 适合内容 | 跨平台成本 | 升级成本 | LMDJ 当前建议 |
|---|---|---:|---:|---|
| GDScript / 内置 API | Patch Adapter、HTTP、ZIP、播放、UI、输入 | 低 | 低 | **首选原型** |
| EditorPlugin | Fixture 检查、开发工具 | 低 | 低 | 条件式 |
| GDExtension | 原生 DSP、平台 API、移动 MIDI | 中高 | 中 | **测量后使用** |
| 自定义 Module | 深度 Server/引擎修改 | 高 | 高 | 暂不使用 |
| 引擎 Fork | 修改核心行为 | 最高 | 最高 | 避免 |
| LibGodot 嵌入 | 把引擎作为宿主库 | 高、仍在演进 | 高 | 低优先级研究 |

---

## 5. 与 LMDJ 直接相关的 Godot 技术能力

### 5.1 运行时能力清单

| Godot 源码区域 | 能力 | LMDJ 对应模块 | 相关性 | 主要缺口 |
|---|---|---|---|---|
| `servers/audio/` | Mixer、Bus、Effect、Stream/Sample 播放 | `AudioEngine.ts`、Pad 播放 | **高** | 需重做 LMDJ transport 和行为语义 |
| `modules/interactive_music/` | 节拍/小节量化切换、fade、auto-advance | Scene / Pattern / Performance | **高** | 不是 Step Sequencer，不读 Patch |
| `core/os/midi_driver.*` + 平台 Driver | MIDI 输入事件 | `MidiInput.ts` | **高** | 无 MIDI 输出；Android/iOS 内置 Driver 缺口 |
| `scene/resources/audio_stream_wav.*` | WAV 文件/Buffer 动态加载 | Patch samples | **高** | 需处理来源路径、安全、内存和缺失素材 |
| `modules/mp3/` | MP3 文件/Buffer 动态加载 | 上传或未来素材 | **高** | Patch 当前样本主要为 WAV |
| `modules/ogg/` + `modules/vorbis/` | Ogg Vorbis 运行时加载 | 压缩内容候选 | **中高** | 改格式会影响音质、延迟和契约，需另行决策 |
| `scene/main/http_request.*` | 异步 HTTP、下载文件 | API job、Patch、samples、Export | **高** | Web 同源/CORS、恢复与错误模型需适配 |
| `core/io/json.*` | JSON parse/stringify | `patch.json` | **高** | 无 AJV 等价的内置 JSON Schema 校验器 |
| `modules/zip/` | ZIP 读取与生成 | Creator Export / Patch 包 | **高** | 路径穿越、大小、原子写入需 LMDJ 规则 |
| `core/io/file_access.*` / `DirAccess` | `res://`、`user://` 和平台文件 | Patch cache、下载、用户内容 | **高** | Web 持久化非强保证；移动沙箱差异 |
| `servers/audio/effects/audio_effect_record.*` | 录制 Audio Bus 为 WAV | Take Recording / Bounce | **中高** | 只解决音频捕获，不解决 Take 事件契约 |
| `servers/audio/effects/audio_stream_generator.*` | 程序化推送音频帧 | 实时 DSP / Preview | **中** | Web 默认 Sample 路径不支持程序化音频 |
| `audio_effect_spectrum_analyzer.*` | FFT 频段强度 | 可视化、输入反馈 | **中高** | 不是离线素材分析与语义分割 |
| `servers/rendering/` / Shader | 2D/3D 视觉 | Performance / Visualizer | **中高** | 不属于 Creator Core 必需范围 |
| `scene/gui/` + TextServer | Control UI、排版、焦点 | Creator Workbench | **高** | DOM 可访问性与表单能力不会自动保留 |
| `servers/display/accessibility_server.*` | 辅助功能后端 | 可访问性 | **中高** | 需逐平台实测，尤其 Web Canvas |
| `core/extension/` | GDExtension | 原生 DSP / Apple / MIDI 插件 | **条件式高** | 多平台构建与 ABI 管理 |
| `editor/export/` + `platform/*/export` | 桌面、Web、移动导出 | 客户端分发 | **高** | 签名、模板、商店和 CI 都需独立门禁 |
| Headless Display / Dummy Audio | 无窗口运行和自动测试 | CI / Fixture tests | **中高** | 无真实设备时不能证明音频延迟和 MIDI |

### 5.2 `interactive_music` 与 LMDJ 的精确关系

[`AudioStreamInteractive`](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/interactive_music/audio_stream_interactive.h) 提供：

- 最多多个音频 Clip。
- 过渡触发点：立即、下一拍、下一小节、源结尾。
- 目标位置：相同位置、起点、上次位置。
- Fade：in、out、cross、automatic，时长以 beat 表达。
- filler、hold previous、auto advance、return。
- 使用流的 BPM、bar beats、beat count 计算过渡。

它与 LMDJ 的关系是：

| LMDJ 对象 | 可借用的 Godot 能力 | 不能直接映射的部分 |
|---|---|---|
| Scene | 按拍/小节切换音乐状态 | LMDJ Scene 包含 pad、pattern 等产品语义 |
| Pattern | 量化后的切换时点 | Pattern 内逐 Note 触发仍需 LMDJ scheduler |
| Phrase A/B | Clip 与 transition table | 仍需遵守 `full_mix_exclusive` |
| Variation | 自动推进或切换候选 | AI 生成、版本、Lineage 不属于该模块 |
| Fill / Drop | filler / transition 概念接近 | Patch v1 中相关 action 仍是 reserved |

**结论：**

可把它作为未来 Scene/长 Phrase 的过渡执行器，但不能替代 Patch Adapter、16-pad 路由或 Pattern transport。

### 5.3 音频输入、录音与分析边界

Godot 内置能力可以覆盖：

- Microphone 输入流。
- Audio Bus 录制。
- 实时 FFT 频段查询。
- 程序化音频帧推送。
- Bus Effect 和 Gain/Pan 等播放处理。

但它不直接提供 LMDJ 现有流水线的：

- 四 Stem 分离。
- Timing artifact。
- Downbeat / loop candidate 质量门。
- Material Extractor。
- 固定 16 Slot 决策。
- `lmdj.materials.v1 -> lmdj.patch.v1` Patchify。

因此：

> **Godot 可以承担“演奏期音频”和有限的“本地编辑/录制”，不能据此推断它能替代“歌曲理解与 Patch 生成”。**

### 5.4 源码 `modules/` 的完整相关性分组

Godot `4.7.1-stable` 本次扫描到 57 个内置构建模块。下表覆盖全部模块；分组表示对当前 LMDJ 的优先级，不表示引擎默认是否启用。

| 分组 | 模块 | LMDJ 判断 |
|---|---|---|
| **P0：直接产品相关** | `gdscript`, `interactive_music`, `mp3`, `ogg`, `vorbis`, `zip`, `mbedtls` | Patch Adapter、音乐播放、动态音频、内容包和 HTTPS |
| **P1：客户端基础支撑** | `freetype`, `text_server_adv`, `text_server_fb`, `svg`, `regex`, `jsonrpc`, `websocket`, `objectdb_profiler` | UI 文本、图标、校验辅助、实时状态和性能诊断 |
| **P1/P2：视觉与资源格式** | `bmp`, `jpg`, `webp`, `tga`, `hdr`, `tinyexr`, `dds`, `ktx`, `astcenc`, `basis_universal`, `bcdec`, `betsy`, `cvtt`, `etcpak`, `msdfgen`, `theora` | 主要服务 UI、纹理、视频和舞台视觉；不是音频核心 |
| **P2：未来通信或平台能力** | `camera`, `webrtc`, `multiplayer`, `enet`, `upnp`, `mono`, `openxr`, `webxr`, `mobile_vr` | 远程协作、摄像互动、C# 或 XR；当前无产品批准 |
| **P3：3D/高级视觉工具链** | `fbx`, `gltf`, `csg`, `gridmap`, `meshoptimizer`, `xatlas_unwrap`, `vhacd`, `lightmapper_rd`, `glslang`, `visual_shader`, `noise`, `raycast` | 可用于未来视觉场景；对 Creator Core 非必需 |
| **当前无直接价值** | `godot_physics_2d`, `godot_physics_3d`, `jolt_physics`, `navigation_2d`, `navigation_3d` | 游戏物理/寻路，不驱动当前 LMDJ 音乐工作流 |

注意：LMDJ 最重要的 HTTP、JSON、FileAccess、AudioServer、MIDI 和 DisplayServer 并不都在 `modules/` 目录；它们属于 `core/`、`scene/`、`servers/`、`drivers/` 和 `platform/`。只看 `modules/` 会漏掉主要跨平台能力。

---

## 6. Godot 与 LMDJ 当前模块的逐项映射

| LMDJ 当前边界 | 当前真相源 / 实现 | Godot 可提供 | 仍需 LMDJ 自己实现 | 建议 |
|---|---|---|---|---|
| Core Models | Python dataclasses + JSON Schema | JSON、Dictionary、Resource/RefCounted 模型 | Schema 同步、16-pad、引用完整性和 reserved action 语义 | **保持 Core Models 权威** |
| Patchify | 纯 Python adapter | 无直接替代 | Material/Legacy 映射、确定性 chart、Patch ID | **保持服务端** |
| Audio Worker | Python、librosa、separator、Material Extractor | 仅有限本地 DSP / 原生桥 | 分轨、质量门、状态、缓存、重试 | **不迁移** |
| App API / JobExecutor | FastAPI + file-backed Job + FIFO | HTTPRequest、WebSocket 候选 | 幂等上传、容量、恢复、路径安全、公开资产边界 | Godot 只做消费者 |
| Web Patch Loader | AJV + `lmdj.patch.v1` + 16-pad assertions | JSON parse、动态文件/Buffer 加载 | JSON Schema、跨引用、错误文案、缺失素材一致性 | 新建 Godot Adapter，不复制真相源 |
| Web AudioEngine | Web Audio look-ahead、Gain、loop、exclusive group | AudioServer、AudioStreamPlayer、Bus、Interactive Music | Note scheduler、catch-up、Scene 读取、exclusive parity | 原型必须做行为对照测试 |
| MIDI | WebMIDI、热插拔、Note On/Off | WinMIDI、CoreMIDI、ALSA MIDI、WebMIDI | Bank、Profile、Pad 映射、移动端插件 | 桌面/Web 可复用，移动专项 |
| Creator Workbench | React DOM、PatternSurface、PadMatrix16 | Control UI、Input Map、2D/Shader | 响应式布局、可访问性、状态恢复、产品交互 | 不整体迁移；可做独立 Performance UI |
| Creator Export | API 生成状态和 ZIP 下载 | ZIPReader/ZIPPacker、HTTP 下载 | 权威 Export 状态、文件清单、可复现性 | 继续由 API 负责；Godot 触发/下载 |
| Sampler Edit | 尚未批准完整实现 | WAV Buffer、Bus Effect、运行时参数 | 非破坏编辑契约、波形、slice、持久化、Lineage | 只作为未来验证项 |
| Take Recording | 产品契约未完成 | AudioEffectRecord、Microphone、事件输入 | 原始事件时间、量化视图、bounce、恢复和版本 | 不提前固化 |
| Scene / Variation | Patch 对象模型 + 后续规划 | Interactive Music、状态切换、视觉过渡 | AI 生成、版本、Lineage、非覆盖语义 | 高潜力，但需产品设计门 |
| Visual Performance | 当前非 Creator Core 主线 | RenderingServer、Shader、Particles、XR | LMDJ 音乐语义驱动和演出 UX | Godot 最具差异化价值的方向 |

### 6.1 Contract Purity 必须继续成立

Godot 客户端必须和 Web、CLI、API、Worker 一样只消费：

```text
patch.json (lmdj.patch.v1)
  + patch.json 明确引用的 sample assets
```

不得让 Godot：

- 直接读取 `materials.json`。
- 直接读取 `timing.json` 作为产品播放真相。
- 从 Job ID 推导 package 路径。
- 用 `.tres` / `.res` 取代公共 Patch。
- 在客户端重新决定 16 个 Slot 的语义。
- 静默填补 Empty Pad 或删除缺失素材对应的 Note。

### 6.2 Godot 内置 JSON 不等于 Schema 校验

Godot 的 `JSON.parse()` 只解决语法解析，不等价于 Web 当前的 AJV 2020-12 校验。候选做法：

1. **首个原型：** 复用服务端已校验 fixture，并在 GDScript 实现必须的语义断言。
2. **正式客户端：** 从 `packages/core-models` 生成 Godot 侧类型/校验代码，加入合同漂移检查。
3. **高要求方案：** 引入受控 JSON Schema GDExtension，但必须证明价值高于生成校验代码。

正式门禁至少要覆盖：

- `schema == "lmdj.patch.v1"`
- 恰好 16 个 Pad，顺序和 index 均为 `0..15`
- Scene 覆盖 `0..15`
- Scene 引用的 Pattern 存在
- Pattern Note 引用的 Element 存在
- source path 为 package-root-safe 相对路径
- reserved action no-op
- 缺失/解码失败素材形成 warning，不能修改 Note 数据

### 6.3 LMDJ Scene 与 Godot Scene 不能混为一谈

建议命名：

- `LmdjSceneModel`：Patch 内的音乐状态。
- `Godot SceneTree / PackedScene`：引擎对象和节点生命周期。
- `PerformanceSceneController`：把音乐状态映射到播放器与视觉节点。

否则“切换 Scene”会同时指产品状态和引擎场景切换，容易导致加载、音频连续性和版本语义错误。

---

## 7. 推荐的 Godot 客户端边界

### 7.1 逻辑分层

```text
PatchTransport
  ├─ ApiPatchTransport
  ├─ ZipPatchTransport
  └─ FixturePatchTransport
        ↓
PatchValidator
        ↓
LmdjPatchModel
        ↓
RuntimeAssetLoader
  ├─ WAV / MP3 / Ogg
  └─ cache + missing warnings
        ↓
PlaybackEngine
  ├─ PatternTransport
  ├─ PadVoicePool
  ├─ Gain / mute / exclusive group
  └─ optional InteractiveMusicBridge
        ↑
InputRouter
  ├─ keyboard
  ├─ pointer / touch
  └─ MIDI backend
        ↓
Performance UI / Visual Runtime
```

配套架构图见：

- [LMDJ + Optional Godot Client](./diagrams/2026-07-29-godot-lmdj-architecture.html)

### 7.2 首个版本不应包含的内容

- 不包含 separator、librosa、Demucs 或 Torch。
- 不生成或修改 `lmdj.patch.v1`。
- 不实现 AI Variation。
- 不实现未批准的 Take / Sampler Edit 契约。
- 不引入 GDExtension。
- 不替换 Creator Web。
- 不承诺移动端。

### 7.3 运行时资源加载

LMDJ 的 Patch 和 samples 在用户运行时到达，不能只依赖 Godot 编辑器的导入管线。源码已经提供：

- `HTTPRequest` 下载 JSON、ZIP 或采样。
- `ZIPReader` 枚举与读取包内文件。
- `AudioStreamWAV.load_from_buffer()`。
- `AudioStreamMP3.load_from_buffer()`。
- `AudioStreamOggVorbis.load_from_buffer()`。

实现时需要补充：

- 下载大小与超时限制。
- ZIP 路径穿越防护。
- source path 规范化。
- 校验先于音频加载。
- 解码并发和内存上限。
- 缓存键使用 Patch / Element 稳定身份，而不是 Job ID。
- Web `user://` 非永久时的降级。

---

## 8. 集成场景比较

### 场景 A：保留现有产品，增加 Godot 原生 Performance Client

**路径：**

```text
LMDJ API / Patch ZIP
  → Godot Patch Adapter
  → Audio + MIDI + Visual Runtime
```

**价值：**

- 原生桌面打包。
- 更强的实时 2D/3D 视觉。
- 更自然的舞台、装置、全屏和游戏手柄输入。
- 可逐步接入原生 DSP 或平台 API。

**风险：**

- 新增客户端需要合同一致性测试。
- 需要独立发行、签名、自动更新和设备验证。
- 音频调度必须与 Web 做基准对照。

**结论：推荐作为唯一优先原型。**

### 场景 B：Godot Web Performance Surface

**价值：**

- 与原生客户端共享较多场景和交互代码。
- 适合链接打开即演奏的视觉体验。

**风险：**

- Wasm/WebGL 包体和启动时间。
- Web Audio 的 Sample / Stream 功能取舍。
- 线程、GDExtension与跨源隔离。
- 浏览器后台暂停。
- Canvas 可访问性。
- WebMIDI 浏览器兼容仍受限制。

**结论：在桌面原型通过后再评估，不作为第一目标。**

### 场景 C：Godot 替换 Creator Web

需要重做：

- 上传与预检。
- 多 Job 和 refresh 恢复。
- Queue / capacity / interrupted 状态。
- AJV 合同校验。
- DOM 可访问性。
- Creator Export。
- 响应式工作台和普通表单交互。

**结论：当前成本高于价值，不建议。**

### 场景 D：Godot Headless 作为后端或 Worker

Headless 模式适合：

- 自动加载 fixture。
- 合同适配测试。
- 节点/状态逻辑测试。
- 无 GPU 的部分 CI。

它不适合取代：

- Python DSP 环境。
- 分轨模型推理。
- FastAPI 与作业治理。
- 云端文件生命周期。

**结论：只用作 Godot 客户端的测试运行时，不用作 LMDJ 后端主框架。**

### 场景 E：Godot 嵌入原生宿主 / LibGodot

Godot 4.6 起源码中出现把引擎作为库实例化的能力，但该方向比普通 Godot 应用复杂，生命周期和平台打包仍在演进。

**结论：低优先级。除非未来已有原生宿主必须嵌入 Godot 渲染，否则不进入第一轮验证。**

---

## 9. 主要风险与验证问题

### 9.1 音频时序

当前 Web AudioEngine 使用：

- `25ms` tick。
- `120ms` look-ahead。
- `250ms` 有界 catch-up。
- 病态后台积压丢弃，避免恢复时 Note 爆发。

Godot 原型必须回答：

- 多 Pad 同时触发时的输出抖动如何？
- Pattern loop 边界是否稳定？
- 暂停、窗口失焦、设备切换后如何恢复？
- `full_mix_exclusive` 是否与 Web 一致？
- Web Sample 与 Stream 路径分别达到什么结果？

不能把编辑器中“听起来能播放”当作验证完成。

### 9.2 音频延迟与设备生态

- Windows 源码提供 WASAPI / XAudio2，但未体现专业音频常用的 ASIO。
- macOS CoreAudio 通常适合低延迟，但仍需具体设备和 buffer 测量。
- Linux 需要覆盖 PulseAudio / ALSA，必要时评估 PipeWire 实际环境。
- Android/iOS 需要端到端设备测试，不能从桌面结果外推。

### 9.3 MIDI 能力

Godot 本次源码范围主要提供 MIDI 输入，没有发现通用 MIDI 输出系统。LMDJ 当前首切片也以输入为主，因此短期可匹配；未来如果需要 MIDI Clock、硬件灯光反馈或外部音序器同步，需要单独扩展。

移动端内置 MIDI Driver 缺口意味着：

- 要么限制平台能力。
- 要么开发平台插件/GDExtension。
- 要么通过专用硬件桥或网络协议连接。

### 9.4 合同漂移

新增 Godot 消费者后，`lmdj.patch.v1` 从四方共享变为五方共享。必须扩展合同门禁，而不是复制 schema 后手工维护。

建议 CI 增加：

- Core schema → Godot fixture / generated validator 同步检查。
- Web 与 Godot 对同一 Patch 的 16-pad、Scene、Pattern、missing sample 结果对照。
- reserved action no-op。
- source path 安全。

### 9.5 GDExtension 发布矩阵

每增加一个原生扩展，就增加：

- OS × architecture × debug/release 二进制。
- Godot 版本兼容范围。
- 签名、公证、Android AAR/iOS framework 处理。
- Web 动态链接模板和跨源隔离。
- 崩溃、内存和线程安全验证。

因此 GDExtension 必须由测量结果驱动，而不是为了“模块化”提前引入。

### 9.6 可访问性和产品体验

现有 Creator Web 已使用 DOM、文本状态和响应式布局。Godot UI 需要重新证明：

- 键盘导航。
- 屏幕阅读器。
- 焦点顺序。
- 中英文输入。
- 高对比度和缩放。
- Pattern 的非视觉摘要。
- 上传、错误和进度信息的可读性。

如果这些不是 Godot Surface 的核心目标，应把它限定为 Performance Client，避免重复 Creator Web 的职责。

---

## 10. 推荐验证原型

### 10.1 原型目标

只验证一句话：

> **Godot 能否在不改变 LMDJ 公开合同的前提下，成为一个行为一致、延迟可接受、可跨桌面平台打包的 16-pad Patch 消费者？**

### 10.2 原型范围

1. 新建独立候选边界，例如 `apps/godot-client/`；开始前需产品/设计批准。
2. 只使用 GDScript 和内置模块。
3. 从固定 fixture ZIP 加载 `patch.json + samples`。
4. 实现最小 Patch Validator。
5. 显示恰好 16 个数据 Pad。
6. 加载 WAV 并支持 click / keyboard / MIDI input。
7. 播放 active LMDJ Scene 引用的 Pattern。
8. 实现 loop、mute、Empty、reserved no-op、missing sample warning 和 `full_mix_exclusive`。
9. 先验证 macOS；再验证 Windows；最后决定是否验证 Web。

### 10.3 验收门

| 门 | 通过条件 |
|---|---|
| Contract Gate | 同一 fixture 在 Web 与 Godot 得到相同的 16-pad、Scene/Pattern 和 warning 结果 |
| Behavior Gate | one-shot、loop、mute、Empty、reserved、exclusive group 与 Web 一致 |
| Timing Gate | Pattern loop、密集 Note、窗口失焦/恢复结果有可重复测量，并不劣于约定基线 |
| MIDI Gate | Note On、Note Off、velocity-zero Note On、断连/重连行为明确 |
| Runtime Asset Gate | WAV 动态加载、缺失/损坏素材、ZIP 路径安全和缓存边界通过 |
| Platform Gate | macOS 与 Windows 导出包在真实设备通过；Web 结果不得从桌面推断 |
| Footprint Gate | 记录包体、冷启动、峰值内存、首声时间和下载量 |
| Boundary Gate | 无 `materials.json`、timing artifact 或 Worker 内部数据泄露到客户端 |

### 10.4 原型后再做的选择

- 如果 GDScript 已满足时序和资源加载：不引入 GDExtension。
- 如果只有波形/FFT 性能不足：做单一职责 DSP Extension。
- 如果 Apple 专有能力有明确产品价值：做 Apple-only Provider，不改变公共合同。
- 如果 Godot Web 包体、可访问性或音频路径不达标：保留原生端，不强求 Web 共享。
- 如果桌面演奏价值不足：停止，不迁移现有 Creator Web。

---

## 11. 最终建议

### 11.1 推荐架构

```text
Authoritative LMDJ backend
  Audio Worker → Core Models / Patchify → lmdj.patch.v1 + samples
                                            ├─ React Creator Web
                                            ├─ CLI / Export
                                            └─ Optional Godot Performance Client
```

### 11.2 现在应保持不变

- `lmdj.patch.v1` 继续是唯一公共合同。
- Patchify 继续是纯服务端 adapter。
- Audio Worker 继续负责音频理解与 Material 生成。
- React Web 继续负责 Creator、上传、Job 恢复和 DOM 可访问性。
- Sampler Edit、Take Recording 和 Variation 继续经过产品设计与契约批准门。

### 11.3 值得进一步验证的唯一主线

> **把 Godot 作为可选的原生 Performance / Visual Client，用现有 Patch fixture 验证 16-pad、Pattern、MIDI、动态采样加载和桌面导出；首个原型不含 GDExtension、不改合同、不替换 Web。**

这条路径利用了 Godot 真正有优势的模块，同时把 LMDJ 已经建立的合同、Worker 和 Web 产品边界完整保留下来。

---

## 12. 主要源码与文档索引

### 12.1 Godot 固定源码

- [SConstruct：平台、模块、target、custom_modules、disable_3d](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/SConstruct)
- [methods.py：module discovery 与 dependency](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/methods.py)
- [OS abstraction](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/os/os.h)
- [DisplayServer](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/display/display_server.h)
- [AudioServer / AudioDriver](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/audio/audio_server.h)
- [MIDI Driver](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/os/midi_driver.h)
- [Web platform detect.py](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/platform/web/detect.py)
- [Web Audio Driver](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/platform/web/audio_driver_web.cpp)
- [WebMIDI bridge](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/platform/web/js/libs/library_godot_webmidi.js)
- [Interactive Music](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/interactive_music/audio_stream_interactive.h)
- [WAV runtime loading](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/scene/resources/audio_stream_wav.cpp)
- [MP3 runtime loading](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/mp3/audio_stream_mp3.cpp)
- [Ogg Vorbis runtime loading](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/vorbis/audio_stream_ogg_vorbis.cpp)
- [HTTPRequest](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/scene/main/http_request.cpp)
- [JSON](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/io/json.cpp)
- [ZIPReader](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/zip/zip_reader.cpp)
- [AudioEffectRecord](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/audio/effects/audio_effect_record.cpp)
- [AudioStreamGenerator](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/audio/effects/audio_stream_generator.cpp)
- [Spectrum Analyzer](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/servers/audio/effects/audio_effect_spectrum_analyzer.cpp)
- [GDExtension Loader compatibility](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/core/extension/gdextension_library_loader.cpp)
- [Editor export platform](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/editor/export/editor_export_platform.h)

### 12.2 Godot 官方文档

- [Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)
- [Compiling for the Web](https://docs.godotengine.org/en/stable/engine_details/development/compiling/compiling_for_web.html)
- [What is GDExtension?](https://docs.godotengine.org/en/latest/engine_details/engine_api/gdextension/what_is_gdextension.html)
- [The .gdextension file](https://docs.godotengine.org/en/latest/engine_details/engine_api/gdextension/gdextension_file.html)

### 12.3 LMDJ 当前依据

- [`packages/core-models/lmdj_core_models/model.py`](../../packages/core-models/lmdj_core_models/model.py)
- [`packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`](../../packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json)
- [`apps/web/src/patch/loader.ts`](../../apps/web/src/patch/loader.ts)
- [`apps/web/src/engine/AudioEngine.ts`](../../apps/web/src/engine/AudioEngine.ts)
- [`apps/web/src/engine/clock.ts`](../../apps/web/src/engine/clock.ts)
- [`apps/web/src/midi/MidiInput.ts`](../../apps/web/src/midi/MidiInput.ts)
- [`docs/prd/decision-log.md`](../prd/decision-log.md)
- [`docs/prd/open-questions.md`](../prd/open-questions.md)
