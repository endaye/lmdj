# LMDJ 版本管理规范

日期：2026-07-30

状态：已生效

适用范围：LMDJ Monorepo 中的产品 Assembly、正式构建、Contract、Core Module、
Provider、模型与所有后续实施计划。

## 1. 目标

LMDJ 使用一套受 Chromium 启发、但适合当前 Monorepo 的版本体系：

```text
产品构建：MILESTONE.MINOR.BUILD.PATCH
发布渠道：canary | dev | beta | stable
源码修订：完整 Git SHA
模块实现：SemVer MAJOR.MINOR.PATCH
公开契约：稳定 Contract ID + Contract SemVer
Provider：Provider ID + Provider SemVer + Capability Contract + Model Identity
```

这几类版本回答不同问题，禁止互相替代：

| 身份 | 回答的问题 |
| --- | --- |
| Product Build Version | 用户或测试者运行的是哪一个完整 LMDJ Assembly？ |
| Release Channel | 这个完全相同的 Build 当前允许进入哪类人群？ |
| Git Revision | 这个 Build 对应 Monorepo 的哪一个精确提交？ |
| Module Version | 某个可复用 Package 的公开 API/ABI 处于哪个兼容版本？ |
| Contract Version | 跨语言、跨进程数据能否被消费者正确理解？ |
| Provider Version | 哪个 Provider 实现处理了请求？ |
| Model Identity | Provider 实际使用了哪组模型、权重或规则资产？ |

版本号不是功能完成度宣传，也不能代替测试、CI、真机验收、发布或部署证据。

### Web Host Product Release 与部署身份

当前 Web Host 发布 profile 是 `web-hosts`：同一个 Product Build/tag/Release 精确包含
Creator Web Host 与 Web Runtime Host 各自的 ZIP、checksum 和 detached checksum signature，
总计六项资产。两个 Host 保持独立 SemVer；一个 Product Release 不把它们合并成同一 Host。

Release assets 是签名交付输入，部署状态属于外部 Host Site。Creator 固定目标
`https://lmdj-creator.netlify.app/`，Runtime 固定目标 `https://lmdj-runtime.netlify.app/`；两条
manual-only workflow 的授权、Environment、Site、凭据、evidence 与 exact prior rollback 独立。
Release publication 不自动触发任一部署，一个 Host 的部署也不证明另一个 Host 已部署。
历史 `1.0.40.0` tag、Release 与部署保持不可变；新六资产 profile 只适用于后续分配的 Build。

## 2. Product Build Version

正式产品构建使用四段数字：

```text
MILESTONE.MINOR.BUILD.PATCH
```

示例：

```text
1.0.12.0
```

### 2.1 MILESTONE

`MILESTONE` 是产品能力列车编号，不是 SemVer 的兼容性 Major。

- 只有经确认的产品/架构设计才能分配新 Milestone。
- Milestone 描述可独立验证的纵向能力边界。
- Milestone 完成不等于 Stable；它仍需通过对应渠道门禁。
- 新 Milestone 不要求重置 `BUILD`。

当前定义：

| Milestone | 定义 | 完成门禁 |
| --- | --- | --- |
| M1 | Headless 64-Pad Beat Project + Sampler + Pattern Playback + Offline WAV Render + Golden Audio + CLI/MCP + 测试 Provider 切换与失败隔离 | Headless Core Proof 计划 PR 1–6 全部合入，双平台 CI 通过，Proof E2E 通过 |

M2 及以后必须由新的已批准设计分配，不能在实现过程中自行命名。

### 2.2 MINOR

`MINOR` 是同一 Milestone 内经设计批准的兼容子列车。

- 默认值为 `0`。
- 普通功能、修复、PR 或 Provider 更新不增加 `MINOR`。
- 只有需要在同一 Milestone 内长期并行维护两个兼容产品列车时才增加。
- 增加 `MINOR` 必须写明兼容范围、迁移策略和支持期限。

M1 当前固定为 `1.0.*.*`。

### 2.3 BUILD

`BUILD` 是产品集成构建号。

- 在同一正式产品版本线中单调递增，跨 Milestone 不重置。
- 每个经保护分支 PR 评审合入、值得被测试或分发的 Product Assembly 分配一个新
  `BUILD`。
