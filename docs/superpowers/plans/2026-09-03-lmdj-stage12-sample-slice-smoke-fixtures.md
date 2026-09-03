# LMDJ Stage 12 `sample.slice` Smoke Fixture Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deterministic, rights-cleared `sample.slice` smoke corpus
with exact onset ground truth, explicit match tolerance, and fail-closed input
scenarios so #467 can review the first formal Capability and later run Provider
conformance against stable bytes.

**Architecture:** A proprietary Python generator under `tools/` creates a small
set of mono PCM16 WAV inputs and one canonical JSON manifest under
`tests/fixtures/provider-benchmark/sample-slice/`. The generated WAV and
manifest bytes alone are dedicated under CC0-1.0; the generator, tests, and the
rest of the repository remain governed by the root proprietary license. A
Python contract test regenerates the corpus into a temporary directory,
compares every byte and SHA-256 digest, validates the closed scenario inventory,
and is registered in the Core contract tier.

**Tech Stack:** Python 3.11 standard library (`argparse`, `hashlib`, `json`,
`math`, `struct`, `tempfile`, `unittest`, `wave`), CMake/CTest, JSON, PCM16 WAV,
Git LFS.

**Spec:**
`docs/superpowers/specs/2026-08-31-lmdj-stage12-provider-benchmark-design.md`

## Global Constraints

- This is the first implementation slice of #466 and must not close #466.
  Benchmark host execution, report schema, subprocess/remote measurement,
  Stem/Pattern corpora, and blind-review packages remain later reviewable
  Tasks.
- Generate every audio byte locally from fixed integer parameters. Do not copy,
  download, record, or derive from third-party audio, model output, or
  `references/demos/`.
- The CC0-1.0 dedication covers only generated `*.wav` and `manifest.json` files
  below `tests/fixtures/provider-benchmark/sample-slice/`. It does not cover
  generator source, tests, plans, or any other repository material.
- `sample.slice.v1` and `lmdj.slice-points.v1` remain #467 draft authority. This
  Task records input bytes and onset ground truth only; it creates no Capability
  instance, Contract schema, output JSON fixture, Provider, Candidate, Project,
  Facade, Assembly, or Product identity.
- WAV success inputs are RIFF/WAVE PCM integer, mono, 16-bit, 48,000 Hz. Ground
  truth uses zero-based integer frame indexes plus an explicit per-scenario
  `tolerance_frames`; a predicted onset matches a truth onset only when the
  absolute frame distance is at most that value. #467 conformance and the later
  benchmark host consume the recorded tolerance and must not invent their own.
- Failure reasons follow the `details.reason` vocabulary of the #467 draft
  (`2026-08-31-lmdj-stage12-capability-artifactsource-design.md`, S12C-D4) and
  are assigned at the layer that actually detects them. WAV-header defects are
  decoder-level `source_audio_unsupported`. The SDK staging reason
  `input_artifact_too_large` depends on the resource limit #467 has not yet
  locked, so that scenario belongs to #467 conformance after its Contract
  review and is not represented by a lying WAV header or a provisional limit
  in this Task.
- Manifest paths are repository-relative POSIX paths. They contain no absolute
  host paths, symlinks, URLs to fixture bytes, secrets, model paths, or mutable
  timestamps.
- Version impact: none. Fixture data, generator tooling, tests, and CI routing
  allocate no Product, Module, Host, Provider, Contract, Assembly, Channel, or
  snapshot identity.
- Documentation impact: none. The retained plan/spec status changes no current
  Architecture Portal fact or route; no current Portal page or immutable
  snapshot is changed.

---

### Task 1: Commit the deterministic `sample.slice` smoke corpus

**Issue boundary:** Create a child Task under #466 before implementation. The
child Issue owns only the files listed here and relates to #467; its completion
must not close either parent.

**Files:**

