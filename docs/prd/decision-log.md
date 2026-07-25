# 决策记录

这里记录已经确认的产品和技术决策。没有确认的内容不要写进这里，先放到 [open-questions.md](open-questions.md)。

## 2026-07-02

### 已确认：当前处于脑暴和 PRD 快速迭代阶段

- 结论：当前仓库先服务于素材整理、工作版 PRD、开放问题和决策记录。
- 原因：已有输入包括高嘉丰 PRD 素材和 demo 工具，但它们都不是最终版本。
- 影响：文档中需要明确区分“素材”“假设”“待决”“已确认”。

### 已确认：`lmdj-song-pipeline` 是高嘉丰 demo 工具

- 结论：`lmdj-song-pipeline` 是后续可参考、可复用的 demo 工具，不是 LMDJ 最终系统架构定稿。
- 原因：该工具能证明音频到 playable patch 包的技术链路，但产品系统仍在脑暴。
- 影响：后续 PRD 可以参考它的 package contract 和运行方式，但不默认继承全部设计。

## 2026-07-06

### 已确认：`lmdj-song-pipeline` 是参考项目，不是最终代码边界

- 结论：`lmdj-song-pipeline` 是高嘉丰提供的个人参考项目和可复用技术素材库；LMDJ 可以吸收其中的功能和代码，但最终云端系统、产品对象、服务边界和 package contract 需要按 LMDJ 自己的架构定义。
- 原因：当前产品方向已经从 demo pipeline 扩展为 AI-native sampler workstation，核心对象是 `Patch / Pad / Scene / Element`，不应被参考项目的目录结构、API、CLI 或状态模型锁死。
- 影响：后续技术方案需要区分“复用 pipeline 能力”和“继承系统架构”。`Patchify` 应作为参考 pipeline 输出到 LMDJ 产品对象之间的 adapter layer；正式实现不写入 `lmdj-song-pipeline`。

## 2026-07-07

### 已确认：Patchify 进入正式源码边界重新编写

- 结论：`references/demos/lmdj-song-pipeline/` 和 `references/demos/ascii-matrix-camera/` 都只作为参考 demo；Patchify 需要作为 LMDJ-owned code 在正式目录中重新编写，第一落点是 `packages/patchify/`。
- 原因：Patchify 是产品核心能力，需要服务 Web、CLI、Audio Worker、云端 API 和后续 community/lineage，不应被参考 demo 的 CLI、API、状态模型或目录结构锁定。
- 影响：新实现计划采用 Path B：先建立 `apps/`、`packages/`、`workers/` 边界，再实现独立 `packages/patchify`，只消费参考 pipeline 可能产出的 `samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`。

### 已确认：`patch.json` v1 携带 normalized patterns

- 结论：`patch.json` 增加 `patterns[]`，scene 通过 `pattern_ids` 引用；notes 为 `{element_id, lane, pitch, step, velocity}`；pattern 携带 `length_steps = beats × 4`（`beats` 取自 `lanes.json` 顶层，不用 `bpm × loop_seconds` 反推，也不用可能出现半小节小数的 `bars`）；v1 不带 note duration；`chart.mid` 保留为 pattern 的 source artifact，不进 `renders`。
- 原因：`patch.json` 是 Web/CLI/Worker/API 四方共同契约，不携带 notes 则消费方必须各自解析 MIDI，"可演奏"闭不了环。demo 的 duration 数据无音乐语义（鼓硬编码 0.1s 占位、长样本为样本文件全长，见 `sequencer.py`），velocity 恒为 100（写入 schema 文档注明）。
- 影响：Patchify loader 需解析 `chart.mid` 为 normalized note events；后续接非量化输入时再加 `start_beats`/`duration_beats`，避免 v1 复杂化。

### 已确认：`packages/core-models/` 即刻成立，patchify 为纯 adapter

- 结论：`Patch / Pattern / Pad / Scene / Element` 等产品对象 dataclass 与 `lmdj.patch.v1` 的 JSON Schema 文件都落在 `packages/core-models/`；`packages/patchify/` 只含 loader、mapper、orchestrator、CLI，依赖 core-models。
- 原因：schema 是四方契约，应放在产品对象包而非某个 adapter 里；云架构对 Patchify 的定位本就是 adapter layer。
- 影响：Path B 计划改为两个 package；TS 前端未来从 JSON Schema codegen 类型。

