# #1371 — generated-only PR 的确定性门禁评审证据路径

## 背景(已核实)

#1365 把工具生成物排除出评审输入后,**全部变更都是生成物的 PR 永远拿不到模型评审**:`scripts/ci/pr_agent_input.py:907-914` 在 `build_input` 拒绝("changed Git inventory contains only excluded generated artifacts"),`pr-review.yml` 的 deepseek/publish 步骤全部 `if: steps.input.outcome == 'success'` 被跳过,PR 上不留任何证据;`scripts/ci/review_wait.py` 只认两种证据(模型评审 v1/v2 marker、owner _attestation_),于是 #1368(Build 1.0.57.0 squash witness)只能靠 owner waiver 手工过桥。每个 Build 分配都有一个 witness PR,waiver 会常态化。

关键事实(探查已确认,file:line 基于 origin/main):

- 生成物分类:`pr_agent_input.py:66-82`(`GENERATED_DIRECTORY_PREFIXES` 含 `apps/architecture-portal/versioned_provenance/` 等;`GENERATED_FILES` 为三个渲染装配件)。
- 拒绝点:`build_input` 在 rename 边界检查之后、MAX_FILES 之前(`pr_agent_input.py:883-914`);排除结果已记录在 `document["excluded_generated"]`(996-1001)。
- collect-t2 成功时写 6 件 artifact(`COLLECTION_ARTIFACTS`),最后写 `collection-receipt.json` 作为成功标记;拒绝时写 `collection-failure.json` 栅栏(`pr_agent_input.py:1223-1266`)。`verify_publication` 拒绝任何含 failure 栅栏的目录(1077)。
- 评审 marker 不变量(新证据必须全部复刻,`review_wait.py`):恰好一个 marker(138)、repo/PR/head/run/attempt 绑定(146)、github-actions bot 数字 id + `commit_id == head` + COMMENTED(147-149)、artifact 名 `pr-review-result-{head}-{run}-{attempt}`(158-160)、`body_observation` 防编辑/重放(39-46)。
- 运行认证:`review_failure_report.collect` 要求 producer/publisher 作业按字面名("Review fallback"/"Publish review and scope")成功、control_sha ∈ main 祖先、workflow 源字节一致;其封闭 schema 检查会拒绝 receipt-only 归档,需显式扩展。
- 确定性门禁:门户 lane(`architecture-portal.yml`,`workflow_call`,仅被 main 自测批次调用)跑 `scripts/docs-site.sh check`,其中 `check:release-docs` → `verifySnapshotProvenance` 会**消费 PR 上新提交的 witness** 重建认证源提交。**但该 lane 并不在 PR head 上运行**(已核实:当前 main 上仅 pr-contract.yml、pr-review.yml、cloudflare-preview-build.yml 触发 pull_request;#1368/#1373 的 head check-runs 中没有门户检查)。本任务因此在 `pr-contract.yml` 新增 `portal-provenance` 作业(check-run 名 `Architecture Portal provenance`),在 PR head 上跑与 `scripts/ci/local_lanes.json` 门户 lane 完全相同的命令,供评审资格绑定。
- fork PR 根本到不了这里(`pr_review_target.py:207-208`),秘密边界不变;只有 `publish` 作业有 `pull-requests: write`。

## 设计(推荐方案)

**一句话:generated-only 不再是拒绝,而是一张由可信控制面签发、由既有门户 lane 背书的 receipt;`review_wait` 新增第三类证据,同时认证 receipt 与 head 上的门户 lane 绿灯。**

窄范围:**仅当全部被排除路径都属于门户快照/provenance 类**(`apps/architecture-portal/versioned_provenance/`、`apps/architecture-portal/versioned_snapshots/` 等,以 `GENERATED_DIRECTORY_PREFIXES` 中门户类前缀的现存集合为准)才发 receipt;其他 generated-only 组合(如纯渲染装配件)**保持现有拒绝不变**。fail-closed:门户 lane 没跑/没绿/对不上 head,资格保持 pending,owner waiver 退路不动。

信任链:

1. `build_input` 检测到「全部被排除 ∧ 全部门户类」→ 抛新的 `GeneratedOnlyInput`(携带 receipt 文档),不再是 `InputCollectionError`。
2. `collect-t2` 捕获后把 receipt 写入 REVIEW_DIR 为 `generated-only-receipt.json`(新 schema `lmdj.pr-agent-input-generated-only.v1`:identity 七字段、excluded paths 及其 digest、head_sha、receipt 自描述 sha256),退出码 0,输出 `generated_only=true` 与 receipt digest。不写 `collection-receipt.json`(避免被当成完整输入),不写 `collection-failure.json`(避免栅栏语义)。
3. workflow:`publish` 作业条件扩到 `generated_only == 'true'`;此时跳过模型产物校验,改用写权限发一条 COMMENT 评审,body 以新 marker 开头:
   `<!-- lmdj-review-generated-v1 {repo} {pr} {head40} {run} {attempt} sha256={receipt_sha256} -->`
   复用 `publish()` 的 duplicate 检查(concurrency cancel-in-progress 会重跑同 head)。
4. `review_wait.py`:新 marker 正则 + `generated()` 准入函数,复刻全部五类不变量,另加两条:
   - 重新从 artifact 归档取出 `generated-only-receipt.json` 重算 digest 与 marker 比对;
   - 通过 check-runs API 要求**同一 head** 上 PR 门禁的门户 provenance 作业(`portal-provenance`,check-run 名 `Architecture Portal provenance`,含 release-docs provenance 验证)conclusion=success。
5. `review_failure_report.collect` / 归档封闭 schema:为 generated-only 归档形状加第三个桶(显式枚举新文件名,拒绝其他偏差)。

被否方案:在 pr-review producer 作业里直接对 PR-head git 对象跑 `verify-witness`。自包含更强,但要改 `verify-squash-witness.mjs` 支持无 checkout 读 blob、在可信 workflow 里新增执行面;改在 pr-contract.yml 增加 `portal-provenance` 作业运行与本地 lane 完全相同的 `scripts/docs-site.sh check` 命令,checker 执行面零新增(只新增一个调用既有命令的 PR 作业)。若未来出现门户类之外的 generated-only 常态 PR,再按同一模式扩 gate 映射。

## 变更文件(一个 Task 一个 commit)

- `scripts/ci/pr_agent_input.py` — 新 schema、`GeneratedOnlyInput`、门户类前缀判定、receipt 构造与发布(复用 `_canonical`/`_sha256`/`publish_*` 机制)。
- `scripts/ci/review_pipeline.py` — `collect_t2` 处理 generated-only;`publish` 或新增 `publish-generated` 模式发 marker 评审。
- `.github/scripts/pr_review_target.py` — `generated_identity`/`generated_body`/`publish_generated`,镜像 `publish_review` 的 resolve/stale/write 姿态(marker 无 backend 字段,既有 `review_identity` 无法承载)。
- `.github/workflows/pr-review.yml` — publish 作业条件与步骤 gating;上传 artifact 清单加 `generated-only-receipt.json`。
- `.github/workflows/pr-contract.yml` — 新增 `portal-provenance` 作业:PR head 上运行门户 lane 命令(`scripts/docs-site.sh install` + `check`),作为 generated-only 证据绑定的同 head 确定性门禁。
- `tools/release/review_inventory.py` — `bind_eligibility` 接受 `generated` 证据类(映射 reviews/review_id,与 automated 同形,含 bot login 后缀投影)。
- `scripts/ci/review_wait.py` — `MARKER_GENERATED` 正则、`generated()` 准入、路由(245-257 旁)、`runs` 清单保持。
- `scripts/ci/review_failure_report.py` — generated-only 归档桶。
- `.agents/skills/issue-done/SKILL.md` — waiver 段落补一句:generated-only 证据存在时优先于 waiver。
- `.agents/pitfalls/review-input-generated-bytes-exhaust-limit.md` — How to apply 指向新机制。

## 测试(随代码同 commit)

- `tests/build/ci_pr_agent_input_test.py`:
  - 更新 `test_all_generated_inventory_is_refused_with_explicit_reason`(门户类全排除不再拒绝,改断 receipt 内容);
  - 新增:非门户类 generated-only 仍拒绝;混合(门户类+其他生成物)仍拒绝;rename 边界检查先于 receipt。
- `tests/build/ci_review_pipeline_test.py`:collect-t2 generated-only 生命周期(写 receipt、退出 0、输出字段)、不写两个旧 marker 文件。
- `tests/build/ci_review_wait_test.py`(镜像现有 v2/owner 测试矩阵):
  - 真实 receipt + 门户 lane 绿 → eligible;
  - wrong head / duplicate marker / edited body / 非 bot 作者 → invalid;
  - 门户 lane 缺失或失败 → 保持 pending(not eligible);
  - receipt digest 不符 → invalid。
- `tests/build/ci_pr_review_workflow_test.py`:作业结构 pin 更新(新增 marker 发布步骤、artifact 清单)。
- `tests/build/ci_review_failure_report_test.py`:generated-only 归档桶认证。
- `tests/build/ci_workflow_topology_test.py` / `tests/build/ci_hosted_runner_policy_test.py`:`portal-provenance` 作业 pin(字面名、lane 选择、exact-head 检出、与 `local_lanes.json` 门户 lane 相同的命令序列)。
- `tests/build/ci_review_wait_test.py`:`generated` 证据经 `bind_eligibility` 绑定(含 bot login 后缀投影)。

## 验证命令

```bash
python3 tests/build/ci_pr_agent_input_test.py
python3 tests/build/ci_review_pipeline_test.py
python3 tests/build/ci_review_wait_test.py
python3 tests/build/ci_pr_review_workflow_test.py
python3 tests/build/ci_review_failure_report_test.py
python3 tests/build/ci_pitfall_ledger_test.py
python3 tests/build/ci_workflow_topology_test.py
python3 tests/build/ci_hosted_runner_policy_test.py
python3 tests/build/release_review_inventory_test.py
scripts/local-ci.sh --declaration-only --pr-body <body>
```

合并后轮证:用下一个真实的 squash-witness PR(下个 Build 分配时)验证「无 waiver 直接 eligible」;若长期没有自然样本,可用 `gh workflow run pr-review.yml -f pr_number` 对一个历史 witness 形状 PR 做干跑确认(不合并)。

## Version Management

Version impact: none — 只改 CI 评审控制面脚本与 workflow,不动 Product Build、Module SemVer、Contract;无版本身份变化。

## Documentation Impact

Documentation impact: none
Reason: 评审证据模型不在任何当前门户页面记载(已 grep `lmdj-review-v2`/`owner-review-attestation`/`waiver`/`squash witness` 于门户 src,无命中);变更是 CI 控制面行为,门户路由、图表、投影身份均不变。

## Pitfall Impact

更新既有 `review-input-generated-bytes-exhaust-limit`(How to apply 指向新证据路径);不新增条目——`review-invalid-output-is-model-flake` 与本任务正交,保持 open。

## 风险与 fail-closed 备注

- 新 marker 的五类不变量全部复刻现有实现;任何认证缺口一律落入 diagnostics → invalid,不会静默缺席(与 250 行预过滤语义一致)。
- 门户 lane 失败/缺失时资格停 pending,不授予合并;owner waiver 机制原样保留。
- 封闭 schema 消费者(review_failure_report、归档读者)显式扩展而非放宽,任何未登记偏差仍是拒绝。