- 新 Build 必须来自 `main` 上一个精确、CI 已验证的提交。
- Build 可以有间断；失败或放弃的编号不得复用。
- 纯文档提交默认不分配 Product Build，除非文档本身是版本、Contract 或发布
  治理的正式产物。
- 同一个 Git SHA 不得分配两个不同 Product Build Version。
- 同一个 Product Build Version 不得指向两个 Git SHA。

M1 的第一个可构建集成版本为 `1.0.1.0`。

### 2.4 PATCH

`PATCH` 是同一 Build 分支上的修订号。

The prospective rule is unambiguous: PATCH may not change Product Assembly identity or `assembly.lock`.
Any module/provider/Host/dependency identity change allocates a new BUILD.
Historical `1.0.16.x` events remain historical facts and are not rewritten;
their recorded deviations are evidence for tightening this rule, not precedent
for another PATCH-level Assembly change.

- 新 Build 的 `PATCH` 从 `0` 开始。
- 只有从同一 Build 修复缺陷、且不增加公开能力或改变 Contract 语义时才增加。
- Patch 必须保留原 Build 的 Milestone、Minor 和 Build 三段。
- 功能增加、依赖升级、Contract 变化或 Assembly 变化必须分配新 Build，而不是
  增加 Patch。
- Patch 修复必须同时回到 `main`，避免 release branch 成为第二 Source of Truth。
- Patch 从已发布 tag 上的短命 `fix/<task>` 分支产生，用完即删；仓库不设 `release/*`
  或 `hotfix/*` 长期分支。新 Build 的分配遵循
  [`git-workflow.md`](git-workflow.md) 的 Release cut 规则：功能与 control-plane
  改动先各自合入 `main`，切版 PR 只携带分配材料并经当前 head 评审 squash 合入。

示例：

```text
1.0.12.0  原始 Build
1.0.12.1  同一 Build 的第一个 hotfix
1.0.13.0  后续新的集成 Build
```

## 3. Release Channel

Channel 与四段数字版本分开记录：

| Channel | 用途 | 最低门禁 |
| --- | --- | --- |
| `canary` | 每个可构建候选，供自动化和开发者快速发现问题 | 编译成功、基础单测通过 |
| `dev` | 一个集成或纵向开发阶段完成，供团队集成验证 | 全量 CI、对应 E2E、版本一致性检查通过 |
| `beta` | 已具备真实用户价值，进入受控用户测试 | 用户流程、数据恢复、平台/设备验收通过 |
| `stable` | 可正式交付的生产版本 | Release Checklist、回滚、签名、发布和生产验证通过 |

Channel 不是版本号的一部分。同一 Build 可以从 `canary` 晋级到 `dev`、`beta` 或
`stable`，晋级不会移动源码 tag，也不会生成一个伪造的新 Build。

Channel 降级或撤回只改变发布记录，不删除原 Build、tag 或验证证据。

M1 Headless Core Proof 最多进入 `dev`；它没有 Creator UI 和真实用户闭环，不能被
标记为 `beta` 或 `stable`。

### 3.1 Channel promotion 机制

晋级是一次经 review 的发布记录变更，永不改动 GitHub Release。ledger 中 Product intent 的
`channel` 字段固定为**发布时的 Channel**，发布后不可变，并继续决定 Release 的
`prerelease` 与 `latest`（见发布管线设计 D6、D8）。晋级写入该 intent 的可选 `promotions`
列表；每条记录固定目标 Channel、UTC 时间、证据路径、每个 Host 部署 run 的 ID 与其保留
`evidence.json` 的 SHA-256，以及 attestation。当前 Channel 等于最后一条晋级记录，没有则等于
`channel`。

晋级只能严格向前，一次一档，且不得超过 `tools/release/policy.json` 的
`promotion.max_channel`（M1 为 `dev`）。各档门禁的可判定形态：

| 目标 | 工具判定 | attestation |
| --- | --- | --- |
| `dev` | intent 已 `published`；full exact-main CI 成立；profile 的每个部署 Host 各有一次成功的 `workflow_dispatch` 部署 run，其保留 `evidence.json` 记录同一 tag、同一 target revision、同一 Product Build，且 immutable 与 production 的 HTTP 和 browser 检查均 `passed`。这是"对应 E2E"的可判定形态。 | `verified` |
| `beta` | `dev` 条件之外，至少一份 `docs/release-evidence/` 或 `docs/quality/` 下被跟踪的人工验收文档；工具只核验存在与跟踪，内容由人判断。 | `manual-attested` |
| `stable` | 工具拒绝。D8 禁止切换已发布 Release 的 `prerelease`，而 `stable` 要求 `prerelease=false`，两者冲突；见 `docs/prd/questions/stable-channel-prerelease-flip.md`。 | 不适用 |

