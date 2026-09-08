# LMDJ Song Pipeline

这是高嘉丰提供的 demo 工具，用来验证“成品音乐或 MusicGen 生成音频 -> playable patch 包”的技术链路。它现在位于 `demos/` 下，是后续 LMDJ 系统的参考资产和技术素材库，不是最终产品架构或正式源码边界。

它当前可以把一段音频转换成：

```text
samples/*.wav + chart.mid + lanes.json
```

完整安装、迁移、调参和脚本说明见 [SETUP_AND_USAGE.md](SETUP_AND_USAGE.md)。这份 README 只保留日常开发最常用的入口。

## 安装

需要 Python 3.10+ 和系统 `ffmpeg`。

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

# 可选：MusicGen 生成支持
.venv/bin/pip install -e ".[generate]"

# 可选：yt-dlp Python 包
.venv/bin/pip install -e ".[fetch]"
```

`numpy` 固定在 2 以下是为了兼容 demucs/numba，不要随意升级。

## 常用命令

```bash
# 单曲管线。本地开发建议带 --fast。
.venv/bin/song-pipeline run input.mp3 --song-id mysong --fast

# MusicGen 生成 30 秒素材，然后串完整管线。
.venv/bin/song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run

# 批量处理目录，输出 output/batch_report.json。
.venv/bin/song-pipeline batch ./lofi_pack --fast

# 启动 FastAPI 服务。
.venv/bin/song-pipeline serve --port 8000
```

`serve` 启动后的 API：

```bash
curl -F file=@input.mp3 http://localhost:8000/songs
curl http://localhost:8000/songs/{song_id}
curl -O http://localhost:8000/songs/{song_id}/package
```

## 验证

```bash
.venv/bin/python -m pytest tests/ -q

# 重新生成带 stems 缓存的 90bpm 合成测试素材。
.venv/bin/python scripts/make_test_song.py output/testsong
.venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong --fast
```

## 管线阶段

```text
generate.py     可选 MusicGen 素材生成
stems.py        Demucs 分出 drums / bass / melody
loop_finder.py  beat/downbeat 检测与候选 loop 打分
slicer.py       鼓 one-shot 与 bass/melody 长样本切片
sequencer.py    16 分网格 MIDI 谱面与 lanes.json
validate.py     重渲染 preview 与 log-mel 相似度打分
```

`pipeline.py` 有两个入口：

- `run_pipeline`：标准 MPC-style 包，包含 kick/snare/hat 与 bass/melody 样本。
- `run_pipeline_abc`：`--abc` 模式，切 A/B/C loops 并生成 A-A-A-BC 谱面。

## 输出格式

```text
output/{song_id}/
├── samples/*.wav
├── chart.mid
├── lanes.json
├── loop_preview.wav
├── render_preview.wav
└── report.json
```

`lanes.json` 是游戏端读取 pitch、sample、lane、kind 的唯一可信来源。不要从文件名推断 lane 顺序。

默认 pitch 映射定义在 `song_pipeline/config.py`：

```text
kick=36, snare=38, hat=42
drum_low=36, drum_high=42
bass=48, melody_a=50, melody_b=52
loop_a/b/c=60/62/64
loop_d/e/f=65/67/69
loop_g/h/i=71/72/74
loop_j/k/l=76/77/79
```

修改 `PipelineConfig.lane_pitches` 会改变游戏端输出格式。

## 关键调参点

- `song_pipeline/config.py` 里的 `PipelineConfig` 是调参唯一入口。
- `bpm_hint` 用于生成端已固定 BPM 的情况，会跳过 BPM 倍频纠错。
- `similarity_threshold` 默认 `0.50`；低于阈值的结果写成 `rejected`，不是程序崩溃。
- `SONG_PIPELINE_DEVICE` 可强制 demucs 使用 `cuda`、`cpu` 或 `mps`。
- `--fast` 会把模型从 `htdemucs_ft` 切到 `htdemucs`。

## 扩展脚本

实验性的 playing-style 脚本在 `scripts/`，详细参数见 [SETUP_AND_USAGE.md](SETUP_AND_USAGE.md)：

- `make_def_package.py`：DEF multi-loop 包，自动避让已切窗口。
- `render_drumvar.py`：鼓变奏重渲染。
- `render_drumswap.py`：鼓 one-shot 替换。
- `rerender_boombap.py`：boom-bap pattern 重渲染。
