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


if __name__ == '__main__':
    unittest.main()