操作入口是 `scripts/release.sh promote TAG CHANNEL --deployment-run HOST=RUN_ID ...`
`[--evidence PATH ...]`。它先运行 exact-tag remote audit 且要求全部通过，再校验转换与门禁并
下载核对部署证据，然后只向工作区写入一份晋级证据文档与一条 ledger 记录，并打印下一步。它不
push、不改 GitHub。这两个文件作为 docs PR 经当前 Git workflow 评审合入，与 release intent
的绑定方式一致。`audit` 会核验 `promotions` 的结构与顺序、`max_channel`，以及每条记录的部署
run 仍然存在、属于该 Host 的部署 workflow、由 `main` 上的 `workflow_dispatch` 触发并成功。
保留制品有生命周期，因此审计不重新下载 `evidence.json`；记录中的 SHA-256 与证据文档是持久
记录。

降级与撤回按本节前文允许，但尚无工具实现，作为后续任务。

## 4. Git Revision 与 Build Identity

每个可运行 Build 必须同时显示：

```text
LMDJ 1.0.12.0 · dev · g34236c06
```

正式 Build Manifest 保存：

- Product Build Version；
- Channel；
- 完整 40 字符 Git SHA；
- Product Assembly lock hash；
- 构建时间与构建平台；
- 产物 hash。

短 SHA 只用于显示，比较、部署、tag 和验证必须使用完整 SHA。

Build Manifest 是 checkout 后由构建流程生成的产物，不能反向写回同一个源码
commit。源码中的 `assembly.lock.json` 也不能保存包含它自身的 Git SHA，否则会形成
无法收敛的自引用。

发布身份的权威核验链按此顺序记录，任何一环都不能由另一环推断：Product Build -> signed tag -> tag revision -> merged PR -> source revision -> snapshot provenance/witness -> merged-main Proof revision -> evidence-only documentation revision。分支本地 Proof 不能填充 merged-main Proof 一环；后写的证据文档也不能把自己的 revision 伪装成被验证的产品 revision。

## 5. Tag 规范

### 5.1 总原则

- 所有正式 tag 必须是 annotated tag；环境支持时使用签名 tag。
- tag 是不可变身份，不得移动、覆盖或复用。
- tag 创建前必须解析并记录完整目标 SHA。
- 创建 tag 不代表获准 push、创建 GitHub Release、部署或发布。
- 一次整体发版授权覆盖 push tag、Release、部署和渠道晋级，各段仍需独立证据；用户明确限制范围时遵循较窄授权。
- 错误 tag 不移动；创建更正 tag，并在事故记录中说明旧 tag。
- 不对普通工作分支的每个 commit 打 tag。

验证命令：

```bash
git cat-file -t <tag>
git rev-list -n 1 <tag>
git for-each-ref "refs/tags/<tag>" \
  --format='%(refname:short) %(objecttype) %(objectname) %(subject)'
git tag -v <tag>
```

如果 tag 未签名，`git tag -v` 可以失败，但必须通过 annotated object、目标 SHA 和
tag message 验证。正式 Beta/Stable tag 必须签名。

### 5.2 计划与阶段 tag

尚无可运行 Build 的设计、计划、Spike 或封存阶段使用：

```text
lmdj-m<MILESTONE>-<stage>.<revision>
```

允许的 `stage`：

```text
design
plan
spike
parked
```

示例：

```text
lmdj-m1-plan.1
lmdj-m1-plan.2
lmdj-m2-spike.1
```

阶段 tag 不属于 Product Build Version，不得显示为用户产品版本。

当前基线：

| Tag | Target | 含义 |
| --- | --- | --- |
| `lmdj-m1-plan.1` | `34236c062d5982d22701ad0482518a29bfaefa60` | M1 Headless Core Proof 计划完成架构 Review，尚未实现 |

### 5.3 Product Build tag

已产生可运行 Product Assembly 的版本使用：

