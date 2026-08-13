# Stage 7 Remediation Canary Evidence — 2026-08-13

> Current candidate note: this file preserves the withdrawn `1.0.18.0` run and
> its historical diagnostic observations. The `1.0.19.0` corrected package was
> fully proved but its blank human sheet was not executed before the keyboard
> spatial-order defect was identified. Product Build `1.0.20.0` requires a new
> evidence record and a fresh ten-step run whose step 5 verifies
> `Q W E R T Y U I -> A1..A8` and `A S D F G H J K -> A9..A16`.

## Evidence boundary

This record binds the Stage 7 remediation candidate's automated Proof to one
committed source revision and provides a blank sheet for the separately required
human canary. It does not claim merged-main Proof, manual acceptance, physical
acceptance, Release, deployment, publication, or Channel promotion.

| Field | Value |
| --- | --- |
| Candidate branch | `fix/stage7-review-remediation` (unpublished at evidence time) |
| Tested source revision | `c44517bc7bde30cea4a40a7cab495a081028eb7e` |
| Tested Product Build | `1.0.18.0` |
| Channel | `canary` |
| Assembly Lock SHA-256 | `3cd490099b7e7f15204d7af719f73bf7983077fe208e7644ce55cdc8c2809407` |
| Creator host manifest SHA-256 | `9dda47e70d26b53dcd3c7d7460c716c401f6ace7d764669f449786745b8ca367` |
| Immutable Portal snapshot source revision | `561fa2d6324d2fe2025eaf692026e5eedcb350bb` |
| Snapshot relationship | The tested revision is a descendant; the snapshot bytes and Assembly Lock identity are unchanged and passed schema-2 provenance validation. |
| Host OS for automated Proof | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| T1 | `withdrawn after failed human Canary; corrected Build must restart at step 1` |
| Historical G1 | `corrected — historical Proof recovered` |
| Product Build 1.0.18.0 disposition | `abandoned and unshipped; no tag or promotion permitted` |

The evidence document is committed after the tested revision, so its own
documentation commit is not the tested product revision. The immutable Portal
snapshot correctly binds its earlier clean source revision rather than claiming
that a later evidence-only commit was the source used to freeze it.

## Disposition after first human Canary

This `1.0.18.0` candidate is **abandoned and unshipped**. During the first human
Canary, the operator reported steps 1–6 behaving normally, then could not perform
step 7 because **Suspend** was disabled. A subsequent Import reproduced a
permanent `importing` state. The screenshot showed local Project inventory had
already recovered while Audio remained inactive and Project/Audio actions were
disabled, which ruled out a merely slow initial list operation.

The confirmed cause was generation ownership during Runtime replacement: the
old Import was aborted, but its invalidated action token caused `finally` to skip
`transfer-ended`, leaking `transfer.phase = importing` into the replacement
Session. A rendered UI regression failed before the fix with
`expected ready, received importing` and passed after retiring Session cleanup
explicitly cleared its transient transfer state.

The operator-reported steps 1–6 have no named operator, exact browser version,
report hash, or sign-off and are retained only as diagnostic observations. They
are not partial T1 acceptance. The blank sheets below are withdrawn and must not
be continued. Product Build `1.0.19.0` / Creator Web `1.1.1` requires a separate
clean evidence record and a fresh ten-step Canary beginning at step 1.

## Recovered historical merged-main Proof

Live GitHub Actions and signed-tag verification on 2026-08-13 established that
the two historical Stage 7 tags already had successful full-mode `main` push
runs at their exact tag revisions. The missing artifact was a repository
binding from Product Build/tag to run, not the Proof execution itself.

| Product Build | Signed tag revision | GitHub Actions run | Event / result |
| --- | --- | --- | --- |
| `1.0.16.5` | `38a8c130e5f1ced6f27d8fd7d2cba2fd1d70f97f` | `31327104838` | `push` / `success`; 12 success, 1 designed fallback skip |
| `1.0.16.8` | `336a27c0799035b2f8d6455b32259ee227df20f6` | `31529410253` | `push` / `success`; 20 success, 1 designed fallback skip |

Both annotated tags passed local GPG verification. `.github/workflows/ci.yml`
runs on pushes to `main`, and `scripts/ci/change_scope.py` forces `push` events
to `full` mode and requires a full manifest to select every lane. This corrects
historical G1 as a documentation binding gap, not a Proof execution gap. It
does not satisfy the separate future merged-main Proof gate for the corrected
Product Build `1.0.19.0`.

## Automated toolchain identity

The generated `build/web/toolchain/toolchain-identity.json` used by the passing
Proof recorded:

```json
{
  "allow_memory_growth": false,
  "emcc_version": "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) 6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)",
  "emscripten_releases_revision": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
  "emsdk_revision": "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
  "emsdk_tag": "6.0.5",
  "initial_memory": 536870912,
  "node": "22",
  "playwright": "1.62.1"
}
```

