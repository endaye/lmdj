# Audio Worker v1 Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `workers/audio/` 落地 `lmdj-audio-worker`：音频输入 → demo pipeline（子进程）→ patchify → `patch.json`，带 status.json 状态机的同步 job 单元 + CLI。

**Architecture:** 三模块分层（spec 方案 A）：`status.py`（JobStatus + 原子读写）、`runner.py`（`PipelineRunner` 协议 + 子进程 `DemoPipelineRunner`）、`job.py`（`process_job` 编排）+ `cli.py`。设计依据：`docs/design/2026-07-08-lmdj-audio-worker-design.md`。

**Tech Stack:** Python 3.11+、stdlib（subprocess/json/dataclasses）、`lmdj-patchify` + `lmdj-core-models`（本地 editable）、pytest。**不进 torch/numpy<2**。

## Global Constraints

- worker 包保持轻量：pyproject `dependencies = []`（`lmdj-patchify`/`lmdj-core-models` 走本地 editable 安装，path 依赖不写 metadata——patchify 同惯例）；venv 内不得出现 torch/numpy<2 锁。
- demo 集成只走子进程：`{demo_dir}/.venv/bin/song-pipeline run <audio> --out {job_dir} --song-id {job_id} [--fast]`；不 import `song_pipeline`。
- `--song-id` 取 job_id：package 目录 = `{job_dir}/{job_id}/`，patch_id = `{job_id}-{内容hash}`。
- `status.json` 契约：字段 `{job_id, state, error, patch_id, package_dir, quality, created_at, updated_at}`；`state` 合法值 = infra 全枚举 `queued/generating/separating/extracting/patchifying/rendering/completed/failed/cancelled`；v1 发射 `queued → separating → patchifying → completed | failed`；**每次转移前落盘**，原子写（tmp + `os.replace`）；时间戳 ISO 8601 UTC（`YYYY-MM-DDTHH:MM:SSZ`）。
- `rejected` 是 `completed` + `quality: "rejected"`，不是 `failed`。
- `error` 仅 failed 非空，子进程 stderr 尾部截断 2000 字符。
- 任何异常必落盘为 failed，不吞；输入音频不存在则建 job 前 `FileNotFoundError`（不产生 job 目录）。
- 默认 `jobs_root = workers/audio/jobs/`（根 `.gitignore` 增加 `workers/audio/jobs/`）；`--demo-dir` 缺省相对 worker 包定位到 `references/demos/lmdj-song-pipeline`。
- CLI：`lmdj-audio-worker run|status`，含 `python -m lmdj_audio_worker.cli` 入口（`__main__` guard）；run 打印每次状态转移，failed 退出码 1。
- 测试零 demucs/torch/ffmpeg：FakeRunner 拷贝 `packages/patchify/tests/fixtures/testsong/`（golden fixture，monorepo 跨包相对路径）；子进程路径用临时 stub 可执行脚本测。
- Commit scope：`feat(audio-worker): ...`（Conventional Commits）。
- 范围外：队列、HTTP、并发、cancel 实现、DB/对象存储、LMDJ 中间格式、进度百分比。

---

## File Structure

- Create: `workers/audio/pyproject.toml`
- Create: `workers/audio/lmdj_audio_worker/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/status.py`（JobStatus、STATES、utc_now、write_status、read_status）
- Create: `workers/audio/lmdj_audio_worker/runner.py`（PipelineRunError、PipelineRunner 协议、DemoPipelineRunner）
- Create: `workers/audio/lmdj_audio_worker/job.py`（process_job）
- Create: `workers/audio/lmdj_audio_worker/cli.py`
- Create: `workers/audio/tests/conftest.py`（GOLDEN 路径、FakeRunner、sample_audio、make_stub_demo）
- Create: `workers/audio/tests/test_status.py`、`test_runner.py`、`test_job.py`、`test_cli.py`
- Modify: 根 `.gitignore`（`workers/audio/jobs/`）、`workers/README.md`（本地验证命令）