```text
lmdj-v<MILESTONE>.<MINOR>.<BUILD>.<PATCH>
```

示例：

```text
lmdj-v1.0.1.0
lmdj-v1.0.12.1
```

Product tag 只指向已合入 `main`、CI 通过并生成匹配 Build Manifest 的提交。Channel
不写入 tag 名称。

New Product tags require merged-main Proof first. 该 Proof 必须绑定将成为 tag target
的精确 `main` revision、Product Build 与 Assembly lock hash；创建、签名、push tag、
Release、部署和 Channel promotion 仍是分别验证的动作；整体发版授权覆盖这些转换。

### 5.4 Module、Contract 与 Provider tag

只有需要独立发布、缓存或被 Assembly 锁定的单元才打独立 tag：

```text
module/<module-id>/v<semver>
contract/<contract-id>/v<semver>
provider/<provider-id>/v<semver>
```

示例：

```text
module/project-io/v0.1.0
contract/lmdj.project/v1.0.0
provider/local.proof.success/v0.1.0
```

这些 tag 只标记对应目录/Contract 的版本身份，不表示整个 LMDJ Product Build
已经晋级。

## 6. Module Package Version

每个 Core Package、Host-neutral Module 和可独立构建 SDK 使用 SemVer：

```text
MAJOR.MINOR.PATCH
```

并在自己的 `module.json` 中声明：

```json
{
  "contract": "lmdj.module.v1",
  "module": "project-io",
  "version": "0.1.0",
  "api_version": 1,
  "dependencies": {
    "foundation": "0.1.0",
    "authoring-domain": "0.1.0"
  }
}
```

版本变化规则：

- `MAJOR`：公开 API/ABI 或持久化语义不兼容；
- `MINOR`：向后兼容的新公开能力；
- `PATCH`：不改变公开行为的修复；
- 只改内部实现且不发布新 Package 时，可以不立即打 Module tag；
- Assembly 必须锁定精确版本，不使用浮动范围；
- 模块版本不能从 Product Build Version 推导。

初始内部模块可以从 `0.1.0` 开始；一旦声明稳定公开接口，再进入 `1.0.0`。

不对 Package 内每一个普通源码函数单独打版本。函数只有在成为可被其他模块、
Host、MCP 或远程 Provider 独立调用和替换的公开 Capability 时，才获得独立
Contract ID/version；其实现仍由所属 Module 或 Provider SemVer 管理。

## 7. Contract Version

Contract 同时具有稳定 ID 和 SemVer：

```text
Contract ID: lmdj.project.v1
Contract version: 1.0.0
```

- ID 中的 `v1` 是兼容性 Major。
- Schema metadata 保存完整 `1.0.0`。
- 向后兼容的可选字段增加 Contract Minor。
- 语义澄清或验证修复增加 Contract Patch。
- 删除字段、改变字段含义或收紧到破坏合法旧数据时创建 `v2`。
- Provider Capability Contract、Project Contract、Assembly Contract 和错误 Contract
  分别演进，不能共享一个万能版本。
- Contract tag 必须对应 Schema、正反例 Fixture 和 Conformance Test。

## 8. Provider 与 Model Version

Provider 必须分离四个身份：

```text
Provider ID
Provider implementation version
Capability Contract ID/version
Model or rule asset identity
```

示例：

```json
{
  "provider_id": "local.proof.success",
  "provider_version": "0.1.0",
  "capability": "proof.candidate.v1",
  "capability_version": "1.0.0",
  "model": {
    "id": "deterministic-proof-rule",
    "version": "1",
    "artifact_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

Provider SemVer 规则：

- 改变 Provider SDK 接口要求或同一输入的公开输出语义：Major；
- 增加兼容 Capability、平台或可选参数：Minor；
- 质量修复、性能修复或内部依赖修复且 Contract 不变：Patch；
- 换模型权重必须更新 Model Identity，即使 Provider SemVer 只增加 Patch；
- 使用外部模型或规则资产时，Provider Attempt 必须记录上述全部身份、参数和
  输入/输出 Artifact hash；
- 纯代码 Provider 明确记录 `model_identity: null`，并记录 Provider SemVer 和本次
  加载的实现 Artifact hash，不能伪造一个模型版本；
- 远程 Provider 不能只记录“latest”或云端别名。

Provider Package、Capability Contract 和模型版本可以独立变化。Assembly 通过精确
lock 把它们组合成一个可复现 Product Build。

同一个 Provider 可以同时实现多个、各自演进的 Capability：

```json
{
  "provider_id": "local.audio-intelligence",
  "provider_version": "0.4.2",
  "capabilities": [
    {"id": "sample.slice.v1", "version": "1.2.0"},
    {"id": "stem.separate.v1", "version": "1.0.1"}
  ]
}
```

只改变 `sample.slice.v1` 的兼容可选输出时，增加它的 Contract Minor 和 Provider
实现版本；`stem.separate.v1` 不跟着改变。这样保留独立组合能力，同时避免给内部
私有函数制造无意义的版本号。

## 9. Product Assembly 与 Version Lock

Product Assembly 声明想要的模块和 Provider；生成的 lock 声明实际解析结果：

```text
products/lmdj/
  version.json
  assembly.json
  assembly.lock.json
