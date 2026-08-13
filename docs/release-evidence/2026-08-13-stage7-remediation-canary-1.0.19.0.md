# Stage 7 Remediation Corrected Canary Evidence — 1.0.19.0

## Evidence boundary

This record binds the corrected Stage 7 remediation candidate's automated Proof
to one clean committed revision and provides a blank sheet for a fresh human
Canary. It does not claim merged-main Proof, manual acceptance, physical-device
acceptance, Release, deployment, publication, or Channel promotion.

| Field | Value |
| --- | --- |
| Candidate branch | `fix/stage7-review-remediation` (unpublished at evidence time) |
| Tested source revision | `213023d096522de0bbe5e02e6699d775a45e67a6` |
| Implementation revision | `35c09053fd2bc64859b1a01c9cbbc2b5fb3a986d` |
| Product Build / Creator Web | `1.0.19.0` / `1.1.1` |
| Channel | `canary` |
| Assembly Lock SHA-256 | `24a341037ccc3c2547f1f79d308d4ea90a998d9f36bf99d79e3c714c1e7e0689` |
| Creator host manifest SHA-256 | `4d1364623dda71828b4733486c1fe9973d8470c0583dfe2bc24ecaeba52985bd` |
| Immutable Portal snapshot source revision | `35c09053fd2bc64859b1a01c9cbbc2b5fb3a986d` |
| Snapshot relationship | The tested revision is the direct snapshot commit; snapshot bytes and Assembly identity passed schema-2 provenance validation. |
| Host OS | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| T1 | `open — corrected candidate must restart at step 1` |
| Integration gate | `pending — requires separately authorized PR/merge and exact merged-main Proof` |

Product Build `1.0.18.0` remains immutable abandoned/unshipped failed-Canary
evidence. Its operator-reported steps 1–6 are diagnostic observations only and
are not transferred into this candidate.

## Canary-discovered defect and correction

Runtime Session replacement invalidated the old Project action token and aborted
the old Import, but the old generation's `finally` consequently skipped
`transfer-ended`. The replacement Session could list Projects while the Creator
remained permanently at `importing`, disabling Project and Audio actions.

The new rendered UI regression reproduced that exact production path. Before the
fix it failed with `expected ready, received importing`. The minimal correction
makes retiring Session cleanup clear the transient transfer state it owns while
stale async results remain rejected by the generation token. The focused test and
the complete Creator suite pass with this correction.

## Automated toolchain identity

The tested toolchain used Emscripten `6.0.5`, Node `22`, Playwright `1.62.1`, a
fixed 536870912-byte heap, `ALLOW_MEMORY_GROWTH=0`, and Google Chrome for Testing
`151.0.7922.34`. The exact Emscripten revisions and linker flags remain locked in
`build/web/toolchain/toolchain-identity.json`. Automated browser results do not
establish physical Keyboard/MIDI, hearing, Safari, or iPadOS acceptance.

## Automated candidate gates

Every passing command below ran from clean committed revision
`213023d096522de0bbe5e02e6699d775a45e67a6`.

