# P0 实现：耐久 Performance 初始状态与控制变更格式

状态：已实现（本文件与实现同 Task）。本 Task 是
[producer/consumer 计划](2026-10-11-performance-live-control-producers.md) 的 P0 节在
schema cut 之后的剩余部分；schema、两个 fixture 与 conformance 由 #2016（5.4.0）与
#2018（5.4.1 词法修复）先行交付，文件拆分记录于
[cut 计划](2026-10-11-project-v5-live-controls-cut.md)。

## 前提与权威

- 设计权威：[D0 编码设计](../prd/decisions/2026-10-11-performance-live-control-encoding.md)。
  本 Task 不重新决定其中的产品/Contract/并发问题。
- 当前 Contract：`lmdj.project.v5` `5.4.1`（header、序号 7/8 事件、`input_sequence`、
  profile 互斥规则已在 schema 层版本化）。
- F1（#2014）已合入 audio-runtime 的 typed Filter/epoch 机器；Facade admission 属于
  P1，不是本 Task。

## 实现范围（对照 P0 计划）

- **Domain**（`packages/authoring-domain`）：`PerformanceEventKind` 末尾追加
  `filter_change`(7)/`pad_gates_set`(8)，旧序号 0–6 与旧 canonical 排序不变；
  `PerformanceEvent` 增加可选 `input_sequence`；`PerformanceInitialLiveState`
  （严格 oneOf 的 legacy/independent Filter、固定七键 other_fx、两组 uint64 slot
  掩码、frozen 只在 HOLD 下合法）；headered profile 的 `(tick, input_sequence)`
  canonical 排序与种子校验（起点 engaged/frozen/HOLD 可配对后续 move/release）；
  两个 profile 在同一个 Performance 内互斥。
- **Project I/O**（`packages/project-io`）：Journal begin 以显式
  `live_control_profile: "header_input_sequence"` discriminator 分支（内部 v1 ID
  保留，旧 grammar 不接收新字段）；扩展 checkpoint（`open_filter` logical gesture、
  完整当前 `live_state`、open Pad 的原 press 序号）；每 session 有界 admission
  ledger（1 pending + 最近 1 completed）；`admission_complete` metadata record 只推进
  `next_recording_sequence`，不分配音乐序号；写入未知按 present/absent 显式恢复；
  owner-loss closure/seal 保留 unknown pending（closure 事件序号从 durable
  high-water 唯一派生，PadHit 复用 press 序号）；legacy receipt 不升级。
  Store 的 begin receipt lookup 先于新 profile 选择；header 随 CreatePerformance
  进入 Truth 并在 save/reopen 中原样往返；旧 reader fingerprint preimage 不变
  （header 只在存在时参与）。
- **Project Cooker**（`packages/project-cooker`）：`PerformanceReplayProjection`
  携带可选 `initial_live_state`；零事件也存活；独立于首事件 tick 归一化；revision
  与素材身份不变。

不在本 Task：实时 DSP（F1 已另合入）、Facade readiness/admission（P1）、Creator
控件（C1/C2）、任何 Host/SDK 改动。

## 最低层验证（对应计划 oracle）

- `domain.performance`：新旧 kind round-trip、越界/重复 slot 拒绝、序号唯一与
  profile 互斥、两方向同 tick 反例、预约 Pattern 原请求序号、种子配对、旧 0–6 与
  旧排序不变。
- `project_io.performance_journal`：begin/tail/complete round-trip；C1 expected0→
  C2 expected1→reattach exact 返回原序号、同 identity 变 payload 为 collision、
  C1 原 wire retry_expired 且零 enqueue（字节不变）；pending/completed 各 ≤1；
  写入故障的 present/absent 恢复；torn/checksum 拒绝；legacy 不升级；owner-loss
  closure 保留 unknown pending 且新 session 空 ledger 独立 begin。
- `project_io.performance_lifecycle`：begin/flush/stop/save/reopen 保留 header、
  扩展 checkpoint 与 ledger；flush 不越过 pending；Store 层 owner-loss reconcile→
  closure/seal→apply 后原 pending 仍 unknown、新 Performance 空 ledger。
- `cooker.performance_replay`：header 零事件存活、独立于首事件 tick、身份固定。
- 旧行为相邻套件（domain/project_io/cooker 全量 + facade.performance）全 PASS。
- `scripts/docs-site.sh check`；staged 后 `python3 tests/build/ci_change_scope_test.py`。

## Version Management

- Contract：本 Task 不改 schema；`lmdj.project.v5` 保持 `5.4.1`（由 #2016/#2018
  交付）。内部 Journal grammar 迁移以 `live_control_profile` discriminator 明确登记
  并经本 Task review；现有 v1 ID 不被误当作已支持新 ledger。
- Module ABI debt（按 producer 计划登记，V1 结算）：`authoring-domain` 的
  `Performance`/`PerformanceEvent`/variant 公开 layout 增长 → MAJOR debt；
  `project-io` 的 begin request/checkpoint/ledger 公开结构增长 → MAJOR debt；
  `project-cooker` 的 `PerformanceReplayProjection` 公开 layout 增长 → MAJOR debt。
  本 Task 不分配 Module 版本号、不结算 Assembly lock。
- 无 Product Build 分配。

## Documentation Impact

Documentation impact: required — `/core/modules/authoring-domain/`、
`/core/modules/project-io/`、`/core/modules/project-cooker/` 三个 current 页面与其
源图/生成图（HTML/SVG）随本 Task 更新。Contract 页 `/contracts/project/` 已在 cut
（#2016/#2018）中描述 5.4.1 语法，本 Task 不重复编辑。

## Pitfall Impact

开发中实际触发并已纠正的实现陷阱（均有失败证据，回归测试覆盖，不写 pitfall
条目）：嵌套 `optional<optional<T>>{nullopt}` 构造歧义（以 `std::in_place` 修复）、
ledger 计数器 `"0"` 与事件序号 `"1"` 起的 canonical 差异、begin ledger 空值不变量
属于写入方而非读取 grammar（恢复的 stopped 表示携带 terminal ledger）、checkpoint
双 Filter binding 校验不能把"零 binding"当作非法（disengaged 即零）。
恢复纪律教训：`git checkout -- <file>` 会丢弃整个未提交文件——突变证明必须恢复
单个 hunk，不能整文件 checkout（本 Task 的实际突变证明在重建后命中目标断言）。
