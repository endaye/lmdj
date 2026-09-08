# Web Runtime Public Deployment Design

日期：2026-08-08

状态：规格已批准

目标渠道：`canary`

## 1. 结论

LMDJ 为 Formal Web Runtime Host 建立一个公开可分享、无需登录、但主动禁止
搜索引擎索引的独立诊断站点：

```text
https://lmdj-runtime.netlify.app/
```

该站点长期属于产品中立的 Runtime 诊断与一致性验证面，不是 Creator Editor，
也不成为 Creator 的网络依赖。未来 Creator Editor 使用独立的产品渠道入口：

```text
https://lmdj-canary.netlify.app/
https://lmdj-beta.netlify.app/
```

本 Task 只设计和交付 `lmdj-runtime.netlify.app`。`lmdj-canary` 与
`lmdj-beta` 只是命名保留，不创建站点、不部署占位页，也不代表 Creator、`beta`
或 `stable` 已交付。

## 1.1 批准的最终安全修正（2026-08-09）

本节是已批准设计的一部分；与后文早期“两资产、仅本地 tag、发布后人工判断”描述冲突时，
以本节为准。Version impact: none；该修正只改变尚未发布的部署控制面，Product/Host/Core
字节与身份不变。Documentation impact: required：同步
`/operations/version-and-release/`、`/hosts/web-runtime/`、`/platform/web-runtime/`。

- 每个 canonical prerelease 必须精确包含 Host ZIP、`<archive>.sha256` 与由专用 Release
  checksum signer 对 checksum 文件签名的 detached armored `<archive>.sha256.asc`。Product
  tag 继续只信任仓库 Product public key 与主指纹
  `2B5EE362F058800036AD4FB5116ECE156F954D29`；checksum signature 只信任独立 public key 与
  主指纹 `CB928A6E89DE498851688EF1AAC3E7019FC1478B`。部署器先验证角色专属签名，之后才允许
  解析 checksum；两把 key 不得互相替代，初始 tag target 与 archive digest pin 继续保留。
  checksum 私钥在仓库外的独立 GNUPGHOME 中生成，并在更新 trust anchor 前完成加密私钥与
  revocation certificate 备份；私钥、密码与 token 不进入 Release、仓库、日志或证据。
- 本地同名 tag 不具权威性。部署器固定 canonical `endaye/lmdj` origin，fetch 远端
  annotated signed tag 与 `origin/main` 到 scratch refs，验证 tag peel 是 protected
  `origin/main` 的祖先。Release `targetCommitish` 仅是非空辅助 metadata，不是 attestation。
- 发布前必须从 Netlify `GET /api/v1/sites/{site_id}` 取得实际 `published_deploy`；若存在，
  从其 immutable manifest 发现真实 Product/Host identity，并先对 prior immutable URL 与
  production alias 各运行完整 HTTP/Chromium。发布后任何 production smoke failure、ERR、
  INT/TERM、受控 timeout 或 publish API error 都先重新 GET reconcile。current ID 只允许
  candidate、exact prior，或首次发布时为空；未知第三 ID 失败。candidate 才可 restore exact
  prior 或 disable；restore 后 GET 必须确认 exact prior，disable 的 204 后 GET 必须确认
  disabled。若站点预先 disabled，拒绝自动 enable 或 publication。
- tracked `_headers` 只保留 base security/no-store。deploy assembly 从已验证 manifest 生成
  九条 exact immutable asset rules；`/assets/*` blanket 禁止，未知 asset/source map 保持
  `no-store`，Release `dist` 不变。
- HTTP 从 `/` 开始，只接受 200 或一次严格同源且最终仅 `/index.html` 的 redirect，并验证
  no-store、安全 headers 与最终 identity。Chromium 同样从 `/` 开始，要求 admitted/outcome
  各精确 +1、rejected 不变，close 后仍保持。
- 成功 evidence 使用 `lmdj.web-runtime-host.deployment-evidence.v2`；失败恢复使用原子
  `lmdj.web-runtime-host.deployment-recovery-evidence.v1`。HTTP 的 index/manifest digest 将
  staged Release、candidate immutable 与 production bytes 绑定，prior 两个 URL 也必须一致。
  Netlify API 证据是 validated secret-safe official allowlist projection，不声称是 raw response；
  disable 记录官方 204 与 post-disable GET。真实 canonical UTC 时间与 HTTP/browser identity
  逐字段交叉绑定。workflow 以 1,080 秒 main、900 秒 recovery kill budget、每个恢复阶段的
  显式 timeout 与 75 分钟 job 上限覆盖 setup、deploy、最坏恢复、证据和 always-upload 余量。
