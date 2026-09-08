# Web Terminal ACK Interleaving Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Issue #166's responsive packaged Chromium regression accept every legal terminal-ACK scheduling order while continuing to prove once-only native completion consumption, terminal cleanup, and unchanged Project Truth.

**Architecture:** Keep the production Web Runtime Host and its native terminal state machine unchanged. Strengthen the Python source-boundary test so it extracts the complete responsive cancellation case and rejects any scheduler-dependent `rejectedConsumes` cardinality, then make the smallest browser-spec change that satisfies that contract while preserving the packaged browser safety proof.

**Tech Stack:** Python 3 source-boundary checks, Playwright JavaScript tests, packaged Chromium, Emscripten Web Runtime Host tooling, Bash verification entry points.

## Global Constraints

- Implement only on a fresh `fix/issue-166-terminal-ack-interleaving` branch and isolated worktree based on the then-current `origin/main`; never modify or commit implementation on `main` or the documentation branch.
- The implementation tracked code/test payload is exactly `apps/web-runtime-host/test/web_host_source_boundary_test.py` and `tests/platform/web/host/web_runtime_host_browser.spec.mjs`.
- Do not modify `packages/web-runtime-platform/`, `apps/web-runtime-host/src/`, manifests, Product Assembly, Assembly Lock, Architecture Portal pages or snapshots, CI/queue workflows, release state, deployment state, or Channel state.
- Add the source-boundary contract and observe its expected RED before changing the browser spec.
- Preserve all thirteen safety invariants in the approved spec: cancellation wins before publication; terminal transport state; exact attack inputs; a real Worker ACK; one accepted consume; explicit replay `-1`; one accepted consume after replay; released terminal owner; no publication claim; unchanged direct OPFS inventory; no late messages; unchanged reopened Truth and inventory; and formal cleanup of the terminal owner and reopened page.
- If any safety invariant fails in the real packaged browser proof, stop with `NEEDS_CONTEXT` and return to product concurrency design. Do not broaden this Task into production code.
- Version impact: none. This Task changes test expectations only and does not change product behavior, public API/ABI, Contract, Module, Host, Provider, Product Build, Product Assembly, dependency, or runtime bytes.
- Documentation impact: none. No Architecture Portal fact, route, source diagram, or immutable snapshot changes; `scripts/architecture-portal.sh check` still gates the commit.
- Each Task is one reviewable Conventional Commit. Verify before committing, stage only the two declared implementation files, inspect `git diff --cached --name-status` and `git diff --cached --check`, then inspect the committed file list and final worktree status.
- This plan authorizes local commits only. It does not authorize push, Pull Request creation, merge-queue labeling, merge, tag, Release, publication, deployment, or Channel promotion.

---

## Current Evidence

- GitHub Actions run `31874142167`, head `a71c62d43c4567daf856eab13f26ebcb5e1b30b3`, failed the packaged Chromium case `Chromium packaged responsive cancellation wins before mutation publication` because `[0, 2]` did not contain the legal `rejectedConsumes == 1` interleaving.
- The same native completion still had exactly one successful consumer. The failure did not report duplicate cleanup, an unreleased owner, mutation publication, Project Truth drift, OPFS drift, or late messages.
- At the planning baseline `origin/main` is `b84dd33023056cb7cee1cb5cae2ece49cc52e2be`, Issue #166 is open, and the browser spec still contains the scheduler-dependent `[0, 2]` assertion.

## File Structure

- Modify `apps/web-runtime-host/test/web_host_source_boundary_test.py`: extract the full responsive cancellation browser-test body and fail closed unless the approved causal proof remains present and all `rejectedConsumes` cardinality disappears from that body.
- Modify `tests/platform/web/host/web_runtime_host_browser.spec.mjs`: remove only the responsive case's automatic rejection count bookkeeping and assertion; keep the shared attack helper and unresponsive case unchanged.

### Task 1: Stabilize the responsive terminal-ACK proof

