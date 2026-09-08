"""FastAPI 服务：提交任务 / 查询状态 / 下载谱面包。

    uvicorn song_pipeline.api:app --port 8000
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .config import PipelineConfig
from .pipeline import run_pipeline

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

OUT_ROOT = Path("output")
app = FastAPI(title="LMDJ song-pipeline")
_lock = threading.Lock()  # demucs 模型非线程安全，任务串行


def _status_path(song_id: str) -> Path:
    return OUT_ROOT / song_id / "status.json"


def _write_status(song_id: str, **kw) -> None:
    p = _status_path(song_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"song_id": song_id, **kw}, ensure_ascii=False))


def _worker(song_id: str, audio_path: Path) -> None:
    with _lock:
        _write_status(song_id, state="processing")
        try:
            report = run_pipeline(audio_path, OUT_ROOT, song_id, PipelineConfig())
            _write_status(song_id, state=report["status"], report=report)
        except Exception as e:  # noqa: BLE001 任务失败要落盘可查
            logging.exception("song %s failed", song_id)
            _write_status(song_id, state="failed", error=str(e))


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/songs")
async def submit(file: UploadFile):
    """上传整曲音频，返回 song_id；管线在后台执行。"""
    song_id = uuid.uuid4().hex[:12]
    in_dir = OUT_ROOT / song_id
    in_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "input.wav").suffix or ".wav"
    audio_path = in_dir / f"input{suffix}"
    with audio_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    _write_status(song_id, state="queued")
    threading.Thread(target=_worker, args=(song_id, audio_path), daemon=True).start()
    return {"song_id": song_id, "state": "queued"}


@app.get("/songs/{song_id}")
def status(song_id: str):
    p = _status_path(song_id)
    if not p.exists():
        raise HTTPException(404, "unknown song_id")
    return json.loads(p.read_text())


@app.get("/songs/{song_id}/package")
def package(song_id: str):
    """下载谱面包 zip：samples/*.wav + chart.mid + lanes.json。"""
    song_dir = OUT_ROOT / song_id
    if not (song_dir / "lanes.json").exists():
        raise HTTPException(404, "package not ready")
    zip_path = song_dir / f"{song_id}.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in ["chart.mid", "lanes.json", "report.json"]:
                z.write(song_dir / f, f)
            for wav in sorted((song_dir / "samples").glob("*.wav")):
                z.write(wav, f"samples/{wav.name}")
    return FileResponse(zip_path, filename=f"{song_id}.zip")
