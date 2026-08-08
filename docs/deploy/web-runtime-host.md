# Web Runtime Host 公共发布运行手册

本运行手册描述正式 Web Runtime Host 的受控发布路径。它是操作说明，**不是**
执行记录，也不授权创建远端资源、写入 secret、发布 Release、运行 workflow 或部署。
当前真相见
[`docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md`](../quality/2026-08-08-web-runtime-public-deployment-acceptance.md)：
Product `1.0.15.2` / Host `1.1.2` 的本地工具已实现，但尚未 push、merge、创建
Netlify 项目、配置 GitHub Environment、运行部署或生成公共证据。本地 Git 数据库已存在
signed annotated tag `lmdj-v1.0.15.2`：`git tag -v` 显示 primary fingerprint
`2B5EE362F058800036AD4FB5116ECE156F954D29` 的 Good signature，且 tag target 是
`72ae40074620cc5681c462ba04a31a666449734f`；该 tag 尚未 push，未做远端验证，不能由此
推断远端 tag、Release 或部署存在。

## 发布不变量

- 目标 Product tag 为 `lmdj-v1.0.15.2`，其签名 target 必须是
  `72ae40074620cc5681c462ba04a31a666449734f`。
- Release archive 的 SHA-256 必须是
  `d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a`。
- 已验证的 Release ZIP 未修改。`apps/web-runtime-host/deploy/_headers` 是
  repository-tracked deploy-control artifact：staging 时独立加入 Netlify digest deploy，
  不在 Release bundle 内；不得写入、删除、改名或替换任何已验证 Release `dist` 文件。
- 唯一生产别名是 `https://lmdj-runtime.netlify.app`。先创建 immutable draft
  Deploy，再对**同一个** ready Deploy ID 运行 smoke，最后才允许把该 ID 设为生产别名。
- `scripts/web-runtime-host.sh proof` 的 Python proof-only server 只用于本地
  Proof；它不是生产服务。生产由 Netlify 静态托管已验证的 `dist`，并应用独立 staging
  的 `_headers` deploy-control artifact。
- 这不是 Creator URL、Creator PWA 或 `lmdj-canary` 的发布。`lmdj-canary` 留给
  未来 Creator 产品，不能在本 Task 创建、绑定、重定向或作为 Runtime Host 的别名。

## 前置条件与发布前验证

获得逐项授权后，在受信任的操作者环境中运行下列命令；它们要求已安装并已认证
`gh`、`git`、`gpg`、Python 3 与 Node/npm。必须在干净、已同步的 `main` checkout
中操作，并以最小权限凭据执行。`verify` 读取 GitHub Release，不部署到 Netlify。

```bash
gh auth status
git fetch origin --tags
git tag -v lmdj-v1.0.15.2
scripts/web-runtime-deploy.sh verify lmdj-v1.0.15.2
gh workflow run deploy-web-runtime-host.yml --ref main -f tag=lmdj-v1.0.15.2
```

前四步必须分别确认 GitHub 身份、远端 tag、签名和 Release archive；不要以本地 tag
或未签名 lightweight tag 代替。`verify` 还会校验 release identity、目标 checkout、
archive digest、bundle manifest 的 Product/Host identity。最后一条仅在前四步成功、
Environment 已配置且本次发布获授权后执行；它是手动 workflow dispatch，不应在本
文档的 pre-deploy 状态下执行。

## 创建 Netlify 项目（一次性、获授权后）

1. 在 Netlify 创建空的团队站点，站点名为 `lmdj-runtime`；记录平台返回的 site ID。
2. 不连接 Git provider。若创建流程默认连接 Git，取消连接；若已有连接，先断开。
   在项目 Deploy 设置中关闭 automatic publishing / auto-publish，并确认没有 build
   command、publish directory、branch deploy 或 Deploy Preview 会替该项目发布。
3. 独立检查项目设置：Git repository 显示未连接，自动发布关闭，生产 URL 仅是
   `lmdj-runtime.netlify.app`。不要创建、别名化或重定向 `lmdj-canary`。
4. site ID 本质上是非敏感身份标识，不得与 token 混淆；为保持已批准的 scoped
   configuration contract，当前把 `NETLIFY_RUNTIME_SITE_ID` 存为 GitHub Environment
   secret 并提供给受控 workflow。此站点只能由下述 GitHub Actions 路径以 API 创建 draft、
   smoke 后同 ID 发布，禁止手工拖拽/CLI 生产上传。

这一步完成前，任何 `lmdj-runtime` site ID、Deploy ID 或 immutable Deploy URL 都是
不存在的值，不能用占位符伪造为证据。

## GitHub Environment 与 secret

workflow `.github/workflows/deploy-web-runtime-host.yml` 使用 GitHub Environment
`runtime-canary`。site ID 本质上不是 secret，但按已批准的 scoped configuration contract
存为 Environment secret；不得与 token 混淆。它可以进入实际的 evidence artifact 和后续
验收记录，供核对 deploy identity；token 不得进入任何 evidence、验收记录或日志。当前
tracked runbook、Portal 和日志不写入尚未创建站点的真实 site ID；该限制不把 site ID
重新分类为敏感值。也就是说，不在 tracked runbook、Portal 或日志中写入真实值；真实 site
ID 只在实际 evidence artifact 与验收记录的身份字段中出现。

| 配置项 | 值 | 操作边界 |
| --- | --- | --- |
| Environment secret `NETLIFY_RUNTIME_SITE_ID` | 已确认的 `lmdj-runtime` Netlify site ID（非敏感身份标识） | 为保持已批准配置契约只在 Environment `runtime-canary` 配置；可写入实际 evidence artifact 和验收记录，不与 token 的敏感性混淆。 |
| Environment secret `NETLIFY_AUTH_TOKEN` | 仅有该站点部署所需的最小权限 Netlify token | 只在 Environment `runtime-canary` 配置；不回显、不写入 evidence、验收记录或日志。 |

