# Stage 7 Keyboard Spatial Mapping Canary Evidence — 1.0.20.0

## Evidence boundary

This record binds the automated candidate Proof for the corrected keyboard
spatial mapping to clean committed revision
`7d409b5ab5ae537e540a46f46a296557570a3e2f`. It does not claim that this
branch has been pushed or merged into `main`, and it does not claim manual,
physical-device, hearing, Safari, iPadOS, Release, deployment, publication, or
Channel-promotion acceptance.

| Field | Value |
| --- | --- |
| Candidate branch | `fix/stage7-review-remediation` (unpublished) |
| Tested source revision | `7d409b5ab5ae537e540a46f46a296557570a3e2f` |
| Mapping implementation revision | `6a1cd97ba4e65f3515fdbe9f99b147170c46d11c` |
| Snapshot commit / source revision | `cd1f18a8928acc60eb25313a928720c5eca55675` / `6a1cd97ba4e65f3515fdbe9f99b147170c46d11c` |
| Integrated `origin/main` | local merge `b65e31e52fe15da72dce6f1322ffe56033edf832`, second parent `6e7d702061858189f4b0048a1aa3e154abfd9c26` |
| Product / Platform / Creator / Formal Host | `1.0.20.0` / `0.2.1` / `1.1.2` / `1.2.8` |
| Channel | `canary` |
| Assembly Lock SHA-256 | `85c6070255bb4d7184aecada7bd4644af418e7c047aaa15631b0af1426e45913` |
| Creator host manifest SHA-256 | `1bd0435628c93b3dbb7dba90330d69bd96ad6234a7f9585bce84d151a939315c` |
| Host OS | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| T1 | `passed — all ten steps confirmed by endaye on 2026-08-13` |
| Branch-to-main integration | `origin/main` advanced by an external direct push to `ccd0aec` on 2026-08-13 11:51 +0800; no associated PR; GitHub run `31665186166` is in progress |
| Manual-acceptance publication | acceptance addendum commit `95ae181` remains branch-local and unpushed |

The immutable Portal snapshot records the clean mapping implementation revision.
The tested revision is its descendant through the snapshot commit, the local
`origin/main` merge, a TypeScript-only lookup typing correction, and a Host test
expectation correction. Schema-2 provenance accepted that ancestry and verified
the unchanged `1.0.20.0` snapshot and Assembly identity.

## Corrected spatial contract

- `Q W E R T Y U I` map top-to-bottom to local Pads 1–8.
- `A S D F G H J K` map top-to-bottom to local Pads 9–16.
- Every Bank applies the same local order.
- Creator visible `<kbd>` hints and accessible Pad names derive from the same
  frozen `DEFAULT_KEYBOARD_MAPPING` used by Runtime input admission.

## Automated candidate gates

All final commands below passed from a clean committed tree ending at
`7d409b5ab5ae537e540a46f46a296557570a3e2f`.

| Command / gate | Result |
| --- | --- |
| `scripts/creator-web.sh proof` | PASS; fixture and distribution reproducibility; Vitest 62/62; Platform 88/88; Chromium 13 passed/1 designed physical-MIDI skip; WebKit capability boundary 1/1 |
| `scripts/web-runtime-host.sh proof` | PASS; AudioWorklet/failure 21/21; package and distribution reproducibility; Chromium 15 passed/1 designed skip; WebKit 1 passed/10 capability skips |
| `scripts/core.sh proof` | PASS; Release CTests 37/37; Product Build `1.0.20.0`; Channel `canary`; Assembly Lock `MATCH` |
| `bash scripts/verify-core-dependencies.sh` | PASS; vendored and offline |
| `bash tests/build/test_active_tree.sh` | PASS |
| Product version / module graph / version lock gates | PASS |
| `scripts/architecture-portal.sh check` | PASS; 47/47 tests, 37 pages, 10 diagram sources/20 outputs, optimized build, 42 routes/internal links |
| `main` integration CI-control tests | PASS; change scope 30/30, local preflight 45/45, runner fallback 18/18, workflow topology 20/20 |

The first full Creator attempt exposed a TypeScript type mismatch in the derived
hint lookup; `ad3b5c6` corrected its static type without introducing a second
mapping table. The first full Host attempt then exposed an old `KeyS -> slot 1`
test expectation; `7d409b5` updated the real Host journey to the shared spatial
contract. Both complete owning Proof commands were restarted and passed.

The Creator Proof's deterministic `creator-proof-bundle.lmdj` lived in its owned
temporary proof directory and was removed by the successful cleanup trap. The
Proof compared two independently packed copies byte-for-byte before browser use;
no durable fixture path or digest is claimed by this record.

## 人工 Canary 验收表（已完成）

T1 状态：`通过 — endaye 在当前 Codex 任务中确认十步全部完成且未发现问题`。
本次结果是 `1.0.20.0` 的独立执行，未沿用 `1.0.18.0` 的步骤 1–6。

