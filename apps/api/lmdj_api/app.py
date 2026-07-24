from __future__ import annotations

import os
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
from lmdj_api.preflight import PreflightError, limits_from_env, persist_and_probe

_API_ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_JOBS_ROOT = _API_ROOT / "jobs"
DEFAULT_DEMO_DIR = _API_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]

_CONTENT_TYPES = {".wav": "audio/wav", ".json": "application/json", ".mid": "audio/midi"}


def default_jobs_root() -> Path:
    value = os.environ.get("LMDJ_JOBS_ROOT")
    return Path(value) if value else _FALLBACK_JOBS_ROOT


def _cors_origins() -> list[str]:
    value = os.environ.get("LMDJ_CORS_ORIGINS")
    if value is None:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def create_app(runner: PipelineRunner | None = None, jobs_root: Path | None = None) -> FastAPI:
    jobs_root = jobs_root or default_jobs_root()
    runner = runner or DemoPipelineRunner(DEFAULT_DEMO_DIR)
    executor = JobExecutor(runner=runner, jobs_root=jobs_root)
    upload_limits = limits_from_env()

    app = FastAPI(title="LMDJ API")
    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _job_dir(job_id: str) -> Path:
        root = jobs_root.resolve()
        job_dir = (root / job_id).resolve()
        # job_id 穿越防护：必须严格落在 jobs_root 内（且不是 jobs_root 本身）
        if not job_dir.is_relative_to(root) or job_dir == root:
            raise HTTPException(status_code=400, detail="invalid job_id")
        if not (job_dir / "status.json").exists():
            raise HTTPException(status_code=404, detail="unknown job_id")
        return job_dir

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/uploads")
    async def uploads(file: UploadFile = File(...)) -> dict:
        temp_dir = Path(tempfile.mkdtemp(prefix="lmdj-upload-"))
        suffix = Path(file.filename or "").suffix.lower()
        destination = temp_dir / f"upload{suffix}"
        try:
            persist_and_probe(file, destination, upload_limits)
        except PreflightError as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(
                status_code=error.status_code,
                detail=error.detail,
            ) from error
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            await file.close()

        job_id = uuid.uuid4().hex[:12]
        try:
            executor.submit(destination, job_id)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
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
        if not status.package_dir:
            raise HTTPException(status_code=404, detail="patch not available")
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
        if not status.package_dir:
            raise HTTPException(status_code=404, detail="patch not available")
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