**Files:**
- Modify: `apps/web-runtime-host/test/web_host_source_boundary_test.py`
- Modify: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`
- Test: `apps/web-runtime-host/test/web_host_source_boundary_test.py`
- Test: `tests/platform/web/host/web_runtime_host_browser.spec.mjs`

**Interfaces:**
- Consumes: the named Playwright case `Chromium packaged responsive cancellation wins before mutation publication`, `terminalAckAttackEvidence(owner)`, `replayConsumedTerminalAck(owner)`, `terminalTransportEvidence(owner)`, `deadlineProofState(owner, requestId)`, and `opfsInventory(page)`.
- Produces: a source-boundary contract that requires one accepted native consume both before and after an explicit rejected replay, and a packaged browser proof with no automatic rejection-cardinality contract.

- [ ] **Step 1: Add the failing responsive source-boundary contract**

Insert the following block after the diagnostic test timeout checks and before the existing `unresponsive_cancellation` extraction in `apps/web-runtime-host/test/web_host_source_boundary_test.py`:

```python
    responsive_cancellation = re.search(
        r'test\("Chromium packaged responsive cancellation wins before '
        r'mutation publication".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        responsive_cancellation is not None,
        "responsive terminal-ack proof is missing",
    )
    responsive_body = responsive_cancellation.group(0)
    replay = responsive_body.find(
        "expect(await replayConsumedTerminalAck(owner)).toBe(-1)"
    )
    accepted_consumes = [
        match.start()
        for match in re.finditer(r"acceptedConsumes:\s*1", responsive_body)
    ]
    require(
        "forgedAcksSent: 2" in responsive_body
        and "duplicateReleaseRequestsSent: 2" in responsive_body
        and "observedWorkerAcks: 1" in responsive_body
        and replay >= 0
        and any(position < replay for position in accepted_consumes)
        and any(position > replay for position in accepted_consumes),
        "responsive terminal-ack proof must preserve the exact attack, real "
        "Worker ACK, one accepted consume, and deterministic replay rejection",
    )
    require(
        responsive_body.count("claimAttempted: false") == 2
        and 'publication: "cancelled"' in responsive_body
        and 'error: { code: "HOST_TIMEOUT" }' in responsive_body
        and '"restart-required"' in responsive_body
        and 'newSubmitCode: "HOST_TIMEOUT"' in responsive_body
        and "terminated: true" in responsive_body
        and "terminalOwnerReleased: true" in responsive_body,
        "responsive terminal-ack proof must preserve cancellation-before-claim "
        "and terminal owner cleanup",
    )
    require(
        "opfsInventory(owner)" in responsive_body
        and "toEqual(inventoryBefore)" in responsive_body
        and "late messages" in responsive_body
        and "toEqual(observationsBefore)" in responsive_body
        and 'window.lmdjWebRuntimeController.close()' in responsive_body
        and "project_revision, selected.name).toBe(0)" in responsive_body
        and "expect(after, selected.name).toEqual(before)" in responsive_body
        and "opfsInventory(reopened)" in responsive_body,
        "responsive terminal-ack proof must preserve OPFS, late-message, "
        "reopen Truth, and clean-close recovery evidence",
    )
    require(
        "rejectedConsumes" not in responsive_body,
        "responsive terminal-ack proof must not assert scheduler-dependent "
        "rejection cardinality",
    )
```

- [ ] **Step 2: Run the source-boundary contract and verify RED**

Run:

```bash
scripts/web-runtime-host.sh build
```

Expected: non-zero exit with `web Host source boundary: FAIL: responsive terminal-ack proof must not assert scheduler-dependent rejection cardinality`. If it fails first for a missing approved safety token, correct the guard to recognize the existing equivalent evidence without weakening the spec requirement; do not edit the browser test yet.

- [ ] **Step 3: Remove only scheduler-dependent rejection bookkeeping from the responsive case**

Replace the responsive attack assertion block in `tests/platform/web/host/web_runtime_host_browser.spec.mjs`:

```javascript
      const attackEvidence = await terminalAckAttackEvidence(owner);
      expect([0, 2]).toContain(attackEvidence.rejectedConsumes);
      expect(await replayConsumedTerminalAck(owner)).toBe(-1);
      expect(await terminalAckAttackEvidence(owner)).toMatchObject({
        acceptedConsumes: 1,
        rejectedConsumes: attackEvidence.rejectedConsumes + 1,
      });
```

with:

```javascript
      expect(await replayConsumedTerminalAck(owner)).toBe(-1);
      expect(await terminalAckAttackEvidence(owner)).toMatchObject({
        acceptedConsumes: 1,
      });
