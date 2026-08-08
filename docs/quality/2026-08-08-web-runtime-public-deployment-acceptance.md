# Web Runtime Host 公共发布验收记录

## 状态：pre-deploy

本记录只描述 Product `1.0.15.2` / Web Runtime Host `1.1.2` 的公共发布前真相。
本地 deployment-tooling branch 已实现安全修正和 workflow 定义；它尚未 push、review、
CI 或 merge，也尚未获得远端执行授权。tag target
`72ae40074620cc5681c462ba04a31a666449734f` 已是 `origin/main` 上 PR #98 的 merge
commit；这不证明 deployment-tooling branch 已合并。本记录
不包含 Deploy ID、site ID、immutable URL、workflow run URL 或部署时间，因为这些值
当前均不存在。本地已存在 signed annotated tag `lmdj-v1.0.15.2`；`git tag -v` 的
Good signature primary fingerprint 是 `2B5EE362F058800036AD4FB5116ECE156F954D29`，
target 是 `72ae40074620cc5681c462ba04a31a666449734f`。该本地 tag 尚未 push，未做远端验证，
所以这不是远端 tag、Release 或部署存在的结论。

| Gate | Current result |
| --- | --- |
| Local deployment tooling security tests | implemented; final verification recorded in local commit/report only |
| Deployment-tooling branch push / PR review / CI / merge | not run |
| Target `72ae4007` on `origin/main` | yes; PR #98 merge commit |
| Netlify project `lmdj-runtime` | not authorized / not created |
| GitHub Environment secrets | not authorized / not configured |
| Immutable Deploy URL | absent |
| Production URL publication | not performed |
| Physical gates | deferred / unverified; unchanged |

## 已实现、但未发生的发布路径

本地代码定义两阶段 Netlify publication：从已签名的 Product tag 和 GitHub Release
验证 canonical remote signed tag、protected `origin/main` ancestor、精确 ZIP/checksum/
checksum signature 三资产，再取得并完整验证实际 prior published deploy，然后创建
immutable draft，分别对 draft 和生产别名运行 HTTP/Chromium smoke，并只将已 smoke 的
同一 Deploy ID 设为生产 alias。staged Release index/manifest digest 必须与 candidate
immutable 和 production 一致，prior 两个 URL 也必须逐字节一致。publish 后任何失败或
信号都 GET reconcile；candidate、exact prior、首次无 publication 之外的第三 ID 失败；
restore/disable 后 GET 必须证明 exact prior/disabled。workflow 目标 Environment 是
`runtime-canary`，所需 secret 名称是 `NETLIFY_RUNTIME_SITE_ID` 与
`NETLIFY_AUTH_TOKEN`。

Release checksum signature 在解析 checksum 前由仓库 Product public key exact primary
fingerprint 验证；tracked `_headers` 没有 `/assets/*`，只从已验证 manifest 组装九条 exact
immutable rule，unknown/source map 保持 `no-store`。HTTP/Chromium 均从 `/` 开始；HTTP
redirect 与最终 identity 受限，Chromium 断言 admitted/outcome 各 +1、rejected 不变并在
close 后保持。

这描述的是工具能力，不是远端事实：没有 GitHub 环境、Netlify site、secret、workflow
run、draft、production alias 变更或 evidence artifact 已创建。deployment-tooling branch
尚未 push/review/CI/merge；也没有远端 verified tag、Release、Channel promotion 或公共部署结论。

成功 evidence exact contract 是 `lmdj.web-runtime-host.deployment-evidence.v2`，包含 archive
filename/SHA、Release file digests、canonical Actions run ID/URL、真实 UTC start/end、
prior-good、immutable HTTP/browser、same-ID publish validated secret-safe official projection
与 production HTTP/browser。失败恢复 exact contract 是
`lmdj.web-runtime-host.deployment-recovery-evidence.v1`，包含 reconcile GET、restore/disable
官方 projection、post-action GET 与四项复验；disable 记录官方 204，不伪造 response。
workflow `always()` 上传两类 JSON 和完整日志。

## 固定候选身份

| 项目 | 值 |
| --- | --- |
| Product Build | `1.0.15.2` |
| Web Runtime Host | `1.1.2` |
| 本地 signed annotated Product tag | `lmdj-v1.0.15.2`（已存在；尚未 push，未做远端验证） |
| 本地 tag Good signature primary fingerprint | `2B5EE362F058800036AD4FB5116ECE156F954D29` |
| 本地 tag target | `72ae40074620cc5681c462ba04a31a666449734f` |
| 预期 release archive SHA-256 | `d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a` |

后续获得授权后，操作者必须按
[`docs/deploy/web-runtime-host.md`](../deploy/web-runtime-host.md) 执行，且仅在实际
evidence artifact 已审查后补记真实 ID、URL、run 和时间。不能以本地 proof 或本记录
中的候选身份代替远端 evidence。

## 不变的非结论

- proof-only Python server 仅用于本地 Proof，不是 Netlify 生产服务；生产将由 Netlify
  静态托管已验证 `dist`。
- `lmdj-canary` 属于未来 Creator，未创建且不属于 Runtime Host 本 Task。
- macOS Safari Pointer、macOS Chrome Pointer、macOS Chrome physical MIDI、iPadOS
  Safari Touch、iPadOS Safari lifecycle 仍为 `deferred / unverified`。
- 自动化部署 smoke 不构成 Creator Web/PWA、物理设备体验、`beta` 或 `stable` 验收。
