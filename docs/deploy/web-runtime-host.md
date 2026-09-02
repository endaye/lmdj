# Web Runtime Host 公共发布运行手册

本运行手册描述正式 Web Runtime Host 的受控发布路径。它是操作说明，**不是**
执行记录，也不授权创建远端资源、写入 secret、发布 Release、运行 workflow 或部署。
最初的 pre-deploy 证据快照见
[`docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md`](../quality/2026-08-08-web-runtime-public-deployment-acceptance.md)：
它冻结 Product `1.0.15.2` / Host `1.1.2` 在记录时的分支、tag 与部署状态，不是当前远端
控制面的动态真相。每次实际操作前都必须从 canonical origin 和 GitHub API 重新验证 remote
signed tag、受保护 `main` ancestry、Release 三资产、workflow run 与 deployment evidence；
不得从该快照、本地同名 tag、Portal 页面或先前命令输出推断当前状态。

## 当前双 Host Release 边界

历史 `1.0.15.2` 三资产 Runtime Release 与已公开的 `1.0.40.0` tag、Release、部署证据均保持
不可变；下文保留其精确操作证据，不能重写成新 profile。从后续获准 Product Build 起，当前
标准 profile 是 `web-hosts`：一个 Product Release 精确包含 Creator 与 Runtime 各自的
ZIP、checksum、detached checksum signature，共六项资产。Runtime verifier 先验证完整六资产
inventory，再只选择 Runtime 三项 staging；Creator verifier 独立选择 Creator 三项。

Creator 的生产 URL 是 `https://lmdj-creator.netlify.app/`，Runtime 保持
`https://lmdj-runtime.netlify.app/`。两条 workflow 都是 manual-only exact-tag dispatch，具有
不同的 Site、Environment、credential、smoke、evidence 和 exact prior rollback。公开 Release
不 fan-out deployment；Creator deployment 也不授权或触发 Runtime deployment，反之亦然。

## 发布不变量

- 目标 Product tag 为 `lmdj-v1.0.15.2`，其签名 target 必须是
  `72ae40074620cc5681c462ba04a31a666449734f`。
- Release archive 的 SHA-256 必须是
  `d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a`。
- canonical prerelease 必须精确包含三个资产：Host ZIP、`<archive>.sha256` 与
  `<archive>.sha256.asc`。最后一项是受信 Release checksum signer 对 checksum 文件的
  detached armored signature；部署器用该角色专属 public key 的唯一 primary fingerprint
  验证成功后才解析 checksum。Product tag signer、Release checksum signer、Release creator
  与 deployment operator 是分离角色；不记录私钥或 token，也不得用任一角色密钥替代另一角色。
- 已验证的 Release ZIP 未修改。`apps/web-runtime-host/deploy/_headers` 是
  repository-tracked deploy-control artifact：staging 时独立加入 Netlify digest deploy，
  不在 Release bundle 内；不得写入、删除、改名或替换任何已验证 Release `dist` 文件。
  tracked 文件只保留 base security 与默认 `no-store`；组装时从已验证 manifest 生成九条
  精确 immutable asset rule。禁止 `/assets/*` blanket；未知资产与 source map 保持
  `no-store`。
- 唯一生产别名是 `https://lmdj-runtime.netlify.app`。先创建 immutable draft
  Deploy，再对**同一个** ready Deploy ID 运行 smoke，最后才允许把该 ID 设为生产别名。
- `scripts/web-runtime-host.sh proof` 的 Python proof-only server 只用于本地
  Proof；它不是生产服务。生产由 Netlify 静态托管已验证的 `dist`，并应用独立 staging
  的 `_headers` deploy-control artifact。
- 这不是 Creator URL、Creator PWA 或 `lmdj-canary` 的发布。`lmdj-canary` 属于
  Creator 交付边界，不能在本 Task 创建、绑定、重定向或作为 Runtime Host 的别名。

## 签名密钥角色与备份

- Product tag 只信任 `.github/release-signing-keys/lmdj-product.asc`，主指纹为
  `2B5EE362F058800036AD4FB5116ECE156F954D29`。它保留用于验证既有不可变 Product tag，
  不授权新的 checksum signature。
- Release checksum 只信任 `.github/release-signing-keys/lmdj-release-checksum.asc`，主指纹为
  `CB928A6E89DE498851688EF1AAC3E7019FC1478B`。它不授权 Product tag。
- checksum 私钥使用权限为 `700` 的独立 `GNUPGHOME`（默认
  `~/.gnupg-lmdj-release`），由本机 pinentry 交互解锁；不得通过命令行、环境变量、聊天、
  GitHub secret、Release asset、workflow artifact 或仓库文件传递密码或私钥。
