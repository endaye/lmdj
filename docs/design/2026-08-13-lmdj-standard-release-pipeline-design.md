# LMDJ Standard Release Pipeline Design

日期：2026-08-13

状态：规格已批准

修订：2026-09-08 — B2 激活 `complete-test-v2`：新候选必须恰好引用旧完整 16-suite
`self_test_evidence` 或新完整 16-suite passed `batch_test_evidence`，缺失/混合引用、
focused/none、旧 14-lane scope 都不能授权。新来源由 reviewed policy 的固定
repository/workflow/path/producer 下界认证；原 origin/admission controller artifact 证明
可信 producer durable-claim attestation（不声称重放最新 journal），verdict/execution/needs
三文件与真实 API jobs 独立重算 exact target 与 current/frozen/executor policy。
新 batch 引用及真实 `executor_event` 完整进入 `lmdj.release-plan-marker.v3`；
旧 self-test v2 与 legacy v1 不改写。仅实际 `Disposition.PUBLISHED` 历史使用原 recorded
attempt provenance 而不重审短期 artifact；tag/signer/Release/assets/精确 v3 marker 仍必需。
此消费者切换不选择或发布任何版本，也不改变测试触发。下述 2026-09-07 修订保留为
旧 self-test 16-suite 来源说明，完整字段以版本治理 §12.1 为准。

修订：2026-09-07 — T7 consumer 与 prospective policy 同一 Task 合入主干时，后续
`releasable` intent 一律改用 `self-test-v1`，本页旧 exact-main scope 描述仅保留为历史协议。
完整自测是 16 suites（含 TSan / Release stress），不是旧 14-lane `full` 或 PR gate。
Owner 可显式复用同 target 的有效日测 / node / candidate verdict；`run.head_sha` 是可信
control，与 candidate SHA 分别验证为 main 历史，不能再假定二者相同。
Intent 通过现有 target / run ID 加闭合 `self_test_evidence`（schema、request_kind、
control_revision、run_attempt、policy_revision、evidence_digest）绑定已验证事实；新 release
plan 的 `ci` 同时记录 target 与此 reference；新的 `lmdj.release-plan-marker.v2` 显式保留
完整 CI 身份，fresh remote audit 必须逐项匹配，旧 v1 marker 不证明新添 reference。
Published 读取 recorded attempt，后续 rerun 不覆盖历史；prospective 仍检查 latest。稳定 workflow
ID / path / repository、可信 producer 下界、同 attempt 的成功 verdict job、全部 suites / jobs、
适用 policy、canonical digest 与 30 天有效 artifact 缺一不可。过期须在 ref main 上以同 target
新 dispatch 并 review 更新 intent，当前不接受 Re-run jobs。旧协议已 published 审计保持只读，
新协议 published reference 仍与不可变签名 / tag / Release / assets / plan marker 联合验证，
不依赖短期 artifact 永久留存。旧入口的删除须另获授权完成真实 producer / consumer 演练，
不能恢复旧 14-lane prospective fallback。日测不阻 merge、不等于日发版；发布继续逐边界人工
授权。详细字段约束以 `docs/governance/version-management.md` §12.1 为准。

修订：2026-08-26 — §8.4 preflight/publish 验证边界。GitHub 不向只读身份暴露 Draft
Release，Draft 专属验证从 preflight 移交 publish job（维护者批准，#335）。

修订：2026-09-01 — 后续 Web 产品发布采用 `web-hosts` profile：Creator 与 Runtime 各自
贡献 ZIP、checksum 和 detached checksum signature，一个 Product Release 精确六资产。
Creator 使用 `https://lmdj-creator.netlify.app/`，Runtime 使用
`https://lmdj-runtime.netlify.app/`；两条部署都是独立 manual-only dispatch，具有独立
Environment、Site credential、evidence 与 exact prior rollback，Release publication 不产生
deployment fan-out。历史 `1.0.40.0` 及更早的三资产 Runtime Release/部署保持不可变；本修订
只约束后续获准 Product Build。

修订：2026-09-06 — §12 新增显式子命令 `scripts/release.sh hydrate`。它是稳定接口里
唯一被允许写本地 Git object store 的子命令，专门补全 release intent 记录的
`target_revision` 对象；audit 仍然只读，缺失 target 只报告 `unverifiable` 并在消息里
写明 remedy，绝不 fetch-on-miss（决策
`docs/prd/decisions/2026-09-06-release-intent-hydrate-subcommand.md`，#332）。

## 1. 结论

LMDJ 将 tag、GitHub Release 与部署从临时人工命令收敛为一个仓库拥有、分段授权、
默认 fail closed 的发布控制面：

```text
release intent
    |
    v
prepare (local only)
    |
    v
push-tag (exact tag only)
    |
    v
create-draft (Draft GitHub Release only)
    |
    v
publish-release.yml (protected release Environment)
    |
    v
published GitHub Release

deployment / Channel promotion remain separate explicit workflows
```

正常入口是 `scripts/release.sh`，远端发布只由
`.github/workflows/publish-release.yml` 由显式 `workflow_dispatch` 启动，并通过受保护的 `release`
GitHub Environment exact-main 策略门完成。当前单人维护者模式不配置 reviewer。发布工作流不持有
Product tag 或 Release checksum 私钥，不构建产品，不部署，不提升 Channel。

仓库规则与机器校验拥有发布语义；一个薄的 repo-local Codex skill 只负责引导操作者调用
这些入口、展示下一授权边界，不复制规则、不持有密钥、不绕过每次显式授权。定期 `audit` 只读核对
manifest、快照、protected `main`、CI、tag、Release、资产与签名，不自动补 tag 或 Release。

