# LMDJ Channel Promotion Design

Issue: [#572](https://github.com/endaye/lmdj/issues/572)

## 1. 背景

`version-management.md` §3 定义了 `canary`、`dev`、`beta`、`stable` 四个 Channel 及门禁，
§12.1 把 Channel promotion 列为独立授权、独立验证的边界。截至 `1.0.41.0` 发布，没有任何命令、
workflow 或 `tools/release/` 代码实现它；ledger 中 30 个 Product 条目全是 `canary`，从未有
Build 晋级过。`1.0.41.0` 的 tag、Release 与两个 Host 部署完成后在这个边界停下。

## 2. 决策

| # | 决策 |
| --- | --- |
| P1 | 晋级是一次经 review 的 ledger 变更，永不改动 GitHub Release。`channel` 固定为发布时的 Channel，继续决定 `prerelease`/`latest`；新增可选 `promotions` 列表记录每次晋级。当前 Channel 等于最后一条记录。 |
| P2 | 晋级严格向前、一次一档，且不超过 policy 的 `promotion.max_channel`。M1 为 `dev`。 |
| P3 | `dev` 门禁完全可判定：intent 已 `published`、full exact-main CI 成立、profile 的每个部署 Host 各有一次成功的 `workflow_dispatch` 部署 run，其保留 `evidence.json` 记录同一 tag、target revision、Product Build，且 immutable 与 production 的 HTTP 和 browser 检查均 `passed`。 |
| P4 | `beta` 在 `dev` 之上要求至少一份 `docs/release-evidence/` 或 `docs/quality/` 下被跟踪的人工验收文档；工具只核验存在与跟踪，记录标为 `manual-attested`。 |
| P5 | `stable` 被工具拒绝并指向 `docs/prd/questions/stable-channel-prerelease-flip.md`。D8 与 Channel 映射表在此冲突，是产品级契约问题，不在实施任务中裁决。 |
| P6 | `scripts/release.sh promote` 只做本地变更：先 exact-tag remote audit 且必须全部通过，再校验转换与门禁并下载核对部署证据，然后写一份证据文档与一条 ledger 记录。变更作为 docs PR 经 Integration Queue 合入。 |
| P7 | `audit` 核验 `promotions` 的结构、顺序与 `max_channel`，并确认每条记录的部署 run 仍存在、属于该 Host 的部署 workflow、由 `main` 上的 `workflow_dispatch` 触发并成功。审计不重新下载制品；记录中的 SHA-256 与证据文档是持久记录。 |
| P8 | 降级与撤回不在本次范围，作为后续任务。 |

## 3. 数据模型

`tools/release/policy.json` 新增顶层 `promotion`：

```json
"promotion": {
  "max_channel": "dev",
  "deployment_evidence": {
    "core-package": [],
    "web-runtime-host": ["runtime"],
    "web-hosts": ["runtime", "creator"]
  },
  "hosts": {
    "runtime": {"workflow_path": ".github/workflows/deploy-web-runtime-host.yml", "artifact": "runtime-host-deployment-evidence", "contract_prefix": "lmdj.web-runtime-host.deployment-evidence."},
    "creator": {"workflow_path": ".github/workflows/deploy-creator-web.yml", "artifact": "creator-host-deployment-evidence", "contract_prefix": "lmdj.creator-web.deployment-evidence."}
  }
}
```

`deployment_evidence` 的键必须恰好等于 Product profile 集合，`hosts` 闭合。

ledger Product 条目新增可选 `promotions`，仅 `published` 条目允许：

```json
"promotions": [
  {
    "channel": "dev",
    "promoted_at": "2026-09-02T13:00:00Z",
    "evidence_paths": ["docs/release-evidence/2026-09-02-lmdj-1.0.41.0-promotion-dev.md"],
    "deployment_runs": [
      {"host": "runtime", "run_id": 33628917537, "evidence_sha256": "…"},
      {"host": "creator", "run_id": 33632230550, "evidence_sha256": "…"}
    ],
    "attestation": "verified"
  }
]
```

`deployment_runs` 的 host 序列必须恰好等于 profile 在 policy 中的 Host 序列。`attestation` 由
目标 Channel 决定：`dev` 为 `verified`，`beta` 为 `manual-attested`。ledger schema 保持
`lmdj.release-intents.v1`：新增字段可选且向后兼容，旧条目无需改动。

## 4. 组件

- `tools/release/model.py`：`PromotionPolicy`、`PromotionRecord`、`DeploymentRunRecord`、
  `ReleaseIntent.promotions` 与 `current_channel`、`CHANNEL_ORDER`、闭合解析与全部拒绝规则。
- `tools/release/github_api.py`：`get_run(repository, run_id)` 以 workflow 文件路径绑定身份；
  `get_run_artifact_member` 从唯一命名、未过期的制品中取出唯一成员并受大小上限约束。
- `tools/release/deployment_evidence.py`：`verify_deployment_run` 对一个 Host 部署 run 做只读核验，
  每一处身份不符都 fail closed，`ok` 时返回 `evidence.json` 的 SHA-256。
- `tools/release/promotion.py`：`plan_promotion` 校验转换与门禁；`apply_promotion` 写证据文档并在
  ledger 的单行条目上追加记录，写后重新加载 ledger 校验，失败则完整回滚两处写入。
- `tools/release/cli.py`：`promote` 子命令。
- `tools/release/audit.py`：`_promotion_problem`。

## 5. 命令语义

```text
scripts/release.sh promote lmdj-v1.0.41.0 dev \
  --deployment-run runtime=33628917537 \
  --deployment-run creator=33632230550
```

1. `audit --remote --tag` 必须全部为成功码，否则拒绝。
2. intent 必须存在、为 Product、`published`；目标 Channel 严格高于当前 Channel 且不超过
   `max_channel`；`stable` 直接拒绝并指向开放问题。
3. profile 要求的每个 Host 必须且只能提供一个 run；每个 run 经 `verify_deployment_run` 为 `ok`。
4. `beta` 需至少一份被跟踪的验收文档；所有 `--evidence` 必须位于允许目录且被跟踪。
5. 写 `docs/release-evidence/<date>-lmdj-<identity>-promotion-<channel>.md` 与 ledger 记录。
6. 打印下一步：以 docs PR 经队列合入。命令不 push、不改 GitHub。

## 6. Version Management

Version impact: none。本次只改发布控制面工具、policy 与 ledger 的可选字段，不改任何
Product、Module、Host、Provider 或 Contract 身份，不分配 Build。ledger schema 字符串保持
`lmdj.release-intents.v1`，理由见 §3。

## 7. Documentation Impact

Documentation impact: required。受影响门户路由：`/operations/version-and-release/`。同一 Task
更新 `docs/governance/version-management.md` §3.1 与 §12.1、`docs/governance/git-workflow.md`
§6、`.agents/skills/lmdj-release/SKILL.md` 命令映射，并新增
`docs/prd/questions/stable-channel-prerelease-flip.md`。

## 8. 首次使用

机制合入 `main` 后，从 `main` 对 `1.0.41.0` 运行 §5 的命令，以 run `33628917537`（Runtime）与
`33632230550`（Creator）为证据晋级到 `dev`，产出的两个文件作为独立 docs PR 合入。本设计合入前
无法在分支上执行该命令：audit 用分支代码读取 `main` 上尚无 `promotion` 字段的 policy，会因
policy 闭合校验失败而报 `external-error`，这与 `release-signing-role-keyrings` pitfall 记录的
"分支代码解析 main 权威树"是同一类现象。