---

### Task 1: Package Skeleton And Status Model

**Files:**
- Create: `workers/audio/pyproject.toml`
- Create: `workers/audio/lmdj_audio_worker/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/status.py`
- Create: `workers/audio/tests/test_status.py`
- Modify: 根 `.gitignore`

**Interfaces:**
- Consumes: no previous task.
- Produces:
  - `STATES: frozenset[str]`（infra 全枚举）
  - `JobStatus(job_id: str, state: str, error: str | None = None, patch_id: str | None = None, package_dir: str | None = None, quality: str | None = None, created_at: str = "", updated_at: str = "")`，`to_dict()`
  - `utc_now() -> str`（`YYYY-MM-DDTHH:MM:SSZ`）
  - `write_status(job_dir: Path, status: JobStatus) -> JobStatus`（原子写，回填 updated_at 后返回落盘的实例；未知 state 抛 ValueError）
  - `read_status(job_dir: Path) -> JobStatus`

- [ ] **Step 1: 写 failing 测试**

Create `workers/audio/tests/test_status.py`:

```python
import json
import re
from pathlib import Path

import pytest

from lmdj_audio_worker.status import STATES, JobStatus, read_status, write_status

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_write_and_read_roundtrip(tmp_path: Path):
    status = JobStatus(job_id="job1", state="queued", created_at="2026-07-08T00:00:00Z")
    written = write_status(tmp_path, status)

    assert ISO_Z.match(written.updated_at)
    loaded = read_status(tmp_path)
    assert loaded == written
    assert loaded.created_at == "2026-07-08T00:00:00Z"


def test_write_rejects_unknown_state(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown job state"):
        write_status(tmp_path, JobStatus(job_id="job1", state="doing_stuff"))


def test_states_is_full_infra_enum():
    assert STATES == {
        "queued", "generating", "separating", "extracting", "patchifying",
        "rendering", "completed", "failed", "cancelled",
    }


def test_write_is_atomic_no_tmp_leftover_and_valid_json(tmp_path: Path):
    for _ in range(5):
        write_status(tmp_path, JobStatus(job_id="job1", state="separating"))
        data = json.loads((tmp_path / "status.json").read_text())
        assert data["state"] == "separating"
    assert list(tmp_path.glob("*.tmp")) == []
```

- [ ] **Step 2: 建包并跑测试确认失败**

Create `workers/audio/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lmdj-audio-worker"
version = "0.1.0"
description = "LMDJ audio worker: audio -> pipeline -> patchify -> patch.json"
requires-python = ">=3.11"
# 本地依赖（path 依赖不写 metadata，与 patchify 同惯例）：
#   pip install -e ../../packages/core-models -e ../../packages/patchify
dependencies = []

[project.optional-dependencies]
test = [
  "pytest>=8,<9",
]

[project.scripts]
lmdj-audio-worker = "lmdj_audio_worker.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["lmdj_audio_worker*"]
```

Create `workers/audio/lmdj_audio_worker/__init__.py`（空文件，Task 3 补导出）。

Modify 根 `.gitignore` 的 `### LMDJ` 节追加:

```gitignore
# Audio worker 本地 job 产物
workers/audio/jobs/
```

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
python3 -m venv .venv
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest tests/test_status.py -q
```

Expected: FAIL——`ModuleNotFoundError: No module named 'lmdj_audio_worker.status'`。

- [ ] **Step 3: 实现 status.py**

Create `workers/audio/lmdj_audio_worker/status.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

# infra spec 全枚举：v1 只发射 queued/separating/patchifying/completed/failed，
# 但契约上全部合法，未来细化不破契约。
STATES = frozenset({
    "queued", "generating", "separating", "extracting", "patchifying",
    "rendering", "completed", "failed", "cancelled",
})

