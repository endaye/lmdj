# 工程同步与协作格式调研：离线优先、云同步、面向未来协作

日期：2026-09-29（外部资料均于该日访问）

状态：**调研材料，不是决策。** 架构、冲突策略、协作模式等产品与 Contract 问题都没有在这里定下来；本文作为后续 Question Issue 与决策记录的输入。用户可见行为的阶段性结论见
[Creator 用户流程决策](../prd/decisions/2026-09-29-creator-user-workflow-baseline.md) 第 14、15 条。

外部引用只代表访问当日的公开文档内容；其中的版本、术语与产品行为不构成本仓库的版本或行为决定。

## 背景

LMDJ 工程包含 64 个 Pad Slot（4 Bank × 16，各引用一个音频 Asset 与播放参数）、最多 16 个 Pattern（1/2/4/8 小节，960 PPQ 事件引用 Pad Slot 而非 Asset）、tempo / swing / quantize、Sound Set 安装与 Perform 录音。Asset 是不可变大二进制（每工程准备后音频上限约 128 MiB）。现状单用户、仅本机（OPFS），以 `.lmdj` 包存储；Project Truth 是权威状态，Runtime Snapshot 是不持久化的派生状态。目标：离线必须可用；登录后自动保存并同步到云端；未来支持多人协作。

## 1. USD（Pixar Universal Scene Description）

- **Layer / SubLayer**：一个 Layer 是一个场景描述文件；subLayers 是最基础的组合弧，让不同部门或同部门的多位艺术家"各自在自己的 Layer 里工作"，再按强度顺序合成。根 Layer 最强。
  来源：<https://openusd.org/release/intro.html>，<https://openusd.org/release/glossary.html>
- **Opinion 与强度顺序**：写入的值称为 opinion；现行术语 LIVERPS（Local、Inherits、VariantSets、Relocates、References、Payload、Specializes），属性取最强 opinion。来源：glossary。
- **非破坏式覆盖**：强层可写 `over`；References、Inherits 等支持 list editing（prepend / append / delete）；删除 prim 可用 Active 元数据做成可逆删除。来源：glossary。
- **Payload**：延迟引用，可 Load / Unload，常用于隔离重型数据。来源：glossary。
- **多人实时协作不是 USD 本身提供的**：同一 Layer 的并发写入没有合并语义；NVIDIA Omniverse 另建 `.live` 层经 Nucleus 同步增量。来源：<https://docs.omniverse.nvidia.com/extensions/latest/ext_core/ext_live/faq.html>

对 LMDJ：

- 适合借鉴："稀疏覆盖层 + 确定强度顺序"（Sound Set 弱层 → 用户编辑强层 → 不持久化的会话层，与 Snapshot 不持久化一致）；Payload 对应音频按需加载；按职责分层可用于异步协作。
- 不适合：LIVERPS 对 LMDJ 的浅对象模型过于复杂；没有同层并发写的合并方案；"最强层获胜"是结构优先级，不能直接当多人冲突策略。

## 2. Figma multiplayer

- **服务器权威**：Figma 明确不是真正的 CRDT，中心化服务器是最终裁决者，借鉴 CRDT 思想；认为 OT 不必要地复杂。
  来源：<https://www.figma.com/blog/how-figmas-multiplayer-technology-works/>
- **数据模型**：`Map<ObjectID, Map<Property, Value>>`；新功能通常只是加属性。
- **按属性 last-writer-wins**：同一对象同一属性以服务器最后收到的为准，不同属性互不影响；客户端优先显示自己未确认的本地修改。
- **ID 与删除**：客户端 ID 编入对象 ID，离线创建不冲突；服务器不保留已删除对象的属性，恢复靠删除方的 undo 缓冲。
- **树**：父子关系是子节点的 parent 属性，服务器拒绝会成环的更新。
- **分数索引**：子节点位置是 (0,1) 内的分数，插入取中间值，同位置并发插入由服务器去重。来源：<https://www.figma.com/blog/realtime-editing-of-ordered-sequences/>
- **Undo 原则**：撤销多次、复制、再重做，文档不应改变；撤销修改 redo 历史，不覆盖别人的工作。
- **离线**：协议层可以离线任意长时间，重连时下载最新副本再重放离线编辑；产品层只有本次会话已加载的文件与页面可用。来源：<https://help.figma.com/hc/en-us/articles/360040328553-What-can-I-do-offline-in-Figma>
- **可靠性**：检查点之外的 write-ahead journal 约每 0.5 秒写一次，95% 的编辑在 600ms 内持久化。来源：<https://www.figma.com/blog/making-multiplayer-more-reliable/>
- **图片 / 大文件**：文档只存 `imageHash` / `imageRef`，实体另行托管，经有时效的 URL 下载。来源：<https://developers.figma.com/docs/plugins/api/Image>，<https://developers.figma.com/docs/rest-api/file-endpoints/>