GitHub Actions 提供短期 `GITHUB_TOKEN` 读取固定仓库的 Release；它不是一个需手工添加
的 repository secret。配置后确认两个 Environment secret 名称存在、值不可见，并核对
`NETLIFY_RUNTIME_SITE_ID` 与 Netlify 返回的 site ID 一致；在 workflow 的 Environment
approval/protection policy（如已配置）通过后再 dispatch。
不要把 token 粘贴到 shell history、PR、runbook、artifact、Portal 或日志；site ID 的记录
规则以前段为准。

## 受控执行与证据检查

获授权的 workflow 只接受发布事件的 prerelease tag 或手动输入的精确 Product tag，
并固定 checkout `main`。它执行：签名 tag/Release/archive 验证 → staging → Netlify
draft → immutable URL HTTP 和 Chromium smoke → 同 Deploy ID production publication →
生产 URL HTTP 和 Chromium smoke → artifact evidence。

调度后记录并审查 workflow run，而不是仅凭 Actions 页面上的绿色图标宣布发布：

```bash
gh run list --workflow deploy-web-runtime-host.yml --limit 5
gh run view RUN_ID --log
gh run download RUN_ID --name runtime-host-deployment-evidence --dir evidence/RUN_ID
python3 -m json.tool evidence/RUN_ID/evidence.json
```

证据按来源分别核对，不能声称 artifact 单独提供全部字段：

- `evidence.json` 提供 deploy identity：`deploy_id`、immutable `deploy_url`、
  `git_revision`、Product Build、Host version、tag、release URL、site ID 和 archive
  digest；确认 digest 等于上文指定值、revision 等于指定 tag target。它不单独提供
  run URL、timestamp 或 smoke detail。
- 不可变 GitHub run metadata 提供该 run 的 URL、run identity 和 timestamps；保留与
  `runtime-host-deployment-evidence` artifact 的 identity 对应关系。
- 同一不可变 run 的 workflow log 与 artifact identity 提供 immutable/prod HTTP 与
  Chromium smoke detail、same-ID restore 结果和失败上下文；这不是 `evidence.json` 的
  字段。

只有三类记录相互一致，成功 evidence 才能填充验收记录；发生失败时保留失败日志，不把
失败 draft 当作发布证据。

生产 alias 切换后，在干净环境执行：

```bash
scripts/web-runtime-deploy.sh smoke https://lmdj-runtime.netlify.app 1.0.15.2 1.1.2
```

该 smoke 检查 HTTPS、index、manifest、全部声明资产、缓存/header 边界和 packaged
Chromium path。它不替代 macOS Safari、physical MIDI、iPadOS Touch/lifecycle 等五项
物理门；这些门仍需独立 dossier。

## 失败处置与回滚

| 情形 | 操作 |
| --- | --- |
| 签名、target、Release、archive digest 或 bundle identity 校验失败 | 停止；不要创建 Netlify Deploy。修复 release provenance 后从验证重新开始。 |
| draft 创建或 immutable URL smoke 失败 | 不发布该 draft；保存 workflow artifact/log，诊断后创建新的 draft。失败 draft 没有生产资格。 |
| production alias 发布 API 失败 | 停止并检查 alias 仍指向的实际 Deploy ID；不要假定新 draft 已上线。保留日志并按授权重试同一已 smoke 的 Deploy ID。 |
| production alias 已切换但 production smoke 失败 | 立即用已记录、曾通过生产 smoke 的**精确 prior Deploy ID**回滚，然后再次 smoke 并记录结果。 |
| evidence artifact 缺失、字段不匹配或含敏感信息 | 将部署视为证据不完整；不要更新 acceptance/Portal 为 deployed，先修复证据链。 |

回滚不是重新构建或从当前分支重新上传，也不在 token 命令行或 shell history 中操作。
现有 `deploy-web-runtime-host.yml` 没有 rollback dispatch；因此回滚必须先获得单独授权，
由受控 GitHub Actions/专用授权流程在受保护 Environment 中执行，不能假装现有 workflow
已自动支持它。受控操作者按以下顺序执行：

1. 从 prior evidence 读取 exact prior Deploy ID、immutable URL、Product Build 和 Host
   version；先 smoke prior immutable URL，使用 prior evidence 的实际 Product/Host
   identity，而不是当前候选身份。
2. 仅在 prior immutable smoke 通过后，使用 sealed Environment credential 发布 exact
   prior Deploy ID；publication 响应必须确认同一个 ready ID 已恢复 production alias。
3. 再 smoke production alias，仍使用该 prior evidence 的实际 Product/Host identity，
   并把三步证据记录到受控运行中。

`PRIOR_DEPLOY_ID` 必须来自先前已验证 evidence；未知、当前 draft、猜测或截断的 ID
一律不可使用。初次发布没有 prior good Deploy 时不可回滚：保持或恢复为无已验证生产
版本，并升级处置，不得把未 smoke draft 或当前候选冒充为回滚目标。

## 凭据轮换

1. 先创建范围最小的新 Netlify token，并以受控方式验证它只能操作该 site。
2. 在 `runtime-canary` Environment 更新 `NETLIFY_AUTH_TOKEN`，不改变 site ID；用
   获授权的验证/部署演练确认新 token 可用。
3. 确认后在 Netlify 撤销旧 token，保留轮换审计记录但不记录 token 值。
4. token 疑似泄露时先撤销/禁用，暂停 dispatch 和 publication，检查最近 Deploy 与
   Environment audit trail；恢复必须走新的明确授权。

轮换或回滚不会使 Creator URL、PWA、Channel promotion 或物理设备验收自动成立。
