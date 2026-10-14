"""Monthly hosted-budget gate and alert ledger for Cloudflare Portal Preview.

--gate runs inside the untrusted build job from the trusted base checkout with
read-only Actions access; --report runs from the daily trusted monitor workflow
and posts threshold alerts to the operations Issue. Neither mode ever sees a
deployment credential.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import build_opener

from cloudflare_preview_artifact import REPOSITORY, require
from cloudflare_preview_download import GitHub, NoRedirect

WORKFLOW = 'cloudflare-preview-build.yml'
RESERVE_SECONDS = 20 * 60  # the build job's full timeout-minutes
# GitHub fails a job still queued after 24 hours and the build times out after
# 20 minutes, so no unfinished run can have been created earlier than this
# before the month began.
UNFINISHED_LOOKBACK = timedelta(days=2)
ALERTS = (50, 75, 90)
STOP_PERCENT = 90
# GitHub returns at most 1,000 runs for a listing filtered by `created`; later
# pages come back empty, so a capped window would silently undercount.
SEARCH_CAP = 1000
# A window under the cap needs at most 10 pages; kept explicit so editing
# SEARCH_CAP cannot silently move the reconciliation bound.
MAX_PAGES = 10
# Bounded retry for transient read failures (5xx, 429, rate-limit 403; real
# runs failed on HTTP 502 and 403). The total wait per read never exceeds
# READ_WAIT_BUDGET_SECONDS, even when Retry-After asks for longer; a read still
# failing then fails closed.
READ_ATTEMPTS = 5
BACKOFF_SECONDS = (5, 15, 30, 60)
MAX_WAIT_SECONDS = 60
READ_WAIT_BUDGET_SECONDS = 110


def budget_minutes(value):
    require(value and re.fullmatch(r'[0-9]+', value) and int(value) > 0,
            'why: CLOUDFLARE_PREVIEW_BUDGET_MINUTES is not a positive integer; '
            'remedy: set the repository variable to the approved monthly hosted-minute budget')
    return int(value)


def month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def parse_instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def completed_ms(run):
    earlier = max(int(run.get('run_attempt') or 1) - 1, 0) * RESERVE_SECONDS * 1000
    if not run.get('run_started_at'):
        return earlier + RESERVE_SECONDS * 1000
    elapsed = parse_instant(run['updated_at']) - parse_instant(run['run_started_at'])
    return earlier + max(elapsed.total_seconds(), 0) * 1000


def consumption(github, now):
    """Month-to-date hosted minutes by billed-time overlap, not creation date.

    A completed run counts when it finished inside the month (its minutes bill
    this month), whenever it was created. The runs list carries no billed
    duration, so a completed run costs the wall time from its latest attempt's
    start to completion, which includes any queue wait and so never undercounts
    the single build job; each earlier attempt, whose timing the list no longer
    shows, costs a full reservation, and so does missing timing. A skipped run
    executed no job and bills nothing. A run still queued or in progress consumes the full timeout
    reservation, so every same-window concurrent admission is itself already a
    visible reservation and a burst is what trips the 90% stop. The residual is
    API indexing latency between run creation and listing, bounded by the 10%
    stop margin (200 of 2000 minutes = ten concurrent reservations) before any
    overshoot is possible.
    """
    start = month_start(now)
    first = (start - UNFINISHED_LOOKBACK).date()
    minutes = 0.0
    runs = 0
    for run in window_runs(github, first, now.date() + timedelta(days=1)):
        if run['status'] != 'completed':
            minutes += RESERVE_SECONDS * 1000
            runs += 1
        elif parse_instant(run['updated_at']) >= start and run.get('conclusion') != 'skipped':
            minutes += completed_ms(run)
            runs += 1
    return minutes / 60000, runs


def window_query(first, last):
    return f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs?created={first}..{last}&per_page=100&page='


def window_runs(github, first, last):
    """Every run created on UTC dates first..last, split below the listing cap."""
    query = window_query(first, last)
    data = read(github, query + '1')
    total = data.get('total_count')
    require(type(total) is int and total >= 0, 'run listing has no total_count')
    if total >= SEARCH_CAP:
        require(first < last,
                f'why: {total} Preview build runs were created on {first}, at or above the {SEARCH_CAP}-result '
                f'listing cap, so the monthly count cannot be exact; '
                f'remedy: investigate the run burst and reconcile the budget by hand before admitting builds')
        middle = first + (last - first) // 2
        return window_runs(github, first, middle) + window_runs(github, middle + timedelta(days=1), last)
    collected = []
    page = 1
    while True:
        batch = data['workflow_runs']
        collected.extend(batch)
        if len(batch) < 100:
            return collected
        page += 1
        require(page <= MAX_PAGES, 'run inventory exceeds reconciliation bound')
        data = read(github, query + str(page))


def transient(error):
    if isinstance(error, HTTPError):
        if error.code >= 500 or error.code == 429:
            return True
        headers = error.headers or {}
        return error.code == 403 and (headers.get('Retry-After') is not None
                                      or headers.get('X-RateLimit-Remaining') == '0')
    return isinstance(error, (URLError, TimeoutError))


def read(github, path, sleep=time.sleep):
    """GET with bounded retry; a permission 403 or 4xx fails at once."""
    waited = 0
    for attempt in range(READ_ATTEMPTS):
        try:
            return github.metadata(path)
        except Exception as error:
            remaining = READ_WAIT_BUDGET_SECONDS - waited
            if attempt + 1 == READ_ATTEMPTS or remaining <= 0 or not transient(error):
                raise
            wait = BACKOFF_SECONDS[attempt]
            retry_after = getattr(error, 'headers', None) and error.headers.get('Retry-After')
            if retry_after and retry_after.isdigit():
                wait = max(wait, int(retry_after))
            wait = min(wait, MAX_WAIT_SECONDS, remaining)
            sleep(wait)
            waited += wait


def post_comment(github, issue, body):
    request = github.request(f'/repos/{REPOSITORY}/issues/{issue}/comments')
    request.data = json.dumps({'body': body}).encode()
    request.add_header('Content-Type', 'application/json')
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        return json.load(response)['id']


def existing_markers(github, issue, since):
    # Only this month's markers matter, and a comment written this month cannot
    # have been updated before the month began, so a busy operations Issue's
    # history never reaches the reconciliation bound.
    markers = set()
    page = 1
    stamp = since.strftime('%Y-%m-%dT%H:%M:%SZ')
    while True:
        comments = read(github, f'/repos/{REPOSITORY}/issues/{issue}/comments'
                                f'?since={stamp}&per_page=100&page={page}')
        for comment in comments:
            markers.update(re.findall(r'cloudflare-preview-budget:[0-9]{4}-[0-9]{2}:[0-9]{2}',
                                      comment.get('body') or ''))
        if len(comments) < 100:
            return markers
        page += 1
        require(page <= 20, 'comment inventory exceeds reconciliation bound')


def gate(github, budget, now):
    minutes, runs = consumption(github, now)
    stop = budget * STOP_PERCENT / 100
    require(minutes < stop,
            f'why: monthly Cloudflare Preview hosted budget exhausted '
            f'({minutes:.1f} of {budget} minutes across {runs} runs; new builds stop at {STOP_PERCENT}%); '
            f'remedy: record a new budget decision and raise CLOUDFLARE_PREVIEW_BUDGET_MINUTES, '
            f'or wait for the next UTC month; never bypass this gate to admit builds')
    print(f'cloudflare preview budget: {minutes:.1f}/{budget} minutes ({runs} runs), '
          f'admitting build below {STOP_PERCENT}% stop')


def report(github, budget, issue, now):
    require(issue and re.fullmatch(r'[0-9]+', issue) and int(issue) > 0,
            'why: CLOUDFLARE_PREVIEW_BUDGET_ISSUE is not a positive Issue number; '
            'remedy: point the repository variable at the operations Issue receiving budget alerts')
    minutes, runs = consumption(github, now)
    month = now.strftime('%Y-%m')
    markers = existing_markers(github, int(issue), month_start(now))
    for threshold in ALERTS:
        marker = f'cloudflare-preview-budget:{month}:{threshold:02d}'
        if minutes * 100 >= budget * threshold and marker not in markers:
            post_comment(github, int(issue),
                         f'{marker}\n\nCloudflare Portal Preview monthly hosted consumption crossed '
                         f'{threshold}% of the approved budget: {minutes:.1f} of {budget} minutes '
                         f'across {runs} runs in {month} (UTC). New builds stop automatically at '
                         f'{STOP_PERCENT}%. Record any new budget decision before raising '
                         f'CLOUDFLARE_PREVIEW_BUDGET_MINUTES.')
            markers.add(marker)
    print(f'cloudflare preview budget report: {minutes:.1f}/{budget} minutes ({runs} runs) in {month}')


def main(argv, github=None, now=None):
    require(len(argv) == 2 and argv[1] in ('--gate', '--report'),
            'usage: cloudflare_preview_budget.py (--gate|--report)')
    now = now or datetime.now(timezone.utc)
    github = github or GitHub(os.environ['GITHUB_TOKEN'])
    budget = budget_minutes(os.environ.get('CLOUDFLARE_PREVIEW_BUDGET_MINUTES', ''))
    if argv[1] == '--gate':
        gate(github, budget, now)
    else:
        report(github, budget, os.environ.get('CLOUDFLARE_PREVIEW_BUDGET_ISSUE', ''), now)


if __name__ == '__main__':
    main(sys.argv)
