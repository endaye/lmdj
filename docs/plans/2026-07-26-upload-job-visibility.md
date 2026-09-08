# Upload Job Visibility Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing single-slot upload executor a truthful FIFO queue whose jobs survive browser refresh, deduplicate one logical submission, expose capacity and queue position, and become explicitly interrupted after an API restart.

**Architecture:** `JobStatus` remains the durable file-backed source of truth and gains submission/display metadata plus an `interrupted` terminal state. `apps/api` owns a small file-backed catalog and a single daemon FIFO worker; API responses enrich persisted status with live queue position and capacity. The Web stores only its own submission references in `localStorage`, resolves them through the API after refresh, and presents all locally submitted jobs in a queue surface while continuing to load completed patches through `loadPatch`.

**Tech Stack:** Python 3.11 dataclasses, FastAPI, file-backed `status.json`, `threading.Condition`, React 19, TypeScript, Vitest, React Testing Library, pytest.

## Global Constraints

- Maximum processing concurrency remains exactly `1`.
- Waiting jobs remain `queued` until the single worker takes the execution slot.
- The browser persists only locally submitted task references; there is no account-level or cross-device history.
- `lmdj.patch.v1` remains the only Web/API playback contract.
- Submission idempotency applies only to one client-generated submission ID; the same audio may be intentionally submitted again with a new ID.
- Restart recovery does not resume DSP work; every old nonterminal job becomes the explicit terminal state `interrupted`.
- Existing path-confinement, upload preflight, patch, file, and Creator Export behavior must remain intact.
- No Redis, Postgres, object storage, authentication, rate limiting, cancellation, or multi-worker execution is introduced.

---

### Task 1: Persist User-Visible Job Identity and Restart Outcome

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/status.py`
- Modify: `workers/audio/lmdj_audio_worker/job.py`
- Modify: `workers/audio/tests/test_status.py`
- Modify: `workers/audio/tests/test_job.py`

**Interfaces:**
- Produces: `TERMINAL_STATES: frozenset[str]`
- Produces: `NONTERMINAL_STATES: frozenset[str]`
- Produces: `JobStatus.submission_id`, `original_filename`, and `error_code`
- Produces: `process_job(audio: Path, *, jobs_root: Path, runner: PipelineRunner, job_id: str | None = None, on_state: Callable[[JobStatus], None] | None = None, key_analyzer: KeyAnalyzer | None = None, initial_status: JobStatus | None = None) -> JobStatus`
- Consumes: existing atomic `write_status` and file-backed `read_status`

- [ ] **Step 1: Write failing status-contract tests**

```python
def test_status_roundtrip_preserves_submission_identity(tmp_path: Path):
    status = JobStatus(
        job_id="job1",
        state="queued",
        submission_id="submit-1",
        original_filename="夜曲.wav",
        created_at="2026-07-26T00:00:00Z",
    )
    assert read_status(tmp_path) == write_status(tmp_path, status)


def test_interrupted_is_terminal():
    assert "interrupted" in STATES
    assert "interrupted" in TERMINAL_STATES
    assert "queued" in NONTERMINAL_STATES
```

- [ ] **Step 2: Run the tests and verify the new contract fails**

Run: `workers/audio/.venv/bin/python -m pytest workers/audio/tests/test_status.py -q`

Expected: FAIL because the new fields and state sets do not exist.

- [ ] **Step 3: Extend the durable status model**

```python
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})
NONTERMINAL_STATES = STATES - TERMINAL_STATES

@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: str
    error: str | None = None
    error_code: str | None = None
    patch_id: str | None = None
    package_dir: str | None = None
    quality: str | None = None
    submission_id: str | None = None
    original_filename: str | None = None
    created_at: str = ""
    updated_at: str = ""
```

Add `"interrupted"` to `STATES`. Defaults keep historical status files readable.

- [ ] **Step 4: Preserve API-created metadata through Worker transitions**

Add `initial_status: JobStatus | None = None` to `process_job`. Validate that an initial status has the selected `job_id` and starts in `queued`; use it as the first emitted status. Direct Worker callers continue to create the existing minimal queued status.

```python
if initial_status is not None:
    if initial_status.job_id != job_id or initial_status.state != "queued":
        raise ValueError("initial status must be queued for the selected job_id")
    status = emit(initial_status)
