# LMDJ

LMDJ 当前是一个脑暴与 PRD 快速迭代工作区。这里先沉淀素材、问题、决策和工作版 PRD，再逐步收敛到可执行方案。

## 项目结构

```text
lmdj/
├── docs/                    # PRD 迭代、素材、决策与开放问题
├── lmdj-song-pipeline/      # 高嘉丰提供的参考项目和技术素材库
├── AGENTS.md                # Codex 协作说明
└── CLAUDE.md                # Claude Code 协作说明
```

## 文档入口

- [docs/README.md](docs/README.md)：文档系统总览与脑暴阶段工作流。
- [docs/prd/working-prd.md](docs/prd/working-prd.md)：当前工作版 PRD，允许快速改写。
- [docs/prd/source-materials.md](docs/prd/source-materials.md)：外部输入、demo、参考资料和素材索引。
- [docs/prd/open-questions.md](docs/prd/open-questions.md)：待讨论问题池。
- [docs/prd/decision-log.md](docs/prd/decision-log.md)：已经确认的产品/技术决策。
- [lmdj-song-pipeline/README.md](lmdj-song-pipeline/README.md)：高嘉丰 demo 工具的快速上手和接口说明。

## 当前定位

`lmdj-song-pipeline` 是高嘉丰给到的可运行参考项目和技术素材库，不等同于 LMDJ 最终系统，也不默认作为最终代码边界。它现在的价值是帮助我们理解“音频输入 -> samples + chart.mid + lanes.json”的可能链路，并为后续 Audio Worker、Patchify adapter 和技术方案提供参考。

```text
PRD 素材
  -> 工作版 PRD
  -> 开放问题
  -> 决策记录
  -> 原型 / 技术验证
```

## 脑暴阶段原则

- 素材不等于定稿：高嘉丰 PRD、demo 工具、外部参考都先进入素材池。
- 工作版 PRD 可以频繁变化：先保证观点清楚，再追求完整。
- 决策单独记录：一旦确认，就写进 decision log，避免反复讨论。
- 问题显式管理：未定问题进入 open questions，不在正文里含糊带过。

## Demo 工具常用命令

需要跑高嘉丰 demo 时，在 `lmdj-song-pipeline/` 内执行：

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