- Create: `tools/provider-benchmark/generate_sample_slice_smoke.py`
- Create: `tests/core/provider/stage12_fixture_corpus_test.py`
- Create: `tests/fixtures/provider-benchmark/sample-slice/LICENSE.md`
- Create: `tests/fixtures/provider-benchmark/sample-slice/manifest.json`
- Create: `tests/fixtures/provider-benchmark/sample-slice/slice-basic.wav`
- Create: `tests/fixtures/provider-benchmark/sample-slice/slice-close-overlap.wav`
- Create: `tests/fixtures/provider-benchmark/sample-slice/slice-silence.wav`
- Create: `tests/fixtures/provider-benchmark/sample-slice/slice-truncated.wav`
- Create: `tests/fixtures/provider-benchmark/sample-slice/slice-bad-header.wav`
- Modify: `CMakeLists.txt`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`

**Interfaces:**

- `tools/provider-benchmark/generate_sample_slice_smoke.py` exposes
  `build_corpus() -> tuple[dict[str, bytes], dict[str, object]]`. The first item
  maps the five WAV basenames to exact bytes; the second is the manifest object.
- Its CLI is
  `python3 tools/provider-benchmark/generate_sample_slice_smoke.py
  [--output-dir PATH] [--check]`. The default output directory is the committed
  fixture directory. Without `--check` it creates/replaces only its declared
  five WAV files plus `manifest.json`; with `--check` it writes nothing and exits
  nonzero if a declared file is absent, has different bytes, or an undeclared
  file other than `LICENSE.md` exists.
- `manifest.json` has the internal, non-Contract schema token
  `lmdj.provider-benchmark-fixtures.v1`, `capability: sample.slice`,
  `generator`, `license`, and a closed `scenarios` array. Each byte-bearing
  scenario records `id`, `class`, repository-relative `path`, `sha256`,
  `byte_length`, `expected`, and generation parameters. Success scenarios record
  `expected.onset_frames` and `expected.tolerance_frames`. The missing-input
  scenario omits `path`, `sha256`, and `byte_length` and records
  `expected.reason: input_artifact_unavailable`.
- The closed scenario IDs and meanings are:

  | Scenario | Class | Bytes | Required truth |
  | --- | --- | --- | --- |
  | `basic_three_onsets` | `success` | WAV | onset frames `[2400, 7200, 12000]`, tolerance `480` |
  | `close_overlapping_tails` | `success` | WAV | onset frames `[480, 1440]`, tolerance `240` |
  | `silence` | `success` | WAV | onset frames `[]`, tolerance `480` |
  | `missing_input` | `input_failure` | none | `input_artifact_unavailable` |
  | `truncated_data` | `input_failure` | WAV | `source_audio_unsupported` |
  | `bad_riff_header` | `input_failure` | WAV | `source_audio_unsupported` |

  Tolerances are in frames at 48,000 Hz: `480` is 10 ms; `240` is 5 ms and is
  deliberately tighter than half the 960-frame spacing of the close pair so
  that one detection cannot satisfy both onsets.

- All byte-bearing scenarios carry `origin: synthetic`,
  `spdx_license: CC0-1.0`, `sample_rate: 48000`, and `channels: 1` where those
  WAV properties are structurally meaningful. The manifest records the
  canonical CC0 URL
  `https://creativecommons.org/publicdomain/zero/1.0/` and names Zhang
  Yuancheng as the affirmer.
- `provider.stage12_fixture_corpus` is a CTest `contract`-tier test with labels
  `provider fixtures`; it invokes the Python test from the repository root.
- Change Scope routes `tools/provider-benchmark/` and
  `tests/fixtures/provider-benchmark/` to `core_ubuntu`, `core_asan`,
  `core_coverage`, and `core_macos`. The existing
  `tests/core/provider/` rule already owns the test. Update `CASES` in
  `tests/build/ci_change_scope_test.py` with one representative path for each
  new prefix.

- [ ] **Step 1: Write the fixture contract test first**

  Create `tests/core/provider/stage12_fixture_corpus_test.py` before the
  generator. The production change that makes the test pass is the declared
  generator plus committed corpus. Import the generator through
  `importlib.util.spec_from_file_location`, call `build_corpus()`, and cover:

  ```python
  class Stage12FixtureCorpusTest(unittest.TestCase):
      def test_scenario_inventory_is_closed(self):
          self.assertEqual(
              [item["id"] for item in self.manifest["scenarios"]],
              [
                  "basic_three_onsets",
                  "close_overlapping_tails",
                  "silence",
                  "missing_input",
                  "truncated_data",
                  "bad_riff_header",
              ],
          )

      def test_success_ground_truth_uses_exact_frames_and_tolerance(self):
          expected = {
              "basic_three_onsets": ([2400, 7200, 12000], 480),
              "close_overlapping_tails": ([480, 1440], 240),
              "silence": ([], 480),
          }
          observed = {
              item["id"]: (
                  item["expected"]["onset_frames"],
                  item["expected"]["tolerance_frames"],
              )
              for item in self.manifest["scenarios"]
              if item["class"] == "success"
          }
          self.assertEqual(observed, expected)

      def test_generated_bytes_match_committed_bytes_and_hashes(self):
          generated, manifest = self.module.build_corpus()
          for scenario in manifest["scenarios"]:
              path = scenario.get("path")
              if path is None:
                  continue
              contents = generated[Path(path).name]
              self.assertEqual(hashlib.sha256(contents).hexdigest(), scenario["sha256"])
              self.assertEqual(len(contents), scenario["byte_length"])
              self.assertEqual((ROOT / path).read_bytes(), contents)

      def test_generated_material_is_synthetic_and_cc0_only(self):
          self.assertEqual(self.manifest["license"]["spdx"], "CC0-1.0")
          self.assertEqual(
              self.manifest["license"]["canonical_url"],
              "https://creativecommons.org/publicdomain/zero/1.0/",
          )
          for scenario in self.manifest["scenarios"]:
              if scenario.get("path") is not None:
                  self.assertEqual(scenario["origin"], "synthetic")
                  self.assertEqual(scenario["spdx_license"], "CC0-1.0")
  ```

  Add separate tests that open the three success WAVs with `wave` and assert
  PCM16/mono/48 kHz, assert every `tolerance_frames` is a positive integer and
  is smaller than the minimum onset spacing whenever a scenario has two or
  more onsets, assert manifest paths are normalized repository-relative paths,
  assert the three input-failure scenarios above, and exercise CLI `--check`
  against a temporary missing file, changed file, and undeclared extra file.