- GitHub、Netlify 与本地 helper 使用互斥 credential scope：gh 不接收 Netlify credential；
  Netlify child 不接收 `GITHUB_TOKEN` 或 `GH*`；metadata/stage/evidence/smoke helper 不接收
  任何部署凭据。

## 2. 决策

| ID | 决策 |
| --- | --- |
| D1 | Web Runtime Host 与 Creator Editor 是不同职责、不同生命周期的独立 Host，不是前后替代关系。 |
| D2 | Runtime 诊断站点使用稳定域名 `lmdj-runtime.netlify.app`；Product Build 不进入固定域名。 |
| D3 | 固定域名指向最新获准发布的 Runtime 诊断版本；每次成功部署的 Netlify Deploy permalink 保留不可变版本证据。 |
| D4 | 生产部署只消费已发布且校验通过的 GitHub Release Host ZIP，不从分支工作树或 Netlify 环境重新编译 Host。 |
| D5 | 首次部署使用 `lmdj-v1.0.15.2` Release 中 Product `1.0.15.2`、Host `1.1.2` 的原始 ZIP。 |
| D6 | 站点无需登录，但所有响应主动发送 `X-Robots-Tag: noindex, nofollow, noarchive`。 |
| D7 | COOP、COEP、CORP、CSP、WASM MIME 与 cache policy 是发布门禁，不是可选优化。 |
| D8 | 部署失败不得替换当前 published deploy；回滚恢复先前不可变 Deploy，不重写 tag、Release 或 Build 证据。 |

## 3. 角色与长期共存

Stage 6 Formal Web Runtime Host 是 diagnostic and conformance Host。它证明
Emscripten、SharedArrayBuffer、AudioWorklet、OPFS、Application Facade、输入适配、
生命周期和错误恢复可以在浏览器正式分发包中共同成立。它不是 Creator Editor 或
公开产品 UI。

Creator Editor 是未来的 LMDJ 产品 UI。Creator 与 diagnostic Host 可以复用相同的
产品中立 Web Runtime Platform，但 Creator 不通过 iframe、redirect、HTTP API 或
其他网络请求调用 `lmdj-runtime.netlify.app`。因此：

- Runtime 诊断站点下线不会让 Creator 停止工作；
- Runtime 诊断站点下线会失去独立的远程复现、设备验证和 Runtime 故障隔离入口；
- Creator 上线不自动授权删除 Formal Web Runtime Host、从 Assembly 移除它或停止
  它的 Proof；
- 是否永久停止公开诊断站点必须由未来独立的退役设计决定。

Architecture Portal 继续使用 `https://lmdj.netlify.app/`，与 Runtime 诊断站点和
未来 Creator 渠道站点互不替代。

## 4. Approved Scope

本设计包含：

1. 一个独立 Netlify project 和稳定 production URL；
2. 从已发布 GitHub Release 取得精确 Host ZIP 与 detached SHA-256 文件；
3. Release/tag/manifest/文件摘要的 provenance 校验；
4. 不修改 Host ZIP 内容的静态部署；
5. Netlify 响应头、MIME 与 cache policy；
6. GitHub Actions 自动发布入口和显式 tag 的人工重试入口；
7. 部署前校验、部署后 HTTP smoke 与真实浏览器 smoke；
8. Deploy ID、immutable URL、Product Build、Host version、tag 与 Git SHA 记录；
9. 失败保持当前线上版本与恢复先前 Deploy 的回滚流程；
10. Architecture Portal current 文档同步。

## 5. Explicit Non-goals

本设计不包含：

- Creator Editor、PWA、营销站或完整产品视觉设计；
- 创建或部署 `lmdj-canary.netlify.app`、`lmdj-beta.netlify.app`；
- `beta`、`stable` 或其他 Channel promotion；
- 用户账号、密码、团队登录或访问控制；
- 网络 API、数据库、遥测、分析、用户内容上传或云同步；
- 修改 Core、Application Facade、Project Truth、Runtime Snapshot 或 Host 私有协议；
- 用远程自动化替代 Pointer、Physical MIDI、Touch、生命周期或声学延迟物理验收；
- 将 proof-only Python loopback server 暴露到公网；
- 手工拖拽 ZIP、Netlify UI 文件上传或从未发布分支直接覆盖 production。

## 6. 发布拓扑

