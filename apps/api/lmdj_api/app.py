from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from lmdj_audio_worker import DemoPipelineRunner, PipelineRunner
from lmdj_audio_worker.status import read_status

from lmdj_api.executor import JobExecutor

_API_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS_ROOT = _API_ROOT / "jobs"
DEFAULT_DEMO_DIR = _API_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"

_CONTENT_TYPES = {".wav": "audio/wav", ".json": "application/json", ".mid": "audio/midi"}


def create_app(runner: PipelineRunner | None = None, jobs_root: Path | None = None) -> FastAPI:
    jobs_root = jobs_root or DEFAULT_JOBS_ROOT
    runner = runner or DemoPipelineRunner(DEFAULT_DEMO_DIR)
    executor = JobExecutor(runner=runner, jobs_root=jobs_root)

    app = FastAPI(title="LMDJ API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _job_dir(job_id: str) -> Path:
        job_dir = jobs_root / job_id
        if not (job_dir / "status.json").exists():
            raise HTTPException(status_code=404, detail="unknown job_id")
        return job_dir

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/uploads")
    async def uploads(file: UploadFile = File(...)) -> dict:
        job_id = uuid.uuid4().hex[:12]
        suffix = Path(file.filename or "input.wav").suffix or ".wav"
        tmp = Path(tempfile.mkdtemp()) / f"upload{suffix}"
        with tmp.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        executor.submit(tmp, job_id)
        return {"job_id": job_id, "state": "queued"}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        return read_status(_job_dir(job_id)).to_dict()

    @app.get("/jobs/{job_id}/patch")
    def job_patch(job_id: str):
        job_dir = _job_dir(job_id)
        status = read_status(job_dir)
        if status.state != "completed":
            return JSONResponse(
                status_code=409,
                content={"detail": "job not completed", "state": status.state},
            )
        patch_path = job_dir / (status.package_dir or "") / "patch.json"
        if not patch_path.exists():
            raise HTTPException(status_code=404, detail="patch.json not found")
        return FileResponse(patch_path, media_type="application/json")

    @app.get("/jobs/{job_id}/files/{path:path}")
    def job_file(job_id: str, path: str):
        job_dir = _job_dir(job_id)
        status = read_status(job_dir)
        if status.state != "completed":
            return JSONResponse(
                status_code=409,
                content={"detail": "job not completed", "state": status.state},
            )
        package_dir = (job_dir / (status.package_dir or "")).resolve()
        target = (package_dir / path).resolve()
        # 路径穿越防护：resolve() 后目标必须严格落在 package_dir 内（且不是 package_dir 本身）
        if not target.is_relative_to(package_dir) or target == package_dir:
            raise HTTPException(status_code=400, detail="invalid path")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        media = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        return FileResponse(target, media_type=media)

    return app


app = create_app()