### 已确认：Patchify 输入契约以 demo 真实输出为准 + golden fixture 方法论

- 结论：`lanes.json` 每条 lane 的 wav 路径 key 是 `sample`（loader 兼容读 `path`，`sample` 优先；内部模型与输出统一为 `source_path`）；`song_id` 取自 `report.json`（`lanes.json` 里没有）。测试 happy path 必须使用真实 demo 输出提交为 golden fixture；错误路径 fixture 从 golden 复制后破坏单个字段，不得从零合成。
- 原因：原计划 fixture 凭想象使用 `path`/`song_id` 字段，与 `sequencer.py` 真实输出不符——TDD 全绿但真实数据直接 KeyError。
- 影响：通用规则——凡消费外部产物的 loader，happy-path fixture 必须取自真实产物。

### 已确认：pad 采用 trigger_group 语义，mapper 走 profile 检测

- 结论：element 槽位 pad 携带 `behavior.element_ids`（全组）+ `element_id`（primary）；组内多 element 时 action 为 `trigger_group`，单 element 为 `trigger_element`。mapper 入口先 `detect_profile()`，v1 只支持 standard profile，ABC/DEF（`loop_*`）包显式报 unsupported 而非静默产出空 pads。melody 第二候选 fallback 到 Lead/Vocal 槽位。未上 pad 的 elements 记入 `metadata.unmapped_element_ids`。占位 action（`scene_fill`/`scene_drop`/`mute_group`/`ai_variation`）进完整 enum 并标 reserved；消费方遇到 unknown/reserved action 必须渲染为禁用态/no-op，不得报错。
- 原因：snare/hat 等素材不可成为不可达孤儿；固定语义槽位不可名不副实；前向兼容规则让 v1 前端天然兼容后续 action 扩展，v2 启用时零迁移。
- 影响：schema 的 action 词表一次到位。

### 已确认：patch_id 内容派生，全局身份归平台层

- 结论：`patch_id = {song_id}-{sha256(lanes.json + chart.mid)[:8]}`；schema 文档注明其为内容派生的局部标识，全局唯一 ID 由 App Backend 入库时分配。
- 原因：deterministic mapping 约束与 worker 重试幂等都要求同输入产生同身份；随机 uuid 出局；单用 song_id 与云架构"一歌多 patch"方向冲突。
- 影响：任何一方不得以 patch_id 作数据库主键。

### 已确认：pitch/sample truth 三段式模型

- 结论：v1 内 `lanes.json`/`chart.mid` 是 Patchify 的输入 truth（demo 契约，已冻结）；`patch.json` 生成之后即产品侧唯一 truth，下游不得回读 lanes/chart；`workers/audio/` 正式实现时直接产出 LMDJ 中间格式，demo 契约 loader 转入维护模式。
- 原因：原架构原则"`lanes.json` 仍然是 pitch/sample truth"无限期锚定 demo 格式，与产品自主性冲突；patterns 决策已使下游无需回读。
- 影响：infra spec 关键架构原则同步改写；jobs 幂等（同输入 → 同 storage key，覆盖写安全）与 Postgres v1 收缩（不单独建 pads/scenes 表）一并修订进 infra spec。

## 2026-07-15

### 已确认：PipelineFromStemsRunner 独立 venv，DSP 栈不进 workers/audio 主包

- 结论：从参考 demo 迁移的 pipeline 阶段 3–6（beat/loop/slicer/sequencer/validation）代码落在 `workers/audio/lmdj_audio_worker/pipeline_from_stems/`，但运行在自己的专用 venv 中、以子进程调用；`workers/audio` 主包 `dependencies` 保持为空，只保留协议层。DSP 关键库版本以入库的 parity constraints 文件为单一来源，PipelineFromStems venv 和 parity 用的 demo baseline venv 都从它创建，运行前校验环境指纹。
- 原因：DSP 栈（librosa 含 numba、numpy<2）若进主包，会经 `apps/api` 的 path dep 传染进 API venv，破坏既有重依赖隔离决策；同版本锁定又是新旧 pipeline parity 数值容差（1e-4/1e-5）成立的前提，而 demo `pyproject.toml` 依赖多数未 pin，只锁新侧锚定的是机器本地产物、不可复现。
- 影响：与现有 `DemoPipelineRunner`、separator runner 统一为"子进程 + 独立 venv"模式；parity 只做同平台比较；详见多分轨 benchmark spec §3.1/§3.2（2026-07-15）。