STATUS_FILENAME = "status.json"


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: str
    error: str | None = None
    patch_id: str | None = None
    package_dir: str | None = None
    quality: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(job_dir: Path, status: JobStatus) -> JobStatus:
    """原子写（tmp + os.replace）：外部任意时刻读到的都是完整 JSON。"""
    if status.state not in STATES:
        raise ValueError(f"unknown job state: {status.state}")
    stamped = replace(status, updated_at=utc_now())
    job_dir.mkdir(parents=True, exist_ok=True)
    tmp = job_dir / (STATUS_FILENAME + ".tmp")
    tmp.write_text(json.dumps(stamped.to_dict(), ensure_ascii=False, indent=2))
    os.replace(tmp, job_dir / STATUS_FILENAME)
    return stamped


def read_status(job_dir: Path) -> JobStatus:
    data = json.loads((job_dir / STATUS_FILENAME).read_text())
    return JobStatus(**data)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_status.py -q
```

Expected: `4 passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add workers/audio .gitignore
git commit -m "feat(audio-worker): add job status model with atomic writes"
```

---

### Task 2: Demo Pipeline Runner（子进程）

**Files:**
- Create: `workers/audio/lmdj_audio_worker/runner.py`
- Create: `workers/audio/tests/conftest.py`
- Create: `workers/audio/tests/test_runner.py`

**Interfaces:**
- Consumes: no previous task（独立于 status）。
- Produces:
  - `class PipelineRunError(RuntimeError)`：`__init__(message: str, stderr_tail: str = "")`，属性 `stderr_tail`
  - `class PipelineRunner(Protocol)`：`run(audio: Path, out_dir: Path, song_id: str) -> Path`
  - `class DemoPipelineRunner(demo_dir: Path, fast: bool = True, timeout_sec: int = 1800)`：属性 `executable`、方法 `command(audio, out_dir, song_id) -> list[str]`、`run(...) -> Path`
  - conftest 提供 `GOLDEN: Path`、`FakeRunner`、`sample_audio` fixture、`make_stub_demo(tmp_path, body) -> Path` 与 `STUB_OK_BODY`/`STUB_FAIL_BODY`/`STUB_EMPTY_BODY`（Task 3/4 复用）

- [ ] **Step 1: 写 conftest 与 failing 测试**

Create `workers/audio/tests/conftest.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# patchify 的 golden fixture（真实 pipeline 输出快照；wav 为占位字节，patchify 只查存在性）
GOLDEN = Path(__file__).resolve().parents[3] / "packages" / "patchify" / "tests" / "fixtures" / "testsong"


class FakeRunner:
    """把 golden fixture 拷成 package，模拟 pipeline 成功；可注入观察点或失败。"""

    def __init__(
        self,
        package_source: Path = GOLDEN,
        on_run=None,
        fail_with: Exception | None = None,
    ) -> None:
        self.package_source = package_source
        self.on_run = on_run
        self.fail_with = fail_with
        self.calls: list[tuple[Path, Path, str]] = []

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        self.calls.append((audio, out_dir, song_id))
        if self.on_run:
            self.on_run()
        if self.fail_with:
            raise self.fail_with
        dst = out_dir / song_id
        shutil.copytree(self.package_source, dst)
        return dst


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF....WAVEfmt fake-audio")
    return audio


def make_stub_demo(tmp_path: Path, body: str) -> Path:
    """伪 demo 目录：.venv/bin/song-pipeline 是一个可执行 python 脚本。"""
    demo = tmp_path / "demo"
    bin_dir = demo / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "song-pipeline"
    exe.write_text("#!/usr/bin/env python3\n" + body)
    exe.chmod(0o755)
    return demo


STUB_OK_BODY = f'''
import argparse, shutil
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("cmd")
p.add_argument("input", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--song-id", required=True)
p.add_argument("--fast", action="store_true")
a = p.parse_args()
shutil.copytree(Path({str(GOLDEN)!r}), a.out / a.song_id)
'''

STUB_FAIL_BODY = '''
import sys
sys.stderr.write("demucs exploded: CUDA out of memory\\n")
sys.exit(2)
'''