```text
signed annotated Product tag
          │
          ▼
GitHub prerelease / canary Release
          │
          ├─ Host ZIP
          └─ Host ZIP.sha256
          │
          ▼
GitHub Actions deployment gate
  ├─ validate tag and Release identity
  ├─ download exact assets
  ├─ verify detached SHA-256
  ├─ verify Host manifest and inventory
  └─ stage the unchanged dist
          │
          ▼
Netlify project: lmdj-runtime
  │
  ▼
draft atomic Deploy
  └─ deploy permalink (immutable pre-publication evidence)
          │
          ▼
immutable HTTP smoke + browser runtime smoke
          │
          ▼
publish the same Deploy ID through restore API
  └─ production URL (mutable latest pointer)
          │
          ▼
production-alias smoke
```

Netlify 不拥有 Host 编译步骤。Emscripten build、clean-room Proof、字节可复现 package
和 Release asset publication 在进入部署工作流前已经完成。部署工作流只验证并发布
相同字节，避免 Netlify 环境重建出一个没有 Release provenance 的第二份候选。

Netlify project 不连接 Git repository，并保持 Git-triggered auto publishing 关闭。工作流
通过 Netlify REST digest API 创建 `draft: true` 的 atomic Deploy，只上传 API 返回的
required files，验证其 immutable Deploy URL 后，再调用 Netlify
`restoreSiteDeploy` API 发布同一个 Deploy ID。不得上传第二份 production Deploy 来
模拟提升，也不得引入运行时下载的未锁定 Netlify CLI。

## 7. 触发与授权

### 7.1 正常触发

正常路径由 GitHub `release.published` 事件触发。工作流只接受：

- 仓库内的 LMDJ Product Release；
- 符合 `lmdj-vPRODUCT_BUILD` 格式的 annotated Product tag；
- `canary` 对应的 GitHub prerelease；
- 同一 Release 中唯一且命名匹配的 Host ZIP 与 `.sha256`；
- Release、tag target、Host manifest Product Build 相互一致。

任一身份不一致时，工作流在调用 Netlify 之前失败。

### 7.2 首次部署与重试

因为 `lmdj-v1.0.15.2` Release 已在部署工作流存在之前发布，首次部署通过
`workflow_dispatch` 输入精确 tag `lmdj-v1.0.15.2`。同一入口也用于基础设施失败后的
显式重试。它不得接受 branch、裸 SHA、`latest` 或可移动引用。

人工 dispatch 只重试相同发布流程，不放宽校验、重建资产或自动提升 Channel。

### 7.3 外部状态权限

实现代码和文档的本地 commit 不授权以下外部动作：

- 创建或重命名 Netlify project；
- 写入 GitHub Actions secrets；
- push、Pull Request、merge；
- 执行首次 production deploy；
- 回滚或 Channel promotion。

这些状态转换必须分别获得明确授权。

## 8. Artifact 与 Provenance Gate

工作流必须按以下顺序执行：

1. 从受保护 `main` checkout 已合入的 deployment tooling；从 pinned canonical origin 把
   tag 与 `main` fetch 到 scratch refs，忽略本地同名 tag，并另建只读 detached tag-target
   checkout；Product/Host manifest、distribution verifier 与版本真值全部取自 tag target；
2. 证明 remote tag 是 annotated signed Product tag、签名来自受信 Product key，peeled
   commit 是 GitHub-proven-protected canonical `main` 的 ancestor；
3. 读取 GitHub Release metadata，确认 Release 非 draft、是 prerelease；
4. 解析 Product Build，并要求 Release inventory 精确为 Host ZIP、detached checksum 与
   canonical armored detached checksum signature 三资产；`targetCommitish` 仅是辅助 metadata；
5. 下载精确三资产，拒绝 redirect 后名称或数量不匹配；
6. 用仓库 Release checksum public key 的 exact primary fingerprint 先验证 checksum signature，
   然后才解析并校验 detached SHA-256；
7. 安全解压到新建临时目录，拒绝绝对路径、`..`、symlink、hardlink 和额外顶层根；
8. 使用 tag target 的仓库 verifier 验证 `host-manifest.json`、完整 inventory、资产摘要、
   Product Build、Host version、Emscripten identity 和 index meta；
9. 证明解压后的 deploy root 与 Release Host distribution 字节一致；
10. 从已验证产品文件与仓库跟踪的 `_headers` deploy-control template 生成 Netlify
    digest，调用 REST API 创建 draft Deploy 并只上传 required files；
