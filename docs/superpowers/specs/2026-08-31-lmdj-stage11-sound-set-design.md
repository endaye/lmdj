# LMDJ Stage 11 Sound Set Design — 2026-08-31

日期：2026-08-31

状态：**草案，待评审**——本文是 [#464](https://github.com/endaye/lmdj/issues/464)
的设计半部：定义 Sound Set v1 的包身份、Catalog 边界、安装事务与派生规则。
逐 Task 实施计划按 #464 的验收另行落笔，不在本文。S11-Q1–Q3 已由
[#465](https://github.com/endaye/lmdj/issues/465) 的决策
[`2026-09-06-sound-set-rights-and-mapping.md`](../../prd/decisions/2026-09-06-sound-set-rights-and-mapping.md)
裁决；本节绑定表与 S11-D2 / D8 / D10–D12 按该决策回填。

评审修正（2026-08-31）：补齐 canonical manifest 与 content-addressed blobs
构成的逻辑包边界；明确 v1 不接收 archive；把公开错误收敛到现有
`lmdj.error.v1` code + `details.reason`；并把 Sound Set 来源纳入 #471 的
typed Lineage source，避免只记录 `kind` 而丢失 Set 身份。

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
| S11-Q1 | 权利与 License 溯源：哪些字段是权威、缺失/矛盾/吊销时 listing/preview/download/install 各自在哪一步 fail closed。 | #465 已裁决 | S11-D2 的 `license` 四键（`spdx_id`、`rights_holder`、`copyright`、`attribution`）；v1 允许清单 `CC0-1.0` / `CC-BY-4.0`；listing/preview/download/install 同一资格；无在线吊销。Schema 失败走 `soundset_manifest_invalid`，资格失败走 `soundset_license_ineligible`。 |
| S11-Q2 | 确定性映射：把 Set 套用到已有 Pattern 时 role/BPM/Key/音域映射的权威输入、占用槽冲突与空槽行为、何时必须显式用户选择。 | #465 已裁决 | S11-D11 的纯函数；v1 映射表是槽位下标恒等。冲突必须带 `occupied_pad_policy`=`keep`\|`replace`，否则 `soundset_occupied_conflict`。empty Set slot 不写入、不清空目标 Pad。Pattern 事件引用不改写。 |
| S11-Q3 | 映射若要求安装或套用时改变素材时长（BPM 对齐），离线 time-stretch 是否成为 Stage 11 前置。 | #465 已裁决 | S11-D11 排除 v1 安装/套用路径任何 DSP；#347 保持 Later，不升为 Stage 11 前置。 |

`docs/prd/questions/curated-packs-content-rights.md` 与
`docs/prd/questions/empty-pad-fill-strategy.md` 已在 #465 的决策 Task 删除。

## 4. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S11-D1 | Sound Set 的身份是 `set_id`（UUID）+ SemVer `version` + canonical manifest 的 SHA-256。接收端先要求原始 object 是无 BOM 的有效 UTF-8 bounded JSON、通过 `lmdj.soundset.v1` Schema，再生成 `foundation::canonical_json(parsed_manifest)`；canonical bytes 精确定义为该 UTF-8 输出、无尾随换行。原始 object 必须与 canonical bytes byte-for-byte 相等（因此重复 key、非规范 key 顺序/空白/数字表示均拒绝），哈希覆盖这组 bytes。同一 `(set_id, version)` 永远指向同一 manifest 哈希；任何 manifest 或被引用内容变更都是新 `version`。不存在就地更新。 | 规格 §5.4「原始 Set 不可变」与仓库既有 bounded parse/canonical JSON 实现 |
| S11-D2 | 新 Contract `lmdj.soundset.v1`（`contracts/soundset/`，Contract SemVer 独立）。manifest 声明：Set 身份、`name`、`publisher`、可选 `description`、可选 set 级 `bpm`/`key`、`license` 块（四键全必填：`spdx_id`、`rights_holder`、`copyright`、`attribution`；v1 `spdx_id` 允许清单为 `CC0-1.0`、`CC-BY-4.0`，见 #465）、恰好 16 个 `slots`。每个 slot 是 `occupied`（引用一个 Artifact：sha256 + media_type + byte_length，外加 `role`、`name`、可选 `bpm`/`key`）或 `empty`。允许空槽：Set 作者的留白是内容的一部分，安装时不写入对应目标 Pad。 | 规格 §5.4、§17.4 Artifact Ref 惯例、#465 |
| S11-D3 | Set 内音频 Artifact 复用 S8-D6 约束：PCM16 WAV、mono/stereo、44.1/48 kHz。不为 Sound Set 引入新格式；压缩分发格式是具名后续能力，届时也在下载层解包为 WAV 后走同一校验。 | S8-D6 |
| S11-D4 | Role 词表 v1 钉死为封闭枚举：`kick`、`snare`、`clap`、`hat_closed`、`hat_open`、`perc`、`cymbal`、`bass`、`melody`、`chord`、`vocal`、`fx`、`other`。manifest 中 role 必填；未知值是校验错误，不是自由文本。词表扩展走 Contract SemVer。 | S11-Q2 的映射需要确定性输入 |
| S11-D5 | 试听分两层：set 级可选 `demo` Artifact（同 S8-D6 约束的一段演示混音）；单音色试听直接以该 slot 的 Artifact 字节经普通 Runtime 试听路径播放。不建第二套预览引擎，不做低码率预览变体。试听不产生 Project 变更。 | 规格 §5.4「整套与单个音色试听」 |
| S11-D6 | Catalog 是新 Contract `lmdj.soundset-catalog.v1`：一份可缓存的只读索引，条目 = Set 身份 + manifest 哈希 + **去重后**下载体积 + 元数据摘要 + License 摘要。Sound Set v1 是逻辑包，不是 archive：一个 canonical manifest object 加其引用的 content-addressed Artifact blobs。Catalog transport 只提供按 `{object_kind, sha256}` 解析 immutable object 的能力；网络端点与本地目录只是两种 adapter。本地 adapter 把已验证的 lowercase sha256 映射为配置根下的单个 basename（调用方不能提供 `/`、`..` 或路径），root-relative open 禁止跟随 symlink，打开后 fstat 必须为 regular file，再做有界读取与 hash 校验。Catalog 配置与缓存归 Workspace/Host settings，永不进 Project Truth。 | CLAUDE.md 不变量类比；避免 archive/路径权限 |
| S11-D7 | 下载与完整性：先按 catalog 声明读取 manifest object，依 S11-D1 完成 bounded parse、Schema、canonical byte equality 与 manifest sha256 验证，再由已验证 manifest 枚举 blobs；每个 blob 在发布到 Set Store 前验证 sha256 + byte_length。相同 Artifact hash 可被多个 slot/demo 复用，只下载/计费一次；`total_bytes` 是 canonical manifest bytes 加唯一 blob byte_length 之和，并必须等于 catalog 声明。Host manifest 必须提供 `maximum_soundset_manifest_bytes`、`maximum_soundset_blob_bytes`、`maximum_soundset_unique_bytes`、`maximum_soundset_staging_bytes`；在分配或下载前同时对单对象、单 Set unique bytes 与当前 staging 总量 fail closed。任何不匹配或超限都使 staging 整体不可见。已验证 Set 原子发布到 Workspace 下只读 Set Store，与 Project bundle 无关。Catalog 不可达是非致命：已缓存 Set 照常可用。 | §17.4、规格 §18.1 Storage 惯例 |
| S11-D8 | 安装是一个原子 Facade Command（`InstallSoundSet`，带 `expected_revision`）：用户显式选择目标 Bank；命令把 occupied slots 的 Artifact 经既有导入 commit 路径物化为普通 Project Asset 并完成 Pad assignment，一次 revision 完成。下载侧 S11-D7 的 unique blob 计量不得复用为 prepared quota：命令按最终每个 Pad 的 decoded float PCM bytes 预演目标 Bank 与整个 generation ledger，同一 Artifact 若占两个 Pad 就按两份 residency 计；在任何变更前分别对 `maximum_user_bank_bytes` / `maximum_generation_bytes` 判定，按既有 binding-constraint 规则返回 `BANK_QUOTA_EXHAUSTED` 或 `PROJECT_QUOTA_EXHAUSTED`，且零变更。映射是槽位下标恒等；occupied Set slot 遇上占用目标 Pad 时必须带 `occupied_pad_policy`=`keep`\|`replace`，缺省返回 `INVALID_ARGUMENT` + `details.reason = soundset_occupied_conflict` 且零变更。永不静默覆盖。 | 规格 §5.2「不得自动覆盖 Bank」、D1 配额、2026-08-28 记账修正、#465 |
| S11-D9 | 安装产生的每个 Asset 复用 #471 的单一 Lineage Contract，并使用 typed source：`source = {kind: soundset, set_id, set_version, manifest_sha256, slot_index, artifact_sha256}`、`derivation.kind = soundset_install`。这些字段全部必填，不能只记 `kind`。之后的裁剪/复制/再派生是普通 §5.2 流程；原始 Set Store 内容永不因用户编辑改变。 | 规格 §5.4、#471 |
| S11-D10 | 不扩张当前封闭的 `lmdj.error.v1` code 枚举。公开 code 与稳定细因分别为：manifest/slot 非法 → `INVALID_ARGUMENT` + `details.reason = soundset_manifest_invalid|soundset_slot_invalid`；占用冲突未带政策 → `INVALID_ARGUMENT` + `details.reason = soundset_occupied_conflict`；内容哈希或长度不符 → `IO_ERROR` + `details.reason = soundset_content_mismatch`；音频不支持 → `UNSUPPORTED_AUDIO` + `details.reason = soundset_audio_unsupported`；License 不满足 #465 的门禁 → `PERMISSION_DENIED` + `details.reason = soundset_license_ineligible`；Catalog 不可达 → `IO_ERROR` + `details.reason = catalog_unavailable`；配额复用 `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` 及其既有 details。`reason` 是本文锁定的 lowercase token，UI 可解释但不得改变 code 语义。所有安装期错误保证 Project、Asset、Pad 与 revision 不变。 | 当前 Error Contract/Foundation 枚举、规格 §18.1、#465 |
| S11-D11 | 把 Set 套用到已有 Pattern（regenerate 声音而保留演奏）在机制上是：一个纯函数 `map(set manifest, 当前 Bank 状态) → {proposed, collisions, kept}`，输出先预览、经用户确认后按 S11-D8 同一原子路径 commit。v1 映射表是槽位下标恒等：occupied slot `i` → pad `i`；role/BPM/Key 只作预览元数据，不置换槽位；音域不是 v1 字段。映射函数的输入只有已声明的 manifest 元数据与 Project 状态，无网络、无 AI 依赖。v1 安装与套用路径不做任何 time-stretch/pitch DSP（#465 不把 #347 升为前置）。 | 规格 §5.4、2026-08-26 D2、#465 |
| S11-D12 | Pattern 事件引用 Pad Slot（规格 §6.6），因此安装/套用改变的是「槽位发出什么声音」，不触碰 Pattern 事件本身。empty Set slot 不是清槽指令，不把占用中的目标 Pad 清空。结果 pad 为空时，已有事件落空静默（非致命），与 P10-D10 的空槽惯例一致。 | 规格 §6.6、P10-D10、#465 |

## 5. 身份与数据

`lmdj.soundset.v1` manifest（示意，字段以 Contract Schema 为准）：

```json
{
  "contract": "lmdj.soundset.v1",
  "set_id": "uuid",
  "version": "1.0.0",
  "name": "…", "publisher": "…",
  "bpm": 120, "key": "Am",
  "license": {
    "spdx_id": "CC-BY-4.0",
    "rights_holder": "…",
    "copyright": "Copyright 2026 …",
    "attribution": "…"
  },
  "demo": { "sha256": "…", "media_type": "audio/wav", "byte_length": 0 },
  "slots": [
    { "slot": 0, "role": "kick", "name": "…",
      "artifact": { "sha256": "…", "media_type": "audio/wav", "byte_length": 0 } },
    { "slot": 1, "empty": true }
  ]
}
```

`lmdj.soundset-catalog.v1` 条目 = `{set_id, version, manifest_sha256,
total_bytes, name, publisher, roles_summary, bpm?, key?, license_summary}`；其中
`total_bytes` 按 S11-D7 的唯一 blob 集合计算；`license_summary` 必须含
`spdx_id` 与 `rights_holder`，且与 manifest 对应字段逐字相等。

v1 分发没有 ZIP/TAR 或其他容器。网络 Catalog adapter 与本地目录 adapter
都只实现两个逻辑读取：canonical manifest object 与 content-addressed blob。
因此 v1 没有 archive 路径、解包、symlink 跟随或压缩炸弹语义；任何未来单文件
分发容器必须另立版本化 Contract 与安全评审，解包结果仍需还原为同一逻辑对象集。

Host 层状态（永不进 Project Truth）：Catalog 端点、Catalog 缓存、只读
Set Store。Project Truth 新增的只有普通 Asset + #471 Lineage 记录（其
Project 持久化位置随 #471/#431 对齐，串行在 v4 之后）。

## 6. Contract 影响

- 新增：`lmdj.soundset.v1`、`lmdj.soundset-catalog.v1`（独立 Contract SemVer）。
- 不改：`lmdj.capability.v2`、`lmdj.project.v4`（安装用既有 Asset/assignment
  语义即可表达；Lineage 的 Project 字段归 #471 的后续 Project 版本）。
- 复用：`lmdj.error.v1` 现有 code + `details.reason`、Artifact Ref 三元组；
  本设计不新增公共错误 code。

## 7. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. manifest 校验：canonical bytes golden vectors；BOM/尾随换行/空白、key
   重排、重复 key、非规范数字、过深 JSON；16 槽不足或超出/未知 role/坏哈希/坏 media_type/
   License 块缺键/空 `rights_holder`/`copyright`、`spdx_id` 不在
   `CC0-1.0`/`CC-BY-4.0`、`CC-BY-4.0` 而 `attribution` 为空、catalog
   `license_summary` 与 manifest 不一致逐条拒绝。
2. 完整性：篡改任一 Artifact 字节 → `IO_ERROR` +
   `details.reason = soundset_content_mismatch`，缓存不可见；重复 hash 只计费和
   下载一次；声明总量与唯一 blob 总量不符 fail closed。
3. 安装原子性：按每 Pad prepared bytes 预演 Bank/generation ledger（重复
   Artifact 占多个 Pad 分别计量）；两种配额超限、目标 Bank 冲突未确认、
   中途失败均零变更；成功恰好一次 revision，Lineage 齐全。
4. 不可变性：安装后编辑 Pad 产生 Derived Asset，Set Store 字节不变。
5. 套用映射：同输入同输出的纯函数性；冲突必须显式确认；empty Set slot
   不清空占用 Pad；结果为空的 pad 上事件落空静默。
6. Catalog：不可达非致命；缓存 Set 可试听可安装；本地 adapter 拒绝 symlink、
   非 lowercase-sha256 key、路径分隔/`..`、非 regular file 与越界对象；四个
   Host 上限逐条 exact/+1；网络 adapter 不能引入 archive 解包。

## 8. Version Management

Version impact: none——本文只是设计文档，不分配任何 Product、Module、Host、
Provider、Contract、Assembly 或 Channel 身份。实施计划必须分配：两个新
Contract 的初始版本、`application-facade` 与承载 Catalog/Set Store 的
Host 模块的 SemVer 影响、以及与 Stage 10 Task 10（#436）串行的 Product
Build 整合。

## 9. Documentation Impact

Documentation impact: none——本次只修订 retained 设计文档，不改变当前
manifest 派生的 Portal 真相。实施时受影响的 Portal 路由（Contracts、Facade、
Host 存储）由实施计划按实际身份变更声明。

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

拒绝 v1。2026-08-26 D2 已定采样无 BPM 语义；#465 确认离线 stretch
（#347）保持 Later，不升为 Stage 11 前置。

### 10.7 v1 单文件 archive

拒绝。逻辑 manifest + content-addressed blobs 已满足下载、缓存、完整性与本地
Catalog；archive 会新增路径穿越、symlink、压缩炸弹与双重身份问题。以后若有
离线搬运需求，另立容器 Contract，不能改变 Set 的 canonical manifest 身份。

## 11. 实施入口（前置条件）

1. #465 决策文件与本文绑定表回填（S11-Q1/Q2/Q3 裁决，S11-D2 / D8 /
   D10–D12 已对齐）。
2. #471 的 Lineage 通用记录定稿（S11-D9 依赖其 `derivation.kind` 词表）。
3. 本文评审通过后，按 #464 验收落笔逐 Task 实施计划（含 Version
   Management 与 Documentation impact 逐 Task 声明）。
4. Project/Facade/Creator 实施与 Product 身份整合串行在 Stage 10 v4
   （#427）与 Task 10（#436）之后。