- [ ] **Step 2: Run the test and verify RED**

  Run:

  ```bash
  python3 tests/core/provider/stage12_fixture_corpus_test.py
  ```

  Expected: FAIL because
  `tools/provider-benchmark/generate_sample_slice_smoke.py` does not exist.
  Do not satisfy RED by weakening the import or skipping when the generator is
  absent.

- [ ] **Step 3: Implement the deterministic generator and CC0 boundary**

  Implement WAV construction with integer-only PCM sample generation and
  explicit little-endian RIFF chunks. The success fixtures use fixed envelopes
  mixed at the exact onset frames; silence contains 4,800 zero frames. The
  truncated fixture removes bytes from a valid data chunk and the bad-header
  fixture replaces `RIFF`. Do not use random module state, NumPy, ffmpeg,
  network access, wall-clock time, or host paths.

  `LICENSE.md` must state that Zhang Yuancheng applies CC0 1.0 Universal only to
  the generated WAV files and generated `manifest.json` in that directory,
  link the canonical legal code, and explicitly state that source code and all
  other repository contents remain governed by the root `LICENSE`.

- [ ] **Step 4: Generate the committed corpus and verify GREEN**

  Run:

  ```bash
  python3 tools/provider-benchmark/generate_sample_slice_smoke.py
  python3 tools/provider-benchmark/generate_sample_slice_smoke.py --check
  python3 tests/core/provider/stage12_fixture_corpus_test.py
  ```

  Expected: all commands exit 0; the test reports every test passing. Confirm
  `git check-attr filter -- tests/fixtures/provider-benchmark/sample-slice/*.wav`
  reports `filter: lfs` for every WAV.

- [ ] **Step 5: Register the contract test and route its files**

  Add this root CMake registration after the existing provider test subtree:

  ```cmake
  lmdj_add_test(
    NAME provider.stage12_fixture_corpus
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      tests/core/provider/stage12_fixture_corpus_test.py
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider fixtures
  )
  ```

  Move `find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)` above this
  registration if necessary; do not add a second discovery call. Add the two
  exact Change Scope prefix rules and their representative `CASES` entries.

- [ ] **Step 6: Run focused and repository verification**

  Run:

  ```bash
  python3 -m unittest tests.build.ci_change_scope_test -v
  python3 tools/provider-benchmark/generate_sample_slice_smoke.py --check
  scripts/core.sh configure dev
  scripts/core.sh build dev
  ctest --preset dev -R '^provider.stage12_fixture_corpus$' --output-on-failure
  scripts/core.sh test dev full
  bash tests/build/test_active_tree.sh
  scripts/architecture-portal.sh check
  ```

  Expected: every command exits 0. `scripts/core.sh test dev full` must include
  the new contract-tier test. Confirm its named CTest invocation also ran once;
  do not infer fixture coverage from an unrelated green Core suite.

- [ ] **Step 7: Commit the implementation Task**

  Before committing, verify the branch is not `main`, stage only the declared
  Task files, inspect `git diff --cached --name-only`, and run
  `git diff --cached --check`. Commit exactly:

  ```text
  test(provider): add Stage 12 slice smoke fixtures (refs #466, #467)
  ```

  Inspect `git show --stat --oneline HEAD` and final `git status --short`. A
  local commit does not authorize push, Pull Request creation, merge, release,
  deployment, or Channel promotion.

## Version Management

Version impact: none.

Reason: this plan and its implementation add only synthetic fixture bytes,
tooling, tests, and CI ownership. They do not change a Product, Module, Host,
Provider, Contract, Assembly, Channel, model identity, or immutable snapshot.
The internal fixture-manifest schema token is test-tool metadata, not a shipped
Contract identity.

## Documentation Impact

Documentation impact: none.

Reason: approving the retained benchmark design and adding this retained plan
does not change current manifest-derived Architecture Portal truth. The fixture
Task changes no Portal route. #467 owns the later Capability/Provider SDK Portal
impact when those active identities are introduced.

## Acceptance and Remaining #466 Work

This plan is complete when the implementation Task produces the six closed
scenarios, per-scenario match tolerance, byte-for-byte reproducibility,
explicit CC0 provenance, Core-tier
registration, and passing verification above. That result unlocks #467's
consumer-driven Contract review but does not complete #466.

Keep #466 open for separately planned and reviewed work: the benchmark report
schema/validator; the `input_artifact_too_large` conformance scenario after #467
locks the `sample.slice.v1` resource limit; the production `AttemptStore` bench
host after #467; the subprocess and remote execution-zone controllers; Stem
and Pattern corpora after their own Contract/product decisions; retained
reports; and blind-review package generation. None of those may be folded into
this fixture Task.
