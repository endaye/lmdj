# 已确认：focused 证据可以授权一次 squash 合并，队列验证改为按分类跑，但排在路由缺口关闭之后

- 日期：2026-08-29
- 结论：`focused` 分类结果可以构成合并证据。Integration Queue 验证的终点是
  与 Ready Pull Request 相同的分类，不再对每一次改动无条件升级 `full`；
  `merge:queue` 标签退回为纯授权信号，不再兼任范围信号。落地分两步且顺序
  不可颠倒：先关闭文档到测试的路由缺口并加上防复发 gate，再解除队列的强制
  `full`。本文件解决 `questions/queue-docs-only-merge-evidence.md`（已删除）
  与 Issue #397。

  发布证据不在本次放宽范围内。`scripts/release.sh audit --remote` 与
  `prepare` 必须继续拒绝 `focused` 与 `requested` 证据，
  [`../../governance/git-workflow.md`](../../governance/git-workflow.md) 中
  `Focused main is a CI cost decision, never a release decision` 对发布路径
  继续成立，本决策只推翻它对合并路径的适用。

- 原因：仓库已经接受 `main` 在 focused 证据上前进——一次 docs-only 的
  `main` push 就是按 `before..after` 分类跑的。既有的不对称是队列在合并
  **前**要 `full`，而 `main` 自己在合并**后**只跑 focused：同一棵树，前面
  查得比后面严。最近 50 个已合并 PR 中有 16 个（32%）的 lane 集是
  `{docs_static, portal}` 的子集，PR #368 这个四文件 Markdown 改动的 PR 检查
  是 3.5 分钟、队列验证是 16.6 分钟。

  队列无条件 `full` 在今天确实还承担着兜底职责，而且这一点有实证而非推断：
  扫描全部测试对 `docs/**` 的真实读取点，有 3 个测试共 11 处读取的文档没有
  路由到该测试所在的 lane。例如
  `tests/build/web_runtime_public_deployment_docs_test.py` 逐条断言
  `docs/design/2026-08-08-web-runtime-public-deployment-design.md`
  的内容，而该文档只路由到 `docs_static`，改它不会触发 `deploy_contract`。
  目前唯一拦住这类漏测的就是队列那次 `full`。先解除强制会拆掉当前唯一的
  安全网，因此排序是本决策的一部分，不是实施细节。

- 影响：第一步补齐这 11 处路由，并加一条 gate——凡被测试以内容断言方式读取
  的路径，必须路由到该测试所在的 lane；判据从测试源码的真实读取点推导，与
  `tests/build/ci_change_scope_test.py` 已有的
  `test_every_tracked_top_level_is_admitted_by_the_policy` 同构。第二步修改
  `scripts/ci/change_scope.py` 的 `merge:queue` 升级与队列 manifest 必须为
  `full` 两处约束，并修订 `git-workflow.md` 的 §Serialized Integration Queue。
  两个 PR 都改控制面路径，因此都走 ordinary protected merge path，不能用队列
  合并自己。第二步落地后，纯文档 PR 的合并周期从约 17 分钟降到分钟级；碰到
  编译或部署 lane 的改动分类结果不变，仍跑对应的完整 lane。