| Command | Result |
| --- | --- |
| `scripts/core.sh configure dev` / `build dev` | PASS |
| `scripts/core.sh test dev full` | PASS; 53/53 CTests |
| `scripts/core.sh test dev stress` | PASS; 2/2 CTests |
| `scripts/core.sh coverage check` | PASS; lines 82.40% (16166/19620), branches 67.89% (4496/6622) |
| `scripts/core.sh proof` | PASS; Product Build `1.0.19.0`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/web-toolchain-conformance.sh proof` | PASS; Chromium toolchain 2/2, Chromium Project I/O 3/3, Chromium AudioWorklet 21/21; WebKit capability boundaries passed with declared skips |
| `scripts/web-runtime-host.sh proof` | PASS; package/reproducibility, deployment orchestration 49/49, Python/Node/native/distribution groups, Chromium 15 passed/1 designed skip, WebKit 1 passed/10 designed skips |
| `scripts/creator-web.sh proof` | PASS; Project fixture and two clean distributions reproducible; Vitest 62/62, package 7/7, server 3/3, Platform 88/88; Chromium 13 passed/1 designed physical-MIDI skip; WebKit boundary 1/1 |
| `scripts/architecture-portal.sh check` | PASS; 47/47 tests, 37 pages, 10 diagram sources/20 outputs, Product `1.0.19.0` snapshot/provenance, optimized build, 42 routes/internal links |
| dependency, active-tree, and version gates | PASS; vendored/offline dependencies, active source boundary, Product version and Assembly Lock verification |

During the first Host Proof attempt, another worktree was concurrently running
the same deployment test in four shards. Two 10/15-second readiness assertions
timed out under that contention. Both exact cases and the complete 49-test group
passed independently; after the competing process ended, the unchanged full Host
Proof command passed. No timeout or product assertion was weakened.

## 人工 Canary 验收表（中文快速执行版）

T1 状态：`开放 — 必须在 1.0.19.0 从步骤 1 重新执行`。

### 开始前记录

| 字段 | 填写内容 |
| --- | --- |
| 操作人姓名 | `待填写` |
| 执行日期、时间及时区 | `待填写` |
| 浏览器及精确版本 | `待填写` |
| 设备及操作系统 | `待填写` |
| 包对应源码 revision | `213023d096522de0bbe5e02e6699d775a45e67a6` |
| Product Build | `1.0.19.0` |
| Creator Host Manifest SHA-256 | `4d1364623dda71828b4733486c1fe9973d8470c0583dfe2bc24ecaeba52985bd` |
| 正式测试工程及 SHA-256 | `stage7-canary-1.0.19.0.lmdj` / `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c` |
| 隐私安全验收报告 SHA-256 | `待填写 / 尚未生成` |
| 人工签字确认 | `待填写` |

### 十步操作

每一步填写 `通过` 或 `失败：具体表现`；不得沿用 1.0.18.0 的结果。

| 步骤 | 操作与必须观察的结果 | 人工结果 |
| ---: | --- | --- |
| 1 | 打开 Creator。确认页面正常加载，且未自行播放声音。 | `未执行` |
| 2 | 导入正式测试工程 `stage7-canary-1.0.19.0.lmdj`；确认短暂 `importing` 后恢复为 `ready`，操作按钮重新可用。 | `未执行` |
| 3 | 记录 Project ID、revision、BPM 和 Pad 占用。期望为 `00000000-0000-4000-8000-000000000001`、`66`、`120`、64 Pad 全部占用。 | `未执行` |
| 4 | 点击 **Activate Audio**，确认音频成功激活。 | `未执行` |
| 5 | Bank A 中用鼠标逐个点击 16 Pad，再用实体键盘 `A S D F G H J K`、`Q W E R T Y U I` 逐个触发；逐项确认能听到声音。 | `未执行` |
| 6 | 切换 Bank B、C、D；每个 Bank 抽查 Pad 地址与声音对应关系。 | `未执行` |
| 7 | 点击 **Suspend**，确认停止；再次点击 **Activate Audio**，确认恢复触发。 | `未执行` |
| 8 | 刷新页面，重新打开同一 Project，再次激活音频。 | `未执行` |
| 9 | 确认无重复/漏触发、按下卡住或自动播放，且 Project ID、revision、BPM、64 Pad 数据未丢失。 | `未执行` |
| 10 | 点击 **Export report**；检查报告后运行 `shasum -a 256 <报告文件>`，把 SHA-256 填入上表。 | `未执行` |

### 必须单独记录

| 观察项 | 人工结果 |
| --- | --- |
| Import 后是否自行退出 `importing` 且按钮恢复 | `延期 / 未验证` |
| Bank A 鼠标逐 Pad 听感 | `延期 / 未验证` |
| Bank A 实体键盘逐键听感 | `延期 / 未验证` |
| Bank B/C/D 地址与声音对应 | `延期 / 未验证` |
| 重复、漏触发或按下状态卡住 | `延期 / 未验证` |
| 显式激活前或刷新后自动播放 | `延期 / 未验证` |
| 刷新重开后 Project 数据保持 | `延期 / 未验证` |
| Suspend 后再次激活恢复 | `延期 / 未验证` |
| 报告已检查并记录 SHA-256 | `延期 / 未验证` |

具名操作人填写并签字前，T1 保持开放。完成 T1 也不建立 merged-main
Proof，亦不授权 push、PR、merge、tag、Release、部署、发布或 Channel promotion。

## Human canary sheet — not executed

T1 status: `open — restart all ten steps on 1.0.19.0`.

| Field | Human result |
| --- | --- |
| Operator / date / timezone | `pending` |
| Browser exact version / device / OS | `pending` |
| Package source revision | `213023d096522de0bbe5e02e6699d775a45e67a6` |
| Product Build / Creator manifest SHA-256 | `1.0.19.0` / `4d1364623dda71828b4733486c1fe9973d8470c0583dfe2bc24ecaeba52985bd` |
| Fixture / SHA-256 | `stage7-canary-1.0.19.0.lmdj` / `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c` |
| Acceptance report SHA-256 / sign-off | `pending` |

Physical MIDI, physical Keyboard, hearing, macOS Safari, and iPadOS Safari touch
and lifecycle remain `deferred / unverified` until actually performed.
