#!/usr/bin/env python3
"""Operator commands for signed Cloudflare Hosts; internal local observations only."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from cloudflare_api import ACCOUNT, TARGETS, CloudflareClient, CloudflareError, version_id
from cloudflare_headers import render
from cloudflare_run_store import RunStore, StoreError, TERMINAL
from cloudflare_smoke import smoke
from cloudflare_transaction import promote, TransactionError

ROOT = Path(__file__).resolve().parents[3]
HOSTS = {'creator-web': 'creator-web', 'creator-recovery': 'creator-web',
         'web-runtime-host': 'web-runtime-host', 'runtime-recovery': 'web-runtime-host'}
SCRIPTS = {'creator-web': 'creator-web-deploy.sh', 'web-runtime-host': 'web-runtime-deploy.sh'}


class CommandError(RuntimeError):
    def __init__(self, why):
        super().__init__('why: ' + why + '; remedy: preserve local receipts and reconcile the exact target before retrying')


def child_environment(*, github=False, cloudflare=False):
    # Deployment children never receive the other provider's credential.
    env = {k: v for k, v in os.environ.items()
           if not any(word in k.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD'))
           and not k.startswith(('CLOUDFLARE_', 'WRANGLER_', 'GH_', 'GITHUB_'))}
    if github:
        env['GITHUB_TOKEN'] = os.environ.get('GITHUB_TOKEN', '')
    if cloudflare:
        env.update(CLOUDFLARE_API_TOKEN=os.environ.get('CLOUDFLARE_API_TOKEN', ''),
                   CLOUDFLARE_ACCOUNT_ID=ACCOUNT, WRANGLER_SEND_METRICS='false', CI='true')
    return env


def stage(tag, host, workspace):
    out = workspace / host
    result = subprocess.run(['bash', str(ROOT/'scripts'/SCRIPTS[host]), 'stage', tag, str(out)],
                            cwd=ROOT, env=child_environment(github=True),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    diagnostic = result.stdout + result.stderr
    for name in ('GITHUB_TOKEN', 'CLOUDFLARE_API_TOKEN'):
        secret = os.environ.get(name)
        if secret:
            diagnostic = diagnostic.replace(secret, '[REDACTED]')
    log = workspace/'stage-verification.log'
    log.write_text(diagnostic[-1024 * 1024:])
    if result.returncode:
        raise CommandError('fresh signed release staging failed; inspect ' + str(log))
    receipt = json.loads((out/'stage.json').read_text())
    if receipt.get('tag') != tag or receipt.get('host_id') != host:
        raise CommandError('signed staging returned another tag or Host')
    return out, receipt


def upload_receipt(path, worker, *, initialize=False):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise CommandError('Wrangler upload receipt unavailable or too large')
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    expected_type = 'deploy' if initialize else 'version-upload'
    uploads = [r for r in rows if isinstance(r, dict) and r.get('type') == expected_type]
    if len(uploads) != 1 or any(not isinstance(r, dict) or r.get('type') == 'error' for r in rows):
        raise CommandError('Wrangler upload did not yield one positive receipt')
    row = uploads[0]
    if type(row.get('version')) is not int or row['version'] != 1 or row.get('worker_name') != worker:
        raise CommandError('Wrangler receipt names another Worker or format')
    value = version_id(row.get('version_id'))
    expected = f'https://{value[:8]}-{worker}.lmdj.workers.dev'
    if not initialize and (not isinstance(row.get('preview_url'), str) or row['preview_url'].rstrip('/') != expected):
        raise CommandError('Wrangler receipt has an unexpected version Preview URL')
    return value


def upload(args, dist, workspace, worker):
    node = Path(args.node).resolve(strict=True)
    wrangler = Path(args.wrangler).resolve(strict=True)
    package = json.loads((wrangler.parent.parent/'package.json').read_text())
    if not isinstance(package, dict) or package.get('name') != 'wrangler' or package.get('version') != '4.129.1':
        raise CommandError('upload requires pinned Wrangler 4.129.1')
    node_version = subprocess.check_output([str(node), '--version'], env=child_environment(), text=True).strip()
    if node_version != 'v22.16.0':
        raise CommandError('upload requires pinned Node 22.16.0')
    assets = workspace/'assets'
    shutil.copytree(dist, assets)
    (assets/'_headers').write_bytes(render(dist))
    worker_file = workspace/'worker.mjs'
    shutil.copyfile(ROOT/'apps/web-runtime-host/deploy/cloudflare_worker.mjs', worker_file)
    config = workspace/'wrangler.json'
    config.write_text(json.dumps({'name': worker, 'account_id': ACCOUNT,
        'main': str(worker_file), 'compatibility_date': '2026-09-08',
        'workers_dev': False, 'preview_urls': True,
        'assets': {'directory': str(assets), 'binding': 'ASSETS', 'run_worker_first': ['/'],
                   'html_handling': 'none', 'not_found_handling': 'none'}}))
    output = workspace/'wrangler-output.jsonl'
    env = child_environment(cloudflare=True)
    env['WRANGLER_OUTPUT_FILE_PATH'] = str(output)
    try:
        command = ['deploy'] if args.initialize else ['versions', 'upload']
        result = subprocess.run([str(node), str(wrangler), *command, '--config', str(config)],
                                cwd=workspace, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise CommandError('upload outcome unknown') from None
    if result.returncode:
        raise CommandError('upload outcome unknown')
    return upload_receipt(output, worker, initialize=args.initialize)


def candidate(client, store, *, uploader, verifier, initialize=False):
    if initialize:
        if client.exists():
            raise CommandError('initialization requires a positively absent Worker')
        prior, route = None, None
    else:
        prior, route = client.deployment(), client.route()
        if not route['previews_enabled']:
            raise CommandError('version previews must be enabled before candidate upload')
    store.observe({'event': 'candidate-upload-starting', 'prior': prior, 'prior_route': route,
                   'initialize': initialize})
    # An exception after this intent leaves the journal unfinished, never retried.
    value = version_id(uploader())
    store.observe({'event': 'candidate-uploaded', 'version': value})
    client.require_version(value)
    if initialize:
        prior, route = client.deployment(), client.route()
        if prior['version_id'] != value or route != {'enabled': False, 'previews_enabled': True}:
            raise CommandError('initialization did not retain the candidate with its stable route disabled')
        store.observe({'event': 'initialized', 'deployment': prior, 'route': route})
    if client.deployment() != prior or client.route() != route:
        raise CommandError('production changed during candidate upload')
    url = f'https://{value[:8]}-{client.worker}.lmdj.workers.dev'
    if verifier(value, url) is not True:
        raise CommandError('candidate HTTP verification failed')
    if client.deployment() != prior or client.route() != route:
        raise CommandError('production changed during candidate verification')
    store.observe({'event': 'passed', 'version': value, 'preview_url': url})
    store.finish()
    return {'version_id': value, 'preview_url': url}


@contextmanager
def command_store(root, worker, operation):
    with RunStore(root, worker) as store:
        if operation not in {'verify', 'inspect', 'reconcile'}:
            store.start(operation)
        try:
            yield store
        except Exception:
            rows = store.records()
            if operation not in {'verify', 'inspect', 'reconcile'} and rows and rows[-1]['data']['event'] != 'run-finished':
                run_id = rows[-1]['run_id']
                events = {r['data']['event'] for r in rows if r['run_id'] == run_id}
                if not events.intersection({'candidate-upload-starting', 'publication-starting',
                                            'route-starting', 'recovery-starting'}):
                    store.observe({'event': 'failed-before-publication'})
                    store.finish()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('candidate', 'verify', 'promote', 'recover', 'inspect', 'reconcile'))
    parser.add_argument('tag', nargs='?')
    parser.add_argument('--target', required=True, choices=sorted(TARGETS))
    parser.add_argument('--state-root', required=True, type=Path)
    parser.add_argument('--version')
    parser.add_argument('--initialize', action='store_true', help='candidate only: explicitly create an absent Worker with stable route disabled')
    parser.add_argument('--prior-tag')
    parser.add_argument('--node', help='absolute path to Node 22.16.0 (candidate only)')
    parser.add_argument('--wrangler', help='absolute path to Wrangler 4.129.1 bin/wrangler.js (candidate only)')
    parser.add_argument('--absent', action='store_true', help='reconcile only: require positive Worker absence')
    parser.add_argument('--expected-run')
    parser.add_argument('--expected-sequence', type=int)
    parser.add_argument('--expected-deployment')
    parser.add_argument('--route', choices=('enabled', 'disabled'))
    args = parser.parse_args(argv)
    try:
        if not args.state_root.is_absolute():
            raise CommandError('state root must be absolute and shared by all local operators')
        if args.initialize and args.command != 'candidate':
            raise CommandError('initialization is only valid for candidate')
        if args.absent and (args.command != 'reconcile' or any((args.tag, args.version, args.expected_deployment, args.route))):
            raise CommandError('absence reconciliation cannot name a release, version, deployment or route')
        if args.command != 'inspect' and not args.absent and not args.tag:
            raise CommandError('explicit signed tag is required')
        if args.command == 'reconcile' and (not all((args.expected_run, args.expected_sequence)) or (not args.absent and not all((args.expected_deployment, args.route)))):
            raise CommandError('reconcile requires exact run, sequence, deployment and route expectations')
        if args.command == 'candidate':
            if not args.node or not args.wrangler or args.version:
                raise CommandError('candidate requires pinned Node and Wrangler paths and no version argument')
            if not Path(args.node).is_absolute() or not Path(args.wrangler).is_absolute():
                raise CommandError('Node and Wrangler paths must be absolute')
        elif args.command != 'inspect' and not args.absent and not args.version:
            raise CommandError('exact Cloudflare version is required')
        elif args.version:
            args.version = version_id(args.version)
        client = CloudflareClient(token=os.environ.get('CLOUDFLARE_API_TOKEN'), target=args.target)
        with command_store(args.state_root, client.worker, args.command) as store:
            if args.command == 'inspect':
                exists = client.exists()
                print(json.dumps({'worker': client.worker, 'exists': exists,
                                  'deployment': client.deployment() if exists else None,
                                  'route': client.route() if exists else None, 'records': store.records()}, sort_keys=True))
                return 0
            if args.command == 'reconcile' and args.absent:
                if client.exists() or client.exists():
                    raise CommandError('Worker is not positively absent')
                store.reconcile_absent(run_id=args.expected_run, sequence=args.expected_sequence)
                print(json.dumps({'worker': client.worker, 'reconciled': True, 'absent': True}))
                return 0
            workspace = Path(tempfile.mkdtemp(prefix=client.worker+'-', dir=args.state_root))
            staged, receipt = stage(args.tag, HOSTS[args.target], workspace)
            recovery = args.target.endswith('-recovery')
            def verify_dist(dist, url):
                try:
                    smoke(dist, url, preview=url != f'https://{client.worker}.lmdj.workers.dev', recovery_target=recovery)
                except Exception:
                    raise CommandError('exact signed HTTP verification failed') from None
                return True
            if args.command == 'reconcile':
                expected = {'id': version_id(args.expected_deployment), 'version_id': args.version}
                route = {'enabled': args.route == 'enabled', 'previews_enabled': True}
                if client.deployment() != expected or client.route() != route:
                    raise CommandError('live state does not match explicit reconciliation expectations')
                client.require_version(args.version)
                verify_dist(staged/'dist', f'https://{args.version[:8]}-{client.worker}.lmdj.workers.dev')
                if route['enabled']:
                    verify_dist(staged/'dist', f'https://{client.worker}.lmdj.workers.dev')
                if client.deployment() != expected or client.route() != route:
                    raise CommandError('live state changed during reconciliation verification')
                store.reconcile(run_id=args.expected_run, sequence=args.expected_sequence,
                                deployment=expected, route=route, tag=args.tag)
                result = {'reconciled': True, 'deployment': expected, 'route': route}
            elif args.command == 'verify':
                client.require_version(args.version)
                verify_dist(staged/'dist', f'https://{args.version[:8]}-{client.worker}.lmdj.workers.dev')
                result = {'version_id': args.version, 'verified': True}
            else:
                store.observe({'event': 'signed-input', 'tag': args.tag, 'source': receipt['source'],
                               'archive': receipt['archive'], 'stage': str(staged)})
                if args.command == 'candidate':
                    result = candidate(client, store,
                        uploader=lambda: upload(args, staged/'dist', workspace, client.worker),
                        verifier=lambda value, url: verify_dist(staged/'dist', url), initialize=args.initialize)
                else:
                    prior = client.deployment()
                    distributions = {args.version: staged/'dist'}
                    if client.route()['enabled'] and prior['version_id'] != args.version:
                        if not args.prior_tag:
                            raise CommandError('enabled production requires its signed prior tag for recovery verification')
                        old_workspace = workspace/'prior'; old_workspace.mkdir(mode=0o700)
                        old, old_receipt = stage(args.prior_tag, HOSTS[args.target], old_workspace)
                        distributions[prior['version_id']] = old/'dist'
                        store.observe({'event': 'signed-prior-input', 'tag': args.prior_tag,
                                       'source': old_receipt['source'], 'version': prior['version_id'], 'stage': str(old)})
                    def verify(value, url):
                        if value not in distributions:
                            raise CommandError('version has no verified signed distribution')
                        return verify_dist(distributions[value], url)
                    try:
                        result = promote(client, candidate=args.version, verify=verify, observe=store.observe)
                    except TransactionError:
                        if store.records()[-1]['data']['event'] in TERMINAL:
                            store.finish()
                        raise
                    store.finish()
            print(json.dumps({'worker': client.worker, 'tag': args.tag, 'result': result, 'workspace': str(workspace)}, sort_keys=True))
        return 0
    except (CommandError, CloudflareError, StoreError, TransactionError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        message = str(error) if str(error).startswith('why:') else str(CommandError('command input, tool execution or retained receipt is invalid'))
        print(message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