- 受信公钥进入仓库前，必须先在仓库外导出受密码保护的 armored secret-key backup 和
  revocation certificate，核对备份主指纹，并把备份复制到不与本机同时丢失的加密介质。
  没有可恢复备份时不得签名、轮换仓库 trust anchor 或发布。
- 轮换时生成 dedicated Ed25519 signing key，UID 为 `LMDJ Release Checksum Signer`，有效期
  两年；先完成备份 gate，再通过受保护 `main` 的独立 PR 更新 public key 与固定指纹。
  Product tag signer 的未来轮换与新 Product tag 是另一项发布任务。

## 独立授权的 tag、三资产 prerelease 与 dispatch

下列是获授权后的操作模板，不是本 Task 的执行记录。Release checksum signer 在受信
workstation 对 checksum 签名；Release operator 独立维护 canonical prerelease；deployment
operator 再独立 dispatch。各角色不得在文档、日志或 artifact 中记录私钥/token。

1. Release checksum signer 先核对 archive filename 与 SHA-256，再在受信 workstation 创建
   canonical detached armored signature：

   ```bash
   release_key_home="$HOME/.gnupg-lmdj-release"
   checksum_signer=CB928A6E89DE498851688EF1AAC3E7019FC1478B
   gpg --homedir "$release_key_home" --armor --detach-sign \
     --local-user "$checksum_signer" \
     --output "$archive.sha256.asc" "$archive.sha256"
   gpg --homedir "$release_key_home" --batch --status-fd 1 \
     --verify "$archive.sha256.asc" "$archive.sha256"
   ```

2. 获得独立 tag-push 授权后，只 push canonical annotated signed tag，并从 canonical
   origin 重新 fetch 到 scratch ref 核对远端对象，不以本地同名 tag 作为证明：

   ```bash
   git push origin refs/tags/lmdj-v1.0.15.2:refs/tags/lmdj-v1.0.15.2
   git fetch --no-tags origin \
     refs/tags/lmdj-v1.0.15.2:refs/lmdj-verify/tags/lmdj-v1.0.15.2
   git cat-file -t refs/lmdj-verify/tags/lmdj-v1.0.15.2
   git verify-tag refs/lmdj-verify/tags/lmdj-v1.0.15.2
   git merge-base --is-ancestor \
     refs/lmdj-verify/tags/lmdj-v1.0.15.2^{commit} origin/main
   git update-ref -d refs/lmdj-verify/tags/lmdj-v1.0.15.2
   ```

3. 获得独立 Release 授权后，创建 canonical prerelease 并一次上传精确三项；不得多传
   source map、替代 ZIP 或未签名 checksum：

   ```bash
   read -rsp 'Short-lived GitHub token: ' GITHUB_TOKEN; printf '\n'
   export GITHUB_TOKEN
   trap 'unset GITHUB_TOKEN' EXIT INT TERM
   gh release create lmdj-v1.0.15.2 \
     "$archive" "$archive.sha256" "$archive.sha256.asc" \
     --repo endaye/lmdj --verify-tag --prerelease \
     --title 'LMDJ Product 1.0.15.2 Web Runtime Host 1.1.2'
   scripts/web-runtime-deploy.sh verify lmdj-v1.0.15.2
   unset GITHUB_TOKEN
   trap - EXIT INT TERM
   ```

4. 只有远端 tag、protected `origin/main` ancestor、三资产 inventory/signature 与 bundle
   全部验证成功，Environment 已配置且本次 deployment 另获授权后，才可 dispatch：

   ```bash
   gh workflow run deploy-web-runtime-host.yml --ref main -f tag=lmdj-v1.0.15.2
   ```

Release `targetCommitish` 只作为非空辅助 metadata；tag 已存在时它不是 commit attestation。
部署器固定 canonical origin URL/repository，并自行 fetch remote tag 与 main scratch refs。

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

Netlify 创建空站点时可能同时建立一个状态为 `ready`、但当前文件列表精确为空的平台占位
Deploy。部署 preflight 必须按顺序读取 current site、官方 `GET /sites/{site_id}/files` 清单、
再读取一次 current site，并要求两次 site projection 完全一致。只有同一 current Deploy 的
validated file count 精确为 `0` 时，才把它视为“尚无可回滚 prior”，不对 404 占位 URL 运行
prior smoke，且成功 evidence 的 `prior_good` 保持 `null`。任何非空 current Deploy 仍必须完成
既有 prior identity 与 immutable/production smoke；清单无效、API 失败或两次 site identity
不同都在创建新 draft 前 fail closed。

站点创建完成前，任何 `lmdj-runtime` site ID、Deploy ID 或 immutable Deploy URL 都是
不存在的值，不能用占位符伪造为证据；平台返回的零文件占位 Deploy 也不是 prior-good 或
已发布 Runtime Host 的证据。

## GitHub Environment 与 secret

