# LMDJ CI Sanitizer and Stress Gate Implementation Plan

**Goal:** Put the Apple-only audio sources and the realtime concurrency stress
test back under a PR-blocking gate, and state the RealtimeEngine thread
contract where its callers can read it.

**Architecture:** Every sanitizer and coverage job runs on Linux, so the
Apple-only CoreAudio sources are compiled out of all of them and reach PRs only
through the plain macOS Release Proof. Both stress tests are excluded from
every PR-blocking job by tier filter, so the newest lock-free primitive cannot
block a merge. This plan adds a macOS sanitizer job and an explicit stress step
without changing any Module API, Contract, or Product identity.

Origin: `docs/quality/2026-08-03-review-backlog.md` unit A, covering
`2026-08-03-build-1.0.10.0-review.md` findings 1, 2, and 3 (partial), and
`2026-08-03-build-1.0.7.0-review.md` finding 4.

## Tasks

- [ ] Add a `core-asan-macos` job so the Apple-only sources are compiled and
  executed under `-fsanitize=address,undefined`.
- [ ] Add an explicit stress step to both sanitizer jobs so
  `facade.c_api_stress` and `audio.realtime_spsc_stress` block a PR.
- [ ] Document the `scripts/core.sh test` tier modes in `AGENTS.md` and
  `CLAUDE.md`, which still present the bare command as if it ran everything.
- [ ] State the RealtimeEngine calling-thread contract on the public header.
- [ ] Run the Task-specific verification.

## Non-goals

- The `coverage` preset keeps excluding `audio.realtime_spsc_stress`.
  Coverage instrumentation perturbs the timing the test exists to exercise;
  the sanitizer jobs are the correct home for it.
- TSan stays nightly and Linux-only. TSan support for Apple frameworks is
  limited, so this plan does not claim race detection for CoreAudio.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

**Version impact: none.**

- Product Build: unchanged. No Assembly member, Host protocol, or runnable
  Product behavior changes.
- Core Modules: unchanged. The only source edit is a comment block on
  `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`; no
  declaration, signature, or generated symbol changes, so `audio-runtime`
  stays `0.3.0` and its API generation stays 1.
- Contracts, Providers, and Models: unchanged.
- Remaining files are CI workflow and repository documentation, which carry no
  version identity.
- No tag, Release, Channel promotion, or deployment is authorized by this plan.
