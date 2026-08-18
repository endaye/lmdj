# Machine Task TODO — 2026-08-17

Everything a coding agent can complete without a human in the loop. Its
companion is [`2026-08-17-manual-verification-todo.md`](2026-08-17-manual-verification-todo.md),
which holds the verifications and decisions that require a person. Between them
the two lists cover every open item in
[`2026-08-16-outstanding-work-before-stage9.md`](2026-08-16-outstanding-work-before-stage9.md),
which stays the canonical triage record; these two are the working lists.

Compiled against `main` at `801fa450` on 2026-08-17.

## Rules that apply to every task here

- Each task needs its own plan under `docs/superpowers/plans/` with a
  `## Version Management` section before implementation starts, per
  `CLAUDE.md`. Several tasks below already have one; the rest do not.
- Each task is one reviewable Conventional Commit on its own
  `feat/` / `fix/` / `docs/` branch in an isolated worktree. Never on `main`.
- A task marked **blocked** must not be started by inventing the missing
  decision. Take it to the decision row named in its Blocked-by column.
- Local commits are autonomous. Push, Pull Request, merge, tag, Release,
  publication, deployment and Channel promotion each need separate explicit
  authorization.

---

## Ready — no decision needed

| ID | Task | Source | Shape |
| --- | --- | --- | --- |
| ~~B1~~ | ~~Make `audit` assert `main` ancestry, matching what `prepare` already requires~~ | triage B1 | **done 2026-08-18** (`33dbff7c`). Narrower than triage stated: ancestry was already asserted after a remote tag existed; the gap was the two pre-mutation paths. Abandoned and superseded-unreleased intents stay ungated by design |
| ~~B2~~ | ~~Emit the Portal snapshot witness on the merge path, or make the failure name the exact command that resolves it~~ | triage B2 | **done 2026-08-18** (`edb16910`). The first option is impossible by construction — the witness records a revision that exists only after the merge, and must itself be committed. The failure now carries the command, and the command derives its second argument |
| B3 | Derive Product Build identity wherever a gate can read committed truth; where a literal is unavoidable, make its failure message name the version | triage B3 | seven hand-maintained locations; none of the failures named a version. Two were converted during Stage 8, the rest remain literal |
| B4 | Fold `assembly.lock.json` regeneration into whatever writes the compiled assembly, or make `version.py lock` refuse to run before the source is final | triage B4 | bit twice in one allocation; the second time surfaced only at the portal freeze |
| C2 | Restructure `decision-log.md` and `open-questions.md` so concurrent branches stop colliding — dated section files with an index, or an append convention that keeps additions apart | triage C2 | both files are append-at-the-end; every parallel session conflicts |
| C4 | Give `project_store.cpp`'s JSON read paths the `O_NOFOLLOW` symmetry `read_artifact()` already has | 2026-08-03 backlog C2, still open | small, mechanical, security-shaped |
| C5 | Make `scripts/architecture-portal.sh witness` refuse an existing witness file cleanly instead of throwing an unhandled `EEXIST` rejection | found while closing B2, 2026-08-18 | `create-squash-witness.mjs:41` is the only `wx` write in the script family, and it is the outlier: `version-docs.mjs:123` and `snapshot-provenance.mjs:394` both refuse with a named error. **Keep the refusal** — `wx` is what stops a witness being silently overwritten; only its presentation is wrong. Now easier to hit, since B2 made this the routine remedy command |
| E2 | Add a range parameter to `CaptureBuffer.envelope(bins)` | triage E2 | only when waveform zoom is actually built; a narrow window at the same bin count currently falls back to the exact path and rescans the whole buffer |
| E3 | Add invalidation to the incremental block peaks in `append()` | triage E3 | only when pre-commit buffer editing is actually built |

**C1 is deliberately not in this table.** The `application-facade` coverage
threshold sits at 84.00% against a measured 84.04% that moves ±4 lines between
runs on identical source, so any PR can be stopped at random. The fix — move
the threshold below the observed floor, or exclude the nondeterministic paths
from measurement — is a judgement about what the gate is for, so it is listed
under **Ready, but state the reasoning** below rather than as a free mechanical
change.

### Ready, but state the reasoning in the plan

| ID | Task | Why it needs an argument, not just a diff |
| --- | --- | --- |
| C1 | Stabilise the `application-facade` coverage gate | Choosing between lowering the threshold and excluding paths changes what the gate can still catch. A genuine 4-line regression is currently indistinguishable from noise, so whichever option is taken must say what it gives up |

---

## Ready — plan already written

| ID | Task | Plan | Status |
| --- | --- | --- | --- |
| F1 + F2 | Capture panel presentation, position and focus | [Creator UI remediation](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md) Task 2 | blocked on P2 |
| F5 | Replace the trim handle pointer model | same plan, Task 3 | blocked on P2 |
| F3 | Recoverable presentation for `DUPLICATE_ID` | same plan, Task 4 | blocked on P2 |
| — | Design gate for the above | same plan, Task 1 | **this is P2** — a person decides, the agent records |

The whole plan is one branch's worth of work once P2 lands. Its Task 5 hands
back to the human list.

---

## Blocked on a decision

Listed so nothing is lost. Each becomes machine work the moment its decision
row is answered.

| ID | Task | Blocked by |
| --- | --- | --- |
| F1, F2, F3, F5 | Creator UI remediation Tasks 2–4 | P2 |
| F4 | Whatever the device/silence resolution turns out to be | F4 decision |
| F6 | Amplitude ramp in the render path, under a realtime-safety review | F6 decision |
| A2 | Rename `native-test-host` and change the Assembly, **or** remove it from the Assembly and every distribution and return it to `tests/`; either way, write the rule for what may enter a distribution package | A2 decision |
| A3 | Reshape the published artifacts to whichever reproducibility option is chosen | A3 decision |
| D1, D2 | Cooker Bank allocation, `PreparedSampleBank` publication layout, manifest semantics, Facade validation, and a new "quota consumed by another Pad" failure class | D1 + D2 decision |
| D3 | Schema provenance on `ArtifactRef` and an input resolver on `AttemptStore`; retire the prototype's Host-injected bridge rather than graduating it | D3 decision |
| D4, D5 | Sequence/Take Contract implementation | D4 + D5 decision — this is Stage 9 |

---

## Suggested order

1. ~~**B1 + B2**~~ — done 2026-08-18 on `fix/release-audit-ancestry`, plan
   [`2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md`](../superpowers/plans/2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md).
2. **C1** — cheap, and it stops random PR failures polluting every future
   signal. Now the top of the ready queue.
3. **The Creator UI remediation branch** — the moment P2 lands. Four findings,
   one branch, and it is what makes Pad Capture usable by hand.
4. **C2** — every parallel branch pays for this one today.
5. **B3, B4, C4, C5** — mechanical hardening, schedule as capacity allows. C5
   is the smallest of them and sits in the path operators now walk on every
   snapshot-carrying Build.
6. **E2, E3** — only when the feature that needs them is actually built.

Everything else waits on a decision, not on capacity.