workflow `.github/workflows/deploy-web-runtime-host.yml` 分为两个 job。`preflight` 不声明
`environment`，因此拿不到下述任何 Environment secret：它只用 Python 和 GitHub Actions 短期
`GITHUB_TOKEN` 运行 `scripts/web-runtime-deploy.sh` 的只读 `verify` 子命令，完成 signed
tag、protected `main` ancestry、Release 三资产与角色分离 checksum signature 的验证以及资产
staging，并且不安装 Node/Chromium。只有它通过后，`deploy` job 才使用 GitHub Environment
`runtime-canary`，并在任何 Netlify mutation 之前对同一 Release 重新验证一次。也就是说，
Netlify credential 与浏览器工具链都只在 Release 已被证明可信之后才进入运行环境。

site ID 本质上不是 secret，但按已批准的 scoped configuration contract
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

若在受信 workstation 临时运行只读 `verify`，必须为该示例显式读取短期
`GITHUB_TOKEN`，用无回显读取且立即注册清理，不把 token 写进命令历史：

```bash
read -rsp 'Short-lived GitHub token: ' GITHUB_TOKEN; printf '\n'
export GITHUB_TOKEN
trap 'unset GITHUB_TOKEN' EXIT INT TERM
scripts/web-runtime-deploy.sh verify lmdj-v1.0.15.2
unset GITHUB_TOKEN
trap - EXIT INT TERM
```

只使用短期、最小只读范围 token；不得在 shell 命令行写 `GITHUB_TOKEN=真实值`，不得
保存到 `.env`、history、tracked file、日志或 evidence。部署 workflow 使用 GitHub 提供的
短期 token，不复制到 Netlify child；Netlify token 同样不进入 gh/local helper。

## 受控执行与证据检查

获授权的 workflow 只接受发布事件的 prerelease tag 或手动输入的精确 Product tag，
并固定 checkout `main`。它执行：签名 tag/Release/archive 验证 → staging → Netlify
current site/file inventory/current site 稳定性 preflight → 非空 prior discovery/immutable+production smoke → draft → immutable URL HTTP 和 Chromium smoke → 同 Deploy ID production publication →
生产 URL HTTP 和 Chromium smoke → artifact evidence。

HTTP smoke 从 `/` 开始，只允许直接 200，或一次严格同源、无 query/fragment 且最终仅到
`/index.html` 的 redirect；随后验证 `no-store`、全部 security headers、manifest identity、
九资产 exact immutable 与 unknown/source map `no-store`。Chromium 同样从 `/` 开始，点击
前后要求 admitted 与 outcome 各精确 `+1`、rejected 不变，并在 close 后再次确认计数保持。

调度后记录并审查 workflow run，而不是仅凭 Actions 页面上的绿色图标宣布发布：

```bash
gh run list --workflow deploy-web-runtime-host.yml --limit 5
gh run view RUN_ID --log
gh run download RUN_ID --name runtime-host-deployment-evidence --dir evidence/RUN_ID
python3 -m json.tool evidence/RUN_ID/evidence.json
```

`evidence.json` 的 exact top-level schema 是
`lmdj.web-runtime-host.deployment-evidence.v2`：

| 字段 | 精确内容 |
| --- | --- |
| `archive` | `{filename, sha256}`，保留 canonical archive filename 与 digest。 |
| `release_files` | `{index_sha256, manifest_sha256}`；与 verified staged Release bytes、candidate immutable 与 production HTTP 结果逐字节绑定。 |
| `github_actions` | `{run_id, run_url}`；URL 必须为 `https://github.com/endaye/lmdj/actions/runs/<run_id>`。 |
| `started_at`, `ended_at` | 本次受控部署的 UTC 起止时间。 |
| `git_revision`, `tag`, `release_url`, `product_build`, `host_version`, `site_id`, `channel` | 已验证 provenance 与 live identity。 |
| `prior_good` | `null`，或发布前 `GET site` 的 validated secret-safe official projection、发现的 prior Product/Host、prior immutable 与 production 的 HTTP/browser 结构化结果及时间；两 URL 的 index/manifest digest 必须一致。 |
| `immutable` | `{deploy_id, deploy_url, http, browser}`；`http.result` 保留完整 HTTP smoke JSON。 |
| `publication` | `{same_deploy_id, response}`；`response` 是字段 allowlist 为 `id/site_id/state/ssl_url/deploy_ssl_url/published_at` 的 validated secret-safe official projection；Netlify 的 `published_at` 允许并原样保留 UTC `Z` 时间戳中的可选小数秒，不声称保存 raw exact response。 |
| `production` | `{url, http, browser}`；HTTP/browser 均含结构化结果和时间。 |

