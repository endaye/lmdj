# Host 部署切换到 Cloudflare：workflow 驱动与证据契约

日期：2026-09-17

状态：待实现。本计划只声明范围与验证，不改动产品代码。

跟踪缺陷：[#1467](https://github.com/endaye/lmdj/issues/1467)。
相关：[#925](https://github.com/endaye/lmdj/issues/925)、
[#926](https://github.com/endaye/lmdj/issues/926)、
[#927](https://github.com/endaye/lmdj/issues/927)、
[#1301](https://github.com/endaye/lmdj/issues/1301)。

## 已核实的前置事实（2026-09-17）

- 两个 Host 部署 workflow 在 GitHub 上都是 `active`：
  `deploy-web-runtime-host.yml`（330384060）、`deploy-creator-web.yml`（348168397）。
- 它们的 `deploy` job 执行 `scripts/<host>-deploy.sh deploy`，该路径的 `production_url`
  硬编码为 `https://lmdj-runtime.netlify.app` / `https://lmdj-creator.netlify.app`
  （`scripts/web-runtime-deploy.sh:9`、`scripts/creator-web-deploy.sh:9`），并对
  `NETLIFY_*_SITE_ID` 调用 Netlify API。
- 这两个 Netlify 站点已于 2026-09-08 经 owner 授权删除。独立 HTTP 复核：两者 **404**，
  而 `creator.lmdj.workers.dev` / `lab.lmdj.workers.dev` **200**。
- `tools/release/entry_composition.py` 的 `runtime` / `creator` 两步 dispatch 的正是这两个
  workflow，并按 `tools/release/deployment_evidence.py` 校验 run artifact 中的 `evidence.json`。
  因此 #1301 的部署那一半当前不可能成功。
- 共享受管 Cloudflare adapter 已存在并已验收（#924）：`scripts/cloudflare-host.sh` →
  `apps/web-runtime-host/tools/cloudflare_host.py`，verbs
  `candidate / verify / promote / recover / inspect / reconcile`，targets 含
  `creator-web` / `web-runtime-host` 及各自 recovery / initialization 变体。它复用两个 deploy
  脚本的 `stage` verb 取已验证签名输入（`docs/plans/2026-09-08-cloudflare-host-release-stage.md`）。
- **缺的不是 adapter，是证据契约与 workflow 接线。** `cloudflare_host.py` 是操作者 CLI 形态：
  receipt 与 diagnostic 写在 `--state-root` 下，不产出 driver 消费的 `evidence.json`。
- `deployment_evidence._evidence_problem` 要求的闭合形状：`contract`（前缀
  `lmdj.web-runtime-host.deployment-evidence.` / `lmdj.creator-web.deployment-evidence.`，
  见 `tools/release/policy.json:50,55`）、`tag`、`git_revision`、`product_build`、
  `github_actions.run_id`，以及 `immutable` 与 `production` 两节各自的 `http` 与 `browser`
  且都必须 `passed`。**契约本身不变**，因此本计划无 Contract 版本影响。
- 凭据落差：`CLOUDFLARE_API_TOKEN` 存在于 `portal-cloudflare` 与 `portal-cloudflare-preview`
  两个 Environment，**不在** `runtime-canary` / `creator-canary`；后两者当前只有 Netlify secret
  且 `protection_rules = 0`。

## 范围

按依赖分组，每组一个可独立审查、可回滚的 Task：

1. **T1 — Cloudflare 部署证据写入器**（无 workflow 改动）。新增生产模块：对一个已提升的
   Cloudflare 版本，运行 immutable（版本 URL）与 production（固定 URL）两侧的 HTTP 与 browser
   检查，并写出满足 `deployment_evidence` 闭合形状的 `evidence.json`。复用既有
   `cloudflare_smoke.py` 与既有 Host 浏览器冒烟，不新写冒烟逻辑。
2. **T2 — Runtime workflow 切换**：`deploy-web-runtime-host.yml` 的 `deploy` job 改为
   `stage` → `cloudflare-host.sh candidate` → `verify` → `promote` → T1 写证据；artifact 名称与
   路径保持 driver 现有期望不变；移除 `NETLIFY_*` env。
3. **T3 — Creator workflow 切换**：`deploy-creator-web.yml` 同构改造。
4. **T4 — 退役生产路径上的 Netlify**：两个脚本保留 `stage` / `verify`，移除或隔离 `deploy`
   的 Netlify 生产路径；同 Task 纠正 #927 中「两个 legacy workflow 已 `disabled_manually`、
   Netlify 无当前生产消费者」这条与现状不符的记录。
5. **T5 — Environment（owner 拥有）**：向 `runtime-canary` / `creator-canary` 配置
   `CLOUDFLARE_API_TOKEN`，并决定这两个 Environment 的保护规则。**这是凭据与保护操作，
   需要用户执行或明确授权，不在编码 Task 内。T2/T3 的实跑验收依赖它。**

不做的：不改 driver 语义、journal 格式、orchestration policy、`lmdj.release-plan.v1`、
部署证据契约前缀；不动 custom DNS、计费、分支保护；不新增 required gate；不删除
Netlify 历史工具源码（按 #927 的处置保留为历史工具，仅停止其生产消费者身份）。

## 最低层验证与完成标准

每条只钉一个事实：

- **T1**：写出的文档通过 `deployment_evidence._evidence_problem`（正例）；`contract`、`tag`、
  `git_revision`、`product_build`、`github_actions.run_id` 各自被改坏时分别被拒（每字段一个负例）；
  `immutable` / `production` 的 `http` / `browser` 任一未 `passed` 时被拒。冒烟失败时不写出
  `passed`，也不写出半份文档。
- **T2 / T3**：workflow contract 测试证明 `deploy` job 不再引用 `NETLIFY_*`、不再出现
  `*.netlify.app`；artifact 名称与 `evidence.json` 路径与 driver 期望一致；candidate 失败时不
  promote，promote 失败时不写证据。复用既有
  `tests/build/{creator_web,web_runtime}_deploy_workflow_test.py`。
- **T4**：生产路径全仓无 `*.netlify.app` 与 Netlify API 调用的 grep 断言；`stage` / `verify`
  行为不变（既有脚本测试全绿）。
- **实跑验收（依赖 T5）**：一次真实 dispatch 部署到 `lab.lmdj.workers.dev` /
  `creator.lmdj.workers.dev`，产出的 `evidence.json` 经 `verify_deployment_run` 验证通过。
  在 T5 完成前，本计划只交付到「源码与 workflow 就绪且本地契约测试全绿」，**不宣称部署已验收**。

## Version Management

Version impact: none

Reason: CI workflow、部署工具与测试；不改 Product、Assembly、Module、Host、Provider 或
Contract 身份，不分配版本或快照，不改部署证据契约前缀。

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release

实现 Task 落地时同步更新该页描述的当前部署事实，以及
`docs/deploy/creator-web.md`、`docs/deploy/web-runtime-host.md` 两份运维手册。
