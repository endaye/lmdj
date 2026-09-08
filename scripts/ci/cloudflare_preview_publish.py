"""Trusted, preview-only publisher; run only from the default-branch workflow."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, build_opener

from cloudflare_preview_artifact import REPOSITORY, WORKFLOW, extract_static, require
from cloudflare_preview_download import GitHub, NoRedirect, download_verified

ACCOUNT = '0b62b8881c07f48f7935f5380a1f55db'
WORKER = 'portal-preview'
SUBDOMAIN = 'lmdj'
ROOT = Path(__file__).resolve().parents[2]
HEADERS = '/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n'


def current_pr(github, run, number, pilot):
    require(run['repository']['full_name'] == REPOSITORY and
            run['head_repository']['full_name'] == REPOSITORY, 'foreign build repository')
    require(run['path'] == WORKFLOW and run['event'] == 'pull_request', 'unexpected build workflow/event')
    require(pilot and run['head_branch'] == pilot, 'build is outside the configured pilot')
    require(run['status'] == 'completed', 'build is not complete')
    require(any(p['number'] == number and p['head']['sha'] == run['head_sha']
                for p in run['pull_requests']), 'run/PR association mismatch')
    pr = github.metadata(f'/repos/{REPOSITORY}/pulls/{number}')
    require(pr['base']['repo']['full_name'] == REPOSITORY and pr['base']['ref'] == 'main' and
            pr['head']['repo']['full_name'] == REPOSITORY, 'foreign PR source/base')
    if pr['state'] != 'open' or pr['head']['sha'] != run['head_sha']:
        return None
    return pr


def product_build(github, head):
    require(bool(re.fullmatch('[0-9a-f]{40}', head)), 'invalid source SHA')
    blob = github.metadata(f'/repos/{REPOSITORY}/contents/products/lmdj/version.json?ref={head}')
    require(blob['encoding'] == 'base64', 'unexpected Product manifest encoding')
    value = json.loads(base64.b64decode(blob['content'], validate=False))
    require(value['contract'] == 'lmdj.product-version.v1' and value['product'] == 'lmdj',
            'unexpected Product manifest identity')
    parts = [value[k] for k in ('milestone', 'minor', 'build', 'patch')]
    require(all(type(n) is int and n >= 0 for n in parts), 'invalid Product Build parts')
    return '.'.join(map(str, parts))


def post_status(github, head, state, url=None):
    body = {'state': state, 'context': 'Cloudflare Portal Preview',
            'description': 'Exact-head Preview smoke passed' if state == 'success' else 'Preview build or verification failed'}
    if url:
        require(bool(re.fullmatch(r'https://[0-9a-f]{8}-portal-preview\.lmdj\.workers\.dev', url)),
                'foreign Preview URL')
        body['target_url'] = url
    request = github.request(f'/repos/{REPOSITORY}/statuses/{head}')
    request.data = json.dumps(body).encode()
    request.add_header('Content-Type', 'application/json')
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        return json.load(response)['id']


def publish():
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_run', 'publisher requires workflow_run')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'publisher must use main workflow')
    github = GitHub(os.environ['GITHUB_TOKEN'])
    run_id = int(os.environ['PREVIEW_RUN_ID'])
    pilot = os.environ.get('PREVIEW_PILOT_BRANCH', '')
    evidence = {'build_run_id': run_id, 'status': 'started'}
    output = Path(os.environ['RUNNER_TEMP']) / f"cloudflare-preview-{os.environ['GITHUB_RUN_ID']}.json"
    run, number = None, None
    status_attempted = False

    def cf(path, body=None):
        request = Request(f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/' + path,
                          headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN'],
                                   'Content-Type': 'application/json'},
                          data=None if body is None else json.dumps(body).encode())
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            value = json.load(response)
        require(value.get('success'), 'Cloudflare API failed')
        return value['result']

    try:
        run = github.metadata(f'/repos/{REPOSITORY}/actions/runs/{run_id}')
        require(run['id'] == run_id and len(run['pull_requests']) == 1, 'ambiguous build identity')
        number = run['pull_requests'][0]['number']
        if current_pr(github, run, number, pilot) is None:
            evidence['status'] = 'superseded'
            return
        require(run['conclusion'] == 'success', 'build did not succeed')
        require(cf('subdomain')['subdomain'] == SUBDOMAIN, 'unexpected account subdomain')
        exists = WORKER in {s['id'] for s in cf('scripts')}
        if exists:
            require(not cf(f'scripts/{WORKER}/subdomain')['enabled'], 'Preview Worker has a live stable route')
        artifacts = github.metadata(f'/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100')
        require(artifacts['total_count'] <= 100, 'artifact inventory requires reconciliation')
        expected = f"portal-preview-{run['head_sha']}-{run['run_attempt']}"
        matches = [a for a in artifacts['artifacts'] if a['name'] == expected]
        require(len(matches) == 1, 'missing or ambiguous static artifact')
        with tempfile.TemporaryDirectory(prefix='trusted-preview-') as temp:
            temp = Path(temp)
            receipt = download_verified(github, number, run_id, matches[0]['id'], temp / 'static.zip')
            files = extract_static(temp / 'static.zip', temp / 'dist')
            evidence.update(receipt)
            evidence['files'] = files
            build = product_build(github, run['head_sha'])
            evidence['product_build'] = build
            (temp / 'dist/_headers').write_text(HEADERS)
            config = {'name': WORKER, 'account_id': ACCOUNT, 'compatibility_date': '2026-09-08',
                      'workers_dev': False, 'preview_urls': True,
                      'assets': {'directory': str(temp / 'dist'), 'not_found_handling': '404-page'}}
            (temp / 'wrangler.json').write_text(json.dumps(config))
            if current_pr(github, run, number, pilot) is None:
                evidence['status'] = 'superseded'
                return
            env = {k: v for k, v in os.environ.items() if k != 'GITHUB_TOKEN'}
            command = ['node', os.environ['WRANGLER_JS']] + (['versions', 'upload'] if exists else ['deploy'])
            result = subprocess.run(command + ['--config', str(temp / 'wrangler.json')], cwd=temp,
                                    env=env, capture_output=True, text=True, timeout=300)
            require(result.returncode == 0, 'Preview upload failed; reconcile versions before retry')
            match = re.search(r'(?:Worker|Current) Version ID: ([0-9a-f-]{36})', result.stdout + result.stderr)
            require(match and re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', match[1]),
                    'upload returned no valid version receipt')
            version = match[1]
            evidence['version_id'] = version
            route = cf(f'scripts/{WORKER}/subdomain')
            require(not route['enabled'] and route['previews_enabled'], 'unexpected Preview route state')
            url = f'https://{version[:8]}-{WORKER}.{SUBDOMAIN}.workers.dev'
            evidence['url'] = url
            manifest = temp / 'smoke.json'
            manifest.write_text(json.dumps({'url': url, 'product_build': build,
                                           'head_sha': run['head_sha'], 'files': files}))
            smoke_env = {k: v for k, v in os.environ.items() if k not in {'GITHUB_TOKEN', 'CLOUDFLARE_API_TOKEN'}}
            subprocess.run(['node', str(ROOT / 'apps/docs-site/scripts/cloudflare-preview-smoke.mjs'),
                            str(manifest)], env=smoke_env, check=True, timeout=600)
            if current_pr(github, run, number, pilot) is None:
                evidence['status'] = 'superseded'
                return
            status_attempted = True
            evidence['status_id'] = post_status(github, run['head_sha'], 'success', url)
            evidence['status'] = 'passed'
    except BaseException as error:
        evidence['status'] = 'status-receipt-unknown' if status_attempted else 'failed'
        evidence['error_class'] = type(error).__name__
        if run is not None and number is not None and not status_attempted:
            try:
                if current_pr(github, run, number, pilot) is not None:
                    status_attempted = True
                    evidence['status_id'] = post_status(github, run['head_sha'], 'failure')
            except BaseException:
                evidence['failure_status_receipt'] = 'unconfirmed'
        # Avoid writing signed download URLs, CLI output or credentials to logs.
        raise RuntimeError('Preview failed; inspect retained sanitized evidence and reconcile before retry') from None
    finally:
        output.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    publish()
