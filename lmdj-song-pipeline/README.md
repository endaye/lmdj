# LMDJ song-pipeline

自动出歌管线：从一段成品音乐全自动产出「≤6 个 samples + MIDI 谱面」，
对应 lmdj-pad-rhythm 的输入格式（`sample-map` + `chart.mid`）。

实现了 **阶段 1–6 + 服务化**：

```
generate.py         MusicGen 生成，prompt 模板固定 BPM + 风格（本地 CPU 用 small）
  ↓ 整曲音频
  → stems.py        Demucs 分轨 (drums / bass / melody)
  → loop_finder.py  beat/downbeat 检测 + 4小节候选窗口打分 + crossfade 无缝化
  → slicer.py       鼓 onset→KMeans 聚 kick/snare/hat（质量差自动降 2 键位）；
                    贝斯/旋律按小节切 phrase，自相似度选 1-2 段长样本
  → sequencer.py    onset/互相关 → 16分网格量化 → chart.mid + lanes.json
  → validate.py     MIDI+samples 重渲染，log-mel 相似度打分，
                    不达标自动换候选窗口重试
```

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

需要系统 ffmpeg（`brew install ffmpeg`）。

## 用法

```bash
# 单曲（--fast 用 htdemucs 单模型分轨，比默认 htdemucs_ft 快 4 倍）
song-pipeline run input.mp3 --song-id mysong --fast

# 批量模式：跑目录下所有音频，输出合格率报告 batch_report.json
song-pipeline batch ./lofi_pack --fast

# FastAPI 服务
song-pipeline serve --port 8000

# 阶段1：生成一首 85bpm lofi 并直接串全管线（BPM 自动作为 bpm_hint）
song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run
```

API：

```bash
curl -F file=@input.mp3 http://localhost:8000/songs        # → {"song_id": ...}
curl http://localhost:8000/songs/{song_id}                 # 状态/report
curl -O http://localhost:8000/songs/{song_id}/package      # 谱面包 zip
```

## 输出格式

```
output/{song_id}/
├── samples/*.wav        # ≤6 个：kick/snare/hat(+降级drum_low/high) + bass + melody_a/b
├── chart.mid            # 16分音符量化谱面，pitch 对齐 lane 约定
├── lanes.json           # pitch ↔ wav ↔ 键位 三方映射 + bpm/loop 元数据
├── loop_preview.wav     # 切出的原 loop（听感对照用）
├── render_preview.wav   # MIDI+samples 重渲染（验收听感）
└── report.json          # 分数 / 重试记录 / 耗时
```

lane pitch 约定（`config.PipelineConfig.lane_pitches`，可改）：
kick=36 snare=38 hat=42 bass=48 melody_a=50 melody_b=52；降级 2 键位时 drum_low=36 drum_high=42。

## 关键配置（song_pipeline/config.py）

- `bpm_hint`：生成端 prompt 固定了 BPM 时直接传入，跳过倍频纠错
- `similarity_threshold`：验收阈值（默认 0.50），不达标自动换窗口重试
- `vocals_strategy`：vocals 并进旋律轨（merge）或丢弃（drop）
- `demucs_model`：默认 htdemucs_ft；本地调试建议 CLI `--fast`
- `SONG_PIPELINE_DEVICE` 环境变量可强制 demucs 设备（cuda/cpu）

## 测试

```bash
# 合成 90bpm 测试曲（预置 stems 缓存，跳过 demucs，秒级跑通阶段 3-6）
.venv/bin/python scripts/make_test_song.py output/testsong
.venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong
```
