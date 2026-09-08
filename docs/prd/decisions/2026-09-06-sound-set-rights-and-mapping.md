# 已确认：Sound Set v1 的权利门禁、安装映射与 stretch 边界

- 日期：2026-09-06
- 解决的问题：`docs/prd/questions/curated-packs-content-rights.md` 与
  `docs/prd/questions/empty-pad-fill-strategy.md`（两文件均无 GitHub Issue
  行、原状态 *延后*，已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#465](https://github.com/endaye/lmdj/issues/465)（S11-Q1 / S11-Q2 /
  S11-Q3）。机制框架仍以
  [Stage 11 Sound Set 设计](../../design/2026-08-31-lmdj-stage11-sound-set-design.md)
  为准；本决策只补权利字段、fail-closed 边界、v1 映射表与 stretch 前置裁决。
- 结论：

  **S11-Q1 权利与 License 溯源**

  1. **权威字段钉在 manifest 的 `license` 对象，四键全必填。**
     `lmdj.soundset.v1` 的 `license` 恰好为：

     | 键 | 类型 | 约束 |
     | --- | --- | --- |
     | `spdx_id` | string | v1 允许清单之一，见第 2 条 |
     | `rights_holder` | string | 非空 |
     | `copyright` | string | 非空 |
     | `attribution` | string | 键必填；空串仅当该 `spdx_id` 无署名义务 |

     内容校验和已经是 Artifact `sha256`，不再另设 provenance / source_record。
     v1 不收 `territory`、`url`、`redistribution` 或吊销登记；缺省即全球、
     Catalog-only、无在线权利服务器。SPDX 标识本身就是再分发与派生编辑的
     权利语言，不平行发明一套 enum。

  2. **v1 SPDX 允许清单是封闭枚举：`CC0-1.0`、`CC-BY-4.0`。** 扩展走
     Contract SemVer。署名义务表 v1 只有一行：`CC-BY-4.0` 的 `attribution`
     必须非空，该字符串是 Host 在 listing / preview / 已安装 Asset 上展示
     的权威署名；`CC0-1.0` 允许空串。排除 `CC-BY-NC-*`（产品不承诺用户只
     做非商业使用）、`CC-BY-SA-*`（ShareAlike 会把用户 Project 导出绑进
     传染义务）以及任意 `LicenseRef-*`（Catalog 首版不做自定义许可证）。

  3. **listing / preview / download / install 共用同一资格。** 许可证不合格
     的 Set 不得出现在 Catalog 索引里，也不得被试听、下载或安装。不为
     Catalog 做「可听不可装」的预告门禁——那是 Marketplace 语义，规格
     §5.4 排除。Catalog 条目的 `license_summary` 必须含 `spdx_id` 与
     `rights_holder`，且与已验证 manifest 的对应字段逐字相等；摘要与
     manifest 不一致视为不合格。

  4. **公开错误分流。** `license` 缺块、缺键、类型不对或空的
     `rights_holder` / `copyright` 是 Schema 失败：`INVALID_ARGUMENT` +
     `details.reason = soundset_manifest_invalid`。`spdx_id` 不在允许清单、
     署名义务未满足、或 catalog `license_summary` 与 manifest 不一致：
     `PERMISSION_DENIED` + `details.reason = soundset_license_ineligible`。
     不新增 `lmdj.error.v1` code，不拆更细的 `soundset_license_*` token。

  5. **v1 没有活的吊销列表。** 下架 = 运营者发布一份不再包含该 Set 的
     Catalog 索引。已通过 S11-D7 验证并进入 Set Store 的缓存副本，资格以
     **该副本自己的 manifest `license` 块**为准，不回访网络。Catalog 不可达
     仍非致命。从 Workspace 删除 Set Store 条目是 Host 运营动作，不进
     Project Truth。若将来需要让已缓存副本对吊销 fail closed，必须新开决策
     ——那会与离线可用冲突，本条不预留字段。

  **S11-Q2 确定性 Bank 映射与空槽填充**

  6. **v1 映射表是槽位下标恒等。** 纯函数

     `map(manifest, 目标 Bank 占用状态) → {proposed, collisions, kept}`

     对每个 occupied Set slot `i` 提出写入目标 Bank pad `i`（`proposed`）。
     目标 pad 已占用则为 `collisions`；否则为可直接写入。empty Set slot
     **不进入** `proposed`：目标 pad 无论空或占用都保持原状，记入 `kept`。
     重复 `role` 合法，不改变下标对应。可选的 set / slot 级 `bpm`、`key`
     只用于 Catalog 与预览展示，不置换槽位，也不因与 Project 全局 BPM/Key
     不一致而拒绝。音域不是 v1 manifest 字段，不是 v1 映射输入；将来若加入
     走 Contract SemVer，不能悄悄改这条恒等表。

  7. **role / BPM / Key 是预览元数据，也是未来映射表唯一允许的输入，v1
     不用它们重排 Pad。** 规格 §5.4「优先使用确定性的角色、BPM、Key 和音域
     映射」在 v1 收成：映射函数不得读取网络、AI 或未声明状态；这四类是
     将来唯一准许的置换输入。v1 仍走下标恒等，因为 `lmdj.project.v4` 的 Pad
     没有 role 字段，按 role 重排要么改写 Pattern 事件（违反规格 §6.6 与
     S11-D12），要么依赖仍可能不在 Set Store 的旧 manifest 反查 Lineage。
     以后若 Project Contract 增加 Pad role 或独立映射表，只替换本条函数，
     不改第 8–10 条的确认、空槽与 Pattern 引用规则。

  8. **占用冲突必须显式政策，默认拒绝。** 只读预览就是第 6 条的纯函数，
     零 Project 变更。`InstallSoundSet`（套用走同一原子路径）在 `collisions`
     非空时必须带 `occupied_pad_policy`：

     | 值 | 行为 |
     | --- | --- |
     | 缺省 | `INVALID_ARGUMENT` + `details.reason = soundset_occupied_conflict`，details 携带完整 `collisions` 清单，零变更 |
     | `keep` | 只写入非冲突的 `proposed`；冲突 pad 原样保留；成功 |
     | `replace` | 写入全部 `proposed`，冲突 pad 换成 Set 的 Asset；成功 |

     永不静默覆盖。`soundset_occupied_conflict` 是本决策新增的稳定
     `details.reason` token，公开 code 仍是 `INVALID_ARGUMENT`。配额拒绝
     继续走既有 `BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED`，政策
     参数不能越过配额。被替换的旧 Asset 按 S8-D5 不立即删除。

  9. **empty Set slot 不是清槽指令。** Set 作者的留白表示「本套不提供这个
     Pad」，不是「把目标 Bank 的这个 Pad 清空」。S11-D12 的「空槽事件落空
     静默」只描述 **结果 pad 为空时** 的播放后果（新装进空 Bank、或用户
     之后自己清空），不是安装期自动 wipe。与规格 §5.2「不得自动覆盖 Bank」
     一致。

  10. **Pattern 事件引用永不改写。** 安装 / 套用只改 Pad 上的 Asset。事件
      继续指向原 Pad Slot；换了声音就发出新声音，pad 仍空就静默。不存在
      「按 role 把 kick 事件改写到另一个槽」的 v1 路径。

  11. **空 Pad 只被显式用户动作填充。** 合法来源只有：用户选择目标 Pad 的
      Capture / 导入 / Resample；本决策的 Sound Set 安装或套用；以及
      Stage 12 采纳路径里用户选择目标 Pad（#471）。禁止自动装进「下一个
      空 Bank / 空 Pad」（设计 10.2 已拒）。role 不是新的 Pad 类型。

  **S11-Q3 离线 time-stretch 不是 Stage 11 前置**

  12. **v1 安装与套用路径不做任何 time-stretch 或 pitch DSP。** 不把
      [#347](https://github.com/endaye/lmdj/issues/347) 从 Later 升为
      Stage 11 前置。采样无 BPM 语义、全局 BPM 只驱动 sequencer，已由
      [2026-08-26 D2](2026-08-26-long-material-quota-and-bpm-stretch.md)
      钉死；Set 上的 BPM/Key 只是浏览与预览元数据。BPM 对齐若成为以后
      映射表的要求，必须新开决策并把 #347 升为前置，不能在实施 Task 里
      把 stretch 塞进安装路径。

- 原因：Catalog 首版是第一方分发，不是上传市场，所以权利模型收敛成「可机
  读的 SPDX 允许清单 + 署名义务」，在 listing 就 fail closed，避免合格包
  带着不能用的内容进入 Set Store。preview 与 install 资格相同，是因为
  Catalog 不做付费墙。不做在线吊销，是因为 S11-D7 已规定 Catalog 不可达
  时缓存 Set 仍可用。映射走下标恒等，是因为 Pattern 事件引用的是 Pad
  Slot、Project v4 又没有 Pad role，role 重排在 v1 没有确定性输入。空槽
  不清目标 Bank，是 §5.2 不覆盖原则的直接推论，也回答了「空 Pad 怎么填」
  ——只允许显式用户动作。stretch 继续留在 #347，避免把 D2 的实时零 DSP
  与离线烘焙边界从安装路径打开。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。本 Task 已回填 Stage 11 设计的 S11-Q1–Q3 绑定表，并按
  第 9 条勘误 S11-D12。#464 仍须把 `license` 四键、`occupied_pad_policy`
  与 `soundset_occupied_conflict` 写入实施计划与 Contract Schema。实施时
  支付：`lmdj.soundset.v1` / `lmdj.soundset-catalog.v1` 的初始 Schema、
  Facade 的只读映射预览与 `InstallSoundSet` 政策参数；不新增公开 error
  code。#347 保持 Later。关闭 #465。