STUB_EMPTY_BODY = '''
import argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("cmd"); p.add_argument("input", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--song-id", required=True)
p.add_argument("--fast", action="store_true")
p.parse_args()
'''
```

Create `workers/audio/tests/test_runner.py`:

```python
from pathlib import Path

import pytest

from lmdj_audio_worker.runner import DemoPipelineRunner, PipelineRunError

from tests.conftest import STUB_EMPTY_BODY, STUB_FAIL_BODY, STUB_OK_BODY, make_stub_demo


def test_command_builds_exact_argv_with_fast(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "demo", fast=True)
    cmd = runner.command(Path("/in/song.wav"), tmp_path / "job", "jobid123")

    assert cmd == [
        str(tmp_path / "demo" / ".venv" / "bin" / "song-pipeline"),
        "run", "/in/song.wav",
        "--out", str(tmp_path / "job"),
        "--song-id", "jobid123",
        "--fast",
    ]


def test_command_omits_fast_when_disabled(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "demo", fast=False)
    cmd = runner.command(Path("/in/song.wav"), tmp_path / "job", "jobid123")
    assert "--fast" not in cmd


def test_run_missing_venv_hints_setup_demo(tmp_path: Path):
    runner = DemoPipelineRunner(tmp_path / "nonexistent-demo")
    with pytest.raises(PipelineRunError, match="setup-demo"):
        runner.run(tmp_path / "song.wav", tmp_path / "job", "jobid123")


