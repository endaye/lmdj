import os
from datetime import datetime, timedelta, timezone
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


def run_entry(status, duration_ms=None, updated_at='2026-10-05T00:00:00Z',
              conclusion='success', attempt=1):
    # Shaped like the Actions runs list, which has no run_duration_ms: timing
    # is only run_started_at (latest attempt) and updated_at.
    run = {'status': status, 'updated_at': updated_at, 'run_attempt': attempt,
           'conclusion': conclusion if status == 'completed' else None}
    if duration_ms is not None:
        started = budget.parse_instant(updated_at) - timedelta(milliseconds=duration_ms)
        run['run_started_at'] = started.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    return run


# Verbatim timing fields of the three newest real runs on 2026-10-10.
LIVE_RUNS = [
    {'status': 'completed', 'conclusion': 'failure', 'run_attempt': 1,
     'run_started_at': '2026-10-10T01:30:00Z', 'updated_at': '2026-10-10T01:30:24Z'},
    {'status': 'completed', 'conclusion': 'skipped', 'run_attempt': 1,
     'run_started_at': '2026-10-10T00:56:57Z', 'updated_at': '2026-10-10T00:56:58Z'},
    {'status': 'completed', 'conclusion': 'skipped', 'run_attempt': 1,
     'run_started_at': '2026-10-10T00:51:52Z', 'updated_at': '2026-10-10T00:51:53Z'},
]


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

    def test_live_runs_list_bills_wall_time_and_skips_nothing_run(self):
        # The runs list has no run_duration_ms; reading it as missing timing
        # charged every skipped run a 20-minute reservation (7,520 phantom
        # minutes on 2026-10-10). Oracle: 24 s for the one executed run.
        github = FakeGitHub([LIVE_RUNS])
        minutes, runs = budget.consumption(github, datetime(2026, 10, 10, 2, tzinfo=timezone.utc))
        self.assertEqual((round(minutes * 60), runs), (24, 1))

    def test_rerun_reserves_each_earlier_attempt(self):
        github = FakeGitHub([[run_entry('completed', 120_000, attempt=3)]])
        self.assertEqual(budget.consumption(github, NOW), (42.0, 1))

    def test_paginates_until_short_page(self):
        github = FakeGitHub([[run_entry('completed', 60_000)] * 100,
                             [run_entry('completed', 60_000)]])
        minutes, runs = budget.consumption(github, NOW)
        self.assertEqual((minutes, runs), (101.0, 101))

    def test_query_reaches_runs_queued_a_full_day_before_the_month(self):
        # A job may stay queued 24 hours and then run 20 minutes, so a run
        # created on 09-29 can still be unfinished on 10-01.
        github = FakeGitHub([[]])
        budget.consumption(github, NOW)
        self.assertIn('created=%3E%3D2026-09-29', github.queries[0])

    def test_run_completed_last_month_is_not_billed_this_month(self):
        github = FakeGitHub([[run_entry('completed', 600_000, updated_at='2026-09-30T23:59:59Z')]])
        self.assertEqual(budget.consumption(github, NOW), (0.0, 0))

    def test_run_completed_after_midnight_counts_full_duration(self):
        # Created last month, finished inside the new month: its minutes bill
        # the new month, so the full duration counts (review finding 2).
        github = FakeGitHub([[run_entry('completed', 600_000, updated_at='2026-10-01T00:00:01Z')]])
        self.assertEqual(budget.consumption(github, NOW), (10.0, 1))

    def test_last_months_unfinished_run_still_consumes_reservation(self):
        github = FakeGitHub([[run_entry('in_progress', updated_at='2026-09-30T23:59:00Z')]])
        self.assertEqual(budget.consumption(github, NOW), (20.0, 1))

    def test_concurrent_admissions_are_bounded_by_reservations(self):
        # Review finding 1: every admitted build already exists as a queued or
        # in-progress run, so a same-window burst consumes reservations and
        # trips the stop rather than overshooting the budget.
        github = FakeGitHub([[run_entry('in_progress')] * 5])
        with patch.dict(os.environ, {'GITHUB_TOKEN': 't', 'CLOUDFLARE_PREVIEW_BUDGET_MINUTES': '100'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                budget.main(['prog', '--gate'], github=github, now=NOW)
        github = FakeGitHub([[run_entry('in_progress')] * 4])
        with patch.dict(os.environ, {'GITHUB_TOKEN': 't', 'CLOUDFLARE_PREVIEW_BUDGET_MINUTES': '100'}, clear=True):
            budget.main(['prog', '--gate'], github=github, now=NOW)


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

    def test_marker_scan_reads_only_this_months_comments(self):
        # An operations Issue with years of comments must not reach the scan bound.
        github = self.invoke(10.0)
        scans = [query for query in github.queries if '/comments' in query]
        self.assertEqual(len(scans), 1)
        self.assertIn('since=2026-10-01T00:00:00Z', scans[0])

    def test_below_all_thresholds_posts_nothing(self):
        self.assertEqual(self.invoke(49.9).posted, [])

    def test_missing_issue_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'CLOUDFLARE_PREVIEW_BUDGET_ISSUE'):
            self.invoke(95.0, issue='')


if __name__ == '__main__':
    unittest.main()