else:
    status = emit(JobStatus(job_id=job_id, state="queued", created_at=utc_now()))
```

- [ ] **Step 5: Add and run a Worker metadata-preservation test**

```python
def test_initial_status_metadata_survives_to_completed(
    tmp_path: Path,
    sample_audio: Path,
):
    initial = JobStatus(
        job_id="jobtest",
        state="queued",
        submission_id="submit-1",
        original_filename="song.wav",
        created_at="2026-07-26T00:00:00Z",
    )
    final = process_job(
        sample_audio,
        jobs_root=tmp_path / "jobs",
        runner=FakeRunner(),
        job_id="jobtest",
        initial_status=initial,
    )
    assert final.submission_id == "submit-1"
    assert final.original_filename == "song.wav"
```

Run: `workers/audio/.venv/bin/python -m pytest workers/audio/tests/test_status.py workers/audio/tests/test_job.py -q`

Expected: PASS.

---

### Task 2: Replace Lock-Waiting Threads with a Truthful FIFO Executor

**Files:**
- Modify: `apps/api/lmdj_api/executor.py`
- Modify: `apps/api/tests/test_executor.py`

**Interfaces:**
- Produces: `QueueCapacity(max_concurrency: int, processing: int, waiting: int)`
- Produces: `QueueSnapshot(capacity: QueueCapacity, positions: dict[str, int], active_job_id: str | None)`
- Produces: `JobExecutor.submit(audio_path: Path, initial_status: JobStatus) -> None`
- Produces: `JobExecutor.snapshot() -> QueueSnapshot`
- Consumes: `process_job(audio_path, jobs_root=self.jobs_root, runner=self.runner, job_id=initial_status.job_id, initial_status=initial_status)`

- [ ] **Step 1: Write failing FIFO and snapshot tests**

Create three queued `JobStatus` objects, hold the first Runner call on a barrier, and assert:

```python
snapshot = executor.snapshot()
assert snapshot.capacity.max_concurrency == 1
assert snapshot.capacity.processing == 1
assert snapshot.capacity.waiting == 2
assert snapshot.positions == {"jobB": 1, "jobC": 2}
```

Release jobs in order and assert Runner calls are `jobA`, `jobB`, `jobC`.

- [ ] **Step 2: Run the executor tests and verify failure**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests/test_executor.py -q`

Expected: FAIL because the current executor has no FIFO deque or snapshot.

- [ ] **Step 3: Implement one condition-driven daemon worker**

Use a private frozen `_QueuedJob(audio_path, initial_status)`, a `deque`, a `Condition`, one active job ID, and one daemon thread created in `__init__`.

```python
@dataclass(frozen=True)
class QueueCapacity:
    max_concurrency: int
    processing: int
    waiting: int

@dataclass(frozen=True)
class QueueSnapshot:
    capacity: QueueCapacity
    positions: dict[str, int]
    active_job_id: str | None

def submit(self, audio_path: Path, initial_status: JobStatus) -> None:
    with self._condition:
        self._pending.append(_QueuedJob(audio_path, initial_status))
        self._condition.notify()
```

The worker pops from the left, sets `_active_job_id`, invokes `process_job`, and clears the active ID in `finally`. `wait_idle` waits on the same condition until both active and pending are empty.

- [ ] **Step 4: Run executor tests**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests/test_executor.py -q`

Expected: PASS, including strict FIFO order and capacity snapshots.

---

### Task 3: Add a Durable Submission Catalog and Restart Recovery

**Files:**
- Create: `apps/api/lmdj_api/job_catalog.py`
- Create: `apps/api/tests/test_job_catalog.py`

**Interfaces:**
- Produces: `validate_submission_id(value: str) -> str`
- Produces: `JobCatalog.get_or_create(submission_id, original_filename) -> tuple[JobStatus, bool]`
- Produces: `JobCatalog.find_by_submission_id(submission_id) -> JobStatus | None`
- Produces: `JobCatalog.interrupt_nonterminal() -> list[JobStatus]`
- Consumes: `read_status`, `write_status`, `NONTERMINAL_STATES`

- [ ] **Step 1: Write failing catalog tests**

Cover:

```python
first, created = catalog.get_or_create("018f-valid-id", "song.wav")
second, duplicate = catalog.get_or_create("018f-valid-id", "ignored.wav")
assert created is True
assert duplicate is False
assert second.job_id == first.job_id
assert second.original_filename == "song.wav"
```

Also persist a `separating` and `queued` job, construct a new catalog, call `interrupt_nonterminal`, and assert both become `interrupted` with `error_code == "service_interrupted"`. Completed and failed jobs remain unchanged.

- [ ] **Step 2: Run tests and verify failure**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests/test_job_catalog.py -q`

