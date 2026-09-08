# Web Capability Probe Timeout Design

日期：2026-08-21

状态：规格已批准；授权后续 planning、implementation、push、Pull Request、required checks、
Integration Queue merge 与受控 runner 验收，不授权 tag、Release、deployment 或 Channel promotion

关联任务：[Issue #247](https://github.com/endaye/lmdj/issues/247)、
[Issue #166](https://github.com/endaye/lmdj/issues/166)

## 1. 结论

Web Runtime Platform 当前把 Control Worker 在 `2_000ms` 内没有回消息直接转换成
`opfs=false`、`opfsSyncAccessHandle=false` 与 `opfsWritableReplace=false`。这混淆了两种不同
事实：浏览器确实缺少 mandatory OPFS primitives，以及具备全部能力的 Worker 因 CPU/文件 I/O
contention 暂时没有被调度。后者最终被 `runPreflight` 错报为
`UNSUPPORTED_WEB_RUNTIME`。

推荐实现保持一次、受限、真实的 Worker/OPFS probe，把默认等待预算设为具名的
`15_000ms`。明确缺少 Worker/Blob、Worker 返回 negative 或既有 Worker error 路径继续 fail
closed；只有等待预算耗尽必须抛出类型化 `HOST_TIMEOUT`，不能伪造 negative capabilities。
probe 在 success、worker error 或 timeout 后
都继续 terminate Worker 并 revoke Blob URL。

本 Task 不增加 retry、backoff 或 capability cache，不修改 OPFS probe operations、Preflight
mandatory capability set、Contract、Product Assembly 或版本身份。它先用 packaged Chromium
回归证明 `2_500ms` delayed response 在旧实现上 RED，再用短的 test-only deadline seam 证明
真正 deadline expiry 精确为 `HOST_TIMEOUT`。

## 2. 已证实根因

Issue #166 的受压验收在 Contabo 固定 Linux session 中运行第一轮完整
`scripts/web-runtime-host.sh proof` 时，visible diagnostic project reload 预期
`audio-suspended`，实际进入 `failed`。同一轮的 #166 responsive terminal-ACK case 没有失败。

后续同一 CPU/文件 I/O contention 下取得三组诊断事实：

1. 单独运行 visible reload case 通过；
2. 按原顺序运行前两个 browser cases 通过；
3. 完整 Chromium Host suite 在 trace-on 下 `15 passed, 1 skipped`，#166 responsive case 通过。

成功 trace 显示 reload preflight 从 navigation 到 `audio-suspended` 约为 `2.06s`，已经越过当前
probe 的 `2.00s` 边界附近。独立 causality experiment 只延迟首个 Blob Worker message
`2_500ms`，即可确定性得到：

```json
{
  "host_state": "failed",
  "error_code": "UNSUPPORTED_WEB_RUNTIME",
  "secureContext": true,
  "crossOriginIsolated": true,
  "sharedArrayBuffer": true,
  "webAssembly": true,
  "audioWorklet": true,
  "opfs": false,
  "opfsSyncAccessHandle": false,
  "opfsWritableReplace": false
}
```

实验没有删除或替换 OPFS API；三项 `false` 只来自
`packages/web-runtime-platform/web/runtime_session.mjs` 的 timeout fallback。因此问题是生产
capability classification 的时序错误，不是 #166 terminal-ACK 实现或 test assertion 回归。

## 3. 行为模型

### 3.1 实际 negative capability

以下路径继续 fail closed 为 `UNSUPPORTED_WEB_RUNTIME`：

- `Worker` 或 `Blob` primitive 不存在；
- Worker 成功运行 probe 并实际返回任一 mandatory OPFS capability 为 `false`；
- Worker 发布 error，无法取得可信 capability result；
- `runPreflight` 发现其他 mandatory capability 为 `false`。

这些既有 fail-closed 路径继续使用 `UNSUPPORTED_WEB_RUNTIME`；它不能表达纯调度 deadline。

### 3.2 Probe deadline expiry

Control Worker 已建立但在 `15_000ms` 内没有发布 result 时，probe reject 类型化
`HostProtocolError("HOST_TIMEOUT", ...)`。Runtime Session 的既有 `start()` error path 捕获它、
进入 terminal failed state，并把 `diagnostics().error_code` 固定为 `HOST_TIMEOUT`。

timeout 不写入三个伪造的 `false` 值。diagnostics 中尚未获得的 capability snapshot 仍保留初始化
状态，但错误分类由 `HOST_TIMEOUT` 权威表达；调用者不能把 snapshot 当作实际 negative probe。

### 3.3 Cleanup

probe 仍由一个 `try/finally` 拥有 Worker 和 Blob URL。无论 Promise 由 message resolve、worker
error resolve，还是 timeout reject，`finally` 都执行：

```text
worker.terminate()
scope.URL.revokeObjectURL(url)
```

late message 不能重新启动 Runtime Session，也不能改变已经锁存的 terminal error。

## 4. 方案比较

### 4.1 只把 `2_000ms` 改大

实现最小，但 deadline 仍返回三个伪造的 `false`，继续把 scheduler/IO delay 误报成不支持。
未来只要机器再次越过新数字，就会重现相同语义错误。因此拒绝。

### 4.2 单次具名预算并区分 timeout（采用）

把默认预算改成具名 `CONTROL_WORKER_CAPABILITY_PROBE_TIMEOUT_MS = 15_000`，message result 仍按
原逻辑进入 preflight，deadline expiry 则抛 `HOST_TIMEOUT`。通过 test-only seam 把 timeout
缩短，避免自动化真实等待 15 秒。

该方案保留 fail-closed、bounded startup 和一次真实 OPFS mutation，同时纠正错误分类；没有
新增可变状态或重复 probe，因此采用。

### 4.3 Retry 或 cache

retry 会重复创建临时 OPFS entry 和 Worker，并需要定义 attempt identity、总预算与 error
precedence；cache 会让 reload 使用陈旧的 browser/storage state。当前证据只要求正确等待和分类，
没有证明需要这些机制。因此拒绝。

## 5. 实现边界

### 5.1 Runtime Session

修改 `packages/web-runtime-platform/web/runtime_session.mjs`：

- 新增具名 `15_000ms` 默认常量；
- 让 `probeControlWorkerCapabilities(scope, timeoutMs)` 使用注入预算；
- timeout callback reject `HOST_TIMEOUT`，不 resolve negative object；
- `defaultCapabilities(scope, timeoutMs)` 传递预算；
- `createRuntimeSessionController` 在 seam 为 `undefined` 时使用默认预算；任何显式 seam value 都
  必须经过 positive-safe-integer validation；
- 预算必须是 positive safe integer，否则在 controller construction 时 fail closed；
- `start()` 只在使用正式 `runPreflight` 时把该预算传给 default probe；既有显式
  `options.capabilities` test seam 不变。

`capabilityProbeTimeoutMs` 只属于既有 `seams` 测试注入，不成为产品 manifest、Project Truth、
Application Facade 或 Contract 字段。

### 5.2 Packaged Chromium regression

修改 `tests/platform/web/host/web_runtime_host_browser.spec.mjs`，新增一个 init-script helper，
只包装首个 Blob Worker 的 `message` listener；仅为既有 Worker-error fail-closed 路径注入可控
synthetic `error` event，不删除或模拟 Worker 内的 OPFS operations。helper 还记录 capability
Worker termination 与 Blob URL revocation，并可向既有 `window.__LMDJ_WEB_HOST_SEAMS__` 注入短
probe budget。

新增三个 Chromium-only cases：

1. `2_500ms` delayed Worker result 使用默认 `15_000ms` budget，必须到达
   `audio-suspended`，三项 OPFS capability 都为 `true`，cleanup owner 各执行一次；
2. `100ms` delayed Worker result 配 `25ms` test budget，必须到达 `failed`，error 精确为
   `HOST_TIMEOUT` 而非 `UNSUPPORTED_WEB_RUNTIME`，cleanup owner 各执行一次；
3. synthetic Worker error 必须保留既有 `UNSUPPORTED_WEB_RUNTIME` classification，cleanup owner
   各执行一次，而且随后到达的 delayed message 不得改变 terminal state。

既有 WebKit capability smoke 继续证明真实 missing capability 输出
`UNSUPPORTED_WEB_RUNTIME`，不修改它自己的独立 browser smoke probe。

### 5.3 Architecture Portal

更新以下 current routes：

- `/core/modules/web-runtime-platform/`：一次受限 probe、actual negative 与 timeout 分类；
- `/platform/web-runtime/`：Host preflight 在 contention 下的 bounded behavior；
- `/operations/testing-and-proof/`：packaged delayed-response/timeout regression 与 #166 三连压测
  evidence boundary。

没有模块/Host/Assembly identity变化，也没有组件或数据流边界变化，因此不修改 source diagram，
不创建 immutable Product Build snapshot。

## 6. TDD 与验证

### 6.1 RED

先新增 timeout-seam construction regression，再新增 delayed success、worker error cleanup 与
deadline expiry 三个 packaged Chromium cases。focused Node regression 必须因旧 controller 接受
invalid seam 而 RED；运行正式 `scripts/web-runtime-host.sh proof` 时，delayed-success case 必须在
旧实现上以 `UNSUPPORTED_WEB_RUNTIME`/host `failed` RED。worker-error case 是对既有 fail-closed
classification/cleanup 的 characterization。不能先改 production constant，也不能用纯字符串测试
替代真实 Worker/OPFS/browser 行为。

### 6.2 GREEN

只实现第 5.1 节最小 runtime change，重新运行 focused browser case 与完整
`scripts/web-runtime-host.sh proof`。三个新 cases、既有 Chromium suite 和 WebKit limitation
必须全部通过。

### 6.3 Repository gates

提交前至少运行：

```bash
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
python3 apps/web-runtime-host/test/web_host_source_boundary_test.py
scripts/web-runtime-host.sh proof
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

Pull Request 必须取得届时 Change Scope 选择的 required checks、same-run `PR Gate`、review 与
Integration Queue exact synchronized-head validation。branch-local proof、PR merge 或 queue report
都不能替代 merged-main/runner acceptance。

## 7. #166 恢复验收

#247 合入后，从 exact merged `main` revision 在一个 pinned Linux runner 上建立一个固定 pressure
session：

- 一个持续 CPU contender；
- 一个持续执行 fixed-size write + `fsync` 的 file-I/O contender；
- contenders 在三次 proof 前启动，在第三次 proof 后统一停止；
- 同一 session 内连续运行恰好三次完整 `scripts/web-runtime-host.sh proof`；
- 三次都必须通过，不允许从更多运行中挑选三次成功。

在 session 前从 Actions runner unit 名提取 runner identity，与 GitHub runner name 做闭集相等
核对。先记录每个 Runner diagnostic log 的 inode/offset，再确认全部 online/idle，随后对这些 exact
units 安装带不存在 marker 的 runtime `ConditionPathExists` lease 并停止；lease 后的 log delta 若
出现 job assignment 就恢复并中止。等待
GitHub 报告该 exact pool offline/not busy 后才开始 proof，三轮 proof 前后都断言 services 保持
leased/inactive。停止前先建立三小时限时自动恢复 watchdog；local 与 remote traps 禁用 cleanup
`errexit` 后分别尝试删除 lease、daemon-reload 并 start exact services，验收结束前证明 service active、GitHub identity
闭集仍相等且 pool online，最后才取消 watchdog。该同主机隔离边界替代跨本机、远端与 GitHub
时钟推断 overlap，旧 workflow run 的 re-run 也无法在 session 内取得 runner。

Watchdog 必须禁止 systemd manager 提前展开 payload 内的 shell `$` 变量，并用 `Type=exec` 启动；
每次恢复重试都逐个验证 exact unit 闭集全部 `active`，不能只信任 `systemctl start` 的返回值。

记录 runner identity、kernel、exact commit/tree、toolchain identity、contention command/PID、session
开始结束时间、每次 proof 开始结束时间和 status。若任一轮失败，保留完整 log/trace 并按新的
root cause 处理；不得关闭 #166。

Netcup SSH 与 non-interactive runner-service control 都可用时，可作为首选独立 pressure host；
否则使用满足同样 service-control 前置条件的 Contabo SSH session 作为等价受控通道。普通
GitHub Actions runner 只能提供 required-check evidence，不能证明手工固定 contention session。

## 8. Version Management

Version impact: none

Reason: 本 Task 修复 Web Runtime Platform 内部 capability probe 的错误 timeout classification，
恢复“实际 negative 才是 unsupported”的既有意图，不改变公开 API/ABI、Contract、Project、
Provider、Model、Host/Module manifest、Product Assembly 或 Assembly Lock。当前 Task 不发布独立
Package、不分配 Product Build、不创建 tag；exact Git revision 是实现与压测证据身份。

若未来决定把该内部 fix 分配为团队测试或发布 Build，必须在后续独立版本 Task 中从当时 exact、
CI-verified `main` 分配新 BUILD 并冻结匹配 snapshot，不能在本 Task 暗中完成。

## 9. Documentation Impact

Documentation impact: required

Affected current routes:

```text
/core/modules/web-runtime-platform/
/platform/web-runtime/
/operations/testing-and-proof/
```

Reason: capability preflight 的 timeout/error 事实与 packaged Proof evidence 发生变化。Product
Build、Assembly、lock、模块身份和架构边界不变，因此不创建 versioned snapshot，不修改 diagram。

## 10. Acceptance Criteria

只有以下条件全部满足，#247 才能报告完成：

- packaged delayed-response test 在 production change 前取得预期 RED；
- 默认 probe budget 为具名 `15_000ms`，单次且 bounded；
- `2_500ms` actual result 成功进入 `audio-suspended`；
- deliberate deadline expiry 精确报告 `HOST_TIMEOUT`；
- zero、negative、fractional、unsafe 与 non-number timeout seam 在 construction 时被拒绝，
  positive safe integer 被接受；
- actual negative capability 继续报告 `UNSUPPORTED_WEB_RUNTIME`；
- success、worker error 与 timeout 三条 packaged cases 都精确证明一次 Worker termination 与一次
  matching Blob URL revocation；
- 没有 retry、cache、Contract、manifest、Assembly 或版本 identity mutation；
- 三个 current Portal routes 更新且完整 Portal check 通过；
- focused、完整 packaged Proof、active-tree 与 version gates 通过；
- 单一 Conventional Commit 只包含本 Task declared files；
- PR review、required checks、Integration Queue merge 与 live remote audit 完成；
- #166 在同一固定 pressure session 连续三次完整 proof 全部通过；
- 没有 tag、Release、deployment 或 Channel mutation。
