# Creator Web Host 公共部署运行手册

> 2026-09-08 退役更新：旧 Netlify 站点已按用户授权删除，对应 GitHub 手动部署
> workflow 已停用。下述 Netlify 路径仅供历史审计，不再是可用的生产或回滚入口。
> 当前部署与恢复使用 [Cloudflare Host 手册](cloudflare-hosts.md)，
> 资源及数据边界见 [退役记录](2026-09-08-retired-site-deletion.md)。

## Cloudflare 迁移目标（2026-09-08）

用户已选择固定地址 `https://creator.lmdj.workers.dev/`，对应 LMDJ account
`0b62b8881c07f48f7935f5380a1f55db` 的 Worker `creator`。
配置位于 `apps/creator-web/deploy/wrangler.json`，默认关闭主访问路由，启用版本
Preview；这份配置本身不是上线证据。部署输入必须来自经签名验证的 Release，放在
`build/deploy/cloudflare/creator/dist`，附加由已验证 manifest 生成的 `_headers`。
使用 `python3 apps/creator-web/deploy/cloudflare_headers.py VERIFIED_DIST` 生成
响应头；除既有安全与精确资产缓存规则外，显式声明 HTML/JS/CSS 的 UTF-8 charset。
Cloudflare 版本 Preview 会覆盖 `X-Robots-Tag` 为 `noindex`，仅 Preview 检查接受此
平台差异；固定地址检查要求完整 robots directives。
`cloudflare_worker.mjs` 只处理 `/` 到 `index.html` 的内部映射，保持两者均直接返回
相同的已签名 HTML；其余路径直接由静态资产服务响应。响应头生成器消除 Netlify
规则迁移后产生的重复值，并为精确 manifest 资产重置默认缓存。

使用 `python3 apps/creator-web/deploy/cloudflare_smoke.py VERIFIED_DIST URL`
验证固定地址，版本 Preview 额外传入 `--preview`。此检查要求响应逐字节匹配经签名验证
的输入，并检查 MIME、安全响应头、精确缓存规则和未知路径 404。编码的 `..` 路径
在远端边缘可被拒绝，在本地模拟器可被规范化；该探针要求有效的 400/404 拒绝，
或内容严格等于已验证的公开 index。输出是迁移观察，不冒充原有
Netlify deployment evidence Contract。浏览器测试仍使用原有 Creator deployment suite。
本次固定入口的 HTTP、浏览器和签名包身份观察记录在
[`2026-09-08-cloudflare-creator-observation.json`](2026-09-08-cloudflare-creator-observation.json)。
禁止用源码重建产物冒充同一个 Release。只有候选验证通过后才启用固定访问地址；
首次上线验证失败时关闭该路由。下述 Netlify 事务源码保留供历史审计，旧站点已删除。

本手册定义 Creator Web Host 的受控生产部署路径。它是操作契约，不是执行记录；文档、
workflow 或本地 Proof 的存在都不表示 Netlify Site 已创建，也不授权 Release publication、
Creator deployment、Runtime deployment 或 Channel promotion。

隔离恢复演练使用显式 `--recovery-target`：Creator 对应
`creator-recovery.lmdj.workers.dev`，Runtime 对应 `lab-recovery.lmdj.workers.dev`。
使用该标志时拒绝正式 Worker 地址，默认模式也拒绝恢复地址；版本预览还需
`--preview`，且前缀必须是实际版本 ID 的八位十六进制短前缀。
检查仍逐文件比对已独立验证的 Release 字节，并保留 MIME、缓存、安全头和
未知路径要求。这个只读检查命令不会创建、部署或切换 Worker。

## 当前交付边界

- 当前标准 Release profile 是 `web-hosts`：同一个 Product tag 的 canonical Release 精确包含
  Creator ZIP/checksum/signature 与 Runtime ZIP/checksum/signature，共六项签名资产。
- Creator 部署只从六资产 Release 选择 Creator 三项，验证整份六资产 inventory 后才 staging；
  不重建源码、不修改 Release ZIP，也不读取 Runtime payload 作为 Creator 内容。
- Creator 生产 URL 固定为 `https://lmdj-creator.netlify.app/`；Runtime 生产 URL 固定为
  `https://lmdj-runtime.netlify.app/`。两个 URL、Site、Deploy ID、Environment、凭据、smoke、
  evidence 与 exact prior rollback 完全独立。
- `.github/workflows/deploy-creator-web.yml` 只有 `workflow_dispatch`，是 manual-only exact-tag
  transaction；Release publication 不 fan-out 到 Creator 或 Runtime，Creator dispatch 也不触发
  Runtime deployment。
- 历史 Product Build `1.0.40.0` 的 tag、Release 与 Runtime deployment 保持不可变；六资产
  `web-hosts` profile 只适用于后续明确分配、合并并获授权的 Product Build。

## 一次性外部 Site 配置

获得单独的 Site provisioning 授权后，在 Netlify 创建未连接 Git provider 的空站点
`lmdj-creator`，关闭 automatic publishing、branch deploy 与 Deploy Preview。确认唯一生产 URL
是 `https://lmdj-creator.netlify.app/`，然后在 GitHub Environment `creator-canary` 中配置：

