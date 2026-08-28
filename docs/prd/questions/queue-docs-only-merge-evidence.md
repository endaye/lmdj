# 队列验证是否应该对纯文档改动保留分类结果，而不是无条件升级全量 CI？

- 范围：新内核（Playable Beat Instrument）
- GitHub Issue: #397
- 来源：2026-08-28 修复 `known_top_levels` 漏配（PR #381 / `37ac837a`）时暴露
- 为什么重要：`change_scope.py:516` 把带 `merge:queue` 的 PR 无条件升级为
  `full`，`change_scope.py:606` 与 `queue_validation_document` 又各自要求队列
  manifest 必须是 `full`。纯文档 PR 因此先按 focused 付一次成本，进队列再付
  一次全量。用线上策略与分类器对最近 50 个已合并 PR 实测，16 个（32%）的
  lane 集是 `{docs_static, portal}` 的子集；PR #368 这个四文件 Markdown 改动
  的 PR 检查是 3.5 分钟，队列验证是 16.6 分钟。按这个占比，每 50 个 PR 约
  4.5 小时以自建节点为主的机时花在风险最低的那一类改动上，同时拉长它们的
  合并周期。

  这不是调参，而是治理裁决：`docs/governance/git-workflow.md` 的
  §Serialized Integration Queue 写明 `Focused main is a CI cost decision,
  never a release decision`，并把队列验证定义为 `Queue validation proves the
  tree that will land`，两处都需要修订，所以不能在实现 Task 内顺手改掉。

  队列无条件全量真正在防的，是 `scope_policy.json` 可能存在的路由不足——今天
  就有一例：`packages/foundation/` 只路由到四条 `core_*` lane，而 Foundation
  被编译进 `packages/web-runtime-platform`，Foundation 改动弄坏 Web 构建时
  PR 的 focused 与队列的 focused 都抓不到。这是既有路由缺口而非队列特有问题，
  但它是保留全量兜底的最强论据。该论据对纯文档不成立：只路由到
  `docs_static` 与 `portal` 的改动没有任何编译或部署产物路径可被漏路由，而
  `portal` 确实依赖 `main` 的 manifest，focused 队列跑仍会校验真正可能坏掉的
  那部分交互。判据必须落在分类后的 lane 集而非目录前缀上——`docs/` 并不统一
  是软路径，`docs/release-evidence/release-intents.json` 路由到
  `deploy_contract` 与 `ci_contract`。
- 处理时点：先裁决"focused 证据能否授权 squash 合并"这一条，写入
  `docs/prd/decision-log.md`；采纳窄白名单方案后再定软 lane 集、判据表达与
  `git-workflow.md` 上述两句的修订，并在
  `tests/build/ci_change_scope_test.py` 与 `tests/build/ci_merge_queue_test.py`
  补齐准入集合、前缀判据的否决用例，以及必须保持全量的
  `docs/release-evidence/release-intents.json` 用例。放宽范围仅限合并证据；
  `scripts/release.sh audit --remote` 与 `prepare` 必须继续拒绝 focused 与
  `requested` 证据。实现 PR 同时改 `change_scope.py` 与 `scope_policy.json`，
  两者都是 `merge_queue.py:38` 的控制面路径，因此它自己不能走队列合并。
