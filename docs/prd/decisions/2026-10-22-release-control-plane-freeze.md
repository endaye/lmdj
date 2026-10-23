# 已确认：发版请求进行期间，CI 与发版工具控制面路径由工具冻结

- 日期：2026-10-22
- 关联：[#2422](https://github.com/endaye/lmdj/issues/2422) 第 10 项、
  [#2404](https://github.com/endaye/lmdj/issues/2404) 第 1 项。Owner 在三个方案
  （A 变量信号 + PR Contract 冻结检查 + skill 规则；B cut 窗口内由驱动器安装临时
  ruleset；C A 加 required status check）中选择 A。
- 结论：`scripts/release.sh run`/`resume` 在驱动前为所驱动的请求持有 repository
  variable `LMDJ_RELEASE_FREEZE`（值为 request id），请求 `final` 完成或被 `retire`
  时释放；同一仓库第二个发版请求在写 journal 之前被拒绝，不接管冻结。PR Contract
  新增 `Release freeze` 作业：变量存在且 PR 改动 `.github/workflows/`、
  `.github/actions/`、`scripts/ci/`、`scripts/release.sh`、`tools/release/` 时判红，
  变更文件取自冻结的 change-scope manifest；issue-done §5 要求 agent 合并前读该变量，
  冻结期间不合并这类 PR。`doctor` 报告持有者，只对已 retire/未知请求持有的陈旧冻结
  给出清除命令。普通产品与文档 PR 不冻结；git-workflow「cut 不冻结普通合并」保留。
- 原因：2.0.122.0 期间 #2365/#2371/#2375 在窗口中合并，其中 #2375 的主机准入脚本
  把 Web lane 改派到 WSL，候选 118 因此失效；冻结此前只靠人和 agent 的约定。仓库
  没有 ruleset，main 只有 conversation 保护；驱动器、agent 与 Owner 共用同一账号，
  ruleset 的 bypass 无法区分驱动器与 agent，驱动器合并自己的 cut/witness PR 还要
  反复开关，留下暴露窗口。变量信号加检查不改保护设置，不需要跨主机信号，驱动器
  自己的 PR 不触及冻结路径。
- 非目标：不改 branch protection、不加 required check（需要时作为单独的 Owner
  决定）；不冻结普通 PR；不自动清除陈旧冻结。
- 影响：`tools/release/release_freeze.py`、`github_api.py` 的 variables 方法、
  `cli.py`、`doctor.py`；`scripts/ci/release_freeze_check.py` 与
  `.github/workflows/pr-contract.yml`；issue-done 与 lmdj-release skill、
  `docs/governance/git-workflow.md`。
