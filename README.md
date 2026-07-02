# LMDJ

LMDJ 当前包含自动出歌管线，以及围绕 playable patch / web prototype 的草案与 PRD 素材。

## 项目结构

```text
lmdj/
├── lmdj-song-pipeline/      # Python 音频管线与 FastAPI 服务
├── docs/                    # 产品 / 原型 / 跨项目草案
├── AGENTS.md                # Codex 协作说明
└── CLAUDE.md                # Claude Code 协作说明
```

## 文档入口

- [lmdj-song-pipeline/README.md](lmdj-song-pipeline/README.md)：管线快速上手、核心命令、输出格式与架构速览。
- [lmdj-song-pipeline/SETUP_AND_USAGE.md](lmdj-song-pipeline/SETUP_AND_USAGE.md)：完整安装、迁移、调参表和实验脚本说明。
- [docs/lmdj-web-prototype-spec.md](docs/lmdj-web-prototype-spec.md)：2026-07-02 收到的 web prototype PRD 素材，覆盖 prompt 生成、包检查和 MIDI 引导演奏；当前仅作脑暴参考。

## 当前系统

当前可运行实现是 `lmdj-song-pipeline`，主流程是六阶段音频管线：

```text
MusicGen 生成或现成音频
  -> Demucs 分轨
  -> loop 选择
  -> sample 切片
  -> MIDI 谱面生成
  -> 验收与出包
```

输出是面向游戏端的 playable patch 包：

```text
output/{song_id}/
  samples/*.wav
  chart.mid
  lanes.json
  loop_preview.wav
  render_preview.wav
  report.json
```

## 常用命令

所有管线命令都在 `lmdj-song-pipeline/` 内执行：

```bash
cd lmdj-song-pipeline

python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m pytest tests/ -q

.venv/bin/song-pipeline run input.mp3 --song-id mysong --fast
.venv/bin/song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run
.venv/bin/song-pipeline serve --port 8000
```

本地开发默认带 `--fast`，除非明确需要更慢但更准的 `htdemucs_ft`。