## 3. Google Docs

- 文档是一份修订日志，显示时重放；并发用 OT，每对操作类型需要专门的变换规则。来源：<https://drive.googleblog.com/2010/09/whats-different-about-new-google-docs_22.html>
- 离线限制：仅 Chrome / Edge、非无痕、需扩展并在联网时启用；只缓存最近的部分文件；每个浏览器配置文件只能有一个账户离线；过大文件不能离线。来源：<https://support.google.com/docs/answer/6388102>
- 对 LMDJ：OT 适合线性文本；结构化对象与属性上成本高、收益低。

## 4. Local-first / CRDT 与音乐协作产品

- **Ink & Switch《Local-first software》**：七条理想（无等待、多设备、网络可选、无缝协作、长期可用、默认安全隐私、用户拥有数据）；承认 CRDT 保存全部历史带来性能与存储问题。来源：<https://www.inkandswitch.com/essay/local-first/>
- **Automerge**：同一 map 键的并发赋值按操作 ID（计数器 + actorId）确定性选出赢家，不看墙钟；败者值可用 `getConflicts()` 取回。来源：<https://automerge.org/docs/reference/documents/conflicts/>；存储与快照压缩：<https://automerge.org/docs/reference/under-the-hood/storage/>，<https://automerge.org/blog/automerge-repo/>。未找到官方的大二进制最佳实践（未找到 ≠ 不存在）。
- **Yjs**：Map 每个键取最后插入的条目，客户端有随机 53 位 clientID。来源：<https://github.com/yjs/yjs/blob/main/INTERNALS.md>。社区讨论称并发胜负由 clientID 次序决定、较晚的编辑可能输（来自论坛，实施前需核实）：<https://discuss.yjs.dev/t/y-map-conflict-resolution-which-side-wins/1952>
- **Ink & Switch Upwelling / Patchwork**：实时协作 + 私有草稿 + 显式合并，与 USD 分层概念接近；Patchwork 探索分支与历史视图。来源：<https://www.inkandswitch.com/upwelling/>，<https://www.inkandswitch.com/project/patchwork/>
- **Audiotool**：浏览器多人云 DAW；NEXUS 是基于 Protocol Buffers 的工程 API，SDK 以事务修改文档并在后台同步；冲突解决与采样引用方式未公开。来源：<https://developer.audiotool.com/js-package-documentation/documents/Getting_Started.html>，<https://www.gearnews.com/audiotool-studio-nexus-daw-tech/>
- **BandLab**：Live Session 实时协作（最多 50 人）与 fork 式异步协作。来源：<https://blog.bandlab.com/forking-and-collaboration-on-bandlab-explained/>，<https://www.audeobox.com/learn/bandlab/bandlab-collaboration-features/>
- **Soundtrap**：2022 年加入实时协作与自动保存。来源：<https://techcrunch.com/2022/08/09/spotifys-soundtrap-app-for-musicians-introduces-live-collaboration-and-auto-save/>
- BandLab 与 Soundtrap 的内部冲突机制均未公开。
- **Splice Studio**：DAW 工程备份、版本历史，无实时合并；2023 年关闭。来源：<https://www.musicradar.com/news/splice-studio-closing>，<https://cdm.link/splice-studio-is-free-backup-version-control-and-collaboration-for-your-daw/>
- **Koala Sampler**：协作方式是导出与分享 `.koala` 文件。来源：<https://manual.koalasampler.com/mobile/7-main-menu/>

## 5. 大二进制资源处理