## 2. 设计输入与已知事实

2026-08-13 的一次人工清点补齐了 14 个此前应存在的 tag 与 GitHub Release：3 个 Product
Release 和 11 个 Module Release。该操作证明当前仓库已有足够的版本、快照、CI、package、
签名与 GitHub API 原语，但也暴露出以下缺口：

- “哪些身份应发布”依赖人工跨文档判断，没有闭合的机器可读发布意图；
- tag 创建、push、Draft、公开 Release 与部署缺少统一、可恢复的状态机；
- Product、Module、Contract、Provider 的 Release 类型与资产集合容易被临时命令混淆；
- `gh release create` 能一步公开 Release，授权面过大；
- 现有 `.github/workflows/deploy-web-runtime-host.yml` 监听 `release.published`，因此公开
  Runtime Host Release 会间接启动部署，这与“Release 不授权部署”的治理边界冲突；
- `scripts/web-runtime-deploy.sh verify` 在 macOS 的空临时 `GNUPGHOME` 中导入 public key
  时会尝试连接 `gpg-agent`；仅公钥验证不应依赖 agent，当前会出现
  `gpg: can't connect to the gpg-agent: IPC connect call failed` 并以状态 2 失败。

上述 14 个 Release 是本设计的迁移基线，不是永久数量。实施与每次审计必须重新读取
canonical GitHub 状态，不能把本节当作当前外部真相缓存。

## 3. 目标

- 用一个稳定脚本统一 Product、Module、Contract 与 Provider 的 release preparation。
- 让 local tag、remote tag、Draft Release、published Release、deployment 和 Channel
  promotion 保持独立授权与独立证据。
- 所有 Product tag 都是 immutable signed annotated tag；其他正式 tag 至少是 annotated，
  并按 policy 要求签名。
- Product Release 只上传从 exact tag target 构建并验证的精确资产。
- Draft 创建可安全重试；发布前任一不一致都留下 Draft，不产生半公开 Release。
- 已发布 Release 默认不可由正常工具修改、替换资产或重新解释身份。
- 可检测漏 tag、漏 Release、错误资产、错误签名、漂移与被错误发布的 abandoned candidate。
- 让 agent 与人工操作者使用同一条仓库路径，而不是维护两套流程。
- 保持 Release publication 与 Runtime Host deployment 完全解耦。

## 4. 非目标

本设计不包含：

- 为当前 `1.0.20.0` 或未来候选自动决定“应该发布”；
- 自动 push branch、创建 PR、merge、创建 Release、部署或 Channel promotion；
- 在 GitHub Actions 保存 Product tag private key、checksum private key 或其口令；
- 以 Release publication 触发 Netlify、Creator、Portal 或其他生产部署；
- 修改 Core、Host、Provider、Contract、Project Truth、Runtime Snapshot 或 Product behavior；
- 把 branch-local Proof、快照、PR CI 或 tag 当作 merged-main Proof；
- 自动为所有历史 commit 打 tag；
- 发布已明确标记为 `abandoned`、`unshipped`、`superseded-unreleased` 或仅存在于普通
  工作分支的身份；
- 重新生成、替换或删除既有 GitHub Release 资产；
- 用 agent skill 代替项目治理、测试、GitHub Environment 配置或真实 mutation 授权。

## 5. 核心决策

| ID | 决策 |
| --- | --- |
| D1 | 正常发布使用 `prepare -> push-tag -> create-draft -> verify-and-publish` 四段状态机。 |
| D2 | `prepare` 是唯一会使用 private signing keys 的阶段，并且只在可信本地执行。 |
| D3 | GitHub Actions 只持有 public trust anchors 与最小 `contents: write`，只发布已存在且重新验证通过的 Draft。 |
| D4 | Product、Module、Contract、Provider 使用同一控制器、不同闭合 policy；不得凭 tag 文本猜资产。 |
| D5 | 一个 tracked release-intent ledger 记录“允许发布什么”，外部 GitHub 状态仍须实时核验。 |
| D6 | Product canary/dev/beta 是 prerelease；stable 才是普通 Product Release。Module Release 默认非 prerelease 且 `latest=false`。 |
| D7 | Runtime Host deployment 改为仅 `workflow_dispatch`，Release publication 不再产生部署事件。 |
| D8 | 已发布 Release 是不可变审计边界；正常工具拒绝编辑 body、替换资产、切换 prerelease 或删除 Release。 |
| D9 | `audit` 永远只读；发现缺口后仍需逐段显式授权修复。 |
| D10 | repo-local skill 是薄导航层；所有规则、分类、验证与状态都由仓库文件和 GitHub 实况拥有。 |

## 6. Source of Truth 与数据模型

### 6.1 既有身份真相

发布工具继续从以下 active sources 读取身份，不手填版本：

- Product：`products/lmdj/version.json`、`assembly.json`、`assembly.lock.json`；
- Module/Host：对应 active `module.json`；
- Contract：active schema metadata、fixtures 与 conformance tests；
- Provider：active Provider manifest、Capability Contract 与 Model identity；
- Product documentation snapshot：Architecture Portal `versions.json`、versioned metadata、
  snapshot provenance/witness；
- Git/CI：canonical `origin/main`、exact 40-character SHA、GitHub Actions run API；
- remote publication：canonical remote tag object 与 GitHub Release API。

短 SHA、branch name、Release `targetCommitish`、本地同名 tag 和 mutable `latest` 均不构成
发布身份真相。

### 6.2 Release intent ledger