```

`version.json` 是四段 Product Build Version 的源码真相：

```json
{
  "contract": "lmdj.product-version.v1",
  "product": "lmdj",
  "milestone": 1,
  "minor": 0,
  "build": 1,
  "patch": 0
}
```

`assembly.lock.json` 必须包含：

- Product Build Version；
- 每个 Module 的精确版本；
- 每个 Contract 的 ID、版本和 schema hash；
- 每个 Provider 的精确版本；
- 模型/规则 Artifact hash；
- Assembly hash。

lock 文件由工具生成，不手工编辑。Build Manifest 在 checkout 之后把 lock hash 与完整
Git revision、Channel、构建平台和产物 hash 绑定起来。

M1 PR 6 完成 Assembly Policy 边界时创建 `lmdj.assembly.v2` Contract
`2.0.0`：Region、数据分类和权限策略成为必填 Assembly 字段。该必填字段会拒绝
旧形状，因此保留 `lmdj.assembly.v1` `1.0.0`，并按 breaking change 创建 `v2`。
Provider lock 必须绑定与运行时 `ProviderRegistration.artifact_sha256` 一致的
确定性 source-package identity，不能只绑定 `module.json`。

### 9.1 Product Build 文档快照门禁

本地构建、普通 CI 和 Pull Request Preview 不分配新的永久文档快照。任何已分配
Product Build 并准备交付团队测试（`canary`、`dev`、`beta`）或正式发布
（`stable`）的构建，在对应发布/晋级门禁前必须冻结匹配的架构门户快照：

```bash
scripts/docs-site.sh version MILESTONE.MINOR.BUILD.PATCH CHANNEL
```

快照必须来自干净工作区，Product Build 与 `version.json` 精确一致，并记录完整 Git
revision 和 Assembly Lock hash。`/versions/PRODUCT_BUILD/` 是不可变说明书；current
文档继续跟随 `main`。同一 Build 的 Channel 晋级复用既有快照并在独立发布记录中
追加证据，不重写快照。冻结说明书不产生新的 Product、Module、Provider 或 Contract
版本，也不授权 tag、push、Release、部署或 Channel 晋级。具体规则见
`docs/governance/architecture-portal.md`。

## 10. M1 开发版本表

M1 采用六个顺序 PR Gate；Build 编号已经分配，失败或取消也不复用：

| Gate | 范围 | Product Build | Channel |
| --- | --- | --- | --- |
| Plan baseline | 已 Review 的实施计划 | 无 Product Build；`lmdj-m1-plan.1` | 无 |
| PR 1 | Build Lab + Contracts | `1.0.1.0` | `dev` |
| PR 2 | Authoring Domain + Project I/O | `1.0.2.0` | `dev` |
| PR 3 | Cooker + Offline Runtime | `1.0.3.0` | `dev` |
| PR 4 | Provider SDK + Facade/C ABI | `1.0.4.0` | `dev` |
| PR 5 | CLI + MCP | `1.0.5.0` | `dev` |
| PR 6 | Product Assembly + Headless Proof | `1.0.6.0` | `dev` |

分支内未合并构建显示候选 Build 加 SHA：

```text
1.0.3.0 · canary · g<short-sha>
```

只有对应 PR squash-merge、CI 和 Build Manifest 校验通过后，Integration Owner 才能
创建 `lmdj-v1.0.<BUILD>.0` tag。

## 11. 每份未来实施计划的强制章节

每一份 LMDJ 实施计划必须包含 `## Version Management`，并明确：