| 配置 | 边界 |
| --- | --- |
| `NETLIFY_CREATOR_SITE_ID` | Netlify 返回的精确 Creator Site ID；它是非敏感身份，但按 scoped configuration contract 存在 Environment secret 中。 |
| `NETLIFY_AUTH_TOKEN` | 仅能部署 Creator Site 的最小权限 token；不得进入日志、artifact、文档或 evidence。 |

站点创建完成前，任何 Creator Site ID、Deploy ID 或 immutable deploy URL 都不存在，不能用
占位符、Runtime Site 身份或本地 server 冒充 live evidence。Site provisioning、Environment
配置和 deployment dispatch 是三个独立授权边界。

## 验证与手动 dispatch

每次操作先重新审计 canonical remote tag、protected `main` ancestry、公开 Release、六资产闭合
inventory、两种 signer 角色和 Creator bundle identity。只读验证与获授权后的 dispatch 为：

```bash
scripts/release.sh audit --remote --tag lmdj-vPRODUCT_BUILD
scripts/creator-web-deploy.sh verify lmdj-vPRODUCT_BUILD
gh workflow run deploy-creator-web.yml --ref main -f tag=lmdj-vPRODUCT_BUILD
```

`verify` 不读取 Netlify credential。workflow 的 preflight job 也不进入 Environment；只有其通过
后，deploy job 才进入 `creator-canary`，重新验证同一 Release，再读取
`NETLIFY_CREATOR_SITE_ID` 与 `NETLIFY_AUTH_TOKEN`。

## 部署事务与证据

事务先稳定读取 current Site/file inventory/current Site。非空 prior 必须在 immutable 与
production URL 上通过 Creator HTTP/Chromium smoke；零文件占位 Deploy 只表示无 prior，不能
作为已发布 Creator 的证据。随后创建 immutable draft，对同一个 ready Deploy ID 运行：

1. HTTP identity、security/cache headers 与 exact asset inventory；
2. Chromium import/open Project、audio activation、Pad admission/outcome、Sample replacement、
   Sequence commit 与 reload/reopen durable truth；
3. 将同一个 Deploy ID 发布为生产 alias；
4. 在 `https://lmdj-creator.netlify.app/` 重跑两类 smoke。

成功 artifact 使用 `lmdj.creator-web.deployment-evidence.v1`，只保留已验证的 Product/Host、
tag/revision、archive digest、Release URL、GitHub run、Site/Deploy identity、prior、immutable、
publication、production、时间与状态 allowlist。失败恢复使用
`lmdj.creator-web.deployment-recovery-evidence.v1`；publish 后即使 API 返回 error，也先 reconcile
production alias。若 alias 仍是 attempted Deploy，必须恢复 exact prior 并复验；首次发布没有
prior 时使用可逆 Site disable。未知第三 Deploy ID 必须 fail closed，不覆盖它。

调度后审查 workflow run 与 artifact：

```bash
gh run list --workflow deploy-creator-web.yml --limit 5
gh run view RUN_ID --log
gh run download RUN_ID --name creator-host-deployment-evidence --dir evidence/RUN_ID
python3 -m json.tool evidence/RUN_ID/evidence.json
```

只有 workflow 成功、证据 schema/identity 完整且生产 URL 再验证通过，才可以报告 Creator
deployed。该结论不自动证明 Runtime deployed、Release promoted 或任何物理 MIDI/Touch/听感门。

## 回滚与停机条件

Release/tag/signature/bundle、Site identity、prior smoke、candidate smoke 或 evidence 任一失败都
停止后续 mutation。draft 创建前失败无需回滚；draft 后但 publish 前失败不改变生产 alias；
publish 后失败按上述 reconcile 恢复 exact prior 或首次发布 disable。删除历史 Deploy、改写
Release、移动 tag、把 Runtime Site 当 Creator Site，均不属于正常恢复路径。

## 保留已验签的 Cloudflare 暂存输入

在已有 GitHub 只读认证环境下，使用：

```bash
scripts/creator-web-deploy.sh stage TAG /absolute/path/to/new-stage
```

该命令复用 `verify TAG` 的远端 tag、签名、Release 元数据和 Host 包检查，
然后保留 `dist/`、原始发布包及校验和/签名、精确源码 `source.tar` 和
逐文件 SHA-256/字节数记录 `stage.json`。目标目录必须不存在；失败目录不得
当作成功暂存复用。命令不会上传、发布或修改 Cloudflare 路由。

`stage.json` 是内部暂存记录，不是部署证据或发布授权。后续部署命令仍须
重新验证保留的签名和资源，并核对实时目标、版本及操作记录；不能仅凭此文件发布。

## Cloudflare operator commands

The shared [Cloudflare Host runbook](cloudflare-hosts.md) documents signed
candidate, verify, promote, recover, inspection and explicit reconciliation.
Use the Host-specific target and verified release tag. HTTP command success does
not replace this Host's browser/manual migration acceptance.
