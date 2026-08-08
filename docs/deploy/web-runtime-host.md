# Web Runtime Host 公共发布运行手册

本运行手册描述正式 Web Runtime Host 的受控发布路径。它是操作说明，**不是**
执行记录，也不授权创建远端资源、写入 secret、发布 Release、运行 workflow 或部署。
当前真相见
[`docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md`](../quality/2026-08-08-web-runtime-public-deployment-acceptance.md)：
Product `1.0.15.2` / Host `1.1.2` 的本地工具已实现，但尚未 push、merge、创建
Netlify 项目、配置 GitHub Environment、运行部署或生成公共证据。

## 发布不变量

- 目标 Product tag 为 `lmdj-v1.0.15.2`，其签名 target 必须是
  `72ae40074620cc5681c462ba04a31a666449734f`。
- Release archive 的 SHA-256 必须是
  `d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a`。
- 唯一生产别名是 `https://lmdj-runtime.netlify.app`。先创建 immutable draft
  Deploy，再对**同一个** ready Deploy ID 运行 smoke，最后才允许把该 ID 设为生产别名。
- `scripts/web-runtime-host.sh proof` 的 Python proof-only server 只用于本地
  Proof；它不是生产服务。生产由 Netlify 静态托管已验证的 `dist`，并使用 release
  bundle 内的 `_headers`。
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

1. 在 Netlify 创建空的团队站点，站点名为 `lmdj-runtime`；记录平台返回的 site ID，
   不把它写入仓库、Issue 或日志。
2. 不连接 Git provider。若创建流程默认连接 Git，取消连接；若已有连接，先断开。
   在项目 Deploy 设置中关闭 automatic publishing / auto-publish，并确认没有 build
   command、publish directory、branch deploy 或 Deploy Preview 会替该项目发布。
3. 独立检查项目设置：Git repository 显示未连接，自动发布关闭，生产 URL 仅是
   `lmdj-runtime.netlify.app`。不要创建、别名化或重定向 `lmdj-canary`。
4. 将 site ID 仅保存为 GitHub Environment secret；此站点只能由下述 GitHub Actions
   路径以 API 创建 draft、smoke 后同 ID 发布，禁止手工拖拽/CLI 生产上传。

这一步完成前，任何 `lmdj-runtime` site ID、Deploy ID 或 immutable Deploy URL 都是
不存在的值，不能用占位符伪造为证据。

## GitHub Environment 与 secret

workflow `.github/workflows/deploy-web-runtime-host.yml` 使用 GitHub Environment
`runtime-canary`，且仅需要以下 secrets：

| Secret | 值 | 操作边界 |
| --- | --- | --- |
| `NETLIFY_RUNTIME_SITE_ID` | 已确认的 `lmdj-runtime` Netlify site ID | 只在 Environment `runtime-canary` 配置；不进入仓库或日志。 |
| `NETLIFY_AUTH_TOKEN` | 仅有该站点部署所需的最小权限 Netlify token | 只在 Environment `runtime-canary` 配置；不回显、不写入证据。 |

GitHub Actions 提供短期 `GITHUB_TOKEN` 读取固定仓库的 Release；它不是一个需手工添加
的 repository secret。配置后从 Environment 设置确认两个名称存在、值不可见，并在
workflow 的 Environment approval/protection policy（如已配置）通过后再 dispatch。
不要把 token 或 site ID 粘贴到 shell history、PR、runbook、artifact 或 Portal。

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

证据必须至少包含实际 `deploy_id`、immutable `deploy_url`、`git_revision`、Product
Build、Host version、tag、release URL、site ID 和 archive digest；确认 digest 等于上文
指定值、revision 等于指定 tag target，且证据不包含 token。只有成功的 evidence
artifact 可以填充验收记录的 ID、URL、run 与时间字段；发生失败时保留失败日志，不把
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

回滚不是重新构建或从当前分支重新上传。获授权后，以记录中的 `PRIOR_DEPLOY_ID` 对同一
site ID 调用 publication，再验证生产 URL：

```bash
NETLIFY_RUNTIME_SITE_ID='recorded-site-id' \
NETLIFY_AUTH_TOKEN='authorized-token' \
python3 apps/web-runtime-host/tools/deploy_orchestrator.py publish \
  "$NETLIFY_RUNTIME_SITE_ID" "$PRIOR_DEPLOY_ID"
scripts/web-runtime-deploy.sh smoke https://lmdj-runtime.netlify.app 1.0.15.2 1.1.2
```

`PRIOR_DEPLOY_ID` 必须来自先前已验证 evidence，且 publication 响应必须确认相同
ready ID 与正式 alias；未知、当前 draft、猜测或截断的 ID 一律不可使用。

## 凭据轮换

1. 先创建范围最小的新 Netlify token，并以受控方式验证它只能操作该 site。
2. 在 `runtime-canary` Environment 更新 `NETLIFY_AUTH_TOKEN`，不改变 site ID；用
   获授权的验证/部署演练确认新 token 可用。
3. 确认后在 Netlify 撤销旧 token，保留轮换审计记录但不记录 token 值。
4. token 疑似泄露时先撤销/禁用，暂停 dispatch 和 publication，检查最近 Deploy 与
   Environment audit trail；恢复必须走新的明确授权。

轮换或回滚不会使 Creator URL、PWA、Channel promotion 或物理设备验收自动成立。
