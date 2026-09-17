# CI 调度器恢复（journal 搁浅与写入成本）：handoff

Living document。本文件记录 2026-09-16 至 2026-09-17 一次连续诊断与两次交付的实际
状态，供下一个接管者直接继续。日期为 Asia/Shanghai。动作前请对着 live GitHub 与本地
仓库复核本文的每个状态声明；本文只记录写入当时为真的事实。

## 接管概述

- 跟踪任务：[#1048 保证 main 批次持续执行时报告仍有进展](https://github.com/endaye/lmdj/issues/1048)
  （仍 OPEN）与 [#1486 一个进程内只验证一次 journal 历史](https://github.com/endaye/lmdj/issues/1486)
  （仍 OPEN，代码已合并）。
- 相关设计/计划（都**未**授权实现）：[`docs/design/2026-09-10-ci-journal-checkpoint.md`](../design/2026-09-10-ci-journal-checkpoint.md)
  （T7b 签名 checkpoint 提案，明确"本轮不实现、不迁移"，且后端选择与 key 生命周期仍待授权）、
  [`docs/plans/2026-09-10-lmdj-ci-reliability-and-cost.md`](../plans/2026-09-10-lmdj-ci-reliability-and-cost.md)。
- 本次范围：让停滞的**合并后增量调度器**重新 admit 批次。**未**触及 release/deploy/Channel/版本分配。
- **停止原因**：第三层阻断不可观测——诊断按设计不外泄原因、失败又不留 artifact，
  在无法确证的情况下停止猜测，转入 handoff。
- 一句话状态：journal 已健康、两层根因已修并合并；**仍无任何批次 admit**,main 的
  "合并后增量回归网"仍缺（PR 门禁本身一直在跑，缺的是合并后的 main 增量批）。

## 问题分层（这是本次最重要的结论）

调度器状态不是数据库，而是 **GitHub Issue #807 的正文（锚点 `{head, pending}`）加它的
评论链（事件）**：#807 每条评论是一个带 `previous`/`digest` 的哈希链事件，每次自动唤醒
（"tick" = `Self-test Report` workflow 的 `Incremental batch controller` job,调度 cron
`7,22,37,52`,报告 cron `9,24,39,54`,另有 push 与完成回调）都要读它、决策、写回。

| 层 | 故障 | 状态 |
| --- | --- | --- |
| 1 | journal 里一条**搁浅的 pending 意图**（09-11 配额打满时 POST 结局不明）→ 协议按设计永久 fail-closed；且被阻时每个 tick 仍全量重放烧 ~1,000 请求 | **已修并已在线执行 drain** |
| 2 | journal 健康时，**每次 append 都完整重放两遍认证历史**；一次 reconcile 最多 4 次 append | **已修（#1488）** |
| 3 | 修复后 tick 仍在 reconcile 处 `journal-blocked`,但**原因不可观测** | **未修：当前卡点** |

### 第 1 层（已闭环）

- 根因：运行 `34648632797`（09-11 21:35）在把 `advance`（request `batch:o1-incremental-20260908-issue807:276`）
  的意图写入锚点后吃 403（`remaining: 0`），POST 结局不明 → 之后每次 entry 都在
  "pending append is not yet visible or its outcome is uncertain" 处 fail-closed,
  且每次都仍先把 291 条评论全量重放一遍（~970 请求），继续烧配额。
- 只读审计（生产代码、零写入）：291 条评论、generation 0–290、链连续、锚点 head 与链头
  一致、pending digest `f95759f540117fe443a2378c66cfd956a0ea0a9f2f0526048915f668f9275ddf`
  在完整清单中**不存在** → 该 POST 确实从未持久化。
- 修复：PR [#1455](https://github.com/endaye/lmdj/pull/1455)（合并 `c78f385d`,01:12:29Z）
  新增封闭手动操作 `batch_operation=reconcile-pending` + `batch_request={"pending_digest":"<64-hex>"}`
  （digest 精确匹配 + 链后继 + 完整认证缺席证明才归位锚点，绝不重放 POST、绝不产生 execute），
  以及"被阻时先做尾部窥视"的 fail-fast（不再每次都全量重放）。
- 生产 drain：dispatch run `35169671238`（01:30–01:38Z,success）：`result.json` 为
  `{"action":"reconciled-pending","request":null,"state":null}`;锚点变为 `{head: 9e95195d…, pending: null}`,
  评论数不变（291）、链与 head 未变 → **零重复 POST、零伪造事件**。
- 证据写在 [#1048 评论 1](https://github.com/endaye/lmdj/issues/1048#issuecomment-5707436486);
  恢复后首个 tick 的**配额归因**写在 [评论 2](https://github.com/endaye/lmdj/issues/1048#issuecomment-5707932911)。

### 第 2 层（已闭环，含量化）

- 实测（只读，2026-09-17）：一遍完整认证重放 **479 请求**（293 条评论 / 103 controls /
  133 writers）;一次 `Journal.append` 做**两遍**（POST 前后各一次）→ **958**;一次 reconcile
  最多 4 次 append（`observe → advance → admit → claim`）→ **≈3,800**;再加 `advice()`
  与其它调用 → **单 tick ≈4,300–4,600 请求**，而 `GITHUB_TOKEN` 是**仓库级 5,000 请求/小时**
  且与评审管线、relay、discovery 共享。tick 因 403 或写途中传输错误死亡，唯一持续产物是零星
  `observe` 事件 → 数天无 admit。
- 修复：PR [#1488](https://github.com/endaye/lmdj/pull/1488)（合并 `ff4c1088`,08:19:55Z）
  —— `GitHubJournalTransport.page_after()`（按已认证 cursor 读增量，节点校验/来源认证/拒绝
  规则与 `page()` 相同）+ `Journal` 在**进程内**缓存已验证前缀（仅当锚点 head 与已验证 head
  严格相等才复用，服务端总数必须等于已认证数加增量，任何不符回退完整重放）+ `Runtime.journal()`
  记忆化。
- 闸门：`tests/build/ci_batch_runtime_test.py::test_append_sequence_authenticates_the_history_once`
  （四个 append 服务的评论行数上限 9；**关掉复用后实测 48 行**，即旧规则）；journal 层
  `test_in_process_appends_verify_the_history_once`（完整遍历 2 次 → 旧规则 8 次）、五类尾部
  伪造仍阻断、总量不符阻断、他处写入强制完整重放、复用与全新进程等价。
- 语义边界（**必须知道**）：进程内已认证前缀若被**带外编辑**（正文变了、digest 未变），
  会在**下一个进程**的完整重放中阻断，而不会在同一进程内被再次发现；这一点已写进
  `/operations/testing-and-proof`。
- 证据写在 [#1048 评论 3](https://github.com/endaye/lmdj/issues/1048#issuecomment-5710414485)。

### 第 3 层（未修：当前卡点）

- 现象（run `35212757259`,control `79590fbe`,11:16:27–11:32:07）：reconcile 步骤
  `journal-blocked`,请求计数 `{"artifact":220,"graphql":22,"rest":2042}`（合计 2,284）、
  **`4xx=0`、`transport_errors=0`、`unavailable=0`、配额充足（remaining core 3,644）**、
  诊断里**没有 `http` 字段** → 触发的是**本地 `require`**,不是配额/网络/GitHub 拒绝。
- 为什么不可观测：`scripts/ci/incremental_entry.py` 的诊断**有意**只输出 `error_kind`
  （注释明确"Never inspect exception text or dynamic names"）;control 失败时 `result.json`
  不生成，artifact 步骤"无文件可传" → CI 里拿不到 `why`。
- 已排除的假设：**main 分支内容损坏**。我用**同一套生产代码**（`_writer`/`_control`/`_metadata`
  全套 provenance 校验）在失败前后从本地把 #807 的 298 条评论完整只读重放：链连续、锚点一致、
  全部 writer 的"control 是当前 main 祖先"证明通过。main 被改写会让这条**持续**失败。
- 最强假设（**未确证**）：写入后的**读后写可见性延迟**——POST 评论后立刻用
  `comments(last:1)` 回读确认，若 GitHub 尚未暴露该评论，或正文 PATCH 的立即回读仍是旧值，
  代码按设计 fail-closed（"pending append is not yet visible…"），**下一个 tick 读到后自愈**。
  这与观察吻合：失败请求里没有 4xx（写其实成功）、事后 journal 完全健康、事件在 tick 之间
  一点点增加（每次由**别的 tick**替上一个收尾）。次要候选：校验刚启动的 writer run 时
  jobs 分页总数在两页之间变化（`jobs changed during pagination`）。
- 解开它的**前置**是让阻断可观测（见下）。

#### 2026-09-18 更新：第 3 层根因已定位并修复

- 根因**不是**读后写可见性，而是**记录体积**：下一批 auto 请求覆盖 `561a8ce8..main` 共 261 个
  first-parent commit，`interval_selection` 为每个变更路径生成一条 reason（`broad foundational or
  concurrency impact: <path>` 等），`selection.reasons` 共 **2,355 条**；`admit` 事件连同 pending
  checkpoint 序列化后 **260,100 字节**，超过 `batch_github_journal.LIMIT = 60,000`（该上限守住
  GitHub 评论 65,536 字符）。`_write` 在 PATCH 锚点**之前**的 `decode(body)` 本地 `require` 失败 →
  `JournalBlocked`、无 HTTP 状态、不留 pending、journal 保持健康——与第 3 层全部观测吻合
  （每 tick 先成功 append 一条小的 `observe`，跑完 `advice()` 后在 `admit` 处死亡）。
- 正反馈：被阻越久，区间越长，记录越大，永不自愈。09-10 的 gen 276 admit 只有 36 条 reason、3,767 字节。
- 复现（只读）：`git fetch origin main` 后用生产 `GitInputs.interval_selection(base=561a8ce8, target=origin/main)`
  构造 admit 信封并按 `_write` 同样方式序列化，直接量字节数。
- 修复（本次 PR）：`batch_controller.bounded_reasons` 以 **16,000 字节**预算截断 canonical 排序后的
  reasons，用一条带计数的 `why/remedy` 说明代替被省略部分，幂等（存储的 request 重建仍等于自身）；
  **suites 不变**，只缩解释不缩覆盖。同时新增闭合诊断种类 `journal-record-oversized`
  （`JournalRecordOversized(JournalBlocked)`），使此类本地拒绝在 CI 诊断里可见且不泄漏异常文本。
- 闸门：`tests/build/ci_batch_controller_test.py`（600 路径区间：选择保持 full、pending-admit
  checkpoint ≤ LIMIT）、`tests/build/ci_batch_github_journal_test.py`（超大记录在任何 PATCH/POST 前
  以闭合种类拒绝）、`tests/build/ci_incremental_entry_test.py`（诊断种类映射）。
- 坑位：`.agents/pitfalls/journal-record-grows-with-backlog.md`（absorbed）。
- 合入后需观察的远端腿：首个 tick 在 `admit → claim` 后返回 `execute` 并启动
  `Execute incremental batch`（16 套 full）；随后 outbox #817 出现交付。

## live 状态（写入时，2026-09-17 ~23:00 +08:00）

- **调度器 journal #807**：298 条评论（generation 297）;链完整、锚点 head
  `175a123ac84563075bfceb64d257e5fd40465c48c3b9b1806c2ccfe55613468b`、`pending=null`。
- **最后一次 `admit` = generation 276（09-10）**;`claim` 277、`result` 284 之后**唯一缺失的
  `advance`（request 276）已在 generation 294 被新代码补写**——这说明新代码已能走完
  `load → settle → append`,是第 2 层生效的直接证据。
- **报告 outbox #817**：668 条评论，**09-09 之后无新交付**（没有新批次 → 没有新失败可报，自洽）。
- main HEAD：`0fa186de`（写入时；合并 #1488 = `ff4c1088`）。
- 额度事实：`GITHUB_TOKEN` 仓库级 **5,000 请求/小时**,与评审、relay、discovery 共享；
  PR-Agent 的 **AI 花费预算**是另一回事，已由 [#1460](https://github.com/endaye/lmdj/pull/1460)
  从 $20 提到 $100。评审**发布**也曾因 `403 remaining=0` 失败（本任务 #1488 首跑即如此，
  按坑位 `rerun-failed-drops-review-artifact` 整跑重派后成功、`findings: []`）。

## 未完成（建议顺序与授权边界）

1. **让 reconcile 阻断可观测**（2026-09-18 部分完成：`journal-record-oversized` 闭合种类已加；其余 `require` 仍只显示 `journal-blocked`）：失败时输出**固定词表**的 reason，
   和/或**始终**上传 result artifact。这是解开第 3 层的前置。注意：现诊断"不外泄异常文本"
   是**有意**的安全设计，放宽属治理决定，必须显式授权，并保持不泄漏响应体/凭证。
2. **收敛 `advice()` 成本**（未立 Task）：实测 25-commit 区间一次 `advice()` =
   **159 请求**（其中 **73 页是恒定的全仓 artifact 清单**,7,156 个 artifact；每个匹配的
   `pr-review-merge-map-*` 约 4 请求）;6 天积压（197 commits / 220 次下载 / 175 个匹配）
   外推 **≈730+**。候选：(a) 改为按 `pr-review.yml` 的运行取 artifact（成本 ∝ 区间内 PR 数）;
   (b) 利用清单按 id 倒序做有序早退；(c) 按 commit 持久化不可变 advice 摘要。
   **语义前提**：advice **只能放宽、不能收紧**选区（缺失/不可信只会回退到 Git+policy 下限），
   因此这些优化不会缩减覆盖。
3. **重新归因第 2 层之后的剩余请求量**：11:16 那次 tick 仍 2,284 请求，journal 部分已确认
   ~500,其余（含 advice ~730）需要在可观测之后再算一次。
4. **#1048 验收剩余腿**：持续吞吐、积压排空、以及恢复后的**首条完整
   admit → Execute incremental batch → 报告交付**周期。
5. **#1486 远端腿**：一个 tick 跑到 `admit` 并启动 `Execute incremental batch`,随后出现
   outbox 交付；`#1486` 因此保持 OPEN。
6. 本线程**未**触及：release / deploy / Channel promotion / 版本分配 / Issue 自动修复。

## 复现方法（全部只读）

- scheduler 配置来源：`scripts/ci/incremental_storage.json`（issue `807`、`issue_node_id`
  `I_kwDOTK_1fs8AAAABQJKJ5w`、`bot_node_id` `MDM6Qm90NDE4OTgyODI=`、`workflow_id` `352307416`、
  epoch `o1-incremental-20260908-issue807`）。
- 完整重放计数：把 `batch_github_journal.GitHubJournalTransport` 包一层计数
  `UrllibGitHubApi._request`，然后遍历 `page(807, cursor)`;同一进程可继续用 `page_after`
  只读增量。注意这会是 **~500 请求**,不要在配额紧张时反复跑。
- 单点查询（1 请求）：GraphQL `issue(number:807){comments(last:N){totalCount nodes{body}}}`
  直接读最新事件的 `generation`/`type`/`data`。
- **建议**（未做）：把上述探针正式化为仓库内一个只读审计命令，而不是留在会话临时目录里。

## 本次新增/变更的知识留存

- `.agents/pitfalls/journal-pending-strand-blocks-without-drain.md`（新，absorbed,
  exit = `tests/build/ci_incremental_batch_journal_test.py`）。
- `.agents/pitfalls/journal-append-replays-full-history.md`（新，absorbed,
  exit = `tests/build/ci_batch_runtime_test.py`）。
- `apps/docs-site/docs/operations/testing-and-proof.mdx`：补写"进程内只验证一次"的规则、
  边界与请求数效果（Documentation impact: required → `/operations/testing-and-proof`）。
- 与本线程相邻、**非本线程**的既有条目：`report-progress-requires-independent-admission`
  （#1048 早期已 absorbed）、`rerun-failed-drops-review-artifact`（本次被真实命中并遵循）。

## 边界与授权

- 本次交付仅两次代码合并（#1455、#1488）与一次生产 journal drain；未分配版本、未发布、
  未部署、未晋升 Channel。
- worktree 与本地分支已清理（内容留存已核）；远端分支按规保留。
- 相关但**仍在他人/其他工作流**手上的条目：`#1048` 的吞吐与积压验收、`advice()` 成本、
  第 3 层可观测性、以及本线程之外的 `#1438`/`#1440`（等产品决策）与 PR-Agent 运维。
