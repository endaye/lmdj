# 已确认：`native-test-host` 是产品面组件，改名 `native-host`，并以书面准则约束分发包内容

- 日期：2026-08-24
- 结论：接受它为正式产品面组件。Module id `native-test-host`（止于
  `1.0.14`，永不再用）改名为 `native-host`，新 id 从 `1.0.0` 起独立演进；
  二进制名 `lmdj-native-host`、协议与测试面不变。Assembly 成员身份变化按
  版本策略分配 Product Build `1.0.31.0`。分发包内容准则写入
  [`../../governance/distribution-contents.md`](../../governance/distribution-contents.md)，
  `scripts/package-core.py` 是其唯一机械清单。本文件解决
  `questions/native-test-host-classification.md`（已删除）与 Issue #210
  （机器任务 A2）。
- 原因：2026-08-02 Formal Native Realtime Host 设计已把它建成"首个正式、
  版本化、Assembly-listed Headless Native Host"；`package-core.py` 有意
  分发 `bin/lmdj-native-host`，`tests/distribution/package_acceptance_test.py`
  断言它在每个分发包中存在且可运行。移除会删掉一个已测试、已交付的产品
  能力；保留旧名则让 Assembly 身份与 `CLAUDE.md` 的 `apps/` 定义互相
  矛盾。改名是唯一与既有设计、打包和测试一致的方向。
- 影响：`apps/native-test-host/` → `apps/native-host/`；Assembly、lock、
  编译装配、门户 current 页面与架构图源同步更新；历史快照、发布证据与
  历史构建记录中的旧名保持不变。退役 id 不得复用；未来任何组件要进入
  分发包，必须先满足分发包内容准则。