### 开始前记录

| 字段 | 填写内容 |
| --- | --- |
| 操作人姓名 | `endaye（本任务用户确认）` |
| 日期、时间及时区 | `2026-08-13 11:46:38 +0800`（报告文件时间）；`11:50:06 +0800` 确认十步通过 |
| 浏览器及精确版本 | `Google Chrome 151.0.7922.110`（验收后读取本机安装版本） |
| 设备及操作系统 | Apple Silicon Mac；macOS `26.6.1` (`25G76`)，Darwin `25.6.0` arm64 |
| 包对应源码 revision | `7d409b5ab5ae537e540a46f46a296557570a3e2f` |
| Product Build | `1.0.20.0` |
| Creator Host Manifest SHA-256 | `1bd0435628c93b3dbb7dba90330d69bd96ad6234a7f9585bce84d151a939315c` |
| 正式测试工程及 SHA-256 | `stage7-canary.lmdj` / `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c`；Bundle verify PASS |
| 验收报告 SHA-256 | `lmdj-creator-web-1.0.20.0.json` / `7e2a2bbeb2cd4eb332112086e849148adf1553345ecce45c6eab22e9e016333a` |
| 人工签字确认 | `通过 — endaye 在当前任务中明确确认“十步都做完了，没有什么问题”` |

### 十步操作

| 步骤 | 操作与必须观察的结果 | 人工结果 |
| ---: | --- | --- |
| 1 | 打开 Creator；页面正常加载，未自行播放声音。 | `通过（用户确认）` |
| 2 | 导入正式 `.lmdj` 工程；短暂 `importing` 后回到 `ready`，操作按钮恢复。 | `通过（用户确认）` |
| 3 | 记录 Project ID、revision、BPM 和 64 Pad 占用，确认数据符合测试工程。 | `通过（用户确认）` |
| 4 | 点击 **Activate Audio**，确认音频成功激活。 | `通过（用户确认）` |
| 5 | Bank A 逐项验证实体键盘：`Q..I -> A1..A8`，`A..K -> A9..A16`；同时确认每个 Pad 显示相同键帽且能听到对应声音。 | `通过（用户确认）` |
| 6 | 切换 Bank B、C、D，抽查同一局部键序映射、Pad 地址和声音对应。 | `通过（用户确认）` |
| 7 | 点击 **Suspend**，确认停止；再次点击 **Activate Audio**，确认恢复触发。 | `通过（用户确认）` |
| 8 | 刷新页面，重新打开同一 Project，再次显式激活音频。 | `通过（用户确认）` |
| 9 | 确认无重复、漏触发、按下卡住或自动播放，且 Project 数据未丢失。 | `通过（用户确认）` |
| 10 | 点击 **Export report**，检查隐私安全字段并记录文件 SHA-256。 | `通过；报告已校验并记录 SHA-256` |

### 必须单独记录

| 观察项 | 人工结果 |
| --- | --- |
| Import 是否退出 `importing` 且按钮恢复 | `通过（用户确认）` |
| 实体键盘空间顺序与逐键听感 | `通过（用户确认）` |
| 实体 MIDI | `延期 / 未验证` |
| Bank B/C/D 地址与声音对应 | `通过（用户确认）` |
| Suspend 后再次激活 | `通过（用户确认）` |
| macOS Safari | `延期 / 未验证` |
| iPadOS Safari touch / lifecycle | `延期 / 未验证` |
| 报告检查、SHA-256 与签字 | `通过；用户确认及 SHA-256 已记录` |

### 导出报告校验

报告 contract 为 `lmdj.creator-web.acceptance.v1`，身份为 Product
`1.0.20.0`、Creator `1.1.2`、Platform `0.2.1`、protocol `1`；九项 capability
均为 `true`，Bank/Pad 为 `4/64`，Trigger 计数为 `28 admitted / 28 outcomes /
0 rejected`，`error_code` 为 `null`。报告导出瞬间的 Host state 是受支持的
`recovering`，并非 `running`；本记录保留该原始事实，不从报告单独推导最终运行态。
十步通过结论来自操作者对实际 UI、声音和流程的明确确认。

报告中的 physical 五项仍按产品 allowlist 写为 `deferred / unverified`。因此本次
T1 关闭只覆盖上述十步，不能被解释为实体 MIDI、macOS Safari、iPadOS touch 或
iPadOS lifecycle 通过。

This task did not push or create a Pull Request, tag, Release, deployment,
publication, or Channel promotion. During acceptance recording, live verification
found that another process had directly pushed the preceding candidate history
through `ccd0aec` to `origin/main`; no associated PR exists. Its full `main` push
run `31665186166` is still in progress, so this record does not yet claim a
successful merged-main Proof. The manual-acceptance addendum remains local.