实施新增一个 tracked、reviewed、闭合 schema 的 operational ledger，例如：

```text
docs/release-evidence/release-intents.json
```

它记录 release authorization intent 与 lifecycle disposition，不声称缓存 GitHub 当前状态。
源码 Product Build 与匹配 immutable snapshot 的分配不创建 release intent；允许它们随普通
Product Build Task 通过受保护 `main` 的 squash workflow 落地，并在 ledger 中暂时没有该 current
Product identity 的 intent。只有 squash merge 产生精确 protected-main SHA 后，后续独立 review
才能新增或更新 intent 并把 `target_revision` 绑定到该 SHA；branch-only/pre-squash SHA 一律无效。
因此 active current Product identity 的 intent cardinality 是零或一，重复记录 fail closed；零
intent 不豁免 active manifests、Assembly/lock/component digest 与 matching immutable snapshot
校验，一个 intent 存在时则继续强制 exact-target、merged-main Proof、CI、main ancestry 与全部
后续发布门禁。

最小形状为：

```json
{
  "schema": "lmdj.release-intents.v1",
  "entries": [
    {
      "tag": "lmdj-v1.0.16.9",
      "kind": "product",
      "identity": "1.0.16.9",
      "target_revision": "d1d8bb6a629b6e05b86b3c8843870ef27edcfe5c",
      "channel": "canary",
      "disposition": "published",
      "profile": "web-runtime-host",
      "snapshot": "1.0.16.9",
      "merged_main_run_id": 31634688566,
      "evidence_paths": [
        "docs/quality/2026-08-13-merged-main-proof.md"
      ]
    }
  ]
}
```

字段使用闭合 allowlist：

- `kind`: `product | module | contract | provider`；
- `disposition`: `allocated | releasable | published | abandoned | superseded-unreleased`；
- Product `profile`: 初始仅 `core-package | web-runtime-host`；
- 非 Product `profile`: 初始仅 `source-only`；
- `channel`: Product 必须为 `canary | dev | beta | stable`，其他 kind 必须省略；
- `target_revision` 必须是完整 SHA，并与 active identity 的 introducing revision 一致；
- `merged_main_run_id` 对 Product 必填；对独立 Module/Contract/Provider 发布也必须绑定
  覆盖其 target 的成功 protected-main CI run；
- `evidence_paths` 只能是 canonical repo-relative tracked paths，不能是 URL、临时路径或
  secret-bearing log。

Top-level 另允许一个闭合的 `historical_exceptions` 数组，只用于让新审计器解释控制面生效前
已经存在且不会被改写的外部状态。每项必须固定 exact tag、target SHA、可选 numeric Release
ID、`observed_before` UTC 时间、单一 exception code、具体 reason 与 evidence paths。初始 code
只允许：

- `pre-governance-tag-scheme`：例如不符合现行四类 tag 语法的既有 `v0.2.0` Release；
- `pre-pipeline-ci-evidence`：例如 exact-main push run 没有成功，但已发布身份有明确的旧 CI、
  Nightly 或部署证据。

历史例外只能关联 `published`、`abandoned` 或 `superseded-unreleased` 的只读身份，或解释一个
现行 tag schema 之外的 legacy artifact。任何 `allocated`/`releasable` entry、pipeline
introducing commit 之后的新 tag/Release、缺少 exact immutable identifiers 的记录都不得使用。
`prepare`、`push-tag`、`create-draft` 与 publish workflow 一律拒绝消费历史例外；只有 `audit`
可以将匹配项报告为 `ok-with-historical-exception`，并必须在 human/JSON output 中显式列出，
不能把它伪装成满足当前 prospective gate。

Ledger 的作用是拒绝“猜测发布”。只有 `releasable` 可以开始新流程；`published` 只能
audit；`abandoned` 与 `superseded-unreleased` 永远拒绝发布。`tagged` 与 `draft` 是从
canonical Git/GitHub 实时派生的 operational state，不写回 ledger，避免在四段流程之间为
镜像外部状态而制造额外 PR。状态变更通过正常 PR review 进入 `main`，但 ledger 本身不授权
tag、push、Release 或部署。

为了避免外部状态反向写进同一 release commit，命令不自动修改 ledger。发布后证据更新是
独立、可 review 的 evidence Task，记录已观察到的 tag object、Release ID/URL、资产 digest
与 workflow run；它不是发布工作流继续执行的前置条件。

### 6.3 Generated release plan

`prepare` 在 ignored output root 生成确定性 operational plan：

```text
build/release/<encoded-tag>/release-plan.json
build/release/<encoded-tag>/release-notes.md
build/release/<encoded-tag>/assets/...
```

tag 中的 `/` 必须使用无歧义编码，禁止直接拼接为目录层级。Plan 最小形状：

```json
{
  "schema": "lmdj.release-plan.v1",
  "repository": "endaye/lmdj",
  "tag": "lmdj-v1.0.16.9",
  "tag_object": "<40-hex>",
  "target_revision": "<40-hex>",
  "kind": "product",
  "identity": "1.0.16.9",
  "channel": "canary",
  "profile": "web-runtime-host",
  "snapshot": "1.0.16.9",
  "ci": {
    "run_id": 31634688566,
    "event": "push",
    "head_sha": "<40-hex>",
    "conclusion": "success"
  },
  "release": {
    "draft": true,
    "prerelease": true,
    "make_latest": false,
    "name": "LMDJ 1.0.16.9"
  },
  "assets": [
    {"name": "<archive>.zip", "bytes": 123, "sha256": "<64-hex>"},
    {"name": "<archive>.zip.sha256", "bytes": 99, "sha256": "<64-hex>"},
    {"name": "<archive>.zip.sha256.asc", "bytes": 488, "sha256": "<64-hex>"}
  ]
}
```

