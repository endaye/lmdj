#!/usr/bin/env python3
"""Contract for the check that closes the `continue-on-error` blind spot.

The advisory review lanes fail quietly by design. This is the only thing that
notices when one of them stops working, so its own correctness matters more
than most: a liveness check that is wrong in the reassuring direction is worse
than none, because it converts an unmonitored lane into one everybody believes
is monitored.

The first two revisions of this check read the review step's conclusion. The
Actions API reports a `continue-on-error` step that exited 1 as `success` --
observed on every Grok run of 2026-09-05, all of which died `Not signed in`
behind a green step. The check now reads the effect instead: did the lane
sign anything on the Pull Request after the run began.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import contextlib
import io
import unittest
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".github/scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))

import advisory_review_liveness as liveness  # noqa: E402
import review_scope_codec as codec  # noqa: E402
from advisory_review_liveness import (  # noqa: E402
    CLAUDE_BACKENDS,
    REVIEW_LANES,
    LivenessUnavailable,
    Observation,
    select_backends,
    collect_observations,
    evaluate,
    evidence_posted,
    render,
)

SCRIPT = REPO_ROOT / ".github/scripts/advisory_review_liveness.py"
SCOPE_POLICY = REPO_ROOT / "scripts/ci/scope_policy.json"
WORKFLOW = REPO_ROOT / ".github/workflows/advisory-review-liveness.yml"
CLAUDE = REPO_ROOT / ".github/workflows/ci.yml"  # the review job lives here since #659
STANDALONE = REPO_ROOT / ".github/workflows/pr-review.yml"  # the T4 standalone entry
GROK_SCRIPT = REPO_ROOT / ".github/scripts/grok_review.py"

GLM = next(l for l in REVIEW_LANES if l.job.endswith("(glm)"))
KIMI = next(l for l in REVIEW_LANES if l.job.endswith("(kimi)"))
GROK_LANE = next(l for l in REVIEW_LANES if l.job.startswith("Grok"))


def fake_api(*, runs, jobs_by_run, comments_by_pr=None, review_comments_by_pr=None,
             reviews_by_pr=None):
    """An `_api` stand-in answering by path, in the shapes the REST API returns."""
    comments_by_pr = comments_by_pr or {}
    review_comments_by_pr = review_comments_by_pr or {}
    reviews_by_pr = reviews_by_pr or {}

    def api(path, context):
        if "/actions/workflows/" in path:
            import re as _re
            per = int(_re.search(r"per_page=(\d+)", path).group(1))
            # `[?&]` so this does not match the `page=` inside `per_page=`.
            page = int((_re.search(r"[?&]page=(\d+)", path) or [0, "1"])[1])
            return {"workflow_runs": runs[(page - 1) * per: page * per]}
        if "/actions/runs/" in path and path.endswith("/jobs"):
            run_id = int(path.split("/runs/")[1].split("/")[0])
            return {"jobs": jobs_by_run.get(run_id, [])}
        pr = int(path.split("/pulls/")[1].split("/")[0]) if "/pulls/" in path \
            else int(path.split("/issues/")[1].split("/")[0])
        if "/issues/" in path:
            return [{"body": b} for b in comments_by_pr.get(pr, [])]
        if path.split("?")[0].endswith("/comments"):
            return [{"body": b} for b in review_comments_by_pr.get(pr, [])]
        return [{"body": b, "submitted_at": "2026-09-05T23:59:59Z"}
                for b in reviews_by_pr.get(pr, [])]
    return api


def seen(outcome, at="2026-09-05T10:00:00Z"):
    """One observation, timestamped like `run()`'s default."""
    return Observation(outcome, at)


def run(run_id, pr, conclusion="success", created="2026-09-05T10:00:00Z"):
    return {"id": run_id, "conclusion": conclusion, "created_at": created,
            "pull_requests": ([{"number": pr}] if pr is not None else [])}


def attempted(step="success", job="success", lane=None):
    """One job entry shaped like the REST API's, named for `lane`."""
    lane = lane or GROK_LANE
    return [{"name": lane.job, "conclusion": job,
             "steps": [{"name": lane.step, "conclusion": step}]}]


class LivenessLogicTest(unittest.TestCase):
    def test_a_lane_failing_every_attempt_in_the_window_is_down(self) -> None:
        verdict = evaluate("lane", [seen("failure")] * 5, window=5)
        self.assertTrue(verdict.down)

    def test_one_success_in_the_window_is_not_down(self) -> None:
        verdict = evaluate("lane", [seen("failure"), seen("failure"), seen("success"), seen("failure"), seen("failure")], window=5)
        self.assertFalse(verdict.down)

    def test_too_few_observations_withholds_judgement(self) -> None:
        verdict = evaluate("lane", [seen("failure"), seen("failure")], window=5)
        self.assertFalse(verdict.down)
        self.assertIn("too few to judge", verdict.detail)

    def test_only_the_window_is_considered(self) -> None:
        verdict = evaluate("lane", [seen("failure")] * 5 + [seen("success")] * 20, window=5)
        self.assertTrue(verdict.down, "why: newest-first, so older successes are history; "
                        "remedy: slice to the window before counting")


