#!/usr/bin/env python3
"""The budget report is a quality instrument, so its own readings are tested."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_budget_report as report


CTEST = """
 1/3 Test  #1: fast.one .................   Passed    0.10 sec
 2/3 Test  #2: slow.two .................   Passed   21.00 sec
 3/3 Test  #3: over.three ...............***Timeout  30.05 sec

Total Test time (real) = 100.00 sec
"""


class ParseTest(unittest.TestCase):
    def test_reads_passing_and_timing_out_tests_alike(self) -> None:
        observations, total = report.parse_run(CTEST, {})
        self.assertEqual(total, 100.0)
        self.assertEqual([o.name for o in observations],
                         ["fast.one", "slow.two", "over.three"])
        # A timeout is the case the report exists to surface, so it must not be
        # dropped for failing to match the "Passed" shape.
        self.assertEqual(observations[2].status, "Timeout")
        self.assertEqual(observations[2].seconds, 30.05)

    def test_used_share_is_measured_against_the_declared_budget(self) -> None:
        observations, _ = report.parse_run(CTEST, {"slow.two": 30.0})
        self.assertAlmostEqual(observations[1].used, 70.0)
        # A test with no declared budget reports nothing rather than guessing.
        self.assertIsNone(observations[0].used)

    def test_multipliers_match_the_cmake_contract(self) -> None:
        # Coverage getting no multiplier is why it is the tightest budget in
        # the repository; that asymmetry is the whole reason for this tool.
        self.assertEqual(report.SANITIZER_MULTIPLIER["coverage"], 1)
        self.assertEqual(report.SANITIZER_MULTIPLIER["address"], 3)
        self.assertEqual(report.SANITIZER_MULTIPLIER["thread"], 4)


class BudgetSourceTest(unittest.TestCase):
    def test_budgets_come_from_the_repository_declarations(self) -> None:
        root = Path(__file__).resolve().parents[2]
        budgets = report.declared_budgets(root, 1)
        # Reading real declarations rather than a fixture keeps the tool honest
        # when a tier or an explicit TIMEOUT changes.
        self.assertIn("facade.application", budgets)
        self.assertEqual(budgets["facade.application"], 30)
        self.assertEqual(report.declared_budgets(root, 3)["facade.application"], 90)


class RegistrationParserTest(unittest.TestCase):
    """Every lmdj_add_test call is read whole, whatever its layout (#2238)."""

    def _budgets(self, cmake: str) -> dict[str, float]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cmake").mkdir()
            (root / "cmake/LmdjTesting.cmake").write_text(
                "set(lmdj_test_timeout_unit 10)\n"
                "set(lmdj_test_timeout_component 30)\n", encoding="utf-8")
            (root / "CMakeLists.txt").write_text(cmake, encoding="utf-8")
            return report.declared_budgets(root, 1)

    def test_closing_parenthesis_on_its_own_line(self) -> None:
        budgets = self._budgets(
            "lmdj_add_test(\n  NAME a.own_line\n  TIER unit\n"
            "  COMMAND a\n  TIMEOUT 7\n)\n")
        self.assertEqual(budgets, {"a.own_line": 7})

    def test_closing_parenthesis_on_the_last_argument_line(self) -> None:
        # The layout the former pattern missed: it needed ')' on its own line,
        # so it ran on into the next call, lost this TIMEOUT to that call's
        # and never saw the next registration at all.
        budgets = self._budgets(
            "lmdj_add_test(NAME a.inline TIER component\n"
            "  COMMAND a TIMEOUT 12)\n"
            "lmdj_add_test(NAME b.single TIER unit COMMAND b)\n"
            "lmdj_add_test(\n  NAME c.own_line\n  TIER component\n"
            "  COMMAND c\n  TIMEOUT 99\n)\n")
        self.assertEqual(budgets, {"a.inline": 12, "b.single": 10, "c.own_line": 99})

    def test_parentheses_inside_arguments_do_not_end_the_call(self) -> None:
        budgets = self._budgets(
            'lmdj_add_test(NAME a.nested TIER unit\n'
            '  COMMAND a "$<IF:$<CONFIG:Debug>,x)y,(z>" [[bracket ) text]]\n'
            '  # a comment with ) in it\n'
            '  LABELS (grouped) TIMEOUT 5)\n')
        self.assertEqual(budgets, {"a.nested": 5})

    def test_call_text_inside_strings_and_comments_registers_nothing(self) -> None:
        budgets = self._budgets(
            '# lmdj_add_test(NAME commented.out TIER unit COMMAND x)\n'
            'message(STATUS "lmdj_add_test(NAME quoted.out TIER unit COMMAND x)")\n'
            '#[[ lmdj_add_test(NAME bracket.out TIER unit COMMAND x) ]]\n'
            'function(lmdj_add_test)\nendfunction()\n'
            'LMDJ_ADD_TEST (NAME real.one TIER unit COMMAND x)\n')
        self.assertEqual(budgets, {"real.one": 10})

    def test_a_timeout_the_scan_cannot_evaluate_has_no_budget(self) -> None:
        # Reporting the tier default instead would state a wrong budget.
        budgets = self._budgets(
            "lmdj_add_test(NAME a.var TIER unit COMMAND a TIMEOUT ${budget})\n")
        self.assertEqual(budgets, {})

    def test_a_loop_registration_budgets_every_name_it_expands_to(self) -> None:
        budgets = {"platform.lcd.${scenario}": 30.0, "platform.lcd.exact": 5.0}
        self.assertEqual(report.budget_for("platform.lcd.flush", budgets), 30.0)
        self.assertEqual(report.budget_for("platform.lcd.exact", budgets), 5.0)
        self.assertIsNone(report.budget_for("platform.lcd.", budgets))
        self.assertIsNone(report.budget_for("other.lcd.flush", budgets))

    def test_the_more_specific_loop_registration_wins(self) -> None:
        budgets = {"a.witness_${group}": 120.0, "a.witness_task_${task}": 300.0}
        self.assertEqual(report.budget_for("a.witness_task_crash", budgets), 300.0)
        self.assertEqual(report.budget_for("a.witness_schema", budgets), 120.0)

    def test_equally_specific_loop_registrations_that_disagree_are_unknown(self) -> None:
        # Both loops can produce this name and the scan cannot tell which did,
        # so naming either budget could be wrong.
        budgets = {"a.prep_${case}": 180.0, "a.prep_${group}": 120.0}
        self.assertIsNone(report.budget_for("a.prep_JourneyTest", budgets))
        agreeing = {"a.prep_${case}": 120.0, "a.prep_${group}": 120.0}
        self.assertEqual(report.budget_for("a.prep_JourneyTest", agreeing), 120.0)

    def test_every_call_in_the_repository_is_read(self) -> None:
        # Independent oracle: a line-anchored count of call sites, which shares
        # no code with the balanced scan. Every call site must yield exactly
        # one registration with a NAME and a TIER.
        root = Path(__file__).resolve().parents[2]
        sites = 0
        parsed = 0
        for path in root.rglob("CMakeLists.txt"):
            relative = path.relative_to(root).as_posix()
            if relative.startswith(("build/", ".worktrees/")):
                continue
            text = path.read_text(encoding="utf-8")
            sites += sum(1 for line in text.splitlines()
                         if line.lstrip().startswith("lmdj_add_test("))
            for arguments in report.cmake_calls(text, "lmdj_add_test"):
                fields = report.registration_fields(arguments)
                if fields.get("NAME") and fields.get("TIER"):
                    parsed += 1
        self.assertGreater(sites, 0)
        self.assertEqual(parsed, sites)

    def test_single_line_facade_registrations_have_budgets(self) -> None:
        # The two registrations #2238 found invisible to the report.
        root = Path(__file__).resolve().parents[2]
        budgets = report.declared_budgets(root, 1)
        self.assertEqual(budgets["facade.pattern_count_in"], 30)
        self.assertEqual(budgets["facade.pattern_transport_controller"], 30)


class NormalisationTest(unittest.TestCase):
    """The distinction the tool exists to make: slower test or slower machine."""

    def _run(self, log: str, baseline: dict | None) -> str:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "ctest.log"
            log_path.write_text(log, encoding="utf-8")
            argv = ["prog", "--ctest-log", str(log_path), "--sanitizer", "coverage",
                    "--repo-root", str(Path(__file__).resolve().parents[2])]
            if baseline is not None:
                base_path = Path(directory) / "baseline.json"
                base_path.write_text(json.dumps(baseline), encoding="utf-8")
                argv += ["--baseline", str(base_path)]
            from contextlib import redirect_stdout
            import io
            buffer = io.StringIO()
            saved, sys.argv = sys.argv, argv
            try:
                with redirect_stdout(buffer):
                    report.main()
            finally:
                sys.argv = saved
            return buffer.getvalue()

    def test_a_uniformly_slower_machine_flags_nothing(self) -> None:
        # Every test doubled and so did the suite: nothing regressed.
        log = (" 1/2 Test  #1: a.one ....   Passed    4.00 sec\n"
               " 2/2 Test  #2: a.two ....   Passed    8.00 sec\n"
               "Total Test time (real) = 12.00 sec\n")
        output = self._run(log, {"total_seconds": 6.0,
                                 "tests": {"a.one": 2.0, "a.two": 4.0}})
        self.assertIn("machine speed versus baseline: ×2.00", output)
        self.assertIn("no test is slower than the machine explains", output)

    def test_one_test_regressing_is_separated_from_the_machine(self) -> None:
        # The suite doubled, but a.two quadrupled: only that one regressed.
        log = (" 1/2 Test  #1: a.one ....   Passed    4.00 sec\n"
               " 2/2 Test  #2: a.two ....   Passed   16.00 sec\n"
               "Total Test time (real) = 20.00 sec\n")
        output = self._run(log, {"total_seconds": 10.0,
                                 "tests": {"a.one": 2.0, "a.two": 4.0}})
        self.assertIn("slower than the machine explains", output)
        self.assertIn("a.two", output)
        self.assertNotIn("  a.one", output.split("slower than")[1])

    def test_sub_second_tests_are_not_compared(self) -> None:
        # Process start-up dominates them, so their ratios are noise that would
        # bury the real signal.
        log = (" 1/1 Test  #1: tiny.one ....   Passed    0.40 sec\n"
               "Total Test time (real) = 1.00 sec\n")
        output = self._run(log, {"total_seconds": 1.0, "tests": {"tiny.one": 0.01}})
        self.assertIn("no test is slower than the machine explains", output)

    def test_report_never_fails_the_build(self) -> None:
        # A guardrail that can stop a Pull Request is one more source of the
        # randomness it exists to remove.
        log = (" 1/1 Test  #1: over.one ....***Timeout   99.00 sec\n"
               "Total Test time (real) = 99.00 sec\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ctest.log"
            path.write_text(log, encoding="utf-8")
            saved, sys.argv = sys.argv, [
                "prog", "--ctest-log", str(path), "--sanitizer", "coverage",
                "--repo-root", str(Path(__file__).resolve().parents[2])]
            try:
                self.assertEqual(report.main(), 0)
            finally:
                sys.argv = saved


if __name__ == "__main__":
    unittest.main()