`core-package` profile 自 2026-08-24 起在上述三资产之外增加并列的
`<archive-stem>.build-manifest.json`（决策
[`../../prd/decisions/2026-08-24-build-manifest-detached.md`](../prd/decisions/2026-08-24-build-manifest-detached.md)，
#211）：Manifest 不再打进归档，归档只含 payload，因此同一源码与工具链的归档
字节可复现；Manifest 字段不变，仍含 version-management.md §4 要求的
`build_time` 与 `platform`。`web-runtime-host` 保持三资产。

Plan 使用 canonical JSON 序列化并输出自己的 SHA-256。它是本地执行记录与 workflow
输入绑定，不是 Product Manifest、Project Truth、public Contract 或额外 Release asset。
尤其 Web Runtime Host Release 仍保持部署 verifier 要求的精确三资产，不能把 plan 当成
第四个资产上传。

`create-draft` 把 plan schema、plan digest、tag object、target SHA 与 intent 摘要写入
Release body 的机器可解析 HTML comment；公开文字仍来自 `release-notes.md`。该 comment
不是信任根，发布 workflow 必须从 tag target、GitHub API 与下载资产重新计算并对比。

## 7. Release 分类与资产政策

### 7.1 Product Release

Product tag 必须匹配：

```text
lmdj-v<MILESTONE>.<MINOR>.<BUILD>.<PATCH>
```

额外门禁：

- remote target 是 protected `main` ancestor；
- exact target 已有成功、未取消的 `push` full-mode CI/PR Gate；
- merged-main Proof 绑定 Product Build、target SHA 与 Assembly lock hash；
- active Product identity 与 tag 文本一致；
- Architecture Portal 存在匹配 immutable snapshot 与通过验证的 provenance；
- ledger disposition 允许本次状态；
- tag 使用 Product signer，primary fingerprint 精确为
  `2B5EE362F058800036AD4FB5116ECE156F954D29`；
- checksum 使用独立 Release checksum signer，primary fingerprint 精确为
  `CB928A6E89DE498851688EF1AAC3E7019FC1478B`；
- 两个 key role 不得互换。

Product profile 决定唯一 payload：

| Profile | 构建与验证 | Release inventory |
| --- | --- | --- |
| `core-package` | exact target 上运行 `scripts/core.sh package` 及 archive acceptance | Core archive、detached `.sha256`、armored detached `.sha256.asc` |
| `web-runtime-host` | locked Node/Emscripten toolchain 构建 Host bundle并运行 release bundle verifier | Host ZIP、detached `.sha256`、armored detached `.sha256.asc` |

初始 schema 中一个 Product Release 只能选择一个 profile。未来若一个 Product Release 需要
多个 public payload，必须先设计新的闭合 inventory schema，不能临时上传第四个文件。

Channel 映射：

| Channel | GitHub prerelease | `latest` | 额外条件 |
| --- | --- | --- | --- |
| `canary` | true | false | 编译、基础测试、merged-main full CI、snapshot 与 profile verifier |
| `dev` | true | false | canary 条件加对应 E2E/团队集成证据 |
| `beta` | true | false | dev 条件加批准的用户流程、恢复、平台/设备验收 |
| `stable` | false | policy-controlled | Release Checklist、回滚、签名、发布与生产验证条件均已明确满足 |

`stable` 是否成为 latest 必须由 ledger 的显式字段和 stable policy 决定；普通命令不得因为
它“看起来最新”而自动设置。

### 7.2 Module Release

Module tag 必须匹配：

```text
module/<module-id>/v<semver>
```

工具从 target revision 的 active `module.json` 验证 module id/version、dependency identity、
main ancestry 与覆盖 CI。初始 Module Release 是普通 GitHub Release、`latest=false`、
`source-only`，不上传自制 binary 或 checksum；GitHub 自动 source archives 不计入 Release
asset inventory。若 Module 将来需要独立 binary package，必须先扩展 profile 与 verifier。

### 7.3 Contract 与 Provider Release

Contract 与 Provider tag 分别匹配：

```text
contract/<contract-id>/v<semver>
provider/<provider-id>/v<semver>
```

它们不会因 active manifest 中出现新版本而自动发布。只有 ledger 中存在显式
`releasable + source-only` intent，且 Contract 的 schema/fixtures/conformance 或 Provider 的
manifest/Capability/Model identity 均完整通过时才允许。初始不上传自制资产、
`prerelease=false`、`latest=false`。

### 7.4 阶段 tag

`lmdj-m<MILESTONE>-<stage>.<revision>` 不进入 GitHub Release pipeline。它们用于 design、
plan、spike、parked 阶段身份，不能伪装为 Product Build 或用户分发。

## 8. 四段命令状态机

### 8.1 `scripts/release.sh prepare TAG`

这是本地命令。显式调用它只授权本地准备与本地 signed/annotated tag creation，不授权任何
remote mutation。

执行顺序：

1. 固定 canonical repository 与 remote，fetch `origin/main`、tag refs 和必要 Git objects；
2. 要求主工作树不被使用，在 scratch detached worktree 中读取 exact intent target；
3. 校验 ledger schema、tag/classification、identity、snapshot、merged-main Proof、CI run、
   main ancestry 与 version policy；
4. 拒绝 remote 同名冲突、本地同名不同 object/target、错误 signer、abandoned 或未知状态；
5. 按 profile 从 exact committed target 构建，拒绝使用调用者的脏工作树内容；
6. 运行 profile-specific verifier，生成 detached checksum；
7. 用 Release checksum private key 生成 armored detached signature，并用 public trust anchor
   在全新临时 keyring 中回验；
