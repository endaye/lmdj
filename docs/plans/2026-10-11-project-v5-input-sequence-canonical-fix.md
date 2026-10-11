# Project Contract 5.4.1：`input_sequence` 规范十进制整串锚定修复

状态：S0/S1 按 [git-workflow 的 Product cut 顺序](../governance/git-workflow.md#product-cut-source-and-snapshot-phases)
在同一 PR 中 shipping；本文件是该修复 cut 的计划与边界记录。

## Outcome and authority

修复 `lmdj.project.v5` 5.4.0 新增 `input_sequence` 模式的词法漏洞：裸 `$` 锚定在
Python `re.search` 下匹配尾部 LF 之前，使 `"10\n"` 通过校验，违反已声明的规范
十进制 Contract。按 [version-management §7](../governance/version-management.md)
"语义澄清或验证修复增加 Contract Patch"，本次为 `5.4.0` → `5.4.1`。

**Audit provenance.** 独立审计（Root coordinator）发现并以 counterexample
sha256 `f0f4c61f2cef651c2bf51ea298aa5b818854f0e54918b969b2414f32cf028b95` 复现；
本 Task 在 origin/main `667e39a47fe42ad07369a337b4c8d80aac47b686`（cut #2016）
上独立复现：valid fixture 仅把 `#/performances/0/events/0/input_sequence` 置为
`"10\n"` 时 `tests/conformance/json_schema.py` 返回零违规；`"10\r\n"` 与
`"10\n\n"` 当时已被拒绝。

**Authority:**

- 5.4.0 cut 的语义声明：`input_sequence` 是 Core 分配的规范十进制字符串，不接受
  符号、前导零、浮点（[5.4.0 cut 计划](2026-10-11-project-v5-live-controls-cut.md)
  与 [D0 编码设计](../prd/decisions/2026-10-11-performance-live-control-encoding.md)）。
- [git-workflow](../governance/git-workflow.md) 与
  [architecture-portal](../governance/architecture-portal.md) 的 S0/S1 与快照义务。

**Explicitly out of scope（审计 finding 的 owner 明确排除）：** 既有模式
（uuid/sha256/semver 等）存在的同类潜在 `$` 泄漏不在本 Task 内；`input_sequence`
的 uint64 精确上界与数组升序校验仍属 Domain reader（P0），本 Task 不触碰；
`tests/conformance/json_schema.py` 验证器本身不改；零事件与 legacy profile 语义不变。

## Facts this cut relies on

Checked on `667e39a47fe42ad07369a337b4c8d80aac47b686`。

- 5.4.0 已由 #2016 合入 main；`input_sequence` 定义为
  `"pattern": "^[1-9][0-9]{0,19}$"`。schema 已有的可移植整串锚定写法是
  `(?![\s\\S])` 后缀（见 `performance.name` 的 `"^[\\s\\S]{1,64}(?![\\s\\S])"` 与
  capability `attempt_id` 的 `"^[A-Za-z0-9._-]{1,128}(?![\\s\\S])"`）。
- Schema 摘要仍被 `products/lmdj/assembly.lock.json` 锁定；版本仍由
  `tests/build/version_test.py` 与 `tests/conformance/schema_contract_test.py` 钉住。
- `2.0.90.0` 未被占用：`git tag -l`、`gh release list`、两份 `versions.json` 与
  `docs/release-evidence/release-intents.json` 均无该号；无打开中的 PR 触碰
  `products/lmdj/`。正向对照：同一组探针能找到 `2.0.89.0`（versions.json）与
  `2.0.87.0`（tag、Release、release intent）。
- 新键仍无读写方（P0 未合入），所以把 `"10\n"` 从"语法上接受"改为拒绝不是
  "收紧到破坏合法旧数据"：按已声明的规范十进制语义它从来不合法，且尚无任何
  Project 能携带该键。

## 修复内容

- `input_sequence` 定义改为 `"^[1-9][0-9]{0,19}(?![\\s\\S])"`：digits 部分不变，
  用 schema 已有的可移植 `(?![\s\S])` 后缀替代裸 `$`，拒绝尾部 LF/CRLF/双 LF。
- Conformance：`tests/conformance/schema_contract_test.py` 的 pattern 钉更新，
  并对 valid fixture 的 `input_sequence` 增加 `"10\n"`、`"10\r\n"`、`"10\n\n"`
  三条回归拒绝；既有接受（`"1"`、`"18446744073709551615"` 等边界）全部保留。

## Tasks

### S0 — source checkpoint

Declared files（完整边界）：

- `contracts/project/lmdj.project.v5.schema.json`
- `tests/conformance/schema_contract_test.py`
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
- `docs/plans/2026-10-11-project-v5-input-sequence-canonical-fix.md`（new，本文件）

验证：先在 origin/main 的新 worktree 上 RED 复现（见上），修复后
`tests/conformance/schema_contract_test.py`、`tests/build/version_test.py`、
`tests/conformance/version_lock_test.py`、`scripts/version.py verify`、
`bash tests/build/test_active_tree.sh`、`scripts/core.sh proof` 全部 PASS；整个
`check:current` PASS；完整 `scripts/docs-site.sh check` 的非零结果恰为新 Build
`2.0.90.0` 的三条缺席快照前置并保留为证据；staged 后
`python3 tests/build/ci_change_scope_test.py` PASS。S0 只是干净冻结源。

### S1 — snapshot

在不变的干净 S0 HEAD 上只运行
`scripts/docs-site.sh version 2.0.90.0 canary`，stage 其实际不可变生成边界，不夹带
其他 source/current 编辑。S1 提交前完整 `scripts/docs-site.sh check` 必须全 PASS。

## Verification

- RED：`"10\n"` 在 origin/main 通过校验（零违规）的实跑记录；`"10\r\n"`、
  `"10\n\n"` 当时已拒绝；控制 `"10"` 合法。
- GREEN：修复后同一探针矩阵全部符合预期（LF/CRLF/双 LF 拒绝，`"10"`、
  边界值接受），conformance 全套 PASS，无既有用例被破坏。
- 版本级联与 Portal 检查与 5.4.0 cut 相同（见 Tasks）。
- 不降低任何阈值、预算、lane 或 journey 段。

## Version Management

- Contract：`lmdj.project.v5` `5.4.0` → `5.4.1`（同 Contract ID 的 Patch：
  语义澄清/验证修复）。不是 Major/Minor 的理由：未删除字段、未改变字段含义；
  "收紧到破坏合法旧数据"不成立——新键尚无读写实现（P0 未合入），且 `"10\n"`
  按已声明的规范十进制语义从来不是合法数据。
- Product Build：分配 `2.0.90.0`（在 `2.0.89.0` 之上单调递增；占用性探针见上，
  含正向对照）。
- Module、Host、Provider 身份全部不变；无 ABI debt 结算。
- 快照：`2.0.90.0` 的不可变 Portal 快照（schema 2 metadata，`canary`）随本 PR
  的 S1 冻结。Build 分配不是 Release；tag、Release、发布、部署与 Channel 晋级
  各保留独立授权边界。

## Documentation Impact

Documentation impact: required — `/contracts/project/`（5.4.0 节更正为 5.4.1 的
锚定语义）与 `/assembly/lmdj/`（当前分配轮换）在本 cut 同 Task 更新；
`2.0.90.0` 的不可变快照随 S1 冻结。Module 页面与源图不变（无产品实现改动）。

## Pitfall Impact

适用 `portal-snapshot-not-deferrable` 与 `worktree-checkout-flattens-symlinks`
（worktree 以 command-local `core.symlinks=true` 创建）。本 Task 的教训
（"新增串模式须用 `(?![\s\S])` 整串锚定而非裸 `$`"，且 uuid/sha256/semver 的
同类潜在泄漏被 owner 明确留作后续）是否入 pitfall ledger 由 shipping 方按
issue-done §2 判定。