The linker contract was `-pthread`, `-sWASMFS`, `-sAUDIO_WORKLET`,
`-sWASM_WORKERS`, `-sPROXY_TO_PTHREAD`, `-sINITIAL_MEMORY=536870912`,
`-sALLOW_MEMORY_GROWTH=0`, `-sASYNCIFY=1`, and the generated OPFS Asyncify
import list. Automated Chromium used Google Chrome for Testing
`151.0.7922.34`. That binary/version is automated evidence only; the human
canary browser field below remains unfilled.

## Automated candidate gates

Every command below was run from clean committed revision
`c44517bc7bde30cea4a40a7cab495a081028eb7e`. Candidate-gate defects discovered
during earlier attempts were fixed in their owning source/tests and the complete
sequence was restarted on this final revision.

| Command | Result |
| --- | --- |
| `scripts/core.sh configure dev` | PASS |
| `scripts/core.sh build dev` | PASS |
| `scripts/core.sh test dev full` | PASS; 53/53 CTests |
| `scripts/core.sh test dev stress` | PASS; 2/2 CTests |
| `scripts/core.sh coverage check` | PASS; lines 82.40% (16166/19620), branches 67.93% (4498/6622) |
| `scripts/core.sh proof` | PASS; Product Build `1.0.18.0`, Channel `canary`, Assembly Lock `MATCH` |
| `scripts/web-toolchain-conformance.sh proof` | PASS; Chromium toolchain 2/2, Chromium Project I/O 3/3, Chromium AudioWorklet 21/21; WebKit capability-boundary coverage passed with the declared capability skips |
| `scripts/web-runtime-host.sh proof` | PASS; package/reproducibility, Python/Node/native/distribution, deployment-orchestrator, and browser groups passed; Chromium full Host 15 passed/1 designed skip; WebKit boundary 1 passed/10 designed skips |
| `scripts/creator-web.sh proof` | PASS; clean package and distribution reproducibility; Vitest 61/61, package 7/7, server 3/3, Platform 88/88; Chromium 13 passed/1 designed physical-MIDI skip; WebKit capability boundary 1/1 |
| `scripts/architecture-portal.sh check` | PASS; 46/46 tests, 37 pages, 10 diagram sources/20 outputs, Product `1.0.18.0` facts, snapshot provenance, typecheck, optimized build, and 42 routes/internal links |
| `bash scripts/verify-core-dependencies.sh` | PASS; vendored and offline |
| `bash tests/build/test_active_tree.sh` | PASS |
| `python3 tests/build/version_test.py` | PASS |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json --assembly products/lmdj/assembly.json --lock products/lmdj/assembly.lock.json` | PASS; `1.0.18.0` |

These results prove the automated candidate contract only. Designed WebKit
capability skips are not Safari product acceptance, and synthetic keyboard/MIDI
events are not physical-device or hearing evidence.

## 人工 Canary 验收表（已撤回，请勿继续执行）

T1 状态：`本轮已撤回 — 1.0.19.0 必须从步骤 1 重新执行`。

本节是下方英文规范表的逐项中文操作版，方便现场执行；两者验收标准
完全相同。如文字理解存在歧义，以下方英文规范表为准。自动化结果或空白项
不得当作人工通过。

### 开始前记录

| 字段 | 填写内容 |
| --- | --- |
| 操作人姓名 | `待填写` |
| 执行日期、时间及时区 | `待填写` |
| 浏览器及精确版本 | `待填写` |
| 设备及操作系统 | `待填写` |
| 包对应的源码 revision | `c44517bc7bde30cea4a40a7cab495a081028eb7e` |
| Product Build | `1.0.18.0` |
| Creator Host Manifest SHA-256 | `9dda47e70d26b53dcd3c7d7460c716c401f6ace7d764669f449786745b8ca367` |
| 正式测试工程及 SHA-256 | `stage7-canary.lmdj` / `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c` |
| 隐私安全验收报告 SHA-256 | `待填写 / 尚未生成` |
| 人工签字确认 | `待填写` |

### 十步操作

在每一步的“人工结果”中填写 `通过` 或 `失败：具体表现`，不要只写“已完成”。

| 步骤 | 操作与必须观察的结果 | 人工结果 |
| ---: | --- | --- |
| 1 | 打开 Creator。确认页面正常加载，且未自行播放声音。 | `未执行` |
| 2 | 导入正式测试工程 `stage7-canary.lmdj`。 | `未执行` |
| 3 | 记录 Project ID、revision、BPM 和 Pad 占用情况。期望值分别为 `00000000-0000-4000-8000-000000000001`、`66`、`120`、64 个 Pad 全部已占用。 | `未执行` |
| 4 | 点击 **Activate Audio**，确认音频成功激活。 | `未执行` |
| 5 | 在 Bank A 中，先用鼠标逐个点击 16 个 Pad，再用实体键盘按 `A S D F G H J K` 和 `Q W E R T Y U I` 逐个触发；逐项确认能听到声音。 | `未执行` |
| 6 | 依次切换到 Bank B、C、D；每个 Bank 抽查 Pad 地址与声音是否对应。 | `未执行` |
| 7 | 点击 **Suspend**，确认停止；然后再次点击 **Activate Audio**，确认可以恢复触发。 | `未执行` |
| 8 | 刷新页面，重新打开同一 Project，再次激活音频。 | `未执行` |
| 9 | 确认没有重复触发、漏触发、按下状态卡住、未激活便自动播放，且 Project ID、revision、BPM 和 64 Pad 数据没有丢失。 | `未执行` |
| 10 | 点击 **Export report** 导出隐私安全验收报告；检查内容后运行 `shasum -a 256 <报告文件>`，把 SHA-256 填入上表。 | `未执行` |

### 必须单独记录的观察结果

| 观察项 | 人工结果 |
| --- | --- |
| Bank A：鼠标逐 Pad 是否听到声音 | `延期 / 未验证` |
| Bank A：实体键盘逐键是否听到声音 | `延期 / 未验证` |
| Bank B/C/D：抽查地址与声音是否对应 | `延期 / 未验证` |
| 是否出现重复触发 | `延期 / 未验证` |
| 是否出现漏触发 | `延期 / 未验证` |
| 是否出现按下状态卡住 | `延期 / 未验证` |
| 显式激活前或刷新后是否自动播放 | `延期 / 未验证` |
| 刷新并重开后 Project ID/revision/BPM/Pad 占用是否保持 | `延期 / 未验证` |
| Suspend 后再次激活是否恢复 | `延期 / 未验证` |
| 是否检查报告并记录 SHA-256 | `延期 / 未验证` |

具名操作人填写并签字前，T1 仍保持开放。完成 T1 也不代表已经取得
Product Build `1.0.18.0` 的 merged-main Proof，亦不授权 push、PR、merge、
tag、Release、部署、发布或 Channel promotion。

## Human canary sheet — withdrawn, do not execute

T1 status: `this run is withdrawn — restart from step 1 on 1.0.19.0`.

The named human operator must fill this sheet from the clean Creator package.
No blank field or automated result may be interpreted as a pass.

| Field | Human result |
| --- | --- |
| Operator | `pending` |
| Execution date/time and timezone | `pending` |
| Browser and exact version | `pending` |
| Device / OS | `pending` |
| Package source revision | `c44517bc7bde30cea4a40a7cab495a081028eb7e` |
| Product Build | `1.0.18.0` |
| Creator host manifest SHA-256 | `9dda47e70d26b53dcd3c7d7460c716c401f6ace7d764669f449786745b8ca367` |
| Formal fixture filename and SHA-256 | `stage7-canary.lmdj` / `d5e17c74777cbf05cef239f79e16cce04ae0e3a380c3c00a93b553a17739aa4c` |
| Privacy-safe acceptance report SHA-256 | `pending / not generated` |
| Human signature / sign-off | `pending` |

### Stage 7 section 13.3 journey

| Step | Required observation | Human result |
| ---: | --- | --- |
| 1 | Open Creator. | `NOT RUN` |
| 2 | Import the formal fixture `.lmdj`. | `NOT RUN` |
| 3 | Observe and record Project ID, revision, BPM, and Pad occupancy. | `NOT RUN` |
| 4 | Activate Audio. | `NOT RUN` |
| 5 | Play all 16 Bank A Pads with Pointer and physical Keyboard. | `NOT RUN` |
| 6 | Switch to Banks B/C/D and sample-check address and sound. | `NOT RUN` |
| 7 | Suspend, then activate again. | `NOT RUN` |
| 8 | Reload, reopen the same Project, then activate again. | `NOT RUN` |
| 9 | Confirm no duplicate or missing trigger, stuck press, autoplay, or Project data loss. | `NOT RUN` |
| 10 | Export the privacy-safe acceptance report and record its SHA-256. | `NOT RUN` |

### Required human observations

| Observation | Human result |
| --- | --- |
| Pointer Bank A heard / not heard per Pad | `deferred / unverified` |
| Physical Keyboard Bank A heard / not heard per Pad | `deferred / unverified` |
| Banks B/C/D sampled address and heard / not heard | `deferred / unverified` |
| Duplicate triggers | `deferred / unverified` |
| Missing triggers | `deferred / unverified` |
| Stuck press state | `deferred / unverified` |
| Autoplay before explicit activation or after reload | `deferred / unverified` |
| Project ID/revision/BPM/occupancy preserved after reload and reopen | `deferred / unverified` |
| Suspend/reactivate recovery | `deferred / unverified` |
| Privacy-safe report reviewed and hash recorded | `deferred / unverified` |

### Explicitly deferred physical rows

| Platform / input | Status |
| --- | --- |
| Physical MIDI controller | `deferred / unverified` |
| Physical Keyboard | `deferred / unverified` |
| Hearing / acoustic output | `deferred / unverified` |
| macOS Safari | `deferred / unverified` |
| iPadOS Safari touch and lifecycle | `deferred / unverified` |

Until a named human fills and signs this sheet, T1 remains open. Even a signed
T1 canary does not by itself establish Product Build `1.0.18.0` merged-main
Proof or authorize a push, PR, merge, tag, Release, deployment, publication, or
Channel promotion.