失败恢复写入独立、原子替换的 `recovery-evidence.json`，contract 为
`lmdj.web-runtime-host.deployment-recovery-evidence.v1`，exact top-level 字段是
`action`、`attempted_deploy`、`original_status`、`prior_deploy`、`reconcile`、
`post_recovery_site`、`recorded_at`、`recovery_response`、`status`、`validation` 与 `contract`。
其中 `reconcile` 与 `post_recovery_site` 保留失败前后 `GET site` 的 validated secret-safe
official projection；restore 的 `recovery_response` 使用上述明确 allowlist，disable 只记录
官方 204 为 `{status_code: 204}`，不伪造 action response，
`validation` 保留 prior immutable 与 production 的 HTTP/browser 复验结构和恢复状态。
workflow 以 `if: always()` 上传 `evidence.json`、`recovery-evidence.json` 与完整
`deployment.log`；不得丢弃 HTTP JSON 或 restore response。

artifact 字段仍须与不可变 GitHub run metadata 和 workflow log 相互一致；只有成功 schema、
canonical run URL、same-ID response 与两阶段 smoke 全部一致，才可填充验收记录。失败 draft
不是发布证据。

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
| remote tag/signature、三资产 inventory/checksum signature、archive digest 或 bundle identity 失败 | 停止；不要创建 Netlify Deploy。修复 release provenance 后从验证重新开始。 |
| current site/file inventory/current site preflight 无效、API 失败或身份变化 | 停止；official site response 的 `disabled: true` 必须规范化为 validated projection 的 `state: disabled`；不要把不稳定、禁用或未知站点状态分类为首次发布，也不要创建新 draft。 |
| prior published deploy/identity/smoke 失败 | 停止；未建立本次 prior-good 前不要创建或发布新 Deploy。 |
| draft 创建或 immutable URL HTTP/Chromium 失败 | 不发布该 draft；保存 workflow artifact/log，诊断后创建新的 draft。失败 draft 没有生产资格。 |
| publish API error、production HTTP/Chromium failure、ERR、INT/TERM 或内部 timeout | workflow 自动重新 `GET /sites/{site_id}` reconcile；当前 ID 只允许 candidate、exact prior，或首次发布时为空；未知第三 ID 必须 recovery FAIL。 |
| alias 指向新 Deploy 且 prior-good 存在 | `POST /sites/{site_id}/deploys/{prior_id}/restore` 恢复 exact prior，随后 GET 必须确认 exact prior，再对 prior immutable 与 production 运行完整 HTTP/Chromium，原子写 recovery evidence。 |
| alias 指向新 Deploy 且首次没有 prior | 使用官方 reversible `PUT /sites/{site_id}/disable` 撤下站点；记录 204 后 GET 必须确认 disabled，并写 recovery evidence；不得伪造 rollback。 |
| preflight 发现 official `disabled: true`（validated projection 为 `state: disabled`） | 拒绝自动 enable 或 publication，升级给独立授权操作。 |
| evidence artifact 缺失、字段不匹配或含敏感信息 | 将部署视为证据不完整；不要更新 acceptance/Portal 为 deployed，先修复证据链。 |

恢复不是重新构建、重新上传或猜 Deploy ID。prior identity 来自发布前官方 site response 与
该 immutable manifest 的实际 Product/Host；脚本先 smoke prior immutable URL，再 smoke
production alias，建立本次 prior-good。publish 后失败即使 API 返回 error，也必须 GET
reconcile，而不能假设 alias 未切换。workflow 内部 1,080 秒 timeout 先发送 TERM，另留
900 秒 kill budget。恢复的三个 API 阶段各 30 秒、两次 HTTP 各 180 秒、两次 Chromium
各 180 秒、证据写入 30 秒，最坏 840 秒并另留 60 秒；deploy step 为 35 分钟，
checkout/setup/install/select/upload 各有显式上限，75 分钟 job timeout 覆盖所有最坏和与
上传余量。

现有 workflow 没有独立的人工 rollback dispatch；正常部署的失败恢复已内建在同一受保护
Environment run 中。任何事后手工恢复仍需单独授权，且必须使用已验证的 exact prior
Deploy ID，不得把当前 draft 或未知 ID 冒充 prior。

## 凭据轮换

1. 先创建范围最小的新 Netlify token，并以受控方式验证它只能操作该 site。
2. 在 `runtime-canary` Environment 更新 `NETLIFY_AUTH_TOKEN`，不改变 site ID；用
   获授权的验证/部署演练确认新 token 可用。
3. 确认后在 Netlify 撤销旧 token，保留轮换审计记录但不记录 token 值。
4. token 疑似泄露时先撤销/禁用，暂停 dispatch 和 publication，检查最近 Deploy 与
   Environment audit trail；恢复必须走新的明确授权。

轮换或回滚不会使 Creator URL、PWA、Channel promotion 或物理设备验收自动成立。
