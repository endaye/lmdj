"""Pipeline 阶段 3–6（beat/loop/slicer/sequencer/validation），LMDJ-owned。

config/audio_utils/loop_finder/slicer/sequencer/validate 六个模块逐字节迁移自
references/demos/lmdj-song-pipeline/song_pipeline/（demo 保持冻结，只作 parity
基线）。本子包运行在专用 venv（workers/audio/.venv-pfs）中、以子进程调用；
DSP 依赖版本由 workers/audio/config/parity-constraints.txt 锁定（spec §3.1）。
任何行为改动必须先通过 scripts/dev.sh parity（spec §3.2）。
"""