```

Do not change `terminalAckAttackEvidence()`, the unresponsive cancellation case, any timeout, any production source, or any other assertion in the responsive case.

- [ ] **Step 4: Run the source-boundary and normal packaged GREEN checks**

Run:

```bash
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh proof
```

Expected: both commands exit `0`; the build prints `web Host source boundary: PASS`, and proof passes the formal `CONFORMANCE=OFF` packaged distribution in Chromium, including the responsive cancellation case.

- [ ] **Step 5: Run three consecutive proofs under one Linux contention session**

On a pinned-Web-toolchain Linux runner, start CPU and file-I/O contention once, keep the same stress processes alive across all three proofs, and record runner identity, exact implementation commit/tree, command lines, timestamps, and exit statuses. One acceptable session shape is:

```bash
runner_identity="$(hostname -f) $(uname -srmo)"
implementation_tree="$(git write-tree)"
session_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
yes > /dev/null & cpu_pid=$!
stress_file="$(mktemp)"
while :; do dd if=/dev/zero of="$stress_file" bs=1M count=64 conv=fsync status=none; done & io_pid=$!
for proof_run in 1 2 3; do
  proof_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  scripts/web-runtime-host.sh proof
  proof_status=$?
  proof_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%s run=%s start=%s end=%s status=%s\n' \
    "$runner_identity" "$proof_run" "$proof_started" "$proof_finished" "$proof_status"
  test "$proof_status" -eq 0 || break
done
kill "$cpu_pid" "$io_pid"
wait "$cpu_pid" "$io_pid" 2>/dev/null || true
rm -f -- "$stress_file"
session_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'tree=%s session_start=%s session_end=%s\n' \
  "$implementation_tree" "$session_started" "$session_finished"
```

Expected: the same session runs proofs `1`, `2`, and `3` consecutively and all exit `0`. Do not select three passing runs from a larger sample. The responsive case must not fail any `acceptedConsumes: 1`, explicit replay `-1`, terminal owner, late-message, Project Truth, or OPFS recovery assertion.

- [ ] **Step 6: Run repository-wide non-product regression gates**

Run:

```bash
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

Expected: all four commands exit `0`; version checks report no identity movement and the Portal check reports no current-truth drift.

- [ ] **Step 7: Audit the approved scope and safety evidence**

Run:

```bash
git diff --name-only origin/main...HEAD
git diff --name-only
rg -n "rejectedConsumes|acceptedConsumes|replayConsumedTerminalAck|terminalOwnerReleased|claim_attempted|opfsInventory|late messages|project_revision" \
  tests/platform/web/host/web_runtime_host_browser.spec.mjs \
  apps/web-runtime-host/test/web_host_source_boundary_test.py
```

Expected: the implementation worktree adds no production-file changes; the only unstaged implementation files are the two declared files; `rejectedConsumes` remains only in shared/unresponsive evidence and is absent from the extracted responsive body; every approved responsive safety invariant has direct browser assertion and source-boundary evidence.

- [ ] **Step 8: Commit the atomic implementation Task**

Run:

```bash
test "$(git branch --show-current)" = "fix/issue-166-terminal-ack-interleaving"
git add apps/web-runtime-host/test/web_host_source_boundary_test.py \
  tests/platform/web/host/web_runtime_host_browser.spec.mjs
git diff --cached --name-status
git diff --cached --check
git commit -m "test(web): stabilize terminal ack interleaving proof"
git show --name-status --format=oneline HEAD
git status --short --branch
```

Expected: the staged and committed file lists contain exactly the two declared implementation files; the commit succeeds; the final implementation worktree is clean and ahead of its base only by the approved local commits.

## Remote Acceptance Boundary

Local completion proves `planned`, `implemented`, and locally verified only. Issue #166 cannot be reported as remotely accepted or closed until a separately authorized push and Pull Request obtain the current `web_runtime_host` lane, a same-run successful `PR Gate`, review approval, and exact-head/base Integration Queue validation after an authorized `merge:queue` label. None of those remote mutations is part of this plan's local implementation authorization.

## Version Management

Version impact: none

Reason: the implementation removes a scheduler-dependent assertion from a packaged test and adds a test-boundary guard. It does not alter runtime bytes, public behavior, Product Build, Assembly, Module, Host, Provider, Contract, dependency, or manifest identity.

## Documentation Impact

Documentation impact: none

Reason: the terminal state machine, cleanup behavior, Project Truth, OPFS recovery, proof command, and Architecture Portal facts remain unchanged. The approved design spec and this implementation plan are process records, not Portal current pages or immutable Product snapshots.