### 已确认：Phase 2A 后生产链路统一走新链，DemoPipelineRunner 退役

- 结论：separator 生产接入（Phase 2A）后，产品 job 统一走 `separator runner 子进程 → PipelineFromStemsRunner 子进程 → Patchify`，包括选 Demucs 时也不再经过 demo 的 `song-pipeline` 整链；`DemoPipelineRunner` 保留到 Phase 2C 端到端验证通过后退役。
- 原因：双链路并存意味着 Demucs 与其他模型走不同代码路径，benchmark 结论对生产不成立；parity 门槛的存在正是为了让新链安全替换旧链。
- 影响：demo 从此只剩 fixture 与 parity 基线角色；CLAUDE.md/AGENTS.md 中"audio → demo pipeline subprocess"的链路描述在 Phase 2C 后需同步改写。

## 2026-07-16

### 已确认：SCNet-large 选 starrytong fixed checkpoint，MSST 以 pinned clone 方式复用

- 结论：SCNet-large 采用 MSST release v1.0.9 的 `SCNet-large_starrytong_fixed.ckpt`（starrytong 训练，MUSDB test SDR 9.70，优于 v1.0.8 的 9.32），config 同 release 入库 vendored；推理复用 MSST 框架的 `demix`，以 `config/msst.lock` pinned commit clone（gitignored），不 pip 安装、不修改其源码。代码与权重 license 均为 MIT。MPS 适配：inference.batch_size 由上游的 8 调为 1（chunk_size 不变），MPS 峰值设备内存 ~11.2GB、CPU 峰值 RSS 从 ~27.9GB 降至 ~5.2GB（代价 CPU 墙钟 ~1.5x）；调优字段与 config_sha256 已同步进 registry。
- 原因：MSST 不是 pip 包；pinned clone + lock 文件哈希进 registry `env_lock_sha256`，与 constraints 方案同构，满足 spec §6 可追溯门禁；两个候选 checkpoint 中选 SDR 更高且训练者可追溯的一个。
- 影响：升级 SCNet 推理代码 = 改 msst.lock 的 commit 并重跑 smoke 验收；registry 条目状态 experimental，双平台验证后方可升 verified（spec §6）。后续升级 upstream config 时必须重放该调优并重跑双设备 smoke。

### 已确认：RoFormer 四轨 checkpoint 选型与 MSST 家族共享实现

- 结论：BS-RoFormer 采用 MSST release v1.0.12 的 `model_bs_roformer_ep_17_sdr_9.6568.ckpt`（ZFTurbo 训练，MUSDB SDR 9.65，唯一过门禁的四轨候选）；Mel-Band RoFormer 采用 MSST release v1.0.11 的 ep_1（SDR 8.22，单文件）——同 release 的 ep_5（SDR 8.94）为 3.5GB 双分卷 zip，与单 artifact 缓存契约冲突，弃选并记录为升级路径（需先扩展 cache/registry 支持多分卷 artifact）；HF 社区 fine-tune 因训练过程可追溯性弱于 ZFTurbo release 一并弃选。三个 MSST 家族 runner（scnet/bs/mel）共享 `runners/_msst.py` 实现、同一 MSST pinned clone 与同一 constraints 文件，但按 spec §5 字面各自独立 venv 运行。
- 原因：spec §6 对 RoFormer 门禁最严（来源/revision/四轨/许可缺一不可）；社区单目标权重不得伪装四轨。benchmark 公平性让位于基建契约完整性，ep_5 升级路径显式保留。
- 影响：mel-band 家族在 Phase 1D benchmark 中以 ep_1（非家族最强形态）参赛，解读结果时需注明 ~0.7dB 的形态差；若家族展现潜力，升级 ep_5 是独立的基建扩展 + 重验收。验收补充：两个 roformer 在 MPS 首跑即通过（bs 74.3s / mel 54.1s），无需 batch 调优；真实推理暴露 MSST roformer 运行时依赖（beartype/rotary_embedding_torch/librosa）缺 pin，已补进 constraints 并加漂移守护测试——constraints 文件未进 registry env_lock 是已知缺口，注册表字段级修复列入 Phase 1C backlog。

