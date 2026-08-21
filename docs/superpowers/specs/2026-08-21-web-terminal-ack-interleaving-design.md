# Web Terminal ACK Interleaving Design

日期：2026-08-21

状态：规格已批准；本文只授权记录设计，不授权 implementation、push、Pull Request、merge 或远端 mutation

关联任务：[Issue #166](https://github.com/endaye/lmdj/issues/166)

## 1. 结论

Issue #166 是一个真实、仍然存在的 packaged Chromium 测试缺陷，但现有证据不支持修改
Web Runtime Host 生产并发语义。`rejectedConsumes == 1` 是合法调度：第一个伪造 ACK
可以在 native terminal completion 前被拒绝，Control completion 随后发生，第二个伪造 ACK
再成功消费该 completion 并触发同步 cleanup。这个顺序仍满足“一次 native completion
最多成功消费一次”的产品契约。

未来 implementation 应删除 responsive cancellation case 对自动 ACK rejection 次数的
cardinality 断言，不把它从 `[0, 2]` 扩成另一个枚举集合。测试继续保留并加强真正的安全
不变量：唯一一次成功 consume、显式 replay 必须返回 `-1`、真实 Worker ACK 可见、terminal
owner 已释放、late messages 不发布、Project Truth 与 OPFS inventory 不变，并且 reopen 后仍能
得到相同权威状态。

未来 implementation 的代码/测试 payload 精确限于两个文件：

- `tests/platform/web/host/web_runtime_host_browser.spec.mjs`；
- `apps/web-runtime-host/test/web_host_source_boundary_test.py`。

不得修改 `packages/web-runtime-platform/src/bridge.cpp`、
`packages/web-runtime-platform/src/web-runtime-pre.js` 或其他生产文件。若新的确定性证据显示
上述安全不变量有任一项失败，必须停止这个测试修复 Task，重新开展产品竞态设计；不能在本
Task 中临时扩大生产范围。

## 2. Live RED 与当前源码

GitHub Actions [Run 31874142167](https://github.com/endaye/lmdj/actions/runs/31874142167)
是当前问题的权威 RED：

- event 为 `push`，branch 为 `main`；
- exact head 为 `a71c62d43c4567daf856eab13f26ebcb5e1b30b3`；
- `web-runtime-host` packaged Chromium lane 失败；
- case 为 `Chromium packaged responsive cancellation wins before mutation publication`；
- `expect([0, 2]).toContain(attackEvidence.rejectedConsumes)` 收到 `1`；
- 同一代码在 netcup Task 4 benchmark 的 5 次执行和后续 rerun 中通过。

截至本设计基线 `origin/main`
`b84dd33023056cb7cee1cb5cae2ece49cc52e2be`，Issue 仍为 `OPEN`，browser spec 仍只接受
`[0, 2]`。后续合入的 Integration Queue 工作没有修改该测试、terminal native state machine
或 Browser Main cleanup 路径，因此偶发失败条件仍在。

当前 test attack 会：

1. 捕获 Browser Main 发出的 `release-and-close` token；
2. 发送两个带同一 token 的 forged `released-and-closed` ACK；
3. 同时发送两个 duplicate `release-and-close` request；
4. 包装 `Module.ccall`，记录每次
   `lmdj_web_host_consume_terminal_release` 的返回值；
5. 观察真实 Worker 发出的 ACK；
6. 在 test 末尾直接 replay 已消费的 token。

失败不是 token、completion、Truth 或 cleanup gate 报错，而是第 4 步的自动 rejection 数量
不在手工枚举集合中。

## 3. 合法 `rejectedConsumes == 1` 的因果顺序

native terminal release state 只允许以下关键路径：

```text
ready
  -> authorized
  -> completed_released | completed_not_released
  -> consumed
```

Browser Main 处理每个 ACK 时不信任 channel message 的 `released` 字段；它把 token 交给
native `lmdj_web_host_consume_terminal_release`。只有 state 已经是 `completed_released` 或
`completed_not_released`、token 匹配且 CAS `completed_* -> consumed` 成功时，consume 才返回
`1` 或 `0`。其他时刻、错误 token 或 CAS loser 一律返回 `-1`。成功 consume 后 Browser Main
同步进入 `completeTerminalCleanup()`，清除 timeout、终止 Worker、关闭 terminal channel 并
完成 terminal failure delivery。

现有 responsive test 还故意延迟真实 Worker ACK 在 Browser Main 的投递；forged ACK 带有
`released: true`，不会走该延迟分支。这使下面三种自动 rejection 计数都合法：

| 自动 rejection | 合法顺序 | 安全结果 |
| --- | --- | --- |
| `0` | native completion 先于第一个 forged ACK；第一个 ACK 成功 consume，cleanup 关闭 channel | 恰好一个 consume 成功，其余 queued ACK 不再交付 |
| `1` | 第一个 forged ACK 在 completion 前返回 `-1`；completion 发生；第二个 forged ACK 成功 consume | 恰好一个早到 ACK 被拒，恰好一个 consume 成功 |
| `2` | 两个 forged ACK 都在 completion 前返回 `-1`；稍后的真实 ACK 或 fallback 成功 consume | 两个早到 ACK 被拒，仍只有一个 consume 成功 |

因此 rejection cardinality 只描述 browser event queue 与 native completion 的相对调度，不描述
安全边界。把 `1` 排除在 `[0, 2]` 外没有 happens-before 依据；把集合扩大成 `[0, 1, 2]`
虽然能覆盖当前三种结果，仍错误地把 incidental delivery count 当成产品契约。

## 4. 必须保留的安全不变量

未来 implementation 只能删除非语义 cardinality，不能减少以下真实断言：

1. cancellation 在 mutation publication claim 前赢得 `open -> cancelled`，outcome 为
   `HOST_TIMEOUT`；
2. Host 进入 `restart-required`，transport 已 sealed/terminated，新 submit 被拒；
3. attack 确实发送两个 forged ACK 和两个 duplicate release request；
4. attack channel 确实观察到一个真实 Worker ACK；
5. 自动 ACK 处理中 `acceptedConsumes == 1`；
6. 对已消费 token 的显式 `replayConsumedTerminalAck(owner)` 返回 `-1`；
7. replay 后 `acceptedConsumes` 仍为 `1`，证明 replay 没有制造第二次成功；
8. `terminalOwnerReleased == true`；
9. deadline proof 仍显示 `claim_attempted == false`；
10. 直接 OPFS inventory 与 cancellation 前完全一致；
11. deadline 后没有新增 response 或 notification；
12. 新 page 能立即重新取得 writer，reopen revision、Project inspect 与 OPFS inventory 都与
    cancellation 前一致；
13. owner 与 reopened page 都通过正式 controller clean close。

这些断言共同证明 forged、duplicate 或 replayed channel messages 不能伪造 native completion、
不能重复释放 owner、不能发布 mutation，也不能破坏权威 Project Truth。任何一项失败都属于新的
产品缺陷证据，不能通过放宽测试解决。

## 5. 为什么不改生产代码

当前生产路径已经把不可信 wake-up message 与权威 native state 分离：

- Control 只授权一次 release，并在 release 后记录一次 native completion；
- Browser Main 只通过 native token/state/CAS 消费 completion；
- forged message 的 `released` 字段不参与权威判断；
- `completed_* -> consumed` 只有一个 CAS winner；
- 成功 winner 立即触发 once-only cleanup；
- 显式 replay 和所有 later ACK 都不能再成功；
- packaged test 继续证明 mutation 未发布、Truth 未变化和 writer 可恢复。

Run 31874142167 没有出现两个 successful consumes、owner 未释放、cleanup 重复、Truth 漂移或
late publication。唯一失败是 test-side rejection count。因此，为了让调度更“整齐”而修改
`bridge.cpp`、`web-runtime-pre.js`、BroadcastChannel delivery 或 timeout 会制造一个产品层顺序
要求，却没有对应安全或用户价值。那还会引入 Host/Platform identity、Product Assembly、版本与
Portal 评估，明显超出当前证据和 YAGNI 边界。

## 6. 方案比较

### 6.1 方案 A：把集合扩大为 `[0, 1, 2]`

优点是只有一行变化，并能直接覆盖 live RED。缺点是继续把 browser 自动投递次数当成契约；未来
合法的 cleanup timing 变化仍可能制造无意义失败，reviewer 也必须重新推导每个数字。因此不采用。

### 6.2 方案 B：删除自动 rejection cardinality，固定因果不变量（推荐）

responsive case 不再读取并枚举自动 `rejectedConsumes`。它仍等待 attack/Worker evidence 和
`acceptedConsumes == 1`，然后直接执行 replay 并断言返回 `-1`，再确认 accepted count 仍为
`1`。source-boundary regression 同时禁止 responsive case 重新引入 rejection cardinality，
并要求保留 replay 与 once-only success。

优点是测试与 native safety contract 对齐，`0/1/2` 三种合法调度自然通过，同时不会放松
mutation、cleanup、Truth 或 recovery 断言。缺点是自动 rejected event 的数量不再显示为 gate；
但该数量没有产品含义，真正需要的 rejection 已由显式 replay 确定性证明。因此采用本方案。

### 6.3 方案 C：修改生产代码以串行化 ACK delivery/completion

可以尝试增加 queue、锁、ack sequence 或延迟，使 automatic rejected count 固定。优点是测试
数字稳定；缺点是改变产品并发和 cleanup timing，引入新的 deadlock/timeout surface，并要求
Host/Platform/Product Build 与 Portal 影响审查。现有 CAS 已提供所需线性化点，没有证据支持
另一层同步。因此拒绝本方案。

## 7. 推荐的未来实现

### 7.1 Browser packaged regression

在 `tests/platform/web/host/web_runtime_host_browser.spec.mjs` 的 responsive cancellation case
中只做以下语义变化：

- 删除保存 `attackEvidence` 仅用于读取 automatic `rejectedConsumes` 的局部变量；
- 删除 `[0, 2]` cardinality assertion；
- 保留 poll 中的 forged/duplicate/real ACK 与 `acceptedConsumes: 1`；
- 保留直接 replay 返回 `-1`；
- replay 后重新读取 attack evidence，只断言 `acceptedConsumes: 1`，不再比较 rejected count
  的增量；
- 保留第 4 节的其余 deadline、terminal、OPFS、late-message、reopen 和 close assertions。

`terminalAckAttackEvidence()` 仍可返回 `rejectedConsumes`，因为 unresponsive cancellation case
仍使用自己的异步 ordering evidence。本 Task 不顺手重构共享 helper，也不改变 unresponsive
case 的已批准边界。

### 7.2 Source-boundary regression

在 `apps/web-runtime-host/test/web_host_source_boundary_test.py` 中提取完整 responsive
cancellation test body，并新增一个 fail-closed contract，要求该 body 同时满足：

- 存在 `forgedAcksSent: 2`、`duplicateReleaseRequestsSent: 2`、
  `observedWorkerAcks: 1` 和 `acceptedConsumes: 1`；
- 存在 `replayConsumedTerminalAck(owner)` 且直接断言 `.toBe(-1)`；
- replay 后仍检查 `acceptedConsumes: 1`；
- 存在 `terminalOwnerReleased: true`、OPFS equality、late-message equality 与 reopen recovery；
- 不包含对 `rejectedConsumes` 的 exact value、集合 membership 或增量 cardinality 断言。

错误诊断必须明确点名 `responsive terminal-ack proof` 与 `scheduler-dependent rejection
cardinality`，使未来回归在 source boundary 就能定位，不能只输出通用 assertion failure。

该 source-boundary test 只锁定测试证据形状，不解释或替代真实 packaged browser proof。两者必须
一起通过。

## 8. TDD 与受压 packaged Proof

### 8.1 RED

未来 implementation 严格按以下顺序开始：

1. 记录 live RED Run 31874142167 的 exact run/head/job/test/error；
2. 先修改 `web_host_source_boundary_test.py`，加入第 7.2 节 contract；
3. 在 browser spec 尚未变化时运行 `scripts/web-runtime-host.sh build`；
4. 预期 source-boundary 以明确的 scheduler-dependent cardinality 诊断失败。

这一步让 repository 内可重复的 contract 先 RED；不能把修改 browser assertion 和新增 guard
合在第一次测试运行之前。

### 8.2 GREEN

只按第 7.1 节修改 browser spec，再运行：

```bash
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh proof
```

`build` 必须证明 source-boundary contract 为 GREEN；`proof` 必须使用正式 packaged
`CONFORMANCE=OFF` distribution、真实 C++/Emscripten/native state、Chromium、OPFS 与
BroadcastChannel，不能用 mock、source shell 或纯字符串测试替代。

### 8.3 CPU/IO contention evidence

在具备 pinned Web toolchain 的 Linux runner 上，保持 CPU 与文件 I/O contention 的同一个
声明 session，连续运行三次完整 `scripts/web-runtime-host.sh proof`。三次必须全部通过，不允许
从更多失败/成功运行中挑选三次成功作为证据。报告必须记录：

- runner identity；
- exact implementation commit；
- contention 命令、开始/结束时间与退出状态；
- 三次 proof 的开始/结束时间与结果；
- responsive case 的 `acceptedConsumes == 1`、explicit replay `-1`、Truth/OPFS recovery 均未
  失败。

受压 proof 的目的不是强求再次观测到 `rejectedConsumes == 1`；该数字已经由 live RED 证明
可达。目的是真实验证删除 incidental cardinality 后，所有安全不变量在调度压力下仍保持。

### 8.4 完整回归

未来 implementation 至少运行：

```bash
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

实现改变 packaged Web test，因此 Pull Request 还必须取得正常 Change Scope 选择的
`web_runtime_host` lane、same-run successful `PR Gate` 与远端 Integration Queue validation；
本地 proof 不能替代这些边界。

## 9. 文件与范围边界

未来 implementation 的 tracked code/test 文件精确为：

```text
tests/platform/web/host/web_runtime_host_browser.spec.mjs
apps/web-runtime-host/test/web_host_source_boundary_test.py
```

implementation planning 是用户批准本 spec 后的下一独立阶段；本文件不创建 implementation
plan。未来 plan 必须保持上述 payload 边界。禁止顺带修改：

- `packages/web-runtime-platform/` 生产代码；
- `apps/web-runtime-host/src/`；
- Module/Host manifests；
- `products/lmdj/`、Assembly 或 lock；
- Architecture Portal current/versioned pages；
- CI/queue workflows 或 controller；
- release intent、tag、Release、deployment 或 Channel state。

若两个 declared files 无法完成第 4 节安全不变量和第 8 节验证，未来 implementation 必须报告
`NEEDS_CONTEXT` 并回到设计阶段，不能静默扩大范围。

## 10. 远端 Integration Queue 边界

本设计分支基于 `origin/main`
`b84dd33023056cb7cee1cb5cae2ece49cc52e2be`。截至 2026-08-21 的 live 顺序为：

1. PR [#223](https://github.com/endaye/lmdj/pull/223) 先以 merge commit
   `9d63a9d8dc3c2d13d67308331f96af67debd25c7` 修复 queue artifact redirect；
2. PR #224 以 `e57f94fc` 固定 synchronized queue run validation；
3. PR [#222](https://github.com/endaye/lmdj/pull/222) 随后完成首个授权的 documentation-only
   end-to-end queue acceptance，full Core CI run `32441268034` 的 `web-runtime-host` 与
   same-run `PR Gate` 均成功，最终 merge commit 为
   `c8c3790efb38ff898114011579faf9e2cfac1c13`；
4. PR #225 再以当前 base `b84dd330` 收敛 merge postcondition reconciliation。

因此 future #166 implementation 没有 #223/#222 文件依赖，但有当前远端 integration gate：

- 必须从届时最新 `origin/main` 创建 fresh implementation worktree；
- normal PR review 与 required checks 完成后，只有具备权限的人显式添加 `merge:queue` 才授权
  自动 squash merge；
- queue 必须同步 exact current main，绑定 exact PR/base/head 与 numeric full validation run，
  same-run `PR Gate` 成功后再次核对 live state；
- label 撤销、head/base 漂移、CI failure 或 reconciliation 不确定时均 fail closed；
- 本 spec commit、未来 implementation commit、push、PR 与普通 CI 都不自动授权添加 label；
- queue merge evidence 不等于 resulting exact-main full release evidence，也不授权 tag、Release、
  deployment 或 Channel promotion。

本轮只创建本地 spec commit，不 push、不创建 PR、不添加 label、不执行 queue 或 issue write。

## 11. Version Management

Version impact: none

Reason: 本设计及推荐实现只纠正测试对 browser scheduler-dependent rejection count 的错误约束，
不改变公开产品行为、Product Build、Web Runtime Platform 或 Web Host API/ABI、Contract、Provider、
Model、Product Assembly、Assembly Lock、依赖或 runtime bytes。未来 implementation 不修改任何
manifest、`version.json`、Assembly 或 lock，不分配 Product Build，不创建 tag 或 immutable
Architecture Portal snapshot。

## 12. Documentation Impact

Documentation impact: none

Reason: 产品 terminal state machine、once-only cleanup、restart-required、Project Truth、OPFS
recovery、测试层级和稳定 Proof 命令均不变。推荐实现只让现有 packaged regression 按这些既有
事实断言，不再把非语义的 browser event delivery count 当成契约；它不改变 Architecture Portal
的 current product、architecture、evidence、operation 或 version facts，因此不需要修改 Portal
route 或 source diagram。

本 spec 是已批准设计记录，不是 Portal current 页面。仍须运行
`scripts/architecture-portal.sh check`，证明 `Documentation impact: none` 没有掩盖身份、路由或
current-truth drift。

## 13. Acceptance Criteria

本设计对应的未来 implementation 只有在以下条件全部满足后，才能报告 implemented：

- repository 内 source-boundary guard 先按第 8.1 节产生预期 RED；
- responsive packaged test 不再断言 automatic rejection cardinality；
- 第 4 节十三项安全不变量全部保留；
- explicit replay 确定性返回 `-1`，且 replay 前后 accepted consume 总数保持 `1`；
- source-boundary failure 明确点名 responsive terminal ACK 与 scheduler-dependent cardinality；
- 普通 packaged proof 和同一受压 session 的连续三次 packaged proof 全部通过；
- active-tree、version、version verify 与 Architecture Portal checks 通过；
- implementation tracked code/test diff 只有第 9 节两个文件；
- PR 按第 10 节通过届时有效的 review、required checks 与远端 Integration Queue gate；
- 没有 Product Build、Assembly、manifest、Portal snapshot、release 或 deployment mutation。

## 14. 设计完成边界

本文记录到 `designed` 状态。spec commit 不代表 planned、implemented、pushed、PR opened、merged、
released 或 deployed。用户 review 并批准本书面 spec 后，下一步才是调用 writing-plans 创建独立
implementation plan；在该批准前不得进入 implementation。