Expected: FAIL because `job_catalog.py` does not exist.

- [ ] **Step 3: Implement the catalog**

Use a process-local lock around scan-and-create. Submission IDs must match:

```python
SUBMISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
```

`get_or_create` scans valid direct child job directories, compares `status.submission_id`, and atomically writes a new queued status only when no match exists. The stored display name uses `Path(original_filename).name` and falls back to `"untitled-audio"`.

`interrupt_nonterminal` rewrites only statuses whose state is in `NONTERMINAL_STATES`:

```python
replace(
    status,
    state="interrupted",
    error_code="service_interrupted",
    error="API service restarted before this Job completed.",
)
```

Malformed or unreadable unrelated directories are skipped by scans and remain unavailable through normal job routes.

- [ ] **Step 4: Run catalog tests**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests/test_job_catalog.py -q`

Expected: PASS.

---

### Task 4: Expose Idempotent Upload, Submission Recovery, and Queue Capacity

**Files:**
- Modify: `apps/api/lmdj_api/app.py`
- Modify: `apps/api/tests/test_app.py`

**Interfaces:**
- Produces: `POST /uploads` accepting optional `Idempotency-Key`
- Produces: `GET /submissions/{submission_id}`
- Produces: `GET /queue`
- Extends: `GET /jobs/{job_id}` with `queue_position` and `capacity`
- Consumes: `JobCatalog`, `JobExecutor.snapshot`

- [ ] **Step 1: Add failing endpoint tests**

Test that:

1. Two uploads with the same `Idempotency-Key` return the same Job ID and Runner runs once.
2. Two different IDs create two Jobs.
3. A barrier-held A and queued B return processing `1`, waiting `1`, and B position `1`.
4. `GET /submissions/{id}` recovers the accepted Job after the original response is ignored.
5. Recreating the app over the same `jobs_root` exposes old nonterminal Jobs as `interrupted`.
6. Original filename, Job ID, created time, state, and queue position are present.

- [ ] **Step 2: Run the focused API tests and verify failure**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests/test_app.py -q`

Expected: FAIL on the new endpoint and response assertions.

- [ ] **Step 3: Wire catalog and executor into `create_app`**

Construct the catalog first, call `interrupt_nonterminal`, then construct the executor. For upload:

```python
submission_id = validate_submission_id(idempotency_key or uuid.uuid4().hex)
status, created = catalog.get_or_create(submission_id, file.filename or "")
if created:
    executor.submit(destination, status)
else:
    shutil.rmtree(temp_dir, ignore_errors=True)
return {"job_id": status.job_id, "state": status.state}
```

Keep preflight before catalog creation so rejected input never creates a Job. Protect catalog lookup/create from concurrent duplicate requests.

- [ ] **Step 4: Add a shared response-enrichment helper**

```python
def _public_status(status: JobStatus) -> dict[str, object]:
    snapshot = executor.snapshot()
    return {
        **status.to_dict(),
        "queue_position": snapshot.positions.get(status.job_id),
        "capacity": asdict(snapshot.capacity),
    }
```

Use it in the Job and submission routes. `/queue` returns `asdict(executor.snapshot().capacity)`.

- [ ] **Step 5: Run API tests**

Run: `apps/api/.venv/bin/python -m pytest apps/api/tests -q`

Expected: PASS.

---

### Task 5: Add Web API Types and Durable Local Submission References

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Create: `apps/web/src/jobs/storage.ts`
- Create: `apps/web/src/jobs/storage.test.ts`