11. draft smoke 成功后，只用该 Deploy ID 执行 publish/restore。

`_headers` 是 Netlify 消费的 deploy-control artifact，不属于 Release Host ZIP、Host
distribution contract 或产品资产。staging 不写入、删除或改名任何已验证 Host dist
文件；部署后 Host 的 canonical manifest inventory 仍描述被发布的全部产品文件。

## 9. HTTP 与浏览器安全合同

### 9.1 所有响应

所有 Host 路径必须发送：

```text
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
Content-Security-Policy: <与正式 proof server 相同的固定 CSP>
X-Content-Type-Options: nosniff
X-Robots-Tag: noindex, nofollow, noarchive
```

不得加入 `unsafe-inline`、第三方 script、analytics、远程字体、外部媒体或额外
`connect-src`。站点保持 same-origin、无遥测的诊断分发面。

### 9.2 MIME 与缓存

| 路径 | Content-Type | Cache-Control |
| --- | --- | --- |
| `/`、`/index.html` | `text/html; charset=UTF-8` 或等价标准 charset 形式 | `no-store` |
| `/host-manifest.json` | `application/json`，允许标准 charset 参数 | `no-store` |
| `*.wasm` | `application/wasm` | `public, max-age=31536000, immutable` |
| content-hashed JS/CSS/MJS | 对应标准 MIME | `public, max-age=31536000, immutable` |

未知路径、source map、fixture、开发依赖和目录 listing 不得公开。Netlify SPA fallback
不得把未知资产错误地改写到 `index.html`。

### 9.3 搜索引擎边界

Production deploy 默认是公开 URL，所以不能依赖 Netlify 对 Deploy Preview 的自动
`noindex` 行为。`X-Robots-Tag` 是强制响应合同。`robots.txt` 可以作为未来的附加提示，
但本 Task 不为了它修改 exact Host distribution；缺少 `robots.txt` 不得删除 header
门禁。

## 10. Deployment Gate 与 Smoke

### 10.1 部署前

部署前必须通过：

- Release/tag/provenance gate；
- Host distribution verifier；
- Netlify 配置结构测试；
- 预期 header、MIME、cache 和 unknown-path 测试；
- `scripts/web-runtime-host.sh proof` 对相同 Release candidate 已有成功证据。

部署工作流不重复全部 Core CI，也不把新的 rebuild 冒充 Release 资产验证。

### 10.2 部署后 HTTP smoke

发布严格分两阶段执行：

1. Netlify REST digest API 创建 `draft: true` 的 atomic Deploy，并上传 required files；
2. 等待 Deploy state `ready`，取得 Deploy ID 与 immutable Deploy URL；
3. 对 immutable URL 执行以下 HTTP 与 browser smoke；
4. smoke 全部通过后，调用
   `POST /api/v1/sites/{site_id}/deploys/{deploy_id}/restore`，把同一 Deploy ID 发布为
   production；
5. 对 production alias 重跑身份与 HTTP/browser smoke。

HTTP smoke 覆盖：

1. 从 `/` 开始，HTTPS 下只接受直接 HTTP 200，或一次严格同源、无 query/fragment 且最终
   仅到 `/index.html` 的 redirect；
2. `index.html`、manifest 和一个 hashed JS/MJS/CSS/WASM 资产；
3. 精确安全 header、`X-Robots-Tag`、MIME 和 cache policy；
4. manifest Product Build、Host version 与 Release identity；
5. index 中 manifest digest 与所有内容哈希资产；
6. unknown path、source map 和 traversal 请求不返回产品页面或敏感文件。

只有 immutable URL 通过后才允许切换 mutable production alias。两者必须指向同一
Deploy ID 和相同 manifest identity。禁止在 smoke 后重新上传或生成第二个 Deploy。

### 10.3 浏览器 smoke

Chromium 对 immutable Deploy URL 执行一个有界远程 smoke：

- `window.isSecureContext === true`；
- `window.crossOriginIsolated === true`；
- `SharedArrayBuffer`、WebAssembly、AudioWorklet 与 OPFS mandatory capability 可见；
- manifest gate 成功；
- `Load diagnostic project -> ready -> Activate audio -> running`；
- 一个 Pointer/Keyboard synthetic trigger 使 admitted 与 outcome 各精确 `+1`，rejected
  不变；
- controller close 后上述三项计数保持，并证明 Worker、MIDI listener、BroadcastChannel
  与 AudioContext 完成清理。

远程 smoke 只证明发布配置与自动化旅程，不升级任何实体设备、声学延迟、Safari、
iPad Touch 或 Physical MIDI 验收状态。