1. 影响哪种版本域：Product、Module、Contract、Provider、Model；
2. 起始版本和目标版本；
3. bump 原因；
4. 每个 PR/阶段对应的 Product Build 和 Channel；
5. 要修改的 `version.json`、`module.json`、Schema 或 Provider Manifest；
6. Contract/Project 兼容性与迁移影响；
7. tag 名称、目标 SHA 条件和 tag message；
8. 哪些验证通过后才能打 tag；
9. 是否允许发布、push、渠道晋级或部署；
10. rollback 时复用哪个不可变版本。

如果计划不产生版本变化，也必须写：

```text
Version impact: none
Reason: 该计划只重构测试夹具，不改变公开产品行为、Module API、Contract、Provider、模型身份或 Product Assembly
```

缺少该章节的计划不得进入实施。

## 12. 操作边界

以下状态必须分别报告：

```text
designed
planned
implemented
committed
merged
tagged
built
channel-promoted
released
deployed
release-verified
```

前一状态不自动授权后一状态。尤其：

- commit 不授权 tag；
- tag 不授权 push；
- push 不授权 Release；
- Release 不授权部署；
- 部署不等于生产验证。

### 12.1 标准 Release 控制面

正常发布只通过 `scripts/release.sh` 与受保护 workflow 完成。每次操作先运行 exact-tag
remote audit；随后 `prepare`、单 tag push、Draft 创建、Draft 发布、Runtime deployment 与
Channel promotion（`promote`，见 §3.1）分别验证。按照 `AGENTS.md`，一次整体发版授权覆盖
这些转换；每段通过后继续执行已覆盖的下一段，不重复询问。仅当门禁失败、范围缺失、
必需外部审批或显式用户限制时停止。命令输出本身不是授权来源。

`docs/release-evidence/release-intents.json` 是经 review 的 release intent ledger：它记录允许
考虑的 exact identity、target、disposition、channel、profile 与 evidence path，但不缓存或
替代 Git/GitHub 当前状态。只有 `releasable` intent 能开始 prospective mutation；
`published` 只读审计，`abandoned` 与 `superseded-unreleased` 拒绝发布。远端 tag 与 Draft 是
live control plane 派生状态，不写回 ledger 充当缓存。

源码 Product Build 与匹配 immutable snapshot 的分配不要求同时创建 release intent；这是让
受保护 `main` 的 squash merge 先产生唯一、精确 target SHA 的必要顺序。Release intent 是后续
独立 review 的授权记录，只能在该 squash SHA 已存在于 protected `main` 后绑定；branch-only 或
pre-squash SHA 不是合法 release target。当前 Product Build 在 ledger 中允许零或一个 intent，
零表示尚未授予发布意图，不削弱 manifest、Assembly lock、component digest 或 immutable
snapshot 校验；重复 current intent 必须 fail closed。一个 current intent 存在时，exact-target、
merged-main Proof、CI、main ancestry 与后续所有 release gate 仍全部适用。

T7 曾将 prospective policy 切换为 `self-test-v1`。2026-09-08 B2 的 consumer 与
`tools/release/policy.json` 同一 Task 将现行协议设为 `complete-test-v2`：`releasable`
intent 恰好引用一种完整证据，旧 `self_test_evidence` 或新增 `batch_test_evidence`，
不得混用。没有 reference 不能退回旧 scope。两种来源都必须引用一次通过的完整
16-suite 自测；旧 `lmdj.ci-scope.v2` 的 14 lanes 即使 `mode=full`、`trusted_head=true`、
`Change Scope` / `PR Gate` 均绿色，也只能解释旧协议，不能绕过新候选的 TSan / Release
stress 要求。T5 切换以新 producer + consumer 的真实演练为前置条件；未通过不得
合入切换。切换后 `ci.yml` 只保留 reusable 执行，不再接受每日或手动产品请求；
历史完整来源的严格 reader 保留，不能退回 legacy prospective fallback。
新手动全量与自动增量共用持久调度，完整候选证据契约不变。
自测红色不构成 PR merge gate；正式版本仍手动发布。

