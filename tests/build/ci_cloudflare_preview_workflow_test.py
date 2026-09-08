from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class BuildBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / '.github/workflows/cloudflare-preview-build.yml').read_text()
        self.workflow = yaml.load(self.raw, Loader=yaml.BaseLoader)
        self.job = self.workflow['jobs']['build']

    def test_only_pr_events_and_exact_opt_in_branch(self):
        self.assertEqual(set(self.workflow['on']), {'pull_request'})
        condition = self.job['if']
        self.assertIn("vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH != ''", condition)
        self.assertIn('github.head_ref == vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH', condition)
        self.assertIn('github.event.pull_request.head.repo.full_name == github.repository', condition)

    def test_untrusted_build_cannot_reuse_privileged_runner(self):
        self.assertEqual(self.job['runs-on'], 'ubuntu-24.04')
        self.assertNotIn('environment', self.job)
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        self.assertNotIn('secrets.', self.raw)
        self.assertNotIn('CLOUDFLARE_API_TOKEN', self.raw)

    def test_no_persistent_checkout_credentials(self):
        checkouts = [s for s in self.job['steps'] if s.get('uses', '').startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 2)
        for checkout in checkouts:
            self.assertEqual(checkout['with']['persist-credentials'], 'false')
        self.assertEqual(checkouts[1]['with']['ref'], '${{ github.event.pull_request.head.sha }}')

    def test_artifact_identity_matches_consumer_contract(self):
        upload = next(s for s in self.job['steps'] if s.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['with']['name'], 'portal-preview-${{ github.event.pull_request.head.sha }}-${{ github.run_attempt }}')
        self.assertTrue(upload['with']['path'].endswith('/static.zip'))
        self.assertEqual(upload['with']['if-no-files-found'], 'error')


class PublisherBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.load((ROOT / '.github/workflows/cloudflare-preview-publish.yml').read_text(), Loader=yaml.BaseLoader)
        self.job = self.workflow['jobs']['publish']

    def test_only_default_branch_workflow_run_control(self):
        self.assertEqual(set(self.workflow['on']), {'workflow_run'})
        checkout = next(s for s in self.job['steps'] if s.get('uses', '').startswith('actions/checkout@'))
        self.assertEqual(checkout['with']['ref'], '${{ github.workflow_sha }}')
        self.assertEqual(checkout['with']['persist-credentials'], 'false')
        self.assertIn("vars.CLOUDFLARE_PREVIEW_PILOT_BRANCH != ''", self.job['if'])

    def test_deploy_secret_only_enters_trusted_publish_step(self):
        holders = [s for s in self.job['steps'] if 'CLOUDFLARE_API_TOKEN' in s.get('env', {})]
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0]['run'], 'python3 scripts/ci/cloudflare_preview_publish.py')
        self.assertEqual(self.job['environment'], 'portal-cloudflare-preview')
        install = next(s for s in self.job['steps'] if s.get('name', '').startswith('Install trusted'))
        self.assertNotIn('env', install)
        self.assertEqual(self.workflow['concurrency']['cancel-in-progress'], 'false')


if __name__ == '__main__':
    unittest.main()
