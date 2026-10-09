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
from datetime import datetime, timezone
from urllib.request import build_opener

from cloudflare_preview_artifact import REPOSITORY, require
from cloudflare_preview_download import GitHub, NoRedirect

WORKFLOW = 'cloudflare-preview-build.yml'
RESERVE_SECONDS = 20 * 60  # the build job's full timeout-minutes
ALERTS = (50, 75, 90)
STOP_PERCENT = 90


def budget_minutes(value):
    require(value and re.fullmatch(r'[0-9]+', value) and int(value) > 0,
            'why: CLOUDFLARE_PREVIEW_BUDGET_MINUTES is not a positive integer; '
            'remedy: set the repository variable to the approved monthly hosted-minute budget')
    return int(value)


def month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def consumption(github, now):
    """Month-to-date hosted minutes: completed durations plus full reservations."""
    created = month_start(now).strftime('%Y-%m-%d')
    minutes = 0.0
    runs = 0
    page = 1
    while True:
        data = github.metadata(f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs'
                               f'?created=%3E%3D{created}&per_page=100&page={page}')
        batch = data['workflow_runs']
        for run in batch:
            runs += 1
            # Missing timing consumes the full reservation, like the pilot ledger.
            if run['status'] == 'completed' and run.get('run_duration_ms'):
                minutes += run['run_duration_ms']
            else:
                minutes += RESERVE_SECONDS * 1000
        if len(batch) < 100:
            return minutes / 60000, runs
        page += 1
        require(page <= 20, 'run inventory exceeds reconciliation bound')


def post_comment(github, issue, body):
    request = github.request(f'/repos/{REPOSITORY}/issues/{issue}/comments')
    request.data = json.dumps({'body': body}).encode()
    request.add_header('Content-Type', 'application/json')
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        return json.load(response)['id']


def existing_markers(github, issue):
    markers = set()
    page = 1
    while True:
        comments = github.metadata(f'/repos/{REPOSITORY}/issues/{issue}/comments?per_page=100&page={page}')
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
    markers = existing_markers(github, int(issue))
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