Owner 在 reviewed intent 中保留 `merged_main_run_id` 与 exact `target_revision`，另增闭合的
`self_test_evidence`：`schema=lmdj.ci-self-test.v1`、`request_kind`、`control_revision`、
`run_attempt`、`policy_revision` 和 `evidence_digest`。这些字段只能来自已验证的真实 verdict，
不自动写入 intent，也不从输入参数或绿色总结猜测。`Core CI` 由稳定 workflow ID 与
`.github/workflows/ci.yml` 及 canonical repository 共同绑定；动态 `run-name:` 不参与授权。
GitHub `run.head_sha` 是 control revision，不要求等于 candidate target：两者各自验证为
protected main 历史，且 control 不早于可信 producer 部署。必须精确绑定同一 run / attempt、
成功的 verdict job、完整 suites / required job 结果、适用 policy 与 canonical digest。
日测或 node 的现成通过证据可由 Owner 显式引用到同 SHA 候选，不重复补测；skip、失败、
混合 attempt、缺少任一 suite、错误 SHA 或过期证据均不能授权候选。

新的 verdict artifact 当前保留 30 天。过期或缺失为 `unverifiable`；身份、摘要、完整性或
结果冲突为 `conflict`；传输与分页故障为 `external-error`。恢复须另行授权在 ref `main` 上
向 `self-test-report.yml` 发送 `batch_operation=reconcile`，`batch_request` 为闭合
`{"id":"<new-stable-request-id>","kind":"candidate","target":"<exact-main-SHA>"}`，
`journal_config` 留空以使用可信源码中的固定调度器，并独立 review intent 更新。
同 ID 同目标的重送只恢复原请求；真正重新测试使用新 ID。显式诊断使用 `kind=node`，
同样固定全 16-suite，不推进自动 processed SHA，也不被后续 main 替换。
不能把 SHA 用作 dispatch ref，也不能 Re-run jobs（producer 当前只支持 attempt 1）。已 `published`
的旧协议 intent 继续原只读审计，新协议 intent 的持久 reference 纳入 release plan digest，
并由 `lmdj.release-plan-marker.v2` 显式保留完整 CI 身份；fresh remote audit 对比 marker
与 intent，旧 v1 marker 不能证明新添的自测引用。Published 读取当时的 recorded attempt，
后来的 rerun 不覆盖其历史；prospective 仍检查 latest attempt，不能借旧通过结论掩盖新失败。
二者仍验证不可变 tag、签名、Release、asset 与 plan marker，不因短期 artifact 过期而改写
历史，也不能只凭 intent 自称 published 就认定发布。自测通过本身不授权任何 release mutation。

增量批次的闭合 `batch_test_evidence` 使用 `lmdj.ci-batch-release-reference.v1`：保存完整
frozen `request`（id/kind/base/target/control/policy/selection/origin_run）、
`executor_control_revision`、`executor_event`、`run_attempt=1`、
`origin_record_digest`、`admission_record_digest`、`evidence_digest`。Executor event 是
workflow_dispatch/push/workflow_run/schedule 闭集，不能从排队 request kind 推断。
来源只由 reviewed policy 的 repository/workflow ID、workflow path 与 producer 下界认证，
不得信任 artifact 自称来源。原 origin 与 executor controller artifact 必须仍在有效保留期，
且分别证明原请求及同 epoch 的 durable-claim admission；这是可信 producer attestation，
不是独立重放最新 Issue Journal。再完整读取 verdict/execution/needs 三文件、真实 API jobs，
独立重算 exact target、current/frozen/executor policy 一致的全 16-suite passed verdict。
focused、none、债务、旧 policy、缺 artifact 或跨 SHA/attempt 拼接一律不授予候选资格。

新 batch reference 全部写入 plan `ci` 及永久 `lmdj.release-plan-marker.v3`（带冻结 changelog 时为 v4）；v1/v2 marker
不证明 batch 引用，旧 self-test v2 与 legacy v1 历史不迁移。仅 `Disposition.PUBLISHED`
可读取 recorded attempt 的稳定来源/target/control/event provenance 而不再次要求短期 artifact
或永远不变的 current policy；仍必须通过实际 immutable tag、signer、Release、assets 和
精确 v3/v4 marker 验证。allocated/abandoned/superseded 不能使用这条历史例外。
本协议不自动选择候选，不修改既有 intent。手动精确 full 能力由上述统一入口保留；
旧 `ci.yml` dispatch 的退役不删除历史来源验证，也不降低完整证据要求。

