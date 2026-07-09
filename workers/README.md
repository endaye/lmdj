# workers/

正式云端异步 worker 放在这里。

当前规划：

- `workers/audio/`：上传歌曲后的分轨、loop finding、切片、sequencing、validation 和 Patchify 调用。
- `workers/generation/`：从 idea / creative brief 生成音乐材料，后续接入 Audio Worker 或 Patchify。
- `workers/render/`：导出 song audio、share video、cover、preview clip 等传播资产。

约束：

- Worker 和 `apps/api/` 分开部署或至少分开进程运行。
- Worker 可以参考 `references/demos/lmdj-song-pipeline/` 的算法和 fixtures，但正式实现应沉淀到 `workers/` 或 `packages/`。
- 第一版优先保证 `Audio Worker -> packages/patchify -> patch.json` 的端到端链路。

## Audio Worker 本地验证

```bash
cd workers/audio
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q
```

真实端到端（需先 `scripts/dev.sh setup-demo`）：

```bash
.venv/bin/lmdj-audio-worker run /path/to/song.mp3
.venv/bin/lmdj-audio-worker status <job_id>
```
