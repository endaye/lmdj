from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "release_version.py"


def load_release_version():
    spec = importlib.util.spec_from_file_location("release_version", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release_version = load_release_version()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


class Repository:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(self.path)],
            check=True,
        )
        git(self.path, "config", "user.name", "Release Test")
        git(self.path, "config", "user.email", "release-test@example.com")

    def close(self) -> None:
        self.temp.cleanup()

    def commit(self, subject: str, body: str = "") -> str:
        args = ["commit", "--allow-empty", "-m", subject]
        if body:
            args.extend(["-m", body])
        git(self.path, *args)
        return git(self.path, "rev-parse", "HEAD")

    def tag(self, name: str, target: str = "HEAD") -> None:
        git(self.path, "tag", "-a", name, target, "-m", name)

    def set_origin_main(self, target: str = "HEAD") -> None:
        sha = git(self.path, "rev-parse", target)
        git(self.path, "update-ref", "refs/remotes/origin/main", sha)


class ReleaseVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repository()

    def tearDown(self) -> None:
        self.repo.close()

    def test_first_current_main_release_is_v020(self) -> None:
        target = self.repo.commit("feat: initial product")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, target)

        self.assertEqual(plan.tag, "v0.2.0")
        self.assertIsNone(plan.previous_tag)
        self.assertFalse(plan.existing)
        self.assertEqual(plan.target_sha, target)
        self.assertEqual([commit.sha for commit in plan.commits], [target])

    def test_first_explicit_old_sha_is_rejected(self) -> None:
        old = self.repo.commit("feat: old product")
        self.repo.commit("fix: current product")
        self.repo.set_origin_main()

        with self.assertRaisesRegex(
            release_version.ReleaseError, "initial release target must equal origin/main"
        ):
            release_version.plan_release(self.repo.path, old)

    def test_prerelease_tags_do_not_participate_in_product_versions(self) -> None:
        target = self.repo.commit("feat: initial product")
        self.repo.tag("v9.9.9-staging.1")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, target)

        self.assertEqual(plan.tag, "v0.2.0")
        self.assertFalse(plan.existing)

    def test_product_tags_must_be_annotated(self) -> None:
        target = self.repo.commit("feat: deployed product")
        git(self.repo.path, "update-ref", "refs/tags/v0.2.0", target)
        self.repo.set_origin_main()

        with self.assertRaisesRegex(
            release_version.ReleaseError, "product tag v0.2.0 must be annotated"
        ):
            release_version.plan_release(self.repo.path, target)

    def test_fix_and_nonconventional_commits_bump_patch(self) -> None:
        self.repo.commit("feat: baseline")
        self.repo.tag("v0.2.0")
        fix = self.repo.commit("fix(api): reject bad input")
        other = self.repo.commit("Merge branch 'maintenance'")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, other)

        self.assertEqual(plan.tag, "v0.2.1")
        self.assertEqual(plan.previous_tag, "v0.2.0")
        self.assertEqual([commit.sha for commit in plan.commits], [fix, other])

    def test_feat_bumps_minor(self) -> None:
        self.repo.commit("feat: baseline")
        self.repo.tag("v0.2.0")
        target = self.repo.commit("feat(web): add creator view")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, target)

        self.assertEqual(plan.tag, "v0.3.0")

    def test_breaking_footer_and_bang_bump_major(self) -> None:
        for subject, body in (
            ("refactor(api): change contract", "BREAKING CHANGE: old clients fail"),
            ("feat(web)!: replace workbench", ""),
        ):
            with self.subTest(subject=subject):
                repo = Repository()
                try:
                    repo.commit("feat: baseline")
                    repo.tag("v0.3.2")
                    target = repo.commit(subject, body)
                    repo.set_origin_main()
                    plan = release_version.plan_release(repo.path, target)
                    self.assertEqual(plan.tag, "v1.0.0")
                    self.assertTrue(plan.commits[-1].breaking)
                finally:
                    repo.close()

    def test_highest_change_wins(self) -> None:
        self.repo.commit("feat: baseline")
        self.repo.tag("v1.2.3")
        self.repo.commit("fix: patch")
        self.repo.commit("feat: minor")
        target = self.repo.commit("chore!: major")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, target)

        self.assertEqual(plan.tag, "v2.0.0")

    def test_existing_single_tag_is_reused(self) -> None:
        self.repo.commit("feat: baseline")
        self.repo.tag("v0.2.0")
        target = self.repo.commit("fix: deployed")
        self.repo.tag("v0.2.1")
        self.repo.set_origin_main()

        plan = release_version.plan_release(self.repo.path, target)

        self.assertEqual(plan.tag, "v0.2.1")
        self.assertEqual(plan.previous_tag, "v0.2.0")
        self.assertTrue(plan.existing)
        self.assertEqual([commit.sha for commit in plan.commits], [target])

    def test_multiple_tags_on_target_are_rejected(self) -> None:
        target = self.repo.commit("feat: deployed")
        self.repo.tag("v0.2.0")
        self.repo.tag("v0.2.1")
        self.repo.set_origin_main()

        with self.assertRaisesRegex(
            release_version.ReleaseError, "multiple product tags"
        ):
            release_version.plan_release(self.repo.path, target)

    def test_latest_tag_must_be_target_ancestor(self) -> None:
        base = self.repo.commit("feat: baseline")
        self.repo.tag("v0.2.0", base)
        git(self.repo.path, "switch", "-q", "-c", "side")
        side = self.repo.commit("feat: side release")
        self.repo.tag("v0.3.0", side)
        git(self.repo.path, "switch", "-q", "main")
        target = self.repo.commit("fix: main line")
        self.repo.set_origin_main()

        with self.assertRaisesRegex(
            release_version.ReleaseError, "is not an ancestor"
        ):
            release_version.plan_release(self.repo.path, target)

    def test_markdown_categories_links_and_breaking_marker(self) -> None:
        self.repo.commit("feat: baseline")
        self.repo.tag("v0.2.0")
        self.repo.commit("feat(core): add pads (#12)")
        self.repo.commit("perf(audio): reduce scheduling overhead")
        self.repo.commit("docs: explain pads")
        self.repo.commit("chore(ci): refresh runner")
        self.repo.commit("Random merge title")
        target = self.repo.commit(
            "fix(api): replace response",
            "BREAKING CHANGE: response fields changed",
        )
        self.repo.set_origin_main()
        plan = release_version.plan_release(self.repo.path, target)

        notes = release_version.render_notes(
            plan,
            repository="endaye/lmdj",
            run_url="https://github.com/endaye/lmdj/actions/runs/42",
            deployed_at="2026-07-26T10:11:12Z",
        )

        self.assertTrue(notes.startswith(f"# {plan.tag}\n"))
        self.assertIn("## Features", notes)
        self.assertIn("## Fixes", notes)
        self.assertIn("## Performance", notes)
        self.assertIn("## Documentation", notes)
        self.assertIn("## Maintenance", notes)
        self.assertIn("## Other", notes)
        self.assertIn("https://github.com/endaye/lmdj/pull/12", notes)
        self.assertIn(
            f"https://github.com/endaye/lmdj/commit/{target}",
            notes,
        )
        self.assertIn("**BREAKING:**", notes)
        self.assertIn("2026-07-26T10:11:12Z", notes)

    def test_cli_writes_notes_and_github_outputs(self) -> None:
        target = self.repo.commit("feat: initial product")
        self.repo.set_origin_main()
        output_dir = self.repo.path / "release-output"
        github_output = self.repo.path / "github-output"

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--mode",
                "render",
                "--repo",
                str(self.repo.path),
                "--target-sha",
                target,
                "--expected-tag",
                "v0.2.0",
                "--repository",
                "endaye/lmdj",
                "--run-url",
                "https://github.com/endaye/lmdj/actions/runs/42",
                "--deployed-at",
                "2026-07-26T10:11:12Z",
                "--output-dir",
                str(output_dir),
                "--github-output",
                str(github_output),
            ],
            check=True,
        )

        notes_file = output_dir / "CHANGELOG-v0.2.0.md"
        self.assertTrue(notes_file.is_file())
        outputs = github_output.read_text()
        self.assertIn("tag=v0.2.0\n", outputs)
        self.assertIn("previous_tag=\n", outputs)
        self.assertIn("existing=false\n", outputs)
        self.assertIn(f"notes_file={notes_file.resolve()}\n", outputs)

    def test_cli_plan_writes_version_without_deployment_metadata(self) -> None:
        target = self.repo.commit("feat: initial product")
        self.repo.set_origin_main()
        github_output = self.repo.path / "github-output"

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--mode",
                "plan",
                "--repo",
                str(self.repo.path),
                "--target-sha",
                target,
                "--github-output",
                str(github_output),
            ],
            check=True,
        )

        outputs = github_output.read_text()
        self.assertIn("tag=v0.2.0\n", outputs)
        self.assertIn("previous_tag=\n", outputs)
        self.assertIn("existing=false\n", outputs)
        self.assertNotIn("notes_file=", outputs)

    def test_cli_render_rejects_expected_tag_drift(self) -> None:
        target = self.repo.commit("feat: initial product")
        self.repo.set_origin_main()

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--mode",
                "render",
                "--repo",
                str(self.repo.path),
                "--target-sha",
                target,
                "--expected-tag",
                "v0.2.1",
                "--repository",
                "endaye/lmdj",
                "--run-url",
                "https://github.com/endaye/lmdj/actions/runs/42",
                "--deployed-at",
                "2026-07-26T10:11:12Z",
                "--output-dir",
                str(self.repo.path / "release-output"),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "expected tag v0.2.1 does not match planned tag v0.2.0",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
