# Web Runtime Host 公共发布验收记录

## 状态：pre-deploy

本记录只描述 Product `1.0.15.2` / Web Runtime Host `1.1.2` 的公共发布前真相。
Task 1–5 已实现本地部署工具和 workflow 定义；它们尚未获得远端执行授权。本记录
不包含 Deploy ID、site ID、immutable URL、workflow run URL 或部署时间，因为这些值
当前均不存在。本地已存在 signed annotated tag `lmdj-v1.0.15.2`；`git tag -v` 的
Good signature primary fingerprint 是 `2B5EE362F058800036AD4FB5116ECE156F954D29`，
target 是 `72ae40074620cc5681c462ba04a31a666449734f`。该 tag 尚未 push，未做远端验证，
所以这不是远端 tag、Release 或部署存在的结论。

| Gate | Current result |
| --- | --- |
| Local deployment tooling tests | pending implementation verification |
| PR review and CI | not run |
| Netlify project `lmdj-runtime` | not authorized / not created |
| GitHub Environment secrets | not authorized / not configured |
| Immutable Deploy URL | absent |
| Production URL publication | not performed |
| Physical gates | deferred / unverified; unchanged |

## 已实现、但未发生的发布路径

本地代码定义两阶段 Netlify publication：从已签名的 Product tag 和 GitHub Release
验证 archive，再创建 immutable draft，分别对 draft 和生产别名运行 HTTP/Chromium
smoke，并只将已 smoke 的同一 Deploy ID 设为生产 alias。workflow 目标 Environment 是
`runtime-canary`，所需 secret 名称是 `NETLIFY_RUNTIME_SITE_ID` 与
`NETLIFY_AUTH_TOKEN`。

这描述的是工具能力，不是远端事实：没有 GitHub 环境、Netlify site、secret、workflow
run、draft、production alias 变更或 evidence artifact 已创建。尚未 push 或 merge，
也没有远端 verified tag、Release、Channel promotion 或公共部署结论。

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