**Interfaces:**
- Produces: `QueueCapacity`
- Extends: `JobStatus` with identity, timestamps, queue position, capacity, and `error_code`
- Produces: `uploadSong(base, file, submissionId) -> Promise<JobStatus>`
- Produces: `fetchJob(base, jobId) -> Promise<JobStatus>`
- Produces: `resolveSubmission(base, submissionId) -> Promise<JobStatus>`
- Produces: `fetchQueueCapacity(base) -> Promise<QueueCapacity>`
- Produces: `StoredSubmission`
- Produces: `loadSubmissions`, `saveSubmissions`, `upsertSubmission`

- [ ] **Step 1: Write failing client tests**

Assert that `uploadSong` sends:

```typescript
headers: { "Idempotency-Key": "submission-123" }
```

and returns the complete status payload. Add route tests for `/jobs/job123`, `/submissions/submission-123`, and `/queue`.

- [ ] **Step 2: Write failing storage tests**

Use the existing `MemoryStorage` pattern. Verify corrupted JSON becomes an empty list, valid records round-trip, and upserting a returned Job ID does not duplicate a submission.

- [ ] **Step 3: Run tests and verify failure**

Run: `cd apps/web && npm test -- src/api/client.test.ts src/jobs/storage.test.ts`

Expected: FAIL because the new APIs and storage module do not exist.

- [ ] **Step 4: Implement API and storage boundaries**

Use `lmdj.upload-submissions.v1` as the localStorage key. A stored record is:

```typescript
export interface StoredSubmission {
  submissionId: string;
  jobId: string | null;
  base: string;
  fileName: string;
  submittedAt: string;
}
```

Do not store audio bytes. Generate IDs through an injected/default `crypto.randomUUID()` at the App boundary before calling `uploadSong`.

- [ ] **Step 5: Run focused Web tests**

Run: `cd apps/web && npm test -- src/api/client.test.ts src/jobs/storage.test.ts`

Expected: PASS.

---

### Task 6: Present and Restore the Browser’s Task Queue

**Files:**
- Create: `apps/web/src/ui/JobQueuePanel.tsx`
- Create: `apps/web/src/ui/JobQueuePanel.test.tsx`
- Modify: `apps/web/src/ui/ProcessingPanel.tsx`
- Modify: `apps/web/src/ui/SourcePanel.tsx`
- Modify: `apps/web/src/ui/UploadPanel.tsx`
- Modify: `apps/web/src/ui/UploadingView.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/App.test.tsx`
- Modify: `apps/web/src/ui/theme.css`

**Interfaces:**
- Produces: `TrackedJob { submission, status, clientError }`
- Produces: `JobQueuePanel({ jobs, capacity, onOpenCompleted })`
- Consumes: client functions and `StoredSubmission`
- Preserves: completed Patch loading through `fetchPatchBundle` then `loadPatch`

- [ ] **Step 1: Write failing queue panel component tests**

Render A as `separating` and B as `queued` position `1`. Assert visible text contains:

```text
最大并发 1
正在处理 1
等待 1
song-a.wav
song-b.wav
job-a
job-b
队列位置 1
```

Render an interrupted Job and assert the service-interruption explanation and resubmit guidance are visible.

- [ ] **Step 2: Write failing App acceptance tests**

Cover the requirement sequence:

1. Submit A and B without leaving the task surface.
2. A shows processing and B waiting.
3. After A completes, B enters processing.
4. A/B retain filename, Job ID, timestamp, and state.
5. Duplicate click uses one persisted submission ID while the request is in flight.
6. Remount with stored Jobs and recover/poll them.
7. A locally stored submission without Job ID resolves through `/submissions/{id}` after a lost response.
8. `interrupted` is terminal and displays server context rather than `Failed to fetch`.
9. A single completed upload still opens the Patch workbench through the existing loader.

- [ ] **Step 3: Run focused component tests and verify failure**

Run: `cd apps/web && npm test -- src/ui/JobQueuePanel.test.tsx src/ui/App.test.tsx`

Expected: FAIL because the task queue does not exist and App tracks only one File/Job.

- [ ] **Step 4: Implement a separate tracked-job state in App**

