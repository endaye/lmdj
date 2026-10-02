# P1 first gesture and current main layout convergence

## Scope

Resolve the actual hardware-layout journey conflict between P1 T1 4472f50e and current main 96b015a3769ea83b7a2e351a95051d712ba1de44. Retain main's centre and short-scrollport assertions and P1's absent activation gate plus accessible touch-workspace scroll target. Preserve the rest of the current main merge, including the Sequence grid and existing authoring history. This Task resolves a real conflict; it does not require unrelated future main updates.

## Declared files

- `.agents/pitfalls/asan-macos-fork-child-stack-depot-boundary.md`
- `.agents/pitfalls/local-ci-list-names-batch-lanes.md`
- `.agents/pitfalls/revert-proof-rebuild-skipped.md`
- `.agents/skills/issue-done/SKILL.md`
- `.github/workflows/pr-review.yml`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/sequence_grid.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/runtime/project_actions.ts`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/state/creator_state.ts`
- `apps/creator-web/src/state/sequence_grid_model.ts`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/creator_state.test.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/sample_state.test.ts`
- `apps/creator-web/test/sequence_grid.test.tsx`
- `apps/creator-web/test/sequence_grid_model.test.ts`
- `apps/creator-web/test/sequence_pattern_overview.test.tsx`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/shell_polish.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/governance/minimization-principle.md`
- `docs/plans/2026-10-02-creator-p1-first-gesture-main-layout.md`
- `scripts/ci/pr-agent/runtime.toml`
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_scope.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`

## Task verification

Stage the exact declared files and capture the tested index tree. Run the complete Creator unit suite and TypeScript, staged ownership scope tests and complete portal check. The complete packaged Creator proof must preserve the hardware layout centre, short viewport reachability, absent activation button and every existing journey leg. After commit rederive the checkout's production input plan. Authenticate any reused complete lane evidence only by identical current input keys; rerun changed inputs. The checks catch lost main behavior, an activation-gate regression, incompatible state/Sequence composition, unowned paths, render/link regressions and stale proof reuse.

The original 45c Linux Creator and macOS Runtime proofs passed. Earlier macOS Creator failures and original traces remain retained. The new merge may change proof inputs and cannot claim those old passes without checking equality. Independent review, finding disposition, live conversations and protection remain separate obligations.

## Version Management

Version impact: none. Preserve identities already allocated by current main. Coordinated P1 Host and Assembly allocation belongs to the integration Task. No new Product Build or snapshot is allocated here; existing immutable snapshots remain unchanged.

Documentation impact: required
Reason: retain current main's Sequence grid and P1 Pad-gesture guidance together in the Creator page, with current main governance documentation preserved.
Affected portal pages: /hosts/creator-web/