8. 生成 deterministic notes structure、asset inventory 与 provisional plan；独立执行的
   OpenPGP signature 包含签名时间，不承诺跨独立签名运行逐字节相同；
9. 创建本地 annotated tag；Product tag 必须使用指定 Product private key 签名；
10. 验证 tag object、signature、peeled target、main ancestry，再写最终 plan 与 digest；
11. 输出已完成状态和下一条可复制命令，但停止。

若本地同名 tag 已存在且 object、signature、target 与 intent 完全一致，`prepare` 可以复用；
否则失败且不移动 tag。任何失败都不得 push、创建 Draft 或修改 GitHub。

### 8.2 `scripts/release.sh push-tag TAG`

这是第一个 remote mutation 边界，必须由操作者明确调用。命令只允许 push：

```text
refs/tags/<TAG>:refs/tags/<TAG>
```

不得顺带 push 当前 branch、`--tags` 或其他 ref。Push 后必须：

1. 清理 scratch refs；
2. 从 canonical origin 重新 fetch 远端 tag object 与 `origin/main`；
3. 忽略本地同名 tag重新验证 annotated type、signature、object id、peeled target 与 main ancestry；
4. 对比 local plan 中的 tag object/target；
5. 输出 remote-tag verified 状态并停止。

若远端同名 tag 已存在且完全一致，该命令成功 reconcile；若任一 byte/object/target 不同，
立即失败，绝不 force push 或删除远端 tag。

### 8.3 `scripts/release.sh create-draft TAG`

这是独立 GitHub mutation 边界。它要求 remote tag 已从 canonical origin 验证通过，然后：

1. 重新验证 intent、CI 与 plan；
2. 用 `gh` 创建 `draft=true` 的 GitHub Release；
3. 设置精确 tag、name、prerelease 与 `latest` policy；
4. 只上传 plan 声明的 custom assets；`source-only` 上传零资产；
5. 逐项从 GitHub API 读取 asset id/name/size，并重新下载计算 SHA-256；
6. 对 Product checksum signature 与 payload verifier再次执行远端下载验证；
7. 回写或 reconcile Draft body 中的 plan digest marker；
8. 输出 immutable Release ID、URL、plan digest 和 publish workflow 输入并停止。

幂等规则：

- 同 tag 不存在 Release：创建 Draft；
- 存在完全匹配的 Draft：复用并验证；
- Draft 缺少部分资产：只允许上传 plan 中缺少且名称未占用的资产，然后完整重验；
- Draft 已有额外资产、同名不同 digest、错误 metadata 或错误 tag：失败并保留 Draft供调查；
- 已存在 published Release：不修改，只执行 audit；完全匹配可报告 already published，
  不匹配则失败；
- API 中断后必须先 reconcile Release/asset IDs，再决定是否继续，不能盲目重复创建。

### 8.4 `.github/workflows/publish-release.yml`

发布 workflow 只监听：

```yaml
on:
  workflow_dispatch:
```

输入至少包含 exact `tag`、numeric `release_id` 与 `plan_sha256`。它 checkout protected
`main` 的发布工具，并把 tag target 放入独立只读 checkout。Workflow 顶层默认
`contents: read`；只有最终 publish job 具有 `contents: write`，且该 job 使用：

```yaml
environment: release
```

精确输入的显式 workflow dispatch 是公开 Release 的人工授权边界；受保护 Environment 负责
exact-main 策略约束和 deployment 记录，不在单人维护者仓库伪造第二人审批。preflight job 只读并
完成：

- canonical remote tag fetch、annotated/signed role、target 与 main ancestry；
- intent、active identity、snapshot/provenance、merged-main CI run 与 channel gate；
- 当前 GitHub actor、repository 与 event 类型 allowlist。

（修订 2026-08-26，#335）GitHub 仅向具备 push/write 权限的身份暴露 Draft Release，
只读 preflight token 读取 Draft 会收到 403，因此 Draft 专属验证不可能在只读阶段完成。
原先分配给 preflight 的以下各项全部改由 publish job 在 `release` Environment 门之后、
唯一 mutation 之前完成；mutation 前的保障不变，代价是坏的 Draft 输入在 Environment
批准之后而非之前被拦下：

- numeric Release ID、Draft state、tag/name/prerelease/latest 与 body marker；
- exact asset inventory、每个 size/digest、checksum signature、profile verifier；
- deterministic plan 重建与 `plan_sha256` 对比。

publish job 必须读取并完整验证 Draft 的 immutable inputs，随后只执行一次设置
`draft: false`、精确 `prerelease` 与精确 `make_latest` policy 的 transition。GitHub Release
API 不提供本流程可依赖的强条件更新契约，因此这里不声称阻止 TOCTOU；流程通过 mutation 前
最后一次完整验证和 mutation 后再次完整读取来检测并 fail closed，必要时按 numeric ID
reconcile。发布后重新读取 Release，确认：

- Release ID/tag 未变；
- `isDraft=false`；
- prerelease/latest policy正确；
- asset IDs、names、sizes 与 digest 未变；
- URL 可按 tag 解析；
- run summary 与 evidence artifact 不含 secret。

任一 preflight 或 postcondition 失败都不得调用部署。发布前失败保留 Draft；publish API
返回不确定结果时先按 Release ID reconcile，不能创建第二个 Release。

## 9. Release 与 Deployment 解耦