class EffectDetectionTest(unittest.TestCase):
    """The signal is what the lane posted, because the API masks what it did."""

    def test_the_masked_failure_that_motivated_this_is_now_seen(self) -> None:
        """Every Grok run on 2026-09-05: step exit 1, API conclusion success, nothing posted."""
        api = fake_api(
            runs=[run(1, 662), run(2, 651), run(3, 633), run(4, 624), run(5, 623)],
            jobs_by_run={i: attempted("success") for i in range(1, 6)},   # the lie the API tells
            comments_by_pr={},                                              # the truth
        )
        obs = collect_observations("o/r", GROK_LANE, limit=5, api=api)
        self.assertEqual(obs, [seen("failure")] * 5,
                         "why: the step conclusion read success while the CLI exited 1 and "
                         "posted nothing, so a conclusion-reading check called this lane "
                         "healthy all day; remedy: judge an attempt by its effect on the PR")
        self.assertTrue(evaluate(GROK_LANE.name, obs, window=5).down)

    def test_a_signed_comment_after_the_run_began_is_success(self) -> None:
        api = fake_api(runs=[run(1, 10)], jobs_by_run={1: attempted()},
                     comments_by_pr={10: [f"{GROK_LANE.marker}\n# Grok advisory review"]})
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api), [seen("success")])

    def test_evidence_is_found_on_all_three_surfaces(self) -> None:
        since = "2026-09-05T10:00:00Z"
        self.assertTrue(evidence_posted("o/r", 1, since, "<!-- m -->", api=fake_api(
            runs=[], jobs_by_run={}, comments_by_pr={1: ["<!-- m -->"]})))
        self.assertTrue(evidence_posted("o/r", 1, since, "<!-- m -->", api=fake_api(
            runs=[], jobs_by_run={}, review_comments_by_pr={1: ["<!-- m -->\nfinding"]})))
        self.assertTrue(evidence_posted("o/r", 1, since, "<!-- m -->", api=fake_api(
            runs=[], jobs_by_run={}, reviews_by_pr={1: ["<!-- m -->"]})))
        self.assertFalse(evidence_posted("o/r", 1, since, "<!-- m -->", api=fake_api(
            runs=[], jobs_by_run={}, comments_by_pr={1: ["<!-- other -->"]})))

    def test_a_half_dead_matrix_is_seen_per_backend(self) -> None:
        """One backend dead, one alive, both posting under github-actions.

        Without a per-backend signature the live leg's comments would count as
        evidence for the dead leg, and the lane would read healthy however
        long the backend stayed broken.
        """
        api = fake_api(
            # After CLAUDE_SIGNS_SINCE, so the cutoff does not drop them.
            runs=[run(i, 100 + i, created="2026-09-09T10:00:00Z") for i in range(1, 6)],
            jobs_by_run={i: attempted(lane=GLM) + attempted(lane=KIMI) for i in range(1, 6)},
            review_comments_by_pr={100 + i: [f"{KIMI.marker}\nfinding"] for i in range(1, 6)},
        )
        self.assertTrue(evaluate(GLM.name, collect_observations("o/r", GLM, limit=5, api=api), window=5).down)
        self.assertFalse(evaluate(KIMI.name, collect_observations("o/r", KIMI, limit=5, api=api), window=5).down)
        self.assertNotEqual(GLM.marker, KIMI.marker)