- **Git LFS**：仓库只存 pointer（版本 + SHA-256 oid + size），实体按内容哈希另存。来源：<https://github.com/git-lfs/git-lfs/blob/main/docs/spec.md>
- **Figma**：文档只存内容哈希，实体经有时效 URL 懒下载。
- **USD**：Payload 延迟加载。
- **CRDT 库**：不适合直接装几十 MiB 音频（保留全部历史）。
- 共识：大文件不可变、按内容寻址（去重、不冲突）；文档只引用哈希；先上传 blob 再提交引用；按需或预取下载；GC 以任一保留版本可达为准。
- 与 LMDJ 契合：Asset 已按 `assets/<sha256>.wav` 命名（`packages/project-io/src/project_store.cpp:309`），Pattern 只引用 Pad Slot；并发冲突只会出现在 Pad Slot → Asset 哈希这一引用属性上。

## 6. 候选架构（供决策参考）

共同前提：Runtime Snapshot、Provider 选择与 Attempt 失败状态不进入同步；Asset 统一为内容寻址不可变 blob；本机 OPFS 为缓存、云端对象存储为权威副本；`.lmdj` 降级为导出与归档格式。

### A：Figma 式，服务器权威 + 按属性 LWW + 本地待发队列

Project Truth 表示为 `(ObjectID, Property) → Value`；客户端先写本机并入队，联网后由服务器定序、校验、广播，重连时拉最新状态再重放本地待发操作。

- 优点：最简单，有规模化先例；服务器可强制全局约束（预算、trim 合法性、配额与权限）；可从单用户自动保存平滑升级到实时多人。
- 缺点：离线编辑到回放时才知结果；同属性冲突无历史可查（除非另记）；需要自建同步服务。

### B：本地优先 CRDT（Automerge / Yjs），服务器只做中继与备份

- 优点：离线可无限期合并；Automerge 可暴露败者值；自带完整历史。
- 缺点：全局不变量无法由 CRDT 保证，需合并后校验修复；历史增长；Yjs 胜负不符合直觉；权限粒度粗；第三方库影响 Contract 版本化与 C++ / Wasm 跨语言一致性。

### C：USD / Upwelling 式分层——主线 Truth + 个人草稿层 + 显式合并

- 优点：最适合异步协作（fork、草稿）；冲突可见可审；离线即"在草稿里工作"；历史与回滚是一等公民。
- 缺点：需要合并 UI；无同屏即时体验（除非叠加 A）；多个草稿增加认知负担。

可行组合：A 负责单人多设备自动保存与未来实时协作，C 负责离线长分叉与异步协作；两者共用按属性寻址的 Truth 模型。

### 各对象的合并语义（通用）

| 对象 | 建议语义 | 注意 |
| --- | --- | --- |
| Pad Slot 参数 | 以 (bank, index, 属性) 为键逐属性 LWW | 固定 64 槽用自然键 |
| trim start / end | 成组作为一个值，或合并后校验 | 分别 LWW 可能得出 start ≥ end |
| Pad Slot → Asset 引用 | LWW，值为内容哈希 | 先传 blob 再提交；GC 以历史可达为准 |
| Pattern 事件 | 按事件 ID 的集合；属性逐项 LWW；顺序由 tick 推导 | 删除与编辑并发；同 tick 并发新增是否去重 |
| Pattern 长度 | LWW | 缩短后越界事件保留还是隐藏 |
| Pattern 槽位 | 固定 16 槽用槽位键；可重排列表用分数索引 | 上限 16 是全局约束 |
| tempo / swing / quantize | 单个 LWW | 演奏中远端修改何时生效 |
| Sound Set 安装 | 集合 add / remove，锁定内容哈希 | 卸载与引用并发 |
| Perform 录音 | 只追加、不可变 | 天然无冲突 |

## 7. 待决问题

2026-09-29 评审已确定用户可见的阶段性行为（决策第 14 条）。仍需决定：

1. 同步 Contract 的形态（A / C 的主次与组合）、ID 与 SemVer；`.lmdj` 降级后的 Bundle 版本。
2. 全局约束的执行位置：服务器强制，还是客户端合并后修复。
3. 权限模型：工程级或对象级。
4. Asset 生命周期：版本历史保留期、跨工程去重的隐私与配额口径、未登录用户 blob 登录后的迁移。
5. 撤销的持久化范围（跨会话、跨设备）。
6. 演奏中远端修改的生效时机（并发语义，须在决策记录中正式确定）。

信息缺口：BandLab、Soundtrap、Audiotool 的冲突机制无公开文档；Yjs 胜负规则来自社区论坛；Automerge 的大二进制官方建议未找到。
