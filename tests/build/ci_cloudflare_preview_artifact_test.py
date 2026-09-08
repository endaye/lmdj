import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview', ROOT / 'scripts/ci/cloudflare_preview_artifact.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.head = 'a' * 40
        repo = {'full_name': 'endaye/lmdj'}
        self.pr = {'number': 922, 'state': 'open', 'head': {'sha': self.head, 'repo': repo},
                   'base': {'ref': 'main', 'repo': repo}}
        self.run = {'id': 123, 'run_attempt': 2, 'repository': repo, 'head_repository': repo,
                    'path': preview.WORKFLOW, 'event': 'pull_request', 'status': 'completed',
                    'conclusion': 'success', 'head_sha': self.head,
                    'pull_requests': [{'number': 922, 'head': {'sha': self.head}}]}
        self.artifact = {'id': 456, 'workflow_run': {'id': 123, 'head_sha': self.head},
                         'name': f'portal-preview-{self.head}-2', 'expired': False, 'size_in_bytes': 100}

    def test_current_head_receipt(self):
        self.assertEqual(preview.validate_identity(self.run, self.pr, self.artifact)['head_sha'], self.head)

    def test_stale_completion(self):
        self.pr['head']['sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'stale'):
            preview.validate_identity(self.run, self.pr, self.artifact)

    def test_unsuccessful_build(self):
        self.run['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'did not succeed'):
            preview.validate_identity(self.run, self.pr, self.artifact)

    def test_foreign_head_repository(self):
        self.pr['head']['repo'] = {'full_name': 'foreign/lmdj'}
        with self.assertRaisesRegex(ValueError, 'external PR'):
            preview.validate_identity(self.run, self.pr, self.artifact)

    def test_old_attempt_artifact(self):
        self.artifact['name'] = f'portal-preview-{self.head}-1'
        with self.assertRaisesRegex(ValueError, 'attempt'):
            preview.validate_identity(self.run, self.pr, self.artifact)

    def test_other_run_artifact(self):
        self.artifact['workflow_run']['id'] = 124
        with self.assertRaisesRegex(ValueError, 'another run'):
            preview.validate_identity(self.run, self.pr, self.artifact)


class StaticZipTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'static.zip'
        self.destination = self.root / 'extracted'

    def write(self, extra=None):
        with ZipFile(self.archive, 'w') as zipped:
            zipped.writestr('index.html', b'index')
            zipped.writestr('404.html', b'not found')
            if extra:
                zipped.writestr(*extra)

    def test_exact_bytes_and_manifest(self):
        self.write(('assets/app.js', b'window.app = true'))
        manifest = preview.extract_static(self.archive, self.destination)
        self.assertEqual((self.destination / 'assets/app.js').read_bytes(), b'window.app = true')
        self.assertEqual([e['path'] for e in manifest], ['404.html', 'assets/app.js', 'index.html'])
        self.assertEqual(manifest[2]['sha256'], '1bc04b5291c26a46d918139138b992d2de976d6851d0893b0476b85bfbdfc6e6')

    def test_traversal_never_creates_output(self):
        self.write(('../escape', b'bad'))
        with self.assertRaisesRegex(ValueError, 'unsafe ZIP path'):
            preview.extract_static(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root / 'escape').exists())

    def test_symlink_never_creates_output(self):
        link = ZipInfo('assets/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write((link, b'/etc/passwd'))
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            preview.extract_static(self.archive, self.destination)
        self.assertFalse(self.destination.exists())

    def test_config_is_not_executable_input(self):
        self.write(('wrangler.json', b'{"build":{"command":"steal"}}'))
        with self.assertRaisesRegex(ValueError, 'configuration'):
            preview.extract_static(self.archive, self.destination)

    def test_expansion_budget(self):
        self.write(('large.js', b'x' * 20))
        old = preview.MAX_TOTAL_BYTES
        preview.MAX_TOTAL_BYTES = 30
        self.addCleanup(setattr, preview, 'MAX_TOTAL_BYTES', old)
        with self.assertRaisesRegex(ValueError, 'expanded static archive'):
            preview.extract_static(self.archive, self.destination)

    def test_existing_output_is_preserved(self):
        self.write()
        self.destination.mkdir()
        (self.destination / 'existing').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            preview.extract_static(self.archive, self.destination)
        self.assertEqual((self.destination / 'existing').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
