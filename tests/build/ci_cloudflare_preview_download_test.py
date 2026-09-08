import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import cloudflare_preview_download as download
from cloudflare_preview_artifact import WORKFLOW


class FakeGitHub:
    def __init__(self):
        head = 'a' * 40
        repo = {'full_name': 'endaye/lmdj'}
        self.pr = {'number': 1, 'state': 'open', 'base': {'ref': 'main', 'repo': repo},
                   'head': {'sha': head, 'repo': repo}}
        self.run = {'id': 2, 'run_attempt': 1, 'repository': repo, 'head_repository': repo,
                    'path': WORKFLOW, 'event': 'pull_request', 'status': 'completed',
                    'conclusion': 'success', 'head_sha': head,
                    'pull_requests': [{'number': 1, 'head': {'sha': head}}]}
        self.artifact = {'id': 3, 'workflow_run': {'id': 2, 'head_sha': head},
                         'name': f'portal-preview-{head}-1', 'expired': False, 'size_in_bytes': 200}
        self.pr_reads = 0
        self.move_head = False
        self.url_reads = 0

    def metadata(self, path):
        if path.endswith('/pulls/1'):
            self.pr_reads += 1
            result = copy.deepcopy(self.pr)
            if self.move_head and self.pr_reads > 1:
                result['head']['sha'] = 'b' * 40
            return result
        return self.run if path.endswith('/runs/2') else self.artifact

    def archive_url(self, artifact_id):
        self.url_reads += 1
        return 'https://artifact.example/static?signature=private'


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'static.zip'
        self.github = FakeGitHub()
        self.name = 'static.zip'
        self.payload = b'inner archive bytes'
        self.requests = []

    def transport(self, request, timeout):
        self.requests.append(request)
        content = io.BytesIO()
        with ZipFile(content, 'w') as zipped:
            zipped.writestr(self.name, self.payload)
        content.seek(0)
        return content

    def run_download(self):
        return download.download_verified(self.github, 1, 2, 3, self.target, self.transport)

    def test_authenticated_selection_and_credential_free_storage_request(self):
        receipt = self.run_download()
        self.assertEqual(receipt['artifact_id'], 3)
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(self.requests[0].header_items(), [])
        self.assertEqual(self.github.pr_reads, 2)

    def test_head_update_during_download_does_not_expose_output(self):
        self.github.move_head = True
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_download()
        self.assertFalse(self.target.exists())

    def test_foreign_run_never_requests_download_url(self):
        self.github.artifact['workflow_run']['id'] = 4
        with self.assertRaisesRegex(ValueError, 'another run'):
            self.run_download()
        self.assertEqual(self.github.url_reads, 0)

    def test_transport_path_is_not_extracted(self):
        self.name = '../static.zip'
        with self.assertRaisesRegex(ValueError, 'exactly static.zip'):
            self.run_download()
        self.assertFalse(self.target.exists())

    def test_stream_limit_rejects_before_writing_excess(self):
        output = io.BytesIO()
        with self.assertRaisesRegex(ValueError, 'exceeds limit'):
            download.copy_bounded(io.BytesIO(b'12345'), output, 4)
        self.assertLessEqual(len(output.getvalue()), 4)

    def test_existing_output_is_preserved(self):
        self.target.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_download()
        self.assertEqual(self.target.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
