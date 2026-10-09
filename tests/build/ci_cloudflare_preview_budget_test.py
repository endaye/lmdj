import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import cloudflare_preview_budget as budget

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


class FakeGitHub:
    def __init__(self, pages, comments=None):
        self.pages = pages
        self.comments = comments if comments is not None else []
        self.posted = []
        self.queries = []

    def metadata(self, path):
        self.queries.append(path)
        if '/comments' in path:
            return self.comments
        page = int(path.rsplit('&page=', 1)[1])
        runs = self.pages[page - 1] if page <= len(self.pages) else []
        return {'workflow_runs': runs}

    def request(self, path):
        self.posted.append(path)

        class FakeRequest:
            data = None

            def add_header(self, *args):
                pass

        return FakeRequest()


def run_entry(status, duration_ms=None):
    run = {'status': status}
    if duration_ms is not None:
        run['run_duration_ms'] = duration_ms
    return run


class BudgetMinutesTest(unittest.TestCase):
    def test_positive_integer_required(self):
        for value in ('', '0', '-5', 'abc', '10.5'):
            with self.assertRaisesRegex(ValueError, 'CLOUDFLARE_PREVIEW_BUDGET_MINUTES'):
                budget.budget_minutes(value)
        self.assertEqual(budget.budget_minutes('2000'), 2000)


class ConsumptionTest(unittest.TestCase):
    def test_completed_runs_sum_durations(self):
        github = FakeGitHub([[run_entry('completed', 180_000), run_entry('completed', 300_000)]])
        minutes, runs = budget.consumption(github, NOW)
        self.assertEqual((minutes, runs), (8.0, 2))

    def test_unfinished_or_missing_timing_consumes_reservation(self):
        github = FakeGitHub([[run_entry('in_progress'), run_entry('completed')]])
        minutes, runs = budget.consumption(github, NOW)
        self.assertEqual((minutes, runs), (40.0, 2))

    def test_paginates_until_short_page(self):
        github = FakeGitHub([[run_entry('completed', 60_000)] * 100,
                             [run_entry('completed', 60_000)]])
        minutes, runs = budget.consumption(github, NOW)
        self.assertEqual((minutes, runs), (101.0, 101))

    def test_query_is_bounded_to_the_utc_month(self):
        github = FakeGitHub([[]])
        budget.consumption(github, NOW)
        self.assertIn('created=%3E%3D2026-10-01', github.queries[0])


class GateTest(unittest.TestCase):
    def invoke(self, minutes_used, budget_value='100'):
        runs = [run_entry('completed', int(minutes_used * 60_000))]
        github = FakeGitHub([runs])
        with patch.dict(os.environ, {'GITHUB_TOKEN': 't', 'CLOUDFLARE_PREVIEW_BUDGET_MINUTES': budget_value}, clear=True):
            budget.main(['prog', '--gate'], github=github, now=NOW)
        return github

    def test_admits_below_the_stop_threshold(self):
        self.invoke(89.9)

    def test_stops_at_ninety_percent_with_why_and_remedy(self):
        with self.assertRaisesRegex(ValueError, 'budget exhausted.*CLOUDFLARE_PREVIEW_BUDGET_MINUTES'):
            self.invoke(90.0)

    def test_missing_budget_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'CLOUDFLARE_PREVIEW_BUDGET_MINUTES'):
            self.invoke(1.0, budget_value='')


class ReportTest(unittest.TestCase):
    def invoke(self, minutes_used, issue='123', comments=None):
        runs = [run_entry('completed', int(minutes_used * 60_000))]
        github = FakeGitHub([runs], comments=comments or [])
        with patch.dict(os.environ, {'GITHUB_TOKEN': 't',
                                     'CLOUDFLARE_PREVIEW_BUDGET_MINUTES': '100',
                                     'CLOUDFLARE_PREVIEW_BUDGET_ISSUE': issue}, clear=True):
            with patch.object(budget, 'post_comment', side_effect=lambda g, i, body: github.posted.append(body) or 1):
                budget.main(['prog', '--report'], github=github, now=NOW)
        return github

    def test_posts_each_newly_crossed_threshold_once(self):
        github = self.invoke(76.0)
        self.assertEqual(len(github.posted), 2)
        self.assertIn('cloudflare-preview-budget:2026-10:50', github.posted[0])
        self.assertIn('cloudflare-preview-budget:2026-10:75', github.posted[1])

    def test_already_marked_thresholds_are_not_reposted(self):
        github = self.invoke(95.0, comments=[{'body': 'cloudflare-preview-budget:2026-10:50 ...'},
                                             {'body': 'cloudflare-preview-budget:2026-10:75 ...'},
                                             {'body': 'cloudflare-preview-budget:2026-10:90 ...'}])
        self.assertEqual(github.posted, [])

    def test_below_all_thresholds_posts_nothing(self):
        self.assertEqual(self.invoke(49.9).posted, [])

    def test_missing_issue_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'CLOUDFLARE_PREVIEW_BUDGET_ISSUE'):
            self.invoke(95.0, issue='')


if __name__ == '__main__':
    unittest.main()