Initialize from `loadSubmissions(localStorage)`. Persist a submission record before starting upload. Maintain File objects only in memory; persisted recovery uses Job/submission endpoints.

For every nonterminal recovered Job, resume polling. Treat `completed`, `failed`, `cancelled`, and `interrupted` as terminal. On network failure, preserve the last server state and attach a recoverable client error instead of changing the Job to failed.

Keep the upload control available on the processing/task surface so B can be submitted while A owns the slot. When exactly one Job completes and no other Job is active/waiting, retain the current automatic transition into the workbench. With multiple Jobs, keep the queue visible and expose an `Open Patch` button per completed Job.

- [ ] **Step 5: Make all processing states truthful**

Add `extracting` between separation and patchifying in `UploadingView` now so the queue slice is forward-compatible with Material Pipeline V1. For `failed` and `interrupted`, freeze prior completed stages and render a terminal explanation; do not collapse all stages to pending.

- [ ] **Step 6: Style responsive queue cards**

Reuse existing Creator workspace borders, monospace metadata, and state colors. At narrow container widths, stack capacity metrics and job facts without truncating filename or Job ID.

- [ ] **Step 7: Run Web unit tests and build**

Run:

```bash
cd apps/web
npm test
npm run check-contract
npm run build
```

Expected: all Vitest tests pass, contract outputs do not drift, and Vite build succeeds.

---

### Task 7: Cross-Stack Regression and Requirement Evidence

**Files:**
- Modify: `docs/superpowers/2026-07-10-status-and-backlog.md`
- Create: `docs/release-evidence/2026-07-26-upload-job-visibility.md`

**Interfaces:**
- Consumes: all completed queue-slice behavior
- Produces: verification evidence tied to the eight acceptance criteria

- [ ] **Step 1: Run Python package regressions**

Run:

```bash
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run repository smoke**

Run: `scripts/dev.sh smoke`

Expected: testsong produces a schema-valid `patch.json` and summary.

- [ ] **Step 3: Exercise real API/Web behavior**

Start the API and Web with the repository dev command, submit two short supported files, and verify:

- capacity displays `最大并发 1 · 正在处理 1 · 等待 1`;
- B remains queued until A completes;
- refresh restores both browser-owned tasks;
- restarting API changes any old nonterminal task to `interrupted`;
- resubmitting one submission ID returns the original Job ID;
- a completed Job opens and plays through the existing Patch loader.

Record exact commands, commit SHA, browser viewport, and observed Job IDs in release evidence.

- [ ] **Step 4: Review the final diff and commit**

Inspect only files changed for this queue slice, verify no unrelated work is staged, and create one Conventional Commit:

```bash
git add \
  workers/audio/lmdj_audio_worker/status.py \
  workers/audio/lmdj_audio_worker/job.py \
  workers/audio/tests/test_status.py \
  workers/audio/tests/test_job.py \
  apps/api/lmdj_api/executor.py \
  apps/api/lmdj_api/job_catalog.py \
  apps/api/lmdj_api/app.py \
  apps/api/tests/test_executor.py \
  apps/api/tests/test_job_catalog.py \
  apps/api/tests/test_app.py \
  apps/web/src/api/client.ts \
  apps/web/src/api/client.test.ts \
  apps/web/src/jobs/storage.ts \
  apps/web/src/jobs/storage.test.ts \
  apps/web/src/ui/JobQueuePanel.tsx \
  apps/web/src/ui/JobQueuePanel.test.tsx \
  apps/web/src/ui/ProcessingPanel.tsx \
  apps/web/src/ui/SourcePanel.tsx \
  apps/web/src/ui/UploadPanel.tsx \
  apps/web/src/ui/UploadingView.tsx \
  apps/web/src/ui/App.tsx \
  apps/web/src/ui/App.test.tsx \
  apps/web/src/ui/theme.css \
  docs/superpowers/2026-07-10-status-and-backlog.md \
  docs/plans/2026-07-26-upload-job-visibility.md \
  docs/release-evidence/2026-07-26-upload-job-visibility.md
git commit -m "feat(api): make upload queue visible and recoverable"
git show --stat --oneline HEAD
git status --short --branch
```

Expected: one verified atomic queue-slice commit on the short-lived branch, with unrelated work untouched.
