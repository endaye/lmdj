# TSan runtime prerequisite under an unprivileged runner

Relates to #782 and #827. The existing sysctl-read classification fix (#821)
correctly preserves debt but requires the runner to read a root-only kernel
interface. [Linux mmap_table](https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux.git/+/52f37fd9f4dc93733c910282e761732f45f2921c/mm/mmap.c)
declares mmap_rnd_bits with mode 0600. The local non-root
reproduction reports root:root 0600 and permission denied without a runner
systemd sandbox. Live netcup job logs show the same failure before any tests.

## Task and declared files

- `.github/workflows/core-nightly.yml`
- `tests/build/ci_nightly_workflow_test.py`
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- `.agents/pitfalls/tsan-runner-runtime-compatibility.md`
- `docs/plans/2026-09-08-lmdj-ci-tsan-runtime-preflight.md`

Compile a minimal joined-thread program with the pinned Clang 22, shared TSan
runtime and compiler-provided rpath used by Core. Require ten successful starts,
as prescribed by sanitizer-runtime-silent-start-failure; stop on the first
failure rather than retrying it. Bound each startup to ten seconds to avoid
hanging a prerequisite on a broken runtime. No existing timeout is widened.
Compiler, runtime-directory and startup failures retain infrastructure output
and verification debt. The full product stress command remains unchanged.
This gate catches inability of the actual runner user to start the pinned
runtime. It grants no test pass and makes no host setting or permission change.

The Task-specific baseline had 13 passing contract tests but the actual ordinary
user sysctl read failed. Regression fixtures run the embedded shell and strict
compiler stand-in, then project its actual output into scoped batch debt.

## Verification

Lowest tier: `python3 tests/build/ci_nightly_workflow_test.py`.
Verify compilation failure, silent startup failure, a tenth-start failure,
timeout exit status, ten successful starts, and the far-side infrastructure
debt adapter; retain the existing full-stress routing checks.
Run staged ownership, whitespace checks, workflow lint and portal check because
this changes the documented CI prerequisite. Host SSH inspection is unavailable:
netcup01 has no configured alias and DNS resolution failed. No live host or
Actions dispatch was performed. Local compiler startup is not runnable because
clang++-22 is absent; this cannot establish live TSan execution or clear debt.

## Version Management

Version impact: none — CI runtime prerequisite only, no product identities.

## Documentation Impact

Documentation impact: required — update the documented runtime prerequisite.
Affected portal pages: /operations/testing-and-proof
The existing runner prerequisite pitfall records this recurrence.

## Recorded results

- Nightly workflow contracts: 15 passed, including source-write failure.
- Actual local prerequisite: exit 1, clang++-22 unavailable, exact
  `infrastructure_failure=true` output; no product test claim.
- Initial Portal check lacked dependencies. After lockfile-based `npm ci`,
  65 Node tests passed; validate:docs exposed the pre-existing release marker v3
  misclassification on /operations/version-and-release. A separate prerequisite
  Task corrects the internal marker wording without weakening the validator.
  Dependency: 57dd7c6f (cherry-picked from 16762412).
- Workflow actionlint passed with the existing exact `queue` syntax exception.
- Independent review caught an unguarded probe-source write; it now emits the
  infrastructure flag on failure and has a regression fixture.

- Staged ownership: 66 tests passed, including every tracked path ownership.
- Final full Portal check with the separate prerequisite commit passed: Node
  tests, docs, diagrams, facts, release snapshot provenance, typecheck,
  production build, and 42 routes/internal links.
- Independent final review found no remaining blocking code findings. Actual
  remote TSan startup/stress remains unexecuted in this Task.