历史例外（historical exception）只解释控制面生效前不可改写的 exact 只读事实。只有 remote
audit 可以报告 `ok-with-historical-exception`，并必须在 human/JSON evidence 中显式列出；
`prepare`、tag push、Draft 创建与 publish workflow 都不能消费它来满足 prospective gate。

Release `profile` 从受保护 policy 选择确定性 builder、verifier 与闭合 asset inventory。不能由
操作者临时增加、覆盖或猜测资产。`create-draft` 只创建或 reconcile Draft；遇到错误、额外或
同名不同内容的资产时保留 Draft 并停止调查，不覆盖既有内容。
Notes、asset inventory 与 plan 的结构和 digest 是确定性的；独立 OpenPGP 签名会包含签名时间，
因此不承诺重新签名得到逐字节相同的 signature。重试复用并验证已经持久化的 exact signature，
不会用新签名覆盖它。

带冻结日志的 Web Hosts Product intent 可携带闭合 `changelog` 文档
（`lmdj.release-changelog.v1`），精确匹配 tag、Product Build、profile 与 target。
该文档记录固定已发布基线、完整提交范围、分类条目与排除理由；PR 审查负责文字事实，
prepare 负责重验真实 Git 范围。文档进入 canonical plan，统一 renderer 同时供 Release
与后续 doc-site 投影使用。永久 `lmdj.release-plan-marker.v4` 保留既有 CI 身份并额外
绑定结构化内容与 notes 摘要；Draft、published verifier 与 remote audit 必须核对完整
正文，不接受仅 marker 正确但文字已变的 Release，也不新增第七项资产。
旧无 changelog 的历史 intent/plan 保持 v1–v3，不重写公开历史。该扩展不自动切换所有
旧调用者；新总控的强制日志准入与网站发布验证需完成各自接入，不能用兼容路径宣称
完整自动发布已实现。

公开 publication 只由 dispatch-only `publish-release.yml` 完成。Workflow 以 exact tag、numeric
Release ID 和 plan digest 重建并验证 Draft，通过受保护 `release` Environment 的 exact-main
策略门后，以一次 PATCH 设置 `draft=false`、精确 prerelease 与 exact make-latest policy，随后重新验证 metadata
与资产不变。GitHub Release API 没有本流程可依赖的强条件更新契约，所以 mutation 前后验证用于
检测并 fail closed，而不宣称消除 TOCTOU。当前单人维护者模式明确要求零 required reviewer，
`prevent_self_review` 不启用，并且只允许 exact `main` branch policy；显式 workflow dispatch 与
整体发版授权是人工边界，remote audit 对 GitHub 侧配置 fail closed。Publication 不触发
Runtime deployment；后者保持 manual-only exact-tag dispatch，并与 Channel promotion 分离。

所有 non-stable Release 都是 prerelease 且 `latest=false`。Stable 是否成为 `latest` 只由 ledger
中的显式 intent 与 stable policy 决定，不能依据版本排序或当前 GitHub latest 推断。每个
published Release 与 tag 都是不可变历史：正常工具不得移动 tag、替换资产、重写 metadata 或删除
Release。发现 drift 或不确定 publish 结果时，先按 exact object/Release ID 做只读 reconcile，
再以独立 incident 和纠正身份处置；不得通过改写历史制造成功。

## 13. 当前状态

截至 2026-07-30：

| 项目 | 状态 |
| --- | --- |
| M1 产品与内核设计 | 已确认 |
| M1 Headless Core 实施计划 | 已 Review |
| 当前阶段 tag | 本地 signed annotated tag `lmdj-m1-plan.1` |
| Tag target | `34236c062d5982d22701ad0482518a29bfaefa60` |
| Product Build | 尚未产生 |
| 当前 Channel | 无 |
| Tag push / GitHub Release / 部署 | 未授权、未执行 |

## 14. 规范来源

- [Chromium Version Numbers](https://chromium.googlesource.com/playground/chromium-org-site/+/refs/heads/main/developers/version-numbers.md)：四段 Product Build 版本的参考。
- [Chrome Release Channels](https://www.chromium.org/chrome-release-channels/)：Channel 与 Build 身份分离的参考。
- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)：Module 与 Provider 实现版本规则。
