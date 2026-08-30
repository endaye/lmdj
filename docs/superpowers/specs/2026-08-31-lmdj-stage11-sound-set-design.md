# LMDJ Stage 11 Sound Set Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是 [#464](https://github.com/endaye/lmdj/issues/464)
的设计半部：定义 Sound Set v1 的包身份、Catalog 边界、安装事务与派生规则。
逐 Task 实施计划按 #464 的验收另行落笔，不在本文。S11-Q1–Q3 绑定
[#465](https://github.com/endaye/lmdj/issues/465)，本文只锁机制与字段承载位，
不裁决权利与映射策略；决策文件合入后回填绑定表。

关联 Issue：[#470](https://github.com/endaye/lmdj/issues/470)（umbrella）、
[#464](https://github.com/endaye/lmdj/issues/464)、
[#465](https://github.com/endaye/lmdj/issues/465)、
[#347](https://github.com/endaye/lmdj/issues/347)、
[#341](https://github.com/endaye/lmdj/issues/341)。

## 1. 结论

Stage 11 让用户不必先录音或导入也能开始演奏：从 Catalog 试听并下载不可变的
16-Pad Bank Package，安装进自选的目标 Bank，然后照常裁剪、调参、录 Pattern、
演出。Sound Set 是素材来源，不是新的 Pad 类型（规格 §5.1）；安装完成后
Project 里只有普通 Asset 与普通 Pad assignment，加上指回 Set 身份的 Lineage。

Stage 11 的成功命题是：

> 用户可以在不绕过 Application Facade、不产生第二种 Pad/Asset 模型、不改动
> 原始 Set 一个字节的前提下，把一个下载的 Sound Set 装进自选 Bank，立刻演奏，
> 并把自己的修改当作普通 Derived Asset 继续演化。

新内核规格 §5.4 是范围权威：整套与单个音色试听；role/BPM/Key/License/Version
元数据；用户选择目标 Bank；原始 Set 不可变；用户修改产生 Derived Asset；
首版只做 Catalog，不做 Marketplace。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 规格 §5.1 | 单一 Pad 模型；Sound Set 只是 Asset 来源之一，不产生新 Pad 类型。 |
| 规格 §5.2 / §5.3 | 派生规则与复制独立编辑；原始素材必须保留，派生结果记录 Lineage。 |
| S8-D6 | 输入只接受 PCM16 WAV、mono/stereo、44.1/48 kHz；Core 确定性准备 48 kHz Runtime PCM。 |
| S8-D2 | 播放参数属于 Pad Slot，不属于 Asset。 |
| 2026-08-26 D1 + 2026-08-28 记账修正案 | `maximum_user_bank_bytes` / `maximum_generation_bytes` / `maximum_resident_bytes` 三个命名量；选区/导入 commit 走同一路径，配额拒绝返回 `BANK_QUOTA_EXHAUSTED` 且不改变 Project、Asset、Pad 与 revision。 |
| 2026-08-26 D2 | time-stretch / pitch 永不进实时引擎；采样本身无 BPM 语义，全局 BPM 只驱动 sequencer。 |
| CLAUDE.md 不变量 | Host 只用 Facade；Provider 选择与外部端点属 Workspace/Host settings，不进 Project Truth；Pattern 事件引用 Pad Slot。 |
| 2026-08-29 Stage 10 计划锁定 | `lmdj.project.v4` 只新增 `performances`；Sound Set 相关 Project Truth 字段必须走 v4 之后的 Project Contract 版本。 |

## 3. 开放问题绑定

| ID | 问题 | 归属 | 本文的承载位 |
| --- | --- | --- | --- |
| S11-Q1 | 权利与 License 溯源：哪些字段是权威、缺失/矛盾/吊销时 listing/preview/download/install 各自在哪一步 fail closed。 | #465 | S11-D2 的 `license` 块与 S11-D10 的 `SOUNDSET_LICENSE_*` 错误族预留承载位；字段清单与判定边界待决策。 |
| S11-Q2 | 确定性映射：把 Set 套用到已有 Pattern 时 role/BPM/Key/音域映射的权威输入、占用槽冲突与空槽行为、何时必须显式用户选择。 | #465 | S11-D11 锁机制框架（映射是纯函数、冲突必须显式确认、Pattern 事件引用不被静默改写）；映射表本身待决策。 |
| S11-Q3 | 映射若要求安装或套用时改变素材时长（BPM 对齐），离线 time-stretch 是否成为 Stage 11 前置。 | #465 → #347 | S11-D11 显式排除 v1 安装路径做任何 DSP；若决策要求，#347 从 Later 升级。 |

`docs/prd/questions/curated-packs-content-rights.md` 与
`docs/prd/questions/empty-pad-fill-strategy.md` 的迁移/裁决属于 #465 的
决策 Task，本文不改动这两个文件。

## 4. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S11-D1 | Sound Set 的身份是 `set_id`（UUID）+ SemVer `version` + 规范化 manifest 的 SHA-256。同一 `(set_id, version)` 永远指向同一 manifest 哈希；任何内容变更都是新 `version`。不存在就地更新。 | 规格 §5.4「原始 Set 不可变」 |
| S11-D2 | 新 Contract `lmdj.soundset.v1`（`contracts/soundset/`，Contract SemVer 独立）。manifest 声明：Set 身份、`name`、`publisher`、可选 `description`、可选 set 级 `bpm`/`key`、`license` 块（字段清单待 S11-Q1）、恰好 16 个 `slots`。每个 slot 是 `occupied`（引用一个 Artifact：sha256 + media_type + byte_length，外加 `role`、`name`、可选 `bpm`/`key`）或 `empty`。允许空槽：Set 作者的留白是内容的一部分。 | 规格 §5.4、§17.4 Artifact Ref 惯例 |
| S11-D3 | Set 内音频 Artifact 复用 S8-D6 约束：PCM16 WAV、mono/stereo、44.1/48 kHz。不为 Sound Set 引入新格式；压缩分发格式是具名后续能力，届时也在下载层解包为 WAV 后走同一校验。 | S8-D6 |
| S11-D4 | Role 词表 v1 钉死为封闭枚举：`kick`、`snare`、`clap`、`hat_closed`、`hat_open`、`perc`、`cymbal`、`bass`、`melody`、`chord`、`vocal`、`fx`、`other`。manifest 中 role 必填；未知值是校验错误，不是自由文本。词表扩展走 Contract SemVer。 | S11-Q2 的映射需要确定性输入 |
| S11-D5 | 试听分两层：set 级可选 `demo` Artifact（同 S8-D6 约束的一段演示混音）；单音色试听直接以该 slot 的 Artifact 字节经普通 Runtime 试听路径播放。不建第二套预览引擎，不做低码率预览变体。试听不产生 Project 变更。 | 规格 §5.4「整套与单个音色试听」 |
| S11-D6 | Catalog 是新 Contract `lmdj.soundset-catalog.v1`：一份可缓存的只读索引，条目 = Set 身份 + manifest 哈希 + 下载体积 + 元数据摘要 + License 摘要。Catalog 端点与本地缓存归 Workspace/Host settings，永不进 Project Truth（与 Provider 选择同一不变量）。v1 允许「本地目录也是合法 Catalog 源」，网络只是传输方式之一。 | CLAUDE.md 不变量类比 |
| S11-D7 | 下载与完整性：所有字节按 content-address 获取；manifest 哈希先验证，再逐 Artifact 验证 sha256 + byte_length；任何不匹配 fail closed，缓存中的半成品不可见。已验证的 Set 进 Host 层只读 Set Store（Workspace 下），与 Project bundle 无关。Catalog 不可达是非致命：已缓存 Set 照常可用。 | §17.4、规格 §18.1 Storage 惯例 |
| S11-D8 | 安装是一个原子 Facade Command（`InstallSoundSet`，带 `expected_revision`）：用户显式选择目标 Bank；命令把 occupied slots 的 Artifact 经既有导入 commit 路径物化为普通 Project Asset 并完成 Pad assignment，一次 revision 完成。配额按整个 Set 的字节和在任何变更前判定，超限返回 `BANK_QUOTA_EXHAUSTED` 且零变更。目标 Bank 有占用 Pad 时的行为（覆盖需确认/合并/拒绝）待 S11-Q2 裁决，机制上冲突必须显式用户确认，永不静默覆盖。 | 规格 §5.2「不得自动覆盖 Bank」、D1 配额 |
| S11-D9 | 安装产生的每个 Asset 记 Lineage：`{set_id, set_version, slot_index, artifact_sha256}`，复用 #471 的通用 Lineage 记录（`derivation.kind = soundset_install`），不为 Sound Set 发明第二套。之后的裁剪/复制/再派生是普通 §5.2 流程；原始 Set Store 内容永不因用户编辑改变。 | 规格 §5.4、#471 |
| S11-D10 | 错误词表（`lmdj.error.v1` 惯例，全大写 token）：`SOUNDSET_MANIFEST_INVALID`、`SOUNDSET_HASH_MISMATCH`、`SOUNDSET_UNSUPPORTED_AUDIO`、`SOUNDSET_SLOT_INVALID`、`SOUNDSET_LICENSE_INCOMPLETE`（判定字段待 S11-Q1）、`CATALOG_UNAVAILABLE`、`BANK_QUOTA_EXHAUSTED`（复用）。所有安装期错误保证 Project、Asset、Pad 与 revision 不变。 | 规格 §18.1 |
| S11-D11 | 把 Set 套用到已有 Pattern（regenerate 声音而保留演奏）在机制上是：一个纯函数 `map(set manifest, 当前 Bank 状态) → {slot 替换清单}`，输出先预览、经用户确认后按 S11-D8 同一原子路径 commit。映射函数的输入只有已声明的 manifest 元数据与 Project 状态，无网络、无 AI 依赖；映射表与冲突策略待 S11-Q2。v1 安装与套用路径不做任何 time-stretch/pitch DSP（S11-Q3）。 | 规格 §5.4、2026-08-26 D2 |
| S11-D12 | Pattern 事件引用 Pad Slot（规格 §6.6），因此安装/套用改变的是「槽位发出什么声音」，不触碰 Pattern 事件本身；被 Set 置空的槽位使已有事件落空静默（非致命），与 P10-D10 的空槽惯例一致。 | 规格 §6.6、P10-D10 |

## 5. 身份与数据

`lmdj.soundset.v1` manifest（示意，字段以 Contract Schema 为准）：

```json
{
  "contract": "lmdj.soundset.v1",
  "set_id": "uuid",
  "version": "1.0.0",
  "name": "…", "publisher": "…",
  "bpm": 120, "key": "Am",
  "license": { "…": "字段清单待 #465" },
  "demo": { "sha256": "…", "media_type": "audio/wav", "byte_length": 0 },
  "slots": [
    { "slot": 0, "role": "kick", "name": "…",
      "artifact": { "sha256": "…", "media_type": "audio/wav", "byte_length": 0 } },
    { "slot": 1, "empty": true }
  ]
}
```

`lmdj.soundset-catalog.v1` 条目 = `{set_id, version, manifest_sha256,
total_bytes, name, publisher, roles_summary, bpm?, key?, license_summary}`。

Host 层状态（永不进 Project Truth）：Catalog 端点、Catalog 缓存、只读
Set Store。Project Truth 新增的只有普通 Asset + #471 Lineage 记录（其
Project 持久化位置随 #471/#431 对齐，串行在 v4 之后）。

## 6. Contract 影响

- 新增：`lmdj.soundset.v1`、`lmdj.soundset-catalog.v1`（独立 Contract SemVer）。
- 不改：`lmdj.capability.v2`、`lmdj.project.v4`（安装用既有 Asset/assignment
  语义即可表达；Lineage 的 Project 字段归 #471 的后续 Project 版本）。
- 复用：`lmdj.error.v1` 错误惯例、Artifact Ref 三元组。

## 7. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. manifest 校验：合法/16 槽不足或超出/未知 role/坏哈希/坏 media_type/
   License 块缺失（按 #465 裁决展开）逐条拒绝。
2. 完整性：篡改任一 Artifact 字节 → `SOUNDSET_HASH_MISMATCH`，缓存不可见。
3. 安装原子性：配额超限、目标 Bank 冲突未确认、中途失败均零变更；成功恰好
   一次 revision，Lineage 齐全。
4. 不可变性：安装后编辑 Pad 产生 Derived Asset，Set Store 字节不变。
5. 套用映射：同输入同输出的纯函数性；冲突必须显式确认；置空槽事件落空静默。
6. Catalog：不可达非致命；缓存 Set 可试听可安装。

## 8. Version Management

Version impact: none——本文只是设计文档，不分配任何 Product、Module、Host、
Provider、Contract、Assembly 或 Channel 身份。实施计划必须分配：两个新
Contract 的初始版本、`application-facade` 与承载 Catalog/Set Store 的
Host 模块的 SemVer 影响、以及与 Stage 10 Task 10（#436）串行的 Product
Build 整合。

## 9. Documentation Impact

Documentation impact: required——本文自身是新增的 retained 设计文档；
实施时受影响的 Portal 路由（Contracts、Facade、Host 存储）由实施计划
按 manifest 派生声明，本文不改当前 Portal 真相。

## 10. 拒绝的替代

### 10.1 可变的就地 Set 更新

拒绝。破坏「原始 Set 不可变」，且使 Lineage 的 `(set_id, version)` 失去
指称能力。更新永远是新 version。

### 10.2 自动装进「下一个空 Bank」

拒绝。目标 Bank 是用户选择（规格 §5.4），自动选择违反 §5.2 的不覆盖原则
且跨 Host 不可复现。

### 10.3 Sound Set 成为新的 Pad/Asset 类型

拒绝。规格 §5.1 单一 Pad 模型；来源差异只体现在 Lineage。

### 10.4 Catalog 端点写进 Project Truth

拒绝。与 Provider 选择同理，属 Workspace/Host settings；Project 换机器
打开不得依赖网络端点。

### 10.5 低码率预览变体 / 第二套预览引擎

拒绝 v1。双倍资产与第二条播放路径；短素材直接播 Artifact 即可，长 demo
是单个可选 Artifact。

### 10.6 安装时 BPM 对齐 time-stretch

拒绝 v1（S11-Q3 承载）。2026-08-26 D2 已定采样无 BPM 语义；离线 stretch
是 #347 的具名能力，是否成为 Stage 11 前置由 #465 裁决。

## 11. 实施入口（前置条件）

1. #465 决策文件合入（S11-Q1/Q2/Q3 裁决），本文回填绑定表并按需勘误。
2. #471 的 Lineage 通用记录定稿（S11-D9 依赖其 `derivation.kind` 词表）。
3. 本文评审通过后，按 #464 验收落笔逐 Task 实施计划（含 Version
   Management 与 Documentation impact 逐 Task 声明）。
4. Project/Facade/Creator 实施与 Product 身份整合串行在 Stage 10 v4
   （#427）与 Task 10（#436）之后。
