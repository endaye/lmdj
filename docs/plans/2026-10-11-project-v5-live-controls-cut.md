# Project Contract 5.4.0 cut：Performance 实时控制的耐久语法

状态：S0/S1 按 [git-workflow 的 Product cut 顺序](../governance/git-workflow.md#product-cut-source-and-snapshot-phases)
在同一 PR 中 shipping；本文件是 cut 的计划与边界记录。

## Outcome and authority

把 Performance 实时控制（D04）的耐久语法以兼容 MINOR 落入 `lmdj.project.v5`
（5.3.0 → 5.4.0，Contract ID 不变），使后续 Core 实现 Task 面对的是已版本化的
持久化语法而不是未版本的新键。本 cut 只做 Contract formalization 与其身份级联；
不实现任何读写新键的产品代码。

**Authority:**

- [已批准 D04 决定](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)：
  独立 LP/HP/BP、Cutoff 20 Hz–20 kHz、Resonance 0–100%，初始 OFF/LP/20 kHz/0%；
  全部 64 Pad 的实时 Mute/Solo；录制必须包含起点状态及后续变化。
- [D0 编码设计](../prd/decisions/2026-10-11-performance-live-control-encoding.md)：
  optional header 的闭合 shape、两种新事件、逐事件 `input_sequence`、profile
  判别与兼容规则。本 cut 不重新决定其中已审阅的 Contract 问题。
- [producer/consumer 计划](2026-10-11-performance-live-control-producers.md) 的
  P0 节：新语法须在实现 Task 之前完成版本化（"never ship unversioned new
  persisted syntax"）。
- Owner 2026-10-11 决定：schema cut 先行（沿用 `ae6a7ce2` 的 5.2.0→5.3.0 先例），
  P0 的 Domain/Journal/Cooker 实现在 cut 合入后另行跟进。

## Facts this cut relies on

Checked on `82c010d0391b956f871d34ecb40720f9a7e0a8d7`（当前 origin/main）。

- `contracts/project/lmdj.project.v5.schema.json` 是 `lmdj.project.v5` 5.3.0；
  `performance` 闭合六键，`performance_event` 是七种 kind 的封闭并集（序号 0–6）。
- Schema 摘要被 `products/lmdj/assembly.lock.json` 锁定，版本被
  `tests/build/version_test.py` 与 `tests/conformance/schema_contract_test.py`
  分别钉住；任何 schema 编辑都必须同提交更新这条身份级联（这正是 5.1.0/5.2.0/5.3.0
  三次 cut 的共同形状）。
- 5.3.0 cut（`ae6a7ce2`）证明同样的追加可以在同一 PR 中完成
  schema、conformance、fixtures、Assembly/Lock/Build 级联与 Portal 快照，
  而读写实现由后续 Core Task 交付；在此之前 Project I/O 的 exact-key reader
  继续拒绝新键。
- `2.0.89.0` 未被占用：`git tag -l`、`gh release list`、两份 `versions.json`
  与 `docs/release-evidence/release-intents.json` 均无该号；无打开中的 PR
  触碰 `products/lmdj/`。正向对照：同一组探针能找到 `2.0.88.0`
  （versions.json）与 `2.0.87.0`（tag、Release、release intent）。

## 5.4.0 的追加内容（additive only）

- `performance` 新增可选键 `initial_live_state`：闭合的
  `{hold, filter, other_fx, muted_slots, solo_slots}`。`filter` 是严格 oneOf：
  `mode: independent` 携带 `type`（`lp`/`hp`/`bp`）、整数 `cutoff_hz`
  20..20000 与 `resonance_milli` 0..1000；`mode: legacy` 只携带 0..1000 的
  `value`；两套参数不混收。`other_fx` 固定为现有七个非 Filter FX
  （delay/reverb/stutter/gate/reverse/crush/cutter）各一组
  `{engaged, frozen, value}`（`value` 0..1000）。任一 `frozen: true` 只在
  `hold: true` 下合法（schema 的八条 if/then）。slot 数组是 0..63 唯一整数。
- `performance_event` 并集末尾追加序号 7 `filter_change`（每次携带
  `phase` engage/move/release 与完整参数 tuple）与序号 8 `pad_gates_set`
  （每次携带两组完整 mask，不是 delta）；原七种 kind 序号与 shape 不变。
- 每个事件（含旧七种 kind）新增可选 `input_sequence`：Core 分配的规范十进制
  字符串，从 `"1"` 起，不接受符号、前导零、小数。uint64 精确上界与数组升序
  由 Domain reader 校验（P0），与旧 canonical 排序一样不属于 Schema 层。
- header 与逐事件序号互为开关（performance 级两条 allOf）：携带
  `initial_live_state` 的 Performance 其每个事件都必须带 `input_sequence`；
  任一事件带 `input_sequence` 则必须携带 header。旧 profile 不允许混入序号，
  零事件的新 profile（只有 header）合法。

每个当前合法的 v5 文档在 5.4.0 下保持合法且语义不变；5.3.0 reader 按设计拒绝
新键（各闭合对象 `additionalProperties: false` 不变）。

## Tasks

### S0 — source checkpoint

Declared files（完整边界）：

- `contracts/project/lmdj.project.v5.schema.json`
- `tests/conformance/schema_contract_test.py`
- `tests/fixtures/contracts/project-v5-live-controls-valid.json`（new）
- `tests/fixtures/contracts/project-v5-live-controls-invalid.json`（new）
- `tests/build/version_test.py`
- `products/lmdj/version.json`
- `products/lmdj/assembly.json`
- `products/lmdj/assembly.lock.json`（`scripts/version.py lock` 生成）
- `products/lmdj/src/compiled_assembly.cpp`（同一命令生成）
- `products/lmdj/src/cardputer_assembly.cpp`（三个手抄字面量，由
  `tests/build/version_test.py` 校验与来源一致）
- `apps/cardputer-host/CMakeLists.txt`（`PROJECT_VER` 手抄，同上）
- `products/lmdj/generated/web-runtime-identity.json`（
  `tools/web-runtime/generate_runtime_identity.py` 生成）
- `products/lmdj/generated/web-runtime-identity.mjs`（同上）
- `apps/docs-site/docs/contracts/project.mdx`
- `apps/docs-site/docs/assembly/lmdj.mdx`
- `docs/plans/2026-10-11-project-v5-live-controls-cut.md`（new，本文件）

验证：owning conformance/version 检查（`tests/conformance/schema_contract_test.py`、
`tests/build/version_test.py`、`tests/conformance/version_lock_test.py`、
`scripts/version.py verify`）、`bash tests/build/test_active_tree.sh`、整个
`check:current` PASS，并实际运行完整 `scripts/docs-site.sh check`：其非零结果的
错误集合恰为新 Build `2.0.89.0` 的三条缺席快照前置（versions.json 条目、snapshot
source、metadata）。该非零结果保留为证据，不记为 PASS；S0 只是干净冻结源，不单独
push/PR/merge。

### S1 — snapshot

在不变的干净 S0 HEAD 上只运行
`scripts/docs-site.sh version 2.0.89.0 canary`，stage 其实际不可变生成边界
（`versions.json`、`versioned_docs/version-2.0.89.0/`、
`versioned_sidebars/version-2.0.89.0-sidebars.json`、
`versioned_metadata/version-2.0.89.0.json`、`versioned_provenance/` 对应条目与
`static/versions/2.0.89.0/` 图表资产），不夹带其他 source/current 编辑或旧快照
删除。S1 提交前完整 `scripts/docs-site.sh check` 与适用 Task 检查必须全部 PASS。

### P0 后续实现的文件分界（记录用）

本 cut 从 producer/consumer 计划 P0 的 declared files 中吸收：
`contracts/project/lmdj.project.v5.schema.json`、
`tests/conformance/schema_contract_test.py` 与两个
`tests/fixtures/contracts/project-v5-live-controls-*` fixture。P0 余下范围不变：
`packages/authoring-domain`、`packages/project-io`、`packages/project-cooker`
的 reader/writer/Journal/projection 实现与其四套既有测试、三个 Module 的 Portal
页面与源图/生成图，以及 P0 自己的计划文档。P0 合入前 Project I/O 继续拒绝新键。

## Verification

- conformance：旧四个有效 v5 fixture 在 5.4.0 下仍合法；新 valid fixture 覆盖
  HOLD 起点、engaged independent HP Filter、frozen Reverb、engaged Delay、muted
  Pad、两种新 kind、带序号的旧 kind 与预约 Pattern 的原请求序号；新 invalid
  fixture 每条新规则一处违规并整体拒绝；另对 valid fixture 做逐规则单点变异
  （type/range/mask/序号/闭合键/profile 两个方向混合）与合法边界（Cutoff
  20/20000、Resonance 0/1000、slot 0/63、空 mask、序号 `"1"` 与 uint64 上限宽度）。
- `python3 tests/build/version_test.py`、`python3 tests/conformance/version_lock_test.py`、
  `python3 scripts/version.py verify --version-file products/lmdj/version.json
  --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json`。
- `scripts/core.sh proof`（Release 构建与 owning native/Host 套件）。
- Portal：`check:current` 全 PASS + 完整 `check`（S0 仅允许三条缺席快照前置，
  S1 必须全 PASS）。
- 新增路径的 ownership/admission：`python3 tests/build/ci_change_scope_test.py`
  在 staging 后运行。
- 不降低任何阈值、预算、lane 或 journey 段。

## Version Management

- Contract：`lmdj.project.v5` 5.3.0 → 5.4.0（同 Contract ID 的兼容 MINOR；
  追加可选键与新并集分支，旧文档全部保持合法，旧 reader 按设计拒绝新键）。
- Product Build：分配 `2.0.89.0`（在 `2.0.88.0` 之上单调递增；占用性探针见上）。
- Module、Host、Provider 身份全部不变；本 cut 不结算任何 ABI debt。读写新键的
  实现 Task（P0 等）的公开 layout/ABI 影响按其计划在实际变更时结算。
- 快照：`2.0.89.0` 的不可变 Portal 快照（schema 2 metadata，`canary`）随本 PR
  的 S1 冻结。Build 分配不是 Release；tag、Release、发布、部署与 Channel 晋级
  各保留独立授权边界。

## Documentation Impact

Documentation impact: required — `/contracts/project/` 与 `/assembly/lmdj/` 两个
current 页面在本 cut 同 Task 更新；`2.0.89.0` 的不可变快照随 S1 冻结。Module 页面
与源图属于后续 P0 实现 Task，本 cut 不改产品实现，不涉及它们。

## Pitfall Impact

适用 `portal-snapshot-not-deferrable`（快照随分配同 PR 冻结）与
`worktree-checkout-flattens-symlinks`（worktree 以 command-local
`core.symlinks=true` 创建；`apps/docs-site/versions.json` 等五个 symlink
投影到 `apps/architecture-portal/`）。无新 pitfall 预期。
