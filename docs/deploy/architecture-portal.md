# Architecture Portal 部署、验证与回滚

日期：2026-08-04

状态：已生效

生产站点：`https://lmdj.netlify.app/`

## 1. 状态必须分开报告

| 状态 | 证据 |
| --- | --- |
| Local check | `scripts/architecture-portal.sh check` 完整输出 |
| CI | Architecture Portal workflow 对目标 SHA 为绿色 |
| Deploy Preview | Netlify Preview URL、Deploy ID、目标 SHA 与 smoke |
| Production deploy | `lmdj.netlify.app` 当前 immutable Deploy ID 与目标 SHA |
| Test release verified | `canary`/`dev`/`beta` 构建证据、匹配 Product Build 快照与目标环境 smoke |
| Stable release verified | 生产 smoke、匹配 Product Build 快照、Release 证据和关键页面人工抽查 |

前一状态不自动证明后一状态。PR Preview 成功不等于 production；Netlify 显示 Published 不等于内容身份正确。

## 2. 正常构建与发布

仓库根 `netlify.toml` 是唯一生产构建配置。Netlify 从 Git checkout 执行：

```text
base: apps/architecture-portal
command: npm ci && npm run check
publish: build
Node: 22
```

Pull Request 使用 Deploy Preview；合入受保护 `main` 后由 Netlify Git integration 自动生产部署。正常流程禁止 Netlify API、CLI `deploy --prod`、ZIP、拖拽或单个 HTML 手工上传。临时诊断如确需手工 deploy，必须使用独立非生产站点并明确记录，不能覆盖 `lmdj.netlify.app`。

普通 Preview 不创建永久文档快照。Product Build 一旦分配并交付给测试者，必须先用
`scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL` 生成匹配快照，并通过
`scripts/architecture-portal.sh check`；`stable` 发布在此基础上追加 Release 与生产验证。

## 3. 部署后 smoke

GitHub `deployment_status=success` 且 URL host 为 `*.netlify.app` 时，工作流 checkout 部署 SHA 并执行：

```bash
scripts/architecture-portal.sh smoke "https://DEPLOYMENT.netlify.app"
```

Smoke 有界并发检查 HTTPS、2xx、HTML MIME、current Product Build/revision、`/versions/1.0.13.0/`、所有顶层区、七个 Module 以及页面引用的同源静态资产。它会捕获“HTML 被当作 `text/plain` 源码显示”的回归。

生产 release verification 还应人工打开首页、一个 Module、全产品图、版本下拉与正式快照，确认暗/亮主题和移动端可读性。

## 4. Deploy ID 与证据记录

在 Netlify Site → Deploys 中选择目标 deploy，记录 Deploy ID、immutable deploy URL、production alias、创建时间、Git SHA 与 build log URL。也可在已授权环境中用 Netlify CLI/API只读查询 deploy 列表；不得为了获取 ID 触发新 deploy。

一条完整记录至少包含：

```text
Git SHA:
Product Build:
Netlify Deploy ID:
Immutable Deploy URL:
Production URL:
HTTP status / Content-Type:
Smoke workflow run:
Formal snapshot route:
Verified at UTC:
Verifier:
```

## 5. 回滚

1. 确认最近一次通过 production smoke 的 immutable Deploy ID 和 Git SHA。
2. 在 Netlify 对该既有 deploy 执行 Publish deploy/restore，不重新打包本地目录。
3. 重新运行 production URL smoke，记录新的发布事件与恢复所用 Deploy ID。
4. 保留失败 deploy、build log 和事故记录；不要删除证据。
5. 另起修复 Task/PR 修复 `main`，使 Git Source of Truth 与生产重新收敛。

回滚只切换 Netlify production alias，不移动 Product tag、不改写正式文档快照、不伪造新的 Product Build，也不隐含 Channel promotion。