## 11. 发布状态与证据记录

成功 evidence exact contract 是 `lmdj.web-runtime-host.deployment-evidence.v2`；失败恢复
exact contract 是 `lmdj.web-runtime-host.deployment-recovery-evidence.v1`。每次成功部署记录：

- Product Build；
- Web Runtime Host SemVer；
- Channel；
- signed tag 与 tag target Git SHA；
- GitHub Release URL；
- Host ZIP 名称与 SHA-256；
- GitHub Actions canonical run URL 与 run ID、执行 start/end；
- Netlify site ID；
- Netlify Deploy ID；
- immutable Deploy URL；
- production URL；
- prior-good 身份与 immutable/production HTTP/browser、immutable 本次 HTTP/browser、
  same-ID publish response、production HTTP/browser 的结构化结果及时间。

失败恢复证据必须原子写入并保留 reconcile site JSON、exact restore/disable response、原始
exit status、attempted/prior Deploy、恢复后 immutable/production HTTP/browser 与时间；不得
丢弃完整 HTTP JSON 或 restore response。workflow 以 `always()` 上传成功/恢复证据与日志。

`lmdj-runtime.netlify.app` 是可移动的 latest approved diagnostic pointer。只有 Deploy ID
URL、Release asset、tag 和 Git SHA 的组合可以作为某个具体版本的不可变发布证据。

## 12. Failure 与 Rollback

| 失败 | 行为 |
| --- | --- |
| tag、Release 或 asset identity 不一致 | 部署前失败；不调用 Netlify |
| checksum、解压或 manifest 验证失败 | 部署前失败；保留证据，不发布 |
| Netlify draft 上传失败 | 当前 published deploy 不变 |
| immutable URL smoke 失败 | 不发布该 Deploy；保留失败 Deploy 和日志 |
| publish API error、production smoke 失败、ERR、INT/TERM 或受控 timeout | 重新 GET site reconcile；只有 alias 指向新 Deploy 才恢复 |
| alias 指向新 Deploy且本次已建立 prior-good | restore exact prior，复验 prior immutable/production 并原子写 recovery evidence |
| alias 指向新 Deploy且首次无 prior | 使用官方 reversible site disable，不能伪造 rollback |
| 新版本 Runtime regression | 恢复先前 Deploy，不删除失败 Release、tag 或 Deploy |
| Netlify outage | 保持 GitHub Release 可下载；不得转为未经设计的临时生产服务器 |

部署前必须从官方 site response 发现 current published deploy（若有），从其 immutable
manifest 发现实际 Product/Host identity，并先对 prior immutable 与 production 跑完整
HTTP/browser，建立本次 prior-good。preflight 若发现 site 已 disabled，拒绝自动 enable 或
publication。恢复后重跑 prior immutable 与 production；workflow 内部 timeout 必须早于 job
timeout，给 reconcile、restore/disable、复验和证据上传留出预算。

## 13. Secrets 与最小权限

工作流只使用专用 secrets：

- `NETLIFY_RUNTIME_SITE_ID`；
- `NETLIFY_AUTH_TOKEN`，或 Netlify 支持的权限更小的等价部署凭据。

Netlify child 必须删除 `GITHUB_TOKEN` 与全部 `GH*`；GitHub child 删除全部 Netlify
credential 并只继承受控 GitHub authority；metadata、stage、evidence、HTTP/Chromium
helper 不继承任何部署 credential。私钥、token、secret response 均不得进入 argv、日志或
evidence。

凭据不得写入仓库、Release asset、Netlify deploy 文件或日志。工作流 permissions 默认
`contents: read`；只在记录 GitHub deployment 状态确有需要时增加最小
`deployments: write`。不授予 PR、issue、package 或仓库写权限。

Fork Pull Request、普通 branch push 和 Deploy Preview 不得取得 production deploy
secret。第三方代码不得在持有部署凭据的 job 中执行。

## 14. Version Management

本设计文档本身：

```text
Version impact: none
```

原因：文档不修改 Product、Module、Host、Provider、Contract、Assembly 或分发字节。

首次部署发布已经存在的 Product Build `1.0.15.2 · canary` 与 Web Runtime Host
`1.1.2` 原始资产，不创建新 Build、不修改 Host SemVer、不移动 tag，也不构成 Channel
promotion。

