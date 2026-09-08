import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import cloudflare_preview_publish as publisher


class FakeGitHub:
    def __init__(self, token='read-token'):
        repo = {'full_name': 'endaye/lmdj'}
        self.head = 'a' * 40
        self.pr = {'number': 1, 'state': 'open', 'head': {'sha': self.head, 'repo': repo},
                   'base': {'ref': 'main', 'repo': repo}}
        self.run = {'id': 2, 'repository': repo, 'head_repository': repo,
                    'head_sha': self.head, 'head_branch': 'pilot', 'path': publisher.WORKFLOW,
                    'status': 'completed', 'conclusion': 'success', 'event': 'pull_request',
                    'run_attempt': 1, 'pull_requests': [{'number': 1, 'head': {'sha': self.head}}]}

    def metadata(self, path):
        if '/pulls/' in path:
            return self.pr
        if '/contents/' in path:
            return {'encoding': 'base64', 'content': base64.b64encode(json.dumps({
                'contract': 'lmdj.product-version.v1', 'product': 'lmdj', 'milestone': 1,
                'minor': 0, 'build': 44, 'patch': 0}).encode()).decode()}
        if path.endswith('artifacts?per_page=100'):
            return {'total_count': 1, 'artifacts': [{'id': 3, 'name': f'portal-preview-{self.head}-1'}]}
        return self.run


class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.github = FakeGitHub()
        self.requests = []
        self.statuses = []
        self.commands = []
        self.fail_smoke = False
        self.move_during_smoke = False
        self.live_route = False
        self.new_target = False
        self.unknown_status_receipt = False
        self.env = {'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_TOKEN': 'read-token', 'CLOUDFLARE_API_TOKEN': 'deploy-token',
                    'PREVIEW_RUN_ID': '2', 'PREVIEW_PILOT_BRANCH': 'pilot',
                    'RUNNER_TEMP': self.temp.name, 'GITHUB_RUN_ID': '10', 'WRANGLER_JS': '/trusted/cli.js'}

    def open(self, request, timeout):
        self.requests.append(request)
        path = request.full_url.split('/workers/')[1]
        if path == 'subdomain':
            result = {'subdomain': 'lmdj'}
        elif path == 'scripts':
            result = [] if self.new_target else [{'id': 'portal-preview'}]
        else:
            self.assertEqual(path, 'scripts/portal-preview/subdomain')
            result = {'enabled': self.live_route, 'previews_enabled': True}
        return io.BytesIO(json.dumps({'success': True, 'result': result}).encode())

    def extract(self, archive, destination):
        destination.mkdir()
        return []

    def command(self, argv, **kwargs):
        self.commands.append(argv)
        if argv[1].endswith('cloudflare-preview-smoke.mjs'):
            self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
            self.assertNotIn('CLOUDFLARE_API_TOKEN', kwargs['env'])
            if self.move_during_smoke:
                self.github.pr['head']['sha'] = 'b' * 40
            if self.fail_smoke:
                raise subprocess.CalledProcessError(1, argv)
        else:
            self.assertEqual(argv[2:3] if self.new_target else argv[2:4], ['deploy'] if self.new_target else ['versions', 'upload'])
            self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
            config = json.loads(Path(argv[-1]).read_text())
            self.assertFalse(config['workers_dev'])
            self.assertNotIn('build', config)
            self.assertNotIn('main', config)
            return subprocess.CompletedProcess(argv, 0, 'Worker Version ID: 12345678-1234-1234-1234-123456789abc', '')

    def post(self, github, head, state, url=None):
        self.statuses.append((head, state, url))
        if self.unknown_status_receipt:
            raise TimeoutError('receipt lost')
        return 100

    def invoke(self):
        with patch.dict(os.environ, self.env, clear=True), patch.object(publisher, 'GitHub', return_value=self.github), \
             patch.object(publisher, 'build_opener', return_value=self), \
             patch.object(publisher, 'download_verified', return_value={'head_sha': self.github.head}), \
             patch.object(publisher, 'extract_static', side_effect=self.extract), \
             patch.object(publisher.subprocess, 'run', side_effect=self.command), \
             patch.object(publisher, 'post_status', side_effect=self.post):
            publisher.publish()

    def evidence(self):
        return json.loads((Path(self.temp.name) / 'cloudflare-preview-10.json').read_text())

    def test_success_publishes_only_verified_version_url(self):
        self.invoke()
        self.assertEqual(self.statuses, [(self.github.head, 'success', 'https://12345678-portal-preview.lmdj.workers.dev')])
        self.assertTrue(all(r.get_method() == 'GET' for r in self.requests))
        self.assertEqual(self.evidence()['status'], 'passed')

    def test_failed_smoke_cannot_publish_success(self):
        self.fail_smoke = True
        with self.assertRaisesRegex(RuntimeError, 'Preview failed'):
            self.invoke()
        self.assertEqual([s[1] for s in self.statuses], ['failure'])

    def test_head_changed_during_smoke_does_not_get_status(self):
        self.move_during_smoke = True
        self.invoke()
        self.assertEqual(self.statuses, [])
        self.assertEqual(self.evidence()['status'], 'superseded')

    def test_live_stable_route_prevents_upload(self):
        self.live_route = True
        with self.assertRaisesRegex(RuntimeError, 'Preview failed'):
            self.invoke()
        self.assertEqual(self.commands, [])

    def test_failed_build_does_not_touch_cloudflare(self):
        self.github.run['conclusion'] = 'failure'
        with self.assertRaisesRegex(RuntimeError, 'Preview failed'):
            self.invoke()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.commands, [])
        self.assertEqual([s[1] for s in self.statuses], ['failure'])

    def test_unknown_success_status_receipt_is_not_retried(self):
        self.unknown_status_receipt = True
        with self.assertRaisesRegex(RuntimeError, 'Preview failed'):
            self.invoke()
        self.assertEqual(len(self.statuses), 1)
        self.assertEqual(self.evidence()['status'], 'status-receipt-unknown')

    def test_initial_target_deploy_keeps_stable_route_disabled(self):
        self.new_target = True
        self.invoke()
        self.assertEqual(self.evidence()['status'], 'passed')
        self.assertTrue(all(r.get_method() == 'GET' for r in self.requests))

    def test_foreign_status_url_rejected_before_api_write(self):
        with self.assertRaisesRegex(ValueError, 'foreign Preview URL'):
            publisher.post_status(self.github, self.github.head, 'success', 'https://foreign.example')


if __name__ == '__main__':
    unittest.main()
