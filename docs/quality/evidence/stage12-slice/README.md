# Slice S1 证据入口与执行记录模板

核定日期 2026-09-22；配套[验收包](../../2026-09-10-stage12-slice-acceptance.md)。
本 README 固定已有输入和证据，不包含伪造的 Windows/S3 运行结果。
S2 [#1167](https://github.com/endaye/lmdj/issues/1167)、
S3 [#1168](https://github.com/endaye/lmdj/issues/1168)、
S4 [#1169](https://github.com/endaye/lmdj/issues/1169)、
S5 [#1170](https://github.com/endaye/lmdj/issues/1170) 分别保留自己的交付。

## 固定源与获取

所有路径相对于仓库根；读取下列固定源，不能静默读取后来的 main：

```text
source_revision = 07044d2950c3ee6ff382468a536d6be87e5cd5d8
tag = lmdj-v1.0.61.0
archive = lmdj-creator-web-4.4.0-product-1.0.61.0.zip
archive_bytes = 2348994
archive_sha256 = 743ec10a965b1288fb59d9b780044e151b878179c0184775192cf27b1eaa5858
```

[下载 ZIP](https://github.com/endaye/lmdj/releases/download/lmdj-v1.0.61.0/lmdj-creator-web-4.4.0-product-1.0.61.0.zip)、
[checksum](https://github.com/endaye/lmdj/releases/download/lmdj-v1.0.61.0/lmdj-creator-web-4.4.0-product-1.0.61.0.zip.sha256)、
[detached signature](https://github.com/endaye/lmdj/releases/download/lmdj-v1.0.61.0/lmdj-creator-web-4.4.0-product-1.0.61.0.zip.sha256.asc)。
在 Windows PowerShell 保存全部文件后检查：

```powershell
$archive = '.\lmdj-creator-web-4.4.0-product-1.0.61.0.zip'
(Get-Item $archive).Length
(Get-FileHash $archive -Algorithm SHA256).Hash.ToLower()
Expand-Archive -Path $archive -DestinationPath .\slice-1.0.61.0
Get-Content .\slice-1.0.61.0\dist\host-manifest.json
```

先比较上面两个固定值，失败则停止；不要仅比较两个一起下载的可变文件。
维护者使用 `scripts/release.sh audit --remote --tag lmdj-v1.0.61.0` 核查完整签名链。
source binding 来自 release plan/tag，不从没有 revision 字段的 host-manifest 猜出。

在该精确 source 的只读检出中，使用已有服务端（Python 3.11；本步骤不构建新包）：

```powershell
python tools/web-runtime/serve_distribution.py --root C:\slice-1.0.61.0\dist --verifier apps/creator-web/tools/package.py --repo-root . --port 4175
```

把 `C:\slice-1.0.61.0\dist` 换成实际解压路径；打开 Windows 浏览器
`http://127.0.0.1:4175/index.html`。仓库和服务路径按实际环境记录。
不得以普通无隔离头静态 server 或 file:// 打开失败来断言 Slice 算法失败。
若包 verifier、平台能力或服务入口拒绝，原样记录 BLOCKED，不绕过。
WSL 可提供同一只读包，但 Windows 浏览器 OS 与 WSL OS 必须分别留证。

### 准备非空 Pattern 基线及读取证据

复用候选的 `tests/platform/web/creator/fixtures/make_candidate_fixture.py`，
以该 source 构建的原生 `build/core/dev/bin/lmdj-core` 和同源 Assembly 为输入。
操作者先设置一个新的绝对 `RUN_DIR`；原生 CLI 可在 Linux/macOS/WSL 准备，
生成环境不是 Windows 浏览器执行环境。没有同源 CLI 时先按 `scripts/core.sh
configure dev` / `scripts/core.sh build dev` 准备并保留构建日志，不给二进制虚填 source。

```bash
python3 tests/platform/web/creator/fixtures/make_candidate_fixture.py \
  "$PWD/build/core/dev/bin/lmdj-core" "$PWD/products/lmdj/assembly.json" \
  "$RUN_DIR/creator-candidate-proof-bundle.lmdj"
```

这是已有生成器的使用说明，S1 没有生成/提交新 fixture。运行后记录输出包及 CLI
的 hash/length、完整 source 和退出码；将包交给 Windows 的 `Import .lmdj`。
generator 合成素材沿用仓库 LICENSE，CC0 声明只用于下一节的 smoke WAV。

Windows Chromium DevTools 可在每个观察点运行以下只读代码，将控制台 `copy`
结果保存为该 leg 的 JSON 证据。它通过公开 Host 查询 Project，并读取当前 Project
的 OPFS 文件；不会更改 Project 或模拟结果。使用小型测试 Project，包含原始 bytes
的输出可能较大。若查询失败，保留错误并按 F02 的故障取证方式处理，不能填造 P。

```javascript
const observed = await window.lmdjWebRuntimeHost.transport.send({
  protocol_version: 1, request_id: crypto.randomUUID(),
  operation: 'project.inspect', payload: {}
});
if (!observed.ok) throw new Error(JSON.stringify(observed));
const projectId = observed.result.project.project_id;
const savedFiles = [];
async function collect(directory, prefix = '') {
  for await (const [name, handle] of directory.entries()) {
    const path = `${prefix}/${name}`;
    if (handle.kind === 'directory') { await collect(handle, path); continue; }
    if (!path.includes(`${projectId}.lmdj/`)) continue;
    const bytes = new Uint8Array(await (await handle.getFile()).arrayBuffer());
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    savedFiles.push({path, byte_length: bytes.length,
      sha256: Array.from(hash, b => b.toString(16).padStart(2, '0')).join(''),
      bytes: Array.from(bytes)});
  }
}
await collect(await navigator.storage.getDirectory());
if (!savedFiles.length) throw new Error('No persisted Project files observed');
copy(JSON.stringify({utc: new Date().toISOString(), inspection: observed, savedFiles}));
```

每次可在新的控制台块作用域 `{ ... }` 内运行以免重声明常量。
Job 另用公开 `window.lmdjWebRuntimeHost.candidates.inspectCandidateJob(jobId)` 查询；
`jobId` 从实际请求/结果保存，不猜 Attempt/Set ID。截图/录屏保留按钮和立即听感，
JSON 留完整 Truth/文件/lineage；两者不能互相代替。

## 合法素材与身份

复用候选中已提交的
[smoke manifest](../../../../tests/fixtures/provider-benchmark/sample-slice/manifest.json)、
[CC0 范围声明](../../../../tests/fixtures/provider-benchmark/sample-slice/LICENSE.md) 和
[生成器](../../../../tools/provider-benchmark/generate_sample_slice_smoke.py)。
CC0 只覆盖该目录生成的 WAV 与 manifest；不覆盖 generator、测试代码或全仓库。
无需第三方音频、下载模型或付费服务。用户录音等额外素材先核实授权和 public 分类，
S3 扩展素材必须有独立真值与 License，不能混入旧 smoke 集改写基准。

manifest SHA-256：`33d06cfe36df2d840aae168908c59be6747753d2c7e3b6fac56b4c6f1f13f5a5`，
3,910 bytes。下表路径前缀均为 `tests/fixtures/provider-benchmark/sample-slice/`。

| 文件 / 场景 | bytes | SHA-256 | 预定结果/标签 |
| --- | --- | --- | --- |
| `slice-basic.wav` | 33644 | `098d33f84f35c3451b35b24fb4957414006e3af87eb4db969db2771cfe89d705` | 48 kHz mono；onsets 2400,7200,12000；tolerance 480 frames |
| `slice-close-overlap.wav` | 9644 | `1395612844ca144ed97cef2df548e0fd12e44c6a7b0a585bc7f64b1f465151fc` | 48 kHz mono；onsets 480,1440；tolerance 240；历史第二 onset 漏检仍保留 |
| `slice-silence.wav` | 9644 | `639dad0ac2923f5fe9e9ccfb99aa9b3084048e2e53317d1903e6e899a4f6296a` | 48 kHz mono；零 onset，零 recipes；tolerance 480 |
| `slice-truncated.wav` | 4780 | `bbbb089b939ea14999a727498235c0407fa0908f454a6aebeb8fec301a3ccd3f` | `source_audio_unsupported` |
| `slice-bad-header.wav` | 9644 | `613fb2b5a8f1025444dc48d675a58afd2d0bdf8b31d48b3f8a388541fa525b6c` | `source_audio_unsupported` |
| `missing_input` | N/A | N/A | 不存在的输入；`input_artifact_unavailable`，不能伪造空文件 hash |

畸形 WAV 可能在 Creator 导入时先被拒绝，记录实际拒绝层；只有 Provider companion
确实走到 execute 才能声称对应 Provider 终态。导入后的 Project WAV 必须重新校验
完整 ArtifactRef/bytes，禁止默认它与磁盘素材字节相同。

## 既有证据索引

核查时从 GitHub ClosedEvent 读取如下 K/L 合入关系；每个 SHA 对固定 source 的
`git merge-base --is-ancestor` 均返回 0。

| Task | PR | merged SHA |
| --- | --- | --- |
| K1 #1033 | #1049 | `101ac6f8b4d588747aaa7939caf9d70f252e0a44` |
| K2 #1034 | #1075 | `692ac4837ce79c9681fed81d06eedfac9ee84f5c` |
| K3 #1035 | #1079 | `bb99f11982450f77ca7f2309776197482690cfa8` |
| K4 #1036 | #1084 | `77e8170aa9ce246d92d44d9d0a983694c3016327` |
| K5 #1037 | #1091 | `16dd0353a1eea5867dff2f07d8f4b6bffe6ec49d` |
| L1 #1038 | #1113 | `c68790864970f46acaf7dd3fd532a580c0170668` |
| L2 #1039 | #1141 | `de1b9fca6ceb0d6fdd9b1a6010e2487b356ec5fb` |
| L3 #1040 | #1126 | `de78b1e35767a172bb27a2b6df1c89c07052e444` |
| L4 #1041 | #1143 | `01d9f5052d4b46da5f1e823d4883dea9ab3fd1d7` |
| L5 #1042 | #1147 | `7fda486349445f8a15aecde7c82743fc1e87b13e` |

- [候选 Core Ubuntu 原始 job](https://github.com/endaye/lmdj/actions/runs/35564190757/job/106229286312)：
  208/208，具体适用测试见验收包；这是历史实际运行，S1 只重新读取证据。
- [候选 Creator 原始 job](https://github.com/endaye/lmdj/actions/runs/35564190757/job/106228094309)：
  Linux Chromium Slice UI 8 + Candidate Runtime 6；保留各组 skipped 数，未执行 Windows。
- [K3 原始研究摘要](../../2026-09-09-stage12-k3-reference-results.md)：历史质量观察，
  无 exact-run SHA/raw scorer 绑定，不能填充本候选 S3 结果。
- 固定候选上 `apps/creator-web/test/candidate_surface.test.tsx` 的 unknown adoption
  测试为 mock；Core recovery 是独立进程测试；二者不是 Windows 网络故障/断电验收。

Actions 日志有保留期。S2/S3 执行时下载原始日志/报告、记录 digest/length 与获取时间，
保存在该任务批准的证据位置；若过期则标 MISSING，不能从本索引重构成原始日志。
本次本地原始读取材料位于 `/tmp/lmdj-1166-evidence/`，仅是本次审查工作目录，
不把临时绝对路径当作永久可用证据。后续路径须先按 S2/S3 声明清单登记。

| 本次下载的原始 job log（未剥除 ANSI） | bytes | SHA-256 |
| --- | --- | --- |
| `creator-ci.raw.log` | 214293 | `85d61ddd682c456c7205eff90f38503523687901afc543a8cbe5cd32fe9b263d` |
| `core-ci.raw.log` | 150708 | `0f8629f1131f0f2912c38066809800673aa3b28d43e0b1cc7cb9fb96929a93c8` |

本地签名核对使用仓库 `tools.release.web_host_bundle` 的
`parse_detached_checksum` / `verify_detached_checksum_signature`，临时隔离 keyring，
canonical public key `.github/release-signing-keys/lmdj-release-checksum.asc`，
固定 fingerprint `CB928A6E89DE498851688EF1AAC3E7019FC1478B`：PASS。
此结果只覆盖已下载的 Creator ZIP/checksum/signature，不替代完整 remote audit。
素材核对同时读取候选 Git LFS pointer 的 oid/size 与实际展开 WAV 的 hash/length，
5/5 PASS；直接对 `git show` 的 LFS pointer 哈希不能当作 WAV 哈希。

完整只读 `scripts/release.sh audit --remote --tag lmdj-v1.0.61.0`：
首次 `2026-09-22T06:32:26Z` 返回 1，`external-error` / `github-assets`
下载不可用；原始失败保留于 `release-audit.log`。第二次
`2026-09-22T06:41:41Z` 返回 0，`remote tag, Release metadata, CI and asset
profile match canonical intent`，原始输出 `release-audit-v2.log`。
未执行 release mutation。remote tag object 为
`95fbb3d4756d4f0c20112dcb376ad01ab8a227f7`，peeled SHA 与固定 source 一致。

S1 文档验证：10 个 Markdown 相对文件链接有效；`scripts/docs-site.sh check`
返回 0（170 tests passed、0 failed/0 skipped，48 routes/internal links valid）；
新增文件暂存后 `python3 tests/build/ci_change_scope_test.py` 返回 0（75 tests）。
这些结果验证文档和路径归属，不补填上面的 Windows 或 S3 NOT_RUN。

## S3 复现入口（待执行，不是结果）

在固定 source 构建出的真实执行文件上使用现有 K3/B2 接口；输出位置须是本次新目录，
下列 `RUN_DIR` 由操作者指定，不能覆盖历史失败。

```bash
build/core/dev/bin/lmdj_provider_sample_slice_tests "$RUN_DIR/predictions-1.json"
build/core/dev/bin/lmdj_provider_sample_slice_tests "$RUN_DIR/predictions-2.json"
python3 tools/provider-benchmark/score_slice.py \
  --manifest tests/fixtures/provider-benchmark/sample-slice/manifest.json \
  --predictions "$RUN_DIR/predictions-1.json"
python3 tools/provider-benchmark/validate_report.py "$RUN_DIR/report.json" --require-measured
```

scorer 两次分别运行并留原始输出/退出码；按完整输出 Artifact 的原始字节比较确定性。
`report.json` 只能由真实记录依现有 schema 整理，不由这段模板伪造。
上述二进制出口不提供完整代表性 corpus/elapsed collector；S3 实施前先补足精确文件
清单和真实执行/计时入口。不得把命令里的输出文件名当作已存在的测量。
参考[报告与执行区规则](../../../../tools/provider-benchmark/README.md)。

## S2/S3 结果记录模板

复制模板到对应任务的新报告，运行前填身份；运行后只按原始证据填结果。
状态只选 `PASS / FAIL / BLOCKED / NOT_RUN / EXPECTED_FAILURE / UNKNOWN / N/A`。
预期的拒绝断言确实执行且正确可以 PASS；runner xfail/expected failure 必须单列，
它后面的未执行腿仍 NOT_RUN。N/A 必须说明适用性理由，不能代替困难的必验腿。

```text
run_id / UTC / operator:
report source revision / harness revision:
candidate source revision / Build / Provider / Capability / parameters bytes+hash:
archive name / sha256 / bytes / release URL / manifest evidence:
snapshot metadata source / introducing revision / witness:
OS build / browser version / CPU / RAM / output device / sample rate:
origin / browser profile / capability preflight evidence:
WSL or build environment separately (if any):
input license / disk sha256+bytes / Project Asset ID+ArtifactRef:
P0 inspection / r0 / source bytes evidence / all Pattern objects+events:
job_id / attempt_id / active_set_id / terminal output sha256+bytes:
recipes / targets / command_id / expected_revision:
adopted Asset IDs / full ArtifactRefs / full lineage / saved-file identities:
raw commands / start-end time / exit codes / recording and log paths+hashes:
discovered / executed / passed / failed / expected-failure / skipped / not-run:
quality TP/FP/FN / precision/recall/F1 by case / elapsed / RTF:
resource statuses (not_enforceable / not_applicable / missing; never fake zero):
pending product thresholds / no production verdict:
defect reproduction / existing Issue or new deduplicated owner / retest run:
```

| Leg | 操作前 evidence | 操作与立即 far-side evidence | 重开后 evidence（适用时） | 自动化/手工/听感与平台 | 结果/缺口 |
| --- | --- | --- | --- | --- | --- |
| W01–W12（每个 ID 一行） | 待填 | 待填 | 待填 | Windows 待执行 | NOT_RUN |
| F01–F12（每个 ID 一行） | 待填 | 待填 | 待填 | 各 companion 与 Windows 分列 | NOT_RUN |

每个 source/output/saved Artifact 都记录 `{sha256, byte_length, media_type}` 并读取
实际字节复核。Pattern 比较完整对象和事件，不仅事件数；lineage 对照验收包完整字段。
人工听感另留 “听到了什么/何时停止/哪些缺陷”，`played=true` 只算回执。
最后由 S4 按预先口径裁定用途和平台；S1 完成不核销 S2–S5 或 Stage 12 总追踪。
