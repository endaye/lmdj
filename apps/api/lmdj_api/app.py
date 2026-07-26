from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from lmdj_audio_worker import DemoPipelineRunner, PipelineRunner
from lmdj_audio_worker.status import read_status

from lmdj_api.executor import JobExecutor
from lmdj_api.export_builder import (
    ExportIncomplete,
    build_creator_export,
    inspect_creator_export,
)
from lmdj_api.preflight import PreflightError, limits_from_env, persist_and_probe
from lmdj_api.job_catalog import JobCatalog, validate_submission_id
from lmdj_api.version import build_identity_from_env

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


def runner_from_env() -> PipelineRunner:
    pipeline = os.environ.get("LMDJ_PIPELINE", "legacy")
    if pipeline == "legacy":
        return DemoPipelineRunner(DEFAULT_DEMO_DIR)
    if pipeline == "materials-v1":
        # DSP dependencies remain optional for legacy API deployments.
        from lmdj_audio_worker.creator_runner import CreatorPipelineRunner

        return CreatorPipelineRunner()
    raise ValueError("LMDJ_PIPELINE must be one of: legacy, materials-v1")


def create_app(runner: PipelineRunner | None = None, jobs_root: Path | None = None) -> FastAPI:
    jobs_root = jobs_root or default_jobs_root()
    runner = runner or runner_from_env()
    catalog = JobCatalog(jobs_root)
    catalog.interrupt_nonterminal()
    executor = JobExecutor(runner=runner, jobs_root=jobs_root)
    upload_limits = limits_from_env()
    build_identity = build_identity_from_env()

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

    def _completed_package_dir(job_id: str) -> tuple[Path, Path]:
        job_dir = _job_dir(job_id)
        status = read_status(job_dir)
        if status.state != "completed":
            raise HTTPException(
                status_code=409,
                detail={"code": "job_not_completed", "state": status.state},
            )
        if not status.package_dir:
            raise HTTPException(status_code=404, detail="export not available")
        package_dir = (job_dir / status.package_dir).resolve()
        if (
            package_dir == job_dir
            or not package_dir.is_relative_to(job_dir)
        ):
            raise HTTPException(status_code=400, detail="invalid package_dir")
        if not package_dir.is_dir():
            raise HTTPException(status_code=404, detail="export package not found")
        return job_dir, package_dir

    def _public_status(status) -> dict[str, object]:
        snapshot = executor.snapshot()
        return {
            **status.to_dict(),
            "queue_position": snapshot.positions.get(status.job_id),
            "capacity": asdict(snapshot.capacity),
        }

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, **asdict(build_identity)}

    @app.get("/queue")
    def queue_capacity() -> dict:
        return asdict(executor.snapshot().capacity)

    @app.post("/uploads")
    async def uploads(
        file: UploadFile = File(...),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        temp_dir = Path(tempfile.mkdtemp(prefix="lmdj-upload-"))
        suffix = Path(file.filename or "").suffix.lower()
        destination = temp_dir / f"upload{suffix}"
        original_filename = file.filename or ""
        try:
            await run_in_threadpool(
                persist_and_probe,
                file,
                destination,
                upload_limits,
            )
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

        try:
            submission_id = validate_submission_id(
                idempotency_key or uuid.uuid4().hex,
            )
        except ValueError as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_submission_id"},
            ) from error

        status, created = catalog.get_or_create(
            submission_id,
            original_filename,
            pipeline=str(getattr(runner, "pipeline_id", "legacy")),
        )
        if not created:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return _public_status(status)

        try:
            executor.submit(destination, status)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(jobs_root / status.job_id, ignore_errors=True)
            try:
                jobs_root.rmdir()
            except OSError:
                pass
            raise
        return _public_status(status)

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        return _public_status(read_status(_job_dir(job_id)))

    @app.get("/submissions/{submission_id}")
    def submission_status(submission_id: str) -> dict:
        try:
            status = catalog.find_by_submission_id(submission_id)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_submission_id"},
            ) from error
        if status is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "unknown_submission_id"},
            )
        return _public_status(status)

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
        internal_contracts = {
            (package_dir / "materials.json").resolve(),
            (package_dir / "separation.json").resolve(),
        }
        if target in internal_contracts:
            raise HTTPException(status_code=404, detail="file not found")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        media = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        return FileResponse(target, media_type=media)

    @app.get("/jobs/{job_id}/export/status")
    def creator_export_status(job_id: str) -> dict:
        _, package_dir = _completed_package_dir(job_id)
        try:
            return inspect_creator_export(package_dir).to_dict()
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_export_source"},
            ) from error

    @app.get("/jobs/{job_id}/export")
    def creator_export(job_id: str):
        job_dir, package_dir = _completed_package_dir(job_id)
        export_dir = job_dir / "exports"
        resolved_export_dir = export_dir.resolve()
        if (
            resolved_export_dir == job_dir
            or not resolved_export_dir.is_relative_to(job_dir)
        ):
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_export_output"},
            )
        try:
            export_path = build_creator_export(
                package_dir,
                export_dir,
            )
        except ExportIncomplete as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "export_incomplete",
                    "missing": error.missing,
                },
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_export_source"},
            ) from error
        return FileResponse(
            export_path,
            media_type="application/zip",
            filename=export_path.name,
        )

    return app


app = create_app()