def test_run_success_returns_package_dir(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_OK_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    package = DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")

    assert package == out_dir / "jobid123"
    assert (package / "lanes.json").exists()


def test_run_nonzero_exit_carries_stderr_tail(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_FAIL_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    with pytest.raises(PipelineRunError, match="exited with code 2") as exc_info:
        DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")
    assert "demucs exploded" in exc_info.value.stderr_tail


def test_run_missing_lanes_json_fails(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_EMPTY_BODY)
    out_dir = tmp_path / "job"
    out_dir.mkdir()

    with pytest.raises(PipelineRunError, match="lanes.json"):
        DemoPipelineRunner(demo).run(sample_audio, out_dir, "jobid123")
```

（`from tests.conftest import ...` 需要 `tests` 可作为包导入——若 pytest 报导入错误，加空 `workers/audio/tests/__init__.py`，与 core-models 的既有解法一致。）

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
.venv/bin/python -m pytest tests/test_runner.py -q
```

Expected: FAIL——`ModuleNotFoundError: No module named 'lmdj_audio_worker.runner'`。

- [ ] **Step 3: 实现 runner.py**

Create `workers/audio/lmdj_audio_worker/runner.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

STDERR_TAIL_CHARS = 2000


class PipelineRunError(RuntimeError):
    def __init__(self, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.stderr_tail = stderr_tail


class PipelineRunner(Protocol):
    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path: ...


class DemoPipelineRunner:
    """子进程调用冻结的参考 demo pipeline（demo 自己的 venv，依赖完全隔离）。"""

    def __init__(self, demo_dir: Path, fast: bool = True, timeout_sec: int = 1800) -> None:
        self.demo_dir = demo_dir.resolve()
        self.fast = fast
        self.timeout_sec = timeout_sec

    @property
    def executable(self) -> Path:
        return self.demo_dir / ".venv" / "bin" / "song-pipeline"

    def command(self, audio: Path, out_dir: Path, song_id: str) -> list[str]:
        cmd = [
            str(self.executable), "run", str(audio),
            "--out", str(out_dir), "--song-id", song_id,
        ]
        if self.fast:
            cmd.append("--fast")
        return cmd

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        if not self.executable.exists():
            raise PipelineRunError(
                f"demo venv missing at {self.executable} — "
                "先在仓库根目录运行: scripts/dev.sh setup-demo"
            )
        try:
            proc = subprocess.run(
                self.command(audio, out_dir, song_id),
                capture_output=True, text=True, timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as error:
            raise PipelineRunError(
                f"pipeline timed out after {self.timeout_sec}s") from error
        if proc.returncode != 0:
            raise PipelineRunError(
                f"pipeline exited with code {proc.returncode}",
                stderr_tail=(proc.stderr or "")[-STDERR_TAIL_CHARS:],
            )
        package_dir = out_dir / song_id
        if not (package_dir / "lanes.json").exists():
            raise PipelineRunError(f"pipeline produced no lanes.json in {package_dir}")
        return package_dir
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_runner.py -q
```

Expected: `6 passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add workers/audio/lmdj_audio_worker/runner.py workers/audio/tests
git commit -m "feat(audio-worker): subprocess pipeline runner with stub-tested contract"
```

---

### Task 3: Job 编排（process_job）

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/__init__.py`
- Create: `workers/audio/lmdj_audio_worker/job.py`
- Create: `workers/audio/tests/test_job.py`

**Interfaces:**
- Consumes: `JobStatus`/`write_status`/`read_status`/`utc_now` from Task 1；`PipelineRunner`/`PipelineRunError` from Task 2；`lmdj_patchify.patchify.patchify_package(package_dir) -> Patch`（既有，`Patch.patch_id: str`、`Patch.metadata: dict`）。
- Produces:
  - `process_job(audio: Path, *, jobs_root: Path, runner: PipelineRunner, job_id: str | None = None, on_state: Callable[[JobStatus], None] | None = None) -> JobStatus`
  - `lmdj_audio_worker` 包导出 `process_job`、`JobStatus`、`DemoPipelineRunner`、`PipelineRunError`

- [ ] **Step 1: 写 failing 测试**

Create `workers/audio/tests/test_job.py`:

```python
import json
import shutil
from pathlib import Path

import pytest

from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import PipelineRunError
from lmdj_audio_worker.status import read_status

from tests.conftest import GOLDEN, FakeRunner


def test_happy_path_completes_with_patch(tmp_path: Path, sample_audio: Path, fake_runner: FakeRunner):
    jobs_root = tmp_path / "jobs"

    final = process_job(sample_audio, jobs_root=jobs_root, runner=fake_runner, job_id="jobtest")

    assert final.state == "completed"
    assert final.quality == "passed"
    assert final.package_dir == "jobtest"
    assert final.patch_id and final.patch_id.startswith("testsong-")  # fixture 的 report.song_id
    job_dir = jobs_root / "jobtest"
    assert (job_dir / "input" / sample_audio.name).exists()
    assert (job_dir / "jobtest" / "patch.json").exists()
    assert read_status(job_dir).state == "completed"


def test_state_sequence_is_persisted_per_transition(tmp_path: Path, sample_audio: Path):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "jobtest"
    seen: list[str] = []
    # FakeRunner 运行期间读盘：此刻必须已是 separating
    runner = FakeRunner(on_run=lambda: seen.append(read_status(job_dir).state))

    transitions: list[str] = []
    process_job(
        sample_audio, jobs_root=jobs_root, runner=runner, job_id="jobtest",
        on_state=lambda s: transitions.append(s.state),
    )

    assert transitions == ["queued", "separating", "patchifying", "completed"]
    assert seen == ["separating"]


def test_rejected_pipeline_is_completed_with_quality_flag(tmp_path: Path, sample_audio: Path):
    rejected_pkg = tmp_path / "rejected-pkg"
    shutil.copytree(GOLDEN, rejected_pkg)
    report = json.loads((rejected_pkg / "report.json").read_text())
    report["status"] = "rejected"
    (rejected_pkg / "report.json").write_text(json.dumps(report))

    final = process_job(
        sample_audio, jobs_root=tmp_path / "jobs",
        runner=FakeRunner(package_source=rejected_pkg), job_id="jobtest",
    )

    assert final.state == "completed"
    assert final.quality == "rejected"


def test_runner_failure_lands_failed_with_stderr_tail(tmp_path: Path, sample_audio: Path):
    runner = FakeRunner(fail_with=PipelineRunError("pipeline exited with code 2", stderr_tail="demucs exploded"))

    final = process_job(sample_audio, jobs_root=tmp_path / "jobs", runner=runner, job_id="jobtest")

    assert final.state == "failed"
    assert "demucs exploded" in (final.error or "")
    assert read_status(tmp_path / "jobs" / "jobtest").state == "failed"


def test_patchify_failure_lands_failed(tmp_path: Path, sample_audio: Path):
    broken_pkg = tmp_path / "broken-pkg"
    shutil.copytree(GOLDEN, broken_pkg)
    lanes = json.loads((broken_pkg / "lanes.json").read_text())
    (broken_pkg / lanes["lanes"][0]["sample"]).unlink()  # 缺 sample → patchify loader 抛错

    final = process_job(
        sample_audio, jobs_root=tmp_path / "jobs",
        runner=FakeRunner(package_source=broken_pkg), job_id="jobtest",
    )

    assert final.state == "failed"
    assert "Missing sample file" in (final.error or "")


def test_missing_input_raises_before_creating_job(tmp_path: Path, fake_runner: FakeRunner):
    jobs_root = tmp_path / "jobs"
    with pytest.raises(FileNotFoundError):
        process_job(tmp_path / "ghost.wav", jobs_root=jobs_root, runner=fake_runner, job_id="jobtest")
    assert not (jobs_root / "jobtest").exists()


def test_default_job_id_is_generated(tmp_path: Path, sample_audio: Path, fake_runner: FakeRunner):
    final = process_job(sample_audio, jobs_root=tmp_path / "jobs", runner=fake_runner)
    assert len(final.job_id) == 12
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
.venv/bin/python -m pytest tests/test_job.py -q
```

Expected: FAIL——`ModuleNotFoundError: No module named 'lmdj_audio_worker.job'`。

- [ ] **Step 3: 实现 job.py 与包导出**

Create `workers/audio/lmdj_audio_worker/job.py`:

```python
from __future__ import annotations

import shutil
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Callable

from lmdj_patchify.patchify import patchify_package

from lmdj_audio_worker.runner import PipelineRunError, PipelineRunner
from lmdj_audio_worker.status import JobStatus, utc_now, write_status


def process_job(
    audio: Path,
    *,
    jobs_root: Path,
    runner: PipelineRunner,
    job_id: str | None = None,
    on_state: Callable[[JobStatus], None] | None = None,
) -> JobStatus:
    """同步执行一个 audio job：input 拷贝 → pipeline → patchify → 终态。

    所有状态转移先落盘（status.json 原子写）；任何异常落为 failed，不吞。
    v1 发射 queued → separating → patchifying → completed | failed。
    """
    if not audio.exists():
        raise FileNotFoundError(f"input audio not found: {audio}")
    job_id = job_id or uuid.uuid4().hex[:12]
    job_dir = jobs_root / job_id
    (job_dir / "input").mkdir(parents=True, exist_ok=True)
    input_copy = job_dir / "input" / audio.name
    shutil.copy2(audio, input_copy)

    def emit(status: JobStatus) -> JobStatus:
        written = write_status(job_dir, status)
        if on_state:
            on_state(written)
        return written

    status = emit(JobStatus(job_id=job_id, state="queued", created_at=utc_now()))
    try:
        status = emit(replace(status, state="separating"))
        package_dir = runner.run(input_copy, job_dir, job_id)
        status = emit(replace(status, state="patchifying", package_dir=package_dir.name))
        patch = patchify_package(package_dir)
        quality = str(patch.metadata.get("status") or "unknown")
        return emit(replace(status, state="completed", patch_id=patch.patch_id, quality=quality))
    except PipelineRunError as error:
        detail = str(error)
        if error.stderr_tail:
            detail += f"\nstderr tail:\n{error.stderr_tail}"
        return emit(replace(status, state="failed", error=detail))
    except Exception as error:  # noqa: BLE001 — 失败必须落盘可查（patchify ValueError 等）
        return emit(replace(status, state="failed", error=str(error)))
```

Update `workers/audio/lmdj_audio_worker/__init__.py`:

```python
from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import DemoPipelineRunner, PipelineRunError, PipelineRunner
from lmdj_audio_worker.status import STATES, JobStatus, read_status, write_status

__all__ = [
    "STATES", "DemoPipelineRunner", "JobStatus", "PipelineRunError",
    "PipelineRunner", "process_job", "read_status", "write_status",
]
```

- [ ] **Step 4: 跑测试确认通过（含回归）**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: `17 passed`（status 4 + runner 6 + job 7）。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add workers/audio/lmdj_audio_worker workers/audio/tests/test_job.py
git commit -m "feat(audio-worker): job orchestration with persisted state machine"
```

---

### Task 4: CLI 与文档

**Files:**
- Create: `workers/audio/lmdj_audio_worker/cli.py`
- Create: `workers/audio/tests/test_cli.py`
- Modify: `workers/README.md`

**Interfaces:**
- Consumes: `process_job`/`DemoPipelineRunner`/`read_status` from Tasks 1-3；conftest 的 `make_stub_demo`/`STUB_OK_BODY`/`STUB_FAIL_BODY`、`sample_audio`。
- Produces: CLI `lmdj-audio-worker run|status` + `python -m lmdj_audio_worker.cli` 入口。

- [ ] **Step 1: 写 failing CLI 测试**

Create `workers/audio/tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

from tests.conftest import STUB_FAIL_BODY, STUB_OK_BODY, make_stub_demo


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lmdj_audio_worker.cli", *args],
        capture_output=True, text=True,
    )


def test_run_completes_and_status_reads_back(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_OK_BODY)
    jobs_root = tmp_path / "jobs"

    result = run_cli(
        "run", str(sample_audio),
        "--job-id", "clitest",
        "--jobs-root", str(jobs_root),
        "--demo-dir", str(demo),
    )

    assert result.returncode == 0, result.stderr
    assert "-> completed" in result.stdout
    assert "patch.json" in result.stdout
    assert (jobs_root / "clitest" / "clitest" / "patch.json").exists()

    status = run_cli("status", "clitest", "--jobs-root", str(jobs_root))
    assert status.returncode == 0
    assert json.loads(status.stdout)["state"] == "completed"


def test_run_failure_exits_1_with_error(tmp_path: Path, sample_audio: Path):
    demo = make_stub_demo(tmp_path, STUB_FAIL_BODY)

    result = run_cli(
        "run", str(sample_audio),
        "--job-id", "clifail",
        "--jobs-root", str(tmp_path / "jobs"),
        "--demo-dir", str(demo),
    )

    assert result.returncode == 1
    assert "demucs exploded" in result.stderr


def test_status_unknown_job_exits_1(tmp_path: Path):
    result = run_cli("status", "ghost", "--jobs-root", str(tmp_path / "jobs"))
    assert result.returncode == 1
    assert "unknown job_id" in result.stderr
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
.venv/bin/python -m pytest tests/test_cli.py -q
```

Expected: FAIL——CLI 模块不存在（子进程退出码非 0 触发断言失败）。

- [ ] **Step 3: 实现 cli.py**

Create `workers/audio/lmdj_audio_worker/cli.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import DemoPipelineRunner
from lmdj_audio_worker.status import read_status

_WORKER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS_ROOT = _WORKER_ROOT / "jobs"
DEFAULT_DEMO_DIR = (
    _WORKER_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LMDJ Audio Worker: audio -> pipeline -> patchify -> patch.json")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="同步处理一个音频文件")
    run.add_argument("audio", type=Path)
    run.add_argument("--job-id", default=None)
    run.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)
    run.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    run.add_argument("--no-fast", action="store_true", help="用 htdemucs_ft（更慢更准）")

    status = sub.add_parser("status", help="打印 job 的 status.json")
    status.add_argument("job_id")
    status.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)

    args = parser.parse_args()

    if args.command == "run":
        runner = DemoPipelineRunner(args.demo_dir, fast=not args.no_fast)
        final = process_job(
            args.audio,
            jobs_root=args.jobs_root,
            runner=runner,
            job_id=args.job_id,
            on_state=lambda s: print(f"[{s.updated_at}] {s.job_id} -> {s.state}"),
        )
        if final.state == "failed":
            print(f"error: {final.error}", file=sys.stderr)
            sys.exit(1)
        patch_path = args.jobs_root / final.job_id / (final.package_dir or "") / "patch.json"
        print(f"patch: {patch_path}")
    else:
        job_dir = args.jobs_root / args.job_id
        if not (job_dir / "status.json").exists():
            print(f"unknown job_id: {args.job_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(read_status(job_dir).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 更新 workers/README.md**

在 `workers/README.md` 末尾追加：

````markdown
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
````

- [ ] **Step 5: 跑全量测试确认通过**

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
.venv/bin/python -m pytest tests/ -q
```

Expected: `20 passed`（status 4 + runner 6 + job 7 + cli 3）。

- [ ] **Step 6: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add workers/audio/lmdj_audio_worker/cli.py workers/audio/tests/test_cli.py workers/README.md
git commit -m "feat(audio-worker): cli with run and status commands"
```

---

## Verification

全计划验证（Task 4 之后）：

```bash
cd /Users/endaye/Projects/lmdj/workers/audio
.venv/bin/python -m pytest tests/ -q     # expected: 20 passed
.venv/bin/pip list | grep -iE "torch" || echo "no torch ✓"   # numpy 仅作为 pretty_midi 传递依赖（无 <2 锁）
```

真实端到端冒烟（**需 demo venv**，约几分钟；用 demo 合成曲避免找歌）：

```bash
cd /Users/endaye/Projects/lmdj
scripts/dev.sh smoke   # 幂等：确保 demo venv + output/testsong/input.wav 存在
workers/audio/.venv/bin/lmdj-audio-worker run \
  references/demos/lmdj-song-pipeline/output/testsong/input.wav
# 预期：逐行打印 queued → separating → patchifying → completed，最后一行 patch: .../patch.json
workers/audio/.venv/bin/lmdj-audio-worker status <上面输出的 job_id>
```

冒烟产物写入 `workers/audio/jobs/`（gitignored），不得改动 demo 源文件。

## Out Of Scope For This Plan

- 队列（Redis/RQ/云托管）、HTTP API、并发/多 job 调度、cancel 实现（枚举已预留）。
- 数据库、对象存储、generation worker。
- LMDJ 中间格式（truth 三段式退出条件，属 pipeline 正式化的独立计划）。
- 进度百分比、细粒度阶段解析。

## Self-Review

- Spec 覆盖：status.json 契约（字段/枚举/原子写/时间戳 → Task 1）、子进程 runner（命令构造/venv 缺失/超时/退出码/lanes.json 判定 → Task 2）、编排与状态序列（含 rejected→completed+quality、异常落盘、输入缺失前置检查 → Task 3）、CLI（run/status/退出码/`-m` 入口 → Task 4）、gitignore 与 README（Task 1/4）、零 demucs 测试（FakeRunner + stub 脚本贯穿）——逐条可指到任务。
- 类型一致性：`JobStatus` 字段、`PipelineRunner.run(audio, out_dir, song_id) -> Path`、`process_job` 签名在 Interfaces 块与实现/测试一致；conftest 的 `GOLDEN`/`FakeRunner`/`make_stub_demo`/STUB 常量只定义一次、Task 2/3/4 共用。
- 已知取舍：`separating` 覆盖整个子进程期间（粗粒度，spec 已定）；timeout 路径无自动化测试（需长驻子进程，成本不成比例——命令构造/退出码/stderr 路径已锁定，timeout 为 stdlib `subprocess.run(timeout=)` 直用）；stub 脚本依赖 POSIX 可执行权限（macOS/Linux 开发环境成立）。
