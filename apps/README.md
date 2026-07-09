# apps/

正式产品应用入口放在这里。

当前规划：

- `apps/web/`：LMDJ Web App。负责 idea input、song upload、job progress、Patch View、render/share/remix 入口。已落地：Patch View 工作台原型（消费 `patch.json`，见 `apps/web/README.md`）。
- `apps/api/`：LMDJ App Backend。早期建议是模块化 monolith，对 Web 和 CLI 暴露同一套产品 API。

约束：

- 不从 `references/demos/` 继承目录结构或 API 形态。
- Web / CLI / API 共享 LMDJ 自己的 `Project / Patch / Pad / Scene / Element` 产品对象。
- 音频、生成、渲染重任务不在 Web 或同步 API request 中执行。

## App API 本地验证

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify -e ../../workers/audio
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q
```

真实端到端（需先 `scripts/dev.sh setup-demo`）：

```bash
.venv/bin/uvicorn lmdj_api.app:app --port 8000
# 另一个终端：
curl -F file=@song.wav localhost:8000/uploads          # → {"job_id":"...","state":"queued"}
curl localhost:8000/jobs/<job_id>                       # 轮询到 completed
curl localhost:8000/jobs/<job_id>/patch                 # patch.json
```
