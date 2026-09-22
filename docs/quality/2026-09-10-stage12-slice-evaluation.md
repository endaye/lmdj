# Stage 12A Slice S3 质量与耗时评测

评测日期：2026-09-23（Asia/Shanghai）；原始 UTC `2026-09-22T16:37:04.591921+00:00`。
S3 [#1168](https://github.com/endaye/lmdj/issues/1168) 按 [S1 固定口径](2026-09-10-stage12-slice-acceptance.md) 完成限定评测。
11 个扩展合成用例 TP/FP/FN=23/0/5，precision=1、recall=23/28、F1=46/51；
既有 smoke 为 4/0/1，precision=1、recall=0.8、F1=8/9。漏检全部保留，未改标签、容差或算法。
本结果仅 `observation_only`，不授予生产资格；Windows 听感 S2 与产品裁定 S4 独立。

## 固定身份与方法

- 候选源 `07044d2950c3ee6ff382468a536d6be87e5cd5d8`；Product Build `1.0.61.0`、Provider `local.sample.slice` `1.0.2`、SDK `2.2.0`、Capability `sample.slice.v1` `1.0.0`，来自该候选 manifest。模型为 null。
- source-package SHA-256 `b3342abaab4673c2ab7060ef4c3d2d0c4ba7d8d5205efb927ecdb6af4b4f0407`；这是源包清单身份，非 Creator 分发 ZIP 或可执行文件身份。
- 原生 executable SHA-256 `af557736c05637dea3f9e835873789836bbb63c9d4e8fe44b093c5ce254adb5e`，806544 bytes。本轮直接构建固定 source 的 Provider/SDK/Foundation，未执行 Creator ZIP。
- harness 基线 `2e24cacff4e4470d1f08510b987570762ea77dd8` 加 `measured.json.frozen_inputs` 中每个 source/manifest/WAV 的 SHA-256 与 byte_length 构成实际实现身份；新 harness 当时是未提交 overlay，报告内 revision 字段不可单独冒充完整 harness 提交。
- 环境：Darwin 27.0.0、arm64、Apple M1、17179869184 bytes RAM；Python 3.11.15、CMake 4.4.3、Apple clang 21.0.0；Release 构建，无 accelerator。assembly lock digest `47d5be5993fddb94f27ca40badd7770993d19df728cb1d0985c6b8fd681f8a8c`。
- 参数 `{}`；候选源码默认 threshold_pcm16=4096、refractory_frames=240。真实 Registry 选择及授权：public/test/local、sample.slice.execute。
- 每例两次真实 `AttemptStore.execute`；每次 reopen 核对终态、输出完整 digest/length/schema，失败无 candidate/minted output，staging budget 释放。14 个成功用例双跑输出字节严格相等；3 个输入失败用例两次均拒绝。
- steady_clock 只包围 execute，含输入认证、Provider 计算、输出验证和持久化；不含编译、素材读取、Registry setup、reopen 或 scorer。无 warmup；主报告使用首跑，两次原值均留存。RTF=elapsed/(frames/sample_rate)，输入拒绝无 RTF。

## 语料与独立真值

扩展 [manifest](../../tests/fixtures/provider-benchmark/sample-slice-evaluation/manifest.json) 在执行前冻结；
其 digest `89d1d0d2f59f74c60ec50711e980424c0de83a96d0a0066281e89263d08862ff`。
整数 PCM16 square-carrier/linear-tail 脉冲由作者给定时间表构造，不从检测输出生成标签。
11 份 WAV 各 4800 frames：48 kHz 为 100 ms，44.1 kHz 约 108.84 ms；
力度 peak=4095/4096/24000，tail=720/1920，密集间隔=239/240 frames。
右声道专用脉冲的左声道全零；包括单声道、双声道、44.1/48 kHz 和双声道静音。
扩展 tolerance=0，smoke 480/240/480 原样保留。
[CC0 声明](../../tests/fixtures/provider-benchmark/sample-slice-evaluation/LICENSE.md) 仅适用于生成 WAV 与 manifest，代码/文档保留根 License；无下载录音或第三方素材。
这些短构造信号覆盖指定因素，不能代表用户音乐的统计分布，也没有物理听音。

## 逐用例计分与耗时

时间单位 ms；RTF 为 ratio；N/A 表示分母为零或不适用，不填作 0/pass。所有值来自真实输出，
显示值四舍五入；完整原值、预测 frames、匹配对、输出字节/digest/length 在测量记录中。

| 语料 / 用例 | TP/FP/FN | precision | recall | F1 | elapsed 1 / 2 (ms) | RTF 1 / 2 |
| --- | --- | --- | --- | --- | --- | --- |
| smoke / basic_three_onsets | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 2.590916 / 3.106875 | 0.007403 / 0.008877 |
| smoke / close_overlapping_tails | 1/0/1 | 1.000000 | 0.500000 | 0.666667 | 2.104750 / 1.995250 | 0.021047 / 0.019952 |
| smoke / silence | 0/0/0 | N/A | N/A | N/A | 2.020375 / 2.079459 | 0.020204 / 0.020795 |
| smoke / missing_input | N/A（拒绝） | N/A | N/A | N/A | 1.305625 / 1.289958 | N/A / N/A |
| smoke / truncated_data | N/A（拒绝） | N/A | N/A | N/A | 1.503708 / 1.322625 | N/A / N/A |
| smoke / bad_riff_header | N/A（拒绝） | N/A | N/A | N/A | 1.334750 / 1.202625 | N/A / N/A |
| 扩展 / velocity-below | 0/0/3 | N/A | 0.000000 | 0.000000 | 1.285250 / 1.272875 | 0.012852 / 0.012729 |
| 扩展 / velocity-at | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.513166 / 1.481625 | 0.015132 / 0.014816 |
| 扩展 / velocity-high | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.246459 / 1.236459 | 0.012465 / 0.012365 |
| 扩展 / tail-separated | 2/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.108542 / 1.154709 | 0.011085 / 0.011547 |
| 扩展 / tail-overlap | 1/0/1 | 1.000000 | 0.500000 | 0.666667 | 1.338209 / 1.306459 | 0.013382 / 0.013065 |
| 扩展 / dense-below | 2/0/1 | 1.000000 | 0.666667 | 0.800000 | 1.217292 / 1.183292 | 0.012173 / 0.011833 |
| 扩展 / dense-at | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.154208 / 1.318083 | 0.011542 / 0.013181 |
| 扩展 / mono-44100 | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.830875 / 1.387625 | 0.016821 / 0.012749 |
| 扩展 / stereo-right-44100 | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.304458 / 1.453625 | 0.011985 / 0.013355 |
| 扩展 / stereo-right-48000 | 3/0/0 | 1.000000 | 1.000000 | 1.000000 | 1.421083 / 1.403667 | 0.014211 / 0.014037 |
| 扩展 / silence-stereo | 0/0/0 | N/A | N/A | N/A | 1.418584 / 1.404250 | 0.014186 / 0.014042 |

低于阈值的三个 onset 全部漏检；overlap 第二 onset 漏检；239-frame 间隔漏掉中间 onset，240-frame 对照均检出。
没有通过删标签、放宽 tolerance 或调默认参数消除这些结果。smoke overlap 的既有漏检仍存在。
静音为空 points，两个静音用例 precision/recall/F1 均 N/A；低力度无预测时 precision N/A、recall/F1=0。
输入失败：missing_input=`input_artifact_unavailable`；truncated_data/bad_riff_header=`source_audio_unsupported`，每例两次均 failed、无输出。

## 资源与资格边界

执行区域 `in_process_reference`。独立 process-tree RSS/GPU 均 `not_enforceable`/null；
sampler/deadline/kill_grace 均 `not_applicable`。本工具没有硬 timeout、进程隔离或资源强制保证。
elapsed 和 RTF 只是本机两次短输入观察，不能推出尾延迟、Windows/Web 性能或生产上限。
没有质量资格阈值，不把低 recall 换成 schema/resource rejection；已确认的确定性、schema、refusal 检查全部通过。
本轮 17 个 report cases 均 observation_only、无 invariant rejection，不等于无质量问题或 production accepted。
按 S1 预定口径，产品阈值、听感和是否 reference-only/no-go 交由 S4，不在看过结果后追设过线阈值。

## 保留证据与复现

[measured.json](evidence/stage12-slice/evaluation/measured.json) SHA-256 `847cf2f3abbabda9580658ec606d6489efef9771dbada1cecdee8116b5445e95`，102451 bytes。
包含执行前 frozen-inputs、候选 manifests/source-package、编译器与 executable 身份、8 个子命令的 argv/cwd/exit_code、
原始 stdout/stderr、两次 execute 输出、预测、scorer 和 validator 报告。全部子命令 exit 0。
本地原始 build/AttemptStore 仍在 `.local/slice-evaluation-r4/`；该目录不提交，持久化输出已与记录逐字节核对。
早期调试运行 r1–r3 保留在本地，未把它们改写为最终测量或合并择优；r4 是最终 frozen harness 的完整运行。

```bash
python3 tools/provider-benchmark/generate_sample_slice_evaluation.py --check
python3 tools/provider-benchmark/tests/sample_slice_evaluation_test.py
python3 tools/provider-benchmark/tests/report_test.py
python3 tools/provider-benchmark/tests/score_slice_test.py
python3 tools/provider-benchmark/run_sample_slice_evaluation.py \
  --candidate-source /absolute/clean/checkout-of-07044d2950c3ee6ff382468a536d6be87e5cd5d8 \
  --output-dir /absolute/new/evaluation-run
```

收集器拒绝已有 output 目录及不匹配/dirty 的候选；执行前后校验冻结输入。复跑质量/输出字节应一致，计时不要求相等。
当前验证：generator/collector 15 tests、report 83 tests、scorer 6 tests 全通过，0 skipped；
CTest 的 4 个 provider corpus/benchmark 入口全部通过；measured reports 重验证、原始日志摘要、
持久化输出字节、重新计分与报告重建均一致。新增 staged 路径 ownership 75 tests 全通过；
`scripts/docs-site.sh check` exit 0，170 tests、48 routes 与内部链接通过（不是产品验收）。

## Version Management

Version impact: none。仅评测工具、合成素材与保留证据；未改 Product/Assembly/Module/Provider/Contract 身份。

## Documentation Impact

Documentation impact: none。本报告记录限定评测，未改变当前 Portal 的产品源码事实/可用性；S5 继续负责最终对齐。
Pitfall impact: none。未发现新的非代码过程缺陷。