现有 `.github/workflows/deploy-web-runtime-host.yml` 的 `release.published` trigger 必须删除，
保留 exact Product tag 的 `workflow_dispatch`。Runtime deployment 继续使用独立受保护
`runtime-canary` Environment、Netlify secrets、Release verifier、draft deploy、smoke 与恢复。

因此状态顺序明确为：

```text
published GitHub Release
        |
        | separate authorization + workflow_dispatch
        v
Runtime deployment
        |
        | separate evidence
        v
deployment verified
        |
        | separate authorization
        v
Channel promotion
```

`publish-release.yml` 不调用 deployment workflow，不发 repository dispatch，不持有 Netlify
credential。GitHub 的 Release publication event 即使存在也不再有生产消费者。部署仍只消费
published、非 Draft、已签名并精确验证的 Release bytes。

## 10. 密钥、权限与信任边界

### 10.1 Local trusted signer

- Product tag private key 与 Release checksum private key 只存在于可信本机/离线备份；
- 两把 key 使用不同 primary fingerprint 与用途；
- passphrase、private key、revocation certificate、token 不写入仓库、Release、plan、日志、
  shell trace、Actions artifact 或 evidence；
- 脚本禁止 `set -x`，子进程只接收完成当前动作所需的最小环境变量；
- temporary `GNUPGHOME` 使用 `mktemp -d`、0700 权限并在退出时清理；
- 签名失败不得降级为 unsigned Product tag 或 unsigned checksum。

### 10.2 Public verification

仓库只保存：

- `.github/release-signing-keys/lmdj-product.asc`；
- `.github/release-signing-keys/lmdj-release-checksum.asc`；
- policy 中的 exact primary fingerprints。

public-key-only 验证必须在 Linux 与 macOS 空 keyring 中不依赖 `gpg-agent`。实施需统一修复
release 与 deploy verifier 的 import helper，例如使用 batch、no-autostart 的 public import
路径，并以 imported primary fingerprint 精确核对。不能用“本机默认 keyring 已有公钥”掩盖
空环境缺陷。

### 10.3 GitHub token

- local `gh` 使用当前操作者凭据；脚本不得读取或打印 token；
- workflow preflight `contents: read`、`actions: read`、`deployments: read`；
- publish job 仅在进入 `release` Environment exact-main 策略门后获得 `contents: write`；
- checkout 使用 `persist-credentials: false`；
- 不向 fork PR 或 self-hosted untrusted workload暴露 write token；
- deployment token 与 GitHub write token不进入同一个 job。

`release` Environment 在当前单人维护者模式必须有零 required reviewer，`prevent_self_review`
为未启用状态，并只允许 exact `main` custom branch policy（不用 protected-branches wildcard）。
Remote audit 每次读取并验证这些 GitHub 侧配置；缺失、不可读或漂移均 fail closed。仓库内 workflow 只声明契约，不自动
创建或修改 Environment。

## 11. 失败语义与恢复

| 失败点 | 外部状态 | 允许的恢复 |
| --- | --- | --- |
| `prepare` 校验/构建/签名失败 | 无 remote mutation；可能保留完全验证的 local tag/output | 修复原因后幂等重跑；不得 push half-prepared tag |
| tag push 网络不确定 | remote tag 可能存在 | fetch canonical tag 并按 object id reconcile |
| remote 同名 tag 冲突 | 旧 tag 保留 | 停止并进行 incident review；不得移动/删除/force |
| Draft create API 不确定 | Draft 或部分资产可能存在 | 按 tag/Release ID/asset ID reconcile |
| Draft 资产错误 | Draft 保留、未公开 | 调查；正常工具不覆盖同名资产 |
| publish preflight 失败 | Draft 保留 | 修复 intent/evidence 或新建纠正版本；重跑 dispatch |
| publish API 不确定 | Draft 或 published | 按 numeric Release ID reread；不得创建第二个 Release |
| post-publish 验证失败 | Release 可能已公开 | 标记 incident并阻止部署；不得自动删除或改写 |
| audit 发现 drift | 只读报告 | 单独批准修复；不可自动 backfill |

错误 tag 与错误 published Release 均视为审计事件。tag 不移动；如需修正，分配正确的新身份或
更正 tag，并在 evidence 中保留旧状态。GitHub Release 不通过删除历史来制造“从未发生”。

## 12. Read-only audit

稳定入口：

```bash
scripts/release.sh hydrate
scripts/release.sh audit
scripts/release.sh audit --tag <exact-tag>
scripts/release.sh audit --json <path>
```

（修订 2026-09-06，#332）`hydrate` 与 audit 是两个分开的边界。已获准 intent 可能记录
一个没有任何 advertised ref 能到达的 pre-squash `target_revision`，全新 clone 因此缺少
该对象，audit 只能报告该 intent `unverifiable`。补全这些对象归 `hydrate`：它读
`docs/release-evidence/release-intents.json` 的 `entries` 与 `historical_exceptions`，
逐个探测后只对缺失的执行一次 `git fetch --no-tags origin <missing shas>`，幂等且什么都
不缺时不发起 fetch。Audit 不做 fetch-on-miss——那会修掉它本该报告的缺陷；缺失 target 的
finding 因此同时携带 why 与 `remedy: run scripts/release.sh hydrate`。全新 clone 的操作
顺序是先 `hydrate` 再 `audit`。

审计数据面：