### 已确认：SI-SDR 自实现、指标归一化与盲听协议（Phase 1C-b）

- 结论：SI-SDR 采用 numpy 自实现（Le Roux 2019 标准公式），全曲整段、逐声道独立计算后均值；弃用 `fast_bss_eval`（0.1.4 版本在无 torch 环境下 si_sdr 计算损坏，已验证复现）。consistency（混合音 L2 范数守恒）与 leakage（stem 频段隔离度）采用自定义指标，精确定义见 plan 2026-07-16-separation-phase1c-metrics.md"自定义指标的精确定义"节。综合分归一化采用同 run 内 min-max 缩放（避免跨 run 之间设备/样本差异导致排序颠覆），得分缺失（盲听项）统一标注为"退化"，盲听按 0–10 线性折算（90 分制数据汇聚）。盲听评测包采用匿名目录（stem 顺序随机化、模型映射隐藏）。
- 原因：museval 外壳重且依赖重（scipy/numba），benchmark 主进程保持轻量需要子进程评分；si_sdr 标准实现在小模型权重配置下数值稳定性远优于 fast_bss_eval；一致性与泄漏是 Patch 可玩性的关键因子，论文 SDR 不能直接度量；综合分一旦跨 run 排序就无法对标固定架构，同 run 内排序足以驱动模型选型（MUSDB 固定 + 真实歌曲重复跑 3 遍）。
- 影响：SI-SDR 计算纳入 workers/audio/benchmark/metrics/ 实现；consistency/leakage 指标的定义与验证可追溯至 plan 文档；blind-listening/ 目录生成器加 stem 随机化与 salt 混淆；报告生成时的缺失项处理与盲听三评者聚合需防范极端样本（可玩性 1 分否决）。

## 2026-07-24

### 已确认：Stage 1 Creator Core 成为当前产品主线

- 结论：2026-07-18 的 `LMDJ Software MVP Stage 1–4 Memo` 是当前 `approved-for-planning` 路线图依据。下一条产品纵向切片是 `Upload → Make It Playable → Play → Creator Export Pack`。
- 原因：仓库已经跑通 Upload → Patchify → 8-pad Play，但尚未证明创作者能用通用 MIDI 演奏并把完整素材包带入真实 DAW。
- 影响：Separator benchmark、Timing、Generation 和 Agent Orchestration 保留各自价值，但不能替代或阻塞这条 Creator 闭环。

### 已确认：首条切片固定 16 个数据 Pad，UI 与数据一一对应

- 结论：`patch.json` 固定描述索引 `0..15` 的 16 个 Pad；Web 与数据一一对应，`>=960px` 使用 8 列 × 2 行，`360–959px` 使用 4×4，不创建 view-only 空槽。未分配素材的位置也是使用 `action: "empty"` 的真实 Pad。
- 原因：数据、Scene、输入映射和 UI 必须共享同一组稳定索引；由消费者自行补槽会形成两套产品事实，并让 16 位界面与 Patch 契约失配。
- 影响：在首条切片内原子收紧 `lmdj.patch.v1` 的 `pads` 约束为恰好 16 项，同步 Patchify、Web、Schema 副本、生成类型、fixtures 和测试；UI 布局、视觉、状态与响应式直接采用 Creator Workspace UI Design Spec，文案使用“16 个 Pad Slot”，同时明确 empty Pad 没有可播放素材。

### 已确认：Creator Export 首期使用通用 ZIP，以 Ableton Live 做 Smoke Test

- 结论：首期导出为包含 Patch、Stems、Samples/Slices、MIDI 和 BPM/Key/Loop Manifest 的通用 ZIP；不生成 `.als`、Logic 或 FL Studio 专有工程文件。第一目标 DAW 是 Ableton Live。
- 原因：开放文件包能验证“继续制作”，又不会把首条切片变成私有 DAW 工程格式兼容项目。
- 影响：导出完整性必须结构化验证；缺失必需项时不得把不完整 ZIP 标成成功。

### 已确认：通用 MIDI Pad 是首条切片的验收项