class SilenceHandlingTest(unittest.TestCase):
    def test_a_cancelled_run_is_dropped(self) -> None:
        api = fake_api(runs=[run(1, 10, conclusion="cancelled"), run(2, 11)],
                     jobs_by_run={1: attempted(), 2: attempted()},
                     comments_by_pr={11: [GROK_LANE.marker]})
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api), [seen("success")],
                         "why: cancel-in-progress fires on every push and reached no verdict; "
                         "remedy: drop cancelled runs before judging")

    def test_a_skipped_job_or_step_is_dropped(self) -> None:
        api = fake_api(
            runs=[run(1, 10), run(2, 11), run(3, 12)],
            jobs_by_run={1: [{"conclusion": "skipped", "step": None}],
                         2: attempted("skipped"),
                         3: attempted()},
            comments_by_pr={},
        )
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api), [seen("failure")],
                         "why: a draft or a missing secret skips the job or step and made no "
                         "attempt; remedy: drop both before judging, keep only real attempts")

    def test_a_null_step_is_an_attempt_the_lane_failed_to_make(self) -> None:
        """Upstream hard failure leaves the review step null. That lane is broken."""
        api = fake_api(runs=[run(1, 10)], jobs_by_run={1: attempted(None)}, comments_by_pr={})
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api), [seen("failure")],
                         "why: a step the run never reached is not skipped -- the lane broke "
                         "before reviewing -- and posted nothing; remedy: judge it by effect "
                         "like any attempt rather than dropping it as silence")

    def test_a_timed_out_step_is_an_attempt_judged_by_effect(self) -> None:
        """The realistic death mode for a hung vendor endpoint.

        `claude-review.yml` sets a 30-minute job timeout, so a stalled endpoint
        is killed by the job timer and the step is recorded `timed_out`, never
        `failure`. Treating any non-`failure` conclusion as healthy would
        report a lane that times out on every run as succeeding — the
        wrong-healthy answer this check exists to prevent.
        """
        api = fake_api(runs=[run(1, 10)], jobs_by_run={1: attempted("timed_out")},
                       comments_by_pr={})
        self.assertEqual(
            collect_observations("o/r", GROK_LANE, limit=5, api=api), [seen("failure")],
            "why: timed_out is how a hung reviewer dies and it is not silence — "
            "the lane attempted a review and posted nothing; remedy: keep SILENT "
            "to skipped/cancelled and judge every other conclusion by effect",
        )

    def test_a_timed_out_step_that_still_posted_is_success(self) -> None:
        """Effect, not conclusion: a review that landed before the timer counts."""
        api = fake_api(runs=[run(1, 10)], jobs_by_run={1: attempted("timed_out")},
                       comments_by_pr={10: [GROK_LANE.marker]})
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api),
                         [seen("success")])

    def test_a_run_without_a_pull_request_is_dropped(self) -> None:
        api = fake_api(runs=[run(1, None)], jobs_by_run={1: attempted()})
        self.assertEqual(collect_observations("o/r", GROK_LANE, limit=5, api=api), [])

    def test_an_unreadable_api_is_a_failure_not_an_empty_observation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("class LivenessUnavailable", source)
        self.assertNotIn("        return []", source,
                         "why: an empty list on API failure reads as 'too few to judge' and "
                         "exits 0 -- green while blind; remedy: raise LivenessUnavailable")

        def broken(path, context):
            raise LivenessUnavailable("why: listing failed; remedy: fix access")
        with self.assertRaises(LivenessUnavailable):
            collect_observations("o/r", GROK_LANE, limit=5, api=broken)

    def test_the_step_conclusion_is_never_the_signal(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        directives = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn('"success" if job', directives)
        self.assertNotIn("step == \"failure\"", directives)
        self.assertIn("evidence_posted(", directives,
                      "why: the API reports a continue-on-error step that exited 1 as success, "
                      "so a step conclusion can never say a review failed; remedy: judge each "
                      "attempt by whether the lane's marker was posted")


class ReadAccessTest(unittest.TestCase):
    """The check must be able to read the surfaces it judges by."""

    def test_the_workflow_passes_the_token_name_the_script_reads(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", source,
            msg=("why: the script reads GITHUB_TOKEN with urllib, so passing it "
                 "under any other name leaves the token unset and every run "
                 "raises LivenessUnavailable; remedy: pass secrets.GITHUB_TOKEN "
                 "as GITHUB_TOKEN"),
        )
        self.assertIn("GITHUB_TOKEN", SCRIPT.read_text(encoding="utf-8"))

    def test_the_workflow_grants_the_scopes_evidence_posted_needs(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        message = (
            "why: evidence_posted reads issue comments, review comments and "
            "review bodies, and an explicit permissions block makes every "
            "omitted scope none -- so those reads 403, _gh raises "
            "LivenessUnavailable, and the job is permanently red while "
            "observing nothing; remedy: grant issues: read and "
            "pull-requests: read alongside actions: read"
        )
        for scope in ("actions: read", "issues: read", "pull-requests: read"):
            self.assertIn(scope, source, message)
        directives = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for write in ("contents: write", "issues: write", "pull-requests: write"):
            self.assertNotIn(write, directives,
                             "why: this workflow publishes nothing and mutates "
                             "nothing; remedy: keep every scope read-only")


class PagingTest(unittest.TestCase):
    def test_cancelled_runs_do_not_starve_the_window(self) -> None:
        """cancel-in-progress makes a busy day mostly cancellations.

        A single fixed page of runs would keep fewer than `window` attempts,
        `evaluate` would report "too few to judge", and the check would exit 0
        -- green while blind, on exactly the day a lane is most likely broken.
        """
        cancelled = [run(i, 200 + i, conclusion="cancelled") for i in range(1, 60)]
        real = [run(1000 + i, 300 + i) for i in range(1, 6)]
        api = fake_api(
            runs=cancelled + real,
            jobs_by_run={1000 + i: attempted() for i in range(1, 6)},
            comments_by_pr={},
        )
        obs = collect_observations("o/r", GROK_LANE, limit=5, api=api)
        self.assertEqual(
            obs, [seen("failure")] * 5,
            "why: 59 cancelled runs precede the real ones, so one page keeps "
            "nothing and the lane reads as too-young instead of down; remedy: "
            "page until the window is filled",
        )
        self.assertTrue(evaluate(GROK_LANE.name, obs, window=5).down)

    def test_runs_that_skip_the_review_do_not_spend_the_budget(self) -> None:
        """ci.yml runs on push, dispatch and drafts; those skip the review.

        They complete, are not cancelled, and carry no observation. Budgeting
        the pager on run count let twenty of them fill the budget before a
        single review attempt was reached, so `evaluate` saw too few to judge
        and the check exited 0 -- green while blind. Only a judged attempt
        spends the budget now. (The listing is also filtered to pull_request
        events; drafts still arrive that way and are dropped as skipped.)
        """
        padding = [run(i, None, created="2026-09-09T10:00:00Z") for i in range(1, 21)]
        real = [run(100 + i, 700 + i, created="2026-09-09T11:00:00Z") for i in range(1, 6)]
        jobs = {i: [{"name": GLM.job, "conclusion": "skipped", "steps": []}] for i in range(1, 21)}
        jobs.update({100 + i: attempted(lane=GLM) for i in range(1, 6)})
        api = fake_api(runs=padding + real, jobs_by_run=jobs, review_comments_by_pr={})
        obs = collect_observations("o/r", GLM, limit=5, api=api)
        self.assertEqual(
            obs, [seen("failure", "2026-09-09T11:00:00Z")] * 5,
            "why: skipped runs are silence and must not exhaust the paging budget "
            "before an attempt is reached; remedy: page until limit observations "
            "exist, not until limit runs have been seen",
        )
        self.assertTrue(evaluate(GLM.name, obs, window=5).down)

    def test_the_listing_asks_only_for_pull_request_runs(self) -> None:
        seen = []
        inner = fake_api(runs=[], jobs_by_run={})
        def api(path, context):
            seen.append(path); return inner(path, context)
        collect_observations("o/r", GLM, limit=5, api=api)
        self.assertTrue(seen and all("event=pull_request" in p for p in seen if "/workflows/" in p),
                        "why: push and dispatch runs of ci.yml never run the review and only pad "
                        "the pages; remedy: filter the run listing to event=pull_request")

    def test_paging_stops_once_the_window_is_filled(self) -> None:
        calls = []
        inner = fake_api(
            runs=[run(i, 400 + i) for i in range(1, 200)],
            jobs_by_run={i: attempted() for i in range(1, 200)},
            comments_by_pr={400 + i: [GROK_LANE.marker] for i in range(1, 200)},
        )

        def counting(path, context):
            if "/actions/workflows/" in path:
                calls.append(path)
            return inner(path, context)

        obs = collect_observations("o/r", GROK_LANE, limit=5, api=counting)
        self.assertEqual(obs, [seen("success")] * 5)
        self.assertEqual(len(calls), 1, "why: a filled window needs no second "
                         "page; remedy: stop paging once enough attempts are kept")


class ApiAccessTest(unittest.TestCase):
    """The check reaches the API the way the rest of the repository does."""

    def test_it_does_not_shell_out_to_gh(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        directives = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for banned in ("subprocess", '"gh"', "'gh'"):
            self.assertNotIn(
                banned, directives,
                msg=("why: no run: step in this repository invokes gh on a "
                     "self-hosted runner and nothing installs it there, so the "
                     "job would fail on every scheduled run — and a missing "
                     "binary raises FileNotFoundError, which a returncode check "
                     "never sees; remedy: use urllib, as grok_review.py does"),
            )
        self.assertIn("urllib.request", directives)

    def test_a_missing_token_is_a_failure_not_a_healthy_report(self) -> None:
        import os as _os
        from unittest import mock
        import advisory_review_liveness as mod
        with mock.patch.dict(_os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            with self.assertRaises(LivenessUnavailable) as caught:
                mod._api("/repos/o/r/actions/workflows/w.yml/runs", "listing runs")
        self.assertIn("why:", str(caught.exception))
        self.assertIn("remedy:", str(caught.exception))


class BootstrapTest(unittest.TestCase):
    """A marker cannot judge runs that predate it."""

    def test_runs_before_the_signing_instruction_are_not_failures(self) -> None:
        """Otherwise both Claude lanes read DOWN on the first scheduled run.

        The markers are new. Every completed run before them posted unsigned
        comments, so `evidence_posted` finds nothing and a healthy backend is
        declared dead — a false red on the exact alert channel this workflow
        uses to report a real one.
        """
        old_runs = [run(i, 500 + i, created="2026-09-01T10:00:00Z") for i in range(1, 6)]
        api = fake_api(runs=old_runs,
                       jobs_by_run={i: attempted(lane=GLM) for i in range(1, 6)},
                       review_comments_by_pr={})
        self.assertEqual(
            collect_observations("o/r", GLM, limit=5, api=api), [],
            "why: those runs were never instructed to sign, so a missing marker "
            "says nothing about them; remedy: drop attempts created before the "
            "lane's signs_since",
        )
        self.assertFalse(evaluate(GLM.name, [], window=5).down)

    def test_runs_after_the_cutoff_are_judged_normally(self) -> None:
        new_runs = [run(i, 600 + i, created="2026-09-09T10:00:00Z") for i in range(1, 6)]
        api = fake_api(runs=new_runs,
                       jobs_by_run={i: attempted(lane=GLM) for i in range(1, 6)},
                       review_comments_by_pr={})
        self.assertEqual(collect_observations("o/r", GLM, limit=5, api=api),
                         [seen("failure", "2026-09-09T10:00:00Z")] * 5)

    def test_grok_needs_no_cutoff(self) -> None:
        """Its sticky-comment marker predates this check."""
        self.assertEqual(GROK_LANE.signs_since, "")
        self.assertTrue(GLM.signs_since and KIMI.signs_since)


class ScopeCostTest(unittest.TestCase):
    def test_the_script_is_not_on_the_mandatory_full_ci_prefix(self) -> None:
        """`scripts/ci/` upgrades any change to full CI — about 185 minutes.

        This is a scheduled diagnostic, not Gate, Queue or scope routing, and
        the analogous Grok reviewer already lives under `.github/scripts/`
        classified `ci_contract` only.
        """
        import json as _json
        policy = _json.loads(SCOPE_POLICY.read_text(encoding="utf-8"))
        self.assertFalse(
            str(SCRIPT).endswith("scripts/ci/advisory_review_liveness.py"),
            "why: the scripts/ci/ prefix is a full_rules match, so every edit "
            "to this diagnostic would run every expensive family; remedy: keep "
            "it next to .github/scripts/grok_review.py",
        )
        rules = {r["match"]["value"]: set(r["lanes"]) for r in policy["rules"]
                 if r["match"]["kind"] == "exact"}
        for path in (".github/scripts/advisory_review_liveness.py",
                     ".github/workflows/advisory-review-liveness.yml"):
            self.assertEqual(rules.get(path), {"ci_contract"},
                             f"{path} must be classified ci_contract only")


class SignatureContractTest(unittest.TestCase):
    """Each lane's marker must be exactly what its workflow actually emits."""

    def test_trusted_publisher_signs_claude_backends_with_their_marker(self) -> None:
        import pr_review_target

        repository, head = "example/project", "a" * 40
        target = {"state": "open", "draft": False,
                  "head": {"sha": head, "repo": {"full_name": repository}},
                  "base": {"ref": "main"}}
        for lane, backend in ((GLM, "glm"), (KIMI, "kimi")):
            with self.subTest(backend=backend):
                writes = []
                pr_review_target.publish_review(
                    repository, 7, head, "123", "1", backend,
                    {"summary": "Review result", "findings": [
                        {"path": "example.py", "line": 1, "body": "Finding"}]},
                    api=lambda path: target,
                    write=lambda path, payload: writes.append((path, payload)))
                self.assertEqual(len(writes), 1)
                self.assertEqual(writes[0][0], "/repos/example/project/pulls/7/reviews")
                for body in (writes[0][1]["body"], writes[0][1]["comments"][0]["body"]):
                    self.assertEqual(body.splitlines()[0], lane.marker,
                                     "why: shared fallback jobs cannot identify the winning backend; "
                                     "remedy: have the trusted publisher prefix each review and "
                                     "inline finding with the matching liveness marker")

    def test_the_vendored_command_does_not_contradict_the_signature(self) -> None:
        """`/pr-review` mandates a fixed clean-review format.

        Asking for the marker on the first line while that format says the
        comment begins with `## Code review` is a contradiction the model
        resolves either way, and a clean review is the common case -- so the
        marker goes missing and a healthy lane reads DOWN.
        """
        vendored = (REPO_ROOT / ".claude/commands/pr-review.md").read_text(encoding="utf-8")
        self.assertIn(
            "signature line", vendored,
            msg=("why: the vendored command's fixed comment format would "
                 "otherwise contradict the workflow's marker instruction, and a "
                 "clean review is the common case; remedy: state in the "
                 "vendored command that a caller-specified signature line comes "
                 "first, before any format it gives"),
        )
        self.assertIn("first line of every comment you post", vendored)

    def test_grok_marker_matches_its_sticky_comment(self) -> None:
        grok = GROK_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(f'COMMENT_MARKER = "{GROK_LANE.marker}"', grok,
                      "why: the lane's marker is looked for in the sticky comment, and a "
                      "rename on either side makes every Grok review invisible; remedy: keep "
                      "REVIEW_LANES and grok_review.COMMENT_MARKER in step")

    def test_every_active_lane_names_a_job_and_step_that_exist(self) -> None:
        # Historical ci.yml evidence stays readable without requiring the
        # retired workflow to retain executable reviewer jobs forever.
        sources = {"pr-review.yml": STANDALONE.read_text(encoding="utf-8")}
        for lane in REVIEW_LANES:
            if lane.workflow not in sources:
                continue
            with self.subTest(lane=lane.name):
                self.assertIn(f"- name: {lane.step}", sources[lane.workflow])
                job_name = lane.job.replace("(glm)", "(${{ matrix.backend }})") \
                                   .replace("(kimi)", "(${{ matrix.backend }})")
                self.assertIn(f"name: {job_name}", sources[lane.workflow],
                              "why: the liveness check finds a lane by its job name; "
                              "remedy: keep the job names identical across workflows")

    def test_it_watches_exactly_the_lanes_that_fail_quietly(self) -> None:
        for workflow, path in (("ci.yml", CLAUDE),):
            with self.subTest(workflow=workflow):
                self.assertIn("continue-on-error: true", path.read_text(encoding="utf-8"))
                self.assertIn(workflow, {l.workflow for l in REVIEW_LANES})

    def test_the_standalone_entry_is_watched_with_the_same_lane_definitions(self) -> None:
        """T4: one lane definition per reviewer describes both entries.

        The standalone workflow does not carry continue-on-error -- its jobs
        are red when they did not review -- but the effect it is judged by is
        the same signature, so the same lane applies.
        """
        self.assertEqual(liveness.REVIEW_WORKFLOWS, ("ci.yml", "pr-review.yml"))
        by_workflow = {}
        for lane in REVIEW_LANES:
            by_workflow.setdefault(lane.workflow, set()).add(lane.marker)
        self.assertEqual(by_workflow["ci.yml"], by_workflow["pr-review.yml"],
                         "why: a lane that exists for one entry and not the other is a "
                         "reviewer the check cannot see there; remedy: derive both from "
                         "REVIEW_WORKFLOWS")
        self.assertEqual({l.workflow for l in liveness.claude_lanes("glm")},
                         set(liveness.REVIEW_WORKFLOWS))
        self.assertEqual(liveness.grok_lane("pr-review.yml").marker, liveness.GROK_MARKER)

    def test_selection_reads_a_backends_evidence_from_every_review_workflow(self) -> None:
        """After T5a only the standalone entry posts; a selector reading ci.yml
        alone would watch every backend age into 'stale' and never DOWN."""
        listed = []

        def api(path, context):
            if "/actions/workflows/" in path:
                listed.append(path.split("/actions/workflows/")[1].split("/")[0])
                return {"workflow_runs": []}
            raise AssertionError(path)

        chosen, _ = select_backends(
            "o/r", ["glm", "kimi"], window=5,
            now=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc), api=api)
        self.assertEqual(chosen, ["glm"])
        self.assertEqual(set(listed), {"ci.yml", "pr-review.yml"})


class StalenessTest(unittest.TestCase):
    """A window that stopped growing stops describing the lane."""

    NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    def test_a_fresh_all_failed_window_is_down(self) -> None:
        verdict = evaluate("lane", [seen("failure", "2026-09-10T09:00:00Z")] * 5,
                           window=5, now=self.NOW)
        self.assertTrue(verdict.down)

    def test_an_old_all_failed_window_is_not_down(self) -> None:
        """Otherwise the first backend `--select` demotes could never return.

        Its last attempts stay in the window forever, so `down` would be
        permanent and a vendor outage would cost the backend its slot for
        good rather than for as long as it was broken.
        """
        verdict = evaluate("lane", [seen("failure", "2026-09-01T09:00:00Z")] * 5,
                           window=5, now=self.NOW)
        self.assertFalse(verdict.down)
        self.assertIn("not being exercised", verdict.detail)

    def test_without_a_clock_the_window_is_judged_on_content_alone(self) -> None:
        """The report keeps its old behaviour when no `now` is supplied."""
        self.assertTrue(evaluate("lane", [seen("failure", "2020-01-01T00:00:00Z")] * 5,
                                 window=5).down)

    def test_an_unparseable_timestamp_is_not_treated_as_old(self) -> None:
        """Guessing "old" from a bad parse would promote a dead backend."""
        self.assertTrue(evaluate("lane", [seen("failure", "not-a-date")] * 5,
                                 window=5, now=self.NOW).down)


class SelectBackendTest(unittest.TestCase):
    """One backend per Pull Request, and which one is evidence-driven (#659)."""

    NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

    def api_for(self, glm_outcomes, kimi_outcomes, created="2026-09-06T09:00:00Z"):
        """A fake API where each backend posted, or did not, on its own runs."""
        runs, jobs, comments = [], {}, {}
        run_id = 1
        for lane, outcomes in ((GLM, glm_outcomes), (KIMI, kimi_outcomes)):
            for outcome in outcomes:
                pr = 100 + run_id
                runs.append(run(run_id, pr, created=created))
                jobs[run_id] = attempted(lane=lane)
                comments[pr] = [lane.marker] if outcome == "success" else []
                run_id += 1
        return fake_api(runs=runs, jobs_by_run=jobs, review_comments_by_pr=comments)

    def test_a_healthy_primary_runs_alone(self) -> None:
        api = self.api_for(["success"] * 5, ["success"] * 5)
        chosen, reason = select_backends(
            "o/r", ["glm", "kimi"], window=5, now=self.NOW, api=api)
        self.assertEqual(chosen, ["glm"])
        self.assertIn("primary", reason)

    def test_a_down_primary_hands_over_to_the_fallback(self) -> None:
        api = self.api_for(["failure"] * 5, ["success"] * 5)
        chosen, reason = select_backends(
            "o/r", ["glm", "kimi"], window=5, now=self.NOW, api=api)
        self.assertEqual(
            chosen, ["kimi"],
            msg=("why: the acceptance is that the fallback switches on the "
                 "liveness signal rather than by hand; remedy: pick the first "
                 "candidate that is not DOWN"),
        )
        self.assertIn("fallback", reason)

    def test_both_down_still_reviews_with_the_primary(self) -> None:
        """A correct alert must not also cost the Pull Request its reviewer."""
        api = self.api_for(["failure"] * 5, ["failure"] * 5)
        chosen, reason = select_backends(
            "o/r", ["glm", "kimi"], window=5, now=self.NOW, api=api)
        self.assertEqual(chosen, ["glm"])
        self.assertIn("every candidate is DOWN", reason)

    def test_thin_evidence_is_not_a_reason_to_withhold_the_primary(self) -> None:
        api = self.api_for(["failure"], ["success"] * 5)
        chosen, _ = select_backends(
            "o/r", ["glm", "kimi"], window=5, now=self.NOW, api=api)
        self.assertEqual(chosen, ["glm"])

    def test_a_demoted_primary_is_tried_again_once_its_window_goes_stale(self) -> None:
        """The recovery path: without it the first handover is permanent."""
        api = self.api_for(["failure"] * 5, ["success"] * 5,
                           created="2026-09-01T09:00:00Z")
        chosen, _ = select_backends(
            "o/r", ["glm", "kimi"], window=5, now=self.NOW, api=api)
        self.assertEqual(chosen, ["glm"])

    def test_a_single_candidate_is_answered_without_reading_the_api(self) -> None:
        """Off the Pull Request path there is nothing to choose between.

        `ci.yml` runs the selector unconditionally so a push run never has to
        evaluate `fromJSON` on a skipped job's output; that run must not also
        spend API calls weighing evidence it will not use.
        """
        def refuse(path, context):
            raise AssertionError(f"the API was read for a single candidate: {path}")

        chosen, reason = select_backends(
            "o/r", ["glm"], window=5, now=self.NOW, api=refuse)
        self.assertEqual(chosen, ["glm"])
        self.assertIn("only candidate", reason)

    def test_the_order_is_a_preference_not_a_fixed_pair(self) -> None:
        api = self.api_for(["failure"] * 5, ["success"] * 5)
        chosen, _ = select_backends(
            "o/r", ["kimi", "glm"], window=5, now=self.NOW, api=api)
        self.assertEqual(chosen, ["kimi"])


class SelectCliTest(unittest.TestCase):
    """`--select` must always print a matrix, whatever it was handed."""

    def run_select(self, order):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = liveness.main(["--repository", "o/r", "--select", order])
        return code, buffer.getvalue().strip().splitlines()

    def backends_in(self, lines):
        return [entry["backend"] for entry in json.loads(lines[-1])["include"]]

    def test_a_mistyped_name_falls_back_to_what_is_left_of_the_order(self) -> None:
        code, lines = self.run_select("glm,kimmi")
        self.assertEqual(code, 0)
        self.assertEqual(self.backends_in(lines), ["glm"])

    def test_a_wholly_unknown_order_still_prints_a_matrix(self) -> None:
        """`set -euo pipefail` plus a nonzero exit here empties strategy.matrix.

        `CLAUDE_REVIEW_ORDER` is an operator knob, so a typo in it must not
        cost the Pull Request its review.
        """
        code, lines = self.run_select("nonsense")
        self.assertEqual(code, 0)
        self.assertEqual(self.backends_in(lines), [CLAUDE_BACKENDS[0]["backend"]])

    def test_an_empty_order_still_prints_a_matrix(self) -> None:
        code, lines = self.run_select(",,")
        self.assertEqual(code, 0)
        self.assertEqual(self.backends_in(lines), [CLAUDE_BACKENDS[0]["backend"]])


class SelectionMatrixTest(unittest.TestCase):
    def test_the_matrix_names_one_backend_with_its_url_and_secret(self) -> None:
        matrix = liveness._selection_matrix(["kimi"])
        self.assertEqual(len(matrix["include"]), 1)
        entry = matrix["include"][0]
        self.assertEqual(entry["backend"], "kimi")
        self.assertIn("base_url", entry)
        self.assertIn("secret_name", entry)

    def test_every_declared_backend_has_a_lane_that_can_judge_it(self) -> None:
        """A backend the workflow can run and the check cannot see is invisible."""
        lanes = {lane.job for lane in REVIEW_LANES}
        for entry in CLAUDE_BACKENDS:
            with self.subTest(backend=entry["backend"]):
                self.assertIn(f"Claude review ({entry['backend']})", lanes)


class LivenessWorkflowTest(unittest.TestCase):
    def test_the_check_runs_self_hosted(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]",
                      source, "why: a daily hosted job cost the watchdog an allowance; "
                      "remedy: keep ci-general")
        self.assertNotIn("runs-on: ubuntu-24.04", source)


class ReportTest(unittest.TestCase):
    def test_the_report_names_a_down_lane_and_the_masking(self) -> None:
        report = render([evaluate(GROK_LANE.name, [seen("failure")] * 5, window=5)])
        self.assertIn("DOWN", report)
        self.assertIn("Grok advisory review", report)
        self.assertIn("continue-on-error", report)
        self.assertIn("`success`", report)

    def test_the_report_separates_the_two_claude_backends(self) -> None:
        report = render([evaluate(l.name, [seen("failure")] * 5, window=5) for l in (GLM, KIMI)])
        self.assertIn("glm", report)
        self.assertIn("kimi", report)


class StandaloneExactEvidenceTest(unittest.TestCase):
    def review(self, **changes):
        value = {"body": "<!-- lmdj-review: glm -->\n<!-- lmdj-review-v1 o/r 7 " + "a" * 40 + " 123 2 glm -->\nclean",
                 "commit_id": "a" * 40, "state": "COMMENTED", "user": {"login": "github-actions[bot]"}}
        value.update(changes)
        return value

    def test_only_bot_review_exact_run_attempt_head_counts(self):
        good = self.review()
        def check(review, run="123", attempt="2", backend="glm"):
            return liveness.exact_review_posted("o/r", 7, run, attempt, backend, api=lambda path, context: [review])
        self.assertTrue(check(good))
        self.assertFalse(check(self.review(user={"login": "human"})))
        self.assertFalse(check(self.review(commit_id="b" * 40)))
        self.assertFalse(check(self.review(state="PENDING")))
        self.assertFalse(check(good, run="122"))
        self.assertFalse(check(good, attempt="1"))
        self.assertFalse(check(good, backend="kimi"))

    def test_v2_publisher_marker_binds_full_history_and_requested_identity(self):
        history = {"schema": "lmdj.ci-review-history.v2", "attempts": [{
            "backend": "deepseek", "status": "reviewed", "error_class": None,
            "review": {"schema": "lmdj.ci-review-output.v1", "summary": "clean", "findings": [],
                        "test_scope": {"labels": ["test:full"], "reason": "full"}},
            "engine": {"name": "pr-agent"}, "provider": "deepseek",
            "model": {"requested": "fixture", "actual": "served"}, "coverage_sha256": "f" * 64,
        }]}
        marker = codec.encode_history(history)
        digest = liveness.V2_HISTORY_MARKER.fullmatch(marker).group(1)
        body = ("<!-- lmdj-review: deepseek -->\n"
                "<!-- lmdj-review-v2 o/r 7 " + "a" * 40 + " 123 2 deepseek sha256=" + digest + " -->\n"
                + marker + "\nclean")
        review = {"body": body, "commit_id": "a" * 40, "state": "COMMENTED",
                  "user": {"login": "github-actions[bot]"}}
        api = lambda path, context: [review]
        self.assertTrue(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek", api=api))
        forged = dict(review, body=body.replace(" o/r 7 ", " other/r 7 "))
        self.assertFalse(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek",
                                                       api=lambda path, context: [forged]))

    def test_v2_digest_only_history_marker_is_not_posted_review_evidence(self):
        digest = "f" * 64
        body = ("<!-- lmdj-review: deepseek -->\n"
                "<!-- lmdj-review-v2 o/r 7 " + "a" * 40 + " 123 2 deepseek sha256=" + digest + " -->\n"
                "<!-- lmdj-review-history-digest-v2 sha256=" + digest + " -->\nclean")
        review = {"body": body, "commit_id": "a" * 40, "state": "COMMENTED",
                  "user": {"login": "github-actions[bot]"}}
        self.assertFalse(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek",
                                                       api=lambda path, context: [review]))

    def test_v2_malformed_or_digest_mismatching_history_is_not_posted_evidence(self):
        digest = "f" * 64
        identity = ("<!-- lmdj-review: deepseek -->\n<!-- lmdj-review-v2 o/r 7 "
                    + "a" * 40 + " 123 2 deepseek sha256=" + digest + " -->\n")
        malformed = identity + "<!-- lmdj-review-history-v2 codec=zlib-base64 sha256=" + digest + " !!! -->\nclean"
        review = {"body": malformed, "commit_id": "a" * 40, "state": "COMMENTED",
                  "user": {"login": "github-actions[bot]"}}
        self.assertFalse(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek",
                                                       api=lambda path, context: [review]))
        history = {"schema": "lmdj.ci-review-history.v2", "attempts": []}
        marker = codec.encode_history(history)
        mismatched = identity + marker + "\nclean"
        review["body"] = mismatched
        self.assertFalse(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek",
                                                       api=lambda path, context: [review]))

    def test_v2_failed_only_history_is_not_posted_clean_review(self):
        history = {"schema": "lmdj.ci-review-history.v2", "attempts": [{
            "backend": "deepseek", "status": "failed", "error_class": "timeout", "review": None,
            "engine": None, "provider": None, "model": None, "coverage_sha256": None,
        }]}
        marker = codec.encode_history(history)
        digest = liveness.V2_HISTORY_MARKER.fullmatch(marker).group(1)
        body = ("<!-- lmdj-review: deepseek -->\n<!-- lmdj-review-v2 o/r 7 "
                + "a" * 40 + " 123 2 deepseek sha256=" + digest + " -->\n" + marker + "\nclean")
        review = {"body": body, "commit_id": "a" * 40, "state": "COMMENTED",
                  "user": {"login": "github-actions[bot]"}}
        self.assertFalse(liveness.exact_review_posted("o/r", 7, "123", "2", "deepseek",
                                                       api=lambda path, context: [review]))

    def collect(self, *, publisher="success", event="workflow_dispatch", model="success", step=None, posted=True):
        run = {"id": 123, "run_attempt": 2, "event": event, "head_branch": "main", "head_sha": "b" * 40,
               "display_title": "PR Review / #7 @ dispatch", "conclusion": "success",
               "pull_requests": [], "created_at": "2026-09-07T10:00:00Z"}
        def api(path, context):
            if "/actions/workflows/" in path:
                self.assertNotIn("event=pull_request", path)
                return {"workflow_runs": [run]}
            if "/jobs?" in path:
                return {"jobs": [{"name": "Review fallback", "conclusion": model,
                                   "steps": [{"name": "Validate glm result before considering fallback", "conclusion": step or model}]},
                                  {"name": "Publish review and scope", "conclusion": publisher}]}
            if "/pulls/7/reviews?" in path:
                return [self.review()] if posted else []
            raise AssertionError(path)
        return liveness.collect_observations("o/r", liveness.claude_lane("glm", "pr-review.yml"), limit=5, api=api)

    def test_dispatch_without_pull_requests_uses_exact_published_head_not_control_sha(self):
        self.assertEqual(self.collect()[0].outcome, "success")

    def test_stale_or_failed_publisher_cannot_pass_on_an_existing_review(self):
        self.assertEqual(self.collect(publisher="failure")[0].outcome, "failure")
        self.assertEqual(self.collect(model="neutral")[0].outcome, "failure")

    def test_shared_job_green_without_this_backend_signature_is_failure(self):
        self.assertEqual(self.collect(posted=False)[0].outcome, "failure")

    def test_backend_skipped_after_prior_success_is_not_failure_sample(self):
        self.assertEqual(self.collect(step="skipped"), [])


if __name__ == "__main__":
    unittest.main()