1. active Product/Module/Contract/Provider manifests 与 Assembly lock；
2. Architecture Portal current identity、immutable snapshots、metadata 与 provenance；
3. release-intent ledger 的 schema、唯一性、lifecycle 与 evidence paths；
4. canonical `origin/main` ancestry 与 GitHub protected-main merge/CI facts；
5. local tag 仅作诊断，对权威结论使用 freshly fetched remote tag object；
6. annotated type、签名 role、primary fingerprint、peeled target 与 immutable target；
7. GitHub Release ID、draft/prerelease/latest、tag、body marker 与 asset inventory；
8. Product asset downloads、digest、checksum signature 与 profile-specific verifier；
9. abandoned/superseded candidates 是否错误出现 tag 或 Release；
10. published Release 是否存在 tag/asset/signature/identity drift；
11. 已有 deployment evidence 与 Release bytes 是否属于同一精确身份，但不把 Release
    existence 推断成 deployed。

输出按闭合 finding code 分类：`ok | missing | conflict | unauthorized | unverifiable |
external-error`。Human summary 与 JSON report 必须区分：

- “应存在但缺失”；
- “明确不应存在”；
- “尚未获准，不能推断”；
- “外部 API/网络不可验证”。

网络/API 失败不能报告为“无缺口”。Audit 不创建、push、编辑或删除任何 Git/GitHub 状态。

CI 集成：

- `main` push 运行 release audit 的静态/本地真相部分；
- scheduled workflow 运行完整 remote audit 并保留 JSON artifact；
- scheduled drift 产生可见失败/告警，但不自动修复；
- `publish-release.yml` 总是运行 exact-tag full audit并 fail closed；
- PR 只运行 schema、policy、workflow 与 fixture 契约，不对 fork 暴露 external write capability。

## 13. 测试设计

### 13.1 单元与契约测试

Python standard-library core 或等价无网络 library 覆盖：

- tag kind 与命名分类；
- Product 四段版本、Module/Contract/Provider SemVer 与 manifest identity；
- intent ledger schema、duplicate、non-canonical path 与 disposition transition；
- channel -> prerelease/latest policy；
- profile -> exact asset inventory；
- release-plan canonical serialization 与 digest；
- tag target、main ancestry、CI run 与 snapshot evidence binding；
- Release metadata/API projection 解析；
- state-machine idempotency 与 conflict detection；
- secret-safe log/output projection。

### 13.2 Fail-closed 矩阵

至少覆盖：

- lightweight/unsigned Product tag；
- tag signer 与 checksum signer互换；
- tag text/version manifest 不一致；
- wrong target SHA、non-main target、local-only branch target；
- missing/red/cancelled CI，或 run head SHA 不匹配；
- branch-local Proof 冒充 merged-main Proof；
- snapshot 缺失、hash/provenance/witness 不匹配；
- missing/extra/duplicate/renamed assets；
- same-name different-digest asset；
- checksum signature 未验证就解析 checksum；
- wrong prerelease/latest/channel；
- duplicate tag/Release、Draft/published state混淆；
- abandoned、superseded-unreleased 与未知 intent；
- GitHub API pagination/truncation/network uncertainty；
- macOS empty-keyring public import 无 agent；
- Release publication 未触发 deployment。

### 13.3 Local integration

使用临时 bare Git remote、isolated keyrings、ephemeral signed test key 与 fake GitHub API
验证完整四段状态机。Fixture 不使用真实 Product private key，不触碰 canonical origin，覆盖
API 中断后的 reconcile、重复运行与 exact refspec。

### 13.4 Workflow static contract

固定测试解析 YAML 并证明：

- `publish-release.yml` 仅 `workflow_dispatch`；
- 顶层/各 job 权限最小；
- publish job 使用 `environment: release`；
- write token 不进入 preflight build/verification；
- workflow checkout protected `main` tooling 并 freshly fetch exact tag；
- 没有 deploy command、Netlify secret、repository dispatch 或 reusable deployment call；
- `deploy-web-runtime-host.yml` 不再监听 `release.published`，只接受 explicit dispatch；
- deployment 仍使用独立 `runtime-canary` Environment。

### 13.5 Safe GitHub rehearsal

在实现合入但正式采用前，使用明确的 test-only annotated tag 与 Draft Release 完成一次受控
rehearsal：

1. 使用非 Product namespace 与测试 signer，防止被分类为正式 Product；
2. 创建、上传、reconcile Draft；
3. 验证正式 publish workflow拒绝 test namespace；
4. 清理由 rehearsal 明确创建的 test tag/Draft；
5. 记录清理目标和可恢复性，确认正式 tag/Release 未变化。

正式 Product/Module tag 不用于破坏性演练。

## 14. 项目规则与 Codex skill

### 14.1 Project governance

实施同步更新：

- `AGENTS.md`：正常 release 必须通过 `scripts/release.sh`；每个状态转换分别授权；禁止 agent
  将 `prepare` 完成解释为 push/tag Release/deploy授权；
- `docs/governance/git-workflow.md`：在现有 authority chain 中加入 Draft 与 publish workflow；
- `docs/governance/version-management.md`：补充 intent ledger、profile、Draft、latest 与
  immutable published Release policy；
- Architecture Portal `/operations/version-and-release/`、`/operations/testing-and-proof/` 与
  `/hosts/web-runtime/`：同步实际 implemented release/deploy boundary；
- PR template/plan guidance：声明 Release impact、候选 tag、profile、channel、intent、资产、
  CI/Proof/snapshot gate 与所有未授权外部状态。

手写 `gh release create`、`gh release upload --clobber` 或 GitHub UI 一步公开 Release 不属于
正常路径。紧急例外必须先有 incident owner、exact target/asset inventory、回滚/停止条件与
事后 evidence；紧急不授权移动 tag、跳过签名或暗中部署。

### 14.2 Thin repo-local skill