- 结论：Web MIDI 输入必须进入首条切片；键盘和鼠标是备用输入，不能代替实体 MIDI Pad 验收。
- 原因：Creator Core 和后续 Hardware Proof 都要求核心演奏从鼠标键盘解耦。
- 影响：16-pad Controller 可直接映射 `0..15`；8-pad Controller 必须通过 Bank A/B 覆盖 `0..7` 和 `8..15`，不能只访问前八个位置。

### 已确认：Prompt、AI Variation、Sampler Edit 和 Take 不进入首条切片

- 结论：Prompt/Voice、Agent Orchestration、AI Replace/Variation、Sampler Edit、Take Recording、Asset Library 都后置。
- 原因：首条切片必须在一条可运行流程内优先证明 Upload、演奏和 DAW Export；同时引入这些能力会破坏一周纵向切片边界。
- 影响：Sampler Edit + Take 是紧随其后的 Stage 1 切片；Generation 在 Creator 基础闭环成立后接入同一个 Patch Engine。

## 2026-07-25

### 已确认：Creator repeatability 以 source identity 与内容后缀建立，而非 Job identity

- 结论：API Job ID 仅标识一次运行；Worker 从上传音频字节计算 SHA-256，并以 `source-<full-hex-digest>` 作为 pipeline `song_id` 和 package identity；`patch_id` 继续使用该 source identity 加 `lanes.json + chart.mid` 的内容 hash 后缀。Worker-owned bootstrap 在 demo venv child 导入 Demucs 前，以音频字节的 SHA-256 seed Python `random`；seed 随子进程退出，不修改冻结 demo。
- 原因：随机 Job ID 进入 `song_id` 会让相同输入跨 Job 必然改变 patch identity；未设 seed 的 Demucs Python random shift offset 也会使同一音频的 pipeline 输出漂移。
- 影响：同一固定音频在生产 FastAPI 路径的三个独立 Job 已验证 full `patch_id`、`lanes.json`、`chart.mid`、`patch.json` 和 stems hash 一致；这只证明当前确定性 pipeline 的 repeatability，不替代实体 MIDI、Ableton Live 或无指导用户验收。

## 2026-07-26

### 已确认：Material Package 是内部契约，Patch 继续是产品真相

- 结论：在规范四轨 Separator 与 Patchify 之间增加
  `lmdj.materials.v1`；它由 `packages/core-models` 托管模型、Schema 与一致性
  约束，只供 Audio Worker 写入、Patchify 读取。Web/API 不读取或公开
  `materials.json`，继续只消费 `lmdj.patch.v1` 和结构化 Export Source。
- 原因：16 Pad 真正可演奏需要在 Owned Product Boundary 内表达来源、
  Timing、质量、A/B 差异和空槽决策；但把中间分析格式暴露给消费者会重新制造
  多套产品真相。
- 影响：Material loader 按固定 `slot_index` 直接映射，不从文件名或 MIDI
  猜角色；旧 `lanes.json + chart.mid` loader 只服务显式 legacy 路径。

### 已确认：16 个 Material 槽固定角色，质量优先于填满

- 结论：槽位 `0..7` 为
  Kick/Snare/Hat/Percussion/Bass/Melody/Vocal/Phrase A，`8..15` 为同角色
  B。B 必须引用同角色 A；未过门槛的位置保留真实 Empty；Phrase 来自原始 Mix
  并使用 `full_mix_exclusive`。
- 原因：固定位置保持键盘/MIDI 肌肉记忆，显式 Empty 比用劣质素材填满或动态
  前移更真实。Vocal 必须保持独立，不能回并到 Melody。
- 影响：少于 6 个素材、没有 Vocal 或没有 B 不触发 review；零 accepted
  Material 才是失败。Web 实现普通素材与 Phrase 的双向排他播放。

### 已确认：Material pipeline 显式选择，默认晋升另设发布门槛

- 结论：新 Job 通过 `LMDJ_PIPELINE=legacy|materials-v1` 选择 Runner；默认
  继续为 `legacy`。选择在 API/Executor 建立时冻结，新链失败不得在同一个 Job
  内静默调用 legacy。
- 原因：可观测失败与可重复身份优先于表面成功；静默回退会让 Job 产物和质量
  无法解释。
- 影响：实现与自动化测试完成不等于生产默认晋升。固定曲库三次重复、盲听、
  实体 8-Pad/16-Pad、Creator Export 与 Ableton Live Smoke 全部通过后，另行
  提交默认值变更。