后续如果实现需要修改 Host UI、manifest、资产 inventory、Runtime 行为或公开 Contract，
必须在独立 Product Build 中按 canonical version policy 分配对应版本；不得把修改后的
内容继续称为 `1.0.15.2` 或覆盖既有 Release。

## 15. Documentation Impact

```text
Documentation impact: required
Affected portal routes:
- /operations/version-and-release/
- /hosts/web-runtime/
- /platform/web-runtime/
```

原因：新增公开 Runtime 诊断部署面、发布 provenance、失败保持与回滚流程。实现 Task
必须同步 current Portal 页面和 source facts；首次部署成功后补充 Deploy ID、immutable
URL、production URL 与 smoke 证据。仅有本地配置、PR Preview 或 Netlify `ready` 状态
不得写成 production deployed。

此次设计不分配新 Product Build，因此不为部署设计本身冻结一个新的 Product snapshot。
未来新 Build 的 snapshot 仍按 Architecture Portal policy 独立生成。

## 16. Rejected Directions

### 16.1 使用 `lmdj-demo.netlify.app`

拒绝。`demo` 会把诊断 Host 混同为完整 Creator 产品演示，并在 Creator 上线后形成
不清楚的所有权和迁移问题。

### 16.2 使用 `lmdj-web-host-canary.netlify.app`

拒绝作为长期主 URL。名称过长，并把可变 Channel 写入一个长期 diagnostic 工具域名。
Channel 由发布证据和页面身份表达，具体版本由 immutable Deploy URL 表达。

### 16.3 让 Creator 接替 Runtime Host 域名

拒绝。两个 Host 角色不同且长期并存；接替会破坏已分享的诊断 URL，并让 Runtime
故障复现与 Creator 产品回归互相耦合。

### 16.4 把 Runtime Host 部署到 Architecture Portal 子路径

拒绝。Portal 与 Runtime 的构建工具链、安全 header、缓存、回滚和验收合同不同。
共享站点会把文档发布与 WASM/AudioWorklet 诊断发布绑定成一个失败域。

### 16.5 Netlify 从 `main` 重新编译 Host

拒绝。Netlify build 不能替代 pinned Emscripten clean-room Proof，也会生成一份与
GitHub Release asset provenance 不同的候选。

### 16.6 暴露 Python proof server

拒绝。现有 server 是 loopback-only 的本地 proof server，不是公网 daemon。Netlify
只托管其已验证静态 distribution，并复现响应合同。

## 17. Acceptance

设计实现只有在以下事实分别成立时才完成：

- deployment config、workflow、tests 和 Portal current docs 经 PR review 合入 `main`；
- Netlify project `lmdj-runtime` 在独立授权后创建；
- production secrets 以最小权限配置；
- `workflow_dispatch(lmdj-v1.0.15.2)` 下载并验证既有 Release 原始 Host 资产；
- immutable Deploy URL 的 HTTP 与 Chromium smoke 通过；
- `https://lmdj-runtime.netlify.app/` 指向同一 Deploy 并通过相同 smoke；
- 发布证据记录完整；
- Architecture Portal 反映真实 deployed 状态；
- `lmdj-canary`、Creator、PWA、物理设备 gates、`beta` 和 `stable` 未被误报为完成。

本地 commit、CI 绿色、Netlify project 存在、上传完成或 immutable URL 可访问都不能
单独升级为“Runtime public deployment complete”。

## 18. References

- [LMDJ Formal Web Runtime Host Design](2026-08-03-lmdj-formal-web-runtime-host-design.md)
- [LMDJ Version Management](../governance/version-management.md)
- [LMDJ Architecture Portal Governance](../governance/architecture-portal.md)
- [Netlify Deploy Overview](https://docs.netlify.com/deploy/deploy-overview/)
- [Netlify API Deploy and Restore](https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/)
- [Netlify OpenAPI `restoreSiteDeploy`](https://open-api.netlify.com/)

## 19. Spec Self-review Checklist

- [x] 固定域名、渠道域名与 immutable Deploy URL 职责唯一；
- [x] Creator 与 diagnostic Host 的共存和网络独立性明确；
- [x] 首次部署与后续自动触发均有精确来源；
- [x] Release asset 不被重建或静默修改；
- [x] COOP/COEP/CORP/CSP、MIME、cache 与 noindex 均为可测试合同；
- [x] 部署失败、smoke 失败、回滚和 Netlify outage 有 fail-closed 行为；
- [x] 自动化与实体设备验收边界明确；
- [x] 版本、文档、权限与外部状态授权边界明确；
- [x] 文档无未决占位标记或模糊要求。