实施在 `.agents/skills/lmdj-release/SKILL.md` 增加薄 skill，并由 `AGENTS.md` 指向它。Skill 只：

- 先运行 `audit` 并解释 finding；
- 定位 intent 与 exact tag；
- 按授权调用 `prepare`、`push-tag`、`create-draft`；
- 在每一步输出真实已验证状态、下一权限边界和尚未发生的状态；
- 为 publish workflow 展示 exact `tag/release_id/plan_sha256`，但不替用户 dispatch 或跨越 publication 边界；
- 发布后重新 audit，并把 deployment/Channel promotion明确列为未授权。

Skill 不包含版本映射、fingerprint、asset name、GitHub repo、secret path 或状态缓存；这些全部
从仓库 policy 与 live API 读取。Skill 不使用 `--yes` 跨越多阶段，不把多个 mutation 合并为
一个 agent tool call。实现该 skill 时使用 `skill-creator`/writing-skills 的验证规则，但仓库
脚本与 tests 才是 correctness boundary。

## 15. 实施分解与迁移

后续实施计划至少分为以下 reviewable Tasks：

1. release policy、intent ledger schema、classification 与 pure validators；
2. `prepare`、profile builders、signing 与 macOS/Linux public-key verification fix；
3. `push-tag`、`create-draft`、GitHub API projection 与 idempotency tests；
4. `publish-release.yml`、protected Environment contract 与 deployment trigger removal；
5. `audit`、scheduled reporting 与当前 remote reconciliation；
6. governance、Portal current pages、thin skill 与 safe rehearsal evidence。

每个 Task 在隔离 worktree、短分支、Task-specific tests 与单一 Conventional Commit 中完成。
实现 commit 不授权 push；push 不授权 PR；PR 不授权 merge；merge 不授权正式 tag、Draft、
publish、deployment 或 Channel promotion。

迁移时先盘点全部 current-policy formal remote tags 与 GitHub Releases，再把 2026-08-13
补齐的 14 个 release identities 标记为该全量基线的 backfill 子集；不能把 14 当作仓库全部
历史。所有 current-policy identities 进入 ledger，现行 schema 之外的既有 tag/Release 只能
通过上述 exact historical exception 解释。随后让 `audit` 从 GitHub 重新证明每个 remote
tag/Release，而不是信任人工清单。明确 abandoned 或 unshipped 的历史 Product Build 录入
相应 disposition，确保 audit 不把快照存在误判为漏发。若 live audit 与本规格背景数量不同，
以 live canonical state 为准并在 evidence 中解释差异。

在新 publish workflow 合入、`release` Environment 保护已单独获准配置、safe rehearsal 与
current audit 全部通过前，现有正式发布继续采用逐项人工核验；不得声称自动化已经生效。

## 16. Version Management

Version impact: none

Reason: 本设计只新增 release control plane、governance、CI workflow、测试与 agent 导航，
不改变 Product behavior、Product Assembly、Assembly Lock、Module/Host API、Contract、Provider、
Model identity 或任何已发布产品字节。`lmdj.release-intents.v1` 与
`lmdj.release-plan.v1` 是 repo-internal operational schemas，不是跨语言产品 Contract，
不分配 Product/Module/Contract/Provider version。

本设计不分配 Product Build、不创建 Architecture Portal immutable snapshot，也不授权任何
正式 tag、tag push、GitHub Release、deployment 或 Channel promotion。未来实施若改变 Product
package format、Host distribution bytes 或公开 Contract，必须在对应 Task 重新评估版本影响，
不能沿用本节的 `none`。

## 17. Documentation Impact

Documentation impact: required

Affected portal pages:

- `/operations/version-and-release/`
- `/operations/testing-and-proof/`
- `/hosts/web-runtime/`

Reason: 本设计改变 release preparation、Draft/publication、审计、publication authorization 和 Release 与
Runtime Host deployment 的操作边界。这些是 Architecture Portal policy 明确要求同步的
发布、测试与部署事实。

Product Build、Assembly 与 Assembly Lock 不变，因此仅实现本发布控制面不创建新的 immutable
Product snapshot；current Portal pages 与必要测试在同一实施 Task 更新。若实施时同时发生新的
Product Build/Assembly 变化，则必须遵守正常 snapshot gate，不能以本设计豁免。

## 18. 完成标准

只有以下条件全部满足，标准化发布能力才可报告为 implemented：

- 本规格与后续 implementation plan 已 review；
- `scripts/release.sh` 四段命令与 `audit` 已实现并通过单元、失败矩阵与 integration tests；
- Product/Module/Contract/Provider classification 与 exact inventory policy 已闭合；
- macOS/Linux empty-keyring public-key verifier均通过且不依赖 agent；
- `publish-release.yml` 只允许 dispatch、使用受保护 `release` Environment且最小权限；
- `deploy-web-runtime-host.yml` 已移除 `release.published` trigger；
- governance、Portal current pages、PR/plan declarations 与 thin skill 同步；
- safe GitHub Draft rehearsal 通过并完成明确清理；
- live audit 重新验证当前 remote tags、Releases、assets 与 signatures，无未解释 gap；
- 没有因本实施创建正式 Product/Module tag、公开 Release、部署或 Channel promotion；
- 所有外部配置变更（尤其 GitHub Environment protection）有独立授权与验证证据。

完成报告必须分别列出 `implemented`、`committed`、`pushed`、`merged`、`environment-configured`、
`rehearsed`、`release-audited`、`released`、`deployed` 与 `channel-promoted`，不得用一个“发布流程
完成”概括不同状态。
